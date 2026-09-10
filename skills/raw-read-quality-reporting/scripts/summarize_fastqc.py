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


def parse_fastqc(raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise UserError("fastqc-encoding", "FastQC data must be UTF-8.") from exc
    lines = text.splitlines()
    require(
        lines and lines[0].startswith("##FastQC\t"),
        "fastqc-format",
        "Supply fastqc_data.txt or one FastQC ZIP; this helper does not run FASTQ analysis.",
    )
    version = lines[0].split("\t", 1)[1]
    modules = []
    current = None
    basic = {}
    for line in lines[1:]:
        if line == ">>END_MODULE":
            require(current is not None, "fastqc-module", "Unexpected module end.")
            current = None
        elif line.startswith(">>"):
            require(
                current is None, "fastqc-module", "A previous module was not closed."
            )
            parts = line[2:].split("\t")
            require(
                len(parts) == 2 and parts[1] in {"pass", "warn", "fail"},
                "fastqc-status",
                "Require recognized module status.",
            )
            current = parts[0]
            require(
                current not in {m["name"] for m in modules},
                "duplicate-module",
                "Duplicate modules are not accepted.",
            )
            modules.append({"name": current, "status": parts[1]})
        elif current == "Basic Statistics" and line and not line.startswith("#"):
            parts = line.split("\t")
            require(
                len(parts) == 2 and parts[0] not in basic,
                "basic-statistics",
                "Malformed or duplicate basic metric.",
            )
            basic[parts[0]] = parts[1]
    require(
        current is None and "Filename" in basic and "Total Sequences" in basic,
        "fastqc-incomplete",
        "FastQC modules or essential metrics are incomplete.",
    )
    total = finite(basic["Total Sequences"])
    require(
        total >= 0 and total.is_integer(),
        "read-count",
        "Total sequences must be a nonnegative integer.",
    )
    return {
        "fastqc_version": version,
        "source_filename": basic["Filename"],
        "total_sequences": int(total),
        "basic_statistics": basic,
        "modules": modules,
    }


def main():
    p = argparse.ArgumentParser(
        description="Summarize an explicit small list of existing FastQC reports without reading raw reads."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--reports", nargs="+")
    p.add_argument("--output")
    p.add_argument("--library-context")
    a = p.parse_args()
    if a.self_test:
        n = base_checks()
        r = parse_fastqc(
            b"##FastQC\t0.12.1\n>>Basic Statistics\tpass\nFilename\ta.fastq\nTotal Sequences\t20\n>>END_MODULE\n"
        )
        assert r["total_sequences"] == 20
        try:
            parse_fastqc(b"##FastQC\t0.12.1\n>>Basic Statistics\tpass\n")
        except UserError:
            pass
        else:
            raise AssertionError("partial report accepted")
        return {"status": "pass", "version": VERSION, "checks": n + 2}
    require(
        a.reports and 1 <= len(a.reports) <= 16 and a.output and a.library_context,
        "missing-contract",
        "Declare 1–16 LABEL=REPORT inputs, library context and a new output JSON.",
        "needs-decision",
    )
    import zipfile

    results = []
    hashes = {}
    seen_names = set()
    for item in a.reports:
        require("=" in item, "report-label", "Use LABEL=PATH.")
        label, path = item.split("=", 1)
        require(
            re.fullmatch(r"[A-Za-z0-9_-]{1,40}", label) and label not in hashes,
            "report-label",
            "Use unique simple sample/mate labels.",
        )
        raw = read_local(path)
        hashes[label] = hashlib.sha256(raw).hexdigest()
        if raw.startswith(b"PK"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    members = [
                        x
                        for x in archive.infolist()
                        if x.filename.endswith("/fastqc_data.txt")
                        or x.filename == "fastqc_data.txt"
                    ]
                    require(
                        len(members) == 1 and members[0].file_size <= MAX_BYTES,
                        "fastqc-archive",
                        "Require exactly one bounded FastQC data member.",
                    )
                    with archive.open(members[0]) as stream:
                        raw = stream.read(MAX_BYTES + 1)
                    require(
                        len(raw) <= MAX_BYTES,
                        "decompression-limit",
                        "Decompressed report exceeds 8 MiB.",
                    )
            except (zipfile.BadZipFile, RuntimeError) as exc:
                raise UserError(
                    "fastqc-archive", "Invalid or encrypted archive."
                ) from exc
        result = parse_fastqc(raw)
        require(
            result["source_filename"] not in seen_names,
            "duplicate-source",
            "Repeated internal filenames could hide sample duplication; resolve the report identity.",
        )
        seen_names.add(result["source_filename"])
        results.append({"label": label, **result})
    report = report_base(
        "goose_fastqc_summary", {"library_context": a.library_context}, hashes
    )
    report["results"] = results
    report["limitations"] = [
        "Summarizes existing FastQC reports only; no raw FASTQ was analyzed, trimmed or uploaded.",
        "FastQC warning/failure flags are attention signals, not automatic sample rejection or trimming decisions.",
        "Each supplied report is preserved separately; library-specific expected biases require researcher interpretation.",
    ]
    new_file(a.output, encoded(report))
    return {"status": "completed", "reports": len(results), "version": VERSION}


if __name__ == "__main__":
    raise SystemExit(cli(main))
