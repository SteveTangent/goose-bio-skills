#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded, no-dependency access to reviewed public research APIs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from http.client import HTTPException, InvalidURL
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "connectors" / "providers.json"
VERSION = "0.9.0"
CATALOG_SCHEMA_VERSION = "0.2.0"
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
HARD_MAX_BYTES = 128 * 1024 * 1024
MAX_PAGES = 20
MAX_RETRIES = 4
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
SUCCESS_STATUS = {
    "GET": {200},
    "HEAD": {200, 204},
}
SECRET_QUERY_KEYS = {
    "apikey",
    "accesstoken",
    "auth",
    "authtoken",
    "authorization",
    "clientsecret",
    "clienttoken",
    "contactemail",
    "credential",
    "credentials",
    "emailaddress",
    "token",
    "key",
    "email",
    "mailto",
    "password",
    "passwd",
    "pass",
    "passcode",
    "pwd",
    "secret",
    "username",
    "xapikey",
}
SECRET_QUERY_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
    "email",
    "mailto",
    "contact",
    "username",
    "authorization",
    "bearer",
)
SECRET_KEY_FAMILY = {
    "key",
    "apikey",
    "accesskey",
    "authkey",
    "clientkey",
    "privatekey",
    "xapikey",
}
PAGE_PARAMETER = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
PUBCHEM_ASYNC_PATH = re.compile(
    r"^/rest/pug/compound/(?:substructure|superstructure|similarity_2d|similarity_3d|identity|formula)(?:/|$)",
    re.IGNORECASE,
)
ENSEMBL_ORTHOLOGY_SPECIES = {
    "danio_rerio": "ENSDARG",
    "homo_sapiens": "ENSG",
    "mus_musculus": "ENSMUSG",
    "rattus_norvegicus": "ENSRNOG",
}
_NETWORK_PERFORMED = False


@dataclass(frozen=True)
class Policy:
    mode: str
    prefixes: tuple[str, ...]
    requests_per_second: float
    max_response_bytes: int


EXPECTED_PROVIDER_IDS = (
    "ncbi-eutils",
    "uniprot-rest",
    "ensembl-rest",
    "europe-pmc",
    "ebi-biostudies",
    "ena-portal-api",
    "rcsb-pdb",
    "alphafold-db",
    "pubchem-pug-rest",
    "chembl-rest",
    "crossref-rest",
    "quickgo",
    "enrichr",
    "kegg-rest",
    "embl-ebi-job-dispatcher",
    "ncbi-blast-remote",
    "ncbi-geo-files",
)
EXECUTION_FIELDS = {
    "execution_mode",
    "allowed_url_prefixes",
    "rate_limit_per_second",
    "max_response_bytes",
}
EXECUTION_MODES = {"direct-read", "terms-read", "conditional-job", "disabled"}


class ConnectorError(RuntimeError):
    """A request violates the connector boundary or cannot complete safely."""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json_no_duplicates(path: Path) -> object:
    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ConnectorError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=pairs_hook
        )
    except ConnectorError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConnectorError(f"invalid provider catalog: {exc}") from exc


def load_catalog() -> dict[str, object]:
    catalog = load_json_no_duplicates(CATALOG_PATH)
    if not isinstance(catalog, dict):
        raise ConnectorError("provider catalog must be a JSON object")
    if catalog.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise ConnectorError("unsupported provider catalog schema")
    if catalog.get("mode") != "live-public-read-only":
        raise ConnectorError("provider catalog is not in live public read-only mode")
    provider_ids = catalog.get("provider_ids")
    providers = catalog.get("providers")
    if not isinstance(provider_ids, list) or not isinstance(providers, dict):
        raise ConnectorError("provider catalog IDs or entries are invalid")
    if provider_ids != list(providers) or len(provider_ids) != len(set(provider_ids)):
        raise ConnectorError("provider catalog IDs must uniquely match entry order")
    if tuple(provider_ids) != EXPECTED_PROVIDER_IDS:
        raise ConnectorError("provider catalog differs from the reviewed allowlist")

    for provider_id in EXPECTED_PROVIDER_IDS:
        provider = providers.get(provider_id)
        if not isinstance(provider, dict):
            raise ConnectorError(f"provider entry is invalid: {provider_id}")
        hosts = provider.get("allowed_hosts")
        billing = provider.get("billing")
        if not isinstance(hosts, list) or not all(
            isinstance(host, str) for host in hosts
        ):
            raise ConnectorError(f"provider hosts are invalid: {provider_id}")
        if not isinstance(billing, dict):
            raise ConnectorError(f"provider billing boundary is invalid: {provider_id}")
        execution = provider.get("execution")
        if not isinstance(execution, dict) or set(execution) != EXECUTION_FIELDS:
            raise ConnectorError(
                f"provider execution boundary is invalid: {provider_id}"
            )
        mode = execution.get("execution_mode")
        prefixes = execution.get("allowed_url_prefixes")
        rate = execution.get("rate_limit_per_second")
        max_bytes = execution.get("max_response_bytes")
        if mode not in EXECUTION_MODES:
            raise ConnectorError(f"provider execution mode is invalid: {provider_id}")
        if (
            not isinstance(prefixes, list)
            or not prefixes
            or not all(isinstance(item, str) for item in prefixes)
        ):
            raise ConnectorError(f"provider URL prefixes are invalid: {provider_id}")
        if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate < 0:
            raise ConnectorError(f"provider rate limit is invalid: {provider_id}")
        if (
            not isinstance(max_bytes, int)
            or isinstance(max_bytes, bool)
            or max_bytes < 0
        ):
            raise ConnectorError(f"provider response limit is invalid: {provider_id}")
        active = mode in {"direct-read", "terms-read"}
        if active and (rate <= 0 or not 0 < max_bytes <= HARD_MAX_BYTES):
            raise ConnectorError(f"active provider limits are invalid: {provider_id}")
        if not active and (rate != 0 or max_bytes != 0):
            raise ConnectorError(
                f"inactive provider limits must be zero: {provider_id}"
            )
        for prefix in prefixes:
            parsed = urlsplit(prefix)
            if parsed.scheme != "https" or parsed.hostname not in hosts:
                raise ConnectorError(
                    f"executable prefix escapes catalog hosts: {provider_id}"
                )
        if mode in {"direct-read", "terms-read"} and billing.get(
            "requires_separate_paid_authorization"
        ):
            raise ConnectorError(f"paid provider cannot be direct: {provider_id}")
    return catalog


def policy_for(
    provider_id: str, catalog: dict[str, object], acknowledge_terms: bool
) -> Policy:
    providers = catalog["providers"]
    assert isinstance(providers, dict)
    if provider_id not in providers:
        raise ConnectorError("unknown provider ID")
    provider = providers[provider_id]
    assert isinstance(provider, dict)
    execution = provider["execution"]
    assert isinstance(execution, dict)
    mode = execution["execution_mode"]
    assert isinstance(mode, str)
    prefixes = execution["allowed_url_prefixes"]
    rate = execution["rate_limit_per_second"]
    max_bytes = execution["max_response_bytes"]
    assert isinstance(prefixes, list)
    assert isinstance(rate, (int, float))
    assert isinstance(max_bytes, int)
    policy = Policy(mode, tuple(prefixes), float(rate), max_bytes)
    if policy.mode == "disabled":
        raise ConnectorError(
            "metered or paid execution is disabled; use a user-supplied external tool"
        )
    if policy.mode == "conditional-job":
        raise ConnectorError(
            "remote submission is conditional and not implemented by this read-only executor"
        )
    if policy.mode == "terms-read" and not acknowledge_terms:
        raise ConnectorError(
            "this provider requires --acknowledge-terms for academic-use terms"
        )
    return policy


def decoded_path(path: str) -> str:
    decoded = path
    for _ in range(3):
        decoded = unquote(decoded)
    return decoded


def _decoded_path_has_traversal(path: str) -> bool:
    decoded = decoded_path(path)
    return "\\" in decoded or any(part in {".", ".."} for part in decoded.split("/"))


def decoded_query_pairs(url: str) -> list[tuple[str, str]]:
    """Parse query pairs conservatively, including legacy semicolon separators."""
    query = decoded_path(urlsplit(url).query).replace(";", "&")
    return parse_qsl(query, keep_blank_values=True)


def validate_read_only_semantics(provider_id: str, url: str) -> None:
    parsed = urlsplit(url)
    decoded_url_path = decoded_path(parsed.path)
    path = decoded_url_path.lower()
    query = [
        (key.lower(), value.strip().lower()) for key, value in decoded_query_pairs(url)
    ]
    if provider_id == "ncbi-geo-files":
        match = re.fullmatch(
            r"/geo/series/(GSE[0-9]*nnn)/(GSE[0-9]{1,9})/matrix/(?:((GSE[0-9]{1,9})(?:-GPL[0-9]{1,9})?_series_matrix\.txt\.gz))?",
            parsed.path,
        )
        if not match or parsed.query or decoded_url_path != parsed.path:
            raise ConnectorError(
                "GEO access is limited to an exact Series Matrix directory or matrix gzip file"
            )
        bucket, accession, filename, file_accession = match.groups()
        expected_bucket = (
            "GSE" + accession[3:-3] + "nnn" if len(accession[3:]) > 3 else "GSEnnn"
        )
        if bucket != expected_bucket or (filename and file_accession != accession):
            raise ConnectorError(
                "GEO directory and matrix filename must match the same accession"
            )
    elif provider_id == "ncbi-eutils":
        if path.endswith("/epost.fcgi"):
            raise ConnectorError(
                "NCBI EPost writes to the History server and requires a job adapter"
            )
        for key, value in query:
            history_write = (
                key == "webenv"
                or key == "query_key"
                or key == "usehistory"
                or (key == "cmd" and value == "neighbor_history")
            )
            if history_write:
                raise ConnectorError(
                    "NCBI History-server state is outside direct-read mode"
                )
    elif provider_id == "ensembl-rest" and path.startswith("/homology/id/"):
        if (
            decoded_url_path != parsed.path
            or parsed.query != unquote(parsed.query)
            or ";" in parsed.query
        ):
            raise ConnectorError(
                "Ensembl orthology path and query must use the exact reviewed ASCII spelling"
            )
        raw_query = parse_qsl(parsed.query, keep_blank_values=True)
        if any(
            key != key.lower() or value != value.strip().lower()
            for key, value in raw_query
        ):
            raise ConnectorError(
                "Ensembl orthology query keys and values must use canonical lowercase spelling"
            )
        match = re.fullmatch(
            r"/homology/id/([a-z][a-z0-9_]{1,63})/"
            r"(ENS[A-Z0-9]*G[0-9]{6,}(?:\.[0-9]+)?)",
            decoded_url_path,
        )
        if match is None:
            raise ConnectorError(
                "Ensembl orthology reads require one exact species path and stable gene ID"
            )
        source_species = match.group(1)
        values: dict[str, list[str]] = {}
        for key, value in query:
            values.setdefault(key, []).append(value)
        expected_keys = {
            "aligned",
            "content-type",
            "format",
            "sequence",
            "target_species",
            "type",
        }
        if set(values) != expected_keys or any(
            len(items) != 1 for items in values.values()
        ):
            raise ConnectorError(
                "Ensembl orthology reads require the exact reviewed query fields"
            )
        target_species = values["target_species"][0]
        if (
            source_species not in ENSEMBL_ORTHOLOGY_SPECIES
            or target_species not in ENSEMBL_ORTHOLOGY_SPECIES
        ):
            raise ConnectorError(
                "Ensembl orthology preview requires a reviewed canonical species name"
            )
        if target_species == source_species:
            raise ConnectorError(
                "Ensembl orthology source and target species must differ"
            )
        expected_prefix = ENSEMBL_ORTHOLOGY_SPECIES[source_species]
        if (
            re.fullmatch(
                rf"{re.escape(expected_prefix)}[0-9]{{6,}}(?:\.[0-9]+)?",
                match.group(2),
            )
            is None
        ):
            raise ConnectorError(
                "Ensembl orthology stable gene ID does not match the declared source species"
            )
        expected_values = {
            "aligned": "0",
            "content-type": "application/json",
            "format": "condensed",
            "sequence": "none",
            "type": "orthologues",
        }
        if any(values[key] != [value] for key, value in expected_values.items()):
            raise ConnectorError(
                "Ensembl orthology query exceeds the reviewed relationship-only boundary"
            )
    elif provider_id == "pubchem-pug-rest":
        if PUBCHEM_ASYNC_PATH.match(path) or re.search(
            r"/(?:listkey|cachekey)(?:/|$)", path
        ):
            raise ConnectorError(
                "PubChem asynchronous and stored-result paths require a job adapter"
            )
        for key, value in query:
            if key in {"listkey", "cachekey"} or (
                key == "list_return" and value in {"listkey", "cachekey"}
            ):
                raise ConnectorError(
                    "PubChem stored-result creation requires a job adapter"
                )
    elif provider_id == "enrichr":
        if re.search(r"/(?:api/)?addlist/?$", path):
            raise ConnectorError("Enrichr list submission is outside direct-read mode")
    elif provider_id == "ena-portal-api":
        values: dict[str, list[str]] = {}
        for key, value in query:
            values.setdefault(key, []).append(value)
        accession = values.get("accession", [])
        result = values.get("result", [])
        response_format = values.get("format", [])
        fields = values.get("fields", [])
        allowed_fields = {
            "run_accession",
            "study_accession",
            "sample_accession",
            "experiment_accession",
            "instrument_platform",
            "instrument_model",
            "library_layout",
            "library_strategy",
            "library_source",
            "library_selection",
            "fastq_file_role",
            "fastq_ftp",
            "fastq_md5",
            "fastq_bytes",
            "submitted_file_role",
            "submitted_ftp",
            "submitted_md5",
            "submitted_bytes",
            "sra_file_role",
            "sra_ftp",
            "sra_md5",
            "sra_bytes",
        }
        accession_pattern = re.compile(
            r"^(?:[SED]R[PRXS][0-9]+|PRJ(?:NA|EB|DB)[0-9]+|SAM(?:N|EA|D)[0-9]+)$",
            re.IGNORECASE,
        )
        if len(accession) != 1 or not accession_pattern.fullmatch(accession[0]):
            raise ConnectorError(
                "ENA file reports require one explicit public INSDC accession"
            )
        if result != ["read_run"]:
            raise ConnectorError("ENA file reports are limited to the read_run result")
        if response_format != ["tsv"]:
            raise ConnectorError("ENA file reports require TSV output")
        if len(fields) != 1:
            raise ConnectorError("ENA file reports require one explicit field list")
        requested_field_list = [
            item.strip() for item in fields[0].split(",") if item.strip()
        ]
        requested_fields = set(requested_field_list)
        common_fields = {
            "run_accession",
            "study_accession",
            "sample_accession",
            "experiment_accession",
            "library_layout",
            "instrument_platform",
            "instrument_model",
        }
        representation_groups = (
            {"fastq_file_role", "fastq_ftp", "fastq_md5", "fastq_bytes"},
            {
                "submitted_file_role",
                "submitted_ftp",
                "submitted_md5",
                "submitted_bytes",
            },
            {"sra_file_role", "sra_ftp", "sra_md5", "sra_bytes"},
        )
        if (
            not requested_fields
            or len(requested_field_list) != len(requested_fields)
            or not requested_fields.issubset(allowed_fields)
            or not common_fields.issubset(requested_fields)
            or sum(group.issubset(requested_fields) for group in representation_groups)
            != 1
            or any(
                requested_fields.intersection(group)
                and requested_fields.intersection(group) != group
                for group in representation_groups
            )
        ):
            raise ConnectorError(
                "ENA file report fields exceed the reviewed run-manifest boundary"
            )
        if any(
            key not in {"accession", "result", "fields", "format"} for key in values
        ):
            raise ConnectorError(
                "ENA file report parameters exceed the reviewed boundary"
            )


def normalized_query_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", decoded_path(key).strip().lower())


def is_sensitive_query_key(key: str) -> bool:
    components = re.findall(r"[a-z0-9]+", decoded_path(key).lower())
    normalized = normalized_query_key(key)
    return (
        normalized in SECRET_QUERY_KEYS
        or normalized in SECRET_KEY_FAMILY
        or any(
            component in SECRET_KEY_FAMILY or component in {"pass", "passcode", "pwd"}
            for component in components
        )
        or any(fragment in normalized for fragment in SECRET_QUERY_FRAGMENTS)
    )


def sensitive_query_pairs(url: str) -> frozenset[str]:
    return frozenset(
        normalized_query_key(key)
        for key, _value in decoded_query_pairs(url)
        if is_sensitive_query_key(key)
    )


def validate_url(
    provider_id: str,
    url: str,
    policy: Policy,
) -> str:
    if any(ord(char) < 33 or ord(char) > 126 for char in url):
        raise ConnectorError(
            "URL must use printable ASCII with non-ASCII data percent-encoded"
        )
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ConnectorError("URL authority is invalid") from exc
    if parsed.scheme != "https" or not hostname:
        raise ConnectorError("only absolute HTTPS URLs are allowed")
    if parsed.username or parsed.password or parsed.fragment:
        raise ConnectorError("URL credentials and fragments are not allowed")
    if port not in {None, 443}:
        raise ConnectorError("non-default URL ports are not allowed")
    if _decoded_path_has_traversal(parsed.path):
        raise ConnectorError("URL path traversal is not allowed")
    if sensitive_query_pairs(url):
        raise ConnectorError(
            "credentials and contact fields are not accepted by the shared executor"
        )
    validate_read_only_semantics(provider_id, url)

    allowed = False
    for prefix in policy.prefixes:
        allowed_prefix = urlsplit(prefix)
        if (
            hostname == allowed_prefix.hostname
            and (port or 443) == (allowed_prefix.port or 443)
            and (
                parsed.path.startswith(allowed_prefix.path)
                if allowed_prefix.path.endswith("/")
                else parsed.path == allowed_prefix.path
            )
        ):
            allowed = True
            break
    if not allowed:
        raise ConnectorError(f"URL is outside reviewed paths for {provider_id}")
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path, parsed.query, ""))


def redact_url(url: str) -> str:
    parsed = urlsplit(url)
    if sensitive_query_pairs(url):
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                "redacted_sensitive_query=1",
                "",
            )
        )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


class ReviewedRedirectHandler(HTTPRedirectHandler):
    def __init__(
        self,
        provider_id: str,
        policy: Policy,
    ) -> None:
        super().__init__()
        self.provider_id = provider_id
        self.policy = policy

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        target = urljoin(req.full_url, newurl)
        validate_url(
            self.provider_id,
            target,
            self.policy,
        )
        redirected = super().redirect_request(req, fp, code, msg, headers, target)
        if redirected is not None:
            redirected.method = req.get_method()
        return redirected


def retry_delay(error: HTTPError | None, attempt: int) -> float:
    if error is not None:
        value = error.headers.get("Retry-After")
        if value and value.isdigit():
            return min(float(value), 10.0)
    return min(0.5 * (2**attempt), 4.0)


def read_bounded(response, remaining: int) -> bytes:  # type: ignore[no-untyped-def]
    content_length = response.headers.get("Content-Length")
    declared_length: int | None = None
    if content_length is not None:
        normalized_length = content_length.strip()
        if not normalized_length.isdigit():
            raise ConnectorError("response Content-Length is invalid")
        declared_length = int(normalized_length)
        if declared_length > remaining:
            raise ConnectorError("response Content-Length exceeds --max-bytes")
    body = bytearray()
    while True:
        chunk = response.read(min(64 * 1024, remaining - len(body) + 1))
        if not chunk:
            if declared_length is not None and len(body) != declared_length:
                raise ConnectorError(
                    "response ended before its declared Content-Length"
                )
            return bytes(body)
        body.extend(chunk)
        if len(body) > remaining:
            raise ConnectorError("response exceeds --max-bytes")


def validate_response_payload(body: bytes, content_type: object) -> None:
    media_type = str(content_type or "").split(";", 1)[0].strip().lower()
    prefix = body[:65536]
    html_prefix = re.compile(
        rb"^(?:\xef\xbb\xbf)?(?:\s|<!--.*?-->)*(?:<!doctype\s+html|<html(?:\s|>))",
        re.IGNORECASE | re.DOTALL,
    )
    if media_type in {"text/html", "application/xhtml+xml"} or html_prefix.match(
        prefix
    ):
        raise ConnectorError(
            "provider returned an HTML page instead of a research payload"
        )
    if not body.strip():
        raise ConnectorError("HTTP 200 GET response contained no payload")
    normalized_prefix = prefix.lstrip(b"\xef\xbb\xbf \t\r\n")
    looks_like_json = "json" in media_type or normalized_prefix.startswith((b"{", b"["))
    if looks_like_json:
        try:
            decoded = json.loads(body.decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ConnectorError("provider returned malformed JSON") from exc
        else:
            if isinstance(decoded, dict):
                normalized = {str(key).lower(): value for key, value in decoded.items()}
                error_value = normalized.get(
                    "error",
                    normalized.get("errors", normalized.get("fault")),
                )
                status_value = str(normalized.get("status", "")).strip().lower()
                if bool(error_value) or status_value in {"error", "failed", "failure"}:
                    raise ConnectorError("provider returned an explicit error payload")
    if re.search(
        rb"<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?(?:ERROR|ERRORS|FAULT)(?:\s|>)",
        prefix,
        re.IGNORECASE,
    ):
        raise ConnectorError("provider returned an explicit XML error payload")


def request_once(
    provider_id: str,
    policy: Policy,
    method: str,
    url: str,
    timeout: float,
    max_bytes: int,
    retries: int,
    open_request: Callable[[Request, float], object] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[bytes, dict[str, object]]:
    validate_url(provider_id, url, policy)
    if open_request is None:
        opener = build_opener(ReviewedRedirectHandler(provider_id, policy))

        def live_open(request: Request, request_timeout: float) -> object:
            global _NETWORK_PERFORMED
            _NETWORK_PERFORMED = True
            return opener.open(request, timeout=request_timeout)

        open_request = live_open
    headers = {
        "Accept": "application/json, text/plain;q=0.9, */*;q=0.5",
        "User-Agent": "Bio02Skills-public-research-connector",
    }
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers=headers, method=method)
            response = open_request(request, timeout)
            try:
                try:
                    status = int(getattr(response, "status", 200))
                except (TypeError, ValueError) as exc:
                    raise ConnectorError("response status is invalid") from exc
                if status not in SUCCESS_STATUS[method]:
                    raise ConnectorError(
                        f"HTTP response status {status} is not a completed result"
                    )
                try:
                    body = (
                        b"" if method == "HEAD" else read_bounded(response, max_bytes)
                    )
                except (OSError, HTTPException) as exc:
                    raise ConnectorError(
                        "response body could not be read completely"
                    ) from exc
                if status == 204 and body:
                    raise ConnectorError(
                        "HTTP 204 response unexpectedly contained a body"
                    )
                response_headers = getattr(response, "headers")
                content_type = response_headers.get("Content-Type")
                if method == "GET" and status == 200:
                    if provider_id == "ncbi-geo-files" and urlsplit(url).path.endswith(
                        "/matrix/"
                    ):
                        accession = urlsplit(url).path.split("/")[-3]
                        from html.parser import HTMLParser

                        class MatrixIndex(HTMLParser):
                            found = False

                            def handle_starttag(self, tag, attrs):
                                href = dict(attrs).get("href", "")
                                if tag == "a" and re.fullmatch(
                                    re.escape(accession)
                                    + r"(?:-GPL[0-9]+)?_series_matrix\.txt\.gz",
                                    href,
                                ):
                                    self.found = True

                        parser = MatrixIndex()
                        try:
                            parser.feed(body.decode("utf-8"))
                        except UnicodeError as exc:
                            raise ConnectorError("invalid GEO index encoding") from exc
                        if not parser.found:
                            raise ConnectorError(
                                "GEO directory contains no supported matching matrix file"
                            )
                    else:
                        validate_response_payload(body, content_type)
                        if provider_id == "ncbi-geo-files" and not body.startswith(
                            b"\x1f\x8b"
                        ):
                            raise ConnectorError("GEO matrix response is not gzip data")
                response_url = validate_url(
                    provider_id,
                    str(getattr(response, "geturl")()),
                    policy,
                )
                return body, {
                    "status": status,
                    "response_url": redact_url(response_url),
                    "content_type": content_type,
                    "etag": response_headers.get("ETag"),
                    "last_modified": response_headers.get("Last-Modified"),
                }
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except HTTPError as exc:
            last_error = exc
            try:
                if exc.code not in RETRYABLE_STATUS or attempt == retries:
                    raise ConnectorError(
                        f"HTTP request failed with status {exc.code}"
                    ) from exc
                sleeper(retry_delay(exc, attempt))
            finally:
                exc.close()
        except URLError as exc:
            last_error = exc
            if attempt == retries:
                raise ConnectorError("network request failed after retries") from exc
            sleeper(retry_delay(None, attempt))
        except InvalidURL as exc:
            raise ConnectorError("network URL was rejected") from exc
        except (HTTPException, OSError, ValueError) as exc:
            last_error = exc
            if attempt == retries:
                raise ConnectorError("network request failed after retries") from exc
            sleeper(retry_delay(None, attempt))
    raise ConnectorError(f"network request failed: {last_error}")


def with_page(url: str, parameter: str, value: int) -> str:
    parsed = urlsplit(url)
    params = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key != parameter
    ]
    params.append((parameter, str(value)))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(params), "")
    )


@dataclass
class StagedIdentity:
    """Keep the staged inode allocated until publication or rollback finishes."""
    device: int
    inode: int
    descriptor: int = -1

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1


def prepare_temp(path: Path, data: bytes) -> tuple[Path, StagedIdentity]:
    if not path.parent.is_dir():
        raise ConnectorError(f"output directory does not exist: {path.parent}")
    temporary: Path | None = None
    identity: StagedIdentity | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            opened = os.fstat(handle.fileno())
            identity = StagedIdentity(opened.st_dev, opened.st_ino)
            identity.descriptor = os.dup(handle.fileno())
            os.fchmod(handle.fileno(), 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary, identity
    except OSError as exc:
        cleanup_failed = False
        if temporary is not None and identity is not None:
            try:
                cleanup_failed = not unlink_if_owned(temporary, identity)
            except OSError:
                cleanup_failed = True
        if identity is not None:
            identity.close()
        if cleanup_failed:
            raise ConnectorError(
                "could not prepare output and staged-file cleanup failed"
            ) from exc
        raise ConnectorError(f"could not prepare output: {exc}") from exc


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def file_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    return metadata.st_dev, metadata.st_ino


def is_owned(target: Path, identity: StagedIdentity) -> bool:
    try:
        return file_identity(target) == (identity.device, identity.inode)
    except FileNotFoundError:
        return False


def unlink_if_owned(target: Path, identity: StagedIdentity) -> bool:
    try:
        if not is_owned(target, identity):
            try:
                target.stat(follow_symlinks=False)
            except FileNotFoundError:
                return True
            return False
        target.unlink()
        return True
    except FileNotFoundError:
        return True


def rollback_owned(
    entries: list[tuple[Path, StagedIdentity]],
    directories: set[Path],
) -> None:
    failures: list[str] = []
    for path, identity in entries:
        try:
            if not unlink_if_owned(path, identity):
                failures.append(f"{path.name}:identity-mismatch")
        except OSError as exc:
            failures.append(f"{path.name}:{exc.__class__.__name__}")
    for directory in directories:
        try:
            fsync_directory(directory)
        except OSError as exc:
            failures.append(f"{directory.name or directory}:{exc.__class__.__name__}")
    if failures:
        raise ConnectorError("publication rollback failed: " + ", ".join(failures))


def publish_outputs(
    output: Path,
    payload: bytes,
    provenance_path: Path,
    provenance: bytes,
) -> None:
    """Publish both create-new files without a check/replace overwrite race."""
    if output == provenance_path:
        raise ConnectorError("payload and provenance paths must differ")
    for parent in {output.parent, provenance_path.parent}:
        if not parent.is_dir():
            raise ConnectorError(f"output directory does not exist: {parent}")
    output_temp: Path | None = None
    provenance_temp: Path | None = None
    output_identity: StagedIdentity | None = None
    provenance_identity: StagedIdentity | None = None
    output_published = False
    provenance_published = False
    directories = {output.parent, provenance_path.parent}
    try:
        output_temp, output_identity = prepare_temp(output, payload)
        if not is_owned(output_temp, output_identity):
            raise OSError("staged payload identity changed before publication")
        provenance_temp, provenance_identity = prepare_temp(provenance_path, provenance)
        if not is_owned(provenance_temp, provenance_identity):
            raise OSError("staged provenance identity changed before publication")
        os.link(output_temp, output)
        output_published = True
        if not is_owned(output, output_identity):
            raise OSError("published payload identity differs from staged data")
        os.link(provenance_temp, provenance_path)
        provenance_published = True
        if not is_owned(provenance_path, provenance_identity):
            raise OSError("published provenance identity differs from staged data")
        if not unlink_if_owned(output_temp, output_identity):
            raise OSError("staged payload identity changed during cleanup")
        output_temp = None
        if not unlink_if_owned(provenance_temp, provenance_identity):
            raise OSError("staged provenance identity changed during cleanup")
        provenance_temp = None
        for directory in directories:
            fsync_directory(directory)
        if not is_owned(output, output_identity) or not is_owned(
            provenance_path, provenance_identity
        ):
            raise OSError("published output identity changed before completion")
    except BaseException as original:
        owned: list[tuple[Path, StagedIdentity]] = []
        if provenance_identity is not None:
            if provenance_published:
                owned.append((provenance_path, provenance_identity))
            if provenance_temp is not None:
                owned.append((provenance_temp, provenance_identity))
        if output_identity is not None:
            if output_published:
                owned.append((output, output_identity))
            if output_temp is not None:
                owned.append((output_temp, output_identity))
        try:
            rollback_owned(owned, directories)
        except ConnectorError as rollback_error:
            raise rollback_error from original
        if isinstance(original, ConnectorError):
            raise
        if isinstance(original, FileExistsError):
            raise ConnectorError(
                "output or provenance already exists; overwrite is forbidden"
            ) from original
        if isinstance(original, OSError):
            raise ConnectorError(
                f"could not publish create-new output pair: {original}"
            ) from original
        raise
    finally:
        for identity in (output_identity, provenance_identity):
            if identity is not None:
                identity.close()


def execute(
    args: argparse.Namespace,
    catalog: dict[str, object],
    *,
    open_request: Callable[[Request, float], object] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    policy = policy_for(args.provider, catalog, args.acknowledge_terms)
    base_url = validate_url(args.provider, args.url, policy)
    output = args.output
    provenance_path = args.provenance or output.with_name(
        f"{output.name}.provenance.json"
    )
    if output == provenance_path:
        raise ConnectorError("payload and provenance paths must differ")
    if output.exists():
        raise ConnectorError(f"output already exists: {output}")
    if provenance_path.exists():
        raise ConnectorError(f"provenance already exists: {provenance_path}")

    started_at = now_utc()
    bodies: list[bytes] = []
    responses: list[dict[str, object]] = []
    requested_urls: list[str] = []
    effective_max_bytes = min(args.max_bytes, policy.max_response_bytes)
    remaining = effective_max_bytes
    for index in range(args.pages):
        url = base_url
        page_value = None
        if args.pages > 1:
            page_value = args.page_start + index * args.page_step
            url = with_page(url, args.page_param, page_value)
        requested_urls.append(redact_url(url))
        body, response = request_once(
            args.provider,
            policy,
            args.method,
            url,
            args.timeout,
            remaining,
            args.retries,
            open_request=open_request,
            sleeper=sleeper,
        )
        remaining -= len(body)
        response["page_value"] = page_value
        bodies.append(body)
        responses.append(response)
        if index + 1 < args.pages:
            sleeper(1.0 / policy.requests_per_second)

    if args.pages == 1:
        payload = bodies[0]
    else:
        pages: list[dict[str, object]] = []
        for response, body in zip(responses, bodies):
            try:
                decoded = json.loads(body.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ConnectorError("multi-page mode requires JSON responses") from exc
            pages.append({"page_value": response["page_value"], "data": decoded})
        payload = (
            json.dumps({"pages": pages}, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        if len(payload) > effective_max_bytes:
            raise ConnectorError("combined paginated output exceeds --max-bytes")

    digest = hashlib.sha256(payload).hexdigest()
    completed_at = now_utc()
    providers = catalog["providers"]
    assert isinstance(providers, dict)
    provider = providers[args.provider]
    assert isinstance(provider, dict)
    provenance = {
        "schema_version": "0.1.0",
        "provider_id": args.provider,
        "provider_documentation": provider.get("official_docs"),
        "execution_mode": "live-public-read-only",
        "method": args.method,
        "started_at": started_at,
        "completed_at": completed_at,
        "request_urls": requested_urls,
        "responses": responses,
        "pages": args.pages,
        "max_response_bytes": effective_max_bytes,
        "bytes": len(payload),
        "sha256": digest,
        "output_file": output.name,
        "optional_contact_applied": False,
        "optional_api_key_applied": False,
        "terms_acknowledged": bool(args.acknowledge_terms),
        "network_performed": True,
        "paid_use_authorized": False,
    }
    provenance_bytes = (
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    publish_outputs(output, payload, provenance_path, provenance_bytes)
    return {
        "event": "connector-result",
        "status": "completed",
        "provider_id": args.provider,
        "output": str(output),
        "provenance": str(provenance_path),
        "bytes": len(payload),
        "sha256": digest,
        "pages": args.pages,
        "network_performed": True,
        "paid_use_authorized": False,
    }


class FakeResponse:
    def __init__(
        self,
        url: str,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "application/json",
    ) -> None:
        self.status = status
        self._url = url
        self._body = body
        self._offset = 0
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(body))

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self._url

    def close(self) -> None:
        pass


def self_test(catalog: dict[str, object]) -> int:
    checks = 0
    uniprot = policy_for("uniprot-rest", catalog, False)
    validate_url(
        "uniprot-rest", "https://rest.uniprot.org/uniprotkb/P04637.json", uniprot
    )
    checks += 1

    ena = policy_for("ena-portal-api", catalog, False)
    validate_url(
        "ena-portal-api",
        "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRR390728&result=read_run&fields=run_accession,study_accession,sample_accession,experiment_accession,library_layout,instrument_platform,instrument_model,fastq_file_role,fastq_ftp,fastq_md5,fastq_bytes&format=tsv",
        ena,
    )
    for disallowed_ena_url in (
        "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRR390728&result=analysis&fields=run_accession&format=tsv",
        "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRR390728&result=read_run&fields=run_accession,private_field&format=tsv",
        "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRR390728&result=read_run&fields=run_accession,study_accession,sample_accession,experiment_accession,library_layout,instrument_platform,instrument_model,fastq_ftp,fastq_md5,fastq_bytes&format=tsv",
        "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRR390728&result=read_run&fields=run_accession,run_accession,study_accession,sample_accession,experiment_accession,library_layout,instrument_platform,instrument_model,fastq_file_role,fastq_ftp,fastq_md5,fastq_bytes&format=tsv",
        "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=not-an-accession&result=read_run&fields=run_accession&format=tsv",
        "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SAMNA123&result=read_run&fields=run_accession&format=tsv",
        "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=PRJZZ123&result=read_run&fields=run_accession&format=tsv",
        "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRR390728&result=read_run&fields=run_accession&format=json",
    ):
        try:
            validate_url("ena-portal-api", disallowed_ena_url, ena)
        except ConnectorError:
            pass
        else:
            raise ConnectorError("ENA run-manifest boundary self-test failed")
    checks += 1

    ensembl = policy_for("ensembl-rest", catalog, False)
    validate_url(
        "ensembl-rest",
        "https://rest.ensembl.org/lookup/id/ENSG00000141510?content-type=application/json",
        ensembl,
    )
    validate_url(
        "ensembl-rest",
        "https://rest.ensembl.org/archive/id/ENSG00000141510?content-type=application/json",
        ensembl,
    )
    orthology_url = (
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510"
        "?target_species=mus_musculus&type=orthologues&sequence=none&aligned=0"
        "&format=condensed&content-type=application/json"
    )
    validate_url("ensembl-rest", orthology_url, ensembl)
    if redact_url(orthology_url) != orthology_url:
        raise ConnectorError(
            "safe request URL bytes changed during provenance redaction"
        )
    orthology_args = argparse.Namespace(
        self_test=False,
        provider="ensembl-rest",
        url=orthology_url,
        output=Path("orthology.json"),
        provenance=None,
        method="GET",
        pages=1,
        page_param=None,
        acknowledge_terms=False,
    )
    validate_args(orthology_args)
    for method, pages, page_param in (
        ("HEAD", 1, None),
        ("GET", 2, "page"),
    ):
        rejected_args = argparse.Namespace(
            **{
                **vars(orthology_args),
                "method": method,
                "pages": pages,
                "page_param": page_param,
            }
        )
        try:
            validate_args(rejected_args)
        except ConnectorError:
            pass
        else:
            raise ConnectorError("Ensembl orthology execution-mode self-test failed")
    for disallowed_orthology_url in (
        "https://rest.ensembl.org/homology/id/homo_sapiens/TP53?target_species=mus_musculus&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?target_species=mus_musculus&type=paralogues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?target_species=mus_musculus&type=orthologues&sequence=protein&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?target_species=mus_musculus&target_species=rattus_norvegicus&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?target_species=homo_sapiens&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?target_species=mus_musculus&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json&extra=1",
        "https://rest.ensembl.org/homology/id/homo%5Fsapiens/ENSG00000141510?target_species=mus_musculus&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?target_species=mus%255Fmusculus&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?TARGET_SPECIES=mus_musculus&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?target_species=mus_musculus;type=orthologues;sequence=none;aligned=0;format=condensed;content-type=application/json",
        "https://rest.ensembl.org/homology/id/human/ENSG00000141510?target_species=mus_musculus&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?target_species=human&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/mouse/ENSMUSG00000059552?target_species=homo_sapiens&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/mus_musculus/ENSMUSG00000059552?target_species=mouse&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSMUSG00000059552?target_species=mus_musculus&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/homo_sapiens/ENSGFOOG000001?target_species=mus_musculus&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
        "https://rest.ensembl.org/homology/id/mus_musculus/ENSMUSGG000001?target_species=homo_sapiens&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json",
    ):
        try:
            validate_url("ensembl-rest", disallowed_orthology_url, ensembl)
        except ConnectorError:
            pass
        else:
            raise ConnectorError("Ensembl orthology boundary self-test failed")
    checks += 1
    try:
        validate_url(
            "ensembl-rest",
            "https://rest.ensembl.org/overlap/id/ENSG00000141510",
            ensembl,
        )
    except ConnectorError:
        pass
    else:
        raise ConnectorError("Ensembl path allowlist self-test failed")
    checks += 1

    for secret_key in (
        "password",
        "client_secret",
        "clientSecret",
        "accessToken",
        "authorization",
        "auth_token",
        "authToken",
        "x-api-key",
        "xApiKey",
        "contactEmail",
        "api_token",
        "api-token",
        "bearer_token",
        "secret_key",
        "contact",
        "user_email",
        "pwd",
        "pass",
        "auth%5Bpass%5D",
        "api%255Fkey",
        "credentials%255Btoken%255D",
    ):
        secret_url = (
            f"https://rest.uniprot.org/uniprotkb/P04637.json?{secret_key}=not-a-secret"
        )
        try:
            validate_url("uniprot-rest", secret_url, uniprot)
        except ConnectorError as exc:
            if "not-a-secret" in str(exc) or "not-a-secret" in redact_url(secret_url):
                raise ConnectorError(
                    "credential rejection leaked a query value"
                ) from exc
        else:
            raise ConnectorError(f"credential query key was accepted: {secret_key}")
    for ambiguous_url in (
        "https://rest.uniprot.org/uniprotkb/P04637.json?term=x;api_key=not-a-secret",
        "https://rest.uniprot.org/uniprotkb/P04637.json?term=x%3Bapi_key=not-a-secret",
        "https://rest.uniprot.org/uniprotkb/P04637.json?term=x%3Bapi%5Fkey=not-a-secret",
        "https://rest.uniprot.org/uniprotkb/P04637.json?term=x%253Bapi%255Fkey=not-a-secret",
    ):
        try:
            validate_url("uniprot-rest", ambiguous_url, uniprot)
        except ConnectorError as exc:
            if "not-a-secret" in str(exc) or "not-a-secret" in redact_url(
                ambiguous_url
            ):
                raise ConnectorError(
                    "credential rejection leaked a query value"
                ) from exc
        else:
            raise ConnectorError("semicolon-delimited credential field was accepted")
    checks += 1
    for bad_url in (
        "http://rest.uniprot.org/uniprotkb/P04637.json",
        "https://example.org/uniprotkb/P04637.json",
        "https://rest.uniprot.org/../private",
        "https://rest.uniprot.org/uniprotkb/P0 4637.json",
        "https://rest.uniprot.org/uniprotkb/search?query=肝癌",
    ):
        try:
            validate_url("uniprot-rest", bad_url, uniprot)
        except ConnectorError:
            pass
        else:
            raise ConnectorError("URL boundary self-test failed")
    checks += 1

    enrichr = policy_for("enrichr", catalog, False)
    validate_url(
        "enrichr",
        "https://maayanlab.cloud/Enrichr/datasetStatistics",
        enrichr,
    )
    validate_url(
        "enrichr",
        "https://maayanlab.cloud/Enrichr/geneSetLibrary?mode=meta",
        enrichr,
    )
    for submission_url in (
        "https://maayanlab.cloud/Enrichr/addList",
        "https://maayanlab.cloud/Enrichr/api/addList",
        "https://maayanlab.cloud/Enrichr/view",
        "https://maayanlab.cloud/Enrichr/enrich?userListId=1",
        "https://maayanlab.cloud/Enrichr/export?userListId=1",
    ):
        try:
            validate_url("enrichr", submission_url, enrichr)
        except ConnectorError:
            pass
        else:
            raise ConnectorError("unreviewed Enrichr path became executable")
    with tempfile.TemporaryDirectory(prefix="bio02-enrichr-boundary-") as temp_dir:
        network_calls = 0

        def must_not_open(_request: Request, _timeout: float) -> object:
            nonlocal network_calls
            network_calls += 1
            raise AssertionError("unreviewed Enrichr path reached the network")

        for index, path in enumerate(("view", "enrich", "export")):
            output = Path(temp_dir) / f"{index}.json"
            args = argparse.Namespace(
                provider="enrichr",
                url=f"https://maayanlab.cloud/Enrichr/{path}",
                output=output,
                provenance=None,
                method="GET",
                pages=1,
                page_param=None,
                page_start=1,
                page_step=1,
                max_bytes=1024,
                timeout=1,
                retries=0,
                acknowledge_terms=False,
            )
            try:
                execute(
                    args,
                    catalog,
                    open_request=must_not_open,
                    sleeper=lambda _seconds: None,
                )
            except ConnectorError:
                pass
            else:
                raise ConnectorError("unreviewed Enrichr execution was accepted")
            if (
                output.exists()
                or output.with_name(f"{output.name}.provenance.json").exists()
            ):
                raise ConnectorError("blocked Enrichr path created an artifact")
        if network_calls:
            raise ConnectorError("blocked Enrichr path attempted network access")
    checks += 1

    redirect_handler = ReviewedRedirectHandler("uniprot-rest", uniprot)
    redirect_source = Request("https://rest.uniprot.org/uniprotkb/P04637.json")
    try:
        redirect_handler.redirect_request(
            redirect_source,
            None,
            302,
            "Found",
            Message(),
            "https://example.org/escaped",
        )
    except ConnectorError:
        pass
    else:
        raise ConnectorError("redirect escape self-test failed")
    allowed_redirect = redirect_handler.redirect_request(
        redirect_source,
        None,
        302,
        "Found",
        Message(),
        "/uniprotkb/Q9Y6K9.json",
    )
    if (
        allowed_redirect is None
        or allowed_redirect.full_url != "https://rest.uniprot.org/uniprotkb/Q9Y6K9.json"
    ):
        raise ConnectorError("reviewed redirect self-test failed")
    if allowed_redirect.get_method() != "GET":
        raise ConnectorError("GET redirect method changed")
    head_redirect = redirect_handler.redirect_request(
        Request("https://rest.uniprot.org/uniprotkb/P04637.json", method="HEAD"),
        None,
        302,
        "Found",
        Message(),
        "/uniprotkb/Q9Y6K9.json",
    )
    if head_redirect is None or head_redirect.get_method() != "HEAD":
        raise ConnectorError("HEAD redirect method changed")
    checks += 1

    ncbi = policy_for("ncbi-eutils", catalog, False)
    validate_url(
        "ncbi-eutils",
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=p53",
        ncbi,
    )
    for remote_state_url in (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/epost.fcgi?db=protein&id=1,2",
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=p53&usehistory=y",
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=p53&usehistory=n",
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=p53;usehistory=y",
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=p53%3Busehistory=y",
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&query_key=1",
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=p53&WebEnv=history",
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&db=pmc&id=1&cmd=neighbor_history",
    ):
        try:
            validate_url("ncbi-eutils", remote_state_url, ncbi)
        except ConnectorError:
            pass
        else:
            raise ConnectorError("NCBI remote-state self-test failed")
    checks += 1

    pubchem = policy_for("pubchem-pug-rest", catalog, False)
    validate_url(
        "pubchem-pug-rest",
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/fastsimilarity_2d/cid/2244/cids/JSON?Threshold=95&MaxRecords=100",
        pubchem,
    )
    for async_url in (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/similarity_2d/cid/2244/cids/JSON",
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/fastformula/C6H12O/cids/JSON?list_return=cachekey",
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/fastformula/C6H12O/cids/JSON?x=1;list_return=cachekey",
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/fastformula/C6H12O/cids/JSON?x=1%3Blist_return=cachekey",
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/listkey/example/cids/JSON",
    ):
        try:
            validate_url("pubchem-pug-rest", async_url, pubchem)
        except ConnectorError:
            pass
        else:
            raise ConnectorError("PubChem asynchronous-path self-test failed")
    checks += 1

    for blocked in ("embl-ebi-job-dispatcher", "ncbi-blast-remote"):
        try:
            policy_for(blocked, catalog, False)
        except ConnectorError:
            pass
        else:
            raise ConnectorError(f"blocked provider became executable: {blocked}")
    checks += 1
    try:
        policy_for("kegg-rest", catalog, False)
    except ConnectorError:
        pass
    else:
        raise ConnectorError("KEGG terms acknowledgement was bypassed")
    policy_for("kegg-rest", catalog, True)
    checks += 1

    with tempfile.TemporaryDirectory(prefix="bio02-anonymous-connector-") as temp_dir:
        output = Path(temp_dir) / "ncbi.json"
        captured_urls: list[str] = []

        def capture_anonymous(request: Request, _timeout: float) -> object:
            captured_urls.append(request.full_url)
            return FakeResponse(request.full_url, b'{"ok":true}')

        anonymous_args = argparse.Namespace(
            provider="ncbi-eutils",
            url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=p53",
            output=output,
            provenance=None,
            method="GET",
            pages=1,
            page_param=None,
            page_start=1,
            page_step=1,
            max_bytes=1024,
            timeout=1,
            retries=0,
            acknowledge_terms=False,
        )
        secret = "self-test-secret-value"
        contact = "self-test-researcher@example.org"
        environment_names = (
            "NCBI_API_KEY",
            "BIO02_NCBI_API_KEY",
            "NCBI_EMAIL",
            "BIO02_NCBI_EMAIL",
        )
        previous_environment = {
            name: os.environ.get(name) for name in environment_names
        }
        try:
            os.environ["NCBI_API_KEY"] = secret
            os.environ["NCBI_EMAIL"] = contact
            event = execute(
                anonymous_args,
                catalog,
                open_request=capture_anonymous,
                sleeper=lambda _seconds: None,
            )
        finally:
            for name, previous in previous_environment.items():
                if previous is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = previous
        provenance_text = output.with_name(f"{output.name}.provenance.json").read_text(
            encoding="utf-8"
        )
        visible = (
            json.dumps(event, sort_keys=True)
            + provenance_text
            + output.read_text(encoding="utf-8")
        )
        if (
            not captured_urls
            or secret in captured_urls[0]
            or contact in captured_urls[0]
            or secret in visible
            or contact in visible
            or '"optional_api_key_applied": false' not in provenance_text
            or '"optional_contact_applied": false' not in provenance_text
            or event["network_performed"] is not True
        ):
            raise ConnectorError("anonymous-only execution self-test failed")
    checks += 1

    with tempfile.TemporaryDirectory(prefix="bio02-pagination-pacing-") as temp_dir:
        pacing_output = Path(temp_dir) / "pages.json"
        pacing_sleeps: list[float] = []
        pacing_urls: list[str] = []

        def capture_page(request: Request, _timeout: float) -> object:
            pacing_urls.append(request.full_url)
            return FakeResponse(request.full_url, b'{"ok":true}')

        pacing_args = argparse.Namespace(
            provider="ncbi-eutils",
            url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=p53",
            output=pacing_output,
            provenance=None,
            method="GET",
            pages=3,
            page_param="retstart",
            page_start=0,
            page_step=20,
            max_bytes=4096,
            timeout=1,
            retries=0,
            acknowledge_terms=False,
        )
        execute(
            pacing_args,
            catalog,
            open_request=capture_page,
            sleeper=pacing_sleeps.append,
        )
        expected_delay = 1.0 / ncbi.requests_per_second
        if (
            len(pacing_urls) != 3
            or len(pacing_sleeps) != 2
            or any(abs(delay - expected_delay) > 1e-12 for delay in pacing_sleeps)
        ):
            raise ConnectorError("single-invocation pagination pacing self-test failed")
    checks += 1

    attempts = 0

    def flaky(request: Request, _timeout: float) -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise URLError("temporary")
        return FakeResponse(request.full_url, b'{"ok":true}')

    body, response = request_once(
        "uniprot-rest",
        uniprot,
        "GET",
        "https://rest.uniprot.org/uniprotkb/P04637.json",
        1,
        64,
        1,
        open_request=flaky,
        sleeper=lambda _seconds: None,
    )
    if attempts != 2 or body != b'{"ok":true}' or response["status"] != 200:
        raise ConnectorError("retry self-test failed")
    checks += 1

    def reject_network_url(_request: Request, _timeout: float) -> object:
        raise InvalidURL("invalid authority")

    try:
        request_once(
            "uniprot-rest",
            uniprot,
            "GET",
            "https://rest.uniprot.org/uniprotkb/P04637.json",
            1,
            64,
            0,
            open_request=reject_network_url,
            sleeper=lambda _seconds: None,
        )
    except ConnectorError as exc:
        if str(exc) != "network URL was rejected":
            raise ConnectorError("invalid URL error was not normalized") from exc
    else:
        raise ConnectorError("invalid network URL was accepted")
    checks += 1

    try:
        request_once(
            "uniprot-rest",
            uniprot,
            "GET",
            "https://rest.uniprot.org/uniprotkb/P04637.json",
            1,
            64,
            0,
            open_request=lambda request, timeout: FakeResponse(
                request.full_url,
                b"pending",
                status=202,
                content_type="text/html",
            ),
            sleeper=lambda _seconds: None,
        )
    except ConnectorError:
        pass
    else:
        raise ConnectorError("HTTP 202 completion self-test failed")
    checks += 1

    invalid_payloads = (
        (b"", 200, "application/json"),
        (b" \n\t", 200, "text/plain"),
        (b"<html>gateway error</html>", 200, "text/html"),
        (b"\xef\xbb\xbf<!-- proxy --><html>gateway error</html>", 200, "text/plain"),
        (b"{malformed", 200, "text/plain"),
        (b'{"error":"invalid record"}', 200, "application/json"),
        (b'{"Error":"invalid record"}', 200, "application/json"),
        (b'{"Fault":{"message":"invalid record"}}', 200, "application/json"),
        (
            b"<eSearchResult><ERROR>invalid database</ERROR></eSearchResult>",
            200,
            "application/xml",
        ),
        (
            b"<eSearchResult><ns:Fault>invalid database</ns:Fault></eSearchResult>",
            200,
            "application/xml",
        ),
        (b"", 204, "application/json"),
    )
    for invalid_body, invalid_status, invalid_content_type in invalid_payloads:
        try:
            request_once(
                "uniprot-rest",
                uniprot,
                "GET",
                "https://rest.uniprot.org/uniprotkb/P04637.json",
                1,
                1024,
                0,
                open_request=lambda request, timeout, body=invalid_body, status=invalid_status, content_type=invalid_content_type: FakeResponse(
                    request.full_url,
                    body,
                    status=status,
                    content_type=content_type,
                ),
                sleeper=lambda _seconds: None,
            )
        except ConnectorError:
            pass
        else:
            raise ConnectorError("invalid provider payload was accepted")
    with tempfile.TemporaryDirectory(prefix="bio02-invalid-payload-") as temp_dir:
        invalid_output = Path(temp_dir) / "invalid.json"
        invalid_args = argparse.Namespace(
            provider="uniprot-rest",
            url="https://rest.uniprot.org/uniprotkb/P04637.json",
            output=invalid_output,
            provenance=None,
            method="GET",
            pages=1,
            page_param=None,
            page_start=1,
            page_step=1,
            max_bytes=1024,
            timeout=1,
            retries=0,
            acknowledge_terms=False,
        )
        try:
            execute(
                invalid_args,
                catalog,
                open_request=lambda request, timeout: FakeResponse(
                    request.full_url,
                    b"<html>gateway error</html>",
                    content_type="text/html",
                ),
                sleeper=lambda _seconds: None,
            )
        except ConnectorError:
            pass
        else:
            raise ConnectorError("invalid payload execution was accepted")
        if (
            invalid_output.exists()
            or invalid_output.with_name(
                f"{invalid_output.name}.provenance.json"
            ).exists()
        ):
            raise ConnectorError("invalid payload created a success artifact")
    checks += 1

    def short_response(request: Request, _timeout: float) -> object:
        response = FakeResponse(request.full_url, b"{}")
        response.headers.replace_header("Content-Length", "10")
        return response

    try:
        request_once(
            "uniprot-rest",
            uniprot,
            "GET",
            "https://rest.uniprot.org/uniprotkb/P04637.json",
            1,
            64,
            0,
            open_request=short_response,
            sleeper=lambda _seconds: None,
        )
    except ConnectorError:
        pass
    else:
        raise ConnectorError("short response self-test failed")
    checks += 1

    try:
        request_once(
            "uniprot-rest",
            uniprot,
            "GET",
            "https://rest.uniprot.org/uniprotkb/P04637.json",
            1,
            2,
            0,
            open_request=lambda request, timeout: FakeResponse(
                request.full_url, b"large"
            ),
            sleeper=lambda _seconds: None,
        )
    except ConnectorError:
        pass
    else:
        raise ConnectorError("byte limit self-test failed")
    checks += 1
    with tempfile.TemporaryDirectory(prefix="bio02-live-connector-") as temp_dir:
        temp_root = Path(temp_dir)
        failed_target = temp_root / "must-not-leak.bin"
        original_fsync = os.fsync

        def fail_fsync(_descriptor: int) -> None:
            raise OSError("forced self-test failure")

        os.fsync = fail_fsync
        try:
            prepare_temp(failed_target, b"sensitive")
        except ConnectorError:
            pass
        else:
            raise ConnectorError("temporary-file failure self-test did not fail")
        finally:
            os.fsync = original_fsync
        if any(temp_root.glob(f".{failed_target.name}.*")):
            raise ConnectorError("temporary output survived a failed prepare")

        target = Path(temp_dir) / "result.json"
        provenance = Path(temp_dir) / "result.provenance.json"
        publish_outputs(target, b'{"ok":true}\n', provenance, b'{"source":"test"}\n')
        if target.read_bytes() != b'{"ok":true}\n':
            raise ConnectorError("atomic output self-test failed")
        sentinel = Path(temp_dir) / "sentinel.json"
        sentinel.write_bytes(b"keep-me")
        absent_provenance = Path(temp_dir) / "must-stay-absent.json"
        try:
            publish_outputs(sentinel, b"overwrite", absent_provenance, b"new")
        except ConnectorError:
            pass
        else:
            raise ConnectorError("atomic no-overwrite self-test failed")
        if sentinel.read_bytes() != b"keep-me" or absent_provenance.exists():
            raise ConnectorError("existing sentinel changed during failed publication")
        rolled_back = Path(temp_dir) / "must-roll-back.json"
        provenance_sentinel = Path(temp_dir) / "provenance-sentinel.json"
        provenance_sentinel.write_bytes(b"keep-provenance")
        try:
            publish_outputs(
                rolled_back, b"temporary", provenance_sentinel, b"overwrite"
            )
        except ConnectorError:
            pass
        else:
            raise ConnectorError("pair rollback self-test failed")
        if (
            rolled_back.exists()
            or provenance_sentinel.read_bytes() != b"keep-provenance"
        ):
            raise ConnectorError("partial pair survived failed publication")

        race_target = Path(temp_dir) / "race-result.json"
        race_provenance = Path(temp_dir) / "race-result.provenance.json"
        original_unlink_if_owned = unlink_if_owned
        race_injected = False

        def replace_final_during_cleanup(
            target_path: Path, identity: StagedIdentity
        ) -> bool:
            nonlocal race_injected
            if not race_injected and target_path.name.startswith(
                f".{race_target.name}."
            ):
                race_injected = True
                race_target.unlink()
                race_target.write_bytes(b"competitor")
            return original_unlink_if_owned(target_path, identity)

        globals()["unlink_if_owned"] = replace_final_during_cleanup
        try:
            publish_outputs(
                race_target,
                b'{"owned":true}\n',
                race_provenance,
                b'{"source":"owned"}\n',
            )
        except ConnectorError:
            pass
        else:
            raise ConnectorError("final-identity replacement self-test did not fail")
        finally:
            globals()["unlink_if_owned"] = original_unlink_if_owned
        if race_target.read_bytes() != b"competitor" or race_provenance.exists():
            raise ConnectorError("final-identity rollback damaged a competing output")
        if any(Path(temp_dir).glob(".race-result*." + "*")):
            raise ConnectorError("final-identity rollback left staged output")

        prepare_race_target = Path(temp_dir) / "prepare-race.json"
        prepare_race_provenance = Path(temp_dir) / "prepare-race.provenance.json"
        original_prepare_temp = prepare_temp
        replaced_stage: Path | None = None

        def replace_stage_after_prepare(
            target_path: Path, data: bytes
        ) -> tuple[Path, StagedIdentity]:
            nonlocal replaced_stage
            staged_path, staged_identity = original_prepare_temp(target_path, data)
            if target_path == prepare_race_target:
                staged_path.unlink()
                staged_path.write_bytes(b"competitor-stage")
                replaced_stage = staged_path
            return staged_path, staged_identity

        globals()["prepare_temp"] = replace_stage_after_prepare
        try:
            publish_outputs(
                prepare_race_target,
                b'{"owned":true}\n',
                prepare_race_provenance,
                b'{"source":"owned"}\n',
            )
        except ConnectorError:
            pass
        else:
            raise ConnectorError("staged-identity replacement self-test did not fail")
        finally:
            globals()["prepare_temp"] = original_prepare_temp
        if prepare_race_target.exists() or prepare_race_provenance.exists():
            raise ConnectorError("staged-identity replacement published an output")
        if replaced_stage is None or replaced_stage.read_bytes() != b"competitor-stage":
            raise ConnectorError("staged-identity rollback damaged a competing file")
    checks += 1
    print(
        json.dumps(
            {
                "event": "self-test",
                "status": "passed",
                "version": VERSION,
                "checks": checks,
                "providers": len(EXPECTED_PROVIDER_IDS),
                "direct_live": sum(
                    isinstance(provider, dict)
                    and isinstance(provider.get("execution"), dict)
                    and provider["execution"].get("execution_mode") == "direct-read"
                    for provider in catalog["providers"].values()
                ),
                "network_performed": False,
                "paid_use_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0


def bounded_int(value: str, *, minimum: int, maximum: int, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise argparse.ArgumentTypeError(
            f"{label} must be between {minimum} and {maximum}"
        )
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a bounded GET or HEAD against a reviewed public research API."
    )
    parser.add_argument("--provider", choices=EXPECTED_PROVIDER_IDS)
    parser.add_argument(
        "--url",
        help="Exact reviewed HTTPS URL; credential and contact parameters are rejected.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--method", choices=("GET", "HEAD"), default="GET")
    parser.add_argument(
        "--pages",
        type=lambda value: bounded_int(
            value, minimum=1, maximum=MAX_PAGES, label="pages"
        ),
        default=1,
    )
    parser.add_argument("--page-param")
    parser.add_argument("--page-start", type=int, default=1)
    parser.add_argument(
        "--page-step",
        type=lambda value: bounded_int(
            value, minimum=1, maximum=1_000_000, label="page-step"
        ),
        default=1,
    )
    parser.add_argument(
        "--max-bytes",
        type=lambda value: bounded_int(
            value, minimum=1, maximum=HARD_MAX_BYTES, label="max-bytes"
        ),
        default=DEFAULT_MAX_BYTES,
    )
    parser.add_argument(
        "--timeout",
        type=lambda value: bounded_int(value, minimum=1, maximum=120, label="timeout"),
        default=30,
    )
    parser.add_argument(
        "--retries",
        type=lambda value: bounded_int(
            value, minimum=0, maximum=MAX_RETRIES, label="retries"
        ),
        default=2,
    )
    parser.add_argument("--acknowledge-terms", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--version", action="version", version=VERSION)
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.self_test:
        if any(
            (
                args.provider,
                args.url,
                args.output,
                args.provenance,
                args.page_param,
                args.acknowledge_terms,
            )
        ):
            raise ConnectorError(
                "--self-test cannot be combined with execution arguments"
            )
        return
    if not args.provider or not args.url or args.output is None:
        raise ConnectorError("--provider, --url, and --output are required")
    if (
        args.provider == "ensembl-rest"
        and decoded_path(urlsplit(args.url).path).lower().startswith("/homology/id/")
        and (args.method != "GET" or args.pages != 1 or args.page_param is not None)
    ):
        raise ConnectorError(
            "Ensembl orthology retrieval requires one non-paginated GET per stable gene ID"
        )
    if args.pages > 1:
        if not args.page_param or not PAGE_PARAMETER.fullmatch(args.page_param):
            raise ConnectorError("multi-page mode requires a valid --page-param")
        if is_sensitive_query_key(args.page_param):
            raise ConnectorError("credential fields cannot be pagination parameters")
    elif args.page_param:
        raise ConnectorError(
            "--page-param is only valid when --pages is greater than one"
        )


def emit(event: dict[str, object]) -> None:
    print(json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True)


def main(argv: list[str] | None = None) -> int:
    global _NETWORK_PERFORMED
    _NETWORK_PERFORMED = False
    try:
        args = build_parser().parse_args(argv)
        validate_args(args)
        catalog = load_catalog()
        if args.self_test:
            return self_test(catalog)
        event = execute(args, catalog)
        emit(event)
        return 0
    except ConnectorError as exc:
        emit(
            {
                "event": "connector-error",
                "status": "blocked-or-failed",
                "reason": str(exc),
                "network_performed": _NETWORK_PERFORMED,
                "paid_use_authorized": False,
            }
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
