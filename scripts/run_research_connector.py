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
from http.client import HTTPException
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "connectors" / "providers.json"
VERSION = "0.4.0"
CATALOG_SCHEMA_VERSION = "0.2.0"
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
HARD_MAX_BYTES = 128 * 1024 * 1024
MAX_PAGES = 20
MAX_RETRIES = 4
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
SUCCESS_STATUS = {
    "GET": {200, 204},
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
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs_hook)
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
        if not isinstance(hosts, list) or not all(isinstance(host, str) for host in hosts):
            raise ConnectorError(f"provider hosts are invalid: {provider_id}")
        if not isinstance(billing, dict):
            raise ConnectorError(f"provider billing boundary is invalid: {provider_id}")
        execution = provider.get("execution")
        if not isinstance(execution, dict) or set(execution) != EXECUTION_FIELDS:
            raise ConnectorError(f"provider execution boundary is invalid: {provider_id}")
        mode = execution.get("execution_mode")
        prefixes = execution.get("allowed_url_prefixes")
        rate = execution.get("rate_limit_per_second")
        max_bytes = execution.get("max_response_bytes")
        if mode not in EXECUTION_MODES:
            raise ConnectorError(f"provider execution mode is invalid: {provider_id}")
        if not isinstance(prefixes, list) or not prefixes or not all(isinstance(item, str) for item in prefixes):
            raise ConnectorError(f"provider URL prefixes are invalid: {provider_id}")
        if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate < 0:
            raise ConnectorError(f"provider rate limit is invalid: {provider_id}")
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
            raise ConnectorError(f"provider response limit is invalid: {provider_id}")
        active = mode in {"direct-read", "terms-read"}
        if active and (rate <= 0 or not 0 < max_bytes <= HARD_MAX_BYTES):
            raise ConnectorError(f"active provider limits are invalid: {provider_id}")
        if not active and (rate != 0 or max_bytes != 0):
            raise ConnectorError(f"inactive provider limits must be zero: {provider_id}")
        for prefix in prefixes:
            parsed = urlsplit(prefix)
            if parsed.scheme != "https" or parsed.hostname not in hosts:
                raise ConnectorError(f"executable prefix escapes catalog hosts: {provider_id}")
        if mode in {"direct-read", "terms-read"} and billing.get("requires_separate_paid_authorization"):
            raise ConnectorError(f"paid provider cannot be direct: {provider_id}")
    return catalog


def policy_for(provider_id: str, catalog: dict[str, object], acknowledge_terms: bool) -> Policy:
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
        raise ConnectorError("metered or paid execution is disabled; use a user-supplied external tool")
    if policy.mode == "conditional-job":
        raise ConnectorError(
            "remote submission is conditional and not implemented by this read-only executor"
        )
    if policy.mode == "terms-read" and not acknowledge_terms:
        raise ConnectorError("this provider requires --acknowledge-terms for academic-use terms")
    return policy


def decoded_path(path: str) -> str:
    decoded = path
    for _ in range(3):
        decoded = unquote(decoded)
    return decoded


def _decoded_path_has_traversal(path: str) -> bool:
    decoded = decoded_path(path)
    return "\\" in decoded or any(part in {".", ".."} for part in decoded.split("/"))


def validate_read_only_semantics(provider_id: str, url: str) -> None:
    parsed = urlsplit(url)
    path = decoded_path(parsed.path).lower()
    query = [(key.lower(), value.strip().lower()) for key, value in parse_qsl(parsed.query, keep_blank_values=True)]
    if provider_id == "ncbi-eutils":
        if path.endswith("/epost.fcgi"):
            raise ConnectorError("NCBI EPost writes to the History server and requires a job adapter")
        for key, value in query:
            history_write = (
                key == "webenv"
                or (key == "usehistory" and value not in {"", "0", "false", "n", "no"})
                or (key == "cmd" and value == "neighbor_history")
            )
            if history_write:
                raise ConnectorError("NCBI History-server writes are outside direct-read mode")
    elif provider_id == "pubchem-pug-rest":
        if PUBCHEM_ASYNC_PATH.match(path) or re.search(r"/(?:listkey|cachekey)(?:/|$)", path):
            raise ConnectorError("PubChem asynchronous and stored-result paths require a job adapter")
        for key, value in query:
            if key in {"listkey", "cachekey"} or (
                key == "list_return" and value in {"listkey", "cachekey"}
            ):
                raise ConnectorError("PubChem stored-result creation requires a job adapter")
    elif provider_id == "enrichr":
        if re.search(r"/(?:api/)?addlist/?$", path):
            raise ConnectorError("Enrichr list submission is outside direct-read mode")


def normalized_query_key(key: str) -> str:
    return re.sub(r"[-_.\s]+", "", key.strip().lower())


def is_sensitive_query_key(key: str) -> bool:
    normalized = normalized_query_key(key)
    return (
        normalized in SECRET_QUERY_KEYS
        or normalized in SECRET_KEY_FAMILY
        or any(fragment in normalized for fragment in SECRET_QUERY_FRAGMENTS)
    )


def sensitive_query_pairs(url: str) -> frozenset[tuple[str, str]]:
    return frozenset(
        (normalized_query_key(key), value)
        for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True)
        if is_sensitive_query_key(key)
    )


def validate_url(
    provider_id: str,
    url: str,
    policy: Policy,
) -> str:
    if any(ord(char) < 32 for char in url):
        raise ConnectorError("URL contains control characters")
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
        raise ConnectorError("credentials and contact fields are not accepted by the shared executor")
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
    redacted = [
        (key, "<redacted>" if is_sensitive_query_key(key) else value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(redacted), ""))


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
                raise ConnectorError("response ended before its declared Content-Length")
            return bytes(body)
        body.extend(chunk)
        if len(body) > remaining:
            raise ConnectorError("response exceeds --max-bytes")


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
        request = Request(url, headers=headers, method=method)
        try:
            response = open_request(request, timeout)
            try:
                try:
                    status = int(getattr(response, "status", 200))
                except (TypeError, ValueError) as exc:
                    raise ConnectorError("response status is invalid") from exc
                if status not in SUCCESS_STATUS[method]:
                    raise ConnectorError(f"HTTP response status {status} is not a completed result")
                try:
                    body = b"" if method == "HEAD" else read_bounded(response, max_bytes)
                except (OSError, HTTPException) as exc:
                    raise ConnectorError("response body could not be read completely") from exc
                if status == 204 and body:
                    raise ConnectorError("HTTP 204 response unexpectedly contained a body")
                response_url = validate_url(
                    provider_id,
                    str(getattr(response, "geturl")()),
                    policy,
                )
                response_headers = getattr(response, "headers")
                return body, {
                    "status": status,
                    "response_url": redact_url(response_url),
                    "content_type": response_headers.get("Content-Type"),
                    "etag": response_headers.get("ETag"),
                    "last_modified": response_headers.get("Last-Modified"),
                }
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except HTTPError as exc:
            last_error = exc
            if exc.code not in RETRYABLE_STATUS or attempt == retries:
                raise ConnectorError(f"HTTP request failed with status {exc.code}") from exc
            sleeper(retry_delay(exc, attempt))
        except URLError as exc:
            last_error = exc
            if attempt == retries:
                raise ConnectorError("network request failed after retries") from exc
            sleeper(retry_delay(None, attempt))
    raise ConnectorError(f"network request failed: {last_error}")


def with_page(url: str, parameter: str, value: int) -> str:
    parsed = urlsplit(url)
    params = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if key != parameter]
    params.append((parameter, str(value)))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(params), ""))


def prepare_temp(path: Path, data: bytes) -> Path:
    if not path.parent.is_dir():
        raise ConnectorError(f"output directory does not exist: {path.parent}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary
    except OSError as exc:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
        raise ConnectorError(f"could not prepare output: {exc}") from exc


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def unlink_if_owned(target: Path, temporary: Path) -> None:
    try:
        if os.path.samestat(target.stat(), temporary.stat()):
            target.unlink()
    except FileNotFoundError:
        pass


def unlink_temp(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass


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
    output_published = False
    provenance_published = False
    try:
        output_temp = prepare_temp(output, payload)
        provenance_temp = prepare_temp(provenance_path, provenance)
        os.link(output_temp, output)
        output_published = True
        os.link(provenance_temp, provenance_path)
        provenance_published = True
        for directory in {output.parent, provenance_path.parent}:
            fsync_directory(directory)
    except FileExistsError as exc:
        if provenance_temp is not None and provenance_published:
            unlink_if_owned(provenance_path, provenance_temp)
        if output_temp is not None and output_published:
            unlink_if_owned(output, output_temp)
        raise ConnectorError("output or provenance already exists; overwrite is forbidden") from exc
    except OSError as exc:
        if provenance_temp is not None and provenance_published:
            unlink_if_owned(provenance_path, provenance_temp)
        if output_temp is not None and output_published:
            unlink_if_owned(output, output_temp)
        raise ConnectorError(f"could not publish create-new output pair: {exc}") from exc
    finally:
        unlink_temp(output_temp)
        unlink_temp(provenance_temp)


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
    provenance_path = args.provenance or output.with_name(f"{output.name}.provenance.json")
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
        payload = (json.dumps({"pages": pages}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
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
    provenance_bytes = (json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
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
    def __init__(self, url: str, body: bytes, *, status: int = 200, content_type: str = "application/json") -> None:
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
    validate_url("uniprot-rest", "https://rest.uniprot.org/uniprotkb/P04637.json", uniprot)
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
    ):
        try:
            validate_url(
                "uniprot-rest",
                f"https://rest.uniprot.org/uniprotkb/P04637.json?{secret_key}=not-a-secret",
                uniprot,
            )
        except ConnectorError:
            pass
        else:
            raise ConnectorError(f"credential query key was accepted: {secret_key}")
    checks += 1
    for bad_url in (
        "http://rest.uniprot.org/uniprotkb/P04637.json",
        "https://example.org/uniprotkb/P04637.json",
        "https://rest.uniprot.org/../private",
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
    for submission_url in (
        "https://maayanlab.cloud/Enrichr/addList",
        "https://maayanlab.cloud/Enrichr/api/addList",
    ):
        try:
            validate_url("enrichr", submission_url, enrichr)
        except ConnectorError:
            pass
        else:
            raise ConnectorError("Enrichr submission path became executable")
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
    if allowed_redirect is None or allowed_redirect.full_url != "https://rest.uniprot.org/uniprotkb/Q9Y6K9.json":
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
        environment_names = ("NCBI_API_KEY", "BIO02_NCBI_API_KEY", "NCBI_EMAIL", "BIO02_NCBI_EMAIL")
        previous_environment = {name: os.environ.get(name) for name in environment_names}
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
        provenance_text = output.with_name(f"{output.name}.provenance.json").read_text(encoding="utf-8")
        visible = json.dumps(event, sort_keys=True) + provenance_text + output.read_text(encoding="utf-8")
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
            open_request=lambda request, timeout: FakeResponse(request.full_url, b"large"),
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
            publish_outputs(rolled_back, b"temporary", provenance_sentinel, b"overwrite")
        except ConnectorError:
            pass
        else:
            raise ConnectorError("pair rollback self-test failed")
        if rolled_back.exists() or provenance_sentinel.read_bytes() != b"keep-provenance":
            raise ConnectorError("partial pair survived failed publication")
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
        raise argparse.ArgumentTypeError(f"{label} must be between {minimum} and {maximum}")
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
        type=lambda value: bounded_int(
            value, minimum=1, maximum=120, label="timeout"
        ),
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
        if any((args.provider, args.url, args.output, args.provenance, args.page_param, args.acknowledge_terms)):
            raise ConnectorError("--self-test cannot be combined with execution arguments")
        return
    if not args.provider or not args.url or args.output is None:
        raise ConnectorError("--provider, --url, and --output are required")
    if args.pages > 1:
        if not args.page_param or not PAGE_PARAMETER.fullmatch(args.page_param):
            raise ConnectorError("multi-page mode requires a valid --page-param")
        if is_sensitive_query_key(args.page_param):
            raise ConnectorError("credential fields cannot be pagination parameters")
    elif args.page_param:
        raise ConnectorError("--page-param is only valid when --pages is greater than one")


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
