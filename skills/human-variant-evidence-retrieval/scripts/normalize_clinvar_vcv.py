# SPDX-License-Identifier: Apache-2.0
"""Normalize bounded ClinVar VCV XML without interpreting clinical meaning."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit


VERSION = "0.9.0"
MAX_IDENTIFIERS = 5
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_TOTAL_INPUT_BYTES = 32 * 1024 * 1024
MAX_PROVENANCE_BYTES = 1024 * 1024
MAX_ELEMENTS = 250_000
MAX_TREE_DEPTH = 32
VCV_PATTERN = re.compile(r"VCV([0-9]{9})(?:\.([1-9][0-9]*))?")
VARIATION_ID_PATTERN = re.compile(r"[1-9][0-9]{0,8}")
SCV_PATTERN = re.compile(r"SCV[0-9]{9}")
RCV_PATTERN = re.compile(r"RCV[0-9]{9}")
POSITIVE_VERSION_PATTERN = re.compile(r"[1-9][0-9]*")
UTC_TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z"
)
DATE_ATTRIBUTE = re.compile(r"date|submission|updated|created", re.IGNORECASE)
PROVIDER_FAILURE_TAGS = frozenset(
    {"diagnostic", "diagnostics", "error", "errorlist", "errors", "warning", "warninglist", "warnings"}
)


class InputError(ValueError):
    """A bounded input or provider-response contract was violated."""


class ProviderFailure(RuntimeError):
    """The provider returned an explicit error or warning envelope."""


def local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def compact_text(element: ET.Element) -> str | None:
    text = " ".join("".join(element.itertext()).split())
    return text or None


def sorted_attributes(element: ET.Element) -> dict[str, str]:
    return {key: element.attrib[key] for key in sorted(element.attrib)}


def normalized_element(element: ET.Element, depth: int = 0) -> dict[str, Any]:
    if depth > MAX_TREE_DEPTH:
        raise InputError("ClinVar XML exceeds the supported nesting depth")
    result: dict[str, Any] = {"tag": local_name(element.tag)}
    if element.attrib:
        result["attributes"] = sorted_attributes(element)
    direct_text = " ".join((element.text or "").split())
    if direct_text:
        result["text"] = direct_text
    children = [normalized_element(child, depth + 1) for child in list(element)]
    if children:
        result["children"] = children
    return result


def direct_child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in list(element) if local_name(child.tag) == name), None)


def descendants(element: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in element.iter() if local_name(item.tag) == name]


def dates_from(attributes: dict[str, str]) -> dict[str, str]:
    return {key: attributes[key] for key in sorted(attributes) if DATE_ATTRIBUTE.search(key)}


def parse_identifier(value: str) -> dict[str, Any]:
    if VARIATION_ID_PATTERN.fullmatch(value):
        number = int(value)
        return {
            "input": value,
            "kind": "variation_id",
            "variation_id": value,
            "vcv_accession": f"VCV{number:09d}",
            "requested_version": None,
        }
    match = VCV_PATTERN.fullmatch(value)
    if match:
        digits, version = match.groups()
        number = int(digits)
        if number == 0:
            raise InputError("VCV accession cannot encode Variation ID zero")
        return {
            "input": value,
            "kind": "vcv_accession",
            "variation_id": str(number),
            "vcv_accession": f"VCV{digits}",
            "requested_version": version,
        }
    raise InputError(
        f"unsupported identifier {value!r}; use a positive numeric Variation ID "
        "or uppercase VCV plus nine digits and optional version"
    )


def validate_identifiers(values: list[str]) -> list[dict[str, Any]]:
    if not 1 <= len(values) <= MAX_IDENTIFIERS:
        raise InputError("provide between one and five exact ClinVar identifiers")
    parsed = [parse_identifier(value) for value in values]
    keys = [item["variation_id"] for item in parsed]
    if len(keys) != len(set(keys)):
        raise InputError("request each Variation ID or equivalent VCV at most once")
    return parsed


def read_regular(path: Path, label: str, limit: int) -> bytes:
    if path.is_symlink():
        raise InputError(f"{label} is a symlink")
    flags = os.O_RDONLY | os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise InputError(f"cannot open {label} as a regular non-symlink file: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise InputError(f"{label} is not a regular file")
        if before.st_size > limit:
            raise InputError(f"{label} exceeds the {limit}-byte limit")
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > limit:
                raise InputError(f"{label} exceeds the {limit}-byte limit")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise InputError(f"{label} changed while it was read")
        return bytes(payload)
    finally:
        os.close(descriptor)


def json_without_duplicate_keys(payload: bytes, label: str) -> dict[str, Any]:
    def object_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise InputError(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=object_hook)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise InputError(f"{label} must contain one JSON object")
    return value


def validate_request_url(url: str, identifier: dict[str, Any]) -> None:
    if any(ord(character) < 33 or ord(character) > 126 for character in url):
        raise InputError("provenance request URL must use printable ASCII")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise InputError("provenance request URL authority is invalid") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "eutils.ncbi.nlm.nih.gov"
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.path != "/entrez/eutils/efetch.fcgi"
    ):
        raise InputError("provenance request is not the reviewed NCBI EFetch endpoint")
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    values: dict[str, list[str]] = {}
    for key, value in pairs:
        values.setdefault(key, []).append(value)
    allowed = {"db", "rettype", "id", "is_variationid", "from_esearch", "retmode"}
    if not set(values).issubset(allowed) or any(len(items) != 1 for items in values.values()):
        raise InputError("provenance request has unsupported or duplicate query parameters")
    if values.get("db") != ["clinvar"] or values.get("rettype") != ["vcv"]:
        raise InputError("provenance request is not a ClinVar VCV retrieval")
    if "retmode" in values and values["retmode"] != ["xml"]:
        raise InputError("ClinVar VCV retmode must be xml when present")
    if values.get("id") != [identifier["input"]]:
        raise InputError("provenance request identifier differs from the declared identifier")
    if identifier["kind"] == "variation_id":
        if values.get("is_variationid") != ["true"] or values.get("from_esearch") != ["true"]:
            raise InputError(
                "numeric Variation ID retrieval requires is_variationid=true "
                "and from_esearch=true"
            )
    elif "is_variationid" in values or "from_esearch" in values:
        raise InputError("VCV accession retrieval must not use Variation-ID query flags")


def utc_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not UTC_TIMESTAMP_PATTERN.fullmatch(value):
        raise InputError(f"{label} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InputError(f"{label} must be an ISO-8601 UTC timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise InputError(f"{label} must be an ISO-8601 UTC timestamp")
    return parsed


def validate_provenance(
    payload_path: Path,
    payload: bytes,
    provenance_payload: bytes,
    identifier: dict[str, Any],
) -> dict[str, Any]:
    label = f"provenance for {payload_path.name}"
    provenance = json_without_duplicate_keys(provenance_payload, label)
    expected_hash = hashlib.sha256(payload).hexdigest()
    expected_fields = {
        "bytes",
        "completed_at",
        "execution_mode",
        "max_response_bytes",
        "method",
        "network_performed",
        "optional_api_key_applied",
        "optional_contact_applied",
        "output_file",
        "pages",
        "paid_use_authorized",
        "provider_documentation",
        "provider_id",
        "request_urls",
        "responses",
        "schema_version",
        "sha256",
        "started_at",
        "terms_acknowledged",
    }
    if set(provenance) != expected_fields:
        raise InputError(f"{label} fields differ from connector schema 0.1.0")
    if provenance.get("schema_version") != "0.1.0":
        raise InputError(f"{label} has an unsupported connector schema")
    if provenance.get("provider_id") != "ncbi-eutils":
        raise InputError(f"{label} does not name ncbi-eutils")
    if provenance.get("provider_documentation") != "https://www.ncbi.nlm.nih.gov/books/NBK25497/":
        raise InputError(f"{label} has unexpected provider documentation")
    if (
        provenance.get("method") != "GET"
        or provenance.get("network_performed") is not True
        or provenance.get("execution_mode") != "live-public-read-only"
    ):
        raise InputError(f"{label} does not record a completed public GET")
    if provenance.get("sha256") != expected_hash or provenance.get("bytes") != len(payload):
        raise InputError(f"{label} does not bind the payload bytes")
    if type(provenance.get("bytes")) is not int:
        raise InputError(f"{label} payload byte count is not an integer")
    if provenance.get("output_file") != payload_path.name:
        raise InputError(f"{label} output filename differs from the payload filename")
    if provenance.get("pages") != 1 or type(provenance.get("pages")) is not int:
        raise InputError(f"{label} must record one connector page")
    max_response_bytes = provenance.get("max_response_bytes")
    if (
        type(max_response_bytes) is not int
        or not len(payload) <= max_response_bytes <= MAX_PAYLOAD_BYTES
    ):
        raise InputError(f"{label} has an invalid response-byte boundary")
    if (
        provenance.get("optional_contact_applied") is not False
        or provenance.get("optional_api_key_applied") is not False
        or provenance.get("terms_acknowledged") is not False
        or provenance.get("paid_use_authorized") is not False
    ):
        raise InputError(f"{label} is not an anonymous free no-terms connector read")
    started_at = provenance.get("started_at")
    completed_at = provenance.get("completed_at")
    if utc_timestamp(started_at, f"{label} started_at") > utc_timestamp(
        completed_at, f"{label} completed_at"
    ):
        raise InputError(f"{label} completes before it starts")
    request_urls = provenance.get("request_urls")
    responses = provenance.get("responses")
    if not isinstance(request_urls, list) or len(request_urls) != 1 or not isinstance(request_urls[0], str):
        raise InputError(f"{label} must record one request URL")
    validate_request_url(request_urls[0], identifier)
    if not isinstance(responses, list) or len(responses) != 1 or not isinstance(responses[0], dict):
        raise InputError(f"{label} must record one response")
    response = responses[0]
    if set(response) != {
        "content_type",
        "etag",
        "last_modified",
        "page_value",
        "response_url",
        "status",
    }:
        raise InputError(f"{label} response fields differ from connector schema 0.1.0")
    if type(response.get("status")) is not int or response.get("status") != 200:
        raise InputError(f"{label} did not record HTTP 200")
    response_url = response.get("response_url")
    if not isinstance(response_url, str):
        raise InputError(f"{label} does not record the accepted response URL")
    validate_request_url(response_url, identifier)
    content_type = response.get("content_type")
    media_type = (
        content_type.split(";", 1)[0].strip().lower()
        if isinstance(content_type, str)
        else ""
    )
    if media_type not in {"application/xml", "text/xml"} and not media_type.endswith("+xml"):
        raise InputError(f"{label} does not record an XML response content type")
    for optional_header in ("etag", "last_modified"):
        if response.get(optional_header) is not None and not isinstance(
            response.get(optional_header), str
        ):
            raise InputError(f"{label} response {optional_header} is invalid")
    if "page_value" not in response or response.get("page_value") is not None:
        raise InputError(f"{label} response is not a single unpaginated read")
    return {
        "payload_file": payload_path.name,
        "payload_bytes": len(payload),
        "payload_sha256": expected_hash,
        "provenance_sha256": hashlib.sha256(provenance_payload).hexdigest(),
        "provider_id": "ncbi-eutils",
        "execution_mode": provenance.get("execution_mode"),
        "completed_at": completed_at,
        "response_status": 200,
        "endpoint_class": "efetch-vcv",
        "requested_identifier": identifier["input"],
    }


def parse_xml(payload: bytes, label: str) -> ET.Element:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError(f"{label} must be UTF-8 XML") from exc
    declaration = re.match(r"<\?xml\s+([^?]*)\?>", text, re.IGNORECASE)
    if declaration is not None:
        encoding = re.search(
            r"\bencoding\s*=\s*(['\"])([^'\"]+)\1",
            declaration.group(1),
            re.IGNORECASE,
        )
        if encoding is not None and encoding.group(2).lower().replace("_", "-") not in {
            "utf-8",
            "utf8",
        }:
            raise InputError(f"{label} must declare UTF-8 when an XML encoding is present")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
        raise InputError(f"{label} contains a forbidden DTD or entity declaration")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise InputError(f"{label} is not well-formed XML") from exc
    if local_name(root.tag) != "ClinVarResult-Set":
        raise InputError(f"{label} is not a ClinVar VCV result set")
    if sum(1 for _ in root.iter()) > MAX_ELEMENTS:
        raise InputError(f"{label} exceeds the supported element count")
    for child in list(root):
        tag = local_name(child.tag)
        if tag == "VariationArchive":
            continue
        if tag.casefold() in PROVIDER_FAILURE_TAGS:
            raise ProviderFailure(
                f"{label} contains a ClinVar provider {tag} envelope"
            )
        raise InputError(
            f"{label} contains an unexpected ClinVar direct child "
            f"{tag} (provider schema drift)"
        )
    return root


def normalize_classification(classification: ET.Element) -> dict[str, Any]:
    review_statuses = [
        value for item in descendants(classification, "ReviewStatus")
        if (value := compact_text(item)) is not None
    ]
    terms: list[dict[str, Any]] = []
    for item in list(classification):
        tag = local_name(item.tag)
        value = compact_text(item)
        if (
            tag in {"ReviewStatus", "Citation", "Comment", "Explanation"}
            or value is None
            or len(item) > 0
        ):
            continue
        terms.append({"type": tag, "value": value, "attributes": sorted_attributes(item)})
    return {
        "review_statuses": review_statuses,
        "classification_terms": terms,
        "provider_subtree": normalized_element(classification),
    }


def normalize_assertion(assertion: ET.Element) -> dict[str, Any]:
    assertion_id = assertion.attrib.get("ID")
    accession = next(iter(descendants(assertion, "ClinVarAccession")), None)
    classification = direct_child(assertion, "Classification")
    if not assertion_id or accession is None or classification is None:
        raise InputError("a ClinVar ClinicalAssertion lacks ID, SCV accession, or Classification")
    scv = accession.attrib.get("Accession")
    scv_version = accession.attrib.get("Version")
    if not scv or not SCV_PATTERN.fullmatch(scv):
        raise InputError("a ClinVar ClinicalAssertion has an invalid SCV accession")
    if not scv_version or not POSITIVE_VERSION_PATTERN.fullmatch(scv_version):
        raise InputError("a ClinVar ClinicalAssertion has an invalid SCV version")
    condition_nodes = [
        item for item in assertion.iter()
        if local_name(item.tag) in {"TraitSet", "ClassifiedConditionList"}
    ]
    assertion_type = direct_child(assertion, "Assertion")
    record_status = direct_child(assertion, "RecordStatus")
    return {
        "assertion_id": assertion_id,
        "scv_accession": scv,
        "scv_version": scv_version,
        "submitter_name": accession.attrib.get("SubmitterName"),
        "organization_category": accession.attrib.get("OrganizationCategory"),
        "record_status": compact_text(record_status) if record_status is not None else None,
        "assertion_type": compact_text(assertion_type) if assertion_type is not None else None,
        "contributes_to_aggregate_classification": assertion.attrib.get(
            "ContributesToAggregateClassification"
        ),
        "dates": {
            "clinical_assertion": dates_from(assertion.attrib),
            "scv": dates_from(accession.attrib),
            "classification": dates_from(classification.attrib),
        },
        "classification": normalize_classification(classification),
        "conditions": [normalized_element(item) for item in condition_nodes],
    }


def normalize_record(archive: ET.Element) -> dict[str, Any]:
    variation_id = archive.attrib.get("VariationID")
    accession = archive.attrib.get("Accession")
    version = archive.attrib.get("Version")
    if not variation_id or not VARIATION_ID_PATTERN.fullmatch(variation_id):
        raise InputError("VariationArchive lacks a valid VariationID")
    if not accession or not VCV_PATTERN.fullmatch(accession):
        raise InputError("VariationArchive lacks a valid unversioned VCV accession")
    if not version or not POSITIVE_VERSION_PATTERN.fullmatch(version):
        raise InputError("VariationArchive lacks a valid positive VCV version")
    expected_accession = f"VCV{int(variation_id):09d}"
    if accession != expected_accession:
        raise InputError("VariationArchive VCV accession and VariationID disagree")
    classified = direct_child(archive, "ClassifiedRecord")
    assertions = descendants(classified, "ClinicalAssertion") if classified is not None else []
    normalized_assertions = [normalize_assertion(item) for item in assertions]
    assertion_ids = [item["assertion_id"] for item in normalized_assertions]
    if len(assertion_ids) != len(set(assertion_ids)):
        raise InputError("VariationArchive contains duplicate ClinicalAssertion IDs")
    scv_accessions = [item["scv_accession"] for item in normalized_assertions]
    if len(scv_accessions) != len(set(scv_accessions)):
        raise InputError("VariationArchive contains duplicate SCV accessions")
    rcv_items = descendants(classified, "RCVAccession") if classified is not None else []
    rcv_accessions: list[str] = []
    for item in rcv_items:
        rcv = item.attrib.get("Accession")
        rcv_version = item.attrib.get("Version")
        if not rcv or not RCV_PATTERN.fullmatch(rcv):
            raise InputError("VariationArchive contains an invalid RCV accession")
        if not rcv_version or not POSITIVE_VERSION_PATTERN.fullmatch(rcv_version):
            raise InputError("VariationArchive contains an invalid RCV version")
        rcv_accessions.append(rcv)
    if len(rcv_accessions) != len(set(rcv_accessions)):
        raise InputError("VariationArchive contains duplicate RCV accessions")
    classifications = direct_child(classified, "Classifications") if classified is not None else None
    aggregate = [] if classifications is None else [
        {"type": local_name(item.tag), **normalize_classification(item)}
        for item in list(classifications)
    ]
    record_status = direct_child(archive, "RecordStatus")
    species = [
        value for item in list(archive)
        if local_name(item.tag) == "Species" and (value := compact_text(item)) is not None
    ]
    return {
        "variation_id": variation_id,
        "vcv_accession": accession,
        "vcv_version": version,
        "variation_name": archive.attrib.get("VariationName"),
        "variation_type": archive.attrib.get("VariationType"),
        "record_type": archive.attrib.get("RecordType"),
        "record_status": compact_text(record_status) if record_status is not None else None,
        "species": species,
        "dates": dates_from(archive.attrib),
        "declared_submission_count": archive.attrib.get("NumberOfSubmissions"),
        "declared_submitter_count": archive.attrib.get("NumberOfSubmitters"),
        "rcv_accessions": [sorted_attributes(item) for item in rcv_items],
        "aggregate_classifications": aggregate,
        "clinical_assertion_count": len(normalized_assertions),
        "clinical_assertions": normalized_assertions,
    }


def match_record(root: ET.Element, identifier: dict[str, Any], label: str) -> dict[str, Any] | None:
    archives = [item for item in list(root) if local_name(item.tag) == "VariationArchive"]
    matches = [
        item for item in archives
        if item.attrib.get("VariationID") == identifier["variation_id"]
        and item.attrib.get("Accession") == identifier["vcv_accession"]
        and (
            identifier["requested_version"] is None
            or item.attrib.get("Version") == identifier["requested_version"]
        )
    ]
    if len(matches) > 1:
        raise InputError(f"{label} contains duplicate records for the requested identifier")
    if archives and len(matches) != len(archives):
        raise InputError(f"{label} contains a non-requested or wrong-version VariationArchive")
    return normalize_record(matches[0]) if matches else None


def build_report(identifiers: list[str], input_paths: list[Path]) -> dict[str, Any]:
    parsed = validate_identifiers(identifiers)
    if len(input_paths) != len(parsed):
        raise InputError("repeat --input exactly once for each --identifier, in the same order")
    total = 0
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    provenance: list[dict[str, Any]] = []
    for identifier, input_path in zip(parsed, input_paths):
        remaining = MAX_TOTAL_INPUT_BYTES - total
        if remaining <= 0:
            raise InputError("combined payloads exceed the total input limit")
        payload = read_regular(
            input_path, f"payload {input_path.name}", min(remaining, MAX_PAYLOAD_BYTES)
        )
        total += len(payload)
        sidecar = Path(str(input_path) + ".provenance.json")
        provenance_payload = read_regular(
            sidecar, f"provenance sidecar {sidecar.name}", MAX_PROVENANCE_BYTES
        )
        total += len(provenance_payload)
        if total > MAX_TOTAL_INPUT_BYTES:
            raise InputError("combined payloads and provenance exceed the total input limit")
        provenance.append(
            validate_provenance(input_path, payload, provenance_payload, identifier)
        )
        record = match_record(parse_xml(payload, input_path.name), identifier, input_path.name)
        if record is None:
            missing.append(identifier["input"])
        else:
            record["requested_identifier"] = identifier["input"]
            records.append(record)
    return {
        "schema_version": "0.1.0",
        "status": "completed" if not missing else "partial",
        "provider": "NCBI ClinVar",
        "requested_identifiers": identifiers,
        "returned_record_count": len(records),
        "missing_identifiers": missing,
        "records": records,
        "retrieval_provenance": provenance,
        "conflict_resolution": "not-performed",
        "clinical_interpretation": "not-performed",
        "scope_note": "Provider assertions are preserved; no ACMG classification, scoring, diagnosis, treatment, or conflict resolution was performed.",
    }


def render_report(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def output_relative_to_cwd(path: Path, cwd: Path) -> tuple[Path, ...]:
    if path.name in {"", ".", ".."}:
        raise FileNotFoundError("output must name a new file")
    candidate = path if path.is_absolute() else cwd / path
    try:
        relative = candidate.relative_to(cwd)
    except ValueError as exc:
        raise PermissionError("output must remain within the current working directory") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise PermissionError("output path traversal is forbidden")
    return relative.parts


def open_output_parent(path: Path) -> tuple[int, str]:
    cwd = Path.cwd()
    parts = output_relative_to_cwd(path, cwd)
    if not hasattr(os, "O_NOFOLLOW"):
        raise OSError("secure output publication requires O_NOFOLLOW support")
    directory_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    descriptor = os.open(cwd, directory_flags)
    try:
        for component in parts[:-1]:
            child = os.open(component, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1]
    except Exception:
        os.close(descriptor)
        raise


def _output_is_owned(name: str, directory: int, identity: tuple[int, int]) -> bool:
    try:
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return (current.st_dev, current.st_ino) == identity


def _unlink_owned(name: str, directory: int, identity: tuple[int, int]) -> bool:
    try:
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return True
    if (current.st_dev, current.st_ino) != identity:
        return False
    os.unlink(name, dir_fd=directory)
    return True


def _rollback_owned(directory: int, identity: tuple[int, int], names: tuple[str, ...]) -> None:
    failures: list[str] = []
    for name in names:
        try:
            if not _unlink_owned(name, directory, identity):
                failures.append(f"{name}:identity-mismatch")
        except OSError as exc:
            failures.append(f"{name}:{exc.__class__.__name__}")
    try:
        os.fsync(directory)
    except OSError as exc:
        failures.append(f"directory:{exc.__class__.__name__}")
    if failures:
        raise OSError("publication rollback failed: " + ", ".join(failures))


def write_new(path: Path, payload: bytes) -> None:
    directory, output_name = open_output_parent(path)
    temporary_name: str | None = None
    temporary_inode: tuple[int, int] | None = None
    published = False
    try:
        for attempt in range(128):
            temporary_name = (
                f".{output_name}.{os.getpid()}.{time.monotonic_ns()}.{attempt}.tmp"
            )
            try:
                temporary = os.open(
                    temporary_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory,
                )
                break
            except FileExistsError:
                continue
        else:
            raise FileExistsError("cannot allocate a unique output temporary file")
        try:
            temporary_stat = os.fstat(temporary)
            temporary_inode = (temporary_stat.st_dev, temporary_stat.st_ino)
            view = memoryview(payload)
            while view:
                written = os.write(temporary, view)
                if written <= 0:
                    raise OSError("short write while publishing output")
                view = view[written:]
            os.fsync(temporary)
        finally:
            os.close(temporary)
        os.link(
            temporary_name,
            output_name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
            follow_symlinks=False,
        )
        published = True
        if not _output_is_owned(output_name, directory, temporary_inode):
            raise OSError("published output identity differs from staged data")
        if not _unlink_owned(temporary_name, directory, temporary_inode):
            raise OSError("temporary output identity changed after publication")
        temporary_name = None
        os.fsync(directory)
        if not _output_is_owned(output_name, directory, temporary_inode):
            raise OSError("published output identity changed before completion")
    except BaseException as original:
        if temporary_inode is not None:
            names = ((output_name,) if published else ()) + (
                (temporary_name,) if temporary_name is not None else ()
            )
            try:
                _rollback_owned(directory, temporary_inode, names)
            except OSError as rollback_error:
                raise rollback_error from original
        if isinstance(original, FileExistsError):
            raise FileExistsError(
                f"output exists; overwrite is forbidden: {path}"
            ) from original
        raise
    finally:
        os.close(directory)


def fixture_xml(variation_id: int, assertions: list[tuple[str, str, str]]) -> bytes:
    accession = f"VCV{variation_id:09d}"
    rows = []
    for index, (scv, submitter, classification) in enumerate(assertions, start=1):
        rows.append(
            f'''<ClinicalAssertion ID="{variation_id}{index}" SubmissionDate="2026-01-0{index}" DateLastUpdated="2026-02-0{index}" ContributesToAggregateClassification="true">
  <ClinVarAccession Accession="{scv}" Version="1" SubmitterName="{submitter}" OrganizationCategory="laboratory" DateUpdated="2026-02-0{index}"/>
  <RecordStatus>current</RecordStatus>
  <Classification DateLastEvaluated="2026-01-01"><ReviewStatus>criteria provided, single submitter</ReviewStatus><GermlineClassification>{classification}</GermlineClassification></Classification>
  <Assertion>variation to disease</Assertion>
  <TraitSet Type="Disease"><Trait Type="Disease"><Name><ElementValue Type="Preferred">Example condition</ElementValue></Name><XRef DB="MedGen" ID="C000000"/></Trait></TraitSet>
</ClinicalAssertion>'''
        )
    aggregate_terms = "".join(
        f"<Description SubmissionCount=\"1\">{classification}</Description>"
        for _, _, classification in assertions
    )
    return (
        f'''<?xml version="1.0" encoding="UTF-8"?>
<ClinVarResult-Set><VariationArchive VariationID="{variation_id}" Accession="{accession}" Version="3" VariationName="fixture" VariationType="single nucleotide variant" RecordType="classified" DateLastUpdated="2026-02-02" NumberOfSubmissions="{len(assertions)}" NumberOfSubmitters="{len(assertions)}">
<RecordStatus>current</RecordStatus><Species>Homo sapiens</Species><ClassifiedRecord>
<RCVList><RCVAccession Accession="RCV000000001" Version="1" Title="fixture condition"/></RCVList>
<Classifications><GermlineClassification><ReviewStatus>criteria provided, conflicting classifications</ReviewStatus>{aggregate_terms}</GermlineClassification></Classifications>
<ClinicalAssertionList>{''.join(rows)}</ClinicalAssertionList>
</ClassifiedRecord></VariationArchive></ClinVarResult-Set>'''
    ).encode("utf-8")


def fixture_provenance(name: str, payload: bytes, identifier: str) -> bytes:
    numeric = bool(VARIATION_ID_PATTERN.fullmatch(identifier))
    suffix = "&is_variationid=true&from_esearch=true" if numeric else ""
    value = {
        "schema_version": "0.1.0",
        "bytes": len(payload),
        "started_at": "2026-02-03T00:00:00Z",
        "completed_at": "2026-02-03T00:00:01Z",
        "execution_mode": "live-public-read-only",
        "max_response_bytes": MAX_PAYLOAD_BYTES,
        "method": "GET",
        "network_performed": True,
        "optional_api_key_applied": False,
        "optional_contact_applied": False,
        "output_file": name,
        "pages": 1,
        "paid_use_authorized": False,
        "provider_documentation": "https://www.ncbi.nlm.nih.gov/books/NBK25497/",
        "provider_id": "ncbi-eutils",
        "request_urls": [
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
            f"db=clinvar&rettype=vcv&id={identifier}{suffix}"
        ],
        "responses": [
            {
                "response_url": (
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
                    f"db=clinvar&rettype=vcv&id={identifier}{suffix}"
                ),
                "content_type": "text/xml; charset=UTF-8",
                "etag": None,
                "last_modified": None,
                "page_value": None,
                "status": 200,
            }
        ],
        "sha256": hashlib.sha256(payload).hexdigest(),
        "terms_acknowledged": False,
    }
    return (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")


def self_test() -> None:
    checks = 0

    def require_input_error(action: Any, message: str) -> None:
        nonlocal checks
        try:
            action()
        except InputError:
            checks += 1
        else:
            raise AssertionError(message)

    def require_provider_failure(action: Any, message: str) -> None:
        nonlocal checks
        try:
            action()
        except ProviderFailure:
            checks += 1
        else:
            raise AssertionError(message)

    assert parse_identifier("101")["vcv_accession"] == "VCV000000101"
    checks += 1
    assert parse_identifier("VCV000000102.3")["requested_version"] == "3"
    checks += 1
    for invalid in ("0", "VCV000000000", "vcv000000101", "rs123"):
        try:
            parse_identifier(invalid)
        except InputError:
            continue
        raise AssertionError(f"invalid identifier was accepted: {invalid}")
    checks += 1
    require_input_error(
        lambda: validate_request_url(
            "https://eutils.ncbi.nlm.nih.gov:8443/entrez/eutils/efetch.fcgi?"
            "db=clinvar&rettype=vcv&id=VCV000000101",
            parse_identifier("VCV000000101"),
        ),
        "non-default provenance URL port was accepted",
    )
    require_input_error(
        lambda: validate_request_url(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
            "db=clinvar&rettype=vcv&id=101&is_variationid=true",
            parse_identifier("101"),
        ),
        "incomplete numeric-ID request flags were accepted",
    )
    require_input_error(
        lambda: validate_identifiers(["9325", "VCV000009325.1"]),
        "equivalent Variation ID and versioned VCV were accepted together",
    )
    require_input_error(
        lambda: parse_xml(
            b'<!DOCTYPE ClinVarResult-Set [<!ENTITY x "expanded">]>'
            b'<ClinVarResult-Set>&x;</ClinVarResult-Set>',
            "UTF-8 DTD fixture",
        ),
        "UTF-8 DTD was accepted",
    )
    utf16_dtd = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE ClinVarResult-Set [<!ENTITY x "expanded">]>'
        '<ClinVarResult-Set>&x;</ClinVarResult-Set>'
    ).encode("utf-16")
    require_input_error(
        lambda: parse_xml(utf16_dtd, "UTF-16 DTD fixture"),
        "UTF-16 DTD bypass was accepted",
    )
    require_input_error(
        lambda: parse_xml(
            b"<ClinVarResult-Set><Unexpected/></ClinVarResult-Set>",
            "unexpected direct-child fixture",
        ),
        "unexpected ClinVar direct child was accepted as a missing record",
    )

    with tempfile.TemporaryDirectory(prefix="clinvar-normalizer-selftest-") as directory:
        root = Path(directory)
        fifo_payload = root / "payload.fifo"
        os.mkfifo(fifo_payload)
        started = time.monotonic()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            fifo_status = main(
                [
                    "--identifier",
                    "120",
                    "--input",
                    str(fifo_payload),
                    "--output",
                    str(root / "fifo-output.json"),
                ]
            )
        assert time.monotonic() - started < 1.0
        fifo_error = json.loads(stderr.getvalue())
        assert fifo_status == 2 and fifo_error["status"] == "invalid-input"
        assert "not a regular file" in fifo_error["reason"]
        checks += 1

        sidecar_fifo_payload = fixture_xml(
            121, [("SCV000000121", "FIFO test", "Uncertain significance")]
        )
        sidecar_fifo_input = root / "sidecar-fifo.xml"
        sidecar_fifo_input.write_bytes(sidecar_fifo_payload)
        sidecar_fifo = Path(str(sidecar_fifo_input) + ".provenance.json")
        os.mkfifo(sidecar_fifo)
        started = time.monotonic()
        require_input_error(
            lambda: build_report(["121"], [sidecar_fifo_input]),
            "FIFO provenance sidecar was accepted",
        )
        assert time.monotonic() - started < 1.0
        checks += 1

        for index, provider_tag in enumerate(
            ("Error", "ERROR", "Warning", "ErrorList", "WarningList"), start=122
        ):
            provider_payload = (
                f"<ClinVarResult-Set><{provider_tag}>provider failure"
                f"</{provider_tag}></ClinVarResult-Set>"
            ).encode("utf-8")
            provider_path = root / f"provider-{provider_tag}.xml"
            provider_path.write_bytes(provider_payload)
            Path(str(provider_path) + ".provenance.json").write_bytes(
                fixture_provenance(provider_path.name, provider_payload, str(index))
            )
            require_provider_failure(
                lambda p=provider_path, identifier=str(index): build_report(
                    [identifier], [p]
                ),
                f"ClinVar {provider_tag} envelope was accepted as a missing record",
            )

        provider_path = root / "provider-Warning.xml"
        provider_output = root / "provider-output.json"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            provider_status = main(
                [
                    "--identifier",
                    "124",
                    "--input",
                    str(provider_path),
                    "--output",
                    str(provider_output),
                ]
            )
        provider_error = json.loads(stderr.getvalue())
        assert provider_status == 4 and provider_error["status"] == "provider-failure"
        assert provider_error["normalization_performed"] is False
        assert not provider_output.exists()
        checks += 1

        identifiers = ["101", "VCV000000102.3", "103"]
        payloads = [
            fixture_xml(101, [("SCV000000101", "Submitter A", "Pathogenic")]),
            fixture_xml(
                102,
                [
                    ("SCV000000102", "Submitter B", "Pathogenic"),
                    ("SCV000000103", "Submitter C", "Benign"),
                ],
            ),
            b'<?xml version="1.0"?><ClinVarResult-Set/>',
        ]
        paths: list[Path] = []
        for index, (identifier, payload) in enumerate(zip(identifiers, payloads), start=1):
            path = root / f"record-{index}.xml"
            path.write_bytes(payload)
            Path(str(path) + ".provenance.json").write_bytes(
                fixture_provenance(path.name, payload, identifier)
            )
            paths.append(path)

        provenance_path = Path(str(paths[0]) + ".provenance.json")
        original_provenance = provenance_path.read_bytes()
        for case in ("schema", "completed_at", "timestamp", "response"):
            malformed_provenance = json.loads(original_provenance)
            if case == "schema":
                malformed_provenance["schema_version"] = "9.9.9"
            elif case == "completed_at":
                malformed_provenance.pop("completed_at")
            elif case == "timestamp":
                malformed_provenance["completed_at"] = "2026-02-03 00:00:01Z"
            else:
                malformed_provenance["responses"][0].pop("content_type")
            provenance_path.write_text(json.dumps(malformed_provenance), encoding="utf-8")
            require_input_error(
                lambda: build_report(["101"], [paths[0]]),
                f"malformed {case} provenance was accepted",
            )
        provenance_path.write_bytes(original_provenance)

        def require_payload_rejection(name: str, identifier: str, payload: bytes) -> None:
            path = root / f"{name}.xml"
            path.write_bytes(payload)
            Path(str(path) + ".provenance.json").write_bytes(
                fixture_provenance(path.name, payload, identifier)
            )
            require_input_error(
                lambda: build_report([identifier], [path]),
                f"{name} provider identity drift was accepted",
            )

        vcv_zero = fixture_xml(107, [("SCV000000107", "A", "Pathogenic")]).replace(
            b'Version="3"', b'Version="0"', 1
        )
        require_payload_rejection("vcv-version-zero", "107", vcv_zero)
        scv_zero = fixture_xml(108, [("SCV000000108", "A", "Pathogenic")]).replace(
            b'<ClinVarAccession Accession="SCV000000108" Version="1"',
            b'<ClinVarAccession Accession="SCV000000108" Version="0"',
        )
        require_payload_rejection("scv-version-zero", "108", scv_zero)
        duplicate_scv = fixture_xml(
            109,
            [
                ("SCV000000109", "A", "Pathogenic"),
                ("SCV000000109", "B", "Benign"),
            ],
        )
        require_payload_rejection("duplicate-scv", "109", duplicate_scv)
        rcv_element = (
            b'<RCVAccession Accession="RCV000000001" Version="1" '
            b'Title="fixture condition"/>'
        )
        rcv_zero = fixture_xml(110, [("SCV000000110", "A", "Pathogenic")]).replace(
            rcv_element, rcv_element.replace(b'Version="1"', b'Version="0"')
        )
        require_payload_rejection("rcv-version-zero", "110", rcv_zero)
        duplicate_rcv = fixture_xml(
            111, [("SCV000000111", "A", "Pathogenic")]
        ).replace(rcv_element, rcv_element + rcv_element)
        require_payload_rejection("duplicate-rcv", "111", duplicate_rcv)

        report = build_report(identifiers, paths)
        assert report["status"] == "partial" and report["missing_identifiers"] == ["103"]
        checks += 1
        assert report["returned_record_count"] == 2
        checks += 1
        first = report["records"][0]
        assert first["clinical_assertions"][0]["scv_accession"] == "SCV000000101"
        checks += 1
        assert first["clinical_assertions"][0]["classification"]["review_statuses"] == [
            "criteria provided, single submitter"
        ]
        checks += 1
        assert first["clinical_assertions"][0]["conditions"][0]["tag"] == "TraitSet"
        checks += 1
        second_terms = [
            item["classification"]["classification_terms"][0]["value"]
            for item in report["records"][1]["clinical_assertions"]
        ]
        assert second_terms == ["Pathogenic", "Benign"]
        assert report["conflict_resolution"] == "not-performed"
        checks += 1
        aggregate = report["records"][1]["aggregate_classifications"][0]
        assert aggregate["review_statuses"] == [
            "criteria provided, conflicting classifications"
        ]
        assert [item["value"] for item in aggregate["classification_terms"]] == [
            "Pathogenic",
            "Benign",
        ]
        checks += 1
        rendered = render_report(report)
        assert rendered == render_report(build_report(identifiers, paths))
        checks += 1
        output = root / "report.json"
        original_cwd = Path.cwd()
        os.chdir(root)
        try:
            outside_root = root / "outside"
            outside_root.mkdir()
            symlink_parent = root / "symlink-parent"
            symlink_parent.symlink_to(outside_root, target_is_directory=True)
            try:
                write_new(Path("symlink-parent") / "escaped.json", b"forbidden")
            except OSError:
                checks += 1
            else:
                raise AssertionError("symlinked output parent was followed")
            assert not (outside_root / "escaped.json").exists()

            try:
                write_new(Path("..") / "traversal.json", b"forbidden")
            except PermissionError:
                checks += 1
            else:
                raise AssertionError("parent traversal output was accepted")

            write_new(Path("report.json"), rendered)
            original = output.read_bytes()
            try:
                write_new(Path("report.json"), b"replacement")
            except FileExistsError:
                pass
            else:
                raise AssertionError("existing output was overwritten")
            assert output.read_bytes() == original
            assert not list(root.glob(f".{output.name}.*"))
            checks += 1

            rollback_output = root / "rollback.json"
            original_fsync = os.fsync

            def fail_directory_fsync(descriptor: int) -> None:
                if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    raise OSError("simulated directory sync failure")
                original_fsync(descriptor)

            os.fsync = fail_directory_fsync
            try:
                try:
                    write_new(Path("rollback.json"), rendered)
                except OSError:
                    pass
                else:
                    raise AssertionError("simulated publication failure was accepted")
            finally:
                os.fsync = original_fsync
            assert not rollback_output.exists()
            assert not list(root.glob(f".{rollback_output.name}.*"))
            checks += 1

            final_identity_output = root / "final-identity.json"
            original_unlink = os.unlink
            final_identity_swapped = False

            def replace_final_during_cleanup(path: str, *args: Any, **kwargs: Any) -> None:
                nonlocal final_identity_swapped
                if (
                    not final_identity_swapped
                    and path.startswith(f".{final_identity_output.name}.")
                    and path.endswith(".tmp")
                ):
                    final_identity_swapped = True
                    original_unlink(final_identity_output.name, dir_fd=kwargs["dir_fd"])
                    replacement = os.open(
                        final_identity_output.name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=kwargs["dir_fd"],
                    )
                    try:
                        competitor = b"competitor\n"
                        assert os.write(replacement, competitor) == len(competitor)
                        os.fsync(replacement)
                    finally:
                        os.close(replacement)
                original_unlink(path, *args, **kwargs)

            os.unlink = replace_final_during_cleanup
            try:
                try:
                    write_new(Path(final_identity_output.name), rendered)
                except OSError as exc:
                    assert "publication rollback failed" in str(exc)
                else:
                    raise AssertionError("final output replacement was accepted")
            finally:
                os.unlink = original_unlink
            assert final_identity_swapped
            assert final_identity_output.read_bytes() == b"competitor\n"
            assert not list(root.glob(f".{final_identity_output.name}.*"))
            final_identity_output.unlink()
            checks += 1
        finally:
            os.chdir(original_cwd)

        bad_xml = root / "bad.xml"
        bad_payload = b"<ClinVarResult-Set>"
        bad_xml.write_bytes(bad_payload)
        Path(str(bad_xml) + ".provenance.json").write_bytes(
            fixture_provenance(bad_xml.name, bad_payload, "104")
        )
        try:
            build_report(["104"], [bad_xml])
        except InputError:
            checks += 1
        else:
            raise AssertionError("malformed provider response was accepted")

        wrong = root / "wrong.xml"
        wrong_payload = fixture_xml(106, [("SCV000000106", "Submitter D", "Uncertain significance")])
        wrong.write_bytes(wrong_payload)
        Path(str(wrong) + ".provenance.json").write_bytes(
            fixture_provenance(wrong.name, wrong_payload, "105")
        )
        try:
            build_report(["105"], [wrong])
        except InputError:
            checks += 1
        else:
            raise AssertionError("wrong VariationArchive was accepted")

        sidecar = Path(str(paths[0]) + ".provenance.json")
        tampered = json.loads(sidecar.read_text(encoding="utf-8"))
        tampered["sha256"] = "0" * 64
        sidecar.write_text(json.dumps(tampered), encoding="utf-8")
        try:
            build_report(["101"], [paths[0]])
        except InputError:
            checks += 1
        else:
            raise AssertionError("unbound provenance was accepted")

        try:
            validate_identifiers([str(index) for index in range(1, 7)])
        except InputError:
            checks += 1
        else:
            raise AssertionError("more than five identifiers were accepted")

    print(json.dumps({"checks": checks, "status": "pass", "version": VERSION}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--identifier", action="append", default=[])
    result.add_argument("--input", type=Path, action="append", default=[])
    result.add_argument("--output", type=Path)
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="version", version=VERSION)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.self_test:
        self_test()
        return 0
    if not arguments.identifier or not arguments.input or arguments.output is None:
        parser().error("execution requires --identifier, --input, and --output")
    try:
        report = build_report(arguments.identifier, arguments.input)
        write_new(arguments.output, render_report(report))
        print(
            json.dumps(
                {
                    "missing": len(report["missing_identifiers"]),
                    "normalization_performed": True,
                    "output": str(arguments.output),
                    "records": report["returned_record_count"],
                    "status": report["status"],
                },
                sort_keys=True,
            )
        )
        return 0
    except InputError as exc:
        print(
            json.dumps(
                {"normalization_performed": False, "reason": str(exc), "status": "invalid-input"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except ProviderFailure as exc:
        print(
            json.dumps(
                {
                    "normalization_performed": False,
                    "reason": str(exc),
                    "status": "provider-failure",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 4
    except (FileExistsError, FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError) as exc:
        print(
            json.dumps(
                {"normalization_performed": False, "reason": str(exc), "status": "invalid-output"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 3
    except OSError as exc:
        print(
            json.dumps(
                {"normalization_performed": False, "reason": str(exc), "status": "io-error"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
