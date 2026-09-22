from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import audit_upstream_merge_state as merge_state
import build_landed_title_asil_mod_metadata_transfer_dry_run as landed


TITLE_HISTORY_PATHS = [
    "BookmarksGit/history/titles/00_ASIA_CHINA.txt",
    "BookmarksGit/history/titles/00_ASIA_JAPAN.txt",
    "BookmarksGit/history/titles/00_ASIA_NORTH.txt",
    "BookmarksGit/history/titles/00_ASIA_SOUTH.txt",
    "BookmarksGit/history/titles/z00_ADEVELOPMENT.txt",
]
LANDED_DIR = "BookmarksGit/common/landed_titles"
OUTPUT_DIR = "development/analysis/generated/upstream_merge_audit"
HEADER_RE = re.compile(r"^\s*([hekdcb]_[A-Za-z0-9_'\-]+)\s*=\s*\{")
TITLE_TOKEN_RE = re.compile(r"\b([hekdcb]_[A-Za-z0-9_'\-]+)\b")
CONFLICT_RE = re.compile(r"^(<<<<<<<|=======|>>>>>>>)", re.MULTILINE)


@dataclass(frozen=True)
class HistoryBlock:
    raw_title_id: str
    logical_title_id: str
    path: str
    start_line: int
    end_line: int
    lines: tuple[str, ...]
    exact_key: str
    semantic_key: str

    @property
    def first_line(self) -> str:
        return self.lines[0].strip() if self.lines else ""


@dataclass
class Snapshot:
    label: str
    blocks: dict[str, HistoryBlock]
    block_lists: dict[str, tuple[HistoryBlock, ...]]
    duplicate_counts: Counter[str]
    unmapped_rows: list[dict[str, str]]
    file_block_counts: Counter[str]
    file_brace_deltas: dict[str, int]


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]
    parser = argparse.ArgumentParser(
        description=(
            "Audit the active upstream merge for title-history blocks after "
            "mapping asil-mod title IDs to current Yusseter title IDs."
        )
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


def git_bytes(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def git_stage_text(repo_root: Path, stage: int, path: str) -> str:
    return git_bytes(repo_root, "show", f":{stage}:{path}").decode(
        "utf-8-sig", errors="strict"
    )


def git_revision_text(repo_root: Path, revision: str, path: str) -> str:
    return git_bytes(repo_root, "show", f"{revision}:{path}").decode(
        "utf-8-sig", errors="strict"
    )


def load_three_way_texts(
    repo_root: Path,
    paths: tuple[str, ...],
    base_revision: str = "",
    ours_revision: str = "",
    upstream_revision: str = "",
) -> tuple[dict[int, dict[str, str]], str]:
    revisions = (base_revision, ours_revision, upstream_revision)
    if any(revisions) and not all(revisions):
        raise RuntimeError(
            "--base-revision, --ours-revision, and --upstream-revision "
            "must be supplied together"
        )
    if all(revisions):
        revision_by_stage = {
            1: base_revision,
            2: ours_revision,
            3: upstream_revision,
        }
        return (
            {
                stage: {
                    path: git_revision_text(repo_root, revision, path)
                    for path in paths
                }
                for stage, revision in revision_by_stage.items()
            },
            "explicit_revisions",
        )
    return (
        {
            stage: {
                path: git_stage_text(repo_root, stage, path)
                for path in paths
            }
            for stage in (1, 2, 3)
        },
        "active_merge_stages",
    )


def git_tree_paths(repo_root: Path, revision: str, directory: str) -> list[str]:
    text = git_bytes(
        repo_root, "ls-tree", "-r", "--name-only", revision, directory
    ).decode("utf-8", errors="strict")
    return [line for line in text.splitlines() if line.lower().endswith(".txt")]


def line_brace_delta(line: str) -> int:
    visible = landed.strip_comment(line)
    return visible.count("{") - visible.count("}")


def normalize_exact(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines())


def normalize_semantic(text: str) -> str:
    return "".join(
        re.sub(r"\s+", "", landed.strip_comment(line))
        for line in text.splitlines()
    )


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def collect_working_landed_ids(repo_root: Path) -> set[str]:
    ids: set[str] = set()
    directory = repo_root / LANDED_DIR
    for path in sorted(directory.glob("*.txt")):
        text = path.read_text(encoding="utf-8-sig")
        ids.update(landed.parse_title_blocks(text.splitlines(keepends=True)))
    return ids


def collect_revision_landed_ids(repo_root: Path, revision: str) -> set[str]:
    ids: set[str] = set()
    for path in git_tree_paths(repo_root, revision, LANDED_DIR):
        text = git_revision_text(repo_root, revision, path)
        ids.update(landed.parse_title_blocks(text.splitlines(keepends=True)))
    return ids


def build_title_mapping(
    current_ids: set[str],
    upstream_ids: set[str],
    relation_csv: Path,
) -> tuple[
    dict[str, str],
    dict[str, list[str]],
    dict[str, list[dict[str, str]]],
    Counter[str],
]:
    relation_index = merge_state.load_relation_index(relation_csv)
    decisions = [
        merge_state.resolve_mapping(title_id, relation_index, upstream_ids)
        for title_id in sorted(current_ids)
    ]
    unique, reverse = merge_state.build_unique_upstream_to_current(decisions)
    counts = Counter(decision.status for decision in decisions)

    # If a same-ID title disappeared upstream and has no explicit relation row,
    # the merge base can still be compared safely to the current title.
    for title_id in current_ids:
        if title_id not in relation_index and title_id not in reverse:
            unique[title_id] = title_id
            reverse[title_id] = [title_id]
    return unique, reverse, relation_index, counts


def remap_text(text: str, upstream_to_current: dict[str, str]) -> str:
    return TITLE_TOKEN_RE.sub(
        lambda match: upstream_to_current.get(match.group(1), match.group(1)),
        text,
    )


def parse_file_blocks(
    label: str,
    path: str,
    text: str,
    mapper: Callable[[str], tuple[str, str]],
    token_mapping: dict[str, str],
) -> tuple[list[HistoryBlock], list[dict[str, str]], int]:
    lines = text.splitlines()
    blocks: list[HistoryBlock] = []
    unmapped: list[dict[str, str]] = []
    index = 0
    global_depth = 0

    while index < len(lines):
        visible = landed.strip_comment(lines[index])
        match = HEADER_RE.match(visible) if global_depth == 0 else None
        if not match:
            global_depth += line_brace_delta(lines[index])
            index += 1
            continue

        raw_title_id = match.group(1)
        start = index
        depth = line_brace_delta(lines[index])
        while depth > 0 and index + 1 < len(lines):
            index += 1
            depth += line_brace_delta(lines[index])
        if depth != 0:
            raise RuntimeError(
                f"unterminated title-history block {raw_title_id} in {label}:{path}"
            )

        block_lines = tuple(lines[start : index + 1])
        logical_title_id, mapping_status = mapper(raw_title_id)
        if not logical_title_id:
            unmapped.append(
                {
                    "snapshot": label,
                    "path": path,
                    "line": str(start + 1),
                    "raw_title_id": raw_title_id,
                    "mapping_status": mapping_status,
                    "header": block_lines[0].strip(),
                }
            )
        else:
            canonical = remap_text("\n".join(block_lines), token_mapping)
            if raw_title_id != logical_title_id:
                canonical = re.sub(
                    rf"(?m)^(\s*){re.escape(raw_title_id)}(\s*=\s*\{{)",
                    rf"\1{logical_title_id}\2",
                    canonical,
                    count=1,
                )
            blocks.append(
                HistoryBlock(
                    raw_title_id=raw_title_id,
                    logical_title_id=logical_title_id,
                    path=path,
                    start_line=start + 1,
                    end_line=index + 1,
                    lines=block_lines,
                    exact_key=digest(normalize_exact(canonical)),
                    semantic_key=digest(normalize_semantic(canonical)),
                )
            )
        index += 1

    brace_delta = sum(line_brace_delta(line) for line in lines)
    if brace_delta != 0:
        raise RuntimeError(f"brace delta {brace_delta} in {label}:{path}")
    return blocks, unmapped, brace_delta


def build_snapshot(
    label: str,
    texts: dict[str, str],
    mapper: Callable[[str], tuple[str, str]],
    token_mapping: dict[str, str],
) -> Snapshot:
    found: dict[str, list[HistoryBlock]] = defaultdict(list)
    unmapped_rows: list[dict[str, str]] = []
    file_block_counts: Counter[str] = Counter()
    brace_deltas: dict[str, int] = {}

    for path in sorted(texts):
        parsed, unmapped, brace_delta = parse_file_blocks(
            label, path, texts[path], mapper, token_mapping
        )
        for block in parsed:
            found[block.logical_title_id].append(block)
            file_block_counts[path] += 1
        unmapped_rows.extend(unmapped)
        brace_deltas[path] = brace_delta

    duplicate_counts = Counter(
        {title_id: len(items) for title_id, items in found.items() if len(items) > 1}
    )
    return Snapshot(
        label=label,
        blocks={title_id: items[0] for title_id, items in found.items()},
        block_lists={title_id: tuple(items) for title_id, items in found.items()},
        duplicate_counts=duplicate_counts,
        unmapped_rows=unmapped_rows,
        file_block_counts=file_block_counts,
        file_brace_deltas=brace_deltas,
    )


def block_key(block: HistoryBlock | None, mode: str) -> str:
    if block is None:
        return "<absent>"
    return block.exact_key if mode == "exact" else block.semantic_key


def relation(
    base: HistoryBlock | None,
    ours: HistoryBlock | None,
    upstream: HistoryBlock | None,
    mode: str,
) -> str:
    base_key = block_key(base, mode)
    ours_key = block_key(ours, mode)
    upstream_key = block_key(upstream, mode)

    if base is None:
        if ours is None and upstream is None:
            return "both_absent"
        if ours is not None and upstream is None:
            return "keep_ours_addition"
        if ours is None and upstream is not None:
            return "take_upstream_addition"
        if ours_key == upstream_key:
            return "both_same_addition"
        return "manual_both_added_differently"

    if ours is None and upstream is None:
        return "both_deleted"
    if ours is None:
        if upstream_key == base_key:
            return "keep_ours_deletion"
        return "manual_ours_deleted_upstream_modified"
    if upstream is None:
        if ours_key == base_key:
            return "take_upstream_deletion"
        return "manual_ours_modified_upstream_deleted"
    if ours_key == upstream_key:
        return "both_same"
    if ours_key == base_key:
        return "take_upstream_change"
    if upstream_key == base_key:
        return "keep_ours_change"
    return "manual_both_modified"


def state(block: HistoryBlock | None) -> str:
    return "present" if block else "absent"


def block_field(block: HistoryBlock | None, field: str) -> str:
    if block is None:
        return ""
    value = getattr(block, field)
    return str(value)


def build_rows(
    base: Snapshot,
    ours: Snapshot,
    upstream: Snapshot,
    current_landed_ids: set[str],
) -> list[dict[str, str]]:
    title_ids = sorted(set(base.blocks) | set(ours.blocks) | set(upstream.blocks))
    duplicate_ids = (
        set(base.duplicate_counts)
        | set(ours.duplicate_counts)
        | set(upstream.duplicate_counts)
    )
    rows: list[dict[str, str]] = []
    for title_id in title_ids:
        base_block = base.blocks.get(title_id)
        ours_block = ours.blocks.get(title_id)
        upstream_block = upstream.blocks.get(title_id)
        exact = relation(base_block, ours_block, upstream_block, "exact")
        semantic = relation(base_block, ours_block, upstream_block, "semantic")
        current_landed = title_id in current_landed_ids

        if title_id in duplicate_ids:
            decision = "manual_duplicate_logical_title"
        elif not current_landed and ours_block is not None:
            decision = "manual_current_history_without_landed_title"
        elif not current_landed:
            decision = "ignore_no_current_landed_counterpart"
        elif semantic.startswith("manual_"):
            decision = semantic
        elif exact != semantic:
            decision = f"keep_ours_exact_only_{semantic}"
        else:
            decision = semantic

        rows.append(
            {
                "title_id": title_id,
                "current_landed": "yes" if current_landed else "no",
                "base_state": state(base_block),
                "ours_state": state(ours_block),
                "upstream_state": state(upstream_block),
                "exact_relation": exact,
                "semantic_relation": semantic,
                "decision": decision,
                "base_raw_title_id": block_field(base_block, "raw_title_id"),
                "ours_raw_title_id": block_field(ours_block, "raw_title_id"),
                "upstream_raw_title_id": block_field(upstream_block, "raw_title_id"),
                "base_path": block_field(base_block, "path"),
                "ours_path": block_field(ours_block, "path"),
                "upstream_path": block_field(upstream_block, "path"),
                "base_line": block_field(base_block, "start_line"),
                "ours_line": block_field(ours_block, "start_line"),
                "upstream_line": block_field(upstream_block, "start_line"),
                "base_header": base_block.first_line if base_block else "",
                "ours_header": ours_block.first_line if ours_block else "",
                "upstream_header": upstream_block.first_line if upstream_block else "",
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not fields:
            return
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def block_lines(block: HistoryBlock | None) -> list[str]:
    return list(block.lines) if block else []


def write_manual_diffs(
    path: Path,
    rows: list[dict[str, str]],
    base: Snapshot,
    ours: Snapshot,
    upstream: Snapshot,
) -> None:
    output: list[str] = []
    for row in rows:
        if not row["decision"].startswith("manual_"):
            continue
        title_id = row["title_id"]
        output.extend(
            [
                "=" * 100,
                f"title_id={title_id} decision={row['decision']}",
                f"base={row['base_path']}:{row['base_line']} raw={row['base_raw_title_id']}",
                f"ours={row['ours_path']}:{row['ours_line']} raw={row['ours_raw_title_id']}",
                f"upstream={row['upstream_path']}:{row['upstream_line']} raw={row['upstream_raw_title_id']}",
                "--- base -> ours",
            ]
        )
        output.extend(
            difflib.unified_diff(
                block_lines(base.blocks.get(title_id)),
                block_lines(ours.blocks.get(title_id)),
                fromfile="base",
                tofile="ours",
                lineterm="",
            )
        )
        output.append("--- base -> upstream")
        output.extend(
            difflib.unified_diff(
                block_lines(base.blocks.get(title_id)),
                block_lines(upstream.blocks.get(title_id)),
                fromfile="base",
                tofile="upstream",
                lineterm="",
            )
        )
        output.append("")
    path.write_text("\n".join(output), encoding="utf-8")


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_DIR)

    current_landed_ids = collect_working_landed_ids(repo_root)
    upstream_revision = args.upstream_revision or "MERGE_HEAD"
    upstream_landed_ids = collect_revision_landed_ids(repo_root, upstream_revision)
    unique_mapping, reverse_mapping, relation_index, mapping_counts = build_title_mapping(
        current_landed_ids, upstream_landed_ids, args.relation_csv
    )

    ambiguous_upstream_ids = {
        upstream_id for upstream_id, current_ids in reverse_mapping.items() if len(current_ids) > 1
    }

    def external_mapper(raw_title_id: str) -> tuple[str, str]:
        if raw_title_id in ambiguous_upstream_ids:
            targets = "&".join(sorted(reverse_mapping[raw_title_id]))
            return "", f"ambiguous_reverse_mapping:{targets}"
        current = unique_mapping.get(raw_title_id, "")
        if current:
            return current, "mapped"
        return "", "no_current_landed_counterpart"

    def ours_mapper(raw_title_id: str) -> tuple[str, str]:
        return raw_title_id, "current_identity"

    stage_texts, source_mode = load_three_way_texts(
        repo_root,
        TITLE_HISTORY_PATHS,
        args.base_revision,
        args.ours_revision,
        args.upstream_revision,
    )
    base = build_snapshot(
        "base", stage_texts[1], external_mapper, unique_mapping
    )
    ours = build_snapshot("ours", stage_texts[2], ours_mapper, {})
    upstream = build_snapshot(
        "upstream", stage_texts[3], external_mapper, unique_mapping
    )

    rows = build_rows(base, ours, upstream, current_landed_ids)
    manual_rows = [row for row in rows if row["decision"].startswith("manual_")]
    safe_rows = [
        row
        for row in rows
        if row["decision"]
        in {
            "take_upstream_addition",
            "take_upstream_change",
            "take_upstream_deletion",
        }
    ]
    unmapped_rows = base.unmapped_rows + upstream.unmapped_rows

    write_csv(output_dir / "title_history_block_merge_audit.csv", rows)
    write_csv(output_dir / "title_history_merge_safe_candidates.csv", safe_rows)
    write_csv(output_dir / "title_history_merge_manual_review.csv", manual_rows)
    write_csv(output_dir / "title_history_unmapped_blocks.csv", unmapped_rows)
    write_manual_diffs(
        output_dir / "title_history_merge_manual_semantic_diffs.txt",
        manual_rows,
        base,
        ours,
        upstream,
    )

    decision_counts = Counter(row["decision"] for row in rows)
    summary_lines = [
        "# Title History Upstream Merge Audit",
        "",
        f"- source mode: {source_mode}",
        f"- base revision: {args.base_revision or 'index stage 1'}",
        f"- ours revision: {args.ours_revision or 'index stage 2'}",
        f"- upstream revision: {args.upstream_revision or 'index stage 3'}",
        f"- current landed title IDs: {len(current_landed_ids)}",
        f"- upstream landed title IDs: {len(upstream_landed_ids)}",
        f"- mapped upstream IDs: {len(unique_mapping)}",
        f"- ambiguous reverse mappings: {len(ambiguous_upstream_ids)}",
        f"- logical base blocks: {len(base.blocks)}",
        f"- logical ours blocks: {len(ours.blocks)}",
        f"- logical upstream blocks: {len(upstream.blocks)}",
        f"- safe candidates: {len(safe_rows)}",
        f"- manual review rows: {len(manual_rows)}",
        f"- unmapped raw blocks: {len(unmapped_rows)}",
        "",
        "## Decisions",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(decision_counts.items())],
        "",
        "## Mapping Status",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(mapping_counts.items())],
        "",
        "## File Block Counts",
        "",
    ]
    for path in TITLE_HISTORY_PATHS:
        summary_lines.append(
            f"- `{path}`: base={base.file_block_counts[path]}, "
            f"ours={ours.file_block_counts[path]}, upstream={upstream.file_block_counts[path]}"
        )
    summary_lines.extend(
        [
            "",
            "## Safety",
            "",
            "- This tool is read-only and does not modify title-history files.",
            "- Safe candidates require a unique current landed-title counterpart.",
            "- Duplicate logical titles, ambiguous reverse mappings, and both-modified blocks are not auto-resolved.",
        ]
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "title_history_block_merge_audit_summary.md").write_text(
        "\n".join(summary_lines) + "\n", encoding="utf-8"
    )

    if any(CONFLICT_RE.search(text) for texts in stage_texts.values() for text in texts.values()):
        raise RuntimeError("conflict marker found inside a Git index stage")

    print(f"logical base blocks: {len(base.blocks)}")
    print(f"logical ours blocks: {len(ours.blocks)}")
    print(f"logical upstream blocks: {len(upstream.blocks)}")
    print(f"safe candidates: {len(safe_rows)}")
    print(f"manual review rows: {len(manual_rows)}")
    print(f"unmapped raw blocks: {len(unmapped_rows)}")
    print(f"summary: {output_dir / 'title_history_block_merge_audit_summary.md'}")


if __name__ == "__main__":
    main()
