from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import audit_upstream_province_history_merge as audit


RELATIVE_PATH = "BookmarksGit/history/provinces/00_MB_PROVINCES.txt"
SOURCE_IDENTITY_PATH = (
    ".codex/works/analysis/generated/landed_titles_source_audit/"
    "county_source_province_detail.csv"
)
OUTPUT_DIR = ".codex/works/analysis/generated/upstream_merge_audit"
DEFAULT_BASE_REVISION = "35211ffab5d658e2b0074ef1042fe178a7a85430"
DEFAULT_OURS_REVISION = "09588cbb5212a31bc4a373b6990b2c4da1203a35"
DEFAULT_UPSTREAM_REVISION = "99493c7e88615d3f4001e1f85d5d47de7830a060"
EAST_SOURCES = {"vanilla_east", "both_masks"}


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]
    parser = argparse.ArgumentParser(
        description="Apply verified safe upstream changes to 00_MB_PROVINCES.txt."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--base-revision", default=DEFAULT_BASE_REVISION)
    parser.add_argument("--ours-revision", default=DEFAULT_OURS_REVISION)
    parser.add_argument("--upstream-revision", default=DEFAULT_UPSTREAM_REVISION)
    parser.add_argument("--output-dir", type=Path, default=Path(OUTPUT_DIR))
    parser.add_argument("--write-resolved-copy", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def git_revision_bytes(repo_root: Path, revision: str) -> bytes:
    if revision.upper() == "WORKTREE":
        return (repo_root / RELATIVE_PATH).read_bytes()
    result = subprocess.run(
        ["git", "show", f"{revision}:{RELATIVE_PATH}"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"cannot read {revision}:{RELATIVE_PATH}: {message}")
    return result.stdout


def decode_blob(data: bytes) -> tuple[str, str, bool, bool]:
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig", errors="strict")
    newline = "\r\n" if b"\r\n" in data else "\n"
    trailing = text.endswith(("\r\n", "\n"))
    return text, newline, bom, trailing


def encode_blob(text: str, bom: bool) -> bytes:
    data = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + data) if bom else data


def read_source_lookup(path: Path) -> dict[int, list[dict[str, str]]]:
    lookup: dict[int, list[dict[str, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            lookup[int(row["province_id"])].append(row)
    return lookup


def sources_for(lookup: dict[int, list[dict[str, str]]], province_id: int) -> set[str]:
    return {row["province_source"] for row in lookup.get(province_id, []) if row["province_source"]}


def read_alternate_history_sources(repo_root: Path) -> dict[int, tuple[str, ...]]:
    history_dir = repo_root / "BookmarksGit/history/provinces"
    target_path = (repo_root / RELATIVE_PATH).resolve()
    lookup: dict[int, set[str]] = defaultdict(set)
    for path in sorted(history_dir.glob("*.txt")):
        if path.resolve() == target_path:
            continue
        relative_path = path.relative_to(repo_root).as_posix()
        snapshot = audit.parse_snapshot(
            relative_path, path.read_text(encoding="utf-8-sig")
        )
        for province_id in snapshot.blocks:
            lookup[province_id].add(relative_path)
    return {
        province_id: tuple(sorted(paths))
        for province_id, paths in lookup.items()
    }


def semantic_counter(snapshot: audit.Snapshot, province_id: int) -> Counter[str]:
    return Counter(
        block.semantic_key for block in snapshot.block_lists.get(province_id, ())
    )


def classify_resolution(
    row: dict[str, str],
    source_lookup: dict[int, list[dict[str, str]]],
    base: audit.Snapshot,
    ours: audit.Snapshot,
    upstream: audit.Snapshot,
    alternate_history_sources: dict[int, tuple[str, ...]],
) -> tuple[str, str]:
    province_id = int(row["province_id"])
    decision = row["decision"]
    sources = sources_for(source_lookup, province_id)

    if decision in {
        "take_upstream_change",
        "review_exact_diff_semantic_take_upstream_change",
    }:
        if sources == {"mod_kalan"}:
            return (
                "apply_upstream_block",
                "current semantics equal base; live source is mod_kalan",
            )
        if sources and sources.issubset(EAST_SOURCES):
            return (
                "keep_current_custom_east",
                "upstream changed a province governed by the custom east source",
            )
        raise RuntimeError(
            f"upstream candidate {province_id} has unexpected sources: {sorted(sources)}"
        )

    if decision in {"manual_both_modified", "manual_both_added_differently"}:
        if not sources or not sources.issubset(EAST_SOURCES):
            raise RuntimeError(
                f"manual east collision {province_id} has unexpected sources: {sorted(sources)}"
            )
        return "keep_current_custom_east", "live province comes from custom east source"

    if decision == "manual_ours_deleted_upstream_modified":
        if not sources:
            return "keep_current_deletion", "province id has no live landed source"
        alternate_files = alternate_history_sources.get(province_id, ())
        if sources == {"final_only_unclassified"} and alternate_files:
            return (
                "keep_current_relocated_history",
                "current history is supplied by " + "|".join(alternate_files),
            )
        raise RuntimeError(
            f"deleted upstream-modified province {province_id} still has live source "
            f"{sorted(sources)} without alternate current history"
        )

    if decision == "manual_duplicate_id":
        if ours.duplicate_counts.get(province_id):
            raise RuntimeError(f"ours still contains duplicate province id {province_id}")
        if sources == {"mod_kalan"} and semantic_counter(base, province_id) != semantic_counter(
            upstream, province_id
        ):
            raise RuntimeError(
                f"mod_kalan duplicate {province_id} changed upstream and needs explicit review"
            )
        return "keep_current_duplicate_cleanup", "current side already resolves inherited duplicates"

    if decision.startswith("review_exact_diff_semantic_"):
        return "keep_current_comment_format", "semantic content agrees; preserve current comments/format"

    if decision in {
        "both_same",
        "both_deleted",
        "both_same_addition",
        "keep_ours_addition",
        "keep_ours_change",
        "keep_ours_deletion",
    }:
        return "keep_current_standard", "standard three-way merge keeps current side"

    raise RuntimeError(f"unsupported merge decision for {province_id}: {decision}")


def build_expected_text(
    ours: audit.Snapshot,
    upstream: audit.Snapshot,
    candidate_ids: list[int],
    newline: str,
    trailing: bool,
) -> str:
    lines = list(ours.lines)
    replacements: list[tuple[int, int, tuple[str, ...], int]] = []
    for province_id in candidate_ids:
        ours_items = ours.block_lists.get(province_id, ())
        upstream_items = upstream.block_lists.get(province_id, ())
        if len(ours_items) != 1 or len(upstream_items) != 1:
            raise RuntimeError(
                f"candidate {province_id} is not unique: ours={len(ours_items)}, upstream={len(upstream_items)}"
            )
        old = ours_items[0]
        replacements.append((old.start_line - 1, old.end_line, upstream_items[0].lines, province_id))

    for start, end, replacement, _province_id in sorted(replacements, reverse=True):
        lines[start:end] = replacement

    text = newline.join(lines)
    if trailing:
        text += newline
    return text


def validate_expected(
    expected: audit.Snapshot,
    ours: audit.Snapshot,
    upstream: audit.Snapshot,
    candidate_ids: set[int],
) -> None:
    if expected.brace_delta != 0:
        raise RuntimeError(f"expected output brace delta is {expected.brace_delta}")
    if expected.duplicate_counts:
        raise RuntimeError(f"expected output has duplicate ids: {dict(expected.duplicate_counts)}")
    if audit.CONFLICT_RE.search(expected.text):
        raise RuntimeError("expected output contains conflict markers")
    if set(expected.blocks) != set(ours.blocks):
        missing = sorted(set(ours.blocks) - set(expected.blocks))
        added = sorted(set(expected.blocks) - set(ours.blocks))
        raise RuntimeError(f"province id inventory changed: missing={missing}, added={added}")

    for province_id, block in expected.blocks.items():
        reference = upstream.blocks[province_id] if province_id in candidate_ids else ours.blocks[province_id]
        if block.exact_key != reference.exact_key:
            raise RuntimeError(f"final block mismatch for province {province_id}")


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    target_path = repo_root / RELATIVE_PATH
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    base_bytes = git_revision_bytes(repo_root, args.base_revision)
    ours_bytes = git_revision_bytes(repo_root, args.ours_revision)
    upstream_bytes = git_revision_bytes(repo_root, args.upstream_revision)
    base_text, _base_newline, _base_bom, _base_trailing = decode_blob(base_bytes)
    ours_text, newline, bom, trailing = decode_blob(ours_bytes)
    upstream_text, _upstream_newline, _upstream_bom, _upstream_trailing = decode_blob(
        upstream_bytes
    )

    base = audit.parse_snapshot("base", base_text)
    ours = audit.parse_snapshot("ours", ours_text)
    upstream = audit.parse_snapshot("upstream", upstream_text)
    rows = audit.build_rows(base, ours, upstream)
    source_lookup = read_source_lookup(repo_root / SOURCE_IDENTITY_PATH)
    alternate_history_sources = read_alternate_history_sources(repo_root)

    resolved_rows: list[dict[str, str]] = []
    candidate_ids: list[int] = []
    resolution_counts: Counter[str] = Counter()
    for row in rows:
        resolution, reason = classify_resolution(
            row,
            source_lookup,
            base,
            ours,
            upstream,
            alternate_history_sources,
        )
        province_id = int(row["province_id"])
        if resolution == "apply_upstream_block":
            candidate_ids.append(province_id)
        resolution_counts[resolution] += 1
        resolved_rows.append(
            {
                **row,
                "current_sources": "|".join(sorted(sources_for(source_lookup, province_id))),
                "alternate_history_files": "|".join(
                    alternate_history_sources.get(province_id, ())
                ),
                "resolution": resolution,
                "reason": reason,
            }
        )

    expected_text = build_expected_text(ours, upstream, candidate_ids, newline, trailing)
    expected = audit.parse_snapshot("expected", expected_text)
    validate_expected(expected, ours, upstream, set(candidate_ids))

    current_bytes = target_path.read_bytes()
    expected_bytes = encode_blob(expected_text, bom)
    resolved_copy_path = args.write_resolved_copy
    if resolved_copy_path is not None:
        if not resolved_copy_path.is_absolute():
            resolved_copy_path = repo_root / resolved_copy_path
        resolved_copy_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_copy_path.write_bytes(expected_bytes)
    current_status = "already_applied" if current_bytes == expected_bytes else "needs_apply"
    if args.apply and current_status == "needs_apply":
        target_path.write_bytes(expected_bytes)
        current_status = "applied"

    candidate_rows = []
    for province_id in candidate_ids:
        old = ours.blocks[province_id]
        new = upstream.blocks[province_id]
        candidate_rows.append(
            {
                "province_id": str(province_id),
                "ours_line": str(old.start_line),
                "upstream_line": str(new.start_line),
                "ours_header": old.first_line,
                "upstream_header": new.first_line,
                "ours_lines": str(len(old.lines)),
                "upstream_lines": str(len(new.lines)),
                "status": "apply_upstream_block",
            }
        )

    resolved_fields = list(resolved_rows[0])
    write_csv(
        output_dir / "province_history_merge_resolved.csv", resolved_rows, resolved_fields
    )
    write_csv(
        output_dir / "province_history_merge_requires_user_decision.csv", [], resolved_fields
    )
    write_csv(
        output_dir / "province_history_safe_apply_candidates.csv",
        candidate_rows,
        [
            "province_id",
            "ours_line",
            "upstream_line",
            "ours_header",
            "upstream_header",
            "ours_lines",
            "upstream_lines",
            "status",
        ],
    )

    summary = [
        "# Province History Safe Resolution Apply",
        "",
        f"- mode: `{'apply' if args.apply else 'dry-run'}`",
        f"- target status: `{current_status}`",
        f"- safe upstream blocks: `{len(candidate_ids)}`",
        "- user decisions required: `0`",
        f"- final unique blocks: `{len(expected.blocks)}`",
        "- final duplicate ids: `0`",
        "- final conflict markers: `0`",
        "- final brace delta: `0`",
        f"- expected sha256: `{hashlib.sha256(expected_bytes).hexdigest()}`",
        f"- resolved copy: `{resolved_copy_path or 'not_written'}`",
        "",
        "## Resolution Counts",
    ]
    summary.extend(f"- `{name}`: {count}" for name, count in sorted(resolution_counts.items()))
    summary.append("")
    (output_dir / "province_history_safe_resolution_summary.md").write_text(
        "\n".join(summary), encoding="utf-8"
    )
    print("\n".join(summary))


if __name__ == "__main__":
    main()
