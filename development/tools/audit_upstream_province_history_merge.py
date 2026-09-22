from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import import_mpe_add_1_history as history_tools


DEFAULT_PATH = "BookmarksGit/history/provinces/00_MB_PROVINCES.txt"
DEFAULT_OUTPUT = "development/analysis/generated/upstream_merge_audit"
HEADER_RE = re.compile(r"^\s*(\d+)\s*=\s*\{")
CONFLICT_RE = re.compile(r"^(<<<<<<<|=======|>>>>>>>)", re.MULTILINE)


@dataclass(frozen=True)
class Block:
    province_id: int
    start_line: int
    end_line: int
    lines: tuple[str, ...]

    @property
    def first_line(self) -> str:
        return self.lines[0].strip() if self.lines else ""

    @property
    def exact_key(self) -> str:
        normalized = "\n".join(line.rstrip() for line in self.lines)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @property
    def semantic_key(self) -> str:
        normalized = "".join(
            re.sub(r"\s+", "", history_tools.strip_comment(line)) for line in self.lines
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class Snapshot:
    label: str
    text: str
    lines: list[str]
    blocks: dict[int, Block]
    block_lists: dict[int, tuple[Block, ...]]
    duplicate_counts: Counter[int]
    brace_delta: int


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]
    parser = argparse.ArgumentParser(
        description="Audit the active Git three-way merge for numeric province-history blocks."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--base-revision", default="")
    parser.add_argument("--ours-revision", default="")
    parser.add_argument("--upstream-revision", default="")
    return parser.parse_args()


def git_stage_text(repo_root: Path, stage: int, relative_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f":{stage}:{relative_path}"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"cannot read stage {stage} for {relative_path}: {message}")
    return result.stdout.decode("utf-8-sig", errors="strict")


def git_revision_text(repo_root: Path, revision: str, relative_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"cannot read revision {revision} for {relative_path}: {message}"
        )
    return result.stdout.decode("utf-8-sig", errors="strict")


def load_three_way_texts(
    repo_root: Path, args: argparse.Namespace
) -> tuple[str, str, str, str]:
    revisions = (
        args.base_revision,
        args.ours_revision,
        args.upstream_revision,
    )
    if any(revisions) and not all(revisions):
        raise RuntimeError(
            "--base-revision, --ours-revision, and --upstream-revision "
            "must be supplied together"
        )
    if all(revisions):
        ours_text = (
            (repo_root / args.path).read_text(encoding="utf-8-sig")
            if args.ours_revision.upper() == "WORKTREE"
            else git_revision_text(repo_root, args.ours_revision, args.path)
        )
        return (
            git_revision_text(repo_root, args.base_revision, args.path),
            ours_text,
            git_revision_text(repo_root, args.upstream_revision, args.path),
            (
                "explicit_revisions_with_worktree_ours"
                if args.ours_revision.upper() == "WORKTREE"
                else "explicit_revisions"
            ),
        )
    return (
        git_stage_text(repo_root, 1, args.path),
        git_stage_text(repo_root, 2, args.path),
        git_stage_text(repo_root, 3, args.path),
        "active_merge_stages",
    )


def line_brace_delta(line: str) -> int:
    visible = history_tools.strip_comment(line)
    return visible.count("{") - visible.count("}")


def parse_snapshot(label: str, text: str) -> Snapshot:
    lines = text.splitlines()
    found: dict[int, list[Block]] = {}
    index = 0
    global_depth = 0
    while index < len(lines):
        visible = history_tools.strip_comment(lines[index])
        match = HEADER_RE.match(visible) if global_depth == 0 else None
        if not match:
            global_depth += line_brace_delta(lines[index])
            index += 1
            continue

        province_id = int(match.group(1))
        start = index
        depth = line_brace_delta(lines[index])
        while depth > 0 and index + 1 < len(lines):
            index += 1
            depth += line_brace_delta(lines[index])
        if depth != 0:
            raise RuntimeError(f"unterminated province block {province_id} in {label}")
        block = Block(
            province_id=province_id,
            start_line=start + 1,
            end_line=index + 1,
            lines=tuple(lines[start : index + 1]),
        )
        found.setdefault(province_id, []).append(block)
        index += 1

    duplicate_counts = Counter(
        {province_id: len(items) for province_id, items in found.items() if len(items) > 1}
    )
    blocks = {province_id: items[0] for province_id, items in found.items()}
    return Snapshot(
        label=label,
        text=text,
        lines=lines,
        blocks=blocks,
        block_lists={province_id: tuple(items) for province_id, items in found.items()},
        duplicate_counts=duplicate_counts,
        brace_delta=sum(line_brace_delta(line) for line in lines),
    )


def key(block: Block | None, mode: str) -> str:
    if block is None:
        return "<absent>"
    return block.exact_key if mode == "exact" else block.semantic_key


def relation(base: Block | None, ours: Block | None, upstream: Block | None, mode: str) -> str:
    b = key(base, mode)
    o = key(ours, mode)
    u = key(upstream, mode)

    if base is None:
        if ours is None and upstream is None:
            return "both_absent"
        if ours is not None and upstream is None:
            return "keep_ours_addition"
        if ours is None and upstream is not None:
            return "take_upstream_addition"
        if o == u:
            return "both_same_addition"
        return "manual_both_added_differently"

    if ours is None and upstream is None:
        return "both_deleted"
    if ours is None:
        if u == b:
            return "keep_ours_deletion"
        return "manual_ours_deleted_upstream_modified"
    if upstream is None:
        if o == b:
            return "take_upstream_deletion"
        return "manual_ours_modified_upstream_deleted"
    if o == u:
        return "both_same"
    if o == b:
        return "take_upstream_change"
    if u == b:
        return "keep_ours_change"
    return "manual_both_modified"


def state(block: Block | None) -> str:
    return "present" if block else "absent"


def build_rows(base: Snapshot, ours: Snapshot, upstream: Snapshot) -> list[dict[str, str]]:
    ids = sorted(set(base.blocks) | set(ours.blocks) | set(upstream.blocks))
    rows: list[dict[str, str]] = []
    duplicate_ids = set(base.duplicate_counts) | set(ours.duplicate_counts) | set(upstream.duplicate_counts)
    for province_id in ids:
        b = base.blocks.get(province_id)
        o = ours.blocks.get(province_id)
        u = upstream.blocks.get(province_id)
        exact = relation(b, o, u, "exact")
        semantic = relation(b, o, u, "semantic")
        if province_id in duplicate_ids:
            decision = "manual_duplicate_id"
        elif semantic.startswith("manual_"):
            decision = semantic
        elif exact != semantic:
            decision = f"review_exact_diff_semantic_{semantic}"
        else:
            decision = semantic
        rows.append(
            {
                "province_id": str(province_id),
                "base_state": state(b),
                "ours_state": state(o),
                "upstream_state": state(u),
                "exact_relation": exact,
                "semantic_relation": semantic,
                "decision": decision,
                "base_line": str(b.start_line if b else ""),
                "ours_line": str(o.start_line if o else ""),
                "upstream_line": str(u.start_line if u else ""),
                "base_header": b.first_line if b else "",
                "ours_header": o.first_line if o else "",
                "upstream_header": u.first_line if u else "",
            }
        )
    return rows


def block_key_counter(snapshot: Snapshot, province_id: int, mode: str) -> Counter[str]:
    return Counter(key(block, mode) for block in snapshot.block_lists.get(province_id, ()))


def format_counter(values: Counter[str]) -> str:
    return " | ".join(f"{digest[:12]}:{count}" for digest, count in sorted(values.items()))


def build_duplicate_rows(
    base: Snapshot, ours: Snapshot, upstream: Snapshot
) -> list[dict[str, str]]:
    ids = sorted(
        set(base.duplicate_counts) | set(ours.duplicate_counts) | set(upstream.duplicate_counts)
    )
    rows: list[dict[str, str]] = []
    for province_id in ids:
        base_semantic = block_key_counter(base, province_id, "semantic")
        ours_semantic = block_key_counter(ours, province_id, "semantic")
        upstream_semantic = block_key_counter(upstream, province_id, "semantic")
        rows.append(
            {
                "province_id": str(province_id),
                "base_count": str(len(base.block_lists.get(province_id, ()))),
                "ours_count": str(len(ours.block_lists.get(province_id, ()))),
                "upstream_count": str(len(upstream.block_lists.get(province_id, ()))),
                "base_vs_upstream_semantic": (
                    "same" if base_semantic == upstream_semantic else "changed"
                ),
                "ours_matches_base_instance": "yes" if bool(ours_semantic & base_semantic) else "no",
                "ours_matches_upstream_instance": (
                    "yes" if bool(ours_semantic & upstream_semantic) else "no"
                ),
                "base_semantic_keys": format_counter(base_semantic),
                "ours_semantic_keys": format_counter(ours_semantic),
                "upstream_semantic_keys": format_counter(upstream_semantic),
                "base_headers": " | ".join(
                    block.first_line for block in base.block_lists.get(province_id, ())
                ),
                "ours_headers": " | ".join(
                    block.first_line for block in ours.block_lists.get(province_id, ())
                ),
                "upstream_headers": " | ".join(
                    block.first_line for block in upstream.block_lists.get(province_id, ())
                ),
            }
        )
    return rows


def write_dynamic_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "province_id",
        "base_state",
        "ours_state",
        "upstream_state",
        "exact_relation",
        "semantic_relation",
        "decision",
        "base_line",
        "ours_line",
        "upstream_line",
        "base_header",
        "ours_header",
        "upstream_header",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
def block_lines(block: Block | None) -> list[str]:
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
        province_id = int(row["province_id"])
        output.extend(
            [
                "=" * 100,
                f"province_id={province_id} decision={row['decision']}",
                f"base_duplicates={base.duplicate_counts.get(province_id, 0)}",
                f"ours_duplicates={ours.duplicate_counts.get(province_id, 0)}",
                f"upstream_duplicates={upstream.duplicate_counts.get(province_id, 0)}",
                "--- base -> ours",
            ]
        )
        output.extend(
            difflib.unified_diff(
                block_lines(base.blocks.get(province_id)),
                block_lines(ours.blocks.get(province_id)),
                fromfile="base",
                tofile="ours",
                lineterm="",
            )
        )
        output.append("--- base -> upstream")
        output.extend(
            difflib.unified_diff(
                block_lines(base.blocks.get(province_id)),
                block_lines(upstream.blocks.get(province_id)),
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
    output_dir = args.output_dir or (repo_root / DEFAULT_OUTPUT)
    base_text, ours_text, upstream_text, source_mode = load_three_way_texts(
        repo_root, args
    )
    base = parse_snapshot("base", base_text)
    ours = parse_snapshot("ours", ours_text)
    upstream = parse_snapshot("upstream", upstream_text)
    working_text = (repo_root / args.path).read_text(encoding="utf-8-sig")
    rows = build_rows(base, ours, upstream)
    manual_rows = [row for row in rows if row["decision"].startswith(("manual_", "review_"))]
    duplicate_rows = build_duplicate_rows(base, ours, upstream)

    write_csv(output_dir / "province_history_block_merge_audit.csv", rows)
    write_csv(output_dir / "province_history_block_merge_manual_review.csv", manual_rows)
    write_dynamic_csv(
        output_dir / "province_history_duplicate_stage_comparison.csv", duplicate_rows
    )
    write_manual_diffs(
        output_dir / "province_history_block_merge_manual_semantic_diffs.txt",
        manual_rows,
        base,
        ours,
        upstream,
    )


    counts = Counter(row["decision"] for row in rows)
    summary = [
        "# Province History Upstream Merge Audit",
        "",
        f"- path: `{args.path}`",
        f"- source mode: `{source_mode}`",
        f"- base revision: `{args.base_revision or 'index stage 1'}`",
        f"- ours revision: `{args.ours_revision or 'index stage 2'}`",
        f"- upstream revision: `{args.upstream_revision or 'index stage 3'}`",
        f"- base blocks: `{len(base.blocks)}`",
        f"- ours blocks: `{len(ours.blocks)}`",
        f"- upstream blocks: `{len(upstream.blocks)}`",
        f"- working conflict markers: `{len(CONFLICT_RE.findall(working_text))}`",
        f"- manual/review rows: `{len(manual_rows)}`",
        f"- base duplicate ids: `{len(base.duplicate_counts)}`",
        f"- ours duplicate ids: `{len(ours.duplicate_counts)}`",
        f"- upstream duplicate ids: `{len(upstream.duplicate_counts)}`",
        f"- stage brace deltas: `base={base.brace_delta}, ours={ours.brace_delta}, upstream={upstream.brace_delta}`",
        "",
        "## Decision Counts",
    ]
    summary.extend(f"- `{name}`: {count}" for name, count in sorted(counts.items()))
    summary.append("")
    (output_dir / "province_history_block_merge_audit_summary.md").write_text(
        "\n".join(summary), encoding="utf-8"
    )
    print("\n".join(summary))


if __name__ == "__main__":
    main()
