from __future__ import annotations

import argparse
import csv
import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import apply_upstream_title_history_safe_resolutions as whole_apply
import audit_upstream_title_history_delta as delta
import audit_upstream_title_history_entry_delta as entry_audit
import audit_upstream_title_history_merge as broad


OUTPUT_DIR = ".codex/works/analysis/generated/upstream_merge_audit"
SAFE_REPORT = "title_history_entry_delta_safe.csv"
DATE_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?$")
CONFLICT_RE = re.compile(r"^(<<<<<<<|=======|>>>>>>>)", re.MULTILINE)


@dataclass(frozen=True)
class PlannedEntryEdit:
    start: int
    end: int
    replacement: tuple[str, ...]
    label: str


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]
    parser = argparse.ArgumentParser(
        description="Apply verified direct-entry title-history resolutions."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--relation-csv",
        type=Path,
        default=repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv",
    )
    parser.add_argument("--base-revision")
    parser.add_argument("--upstream-revision")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {str(key).strip(): (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, skipinitialspace=True)
        ]


def working_texts(repo_root: Path) -> dict[str, str]:
    return {
        path: (repo_root / path).read_text(encoding="utf-8-sig")
        for path in broad.TITLE_HISTORY_PATHS
    }


def date_key(value: str) -> tuple[int, int, int] | None:
    match = DATE_RE.fullmatch(value)
    if not match:
        return None
    return tuple(int(part or 1) for part in match.groups())


def insertion_position(
    current_entries: list[entry_audit.CanonicalEntry],
    upstream_entry: entry_audit.CanonicalEntry,
    closing_index: int,
) -> int:
    target_date = date_key(upstream_entry.entry.key)
    if target_date is None:
        return closing_index
    same_date = [
        item for item in current_entries if item.entry.key == upstream_entry.entry.key
    ]
    if same_date:
        return max(item.entry.relative_end for item in same_date)
    dated_entries = [
        (date_key(item.entry.key), item)
        for item in current_entries
        if date_key(item.entry.key) is not None
    ]
    for current_date, item in dated_entries:
        if current_date and current_date > target_date:
            return item.entry.relative_start
    return closing_index


def apply_local_edits(lines: list[str], edits: list[PlannedEntryEdit]) -> list[str]:
    result = list(lines)
    previous_start = len(lines) + 1
    for edit in sorted(edits, key=lambda item: (item.start, item.end), reverse=True):
        if edit.end > previous_start:
            raise RuntimeError(f"overlapping entry edits: {edit.label}")
        result[edit.start : edit.end] = edit.replacement
        previous_start = edit.start
    return result


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_DIR)
    safe_rows = read_csv(output_dir / SAFE_REPORT)

    current_landed_ids = broad.collect_working_landed_ids(repo_root)
    _tokens, by_upstream, _by_current, mapping_issues = delta.load_mapping(
        args.relation_csv, current_landed_ids
    )
    if mapping_issues:
        raise RuntimeError(f"mapping parse issues remain: {len(mapping_issues)}")
    unique_mapping = {
        upstream_id: next(iter({token.current_title_id for token in group}))
        for upstream_id, group in by_upstream.items()
        if len({token.current_title_id for token in group}) == 1
    }

    stage_revisions = {
        1: args.base_revision,
        3: args.upstream_revision,
    }
    stage_texts = {
        stage: {
            path: (
                broad.git_revision_text(
                    repo_root, stage_revisions[stage], path
                )
                if stage_revisions[stage]
                else broad.git_stage_text(repo_root, stage, path)
            )
            for path in broad.TITLE_HISTORY_PATHS
        }
        for stage in (1, 3)
    }
    raw_base = broad.build_snapshot(
        "raw_base", stage_texts[1], delta.identity_mapper, {}
    )
    raw_upstream = broad.build_snapshot(
        "raw_upstream", stage_texts[3], delta.identity_mapper, {}
    )
    current_text_by_path = working_texts(repo_root)
    current = broad.build_snapshot(
        "working_current", current_text_by_path, delta.identity_mapper, {}
    )
    base_layers = delta.layered_blocks(raw_base)
    upstream_layers = delta.layered_blocks(raw_upstream)

    grouped_rows: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in safe_rows:
        grouped_rows[(row["current_target"], row["history_layer"])].append(row)

    block_replacements: dict[
        str, list[tuple[int, int, tuple[str, ...], str]]
    ] = defaultdict(list)
    report_rows: list[dict[str, str]] = []

    for (target, layer), rows in sorted(grouped_rows.items()):
        current_candidates = delta.current_layer_blocks(current, target, layer)
        if len(current_candidates) != 1:
            raise RuntimeError(
                f"expected one current block for {target}/{layer}, found {len(current_candidates)}"
            )
        current_block = current_candidates[0]
        current_lines = list(current_block.lines)
        current_entries_raw = entry_audit.parse_entries(current_block)
        planned_by_interval: dict[tuple[int, int], PlannedEntryEdit] = {}
        inserts_by_position: dict[int, list[tuple[int, tuple[str, ...], str]]] = defaultdict(list)

        for row in rows:
            raw_id = row["raw_upstream_title_id"]
            base_candidates = base_layers.get((raw_id, layer), [])
            upstream_candidates = upstream_layers.get((raw_id, layer), [])
            if len(base_candidates) != 1 or len(upstream_candidates) != 1:
                raise RuntimeError(f"non-unique donor block for {raw_id}/{layer}")
            base_block = base_candidates[0]
            upstream_block = upstream_candidates[0]
            target_mapping = dict(unique_mapping)
            target_mapping[raw_id] = target
            base_entries = [
                entry_audit.canonicalize(item, target_mapping)
                for item in entry_audit.parse_entries(base_block)
            ]
            upstream_entries = [
                entry_audit.canonicalize(item, target_mapping)
                for item in entry_audit.parse_entries(upstream_block)
            ]
            operations = entry_audit.entry_operations(base_entries, upstream_entries)
            operation_index = int(row["operation_index"]) - 1
            if operation_index < 0 or operation_index >= len(operations):
                raise RuntimeError(f"stale operation index for {raw_id}/{target}")
            operation, base_entry, upstream_entry = operations[operation_index]
            if operation != row["operation"]:
                raise RuntimeError(f"stale operation kind for {raw_id}/{target}")

            current_entries = [
                entry_audit.canonicalize(item, target_mapping)
                for item in current_entries_raw
            ]
            base_matches = [
                item
                for item in current_entries
                if base_entry and item.semantic == base_entry.semantic
            ]
            upstream_matches = [
                item
                for item in current_entries
                if upstream_entry and item.semantic == upstream_entry.semantic
            ]
            label = (
                f"{operation} {raw_id}/{target}/{row['entry_key']}/"
                f"op{row['operation_index']}"
            )

            if operation == "replace":
                if len(base_matches) == 0 and len(upstream_matches) == 1:
                    report_rows.append({**row, "apply_status": "already_applied"})
                    continue
                if len(base_matches) != 1 or upstream_matches:
                    raise RuntimeError(
                        f"replace precondition changed for {label}: "
                        f"base={len(base_matches)}, upstream={len(upstream_matches)}"
                    )
                match = base_matches[0]
                edit = PlannedEntryEdit(
                    start=match.entry.relative_start,
                    end=match.entry.relative_end,
                    replacement=upstream_entry.remapped_lines,
                    label=label,
                )
                interval = (edit.start, edit.end)
                prior = planned_by_interval.get(interval)
                if prior and prior.replacement != edit.replacement:
                    raise RuntimeError(f"conflicting replacements for {target}: {label}")
                planned_by_interval[interval] = edit
            elif operation == "delete":
                if not base_matches:
                    report_rows.append({**row, "apply_status": "already_applied"})
                    continue
                if len(base_matches) != 1:
                    raise RuntimeError(
                        f"delete precondition changed for {label}: base={len(base_matches)}"
                    )
                match = base_matches[0]
                edit = PlannedEntryEdit(
                    start=match.entry.relative_start,
                    end=match.entry.relative_end,
                    replacement=(),
                    label=label,
                )
                interval = (edit.start, edit.end)
                prior = planned_by_interval.get(interval)
                if prior and prior.replacement:
                    raise RuntimeError(f"delete conflicts with replacement: {label}")
                planned_by_interval[interval] = edit
            elif operation == "insert":
                if upstream_matches:
                    report_rows.append({**row, "apply_status": "already_applied"})
                    continue
                position = insertion_position(
                    current_entries, upstream_entry, len(current_lines) - 1
                )
                inserts_by_position[position].append(
                    (
                        int(row["upstream_line"] or 0),
                        upstream_entry.remapped_lines,
                        label,
                    )
                )
            else:
                raise RuntimeError(f"unsupported operation: {operation}")
            report_rows.append({**row, "apply_status": "planned"})

        edits = list(planned_by_interval.values())
        for position, items in inserts_by_position.items():
            ordered = sorted(items, key=lambda item: (item[0], item[2]))
            replacement = tuple(line for _line, lines, _label in ordered for line in lines)
            edits.append(
                PlannedEntryEdit(
                    start=position,
                    end=position,
                    replacement=replacement,
                    label="; ".join(item[2] for item in ordered),
                )
            )
        merged_block = tuple(apply_local_edits(current_lines, edits))
        block_replacements[current_block.path].append(
            (
                current_block.start_line - 1,
                current_block.end_line,
                merged_block,
                f"entry merge {target}/{layer}",
            )
        )

    expected_bytes: dict[str, bytes] = {}
    for path in broad.TITLE_HISTORY_PATHS:
        current_bytes = (repo_root / path).read_bytes()
        text, fmt = whole_apply.decode(current_bytes)
        lines = whole_apply.apply_intervals(
            text.splitlines(), block_replacements.get(path, [])
        )
        expected_text = whole_apply.join_lines(lines, fmt)
        if CONFLICT_RE.search(expected_text):
            raise RuntimeError(f"conflict marker remains in expected {path}")
        if sum(broad.line_brace_delta(line) for line in expected_text.splitlines()) != 0:
            raise RuntimeError(f"brace delta is not zero in expected {path}")
        expected_bytes[path] = whole_apply.encode(expected_text, fmt)

    expected_texts = {
        path: data.decode("utf-8-sig", errors="strict")
        for path, data in expected_bytes.items()
    }
    final_snapshot = broad.build_snapshot(
        "entry_expected", expected_texts, delta.identity_mapper, {}
    )
    if any(final_snapshot.file_brace_deltas.values()):
        raise RuntimeError("non-zero brace delta after entry merge")

    file_rows: list[dict[str, str]] = []
    for path, expected in expected_bytes.items():
        target_path = repo_root / path
        current_bytes = target_path.read_bytes()
        status = "already_applied" if current_bytes == expected else "needs_apply"
        if args.apply and status == "needs_apply":
            target_path.write_bytes(expected)
            status = "applied"
        file_rows.append(
            {
                "path": path,
                "status": status,
                "expected_sha256": sha256(expected),
                "changed_target_blocks": str(len(block_replacements.get(path, []))),
            }
        )

    broad.write_csv(output_dir / "title_history_entry_apply_rows.csv", report_rows)
    broad.write_csv(output_dir / "title_history_entry_apply_files.csv", file_rows)
    row_counts = Counter(row["apply_status"] for row in report_rows)
    file_counts = Counter(row["status"] for row in file_rows)
    summary = [
        "# Title History Entry Apply Summary",
        "",
        f"- safe report rows: {len(safe_rows)}",
        f"- planned rows: {row_counts.get('planned', 0)}",
        f"- already-applied rows: {row_counts.get('already_applied', 0)}",
        f"- apply requested: {'yes' if args.apply else 'no'}",
        "",
        "## Row Status",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(row_counts.items())],
        "",
        "## File Status",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(file_counts.items())],
    ]
    (output_dir / "title_history_entry_apply_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )

    print(f"safe report rows: {len(safe_rows)}")
    print(f"planned rows: {row_counts.get('planned', 0)}")
    print(f"already-applied rows: {row_counts.get('already_applied', 0)}")
    print(f"file statuses: {dict(file_counts)}")
    print(f"summary: {output_dir / 'title_history_entry_apply_summary.md'}")


if __name__ == "__main__":
    main()
