from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import audit_repo_semantic_compatibility as semantic
import audit_upstream_title_history_entry_delta as entry_audit
import audit_upstream_title_history_merge as history_merge


DEFAULT_INPUT = (
    "development/analysis/generated/repo_semantic_compatibility/"
    "title_history_source_overwrite_candidates.csv"
)
DEFAULT_OUTPUT_DIR = (
    "development/analysis/generated/repo_integration_closure/"
    "title_history_merge_regression_fixes"
)
DEFAULT_TITLES = (
    "c_SUM_riak_nan_berbedur",
    "c_dole",
    "c_hyuga",
    "d_lucca",
)
HOLDER_RE = re.compile(r"(?m)^\s*holder\s*=\s*([A-Za-z0-9_.\-]+)\b")


@dataclass(frozen=True)
class TextEdit:
    title_id: str
    path: str
    start: int
    end: int
    replacement: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    repo_root = semantic.find_project_root()
    parser = argparse.ArgumentParser(
        description=(
            "Build a read-only, entry-level fix report for title-history merge "
            "regressions. Live title-history files are never edited."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--premerge", default=semantic.DEFAULT_PREMERGE_REVISION)
    parser.add_argument(
        "--merged-source", default=semantic.DEFAULT_MERGED_SOURCE_REVISION
    )
    parser.add_argument(
        "--vanilla-game-root",
        type=Path,
        default=semantic.DEFAULT_VANILLA_GAME_ROOT,
    )
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--titles", nargs="*", default=list(DEFAULT_TITLES))
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {str(key).strip(): (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, skipinitialspace=True)
        ]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity_mapper(title_id: str) -> tuple[str, str]:
    return title_id, "identity"


def parse_blocks(
    label: str, path: str, text: str
) -> list[history_merge.HistoryBlock]:
    blocks, unmapped, brace_delta = history_merge.parse_file_blocks(
        label, path, text, identity_mapper, {}
    )
    if unmapped:
        raise RuntimeError(f"unexpected unmapped blocks in {label}:{path}")
    if brace_delta:
        raise RuntimeError(f"brace delta {brace_delta} in {label}:{path}")
    return blocks


def block_at_line(
    label: str, path: str, text: str, start_line: int
) -> history_merge.HistoryBlock:
    matches = [
        block
        for block in parse_blocks(label, path, text)
        if block.start_line == start_line
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one block at {label}:{path}:{start_line}, found {len(matches)}"
        )
    return matches[0]


def block_for_title(
    label: str, path: str, text: str, title_id: str
) -> history_merge.HistoryBlock:
    matches = [
        block
        for block in parse_blocks(label, path, text)
        if block.raw_title_id == title_id
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one {title_id} block in {label}:{path}, found {len(matches)}"
        )
    return matches[0]


def entry_holder(item: entry_audit.Entry | None) -> str:
    if item is None:
        return ""
    active = "\n".join(semantic.strip_comment(line) for line in item.lines)
    match = HOLDER_RE.search(active)
    return match.group(1) if match else ""


def block_holders(block: history_merge.HistoryBlock) -> list[str]:
    return [
        holder
        for item in entry_audit.parse_entries(block)
        if (holder := entry_holder(item))
    ]


def entry_semantic(item: entry_audit.Entry) -> str:
    return history_merge.normalize_semantic("\n".join(item.lines))


def entry_counter(items: list[entry_audit.Entry]) -> Counter[str]:
    return Counter(entry_semantic(item) for item in items)


def counter_without(
    items: list[entry_audit.Entry], remove: entry_audit.Entry
) -> Counter[str]:
    result = entry_counter(items)
    key = entry_semantic(remove)
    result[key] -= 1
    if result[key] == 0:
        del result[key]
    return result


def entry_groups(
    items: list[entry_audit.Entry],
) -> dict[str, list[entry_audit.Entry]]:
    grouped: dict[str, list[entry_audit.Entry]] = defaultdict(list)
    for item in items:
        grouped[item.key].append(item)
    return dict(grouped)


def compact_lines(lines: tuple[str, ...], limit: int = 420) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def compact_entry(item: entry_audit.Entry | None) -> str:
    return compact_lines(item.lines) if item else ""


def same_except_pair(
    current_entries: list[entry_audit.Entry],
    current_item: entry_audit.Entry,
    premerge_entries: list[entry_audit.Entry],
    premerge_item: entry_audit.Entry,
) -> bool:
    return counter_without(current_entries, current_item) == counter_without(
        premerge_entries, premerge_item
    )


def absolute_entry_edit(
    title_id: str,
    block: history_merge.HistoryBlock,
    item: entry_audit.Entry,
    replacement: tuple[str, ...],
) -> TextEdit:
    file_start = block.start_line - 1
    return TextEdit(
        title_id=title_id,
        path=block.path,
        start=file_start + item.relative_start,
        end=file_start + item.relative_end,
        replacement=replacement,
    )


def apply_edits(lines: list[str], edits: list[TextEdit]) -> list[str]:
    result = list(lines)
    previous_start = len(result) + 1
    for edit in sorted(edits, key=lambda item: item.start, reverse=True):
        if edit.end > previous_start:
            raise RuntimeError(f"overlapping preview edits near {edit.title_id}")
        result[edit.start : edit.end] = list(edit.replacement)
        previous_start = edit.start
    return result


def build_patch(
    current_texts: dict[str, str], modified_texts: dict[str, str]
) -> str:
    output: list[str] = []
    for path in sorted(modified_texts):
        before = current_texts[path].splitlines()
        after = modified_texts[path].splitlines()
        if before == after:
            continue
        output.extend(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
        )
    return "\n".join(output) + ("\n" if output else "")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    input_path = args.input or (repo_root / DEFAULT_INPUT)
    output_dir = args.output_dir or (repo_root / DEFAULT_OUTPUT_DIR)
    if not input_path.is_absolute():
        input_path = repo_root / input_path
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    requested = set(args.titles)
    all_rows = read_csv(input_path)
    requested_rows = [
        row for row in all_rows if row.get("current_title_id") in requested
    ]
    found = {row["current_title_id"] for row in requested_rows}
    missing = sorted(requested - found)
    if missing:
        raise RuntimeError(f"semantic report rows missing: {', '.join(missing)}")

    source_rows = [
        row
        for row in requested_rows
        if row.get("classification") == "merge_regression"
    ]
    skipped_rows = [
        {
            "title_id": row["current_title_id"],
            "classification": row.get("classification", ""),
            "history_layer": row.get("history_layer", ""),
            "current_path": row.get("current_path", ""),
            "premerge_holder_provenance": row.get(
                "premerge_holder_provenance", ""
            ),
            "premerge_holder_commits": row.get("premerge_holder_commits", ""),
            "recommendation": row.get("recommendation", ""),
            "skip_reason": "not_classified_as_merge_regression",
        }
        for row in sorted(requested_rows, key=lambda item: item["current_title_id"])
        if row.get("classification") != "merge_regression"
    ]

    premerge_revision = semantic.git_text(
        repo_root, "rev-parse", args.premerge
    ).strip()
    source_revision = semantic.git_text(
        repo_root, "rev-parse", args.merged_source
    ).strip()
    current_revision = semantic.git_text(repo_root, "rev-parse", "HEAD").strip()
    character_ids = semantic.collect_current_character_ids(
        repo_root, args.vanilla_game_root.resolve()
    )

    current_texts: dict[str, str] = {}
    edits_by_path: dict[str, list[TextEdit]] = defaultdict(list)
    candidate_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []

    for row in sorted(source_rows, key=lambda item: item["current_title_id"]):
        title_id = row["current_title_id"]
        current_path = row["current_path"]
        premerge_path = row["premerge_path"]
        source_path = row["source_path"]
        current_text = current_texts.setdefault(
            current_path,
            (repo_root / current_path).read_text(
                encoding="utf-8-sig", errors="strict"
            ),
        )
        premerge_text = history_merge.git_revision_text(
            repo_root, premerge_revision, premerge_path
        )
        source_text = history_merge.git_revision_text(
            repo_root, source_revision, source_path
        )
        current_block = block_at_line(
            "current", current_path, current_text, int(row["current_line"])
        )
        premerge_block = block_at_line(
            "premerge", premerge_path, premerge_text, int(row["premerge_line"])
        )
        source_block = block_at_line(
            "source", source_path, source_text, int(row["source_line"])
        )
        if current_block.raw_title_id != title_id:
            raise RuntimeError(
                f"current block at reported line is {current_block.raw_title_id}, "
                f"expected {title_id}"
            )
        if premerge_block.raw_title_id != title_id:
            raise RuntimeError(
                f"premerge block at reported line is {premerge_block.raw_title_id}, "
                f"expected {title_id}"
            )

        current_entries = entry_audit.parse_entries(current_block)
        premerge_entries = entry_audit.parse_entries(premerge_block)
        current_groups = entry_groups(current_entries)
        premerge_groups = entry_groups(premerge_entries)
        current_holders = block_holders(current_block)
        premerge_holders = block_holders(premerge_block)
        source_holders = block_holders(source_block)
        current_undefined = [
            holder for holder in current_holders if holder not in character_ids
        ]
        premerge_undefined = [
            holder for holder in premerge_holders if holder not in character_ids
        ]
        undefined_entries = [
            item
            for item in current_entries
            if entry_holder(item) and entry_holder(item) not in character_ids
        ]
        source_match = (
            current_block.semantic_key == source_block.semantic_key
            or current_holders == source_holders
        )

        action = "manual_reconcile_block"
        scope = "block_review"
        confidence = "low"
        manual_resolution = "yes"
        affected_key = ""
        current_preview = ""
        candidate_preview = ""
        reason = (
            "No unambiguous entry-level replacement removes every undefined "
            "holder while preserving both source additions and premerge local history."
        )
        patch_included = "no"

        all_current_holders_undefined = bool(current_holders) and (
            len(current_undefined) == len(current_holders)
        )
        all_premerge_holders_defined = bool(premerge_holders) and not premerge_undefined

        if (
            source_match
            and all_current_holders_undefined
            and all_premerge_holders_defined
        ):
            action = "restore_premerge_block"
            scope = "whole_block"
            confidence = "high"
            manual_resolution = "no"
            affected_key = "all_holder_dates"
            current_preview = (
                f"{len(current_holders)} source-matching holders; all undefined"
            )
            candidate_preview = (
                f"restore premerge lines {premerge_block.start_line}-"
                f"{premerge_block.end_line}; {len(premerge_holders)} holders; "
                "all defined"
            )
            reason = (
                "The current holder chain matches the source chain and every "
                "holder is undefined; the complete premerge chain is defined."
            )
            edits_by_path[current_path].append(
                TextEdit(
                    title_id=title_id,
                    path=current_path,
                    start=current_block.start_line - 1,
                    end=current_block.end_line,
                    replacement=premerge_block.lines,
                )
            )
            patch_included = "yes"
            review_rows.append(
                {
                    "title_id": title_id,
                    "entry_key": "all_holder_dates",
                    "review_type": "high_confidence_candidate",
                    "current_holder": " | ".join(current_holders),
                    "current_holder_defined": "no",
                    "current_preview": current_preview,
                    "premerge_holder": " | ".join(premerge_holders),
                    "premerge_holder_defined": "yes",
                    "premerge_preview": candidate_preview,
                    "suggested_action": action,
                    "confidence": confidence,
                    "reason": reason,
                }
            )
        elif len(undefined_entries) == 1:
            problem_entry = undefined_entries[0]
            affected_key = problem_entry.key
            current_preview = compact_entry(problem_entry)
            same_key_premerge = premerge_groups.get(problem_entry.key, [])
            replacement = next(
                (
                    item
                    for item in same_key_premerge
                    if entry_holder(item) in character_ids
                    and same_except_pair(
                        current_entries,
                        problem_entry,
                        premerge_entries,
                        item,
                    )
                ),
                None,
            )
            if source_match and replacement is not None:
                action = "replace_entry_from_premerge"
                scope = "single_entry"
                confidence = "high"
                manual_resolution = "no"
                candidate_preview = compact_entry(replacement)
                reason = (
                    "The same date has one defined premerge holder, and every "
                    "other direct entry is semantically unchanged."
                )
                edits_by_path[current_path].append(
                    absolute_entry_edit(
                        title_id, current_block, problem_entry, replacement.lines
                    )
                )
                patch_included = "yes"
                review_rows.append(
                    {
                        "title_id": title_id,
                        "entry_key": problem_entry.key,
                        "review_type": "high_confidence_candidate",
                        "current_holder": entry_holder(problem_entry),
                        "current_holder_defined": "no",
                        "current_preview": current_preview,
                        "premerge_holder": entry_holder(replacement),
                        "premerge_holder_defined": "yes",
                        "premerge_preview": candidate_preview,
                        "suggested_action": action,
                        "confidence": confidence,
                        "reason": reason,
                    }
                )
            elif (
                source_match
                and not same_key_premerge
                and counter_without(current_entries, problem_entry)
                == entry_counter(premerge_entries)
            ):
                action = "delete_source_only_undefined_entry"
                scope = "single_entry"
                confidence = "high"
                manual_resolution = "no"
                candidate_preview = "<delete entry>"
                reason = (
                    "The undefined entry exists only in the source/current block; "
                    "removing it makes the direct-entry set match premerge."
                )
                edits_by_path[current_path].append(
                    absolute_entry_edit(title_id, current_block, problem_entry, ())
                )
                patch_included = "yes"
                review_rows.append(
                    {
                        "title_id": title_id,
                        "entry_key": problem_entry.key,
                        "review_type": "high_confidence_candidate",
                        "current_holder": entry_holder(problem_entry),
                        "current_holder_defined": "no",
                        "current_preview": current_preview,
                        "premerge_holder": "",
                        "premerge_holder_defined": "",
                        "premerge_preview": "<entry absent>",
                        "suggested_action": action,
                        "confidence": confidence,
                        "reason": reason,
                    }
                )

        if manual_resolution == "yes":
            for problem_entry in undefined_entries:
                review_rows.append(
                    {
                        "title_id": title_id,
                        "entry_key": problem_entry.key,
                        "review_type": "undefined_current_entry",
                        "current_holder": entry_holder(problem_entry),
                        "current_holder_defined": "no",
                        "current_preview": compact_entry(problem_entry),
                        "premerge_holder": "",
                        "premerge_holder_defined": "",
                        "premerge_preview": "",
                        "suggested_action": "manual_resolve_undefined_holder",
                        "confidence": "low",
                        "reason": "No defined premerge holder exists at the same date.",
                    }
                )
            for premerge_entry in premerge_entries:
                current_peers = current_groups.get(premerge_entry.key, [])
                if any(
                    entry_semantic(peer) == entry_semantic(premerge_entry)
                    for peer in current_peers
                ):
                    continue
                suggested_action = (
                    "manual_review_replace_with_premerge_entry"
                    if current_peers
                    else "manual_review_insert_premerge_entry"
                )
                review_rows.append(
                    {
                        "title_id": title_id,
                        "entry_key": premerge_entry.key,
                        "review_type": "lost_premerge_local_entry",
                        "current_holder": " | ".join(
                            filter(None, (entry_holder(item) for item in current_peers))
                        ),
                        "current_holder_defined": "",
                        "current_preview": " || ".join(
                            compact_entry(item) for item in current_peers
                        ),
                        "premerge_holder": entry_holder(premerge_entry),
                        "premerge_holder_defined": (
                            "yes"
                            if not entry_holder(premerge_entry)
                            or entry_holder(premerge_entry) in character_ids
                            else "no"
                        ),
                        "premerge_preview": compact_entry(premerge_entry),
                        "suggested_action": suggested_action,
                        "confidence": "medium",
                        "reason": (
                            "This local premerge entry is absent or changed in the "
                            "source-matching current block."
                        ),
                    }
                )

        candidate_rows.append(
            {
                "title_id": title_id,
                "history_layer": row["history_layer"],
                "current_path": current_path,
                "current_block_line": str(current_block.start_line),
                "premerge_path": premerge_path,
                "premerge_block_line": str(premerge_block.start_line),
                "source_title_id": source_block.raw_title_id,
                "source_path": source_path,
                "source_block_line": str(source_block.start_line),
                "current_matches_source": "yes" if source_match else "no",
                "current_holder_count": str(len(current_holders)),
                "current_undefined_count": str(len(current_undefined)),
                "current_undefined_holders": " | ".join(current_undefined),
                "premerge_holder_count": str(len(premerge_holders)),
                "premerge_defined_count": str(
                    len(premerge_holders) - len(premerge_undefined)
                ),
                "premerge_undefined_count": str(len(premerge_undefined)),
                "resolution_scope": scope,
                "candidate_action": action,
                "affected_key": affected_key,
                "current_preview": current_preview,
                "candidate_preview": candidate_preview,
                "confidence": confidence,
                "manual_resolution_required": manual_resolution,
                "patch_preview_included": patch_included,
                "reason": reason,
                "current_file_sha256": sha256_file(repo_root / current_path),
            }
        )

    modified_texts = dict(current_texts)
    for path, edits in edits_by_path.items():
        before_lines = current_texts[path].splitlines()
        after_lines = apply_edits(before_lines, edits)
        modified_texts[path] = "\n".join(after_lines) + "\n"

    validation_rows: list[dict[str, str]] = []
    by_title = {row["title_id"]: row for row in candidate_rows}
    for title_id in sorted(by_title):
        candidate = by_title[title_id]
        path = candidate["current_path"]
        before_block = block_for_title(
            "validation_before", path, current_texts[path], title_id
        )
        after_block = block_for_title(
            "validation_after", path, modified_texts[path], title_id
        )
        before_holders = block_holders(before_block)
        after_holders = block_holders(after_block)
        before_undefined = [
            holder for holder in before_holders if holder not in character_ids
        ]
        after_undefined = [
            holder for holder in after_holders if holder not in character_ids
        ]
        validation_rows.append(
            {
                "title_id": title_id,
                "patch_preview_applied": candidate["patch_preview_included"],
                "before_holder_count": str(len(before_holders)),
                "before_undefined_count": str(len(before_undefined)),
                "before_undefined_holders": " | ".join(before_undefined),
                "after_holder_count": str(len(after_holders)),
                "after_undefined_count": str(len(after_undefined)),
                "after_undefined_holders": " | ".join(after_undefined),
                "candidate_block_brace_delta": str(
                    sum(history_merge.line_brace_delta(line) for line in after_block.lines)
                ),
            }
        )

    patch_text = build_patch(current_texts, modified_texts)
    semantic.write_csv(
        output_dir / "title_history_merge_regression_fix_candidates.csv",
        candidate_rows,
    )
    semantic.write_csv(
        output_dir / "title_history_merge_regression_entry_review.csv",
        review_rows,
    )
    semantic.write_csv(
        output_dir / "title_history_merge_regression_preview_validation.csv",
        validation_rows,
    )
    semantic.write_csv(
        output_dir / "title_history_merge_regression_skipped_source_evolution.csv",
        skipped_rows,
    )
    patch_path = output_dir / "title_history_merge_regression_high_confidence.patch"
    with patch_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(patch_text)

    high_count = sum(row["confidence"] == "high" for row in candidate_rows)
    manual_count = sum(
        row["manual_resolution_required"] == "yes" for row in candidate_rows
    )
    summary = [
        "# Title History Merge Regression Fix Candidates",
        "",
        "## Revisions",
        "",
        f"- current Yusseter: `{current_revision}`",
        f"- premerge Yusseter: `{premerge_revision}`",
        f"- merged source: `{source_revision}`",
        "",
        "## Results",
        "",
        f"- regression titles: `{len(candidate_rows)}`",
        f"- high-confidence patch-preview candidates: `{high_count}`",
        f"- manual-resolution titles: `{manual_count}`",
        f"- entry review rows: `{len(review_rows)}`",
        f"- skipped non-regressions: `{len(skipped_rows)}`",
        "",
        "## Candidates",
        "",
        *[
            f"- `{row['title_id']}`: `{row['candidate_action']}` "
            f"({row['confidence']}; manual={row['manual_resolution_required']})"
            for row in candidate_rows
        ],
        *[
            f"- `{row['title_id']}`: skipped "
            f"(`{row['classification']}`; {row['premerge_holder_provenance']})"
            for row in skipped_rows
        ],
        "",
        "## Safety",
        "",
        "- This tool is read-only for live title-history files.",
        "- The patch file is a preview and is not applied automatically.",
        "- Every high-confidence preview is reparsed and checked for undefined holders.",
        "- Manual-resolution rows are excluded from the patch preview.",
        "",
    ]
    (output_dir / "title_history_merge_regression_fix_summary.md").write_text(
        "\n".join(summary), encoding="utf-8"
    )

    print(f"output: {output_dir}")
    print(f"regression titles: {len(candidate_rows)}")
    print(f"high-confidence candidates: {high_count}")
    print(f"manual-resolution titles: {manual_count}")
    print(f"entry review rows: {len(review_rows)}")
    print(f"skipped non-regressions: {len(skipped_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
