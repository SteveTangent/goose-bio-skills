#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a bounded, deterministic structural QC report for one Newick tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import secrets
import stat
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator


VERSION = "0.7.0"
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_NODES = 10_000
MAX_DEPTH = 256
MAX_LABEL_BYTES = 1024
NUMBER = re.compile(r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?")


class ContractError(Exception):
    """The requested report cannot safely or completely run."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: str = "invalid-input",
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.path = path

    def as_dict(self) -> dict[str, str]:
        result = {"code": self.code, "message": str(self)}
        if self.path is not None:
            result["path"] = self.path
        return result


@dataclass
class Node:
    label: str | None = None
    branch_length: float | None = None
    children: list["Node"] = field(default_factory=list)


def lexical_absolute(raw: str | Path) -> Path:
    raw_text = os.fspath(raw)
    if not raw_text or "\x00" in raw_text:
        raise ContractError("invalid-path", "path must be non-empty and contain no NUL byte")
    supplied = Path(raw_text)
    if ".." in supplied.parts:
        raise ContractError("parent-traversal", "parent traversal is forbidden", path=raw_text)
    return Path(os.path.abspath(supplied))


def checked_root(root: Path | None = None) -> Path:
    path = Path(os.path.abspath(Path.cwd() if root is None else root))
    try:
        metadata = os.lstat(path)
    except FileNotFoundError as exc:
        raise ContractError("working-directory-missing", "working directory does not exist", path=str(path)) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ContractError("unsafe-working-directory", "working directory must be a real directory", path=str(path))
    return path


def require_below_root(path: Path, root: Path) -> tuple[str, ...]:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ContractError("path-outside-working-directory", "path must remain below the working directory", path=str(path)) from exc
    if not relative.parts:
        raise ContractError("path-not-file", "path must name a file", path=str(path))
    return relative.parts


def open_parent_directory(root: Path, parts: tuple[str, ...], target: Path, *, output: bool) -> tuple[int, str]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise ContractError("unsafe-working-directory", "working directory changed or is unsafe", path=str(root)) from exc
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError as exc:
                code = "output-parent-missing" if output else "path-not-found"
                raise ContractError(code, "parent directory does not exist", path=str(target.parent)) from exc
            except OSError as exc:
                code = "output-parent-symlink" if output else "input-parent-symlink"
                raise ContractError(code, "parent directory changed or contains a symlink", path=str(target.parent)) from exc
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


@contextmanager
def bounded_binary_input(raw_path: str | Path, *, root: Path | None = None) -> Iterator[tuple[Path, os.stat_result, BinaryIO]]:
    lexical_root = checked_root(root)
    path = lexical_absolute(raw_path)
    parts = require_below_root(path, lexical_root)
    parent_fd, name = open_parent_directory(lexical_root, parts, path, output=False)
    try:
        try:
            before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise ContractError("path-not-found", "input does not exist", path=str(path)) from exc
        if stat.S_ISLNK(before.st_mode):
            raise ContractError("symlink-refused", "input must not be a leaf symlink", path=str(path))
        if not stat.S_ISREG(before.st_mode):
            raise ContractError("not-regular-file", "input must be a regular file", path=str(path))
        if before.st_size > MAX_INPUT_BYTES:
            raise ContractError(
                "input-too-large",
                f"input exceeds the {MAX_INPUT_BYTES}-byte package limit",
                status="needs-tool",
                path=str(path),
            )
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ContractError("input-open-failed", str(exc), path=str(path)) from exc
        handle: BinaryIO | None = None
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise ContractError("input-changed", "input changed while opening", path=str(path))
            handle = os.fdopen(descriptor, "rb")
            descriptor = -1
            yield path, opened, handle
            after_open = os.fstat(handle.fileno())
            try:
                after_path = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise ContractError("input-changed", "input changed during analysis", path=str(path)) from exc
            stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if stat.S_ISLNK(after_path.st_mode) or any(
                getattr(opened, item) != getattr(after_open, item)
                or getattr(after_open, item) != getattr(after_path, item)
                for item in stable
            ):
                raise ContractError("input-changed", "input changed during analysis", path=str(path))
        finally:
            if handle is not None:
                handle.close()
            elif descriptor >= 0:
                os.close(descriptor)
    finally:
        os.close(parent_fd)


def read_newick(raw_path: str | Path, *, root: Path | None = None) -> tuple[str, dict[str, Any]]:
    digest = hashlib.sha256()
    payload = bytearray()
    with bounded_binary_input(raw_path, root=root) as (_, metadata, handle):
        while True:
            chunk = handle.read(64 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            payload.extend(chunk)
    try:
        text = bytes(payload).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("invalid-utf8", "Newick input must be valid UTF-8") from exc
    if not text.strip():
        raise ContractError("empty-tree", "Newick input is empty")
    return text, {"sha256": digest.hexdigest(), "size_bytes": metadata.st_size}


class NewickParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.position = 0
        self.node_count = 0

    def error(self, code: str, message: str) -> ContractError:
        return ContractError(code, f"{message} at character {self.position + 1}")

    def skip_space(self) -> None:
        while self.position < len(self.text) and self.text[self.position].isspace():
            self.position += 1

    def peek(self) -> str | None:
        self.skip_space()
        if self.position >= len(self.text):
            return None
        character = self.text[self.position]
        if character == "[":
            raise self.error("unsupported-comment", "square-bracket comments and NHX are unsupported")
        return character

    def consume(self, expected: str) -> None:
        self.skip_space()
        if self.position >= len(self.text) or self.text[self.position] != expected:
            raise self.error("malformed-newick", f"expected {expected!r}")
        self.position += 1

    def new_node(self, depth: int) -> Node:
        if depth > MAX_DEPTH:
            raise ContractError("tree-too-deep", f"tree exceeds {MAX_DEPTH} nesting levels", status="needs-tool")
        self.node_count += 1
        if self.node_count > MAX_NODES:
            raise ContractError("too-many-nodes", f"tree exceeds {MAX_NODES} nodes", status="needs-tool")
        return Node()

    def parse_label(self) -> str | None:
        self.skip_space()
        if self.position >= len(self.text):
            return None
        character = self.text[self.position]
        if character == "'":
            self.position += 1
            pieces: list[str] = []
            while self.position < len(self.text):
                character = self.text[self.position]
                if character == "'":
                    if self.position + 1 < len(self.text) and self.text[self.position + 1] == "'":
                        pieces.append("'")
                        self.position += 2
                        continue
                    self.position += 1
                    label = "".join(pieces)
                    if not label:
                        raise self.error("empty-label", "quoted labels must not be empty")
                    if len(label.encode("utf-8")) > MAX_LABEL_BYTES:
                        raise ContractError("label-too-long", f"label exceeds {MAX_LABEL_BYTES} UTF-8 bytes", status="needs-tool")
                    return label
                if ord(character) < 32 or ord(character) == 127:
                    raise self.error("invalid-label", "labels must not contain control characters")
                pieces.append(character)
                self.position += 1
            raise self.error("unterminated-quoted-label", "quoted label is not terminated")
        if character in "(),:;":
            return None
        if character == "[":
            raise self.error("unsupported-comment", "square-bracket comments and NHX are unsupported")
        start = self.position
        while self.position < len(self.text):
            character = self.text[self.position]
            if character.isspace() or character in "()[],:;'":
                break
            if ord(character) < 32 or ord(character) == 127:
                raise self.error("invalid-label", "labels must not contain control characters")
            self.position += 1
        label = self.text[start:self.position]
        if label and len(label.encode("utf-8")) > MAX_LABEL_BYTES:
            raise ContractError("label-too-long", f"label exceeds {MAX_LABEL_BYTES} UTF-8 bytes", status="needs-tool")
        return label or None

    def parse_length(self) -> float | None:
        self.skip_space()
        if self.position >= len(self.text) or self.text[self.position] != ":":
            return None
        self.position += 1
        self.skip_space()
        nonfinite = re.match(r"[+-]?(?:nan|inf(?:inity)?)", self.text[self.position :], re.IGNORECASE)
        if nonfinite is not None:
            end = self.position + nonfinite.end()
            if end == len(self.text) or self.text[end].isspace() or self.text[end] in ",);":
                raise self.error("non-finite-branch-length", "branch length must be finite")
        match = NUMBER.match(self.text, self.position)
        if match is None:
            raise self.error("invalid-branch-length", "branch length must be an ordinary decimal number")
        token = match.group(0)
        self.position = match.end()
        value = float(token)
        if not math.isfinite(value):
            raise self.error("non-finite-branch-length", "branch length must be finite")
        if value < 0.0:
            raise self.error("negative-branch-length", "branch length must be nonnegative")
        return value

    def parse_subtree(self, depth: int) -> Node:
        node = self.new_node(depth)
        if self.peek() == "(":
            self.consume("(")
            if self.peek() in {None, ")", ","}:
                raise self.error("empty-child", "internal node requires a child")
            node.children.append(self.parse_subtree(depth + 1))
            while self.peek() == ",":
                self.consume(",")
                if self.peek() in {None, ")", ","}:
                    raise self.error("empty-child", "internal node requires a child after comma")
                node.children.append(self.parse_subtree(depth + 1))
            self.consume(")")
            node.label = self.parse_label()
        else:
            node.label = self.parse_label()
            if node.label is None:
                raise self.error("missing-tip-label", "tip label is required")
        node.branch_length = self.parse_length()
        return node

    def parse(self) -> Node:
        root = self.parse_subtree(0)
        self.consume(";")
        self.skip_space()
        if self.position != len(self.text):
            raise self.error("trailing-content", "content after the one terminal semicolon is unsupported")
        return root


def finite_numeric_label(label: str) -> float | None:
    if not NUMBER.fullmatch(label):
        return None
    value = float(label)
    return value if math.isfinite(value) else None


def summarize_tree(root: Node) -> tuple[dict[str, Any], list[str]]:
    stack = [(root, 0)]
    tips: list[str] = []
    branch_lengths: list[float] = []
    missing_lengths = 0
    internal_nodes = 0
    unary = 0
    bifurcations = 0
    polytomies = 0
    numeric_supports: list[float] = []
    nonnumeric_internal_labels = 0
    maximum_depth = 0
    while stack:
        node, depth = stack.pop()
        maximum_depth = max(maximum_depth, depth)
        if node.branch_length is None:
            missing_lengths += 1
        else:
            branch_lengths.append(node.branch_length)
        if node.children:
            internal_nodes += 1
            degree = len(node.children)
            unary += degree == 1
            bifurcations += degree == 2
            polytomies += degree > 2
            if node.label is not None:
                support = finite_numeric_label(node.label)
                if support is None:
                    nonnumeric_internal_labels += 1
                else:
                    numeric_supports.append(support)
            for child in reversed(node.children):
                stack.append((child, depth + 1))
        else:
            if node.label is None:
                raise ContractError("missing-tip-label", "every tip must have a non-empty label")
            tips.append(node.label)
    duplicates = sorted(label for label in set(tips) if tips.count(label) > 1)
    if duplicates:
        raise ContractError("duplicate-tip-label", f"tip labels must be unique; duplicate: {duplicates[0]!r}")
    sorted_tips = sorted(tips)
    tip_payload = json.dumps(sorted_tips, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    support_summary: dict[str, Any] = {
        "numeric_internal_label_count": len(numeric_supports),
        "nonnumeric_internal_label_count": nonnumeric_internal_labels,
        "numeric_scale_interpretation": "not-inferred",
        "numeric_values_outside_0_to_100": sum(value < 0.0 or value > 100.0 for value in numeric_supports),
    }
    if numeric_supports:
        support_summary.update({
            "minimum_numeric_internal_label": min(numeric_supports),
            "maximum_numeric_internal_label": max(numeric_supports),
        })
    length_summary: dict[str, Any] = {
        "present_count": len(branch_lengths),
        "missing_count": missing_lengths,
        "zero_count": sum(value == 0.0 for value in branch_lengths),
    }
    if branch_lengths:
        try:
            branch_sum: float | None = math.fsum(branch_lengths)
        except OverflowError:
            branch_sum = None
        length_summary.update({
            "minimum": min(branch_lengths),
            "maximum": max(branch_lengths),
            "sum": branch_sum,
        })
        if branch_sum is None:
            length_summary["sum_status"] = "not-estimable-numeric-overflow"
    summary = {
        "tip_count": len(tips),
        "internal_node_count": internal_nodes,
        "node_count": len(tips) + internal_nodes,
        "maximum_root_to_node_depth_edges": maximum_depth,
        "root_child_count": len(root.children),
        "unary_internal_node_count": unary,
        "bifurcating_internal_node_count": bifurcations,
        "polytomy_count": polytomies,
        "tip_label_set_sha256": hashlib.sha256(tip_payload).hexdigest(),
        "branch_lengths": length_summary,
        "internal_labels": support_summary,
    }
    return summary, sorted_tips


def parse_tree_file(raw_path: str | Path, *, root: Path | None = None) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    text, input_details = read_newick(raw_path, root=root)
    tree = NewickParser(text).parse()
    summary, tips = summarize_tree(tree)
    return summary, tips, input_details


def build_report(tree_path: str | Path, compare_path: str | Path | None = None, *, root: Path | None = None) -> dict[str, Any]:
    primary_summary, primary_tips, primary_input = parse_tree_file(tree_path, root=root)
    comparison: dict[str, Any] | None = None
    if compare_path is not None:
        other_summary, other_tips, other_input = parse_tree_file(compare_path, root=root)
        if primary_tips != other_tips:
            missing = sorted(set(primary_tips) - set(other_tips))
            extra = sorted(set(other_tips) - set(primary_tips))
            comparison = {
                "status": "tip-set-mismatch",
                "comparison_input": other_input,
                "comparison_tip_count": other_summary["tip_count"],
                "tip_label_set_sha256": other_summary["tip_label_set_sha256"],
                "missing_tip_labels": missing,
                "extra_tip_labels": extra,
            }
        else:
            comparison = {
                "status": "exact-tip-set-match",
                "comparison_input": other_input,
                "comparison_tip_count": other_summary["tip_count"],
                "tip_label_set_sha256": other_summary["tip_label_set_sha256"],
                "missing_tip_labels": [],
                "extra_tip_labels": [],
            }
    return {
        "schema_version": "0.1.0",
        "tool": "qc_newick_tree.py",
        "tool_version": VERSION,
        "status": "completed",
        "analysis": "phylogenetic-tree-io-and-qc",
        "tree": {"input": primary_input, "format": "newick-subset", "summary": primary_summary},
        "tip_set_comparison": comparison,
        "limits": {
            "max_input_bytes_per_file": MAX_INPUT_BYTES,
            "max_nodes_per_tree": MAX_NODES,
            "max_nesting_depth": MAX_DEPTH,
            "max_label_bytes": MAX_LABEL_BYTES,
            "network": False,
            "subprocess": False,
            "compression": False,
        },
        "limitations": [
            "Only the documented single-tree Newick subset is supported; Nexus, NHX, comments, and multiple trees are excluded.",
            "Numeric internal labels are reported descriptively without assuming that they encode support or inferring their meaning.",
            "The report does not infer, root, prune, resolve, compare topology, visualize, reconcile taxonomy, or make biological or evolutionary claims.",
        ],
    }


def open_output_parent(raw_path: str | Path, *, root: Path | None = None) -> tuple[Path, int, str]:
    lexical_root = checked_root(root)
    target = lexical_absolute(raw_path)
    parts = require_below_root(target, lexical_root)
    parent_fd, name = open_parent_directory(lexical_root, parts, target, output=True)
    try:
        try:
            target_state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            code = "output-symlink-refused" if stat.S_ISLNK(target_state.st_mode) else "output-exists"
            raise ContractError(code, "output exists; overwrite is forbidden", path=str(target))
        return target, parent_fd, name
    except BaseException:
        os.close(parent_fd)
        raise


def safe_output_target(raw_path: str | Path, *, root: Path | None = None) -> Path:
    target, descriptor, _ = open_output_parent(raw_path, root=root)
    os.close(descriptor)
    return target


def unlink_owned_at(name: str, directory_fd: int, identity: tuple[int, int]) -> bool:
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    if (current.st_dev, current.st_ino) != identity:
        return False
    os.unlink(name, dir_fd=directory_fd)
    return True


def write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("output write made no progress")
        offset += written


def write_new_json(
    raw_path: str | Path,
    report: dict[str, Any],
    *,
    root: Path | None = None,
    before_publish: Callable[[], None] | None = None,
) -> Path:
    target, directory_fd, target_name = open_output_parent(raw_path, root=root)
    payload = (json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    temporary_name = f".{target_name}.tmp-{secrets.token_hex(12)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    identity: tuple[int, int] | None = None
    temporary_created = False
    temporary_present = False
    published = False
    original_error: BaseException | None = None
    cleanup_failures: list[str] = []
    try:
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        temporary_created = True
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        temporary_present = True
        write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        if before_publish is not None:
            before_publish()
        try:
            os.link(temporary_name, target_name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        except FileExistsError as exc:
            raise ContractError("output-exists", "output appeared; overwrite is forbidden", path=str(target)) from exc
        published = True
        published_state = os.stat(
            target_name, dir_fd=directory_fd, follow_symlinks=False
        )
        if (published_state.st_dev, published_state.st_ino) != identity:
            raise OSError("published output identity differs from staged data")
        if not unlink_owned_at(temporary_name, directory_fd, identity):
            raise OSError("staged output identity changed before cleanup")
        temporary_present = False
        os.fsync(directory_fd)
        final_state = os.stat(
            target_name, dir_fd=directory_fd, follow_symlinks=False
        )
        if (final_state.st_dev, final_state.st_ino) != identity:
            raise OSError("published output identity changed before completion")
    except BaseException as exc:
        original_error = exc
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                cleanup_failures.append(f"descriptor:{exc.__class__.__name__}")
        if original_error is not None:
            if temporary_created and identity is None:
                cleanup_failures.append("staged:identity-unavailable")
            if published and identity is not None:
                try:
                    if not unlink_owned_at(target_name, directory_fd, identity):
                        cleanup_failures.append("published:identity-changed")
                except OSError as exc:
                    cleanup_failures.append(f"published:{exc.__class__.__name__}")
            if temporary_present and identity is not None:
                try:
                    if not unlink_owned_at(temporary_name, directory_fd, identity):
                        cleanup_failures.append("staged:identity-changed")
                except OSError as exc:
                    cleanup_failures.append(f"staged:{exc.__class__.__name__}")
            if temporary_created:
                try:
                    os.fsync(directory_fd)
                except OSError as exc:
                    cleanup_failures.append(f"directory:{exc.__class__.__name__}")
        os.close(directory_fd)
    if cleanup_failures:
        raise ContractError(
            "publication-rollback-failed",
            "output publication failed and owned files could not all be rolled back: "
            + ", ".join(cleanup_failures),
            status="io-error",
            path=str(target),
        ) from original_error
    if original_error is not None:
        if isinstance(original_error, ContractError):
            raise original_error
        raise ContractError(
            "publication-failed",
            str(original_error),
            status="io-error",
            path=str(target),
        ) from original_error
    return target


def expect_error(code: str, action: Callable[[], Any]) -> None:
    try:
        action()
    except ContractError as exc:
        if exc.code != code:
            raise RuntimeError(f"expected {code}, got {exc.code}") from exc
    else:
        raise RuntimeError(f"expected {code}")


def require_test(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def self_test() -> None:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="bio02-tree-qc-") as temporary:
        root = Path(temporary)
        tree = root / "tree.nwk"
        tree.write_text("(('A one':0.1,B:0.2)95:0.3,C:0,D:1e-2)'root label':0;\n", encoding="utf-8")
        reordered = root / "reordered.nwk"
        reordered.write_text("(D:0.01,(B:0.2,'A one':0.1)80:0.3,C:0);\n", encoding="utf-8")
        report = build_report(tree, reordered, root=root)
        summary = report["tree"]["summary"]
        require_test(summary["tip_count"] == 4, "tip count differs")
        require_test(summary["internal_node_count"] == 2, "internal-node count differs")
        require_test(summary["polytomy_count"] == 1, "polytomy count differs")
        require_test(summary["branch_lengths"] == {"present_count": 6, "missing_count": 0, "zero_count": 2, "minimum": 0.0, "maximum": 0.3, "sum": 0.61}, "branch summary differs")
        require_test(summary["internal_labels"]["numeric_internal_label_count"] == 1, "numeric support count differs")
        require_test(summary["internal_labels"]["nonnumeric_internal_label_count"] == 1, "internal label count differs")
        require_test(report["tip_set_comparison"]["status"] == "exact-tip-set-match", "tip-set match differs")
        require_test(report == build_report(tree, reordered, root=root), "report is not deterministic")
        checks += 8

        first_output = root / "report.json"
        second_output = root / "report-copy.json"
        write_new_json(first_output, report, root=root)
        write_new_json(second_output, report, root=root)
        require_test(first_output.read_bytes() == second_output.read_bytes(), "repeat report bytes differ")
        expect_error("output-exists", lambda: write_new_json(first_output, report, root=root))
        expect_error("parent-traversal", lambda: write_new_json(Path("..") / "escape.json", report, root=root))
        checks += 3

        cases = {
            "malformed-newick": "((A:1,B:1);",
            "duplicate-tip-label": "(A:1,A:2);",
            "non-finite-branch-length": "(A:NaN,B:1);",
            "negative-branch-length": "(A:-0.1,B:1);",
            "unsupported-comment": "(A[comment]:1,B:1);",
            "trailing-content": "(A:1,B:1);(C:1,D:1);",
        }
        for expected, payload in cases.items():
            path = root / f"{expected}.nwk"
            path.write_text(payload, encoding="utf-8")
            expect_error(expected, lambda path=path: build_report(path, root=root))
            checks += 1

        extreme = root / "extreme-finite-branches.nwk"
        extreme.write_text("(A:1e308,B:1e308);", encoding="utf-8")
        extreme_report = build_report(extreme, root=root)
        extreme_lengths = extreme_report["tree"]["summary"]["branch_lengths"]
        require_test(
            extreme_lengths["sum"] is None
            and extreme_lengths["sum_status"] == "not-estimable-numeric-overflow",
            "finite branch summary overflow did not remain structured",
        )
        checks += 1

        mismatch = root / "mismatch.nwk"
        mismatch.write_text("(A:1,B:1,X:1,D:1);", encoding="utf-8")
        mismatch_output = root / "mismatch-report.json"

        safe_output_target(mismatch_output, root=root)
        mismatch_report = build_report(tree, mismatch, root=root)
        write_new_json(mismatch_output, mismatch_report, root=root)
        mismatch_comparison = mismatch_report["tip_set_comparison"]
        require_test(mismatch_comparison["status"] == "tip-set-mismatch", "tip mismatch status differs")
        require_test(mismatch_comparison["missing_tip_labels"] == ["A one", "C"] and mismatch_comparison["extra_tip_labels"] == ["A", "X"], "tip mismatch details differ")
        require_test(mismatch_output.is_file(), "tip mismatch diagnostic report was not created")
        checks += 2

        input_link = root / "input-link.nwk"
        input_link.symlink_to(tree)
        expect_error("symlink-refused", lambda: build_report(input_link, root=root))
        input_real_parent = root / "input-real-parent"
        input_real_parent.mkdir()
        nested_tree = input_real_parent / "nested.nwk"
        nested_tree.write_text("(A:1,B:1);", encoding="utf-8")
        input_linked_parent = root / "input-linked-parent"
        input_linked_parent.symlink_to(input_real_parent, target_is_directory=True)
        expect_error("input-parent-symlink", lambda: build_report(input_linked_parent / "nested.nwk", root=root))
        real_parent = root / "real-parent"
        real_parent.mkdir()
        linked_parent = root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        expect_error("output-parent-symlink", lambda: write_new_json(linked_parent / "report.json", report, root=root))
        output_link = root / "output-link.json"
        output_link.symlink_to(first_output)
        expect_error("output-symlink-refused", lambda: write_new_json(output_link, report, root=root))
        checks += 4

        swap_parent = root / "swap-parent"
        swap_parent.mkdir()
        held_parent = root / "held-parent"
        with tempfile.TemporaryDirectory(prefix="tree-qc-outside-") as outside_name:
            outside = Path(outside_name)

            def swap_output_parent() -> None:
                swap_parent.rename(held_parent)
                swap_parent.symlink_to(outside, target_is_directory=True)

            write_new_json(swap_parent / "report.json", report, root=root, before_publish=swap_output_parent)
            require_test(not (outside / "report.json").exists(), "output-parent swap escaped root")
            require_test((held_parent / "report.json").is_file(), "held output-parent publication differs")
            swap_parent.unlink()
            held_parent.rename(swap_parent)
        checks += 2

        fsync_output = root / "post-link-fsync.json"
        real_fsync = os.fsync
        failed_directory_fsync = False

        def fail_first_directory_fsync(descriptor: int) -> None:
            nonlocal failed_directory_fsync
            if stat.S_ISDIR(os.fstat(descriptor).st_mode) and not failed_directory_fsync:
                failed_directory_fsync = True
                raise OSError("injected post-link directory fsync failure")
            real_fsync(descriptor)

        os.fsync = fail_first_directory_fsync
        try:
            expect_error(
                "publication-failed",
                lambda: write_new_json(fsync_output, report, root=root),
            )
        finally:
            os.fsync = real_fsync
        require_test(failed_directory_fsync and not fsync_output.exists(), "directory fsync failure was not rolled back")
        require_test(not list(root.glob(f".{fsync_output.name}.tmp-*")), "directory fsync rollback left a staged file")
        checks += 2

        cleanup_output = root / "cleanup-failure.json"
        real_unlink = os.unlink

        def fail_staged_unlink(path: str | bytes, *args: Any, **kwargs: Any) -> None:
            if os.fspath(path).startswith(f".{cleanup_output.name}.tmp-"):
                raise PermissionError("injected staged cleanup failure")
            real_unlink(path, *args, **kwargs)

        os.unlink = fail_staged_unlink
        try:
            expect_error(
                "publication-rollback-failed",
                lambda: write_new_json(cleanup_output, report, root=root),
            )
        finally:
            os.unlink = real_unlink
        require_test(not cleanup_output.exists(), "cleanup failure left the final output")
        staged_leftovers = list(root.glob(f".{cleanup_output.name}.tmp-*"))
        require_test(len(staged_leftovers) == 1, "cleanup failure was not reported with its owned staged file")
        staged_leftovers[0].unlink()
        checks += 2

    print(json.dumps({"checks": checks, "status": "pass", "version": VERSION}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Check one bounded local single-tree Newick file.")
    command.add_argument("--tree")
    command.add_argument("--compare-tree")
    command.add_argument("--output")
    command.add_argument("--self-test", action="store_true")
    command.add_argument("--version", action="version", version=VERSION)
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    missing = [name for name, value in (("tree", args.tree), ("output", args.output)) if not value]
    if missing:
        print(json.dumps({"error": {"code": "missing-argument", "message": f"missing: {', '.join(missing)}"}, "status": "needs-decision"}, sort_keys=True), file=sys.stderr)
        return 2
    try:
        safe_output_target(args.output)
        report = build_report(args.tree, args.compare_tree)
        output = write_new_json(args.output, report)
    except ContractError as exc:
        print(json.dumps({"error": exc.as_dict(), "status": exc.status}, sort_keys=True), file=sys.stderr)
        return 3 if exc.status == "io-error" else 2
    print(json.dumps({"output": str(output), "status": "completed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
