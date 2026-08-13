#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run one bounded protein-level differential-abundance contrast with limma."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


VERSION = "0.8.0"
EXPECTED_R_VERSION = "4.4.1"
EXPECTED_LIMMA_VERSION = "3.60.6"
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_PROTEINS = 50_000
MAX_SAMPLES = 256
MAX_COVARIATES = 4
MAX_IDENTIFIER_CHARS = 128
WORKER_TIMEOUT_SECONDS = 120
TRUSTED_RSCRIPT_CANDIDATES = (
    Path("/usr/local/bin/Rscript"),
    Path("/opt/homebrew/bin/Rscript"),
    Path("/usr/bin/Rscript"),
)
SAFE_COLUMN = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
SAFE_FACTOR = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")

# This immutable worker is copied byte-for-byte into the private run directory.
# It is never composed with caller text, and its digest is recorded in reports.
FIXED_LIMMA_WORKER = r'''#!/usr/bin/env Rscript
# SPDX-License-Identifier: Apache-2.0

EXPECTED_R_VERSION <- "4.4.1"
EXPECTED_LIMMA_VERSION <- "3.60.6"

fail_closed <- function(status, code, exit_status = 65L) {
  cat(paste("BIO02_ERROR", status, code, sep = "\t"), "\n", sep = "", file = stderr())
  quit(save = "no", status = exit_status, runLast = FALSE)
}

arguments <- commandArgs(trailingOnly = TRUE)
if (length(arguments) != 8L) {
  fail_closed("invalid-input", "invalid-worker-arguments")
}

matrix_path <- arguments[[1L]]
metadata_path <- arguments[[2L]]
condition_column <- arguments[[3L]]
numerator <- arguments[[4L]]
denominator <- arguments[[5L]]
covariate_token <- arguments[[6L]]
result_path <- arguments[[7L]]
metadata_result_path <- arguments[[8L]]
covariate_columns <- if (identical(covariate_token, "-")) {
  character(0L)
} else {
  strsplit(covariate_token, ",", fixed = TRUE)[[1L]]
}

if (!identical(as.character(getRversion()), EXPECTED_R_VERSION)) {
  fail_closed("needs-tool", "unsupported-r-version", 69L)
}
if (!requireNamespace("limma", quietly = TRUE)) {
  fail_closed("needs-tool", "limma-not-installed", 69L)
}
if (!identical(as.character(utils::packageVersion("limma")), EXPECTED_LIMMA_VERSION)) {
  fail_closed("needs-tool", "unsupported-limma-version", 69L)
}

options(stringsAsFactors = FALSE, warn = 2, digits = 17)

tryCatch({
  abundance_table <- utils::read.delim(
    matrix_path,
    header = TRUE,
    check.names = FALSE,
    quote = "",
    comment.char = "",
    na.strings = NULL
  )
  sample_table <- utils::read.delim(
    metadata_path,
    header = TRUE,
    check.names = FALSE,
    quote = "",
    comment.char = "",
    na.strings = NULL
  )

  if (ncol(abundance_table) < 2L || nrow(abundance_table) < 1L) {
    fail_closed("invalid-input", "empty-canonical-matrix")
  }
  if (nrow(sample_table) != ncol(abundance_table) - 1L) {
    fail_closed("invalid-input", "canonical-sample-count-mismatch")
  }
  if (!identical(as.character(sample_table[[1L]]), names(abundance_table)[-1L])) {
    fail_closed("invalid-input", "canonical-sample-order-mismatch")
  }

  abundance <- as.matrix(abundance_table[-1L])
  storage.mode(abundance) <- "double"
  if (any(!is.finite(abundance))) {
    fail_closed("invalid-input", "nonfinite-canonical-abundance")
  }
  rownames(abundance) <- as.character(abundance_table[[1L]])

  model_columns <- c(condition_column, covariate_columns)
  if (!all(model_columns %in% names(sample_table))) {
    fail_closed("invalid-input", "canonical-metadata-column-missing")
  }
  model_data <- sample_table[model_columns]
  for (column in model_columns) {
    model_data[[column]] <- factor(
      as.character(model_data[[column]]),
      levels = sort(unique(as.character(model_data[[column]])))
    )
  }

  model_formula <- stats::reformulate(model_columns, intercept = FALSE)
  design <- stats::model.matrix(model_formula, data = model_data)
  design_rank <- qr(design)$rank
  if (design_rank != ncol(design)) {
    fail_closed("invalid-input", "rank-deficient-design")
  }
  residual_df <- nrow(design) - design_rank
  if (residual_df < 1L) {
    fail_closed("invalid-input", "no-residual-degrees-of-freedom")
  }

  numerator_column <- paste0(condition_column, numerator)
  denominator_column <- paste0(condition_column, denominator)
  if (!(numerator_column %in% colnames(design)) ||
      !(denominator_column %in% colnames(design))) {
    fail_closed("invalid-input", "contrast-not-estimable")
  }
  contrast <- numeric(ncol(design))
  names(contrast) <- colnames(design)
  contrast[[numerator_column]] <- 1
  contrast[[denominator_column]] <- -1
  if (any(abs(drop(qr.resid(qr(t(design)), contrast))) > 1e-10)) {
    fail_closed("invalid-input", "contrast-not-estimable")
  }

  fit <- limma::lmFit(abundance, design)
  fit <- limma::contrasts.fit(fit, contrasts = matrix(contrast, ncol = 1L))
  fit <- limma::eBayes(fit, trend = FALSE, robust = FALSE)

  moderated_se <- as.vector(fit$stdev.unscaled[, 1L] * sqrt(fit$s2.post))
  results <- data.frame(
    protein_id = rownames(abundance),
    effect_log2 = as.vector(fit$coefficients[, 1L]),
    moderated_standard_error = moderated_se,
    moderated_t = as.vector(fit$t[, 1L]),
    raw_p_value = as.vector(fit$p.value[, 1L]),
    adjusted_p_value = stats::p.adjust(as.vector(fit$p.value[, 1L]), method = "BH"),
    average_log2_abundance = as.vector(fit$Amean),
    total_degrees_of_freedom = as.vector(fit$df.total),
    b_statistic = as.vector(fit$lods[, 1L]),
    check.names = FALSE,
    stringsAsFactors = FALSE
  )
  if (any(!is.finite(as.matrix(results[-1L])))) {
    fail_closed("invalid-input", "nonfinite-model-result")
  }

  worker_metadata <- data.frame(
    key = c(
      "r_version",
      "limma_version",
      "design_formula",
      "design_columns",
      "design_rank",
      "residual_degrees_of_freedom",
      "contrast_label",
      "proteins",
      "samples"
    ),
    value = c(
      as.character(getRversion()),
      as.character(utils::packageVersion("limma")),
      paste("~ 0 +", paste(model_columns, collapse = " + ")),
      paste(colnames(design), collapse = ","),
      as.character(design_rank),
      as.character(residual_df),
      paste0(numerator, "-", denominator),
      as.character(nrow(abundance)),
      as.character(ncol(abundance))
    ),
    stringsAsFactors = FALSE
  )

  utils::write.table(
    results,
    file = result_path,
    sep = "\t",
    quote = FALSE,
    row.names = FALSE,
    col.names = TRUE,
    na = ""
  )
  utils::write.table(
    worker_metadata,
    file = metadata_result_path,
    sep = "\t",
    quote = FALSE,
    row.names = FALSE,
    col.names = TRUE,
    na = ""
  )
}, error = function(error) {
  fail_closed("invalid-input", "model-fit-failed")
})
'''


class ContractError(Exception):
    """A fail-closed boundary result safe to expose without local paths."""

    def __init__(self, status: str, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def fail(status: str, code: str, message: str) -> ContractError:
    return ContractError(status, code, message)


def _validate_lexical_path(path: Path, role: str) -> None:
    if not str(path) or "\x00" in str(path):
        raise fail("invalid-input", f"invalid-{role}-path", f"{role} path is invalid")
    if ".." in path.parts:
        raise fail(
            "invalid-input",
            f"parent-traversal-{role}-path",
            f"{role} path may not contain parent traversal",
        )


def _open_input_without_symlink(path: Path, role: str) -> int:
    """Open a file from cwd without following any path-component symlink."""
    try:
        root = Path.cwd()
        resolved_root = root.resolve(strict=True)
        if root.is_symlink() or not resolved_root.is_dir():
            raise fail("invalid-input", "unsafe-input-root", "input root is unsafe")
        if path.is_absolute():
            raw = Path(os.path.abspath(path))
            try:
                relative = raw.relative_to(resolved_root)
            except ValueError as exc:
                raise fail(
                    "invalid-input",
                    f"{role}-outside-root",
                    f"{role} must remain inside the current root",
                ) from exc
        else:
            relative = path
        if not relative.parts:
            raise fail("invalid-input", f"invalid-{role}-path", f"{role} path is invalid")
        directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        directory_flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved_root, directory_flags)
        try:
            for part in relative.parts[:-1]:
                child = os.open(part, directory_flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            file_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            opened = os.open(relative.name, file_flags, dir_fd=descriptor)
            os.close(descriptor)
            return opened
        except BaseException:
            os.close(descriptor)
            raise
    except ContractError:
        raise
    except (OSError, ValueError) as exc:
        raise fail(
            "invalid-input",
            f"{role}-unsafe-path",
            f"{role} path is unsafe or unreadable",
        ) from exc


def read_stable_input(path: Path, role: str) -> tuple[bytes, str]:
    """Read a stable, bounded, regular, non-symlink UTF-8 file."""
    _validate_lexical_path(path, role)
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise fail("invalid-input", f"{role}-not-regular", f"{role} must be a regular file")
        if before.st_size > MAX_INPUT_BYTES:
            raise fail("invalid-input", f"{role}-too-large", f"{role} exceeds the byte cap")
        descriptor = _open_input_without_symlink(path, role)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise fail("invalid-input", f"{role}-not-regular", f"{role} must be a regular file")
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise fail("invalid-input", f"{role}-changed", f"{role} changed during validation")
            payload = bytearray()
            while len(payload) <= MAX_INPUT_BYTES:
                chunk = os.read(descriptor, min(1024 * 1024, MAX_INPUT_BYTES + 1 - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
            after_open = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after_path = path.lstat()
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(payload) > MAX_INPUT_BYTES:
            raise fail("invalid-input", f"{role}-too-large", f"{role} exceeds the byte cap")
        if any(getattr(opened, field) != getattr(after_open, field) for field in stable):
            raise fail("invalid-input", f"{role}-changed", f"{role} changed during read")
        if any(getattr(after_open, field) != getattr(after_path, field) for field in stable):
            raise fail("invalid-input", f"{role}-changed", f"{role} changed during read")
        raw = bytes(payload)
        try:
            return raw, raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise fail("invalid-input", f"{role}-not-utf8", f"{role} must be UTF-8") from exc
    except ContractError:
        raise
    except (OSError, ValueError) as exc:
        raise fail("invalid-input", f"{role}-unreadable", f"{role} is unreadable") from exc


def choose_delimiter(path: Path, text: str) -> tuple[str, str]:
    if path.suffix.lower() == ".csv":
        return ",", "csv"
    if path.suffix.lower() in {".tsv", ".tab"}:
        return "\t", "tsv"
    try:
        delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",\t").delimiter
    except csv.Error as exc:
        raise fail("invalid-input", "delimiter-not-detected", "input delimiter was not detected") from exc
    return delimiter, "tsv" if delimiter == "\t" else "csv"


def _parse_rows(text: str, delimiter: str, role: str) -> list[list[str]]:
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter, strict=True))
    except csv.Error as exc:
        raise fail("invalid-input", f"malformed-{role}", f"{role} is malformed") from exc
    if not rows or not rows[0]:
        raise fail("invalid-input", f"missing-{role}-header", f"{role} has no header")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise fail("invalid-input", f"ragged-{role}", f"{role} has ragged rows")
    if any(value != value.strip() for row in rows for value in row):
        raise fail("invalid-input", f"whitespace-in-{role}", f"{role} fields may not have edge whitespace")
    return rows


def _validate_header(header: list[str], role: str) -> None:
    if any(not SAFE_COLUMN.fullmatch(field) for field in header):
        raise fail("invalid-input", f"invalid-{role}-header", f"{role} has an unsafe column name")
    if len(set(header)) != len(header):
        raise fail("invalid-input", f"duplicate-{role}-header", f"{role} has duplicate columns")


def parse_matrix(
    payload: bytes,
    text: str,
    path: Path,
    protein_id_column: str,
) -> dict[str, Any]:
    delimiter, delimiter_name = choose_delimiter(path, text)
    rows = _parse_rows(text, delimiter, "matrix")
    header = rows[0]
    _validate_header(header, "matrix")
    if protein_id_column not in header:
        raise fail("invalid-input", "missing-protein-id-column", "matrix lacks the protein ID column")
    protein_index = header.index(protein_id_column)
    samples = [field for index, field in enumerate(header) if index != protein_index]
    if len(samples) < 4:
        raise fail("invalid-input", "too-few-samples", "matrix requires at least four samples")
    if len(samples) > MAX_SAMPLES:
        raise fail("invalid-input", "too-many-samples", "matrix exceeds the sample cap")
    if len(set(samples)) != len(samples):
        raise fail("invalid-input", "duplicate-matrix-sample", "matrix sample columns must be unique")
    if any(not SAFE_IDENTIFIER.fullmatch(sample) for sample in samples):
        raise fail("invalid-input", "invalid-matrix-sample", "matrix has an unsafe sample ID")
    if len(rows) == 1:
        raise fail("invalid-input", "no-proteins", "matrix has no protein rows")
    if len(rows) - 1 > MAX_PROTEINS:
        raise fail("invalid-input", "too-many-proteins", "matrix exceeds the protein cap")

    proteins: list[str] = []
    values: list[list[float]] = []
    for row in rows[1:]:
        protein_id = row[protein_index]
        if not SAFE_IDENTIFIER.fullmatch(protein_id) or len(protein_id) > MAX_IDENTIFIER_CHARS:
            raise fail("invalid-input", "invalid-protein-id", "matrix has an unsafe protein ID")
        proteins.append(protein_id)
        numeric_row: list[float] = []
        for index, raw in enumerate(row):
            if index == protein_index:
                continue
            if raw == "":
                raise fail("invalid-input", "missing-abundance", "matrix contains a missing abundance")
            try:
                value = float(raw)
            except ValueError as exc:
                raise fail("invalid-input", "nonnumeric-abundance", "matrix contains a nonnumeric abundance") from exc
            if not math.isfinite(value):
                raise fail("invalid-input", "nonfinite-abundance", "matrix contains a nonfinite abundance")
            numeric_row.append(0.0 if value == 0.0 else value)
        values.append(numeric_row)
    if len(set(proteins)) != len(proteins):
        raise fail("invalid-input", "duplicate-protein-id", "matrix protein IDs must be unique")
    return {
        "payload": payload,
        "delimiter": delimiter_name,
        "protein_id_column": protein_id_column,
        "proteins": proteins,
        "samples": samples,
        "values": values,
    }


def parse_metadata(
    payload: bytes,
    text: str,
    path: Path,
    *,
    sample_id_column: str,
    condition_column: str,
    covariate_columns: list[str],
    matrix_samples: list[str],
    numerator: str,
    denominator: str,
) -> dict[str, Any]:
    delimiter, delimiter_name = choose_delimiter(path, text)
    rows = _parse_rows(text, delimiter, "metadata")
    header = rows[0]
    _validate_header(header, "metadata")
    required = [sample_id_column, condition_column, *covariate_columns]
    if len(set(required)) != len(required):
        raise fail("invalid-input", "metadata-role-collision", "metadata column roles must be distinct")
    if set(header) != set(required) or len(header) != len(required):
        raise fail(
            "invalid-input",
            "metadata-columns-not-exact",
            "metadata must contain exactly the declared columns",
        )
    if len(covariate_columns) > MAX_COVARIATES:
        raise fail("invalid-input", "too-many-covariates", "covariate count exceeds the cap")
    if any(not SAFE_COLUMN.fullmatch(column) for column in required):
        raise fail("invalid-input", "invalid-declared-column", "a declared column name is unsafe")
    if not SAFE_FACTOR.fullmatch(numerator) or not SAFE_FACTOR.fullmatch(denominator):
        raise fail("invalid-input", "invalid-contrast-level", "contrast levels are unsafe")
    if numerator == denominator:
        raise fail("needs-decision", "identical-contrast-levels", "numerator and denominator must differ")

    by_sample: dict[str, dict[str, str]] = {}
    for row in rows[1:]:
        record = dict(zip(header, row, strict=True))
        sample_id = record[sample_id_column]
        if not SAFE_IDENTIFIER.fullmatch(sample_id):
            raise fail("invalid-input", "invalid-metadata-sample", "metadata has an unsafe sample ID")
        if sample_id in by_sample:
            raise fail("invalid-input", "duplicate-metadata-sample", "metadata sample IDs must be unique")
        if any(not SAFE_FACTOR.fullmatch(record[column]) for column in [condition_column, *covariate_columns]):
            raise fail("invalid-input", "invalid-factor-level", "metadata has an unsafe factor level")
        by_sample[sample_id] = record
    if set(by_sample) != set(matrix_samples) or len(by_sample) != len(matrix_samples):
        raise fail("invalid-input", "sample-set-mismatch", "metadata samples must exactly match matrix samples")
    ordered = [by_sample[sample] for sample in matrix_samples]
    conditions = [record[condition_column] for record in ordered]
    for level, role in ((numerator, "numerator"), (denominator, "denominator")):
        if level not in conditions:
            raise fail("needs-decision", f"missing-{role}-level", f"declared {role} level is absent")
        if conditions.count(level) < 2:
            raise fail("invalid-input", f"unreplicated-{role}-level", f"declared {role} requires replication")
    for column in covariate_columns:
        if len({record[column] for record in ordered}) < 2:
            raise fail("invalid-input", "constant-covariate", "declared covariates must vary")
    return {
        "payload": payload,
        "delimiter": delimiter_name,
        "rows": ordered,
        "sample_id_column": sample_id_column,
        "condition_column": condition_column,
        "covariate_columns": covariate_columns,
    }


def _write_canonical_inputs(directory: Path, matrix: dict[str, Any], metadata: dict[str, Any]) -> tuple[Path, Path]:
    matrix_path = directory / "matrix.tsv"
    metadata_path = directory / "metadata.tsv"
    with matrix_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow([matrix["protein_id_column"], *matrix["samples"]])
        for protein_id, values in zip(matrix["proteins"], matrix["values"], strict=True):
            writer.writerow([protein_id, *(format(value, ".17g") for value in values)])
    with metadata_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        fields = [metadata["sample_id_column"], metadata["condition_column"], *metadata["covariate_columns"]]
        writer.writerow(fields)
        for record in metadata["rows"]:
            writer.writerow([record[field] for field in fields])
    os.chmod(matrix_path, 0o600)
    os.chmod(metadata_path, 0o600)
    return matrix_path, metadata_path


def resolve_rscript(override: Path | None = None) -> Path:
    candidates = (override,) if override is not None else TRUSTED_RSCRIPT_CANDIDATES
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            resolved = candidate.resolve(strict=True)
            details = resolved.stat()
        except OSError:
            continue
        if stat.S_ISREG(details.st_mode) and os.access(resolved, os.X_OK):
            return resolved
    if override is not None:
        raise fail("needs-tool", "rscript-unavailable", "Rscript is unavailable")
    raise fail("needs-tool", "rscript-not-found", "Rscript is unavailable")


def bundled_worker() -> tuple[bytes, str]:
    payload = FIXED_LIMMA_WORKER.encode("utf-8")
    return payload, hashlib.sha256(payload).hexdigest()


def _run_worker(
    matrix: dict[str, Any],
    metadata: dict[str, Any],
    *,
    numerator: str,
    denominator: str,
    rscript_override: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str], str]:
    rscript = resolve_rscript(rscript_override)
    worker_payload, worker_sha256 = bundled_worker()
    with tempfile.TemporaryDirectory(prefix="protein-limma-") as temporary_name:
        directory = Path(temporary_name)
        os.chmod(directory, 0o700)
        worker = directory / "fit_limma.R"
        with worker.open("xb") as handle:
            handle.write(worker_payload)
        os.chmod(worker, 0o600)
        canonical_matrix, canonical_metadata = _write_canonical_inputs(directory, matrix, metadata)
        result_path = directory / "results.tsv"
        worker_metadata_path = directory / "worker-metadata.tsv"
        covariates = ",".join(metadata["covariate_columns"]) or "-"
        environment = {
            "HOME": str(directory),
            "LANG": "C",
            "LC_ALL": "C",
            "MKL_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "PATH": os.defpath,
            "R_DEFAULT_PACKAGES": "NULL",
            "TMPDIR": str(directory),
            "TZ": "UTC",
            "VECLIB_MAXIMUM_THREADS": "1",
        }
        command = [
            str(rscript),
            "--vanilla",
            str(worker),
            str(canonical_matrix),
            str(canonical_metadata),
            metadata["condition_column"],
            numerator,
            denominator,
            covariates,
            str(result_path),
            str(worker_metadata_path),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=WORKER_TIMEOUT_SECONDS,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise fail("needs-tool", "r-worker-unavailable", "fixed R worker could not complete") from exc
        if completed.returncode != 0:
            for line in completed.stderr.splitlines():
                fields = line.split("\t")
                if len(fields) == 3 and fields[0] == "BIO02_ERROR" and fields[1] in {
                    "invalid-input", "needs-tool"
                }:
                    raise fail(fields[1], fields[2], "fixed R worker rejected the request")
            raise fail("needs-tool", "r-worker-failed", "fixed R worker failed closed")
        if completed.stdout.strip():
            raise fail("needs-tool", "unexpected-worker-output", "fixed R worker emitted unexpected output")
        if not result_path.is_file() or result_path.is_symlink():
            raise fail("needs-tool", "missing-worker-results", "fixed R worker did not create results")
        if not worker_metadata_path.is_file() or worker_metadata_path.is_symlink():
            raise fail("needs-tool", "missing-worker-metadata", "fixed R worker did not create metadata")
        result_rows = _parse_worker_results(result_path, matrix["proteins"])
        worker_metadata = _parse_worker_metadata(worker_metadata_path)
        return result_rows, worker_metadata, worker_sha256


RESULT_FIELDS = [
    "protein_id",
    "effect_log2",
    "moderated_standard_error",
    "moderated_t",
    "raw_p_value",
    "adjusted_p_value",
    "average_log2_abundance",
    "total_degrees_of_freedom",
    "b_statistic",
]


def _parse_worker_results(path: Path, expected_proteins: list[str]) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t", strict=True))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise fail("needs-tool", "invalid-worker-results", "fixed R worker returned invalid results") from exc
    if not rows or list(rows[0]) != RESULT_FIELDS or len(rows) != len(expected_proteins):
        raise fail("needs-tool", "invalid-worker-results", "fixed R worker returned invalid results")
    parsed: list[dict[str, Any]] = []
    for expected, row in zip(expected_proteins, rows, strict=True):
        if row["protein_id"] != expected:
            raise fail("needs-tool", "worker-result-order-mismatch", "fixed R worker changed protein order")
        item: dict[str, Any] = {"protein_id": expected}
        for field in RESULT_FIELDS[1:]:
            try:
                value = float(row[field])
            except (TypeError, ValueError) as exc:
                raise fail("needs-tool", "invalid-worker-number", "fixed R worker returned invalid numbers") from exc
            if not math.isfinite(value):
                raise fail("needs-tool", "nonfinite-worker-number", "fixed R worker returned nonfinite numbers")
            item[field] = 0.0 if value == 0.0 else value
        if not 0.0 <= item["raw_p_value"] <= 1.0 or not 0.0 <= item["adjusted_p_value"] <= 1.0:
            raise fail("needs-tool", "invalid-worker-pvalue", "fixed R worker returned invalid p-values")
        parsed.append(item)
    return parsed


def _parse_worker_metadata(path: Path) -> dict[str, str]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t", strict=True)
            if reader.fieldnames != ["key", "value"]:
                raise ValueError("unexpected header")
            pairs = list(reader)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        raise fail("needs-tool", "invalid-worker-metadata", "fixed R worker returned invalid metadata") from exc
    metadata = {row["key"]: row["value"] for row in pairs}
    expected = {
        "r_version",
        "limma_version",
        "design_formula",
        "design_columns",
        "design_rank",
        "residual_degrees_of_freedom",
        "contrast_label",
        "proteins",
        "samples",
    }
    if set(metadata) != expected or len(pairs) != len(expected):
        raise fail("needs-tool", "invalid-worker-metadata", "fixed R worker returned invalid metadata")
    if metadata["r_version"] != EXPECTED_R_VERSION or metadata["limma_version"] != EXPECTED_LIMMA_VERSION:
        raise fail("needs-tool", "worker-version-mismatch", "fixed R worker version metadata differs")
    return metadata


def analyze_files(
    *,
    matrix_path: Path,
    metadata_path: Path,
    protein_id_column: str,
    sample_id_column: str,
    condition_column: str,
    numerator: str,
    denominator: str,
    covariate_columns: list[str],
    declared_normalized_log2: bool,
    rscript_override: Path | None = None,
) -> dict[str, Any]:
    if not declared_normalized_log2:
        raise fail(
            "needs-decision",
            "missing-protein-level-normalized-log2-declaration",
            "caller must explicitly declare normalized log2 protein-level input",
        )
    if not numerator or not denominator:
        raise fail("needs-decision", "missing-primary-contrast", "one contrast must be declared")
    matrix_payload, matrix_text = read_stable_input(matrix_path, "matrix")
    metadata_payload, metadata_text = read_stable_input(metadata_path, "metadata")
    matrix = parse_matrix(matrix_payload, matrix_text, matrix_path, protein_id_column)
    metadata = parse_metadata(
        metadata_payload,
        metadata_text,
        metadata_path,
        sample_id_column=sample_id_column,
        condition_column=condition_column,
        covariate_columns=covariate_columns,
        matrix_samples=matrix["samples"],
        numerator=numerator,
        denominator=denominator,
    )
    results, worker_metadata, worker_sha256 = _run_worker(
        matrix,
        metadata,
        numerator=numerator,
        denominator=denominator,
        rscript_override=rscript_override,
    )
    try:
        design_rank = int(worker_metadata["design_rank"])
        residual_df = int(worker_metadata["residual_degrees_of_freedom"])
        proteins = int(worker_metadata["proteins"])
        samples = int(worker_metadata["samples"])
    except ValueError as exc:
        raise fail("needs-tool", "invalid-worker-metadata", "fixed R worker returned invalid metadata") from exc
    if proteins != len(matrix["proteins"]) or samples != len(matrix["samples"]):
        raise fail("needs-tool", "worker-dimension-mismatch", "fixed R worker dimensions differ")
    return {
        "schema_version": "1.0",
        "status": "completed",
        "analysis_performed": True,
        "tool": {
            "name": "protein-level-differential-abundance",
            "version": VERSION,
            "r_version": worker_metadata["r_version"],
            "limma_version": worker_metadata["limma_version"],
            "worker_sha256": worker_sha256,
        },
        "inputs": {
            "matrix": {
                "sha256": hashlib.sha256(matrix_payload).hexdigest(),
                "bytes": len(matrix_payload),
                "delimiter": matrix["delimiter"],
                "protein_id_column": protein_id_column,
                "proteins": len(matrix["proteins"]),
                "samples": len(matrix["samples"]),
                "sample_order": matrix["samples"],
            },
            "metadata": {
                "sha256": hashlib.sha256(metadata_payload).hexdigest(),
                "bytes": len(metadata_payload),
                "delimiter": metadata["delimiter"],
                "sample_id_column": sample_id_column,
            },
            "declarations": {
                "protein_level": True,
                "already_normalized": True,
                "log2_transformed": True,
                "finite_complete_matrix": True,
            },
        },
        "design": {
            "formula": worker_metadata["design_formula"],
            "columns": worker_metadata["design_columns"].split(","),
            "rank": design_rank,
            "residual_degrees_of_freedom": residual_df,
            "condition_column": condition_column,
            "categorical_covariate_columns": covariate_columns,
        },
        "contrast": {
            "label": worker_metadata["contrast_label"],
            "numerator": numerator,
            "denominator": denominator,
            "effect_direction": f"{numerator} minus {denominator} on the declared log2 scale",
            "multiplicity_adjustment": "Benjamini-Hochberg across all reported proteins",
        },
        "results": results,
        "limitations": [
            "One prespecified limma contrast on a complete normalized log2 protein-level matrix only.",
            "No raw-MS processing, protein inference, normalization, imputation, RNA-count analysis, enrichment, feature selection, biomarker claim, causal claim, or clinical use.",
            "A valid fit does not establish correct provenance, sufficient power, biological relevance, or freedom from unmeasured confounding.",
        ],
    }


def _safe_output_target(path: Path, root: Path | None = None) -> Path:
    _validate_lexical_path(path, "output")
    lexical_root = Path.cwd() if root is None else root
    try:
        if lexical_root.is_symlink():
            raise fail("invalid-input", "symlink-output-root", "output root may not be a symlink")
        resolved_root = lexical_root.resolve(strict=True)
    except OSError as exc:
        raise fail("invalid-input", "invalid-output-root", "output root is invalid") from exc
    if not resolved_root.is_dir():
        raise fail("invalid-input", "invalid-output-root", "output root must be a directory")
    if path.is_absolute():
        raw_candidate = Path(os.path.abspath(path))
        lexical_absolute_root = Path(os.path.abspath(lexical_root))
        try:
            candidate = resolved_root / raw_candidate.relative_to(lexical_absolute_root)
        except ValueError:
            candidate = raw_candidate
    else:
        candidate = Path(os.path.abspath(resolved_root / path))
    try:
        relative = candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise fail("invalid-input", "output-outside-root", "output must remain inside the current root") from exc
    if not relative.parts:
        raise fail("invalid-input", "output-not-file", "output must name a file")
    cursor = resolved_root
    for part in relative.parts[:-1]:
        cursor /= part
        if cursor.is_symlink():
            raise fail("invalid-input", "symlink-output-parent", "output parent may not be a symlink")
        if not cursor.is_dir():
            raise fail("invalid-input", "missing-output-parent", "output parent must already exist")
    if candidate.exists() or candidate.is_symlink():
        raise fail("invalid-input", "output-exists", "output path already exists")
    return candidate


def _open_output_parent(target: Path, root: Path | None = None) -> tuple[int, str]:
    lexical_root = Path.cwd() if root is None else root
    resolved_root = lexical_root.resolve(strict=True)
    relative = target.relative_to(resolved_root)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved_root, flags)
        try:
            for part in relative.parts[:-1]:
                child = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            return descriptor, relative.name
        except BaseException:
            os.close(descriptor)
            raise
    except ContractError:
        raise
    except OSError as exc:
        raise fail(
            "invalid-input",
            "unsafe-output-parent",
            "output parent changed or is unsafe",
        ) from exc


def _unlink_owned_at(name: str, directory_fd: int, identity: tuple[int, int]) -> bool:
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    if (current.st_dev, current.st_ino) != identity:
        return False
    os.unlink(name, dir_fd=directory_fd)
    return True


def _is_owned_at(name: str, directory_fd: int, identity: tuple[int, int]) -> bool:
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return (current.st_dev, current.st_ino) == identity


def _rollback_owned_at(
    directory_fd: int,
    identity: tuple[int, int],
    names: tuple[str, ...],
) -> None:
    failures: list[str] = []
    for name in names:
        try:
            if not _unlink_owned_at(name, directory_fd, identity):
                failures.append(f"{name}:identity-mismatch")
        except OSError as exc:
            failures.append(f"{name}:{exc.__class__.__name__}")
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        failures.append(f"directory:{exc.__class__.__name__}")
    if failures:
        raise OSError("publication rollback failed: " + ", ".join(failures))


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("output write made no progress")
        offset += written


def write_new(path: Path, rendered: str, root: Path | None = None) -> Path:
    target = _safe_output_target(path, root)
    directory_fd, target_name = _open_output_parent(target, root)
    temporary_name = f".{target_name}.tmp-{secrets.token_hex(12)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    identity: tuple[int, int] | None = None
    published = False
    try:
        try:
            os.stat(target_name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise fail("invalid-input", "output-exists", "output path already exists")
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        temporary_stat = os.fstat(descriptor)
        identity = (temporary_stat.st_dev, temporary_stat.st_ino)
        payload = rendered.encode("utf-8")
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        try:
            os.close(descriptor)
        finally:
            descriptor = -1
        try:
            os.link(
                temporary_name,
                target_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise fail("invalid-input", "output-exists", "output path already exists") from exc
        published = True
        if not _is_owned_at(target_name, directory_fd, identity):
            raise OSError("published output identity differs from staged data")
        if not _unlink_owned_at(temporary_name, directory_fd, identity):
            raise OSError("temporary output identity changed")
        os.fsync(directory_fd)
        if not _is_owned_at(target_name, directory_fd, identity):
            raise OSError("published output identity changed before completion")
    except BaseException as original:
        if descriptor >= 0:
            os.close(descriptor)
        if identity is not None:
            names = (target_name, temporary_name) if published else (temporary_name,)
            try:
                _rollback_owned_at(directory_fd, identity, names)
            except OSError as rollback_error:
                raise rollback_error from original
        raise
    finally:
        os.close(directory_fd)
    return target


FIXTURE_MATRIX = """protein_id,C1,C2,C3,T1,T2,T3
P1,10.0,10.2,9.7,12.1,11.8,12.3
P2,8.0,7.6,8.3,7.1,6.8,7.4
P3,5.0,5.5,4.8,5.1,4.7,5.4
P4,20.0,19.2,20.6,23.2,22.5,23.4
P5,2.0,2.3,1.8,1.2,1.5,0.9
P6,14.0,13.5,14.8,15.0,15.4,14.7
"""
FIXTURE_METADATA = """sample_id,condition
C1,control
C2,control
C3,control
T1,treated
T2,treated
T3,treated
"""


@contextmanager
def temporary_working_directory(path: Path) -> Any:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def self_test() -> None:
    checks = 0

    def check(condition: bool, message: str) -> None:
        nonlocal checks
        if not condition:
            raise RuntimeError(message)
        checks += 1

    def expect(code: str, operation: Any) -> None:
        nonlocal checks
        try:
            operation()
        except ContractError as exc:
            if exc.code != code:
                raise RuntimeError(f"expected {code}, received {exc.code}") from exc
        else:
            raise AssertionError(f"boundary {code} was accepted")
        checks += 1

    def expect_os_error(fragment: str, operation: Any) -> None:
        nonlocal checks
        try:
            operation()
        except OSError as exc:
            if fragment not in str(exc):
                raise RuntimeError(
                    f"expected OSError containing {fragment!r}, received {exc!r}"
                ) from exc
        else:
            raise AssertionError(f"I/O failure {fragment!r} was accepted")
        checks += 1

    @contextmanager
    def patched_os(name: str, replacement: Any) -> Iterator[None]:
        original = getattr(os, name)
        setattr(os, name, replacement)
        try:
            yield
        finally:
            setattr(os, name, original)

    with tempfile.TemporaryDirectory(prefix="protein-limma-selftest-") as temporary_name, \
            temporary_working_directory(Path(temporary_name)):
        root = Path.cwd()
        matrix_path = root / "matrix.csv"
        metadata_path = root / "metadata.csv"
        matrix_path.write_text(FIXTURE_MATRIX, encoding="utf-8")
        metadata_path.write_text(FIXTURE_METADATA, encoding="utf-8")

        arguments = {
            "matrix_path": matrix_path,
            "metadata_path": metadata_path,
            "protein_id_column": "protein_id",
            "sample_id_column": "sample_id",
            "condition_column": "condition",
            "numerator": "treated",
            "denominator": "control",
            "covariate_columns": [],
            "declared_normalized_log2": True,
        }
        first = analyze_files(**arguments)
        second = analyze_files(**arguments)
        first_rendered = json.dumps(first, allow_nan=False, indent=2, sort_keys=True) + "\n"
        second_rendered = json.dumps(second, allow_nan=False, indent=2, sort_keys=True) + "\n"
        if first_rendered != second_rendered or len(first["results"]) != 6:
            raise RuntimeError("repeatability fixture differs")
        if first["tool"]["r_version"] != EXPECTED_R_VERSION or first["tool"]["limma_version"] != EXPECTED_LIMMA_VERSION:
            raise RuntimeError("fixed adapter versions differ")
        p1 = first["results"][0]
        if not math.isclose(p1["effect_log2"], 2.1, abs_tol=1e-12):
            raise RuntimeError("fixture effect differs")
        checks += 2

        duplicate = root / "duplicate.csv"
        duplicate.write_text(FIXTURE_MATRIX.replace("P2,", "P1,"), encoding="utf-8")
        expect("duplicate-protein-id", lambda: analyze_files(**{**arguments, "matrix_path": duplicate}))

        missing = root / "missing.csv"
        missing.write_text(FIXTURE_MATRIX.replace("P2,8.0", "P2,"), encoding="utf-8")
        expect("missing-abundance", lambda: analyze_files(**{**arguments, "matrix_path": missing}))

        nonfinite = root / "nonfinite.csv"
        nonfinite.write_text(FIXTURE_MATRIX.replace("P2,8.0", "P2,Inf"), encoding="utf-8")
        expect("nonfinite-abundance", lambda: analyze_files(**{**arguments, "matrix_path": nonfinite}))

        mismatch = root / "mismatch.csv"
        mismatch.write_text(FIXTURE_METADATA.replace("T3,treated\n", ""), encoding="utf-8")
        expect("sample-set-mismatch", lambda: analyze_files(**{**arguments, "metadata_path": mismatch}))

        duplicated_metadata = root / "duplicated-metadata.csv"
        duplicated_metadata.write_text(FIXTURE_METADATA.replace("T3,treated", "T2,treated"), encoding="utf-8")
        expect("duplicate-metadata-sample", lambda: analyze_files(**{**arguments, "metadata_path": duplicated_metadata}))

        confounded = root / "confounded.csv"
        confounded.write_text(
            FIXTURE_METADATA.replace("sample_id,condition", "sample_id,condition,batch")
            .replace("C1,control", "C1,control,A")
            .replace("C2,control", "C2,control,A")
            .replace("C3,control", "C3,control,A")
            .replace("T1,treated", "T1,treated,B")
            .replace("T2,treated", "T2,treated,B")
            .replace("T3,treated", "T3,treated,B"),
            encoding="utf-8",
        )
        expect(
            "rank-deficient-design",
            lambda: analyze_files(**{**arguments, "metadata_path": confounded, "covariate_columns": ["batch"]}),
        )

        expect(
            "missing-protein-level-normalized-log2-declaration",
            lambda: analyze_files(**{**arguments, "declared_normalized_log2": False}),
        )
        expect(
            "rscript-unavailable",
            lambda: analyze_files(**{**arguments, "rscript_override": root / "not-rscript"}),
        )

        output = root / "report.json"
        write_new(output, first_rendered, root)
        expect("output-exists", lambda: write_new(output, "replacement\n", root))
        if output.read_text(encoding="utf-8") != first_rendered:
            raise RuntimeError("existing output was changed")

        zero_output = root / "zero.json"
        with patched_os("write", lambda _descriptor, _payload: 0):
            expect_os_error(
                "no progress",
                lambda: write_new(zero_output, first_rendered, root),
            )
        check(not zero_output.exists(), "zero-write publication left a final output")
        check(not list(root.glob(".zero.json.tmp-*")), "zero-write publication left a temporary output")

        original_write = os.write

        def short_write(descriptor: int, payload: bytes) -> int:
            return original_write(descriptor, payload[:max(1, len(payload) // 3)])

        short_output = root / "short.json"
        with patched_os("write", short_write):
            write_new(short_output, first_rendered, root)
        check(short_output.read_text(encoding="utf-8") == first_rendered, "short writes truncated output")

        final_identity_output = root / "final-identity.json"
        original_unlink = os.unlink
        final_identity_swapped = False

        def replace_final_during_cleanup(path: str, *args: Any, **kwargs: Any) -> None:
            nonlocal final_identity_swapped
            if not final_identity_swapped and path.startswith(".final-identity.json.tmp-"):
                final_identity_swapped = True
                original_unlink(final_identity_output.name, dir_fd=kwargs["dir_fd"])
                replacement = os.open(
                    final_identity_output.name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=kwargs["dir_fd"],
                )
                try:
                    _write_all(replacement, b"competitor\n")
                    os.fsync(replacement)
                finally:
                    os.close(replacement)
            original_unlink(path, *args, **kwargs)

        with patched_os("unlink", replace_final_during_cleanup):
            expect_os_error(
                "publication rollback failed",
                lambda: write_new(final_identity_output, first_rendered, root),
            )
        check(
            final_identity_output.read_bytes() == b"competitor\n",
            "identity check removed a replacement final output",
        )
        check(
            not list(root.glob(".final-identity.json.tmp-*")),
            "identity check left an owned temporary output",
        )
        final_identity_output.unlink()

        linked_input = root / "linked-matrix.csv"
        linked_input.symlink_to(matrix_path)
        expect("matrix-not-regular", lambda: analyze_files(**{**arguments, "matrix_path": linked_input}))

        real_input_parent = root / "real-input-parent"
        real_input_parent.mkdir()
        nested_matrix = real_input_parent / "matrix.csv"
        nested_matrix.write_text(FIXTURE_MATRIX, encoding="utf-8")
        linked_input_parent = root / "linked-input-parent"
        linked_input_parent.symlink_to(real_input_parent, target_is_directory=True)
        expect(
            "matrix-unsafe-path",
            lambda: analyze_files(
                **{**arguments, "matrix_path": linked_input_parent / "matrix.csv"}
            ),
        )
        expect(
            "parent-traversal-matrix-path",
            lambda: analyze_files(**{**arguments, "matrix_path": Path("..") / "matrix.csv"}),
        )

        real_parent = root / "real-parent"
        real_parent.mkdir()
        linked_parent = root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        expect("symlink-output-parent", lambda: write_new(linked_parent / "report.json", "{}\n", root))
        expect("parent-traversal-output-path", lambda: write_new(Path("..") / "escape.json", "{}\n", root))

    print(json.dumps({"checks": checks, "status": "pass", "version": VERSION}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--matrix", type=Path)
    result.add_argument("--metadata", type=Path)
    result.add_argument("--output", type=Path)
    result.add_argument("--protein-id-column", default="protein_id")
    result.add_argument("--sample-id-column", default="sample_id")
    result.add_argument("--condition-column", default="condition")
    result.add_argument("--numerator")
    result.add_argument("--denominator")
    result.add_argument("--covariate-column", action="append", default=[])
    result.add_argument("--declared-protein-level-normalized-log2", action="store_true")
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="version", version=VERSION)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.self_test:
        self_test()
        return 0
    missing = [name for name in ("matrix", "metadata", "output", "numerator", "denominator") if getattr(arguments, name) is None]
    if missing:
        error = fail("needs-decision", "missing-required-input", "required execution arguments are missing")
        print(json.dumps({
            "analysis_performed": False,
            "code": error.code,
            "message": error.message,
            "missing": [f"--{name.replace('_', '-')}" for name in missing],
            "status": error.status,
        }, sort_keys=True), file=sys.stderr)
        return 2
    try:
        _safe_output_target(arguments.output)
        report = analyze_files(
            matrix_path=arguments.matrix,
            metadata_path=arguments.metadata,
            protein_id_column=arguments.protein_id_column,
            sample_id_column=arguments.sample_id_column,
            condition_column=arguments.condition_column,
            numerator=arguments.numerator,
            denominator=arguments.denominator,
            covariate_columns=arguments.covariate_column,
            declared_normalized_log2=arguments.declared_protein_level_normalized_log2,
        )
        rendered = json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n"
        write_new(arguments.output, rendered)
        print(json.dumps({
            "analysis_performed": True,
            "output_created": True,
            "proteins": len(report["results"]),
            "samples": report["inputs"]["matrix"]["samples"],
            "status": "completed",
        }, sort_keys=True))
        return 0
    except ContractError as exc:
        print(json.dumps({
            "analysis_performed": False,
            "code": exc.code,
            "message": exc.message,
            "status": exc.status,
        }, sort_keys=True), file=sys.stderr)
        return 3 if exc.status == "needs-tool" else 2
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({
            "analysis_performed": False,
            "code": "local-io-failure",
            "message": "local I/O failed closed",
            "status": "io-error",
        }, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
