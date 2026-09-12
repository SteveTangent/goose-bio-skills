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


VERSION = "0.13.0"


def numeric(x):
    return (
        isinstance(x, (float, int))
        and not isinstance(x, bool)
        and math.isfinite(x)
        and 0 <= x <= 1e12
    )


def distance_input(raw, fmt, metric):
    if fmt == "square-tsv":
        table = tsv(raw)
        samples = table[0][1:]
        require(
            table[0][0] == "sample_id"
            and len(table) == len(samples) + 1
            and [r[0] for r in table[1:]] == samples,
            "distance-shape",
            "Use a square table headed sample_id, with identical row and column sample order.",
        )
        try:
            values = [[float(v) for v in r[1:]] for r in table[1:]]
        except ValueError as exc:
            raise UserError(
                "missing-distance",
                "Every distance must be numeric; missing pairs are not filled.",
            ) from exc
    else:
        source = parse_json(raw)
        require(
            source.get("schema_version") == "1.0"
            and source.get("analysis", {}).get("method")
            == "pairwise-descriptive-beta-diversity-distances",
            "distance-source",
            "Use the native bounded beta-distance helper result.",
        )
        samples = source["sample_ids"]
        pairs = source["pairs"]
        n = len(samples)
        require(
            isinstance(samples, list)
            and 3 <= n <= 128
            and all(isinstance(x, str) and 0 < len(x) <= 128 for x in samples)
            and len(set(samples)) == n,
            "sample-identities",
            "Use 3–128 unique sample IDs before constructing a matrix.",
        )
        require(
            metric in {"bray_curtis", "jaccard_presence_absence"},
            "distance-metric",
            "Choose one native distance metric.",
            "needs-decision",
        )
        require(
            isinstance(pairs, list) and len(pairs) == n * (n - 1) // 2,
            "missing-pairs",
            "Each distinct sample pair must be present exactly once.",
        )
        require(
            not source.get("zero_depth_sample_ids"),
            "zero-depth",
            "Resolve zero-depth samples upstream; undefined distances cannot be filled.",
            "needs-decision",
        )
        positions = {s: i for i, s in enumerate(samples)}
        values = [[0.0] * n for _ in samples]
        seen = set()
        for pair in pairs:
            a, b = pair["sample_a"], pair["sample_b"]
            require(
                a in positions and b in positions and a != b,
                "pair-identities",
                "Pair sample IDs must match the sample inventory.",
            )
            key = tuple(sorted([a, b]))
            require(
                key not in seen, "duplicate-pair", "Duplicate pairs are not allowed."
            )
            seen.add(key)
            entry = pair[metric]
            require(
                entry.get("status") == "estimated"
                and not pair.get("zero_depth_sample_ids"),
                "undefined-distance",
                "A distance is not estimable; resolve the upstream reason.",
                "needs-decision",
            )
            value = entry.get("value")
            num = entry.get("numerator")
            den = entry.get("denominator")
            require(
                numeric(value)
                and numeric(num)
                and numeric(den)
                and den > 0
                and num <= den
                and math.isclose(value, num / den, rel_tol=1e-12, abs_tol=1e-15),
                "ratio-integrity",
                "Native distance must agree with its stored numerator and denominator.",
            )
            i, j = positions[a], positions[b]
            values[i][j] = values[j][i] = value
    require(
        isinstance(samples, list)
        and 3 <= len(samples) <= 128
        and all(
            isinstance(s, str) and 0 < len(s) <= 128 and not any(ord(c) < 32 for c in s)
            for s in samples
        )
        and len(set(samples)) == len(samples),
        "sample-identities",
        "Use 3–128 unique nonempty sample IDs.",
    )
    require(
        all(numeric(v) for row in values for v in row),
        "distance-values",
        "Distances must be finite, nonnegative and at most 1e12.",
    )
    require(
        all(values[i][i] == 0 for i in range(len(samples))),
        "diagonal",
        "The diagonal must be exactly zero.",
    )
    require(
        all(
            values[i][j] == values[j][i] for i in range(len(samples)) for j in range(i)
        ),
        "symmetry",
        "Distances must be symmetric; this helper does not silently average mismatched entries.",
    )
    return samples, values


def ordinates(values):
    try:
        import numpy as np
    except ImportError as exc:
        raise UserError(
            "numpy-required",
            "Use a trusted Python environment with NumPy.",
            "needs-tool",
        ) from exc
    d = np.asarray(values, dtype=float)
    scale = float(d.max())
    require(
        scale > 0,
        "zero-distances",
        "All distances are zero; there is no ordination to interpret.",
        "needs-decision",
    )
    # Normalize only inside the eigensolver for numerical range; restore original units below.
    squared = (d / scale) ** 2
    gram = -0.5 * (
        squared
        - squared.mean(axis=0)[None, :]
        - squared.mean(axis=1)[:, None]
        + squared.mean()
    )
    try:
        eigen, vectors = np.linalg.eigh(gram)
    except np.linalg.LinAlgError as exc:
        raise UserError(
            "eigensolver", "The symmetric eigensolver did not converge.", "needs-tool"
        ) from exc
    order = np.argsort(eigen)[::-1]
    eigen = eigen[order] * scale**2
    vectors = vectors[:, order]
    tolerance = float(np.max(np.abs(eigen))) * 1e-10
    positive = eigen > tolerance
    negative = eigen < -tolerance
    require(
        bool(positive.any()),
        "no-positive-axis",
        "No positive axis exceeds the declared numerical tolerance.",
        "needs-decision",
    )
    coords = vectors[:, positive] * np.sqrt(eigen[positive])
    negcoords = vectors[:, negative] * np.sqrt(-eigen[negative])
    for array in [coords, negcoords]:
        for j in range(array.shape[1]):
            if array[np.argmax(np.abs(array[:, j])), j] < 0:
                array[:, j] *= -1
    pos = float(eigen[positive].sum())
    neg = float(-eigen[negative].sum())
    spectrum = [
        {
            "axis": i + 1,
            "eigenvalue": float(v),
            "classification": "positive"
            if v > tolerance
            else "negative"
            if v < -tolerance
            else "numerical-zero",
            "fraction_positive_sum": float(v / pos) if v > tolerance else 0.0,
            "fraction_absolute_sum": float(abs(v) / (pos + neg))
            if abs(v) > tolerance
            else 0.0,
        }
        for i, v in enumerate(eigen)
    ]
    reconstructed = np.sqrt(
        np.maximum(0, ((coords[:, None, :] - coords[None, :, :]) ** 2).sum(axis=2))
    )
    return {
        "eigenvalues": spectrum,
        "coordinates": coords.tolist(),
        "negative_coordinates": negcoords.tolist(),
        "eigenvalue_tolerance": tolerance,
        "positive_inertia": pos,
        "negative_inertia_magnitude": neg,
        "negative_inertia_fraction": neg / (pos + neg),
        "positive_axes": int(positive.sum()),
        "negative_axes": int(negative.sum()),
        "positive_space_relative_distance_error": float(
            np.linalg.norm(reconstructed - d) / np.linalg.norm(d)
        ),
        "axis_fraction_definition": "positive eigenvalue / sum of eigenvalues above tolerance; excludes negative and numerical-zero eigenvalues",
        "absolute_fraction_definition": "absolute eigenvalue / (positive sum + negative magnitude), excluding numerical-zero eigenvalues",
        "runtime_versions": {"numpy": np.__version__, "python": sys.version.split()[0]},
    }


def table_bytes(rows):
    out = io.StringIO()
    csv.writer(out, delimiter="\t", lineterminator="\n").writerows(rows)
    return out.getvalue().encode()


def main():
    p = argparse.ArgumentParser(
        description="Classical PCoA of an existing complete distance matrix; no group inference."
    )
    p.add_argument("--self-test", action="store_true")
    for n in ["distances", "metadata", "output", "metric"]:
        p.add_argument("--" + n)
    p.add_argument("--format", choices=["square-tsv", "beta-json"])
    a = p.parse_args()
    if a.self_test:
        ids, values = distance_input(
            b"sample_id\ta\tb\tc\na\t0\t1\t2\nb\t1\t0\t1\nc\t2\t1\t0\n",
            "square-tsv",
            "euclidean",
        )
        assert ids == ["a", "b", "c"] and values[0][2] == 2
        try:
            distance_input(
                b"sample_id\ta\tb\tc\na\t0\t2\t2\nb\t1\t0\t1\nc\t2\t1\t0\n",
                "square-tsv",
                "euclidean",
            )
        except UserError as e:
            assert e.code == "symmetry"
        else:
            raise AssertionError("asymmetry accepted")
        return {
            "status": "pass",
            "checks": base_checks() + 2,
            "version": VERSION,
            "scope": "dependency-free input and I/O checks; eigensolver checked separately",
        }
    require(
        a.distances and a.output and a.format and a.metric,
        "required-facts",
        "Provide distance input, format, declared metric and a new output directory.",
        "needs-decision",
    )
    require(
        0 < len(a.metric) <= 80 and not any(ord(c) < 32 for c in a.metric),
        "metric-label",
        "Use a short metric label.",
    )
    raw = read_local(a.distances)
    samples, values = distance_input(raw, a.format, a.metric)
    groups = {s: "sample" for s in samples}
    hashes = {"distances": hashlib.sha256(raw).hexdigest()}
    if a.metadata:
        raw_meta = read_local(a.metadata)
        meta = tsv(raw_meta)
        require(
            meta[0] == ["sample_id", "group"]
            and len(meta) == len(samples) + 1
            and len({r[0] for r in meta[1:]}) == len(samples)
            and {r[0] for r in meta[1:]} == set(samples),
            "sample-join",
            "Group metadata must match each distance sample exactly once.",
        )
        groups = dict(meta[1:])
        hashes["metadata"] = hashlib.sha256(raw_meta).hexdigest()
    result = ordinates(values)
    result.update(
        schema_version="1.0",
        status="completed",
        tool={"name": "goose_pcoa", "version": VERSION},
        config={
            "format": a.format,
            "metric": a.metric,
            "correction": "none",
            "eigenvalue_relative_tolerance": 1e-10,
        },
        input_sha256=hashes,
        sample_ids=samples,
        groups=groups,
    )
    result["warnings"] = (
        [
            "Negative eigenvalues are retained; positive-axis plots distort non-Euclidean distances. Inspect negative inertia and reconstruction error."
        ]
        if result["negative_axes"]
        else []
    ) + (
        ["Only one positive axis exists; the display pads PCoA2 with zero."]
        if result["positive_axes"] == 1
        else []
    )
    result["limitations"] = [
        "PCoA uses distances; it is not PCA on an abundance matrix.",
        "Axis percentages use only positive eigenvalues above tolerance, not total signed inertia.",
        "No correction, normalization, rarefaction, PERMANOVA, dispersion test or differential abundance. Group separation does not establish statistical significance.",
        "Sign orientation is canonical within distinct axes; tied eigenspaces may rotate across numerical libraries.",
    ]
    files = {
        "coordinates.tsv": table_bytes(
            [
                [
                    "sample_id",
                    "group",
                    *[f"PCoA{i+1}" for i in range(result["positive_axes"])],
                ],
                *[
                    [s, groups[s], *row]
                    for s, row in zip(samples, result["coordinates"])
                ],
            ]
        ),
        "eigenvalues.tsv": table_bytes(
            [
                list(result["eigenvalues"][0]),
                *[list(r.values()) for r in result["eigenvalues"]],
            ]
        ),
    }
    result["files"] = list(files)
    result["output_sha256"] = {
        k: hashlib.sha256(v).hexdigest() for k, v in files.items()
    }
    files["pcoa.json"] = encoded(result)
    new_bundle(a.output, files)
    return {
        "status": "completed",
        "samples": len(samples),
        "negative_axes": result["negative_axes"],
        "version": VERSION,
    }


if __name__ == "__main__":
    raise SystemExit(cli(main))
