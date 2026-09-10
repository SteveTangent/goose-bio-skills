#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Original, embedded I/O boundary: each exported helper remains standalone.
import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

MAX_BYTES = 8 * 1024 * 1024


class UserError(ValueError):
    def __init__(self, code, message, status="invalid-input"):
        self.code, self.status = code, status
        super().__init__(message)


def require(condition, code, message, status="invalid-input"):
    if not condition:
        raise UserError(code, message, status)


def local_path(value):
    path = Path(value)
    root = Path.cwd().resolve()
    require(
        ".." not in path.parts,
        "parent-traversal",
        "Use a path within the working directory.",
    )
    path = path if path.is_absolute() else root / path
    require(
        path != root and path.is_relative_to(root),
        "outside-workspace",
        "Use a file or new output directory inside the working directory.",
    )
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        require(
            not current.is_symlink(), "symlink-path", "Symlink paths are not accepted."
        )
    require(
        path.parent.is_dir(),
        "missing-parent",
        "Create the output parent directory first.",
    )
    return path


def read_local(value):
    path = local_path(value)
    fd = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(before.st_mode) and before.st_size <= MAX_BYTES,
            "input-size-or-type",
            "Use a regular file of at most 8 MiB.",
        )
        data = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    require(
        len(data) <= MAX_BYTES
        and (before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_ino, after.st_size, after.st_mtime_ns),
        "input-changed",
        "The input changed or exceeded its size limit.",
    )
    return data


def parse_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(
                key not in result, "duplicate-json-key", "JSON keys must be unique."
            )
            result[key] = value
        return result

    try:
        return json.loads(
            data,
            object_pairs_hook=pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, UserError):
            raise
        raise UserError("invalid-json", "Use finite, valid UTF-8 JSON.") from exc


def read_json(value):
    data = read_local(value)
    return parse_json(data), hashlib.sha256(data).hexdigest()


def tsv(data):
    try:
        rows = list(
            csv.reader(io.StringIO(data.decode("utf-8")), delimiter="\t", strict=True)
        )
    except (UnicodeError, csv.Error) as exc:
        raise UserError("invalid-tsv", "Use a UTF-8 tab-separated table.") from exc
    require(
        len(rows) >= 2 and len(rows[0]) == len(set(rows[0])),
        "table-header",
        "A unique header and data rows are required.",
    )
    require(
        all(len(row) == len(rows[0]) for row in rows),
        "table-shape",
        "Every row must match the header.",
    )
    require(
        all(
            cell and len(cell) <= 256 and not any(ord(c) < 32 for c in cell)
            for row in rows
            for cell in row
        ),
        "table-cell",
        "Empty, oversized or control-character fields are not accepted.",
    )
    return rows


def encoded(value):
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        + "\n"
    ).encode("utf-8")


def new_file(value, data):
    path = local_path(value)
    require(
        not path.exists(),
        "output-exists",
        "Choose a new output path; existing files are preserved.",
        "invalid-output",
    )
    require(
        len(data) <= 64 * 1024 * 1024,
        "output-size",
        "Output exceeds the bounded size.",
        "invalid-output",
    )
    fd, stage = tempfile.mkstemp(prefix=".goose-stage-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(stage, path, follow_symlinks=False)
    finally:
        os.unlink(stage)


def new_bundle(value, files):
    """Reserve a new directory exclusively; rollback only files we created."""
    path = local_path(value)
    require(
        not path.exists(),
        "output-exists",
        "Choose a new output directory.",
        "invalid-output",
    )
    require(
        files
        and all(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", name) for name in files
        ),
        "bundle-names",
        "Invalid output member.",
        "invalid-output",
    )
    require(
        sum(map(len, files.values())) <= 64 * 1024 * 1024,
        "output-size",
        "Output exceeds 64 MiB.",
        "invalid-output",
    )
    created = []
    with tempfile.TemporaryDirectory(prefix=".goose-stage-", dir=path.parent) as stage:
        for name, data in files.items():
            with (Path(stage) / name).open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        path.mkdir(mode=0o700, exist_ok=False)
        directory_id = path.stat().st_ino
        try:
            for name in files:
                target = path / name
                os.link(Path(stage) / name, target, follow_symlinks=False)
                created.append((target, target.stat().st_ino))
        except BaseException:
            if not path.is_symlink() and path.stat().st_ino == directory_id:
                for target, identity in created:
                    if (
                        not target.is_symlink()
                        and target.exists()
                        and target.stat().st_ino == identity
                    ):
                        target.unlink()
                try:
                    path.rmdir()
                except OSError:
                    pass
            raise


def base_checks():
    old = Path.cwd()
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            new_file("a.json", encoded({"value": 1}))
            before = Path("a.json").read_bytes()
            try:
                new_file("a.json", b"changed")
            except UserError:
                pass
            else:
                raise AssertionError("overwrite accepted")
            assert Path("a.json").read_bytes() == before
            Path("link").symlink_to("a.json")
            for path in ["link", "../outside"]:
                try:
                    read_local(path)
                except UserError:
                    pass
                else:
                    raise AssertionError("unsafe path accepted")
            for payload in [b'{"a":1,"a":2}', b'{"a":NaN}']:
                try:
                    parse_json(payload)
                except UserError:
                    pass
                else:
                    raise AssertionError("invalid JSON accepted")
            new_bundle("bundle", {"a.txt": b"a", "b.txt": b"b"})
            try:
                new_bundle("bundle", {"a.txt": b"changed"})
            except UserError:
                pass
            else:
                raise AssertionError("bundle overwritten")
            assert (Path("bundle") / "a.txt").read_bytes() == b"a"
        finally:
            os.chdir(old)
    return 6


def cli(run):
    try:
        result = run()
        print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
        return 0
    except UserError as exc:
        print(
            json.dumps(
                {
                    "status": exc.status,
                    "code": exc.code,
                    "message": str(exc),
                    "analysis_completed": False,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        print(
            json.dumps(
                {
                    "status": "invalid-input",
                    "code": "unsupported-record-schema",
                    "message": "Check the input record shape and declared adapter version.",
                    "analysis_completed": False,
                }
            ),
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "io-error",
                    "code": type(exc).__name__,
                    "analysis_completed": False,
                }
            ),
            file=sys.stderr,
        )
        return 3


# Explicit tabular contracts shared at authoring time; each export is standalone.
def read_table(path):
    raw = read_local(path)
    try:
        rows = list(
            csv.reader(io.StringIO(raw.decode("utf-8")), delimiter="\t", strict=True)
        )
    except (UnicodeError, csv.Error) as exc:
        raise UserError("invalid-tsv", "Use a UTF-8 TSV with a header.") from exc
    require(
        len(rows) >= 2
        and rows[0]
        and all(rows[0])
        and len(set(rows[0])) == len(rows[0]),
        "table-header",
        "Use unique nonempty columns and data rows.",
    )
    require(
        len(rows) <= 100001 and all(len(r) == len(rows[0]) for r in rows),
        "table-shape",
        "Use a bounded rectangular table.",
    )
    require(
        all(
            len(v) <= 1024 and not any(ord(c) < 32 for c in v) for r in rows for v in r
        ),
        "table-cell",
        "Table cells must be bounded single-line values.",
    )
    return (
        rows[0],
        [dict(zip(rows[0], r)) for r in rows[1:]],
        hashlib.sha256(raw).hexdigest(),
    )


def fields(header, names):
    require(
        all(n in header for n in names) and len(names) == len(set(names)),
        "columns",
        "Declare distinct existing input columns.",
    )


def finite(value):
    require(not isinstance(value, bool), "number", "Use finite numeric values.")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise UserError("number", "Use finite numeric values.") from exc
    require(math.isfinite(result), "number", "Non-finite values are not measurements.")
    return result


def identity(value):
    require(
        isinstance(value, str)
        and 0 < len(value) <= 128
        and not any(ord(c) < 32 for c in value),
        "identifier",
        "Use nonempty, unique, bounded identifiers.",
    )
    return value


def table_bytes(header, rows):
    stream = io.StringIO()
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def report_base(name, config, hashes):
    return {
        "schema_version": "1.0",
        "status": "completed",
        "tool": {"name": name, "version": VERSION},
        "config": config,
        "input_sha256": hashes,
        "network_performed": False,
        "limitations": [],
    }


VERSION = "0.11.0"


def geo_directory(accession):
    require(
        re.fullmatch(r"GSE[1-9][0-9]{0,8}", accession or "") is not None,
        "accession",
        "Use one valid GSE accession.",
    )
    digits = accession[3:]
    bucket = "GSE" + (digits[:-3] if len(digits) > 3 else "") + "nnn"
    return f"https://ftp.ncbi.nlm.nih.gov/geo/series/{bucket}/{accession}/matrix/"


def parse_matrix(raw, accession, platform, scale):
    if raw[:2] == b"\x1f\x8b":
        import gzip

        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
        except (OSError, EOFError) as exc:
            raise UserError("gzip", "Invalid compressed matrix.") from exc
    require(
        len(raw) <= 16 * 1024 * 1024,
        "decompression-limit",
        "Expanded matrix must be at most 16 MiB.",
    )
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise UserError("encoding", "Matrix must be UTF-8.") from exc
    require(
        lines.count("!series_matrix_table_begin") == 1
        and lines.count("!series_matrix_table_end") == 1,
        "series-matrix",
        "Use one complete GEO Series Matrix file, not SOFT family or arbitrary supplementary data.",
    )
    begin = lines.index("!series_matrix_table_begin")
    end = lines.index("!series_matrix_table_end")
    require(
        begin < end and not any(l.strip() for l in lines[end + 1 :]),
        "matrix-boundary",
        "Unexpected data after the matrix or reversed markers.",
    )
    meta = []
    for line in lines[:begin]:
        if not line:
            continue
        require(
            line.startswith("!"),
            "metadata",
            "Unexpected nonmetadata line before matrix.",
        )
        values = next(csv.reader([line], delimiter="\t", strict=True))
        meta.append({"field": values[0][1:], "values": values[1:]})
    table = list(csv.reader(lines[begin + 1 : end], delimiter="\t", strict=True))
    require(
        len(table) >= 2 and table[0][0] == "ID_REF" and 1 <= len(table[0]) - 1 <= 256,
        "matrix-header",
        "Expect ID_REF followed by up to 256 unique GSM columns.",
    )
    samples = table[0][1:]
    require(
        len(set(samples)) == len(samples)
        and all(re.fullmatch(r"GSM[1-9][0-9]*", s) for s in samples),
        "sample-ids",
        "Use unique GSM sample IDs.",
    )
    require(
        len(table) - 1 <= 30000 and all(len(r) == len(table[0]) for r in table),
        "matrix-shape",
        "Use at most 30,000 rectangular feature rows.",
    )
    ids = [identity(r[0]) for r in table[1:]]
    require(
        len(set(ids)) == len(ids), "feature-ids", "Feature identifiers must be unique."
    )

    def values(field):
        return [m["values"] for m in meta if m["field"] == field]

    require(
        values("Series_geo_accession") == [[accession]],
        "series-identity",
        "File accession differs from the requested study.",
    )
    require(
        values("Sample_geo_accession") == [samples],
        "sample-metadata",
        "Sample metadata order differs from the matrix.",
    )
    require(
        values("Sample_platform_id") == [[platform] * len(samples)],
        "platform",
        "Use one explicitly selected matching platform; do not combine platforms.",
    )
    missing = 0
    for row in table[1:]:
        for value in row[1:]:
            if value in {"", "NA", "null"}:
                missing += 1
                continue
            number = finite(value)
            require(
                scale != "raw-counts"
                or (number >= 0 and number.is_integer() and number <= 2**31 - 1),
                "count-scale",
                "Declared counts contain values incompatible with the count contract.",
            )
    return samples, table, meta, missing


def main():
    p = argparse.ArgumentParser(
        description="Plan a bounded GEO matrix retrieval or prepare one explicitly selected local Series Matrix."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--accession")
    p.add_argument("--index")
    p.add_argument("--matrix")
    p.add_argument("--platform")
    p.add_argument("--output")
    p.add_argument("--samples")
    p.add_argument(
        "--scale",
        choices=["raw-counts", "tpm", "log2-normalized", "processed-other", "unknown"],
    )
    a = p.parse_args()
    if a.self_test:
        n = base_checks()
        assert geo_directory("GSE10").endswith(
            "/GSEnnn/GSE10/matrix/"
        ) and "/GSE123nnn/" in geo_directory("GSE123456")
        try:
            geo_directory("GSE1/../x")
        except UserError:
            pass
        else:
            raise AssertionError("unsafe accession accepted")
        return {"status": "pass", "version": VERSION, "checks": n + 2}
    require(a.output, "output", "Declare a new output path.", "needs-decision")
    url = geo_directory(a.accession)
    require(
        not (a.index and a.matrix), "mode", "Use index discovery or a matrix, not both."
    )
    if not a.matrix:
        candidates = []
        hashes = {}
        if a.index:
            raw = read_local(a.index)
            hashes["index"] = hashlib.sha256(raw).hexdigest()
            from html.parser import HTMLParser

            class Links(HTMLParser):
                def handle_starttag(self, tag, attrs):
                    if tag == "a":
                        for key, value in attrs:
                            if key == "href" and re.fullmatch(
                                re.escape(a.accession)
                                + r"(?:-GPL[0-9]+)?_series_matrix\.txt\.gz",
                                value or "",
                            ):
                                candidates.append(url + value)

            Links().feed(raw.decode("utf-8"))
            require(
                candidates,
                "matrix-list",
                "No supported matrix filenames were found; do not guess a supplementary format.",
                "needs-tool",
            )
        report = report_base(
            "goose_geo_preparation", {"accession": a.accession}, hashes
        )
        report.update(
            status="needs-download" if not candidates else "needs-decision",
            retrieval={
                "provider": "ncbi-geo-files",
                "directory_url": url,
                "candidate_urls": sorted(set(candidates)),
                "max_download_bytes": 5 * 1024 * 1024,
                "instruction": "Use the shared bounded connector to list, inspect HEAD/size, and fetch one explicitly selected matrix; this helper makes no network request.",
            },
        )
        new_file(a.output, encoded(report))
        return {
            "status": report["status"],
            "candidate_files": len(set(candidates)),
            "version": VERSION,
        }
    require(
        a.platform and re.fullmatch(r"GPL[1-9][0-9]*", a.platform) and a.scale,
        "matrix-contract",
        "Declare the selected platform and actual scale; unknown stays unresolved.",
        "needs-decision",
    )
    raw = read_local(a.matrix)
    samples, table, meta, missing = parse_matrix(raw, a.accession, a.platform, a.scale)
    hashes = {"matrix": hashlib.sha256(raw).hexdigest()}
    metadata_columns = []
    metadata_values = []
    counts = {}
    for entry in meta:
        if entry["field"].startswith("Sample_"):
            require(
                len(entry["values"]) == len(samples),
                "metadata-width",
                "Sample fields must align exactly to GSM columns.",
            )
            name = entry["field"]
            counts[name] = counts.get(name, 0) + 1
            metadata_columns.append(name + "__" + str(counts[name]))
            metadata_values.append(entry["values"])
    curated = [["sample_id", "condition"]] + [[s, ""] for s in samples]
    unresolved = ["condition"]
    if a.samples:
        h, rs, d = read_table(a.samples)
        fields(h, ["sample_id", "condition"])
        require(
            len(rs) == len(samples) and {r["sample_id"] for r in rs} == set(samples),
            "curated-samples",
            "Curated samples must uniquely and exactly match the matrix.",
        )
        lookup = {r["sample_id"]: r for r in rs}
        require(
            all(lookup[s]["condition"] for s in samples),
            "condition",
            "Curated conditions cannot be blank.",
        )
        curated = [h] + [[lookup[s][c] for c in h] for s in samples]
        unresolved = []
        hashes["curated_samples"] = d
    if a.scale == "unknown":
        unresolved.append("data-scale")
    if missing:
        unresolved.append("missing-measurements")
    report = report_base(
        "goose_geo_preparation",
        {"accession": a.accession, "platform": a.platform, "declared_scale": a.scale},
        hashes,
    )
    report.update(
        samples=len(samples),
        features=len(table) - 1,
        missing_values=missing,
        unresolved=unresolved,
        original_metadata=meta,
        annotation_status="Original feature IDs retained; biological identifier mapping not inferred.",
    )
    if unresolved:
        report["status"] = "needs-decision"
    report["limitations"] = [
        "Series Matrix preparation only; no group/scale inference, annotation lookup, normalization or differential analysis.",
        "Original metadata fields and repeated characteristics are preserved; title text is never treated as instructions.",
        "A completed preparation does not establish compatibility with count-DE; processed arrays, TPM and unknown scales cannot be passed as raw counts.",
    ]
    files = {
        "expression.tsv": table_bytes(["feature_id", *samples], table[1:]),
        "features.tsv": table_bytes(["feature_id"], [[r[0]] for r in table[1:]]),
        "samples.tsv": table_bytes(curated[0], curated[1:]),
        "original-samples.tsv": table_bytes(
            ["sample_id", *metadata_columns],
            [[s, *[v[i] for v in metadata_values]] for i, s in enumerate(samples)],
        ),
        "preparation.json": encoded(report),
    }
    new_bundle(a.output, files)
    return {
        "status": report["status"],
        "samples": len(samples),
        "features": len(table) - 1,
        "version": VERSION,
    }


if __name__ == "__main__":
    raise SystemExit(cli(main))
