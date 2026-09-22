from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

import audit_upstream_title_history_delta as delta
import audit_upstream_title_history_entry_delta as entry_audit
import audit_upstream_title_history_merge as broad


OUTPUT_DIR = "development/analysis/generated/upstream_merge_audit"


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]
    parser = argparse.ArgumentParser(
        description="Classify the remaining title-history merge conflicts after safe apply."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--relation-csv",
        type=Path,
        default=repo_root
        / "development/pipeline_inputs/title_relations/curated_title_relations.csv",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {str(key).strip(): (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, skipinitialspace=True)
        ]


def operation_key(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row.get("raw_upstream_title_id", ""),
        row.get("history_layer", ""),
        row.get("current_target", ""),
        row.get("entry_key", ""),
        row.get("operation", ""),
        row.get("base_preview", ""),
        row.get("upstream_preview", ""),
    )


def working_texts(repo_root: Path) -> dict[str, str]:
    return {
        path: (repo_root / path).read_text(encoding="utf-8-sig")
        for path in broad.TITLE_HISTORY_PATHS
    }


def current_key_entries(
    current: broad.Snapshot,
    target: str,
    layer: str,
    key: str,
    mapping: dict[str, str],
) -> list[entry_audit.CanonicalEntry]:
    blocks = delta.current_layer_blocks(current, target, layer)
    if len(blocks) != 1:
        return []
    return [
        entry_audit.canonicalize(entry, mapping)
        for entry in entry_audit.parse_entries(blocks[0])
        if entry.key == key
    ]


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_DIR)
    manual_rows = read_csv(output_dir / "title_history_entry_delta_manual.csv")
    block_rows = read_csv(output_dir / "title_history_entry_delta_block_review.csv")
    applied_rows = read_csv(output_dir / "title_history_entry_apply_rows.csv")
    applied_keys = {operation_key(row) for row in applied_rows}

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
    current = broad.build_snapshot(
        "working_current", working_texts(repo_root), delta.identity_mapper, {}
    )

    classified_entries: list[dict[str, str]] = []
    for row in manual_rows:
        raw_id = row["raw_upstream_title_id"]
        target = row["current_target"]
        target_mapping = dict(unique_mapping)
        target_mapping[raw_id] = target
        current_entries = current_key_entries(
            current,
            target,
            row["history_layer"],
            row["entry_key"],
            target_mapping,
        )
        current_previews = " || ".join(entry_audit.preview(entry) for entry in current_entries)
        if operation_key(row) in applied_keys:
            classification = "resolved_by_verified_safe_apply"
        elif row["resolution"] == "manual_current_entry_missing":
            classification = "keep_current_upstream_delete_conflict"
        else:
            classification = "inspect_three_way_entry"
        classified_entries.append(
            {
                **row,
                "classification": classification,
                "current_same_key_count": str(len(current_entries)),
                "current_same_key_previews": current_previews,
            }
        )

    classified_blocks: list[dict[str, str]] = []
    for row in block_rows:
        if row["upstream_change"] == "comment_or_format_only":
            classification = "resolved_keep_current_format"
        elif row["resolution"] == "manual_ours_modified_upstream_deleted":
            classification = "resolved_keep_ours_modified_block"
        elif row["entry_audit_status"] == "manual_no_base_lineage_in_current":
            classification = "inspect_no_lineage_block"
        else:
            classification = "inspect_block_level"
        classified_blocks.append({**row, "classification": classification})

    broad.write_csv(
        output_dir / "title_history_remaining_entry_classification.csv",
        classified_entries,
    )
    broad.write_csv(
        output_dir / "title_history_remaining_block_classification.csv",
        classified_blocks,
    )
    entry_counts = Counter(row["classification"] for row in classified_entries)
    block_counts = Counter(row["classification"] for row in classified_blocks)
    summary = [
        "# Title History Remaining Classification",
        "",
        f"- current manual entry rows: {len(manual_rows)}",
        f"- current block review rows: {len(block_rows)}",
        "",
        "## Entry Classification",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(entry_counts.items())],
        "",
        "## Block Classification",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(block_counts.items())],
    ]
    (output_dir / "title_history_remaining_classification_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )

    print(f"entry classifications: {dict(entry_counts)}")
    print(f"block classifications: {dict(block_counts)}")
    print(
        "summary: "
        f"{output_dir / 'title_history_remaining_classification_summary.md'}"
    )


if __name__ == "__main__":
    main()
