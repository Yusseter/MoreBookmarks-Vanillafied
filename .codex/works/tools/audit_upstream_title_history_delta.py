from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import audit_upstream_title_history_merge as broad
import build_landed_title_asil_mod_metadata_transfer_dry_run as landed


OUTPUT_DIR = ".codex/works/analysis/generated/upstream_merge_audit"
NO_COUNTERPART = "*there_is_no*"


@dataclass(frozen=True)
class MappingToken:
    current_title_id: str
    upstream_title_id: str
    is_same: bool
    is_second: bool
    row_number: int
    token_index: int


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]
    parser = argparse.ArgumentParser(
        description="Audit only the upstream base-to-MERGE_HEAD title-history delta."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--relation-csv",
        type=Path,
        default=repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--base-revision", default="")
    parser.add_argument("--ours-revision", default="")
    parser.add_argument("--upstream-revision", default="")
    return parser.parse_args()


def split_tokens(value: str) -> list[str]:
    return [token.strip() for token in re.split(r"\s*[;&]\s*", value) if token.strip()]


def load_mapping(
    path: Path,
    current_landed_ids: set[str],
) -> tuple[
    list[MappingToken],
    dict[str, list[MappingToken]],
    dict[str, list[MappingToken]],
    list[dict[str, str]],
]:
    tokens: list[MappingToken] = []
    issues: list[dict[str, str]] = []
    explicit_current_ids: set[str] = set()
    suppressed_upstream_ids: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row_number, raw_row in enumerate(
            csv.DictReader(handle, skipinitialspace=True), start=2
        ):
            row = {
                str(key).strip(): (value or "").strip()
                for key, value in raw_row.items()
                if key is not None
            }
            current_values = split_tokens(row.get("source_title_id", ""))
            upstream_values = split_tokens(row.get("mod_title_id", ""))
            same_values = split_tokens(row.get("is_same_title_id", ""))
            if not current_values:
                continue
            if current_values == ["none"]:
                suppressed_upstream_ids.update(
                    raw.replace("(second)", "").strip()
                    for raw in upstream_values
                    if raw.replace("(second)", "").strip()
                )
                continue
            explicit_current_ids.update(current_values)
            if not upstream_values:
                continue

            pairs: list[tuple[str, str, str, int]] = []
            if len(current_values) == 1:
                if len(same_values) not in {0, 1, len(upstream_values)}:
                    issues.append(
                        {
                            "row_number": str(row_number),
                            "current_title_id": current_values[0],
                            "status": "mapping_token_count_mismatch",
                            "detail": (
                                f"current_tokens=1;upstream_tokens={len(upstream_values)};"
                                f"same_tokens={len(same_values)}"
                            ),
                        }
                    )
                for index, upstream in enumerate(upstream_values):
                    same = (
                        same_values[index]
                        if len(same_values) == len(upstream_values)
                        else (same_values[0] if same_values else "")
                    )
                    pairs.append((current_values[0], upstream, same, index + 1))
            elif len(upstream_values) == 1:
                if len(same_values) not in {0, 1, len(current_values)}:
                    issues.append(
                        {
                            "row_number": str(row_number),
                            "current_title_id": "&".join(current_values),
                            "status": "mapping_token_count_mismatch",
                            "detail": (
                                f"current_tokens={len(current_values)};upstream_tokens=1;"
                                f"same_tokens={len(same_values)}"
                            ),
                        }
                    )
                for index, current in enumerate(current_values):
                    same = (
                        same_values[index]
                        if len(same_values) == len(current_values)
                        else (same_values[0] if same_values else "")
                    )
                    pairs.append((current, upstream_values[0], same, index + 1))
            elif len(current_values) == len(upstream_values):
                for index, (current, upstream) in enumerate(
                    zip(current_values, upstream_values, strict=True), start=1
                ):
                    same = (
                        same_values[index - 1]
                        if len(same_values) == len(current_values)
                        else (same_values[0] if same_values else "")
                    )
                    pairs.append((current, upstream, same, index))
            else:
                issues.append(
                    {
                        "row_number": str(row_number),
                        "current_title_id": "&".join(current_values),
                        "status": "mapping_group_shape_mismatch",
                        "detail": (
                            f"current_tokens={len(current_values)};"
                            f"upstream_tokens={len(upstream_values)}"
                        ),
                    }
                )
                continue

            for current, raw_upstream, same_raw, token_index in pairs:
                is_second = "(second)" in raw_upstream
                upstream = raw_upstream.replace("(second)", "").strip()
                if not upstream or upstream == NO_COUNTERPART:
                    continue
                tokens.append(
                    MappingToken(
                        current_title_id=current,
                        upstream_title_id=upstream,
                        is_same=same_raw.lower() == "yes",
                        is_second=is_second,
                        row_number=row_number,
                        token_index=token_index,
                    )
                )

    # Titles outside the curated east scope use their unchanged ID.
    for title_id in sorted(current_landed_ids - explicit_current_ids):
        if title_id in suppressed_upstream_ids:
            continue
        tokens.append(
            MappingToken(
                current_title_id=title_id,
                upstream_title_id=title_id,
                is_same=True,
                is_second=False,
                row_number=0,
                token_index=1,
            )
        )

    by_upstream: dict[str, list[MappingToken]] = defaultdict(list)
    by_current: dict[str, list[MappingToken]] = defaultdict(list)
    for token in tokens:
        by_upstream[token.upstream_title_id].append(token)
        by_current[token.current_title_id].append(token)
    return tokens, dict(by_upstream), dict(by_current), issues


def identity_mapper(raw_title_id: str) -> tuple[str, str]:
    return raw_title_id, "identity"


def canonical_block_text(
    block: broad.HistoryBlock | None,
    target_title_id: str,
    unique_token_map: dict[str, str],
) -> str:
    if block is None:
        return ""
    text = "\n".join(block.lines)
    text = broad.remap_text(text, unique_token_map)
    if block.raw_title_id != target_title_id:
        text = re.sub(
            rf"(?m)^(\s*){re.escape(block.raw_title_id)}(\s*=\s*\{{)",
            rf"\1{target_title_id}\2",
            text,
            count=1,
        )
    return text


def semantic(text: str) -> str:
    return broad.normalize_semantic(text)


def raw_change(
    base: broad.HistoryBlock | None,
    upstream: broad.HistoryBlock | None,
) -> str:
    if base is None:
        return "added"
    if upstream is None:
        return "deleted"
    if base.semantic_key != upstream.semantic_key:
        return "changed"
    if base.exact_key != upstream.exact_key:
        return "comment_or_format_only"
    return "unchanged"


def history_layer(path: str) -> str:
    return "development" if path.endswith("z00_ADEVELOPMENT.txt") else "regional"


def layered_blocks(
    snapshot: broad.Snapshot,
) -> dict[tuple[str, str], list[broad.HistoryBlock]]:
    result: dict[tuple[str, str], list[broad.HistoryBlock]] = defaultdict(list)
    for raw_id, blocks in snapshot.block_lists.items():
        for block in blocks:
            result[(raw_id, history_layer(block.path))].append(block)
    return dict(result)


def current_layer_blocks(
    snapshot: broad.Snapshot,
    title_id: str,
    layer: str,
) -> list[broad.HistoryBlock]:
    return [
        block
        for block in snapshot.block_lists.get(title_id, ())
        if history_layer(block.path) == layer
    ]


def determine_resolution(
    raw_id: str,
    change: str,
    mapping_tokens: list[MappingToken],
    by_current: dict[str, list[MappingToken]],
    base_block: broad.HistoryBlock | None,
    ours_block: broad.HistoryBlock | None,
    ours_block_count: int,
    upstream_block: broad.HistoryBlock | None,
    unique_token_map: dict[str, str],
) -> tuple[str, str, str]:
    targets = sorted({token.current_title_id for token in mapping_tokens})
    if not targets:
        return "ignore_no_current_counterpart", "", ""
    primary_targets = sorted(
        {token.current_title_id for token in mapping_tokens if not token.is_second}
    )
    if len(primary_targets) != 1 or len(targets) != 1:
        return "manual_ambiguous_mapping", "&".join(targets), ""

    target = targets[0]
    if ours_block_count > 1:
        return "manual_duplicate_current_block", target, ""

    donor_count = len({token.upstream_title_id for token in by_current.get(target, [])})
    if donor_count > 1:
        return "needs_entry_merge_multi_donor", target, str(donor_count)

    if change == "added":
        if ours_block is None:
            return "safe_add_whole_block", target, "1"
        upstream_text = canonical_block_text(upstream_block, target, unique_token_map)
        ours_text = "\n".join(ours_block.lines)
        if semantic(ours_text) == semantic(upstream_text):
            return "already_applied", target, "1"
        return "manual_both_added", target, "1"

    if change == "deleted":
        if ours_block is None:
            return "already_applied", target, "1"
        base_text = canonical_block_text(base_block, target, unique_token_map)
        ours_text = "\n".join(ours_block.lines)
        if semantic(ours_text) == semantic(base_text):
            return "safe_delete_whole_block", target, "1"
        return "manual_ours_modified_upstream_deleted", target, "1"

    if change == "changed":
        if ours_block is None:
            return "manual_missing_current_block", target, "1"
        base_text = canonical_block_text(base_block, target, unique_token_map)
        upstream_text = canonical_block_text(upstream_block, target, unique_token_map)
        ours_text = "\n".join(ours_block.lines)
        if semantic(ours_text) == semantic(upstream_text):
            return "already_applied", target, "1"
        if semantic(ours_text) == semantic(base_text):
            return "safe_replace_whole_block", target, "1"
        return "manual_both_modified", target, "1"

    return "ignore_comment_or_format_only", target, str(donor_count)


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_DIR)

    current_landed_ids = broad.collect_working_landed_ids(repo_root)
    tokens, by_upstream, by_current, mapping_issues = load_mapping(
        args.relation_csv, current_landed_ids
    )
    unique_token_map = {
        upstream_id: next(iter({token.current_title_id for token in group}))
        for upstream_id, group in by_upstream.items()
        if len({token.current_title_id for token in group}) == 1
    }

    stage_texts, source_mode = broad.load_three_way_texts(
        repo_root,
        broad.TITLE_HISTORY_PATHS,
        args.base_revision,
        args.ours_revision,
        args.upstream_revision,
    )
    raw_base = broad.build_snapshot("raw_base", stage_texts[1], identity_mapper, {})
    ours = broad.build_snapshot("ours", stage_texts[2], identity_mapper, {})
    raw_upstream = broad.build_snapshot(
        "raw_upstream", stage_texts[3], identity_mapper, {}
    )

    base_layers = layered_blocks(raw_base)
    ours_layers = layered_blocks(ours)
    upstream_layers = layered_blocks(raw_upstream)
    rows: list[dict[str, str]] = []
    raw_keys = sorted(set(base_layers) | set(upstream_layers))
    for raw_id, layer in raw_keys:
        base_candidates = base_layers.get((raw_id, layer), [])
        upstream_candidates = upstream_layers.get((raw_id, layer), [])
        base_block = base_candidates[0] if base_candidates else None
        upstream_block = upstream_candidates[0] if upstream_candidates else None
        change = raw_change(base_block, upstream_block)
        if change == "unchanged":
            continue
        mapping_group = by_upstream.get(raw_id, [])
        mapping_targets = sorted({token.current_title_id for token in mapping_group})
        provisional_target = mapping_targets[0] if len(mapping_targets) == 1 else ""
        ours_candidates = current_layer_blocks(ours, provisional_target, layer)
        ours_block = ours_candidates[0] if ours_candidates else None
        if len(base_candidates) > 1 or len(upstream_candidates) > 1:
            resolution, target, donor_count = (
                "manual_duplicate_raw_block",
                "",
                "",
            )
        else:
            resolution, target, donor_count = determine_resolution(
                raw_id,
                change,
                mapping_group,
                by_current,
                base_block,
                ours_block,
                len(ours_candidates),
                upstream_block,
                unique_token_map,
            )
        rows.append(
            {
                "raw_upstream_title_id": raw_id,
                "history_layer": layer,
                "upstream_change": change,
                "resolution": resolution,
                "current_target": target,
                "target_donor_count": donor_count,
                "mapping_targets": "&".join(
                    sorted(
                        {
                            token.current_title_id
                            for token in by_upstream.get(raw_id, [])
                        }
                    )
                ),
                "base_path": broad.block_field(base_block, "path"),
                "upstream_path": broad.block_field(upstream_block, "path"),
                "base_line": broad.block_field(base_block, "start_line"),
                "upstream_line": broad.block_field(upstream_block, "start_line"),
                "ours_path": broad.block_field(ours_block, "path"),
                "ours_line": broad.block_field(ours_block, "start_line"),
            }
        )

    safe_resolutions = {
        "safe_add_whole_block",
        "safe_delete_whole_block",
        "safe_replace_whole_block",
    }
    safe_rows = [row for row in rows if row["resolution"] in safe_resolutions]
    review_rows = [
        row
        for row in rows
        if row["resolution"].startswith(("manual_", "needs_entry_merge_"))
    ]
    broad.write_csv(output_dir / "title_history_upstream_delta_audit.csv", rows)
    broad.write_csv(output_dir / "title_history_upstream_delta_safe.csv", safe_rows)
    broad.write_csv(output_dir / "title_history_upstream_delta_review.csv", review_rows)
    broad.write_csv(output_dir / "title_history_mapping_parse_issues.csv", mapping_issues)

    change_counts = Counter(row["upstream_change"] for row in rows)
    resolution_counts = Counter(row["resolution"] for row in rows)
    summary = [
        "# Title History Upstream Delta Audit",
        "",
        f"- source mode: {source_mode}",
        f"- base revision: {args.base_revision or 'index stage 1'}",
        f"- ours revision: {args.ours_revision or 'index stage 2'}",
        f"- upstream revision: {args.upstream_revision or 'index stage 3'}",
        f"- mapping tokens: {len(tokens)}",
        f"- mapping parse issues: {len(mapping_issues)}",
        f"- base raw history blocks: {sum(len(items) for items in raw_base.block_lists.values())}",
        f"- upstream raw history blocks: {sum(len(items) for items in raw_upstream.block_lists.values())}",
        f"- upstream delta rows: {len(rows)}",
        f"- safe whole-block rows: {len(safe_rows)}",
        f"- review rows: {len(review_rows)}",
        "",
        "## Changes",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(change_counts.items())],
        "",
        "## Resolutions",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(resolution_counts.items())],
        "",
        "## Safety",
        "",
        "- This tool is read-only.",
        "- Semicolon and ampersand mapping groups are both expanded.",
        "- Multi-donor current titles are never replaced as whole blocks.",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "title_history_upstream_delta_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )

    print(f"upstream delta rows: {len(rows)}")
    print(f"safe whole-block rows: {len(safe_rows)}")
    print(f"review rows: {len(review_rows)}")
    print(f"mapping parse issues: {len(mapping_issues)}")
    print(f"summary: {output_dir / 'title_history_upstream_delta_summary.md'}")


if __name__ == "__main__":
    main()
