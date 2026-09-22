from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import audit_upstream_title_history_delta as delta
import audit_upstream_title_history_merge as broad
import build_landed_title_asil_mod_metadata_transfer_dry_run as landed


OUTPUT_DIR = "development/analysis/generated/upstream_merge_audit"
REVIEW_REPORT = "title_history_upstream_delta_review.csv"
ENTRY_RE = re.compile(r"^\s*([A-Za-z0-9_.@?:'\"\-]+)\s*=")


@dataclass(frozen=True)
class Entry:
    key: str
    relative_start: int
    relative_end: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalEntry:
    entry: Entry
    semantic: str
    remapped_lines: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]
    parser = argparse.ArgumentParser(
        description="Audit changed title-history blocks at direct entry level."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--relation-csv",
        type=Path,
        default=repo_root
        / "development/pipeline_inputs/title_relations/curated_title_relations.csv",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--base-revision", default="")
    parser.add_argument("--ours-revision", default="")
    parser.add_argument("--upstream-revision", default="")
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


def parse_entries(block: broad.HistoryBlock) -> list[Entry]:
    lines = list(block.lines)
    entries: list[Entry] = []
    index = 1
    depth = 1
    closing_index = len(lines) - 1
    while index < closing_index:
        visible = landed.strip_comment(lines[index])
        match = ENTRY_RE.match(visible) if depth == 1 else None
        if not match:
            depth += broad.line_brace_delta(lines[index])
            index += 1
            continue
        start = index
        local_depth = depth + broad.line_brace_delta(lines[index])
        while local_depth > 1 and index + 1 < closing_index:
            index += 1
            local_depth += broad.line_brace_delta(lines[index])
        if local_depth != 1:
            raise RuntimeError(
                f"unterminated direct entry {match.group(1)} in "
                f"{block.path}:{block.start_line + start}"
            )
        entries.append(
            Entry(
                key=match.group(1),
                relative_start=start,
                relative_end=index + 1,
                lines=tuple(lines[start : index + 1]),
            )
        )
        depth = local_depth
        index += 1
    return entries


def remap_active_line(line: str, mapping: dict[str, str]) -> str:
    active = landed.strip_comment(line)
    suffix = line[len(active) :]
    active = broad.TITLE_TOKEN_RE.sub(
        lambda match: mapping.get(match.group(1), match.group(1)), active
    )
    return active + suffix


def canonicalize(entry: Entry, mapping: dict[str, str]) -> CanonicalEntry:
    lines = tuple(remap_active_line(line, mapping) for line in entry.lines)
    semantic = broad.normalize_semantic("\n".join(lines))
    return CanonicalEntry(entry=entry, semantic=semantic, remapped_lines=lines)


def active_tokens(lines: tuple[str, ...]) -> set[str]:
    return {
        token
        for line in lines
        for token in broad.TITLE_TOKEN_RE.findall(landed.strip_comment(line))
    }


def group_entries(entries: list[CanonicalEntry]) -> dict[str, list[CanonicalEntry]]:
    grouped: dict[str, list[CanonicalEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.entry.key].append(entry)
    return dict(grouped)


def cancel_equal(
    base: list[CanonicalEntry], upstream: list[CanonicalEntry]
) -> tuple[list[CanonicalEntry], list[CanonicalEntry]]:
    remaining_upstream = list(upstream)
    remaining_base: list[CanonicalEntry] = []
    for base_entry in base:
        match_index = next(
            (
                index
                for index, upstream_entry in enumerate(remaining_upstream)
                if upstream_entry.semantic == base_entry.semantic
            ),
            None,
        )
        if match_index is None:
            remaining_base.append(base_entry)
        else:
            remaining_upstream.pop(match_index)
    return remaining_base, remaining_upstream


def entry_operations(
    base_entries: list[CanonicalEntry],
    upstream_entries: list[CanonicalEntry],
) -> list[tuple[str, CanonicalEntry | None, CanonicalEntry | None]]:
    base_groups = group_entries(base_entries)
    upstream_groups = group_entries(upstream_entries)
    operations: list[tuple[str, CanonicalEntry | None, CanonicalEntry | None]] = []
    for key in sorted(set(base_groups) | set(upstream_groups)):
        base_left, upstream_left = cancel_equal(
            base_groups.get(key, []), upstream_groups.get(key, [])
        )
        pair_count = min(len(base_left), len(upstream_left))
        for index in range(pair_count):
            operations.append(("replace", base_left[index], upstream_left[index]))
        for entry in base_left[pair_count:]:
            operations.append(("delete", entry, None))
        for entry in upstream_left[pair_count:]:
            operations.append(("insert", None, entry))
    return operations


def semantic_counts(entries: list[CanonicalEntry]) -> Counter[str]:
    return Counter(entry.semantic for entry in entries)


def preview(entry: CanonicalEntry | None, limit: int = 240) -> str:
    if entry is None:
        return ""
    text = " ".join(line.strip() for line in entry.remapped_lines if line.strip())
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def find_layer_block(
    layers: dict[tuple[str, str], list[broad.HistoryBlock]],
    raw_id: str,
    layer: str,
) -> tuple[broad.HistoryBlock | None, int]:
    candidates = layers.get((raw_id, layer), [])
    return (candidates[0] if candidates else None, len(candidates))


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_DIR)
    review_rows = read_csv(output_dir / REVIEW_REPORT)

    current_landed_ids = broad.collect_working_landed_ids(repo_root)
    upstream_revision = args.upstream_revision or "MERGE_HEAD"
    upstream_landed_ids = broad.collect_revision_landed_ids(
        repo_root, upstream_revision
    )
    _tokens, by_upstream, by_current, mapping_issues = delta.load_mapping(
        args.relation_csv, current_landed_ids
    )
    if mapping_issues:
        raise RuntimeError(f"mapping parse issues remain: {len(mapping_issues)}")
    unique_mapping = {
        upstream_id: next(iter({token.current_title_id for token in group}))
        for upstream_id, group in by_upstream.items()
        if len({token.current_title_id for token in group}) == 1
    }
    ambiguous_mapping_ids = {
        upstream_id
        for upstream_id, group in by_upstream.items()
        if len({token.current_title_id for token in group}) > 1
    }

    stage_texts, source_mode = broad.load_three_way_texts(
        repo_root,
        broad.TITLE_HISTORY_PATHS,
        args.base_revision,
        args.ours_revision,
        args.upstream_revision,
    )
    raw_base = broad.build_snapshot(
        "raw_base", stage_texts[1], delta.identity_mapper, {}
    )
    raw_upstream = broad.build_snapshot(
        "raw_upstream", stage_texts[3], delta.identity_mapper, {}
    )
    current = broad.build_snapshot(
        "working_current", working_texts(repo_root), delta.identity_mapper, {}
    )
    base_layers = delta.layered_blocks(raw_base)
    upstream_layers = delta.layered_blocks(raw_upstream)

    entry_rows: list[dict[str, str]] = []
    block_rows: list[dict[str, str]] = []
    processable = {
        "manual_both_modified",
        "needs_entry_merge_multi_donor",
        "manual_ambiguous_mapping",
    }

    for donor_row in review_rows:
        donor_resolution = donor_row["resolution"]
        raw_id = donor_row["raw_upstream_title_id"]
        layer = donor_row["history_layer"]
        if donor_resolution not in processable or donor_row["upstream_change"] != "changed":
            block_rows.append(
                {
                    **donor_row,
                    "entry_audit_status": "manual_block_level_resolution",
                    "detail": "not eligible for entry-level merge",
                }
            )
            continue

        base_block, base_count = find_layer_block(base_layers, raw_id, layer)
        upstream_block, upstream_count = find_layer_block(upstream_layers, raw_id, layer)
        if base_count != 1 or upstream_count != 1 or not base_block or not upstream_block:
            block_rows.append(
                {
                    **donor_row,
                    "entry_audit_status": "manual_non_unique_donor_layer",
                    "detail": f"base_count={base_count};upstream_count={upstream_count}",
                }
            )
            continue

        targets = sorted(
            {token.current_title_id for token in by_upstream.get(raw_id, [])}
        )
        if not targets:
            block_rows.append(
                {
                    **donor_row,
                    "entry_audit_status": "manual_no_current_target",
                    "detail": "",
                }
            )
            continue

        for target in targets:
            current_candidates = delta.current_layer_blocks(current, target, layer)
            if len(current_candidates) != 1:
                block_rows.append(
                    {
                        **donor_row,
                        "current_target": target,
                        "entry_audit_status": "manual_current_layer_block_count",
                        "detail": f"current_count={len(current_candidates)}",
                    }
                )
                continue
            current_block = current_candidates[0]
            target_mapping = dict(unique_mapping)
            target_mapping[raw_id] = target
            base_entries = [
                canonicalize(entry, target_mapping) for entry in parse_entries(base_block)
            ]
            upstream_entries = [
                canonicalize(entry, target_mapping)
                for entry in parse_entries(upstream_block)
            ]
            current_entries = [
                canonicalize(entry, target_mapping)
                for entry in parse_entries(current_block)
            ]
            current_counts = semantic_counts(current_entries)
            base_counts = semantic_counts(base_entries)
            donor_presence = sum(
                min(count, current_counts.get(semantic_key, 0))
                for semantic_key, count in base_counts.items()
            )
            operations = entry_operations(base_entries, upstream_entries)
            if donor_presence == 0:
                block_rows.append(
                    {
                        **donor_row,
                        "current_target": target,
                        "entry_audit_status": "manual_no_base_lineage_in_current",
                        "detail": f"base_entries={len(base_entries)};operations={len(operations)}",
                    }
                )
                continue

            for operation_index, (operation, base_entry, upstream_entry) in enumerate(
                operations, start=1
            ):
                base_matches = current_counts.get(
                    base_entry.semantic if base_entry else "", 0
                )
                upstream_matches = current_counts.get(
                    upstream_entry.semantic if upstream_entry else "", 0
                )
                base_tokens = active_tokens(base_entry.remapped_lines) if base_entry else set()
                upstream_tokens = (
                    active_tokens(upstream_entry.remapped_lines) if upstream_entry else set()
                )
                unresolved_new = sorted(
                    token
                    for token in upstream_tokens - base_tokens
                    if token in ambiguous_mapping_ids
                    or (token in upstream_landed_ids and token not in current_landed_ids)
                )

                if unresolved_new:
                    resolution = "manual_new_unresolved_title_reference"
                elif operation == "replace":
                    if base_matches == 1 and upstream_matches == 0:
                        resolution = "safe_replace_entry"
                    elif base_matches == 0 and upstream_matches == 1:
                        resolution = "already_applied_entry"
                    elif base_matches > 1 or upstream_matches > 1:
                        resolution = "manual_duplicate_entry_match"
                    elif base_matches == 1 and upstream_matches == 1:
                        resolution = "manual_both_entry_versions_present"
                    else:
                        resolution = "manual_current_entry_modified"
                elif operation == "delete":
                    if base_matches == 1:
                        resolution = "safe_delete_entry"
                    elif base_matches > 1:
                        resolution = "manual_duplicate_entry_match"
                    else:
                        resolution = "manual_current_entry_missing"
                else:
                    if upstream_matches == 0:
                        resolution = "safe_insert_entry"
                    elif upstream_matches == 1:
                        resolution = "already_applied_entry"
                    else:
                        resolution = "manual_duplicate_entry_match"

                source_entry = base_entry or upstream_entry
                entry_rows.append(
                    {
                        "raw_upstream_title_id": raw_id,
                        "history_layer": layer,
                        "current_target": target,
                        "donor_resolution": donor_resolution,
                        "donor_presence": str(donor_presence),
                        "base_entry_count": str(len(base_entries)),
                        "operation_index": str(operation_index),
                        "entry_key": source_entry.entry.key if source_entry else "",
                        "operation": operation,
                        "resolution": resolution,
                        "base_matches_in_current": str(base_matches),
                        "upstream_matches_in_current": str(upstream_matches),
                        "unresolved_new_title_tokens": "&".join(unresolved_new),
                        "base_preview": preview(base_entry),
                        "upstream_preview": preview(upstream_entry),
                        "base_path": base_block.path,
                        "base_line": str(
                            base_block.start_line
                            + (base_entry.entry.relative_start if base_entry else 0)
                        ),
                        "upstream_path": upstream_block.path,
                        "upstream_line": str(
                            upstream_block.start_line
                            + (upstream_entry.entry.relative_start if upstream_entry else 0)
                        ),
                        "current_path": current_block.path,
                        "current_block_line": str(current_block.start_line),
                    }
                )

    safe_entry_resolutions = {
        "safe_replace_entry",
        "safe_delete_entry",
        "safe_insert_entry",
    }
    safe_rows = [
        row for row in entry_rows if row["resolution"] in safe_entry_resolutions
    ]
    manual_rows = [
        row for row in entry_rows if row["resolution"].startswith("manual_")
    ]
    broad.write_csv(output_dir / "title_history_entry_delta_audit.csv", entry_rows)
    broad.write_csv(output_dir / "title_history_entry_delta_safe.csv", safe_rows)
    broad.write_csv(output_dir / "title_history_entry_delta_manual.csv", manual_rows)
    broad.write_csv(output_dir / "title_history_entry_delta_block_review.csv", block_rows)

    resolution_counts = Counter(row["resolution"] for row in entry_rows)
    block_counts = Counter(row["entry_audit_status"] for row in block_rows)
    summary = [
        "# Title History Entry Delta Audit",
        "",
        f"- source mode: {source_mode}",
        f"- base revision: {args.base_revision or 'index stage 1'}",
        f"- current source: working tree (ours revision {args.ours_revision or 'index stage 2'})",
        f"- upstream revision: {args.upstream_revision or 'index stage 3'}",
        f"- donor review rows: {len(review_rows)}",
        f"- entry operations: {len(entry_rows)}",
        f"- safe entry operations: {len(safe_rows)}",
        f"- manual entry operations: {len(manual_rows)}",
        f"- block-level review rows: {len(block_rows)}",
        "",
        "## Entry Resolutions",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(resolution_counts.items())],
        "",
        "## Block Resolutions",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(block_counts.items())],
        "",
        "## Safety",
        "",
        "- This tool is read-only.",
        "- Safe replacements require one exact base entry in current and no upstream version.",
        "- Insertions require proven donor lineage in the current target block.",
    ]
    (output_dir / "title_history_entry_delta_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )

    print(f"entry operations: {len(entry_rows)}")
    print(f"safe entry operations: {len(safe_rows)}")
    print(f"manual entry operations: {len(manual_rows)}")
    print(f"block-level review rows: {len(block_rows)}")
    print(f"summary: {output_dir / 'title_history_entry_delta_summary.md'}")


if __name__ == "__main__":
    main()
