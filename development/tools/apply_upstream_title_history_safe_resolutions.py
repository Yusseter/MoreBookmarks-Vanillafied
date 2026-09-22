from __future__ import annotations

import argparse
import csv
import hashlib
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import audit_upstream_title_history_delta as delta
import audit_upstream_title_history_merge as broad
import build_landed_title_asil_mod_metadata_transfer_dry_run as landed


OUTPUT_DIR = "development/analysis/generated/upstream_merge_audit"
SAFE_REPORT = "title_history_upstream_delta_safe.csv"
CONFLICT_RE = re.compile(r"^(<<<<<<<|=======|>>>>>>>)", re.MULTILINE)


@dataclass(frozen=True)
class TextFormat:
    newline: str
    bom: bool
    trailing: bool


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]
    parser = argparse.ArgumentParser(
        description="Apply only verified whole-block title-history merge resolutions."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--relation-csv",
        type=Path,
        default=repo_root
        / "development/pipeline_inputs/title_relations/curated_title_relations.csv",
    )
    parser.add_argument("--base-revision")
    parser.add_argument("--ours-revision")
    parser.add_argument("--upstream-revision")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def git_stage_bytes(
    repo_root: Path,
    stage: int,
    path: str,
    revision: str | None = None,
) -> bytes:
    source = f"{revision}:{path}" if revision else f":{stage}:{path}"
    result = subprocess.run(
        ["git", "show", source],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"cannot read {source}: {message}")
    return result.stdout


def decode(data: bytes) -> tuple[str, TextFormat]:
    text = data.decode("utf-8-sig", errors="strict")
    return text, TextFormat(
        newline="\r\n" if b"\r\n" in data else "\n",
        bom=data.startswith(b"\xef\xbb\xbf"),
        trailing=text.endswith(("\r\n", "\n")),
    )


def encode(text: str, fmt: TextFormat) -> bytes:
    data = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + data) if fmt.bom else data


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {str(key).strip(): (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, skipinitialspace=True)
        ]


def remap_active_line(line: str, mapping: dict[str, str]) -> str:
    active = landed.strip_comment(line)
    suffix = line[len(active) :]
    remapped = broad.TITLE_TOKEN_RE.sub(
        lambda match: mapping.get(match.group(1), match.group(1)), active
    )
    return remapped + suffix


def remap_block(
    block: broad.HistoryBlock,
    target_title_id: str,
    mapping: dict[str, str],
) -> tuple[str, ...]:
    lines = [remap_active_line(line, mapping) for line in block.lines]
    active = landed.strip_comment(lines[0])
    suffix = lines[0][len(active) :]
    active = re.sub(
        rf"^(\s*){re.escape(block.raw_title_id)}(\s*=\s*\{{)",
        rf"\1{target_title_id}\2",
        active,
        count=1,
    )
    lines[0] = active + suffix
    return tuple(lines)


def active_title_tokens(lines: tuple[str, ...]) -> set[str]:
    return {
        token
        for line in lines
        for token in broad.TITLE_TOKEN_RE.findall(landed.strip_comment(line))
    }


def keyed_blocks(
    snapshot: broad.Snapshot,
) -> dict[tuple[str, str], list[broad.HistoryBlock]]:
    return delta.layered_blocks(snapshot)


def join_lines(lines: list[str], fmt: TextFormat) -> str:
    text = fmt.newline.join(lines)
    if fmt.trailing:
        text += fmt.newline
    return text


def apply_intervals(
    lines: list[str],
    intervals: list[tuple[int, int, tuple[str, ...], str]],
) -> list[str]:
    result = list(lines)
    previous_start = len(lines) + 1
    for start, end, replacement, label in sorted(intervals, reverse=True):
        if end > previous_start:
            raise RuntimeError(f"overlapping replacement interval: {label}")
        result[start:end] = replacement
        previous_start = start
    return result


def append_block(lines: list[str], block_lines: tuple[str, ...]) -> None:
    while lines and not lines[-1].strip():
        lines.pop()
    if lines:
        lines.append("")
    lines.extend(block_lines)
    lines.append("")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_DIR)
    safe_rows = read_csv(output_dir / SAFE_REPORT)

    current_landed_ids = broad.collect_working_landed_ids(repo_root)
    upstream_revision = args.upstream_revision or "MERGE_HEAD"
    upstream_landed_ids = broad.collect_revision_landed_ids(
        repo_root, upstream_revision
    )
    tokens, by_upstream, by_current, mapping_issues = delta.load_mapping(
        args.relation_csv, current_landed_ids
    )
    if mapping_issues:
        raise RuntimeError(f"mapping parse issues remain: {len(mapping_issues)}")
    unique_token_map = {
        upstream_id: next(iter({token.current_title_id for token in group}))
        for upstream_id, group in by_upstream.items()
        if len({token.current_title_id for token in group}) == 1
    }
    ambiguous_tokens = {
        upstream_id
        for upstream_id, group in by_upstream.items()
        if len({token.current_title_id for token in group}) > 1
    }

    stage_revisions = {
        1: args.base_revision,
        2: args.ours_revision,
        3: args.upstream_revision,
    }
    stage_bytes = {
        stage: {
            path: git_stage_bytes(
                repo_root, stage, path, stage_revisions[stage]
            )
            for path in broad.TITLE_HISTORY_PATHS
        }
        for stage in (1, 2, 3)
    }
    stage_texts = {
        stage: {
            path: data.decode("utf-8-sig", errors="strict")
            for path, data in files.items()
        }
        for stage, files in stage_bytes.items()
    }
    raw_base = broad.build_snapshot(
        "raw_base", stage_texts[1], delta.identity_mapper, {}
    )
    ours = broad.build_snapshot("ours", stage_texts[2], delta.identity_mapper, {})
    raw_upstream = broad.build_snapshot(
        "raw_upstream", stage_texts[3], delta.identity_mapper, {}
    )
    base_layers = keyed_blocks(raw_base)
    upstream_layers = keyed_blocks(raw_upstream)

    intervals: dict[str, list[tuple[int, int, tuple[str, ...], str]]] = defaultdict(list)
    additions: dict[str, list[tuple[tuple[str, ...], str]]] = defaultdict(list)
    report_rows: list[dict[str, str]] = []
    seen_targets: set[tuple[str, str]] = set()

    for row in safe_rows:
        raw_id = row["raw_upstream_title_id"]
        layer = row["history_layer"]
        target = row["current_target"]
        resolution = row["resolution"]
        key = (raw_id, layer)
        base_candidates = base_layers.get(key, [])
        upstream_candidates = upstream_layers.get(key, [])
        ours_candidates = delta.current_layer_blocks(ours, target, layer)
        if len(base_candidates) > 1 or len(upstream_candidates) > 1 or len(ours_candidates) > 1:
            raise RuntimeError(f"candidate became non-unique: {raw_id}/{layer}")
        base_block = base_candidates[0] if base_candidates else None
        upstream_block = upstream_candidates[0] if upstream_candidates else None
        ours_block = ours_candidates[0] if ours_candidates else None

        recalculated, recalculated_target, _donor_count = delta.determine_resolution(
            raw_id,
            row["upstream_change"],
            by_upstream.get(raw_id, []),
            by_current,
            base_block,
            ours_block,
            len(ours_candidates),
            upstream_block,
            unique_token_map,
        )
        if recalculated != resolution or recalculated_target != target:
            raise RuntimeError(
                f"stale safe report for {raw_id}/{layer}: "
                f"report={resolution}/{target}, current={recalculated}/{recalculated_target}"
            )
        target_key = (target, layer)
        if target_key in seen_targets:
            raise RuntimeError(f"multiple safe operations target {target}/{layer}")
        seen_targets.add(target_key)

        replacement = remap_block(upstream_block, target, unique_token_map) if upstream_block else ()
        base_remapped = remap_block(base_block, target, unique_token_map) if base_block else ()
        unresolved_new = sorted(
            token
            for token in active_title_tokens(replacement) - active_title_tokens(base_remapped)
            if token in ambiguous_tokens
            or (token in upstream_landed_ids and token not in current_landed_ids)
        )
        if unresolved_new:
            report_rows.append(
                {
                    **row,
                    "apply_status": "blocked_new_unresolved_title_reference",
                    "detail": "&".join(unresolved_new),
                }
            )
            continue

        if resolution == "safe_replace_whole_block":
            if ours_block is None or upstream_block is None:
                raise RuntimeError(f"missing replacement block for {raw_id}/{layer}")
            intervals[ours_block.path].append(
                (
                    ours_block.start_line - 1,
                    ours_block.end_line,
                    replacement,
                    f"replace {raw_id} -> {target}/{layer}",
                )
            )
        elif resolution == "safe_delete_whole_block":
            if ours_block is None:
                raise RuntimeError(f"missing deletion block for {raw_id}/{layer}")
            intervals[ours_block.path].append(
                (
                    ours_block.start_line - 1,
                    ours_block.end_line,
                    (),
                    f"delete {target}/{layer}",
                )
            )
        elif resolution == "safe_add_whole_block":
            if upstream_block is None:
                raise RuntimeError(f"missing addition block for {raw_id}/{layer}")
            additions[upstream_block.path].append(
                (replacement, f"add {raw_id} -> {target}/{layer}")
            )
        else:
            raise RuntimeError(f"unexpected safe resolution: {resolution}")
        report_rows.append({**row, "apply_status": "planned", "detail": ""})

    expected_bytes: dict[str, bytes] = {}
    for path in broad.TITLE_HISTORY_PATHS:
        text, fmt = decode(stage_bytes[2][path])
        lines = text.splitlines()
        lines = apply_intervals(lines, intervals.get(path, []))
        for block_lines, _label in additions.get(path, []):
            append_block(lines, block_lines)
        expected_text = join_lines(lines, fmt)
        if CONFLICT_RE.search(expected_text):
            raise RuntimeError(f"conflict marker remains in expected {path}")
        if sum(broad.line_brace_delta(line) for line in expected_text.splitlines()) != 0:
            raise RuntimeError(f"brace delta is not zero in expected {path}")
        expected_bytes[path] = encode(expected_text, fmt)

    expected_texts = {
        path: data.decode("utf-8-sig", errors="strict")
        for path, data in expected_bytes.items()
    }
    final_snapshot = broad.build_snapshot(
        "safe_expected", expected_texts, delta.identity_mapper, {}
    )
    if any(final_snapshot.file_brace_deltas.values()):
        raise RuntimeError("non-zero brace delta after safe title-history merge")

    file_rows: list[dict[str, str]] = []
    for path, expected in expected_bytes.items():
        target_path = repo_root / path
        current = target_path.read_bytes()
        status = "already_applied" if current == expected else "needs_apply"
        if args.apply and status == "needs_apply":
            target_path.write_bytes(expected)
            status = "applied"
        file_rows.append(
            {
                "path": path,
                "status": status,
                "expected_sha256": sha256(expected),
                "planned_intervals": str(len(intervals.get(path, []))),
                "planned_additions": str(len(additions.get(path, []))),
            }
        )

    broad.write_csv(output_dir / "title_history_safe_apply_rows.csv", report_rows)
    broad.write_csv(output_dir / "title_history_safe_apply_files.csv", file_rows)
    status_counts = Counter(row["apply_status"] for row in report_rows)
    file_status_counts = Counter(row["status"] for row in file_rows)
    summary = [
        "# Title History Safe Apply Summary",
        "",
        f"- report candidates: {len(safe_rows)}",
        f"- planned safe operations: {status_counts.get('planned', 0)}",
        f"- blocked reference rows: {status_counts.get('blocked_new_unresolved_title_reference', 0)}",
        f"- apply requested: {'yes' if args.apply else 'no'}",
        "",
        "## Row Status",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(status_counts.items())],
        "",
        "## File Status",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(file_status_counts.items())],
    ]
    (output_dir / "title_history_safe_apply_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )

    print(f"report candidates: {len(safe_rows)}")
    print(f"planned safe operations: {status_counts.get('planned', 0)}")
    print(
        "blocked reference rows: "
        f"{status_counts.get('blocked_new_unresolved_title_reference', 0)}"
    )
    print(f"file statuses: {dict(file_status_counts)}")
    print(f"summary: {output_dir / 'title_history_safe_apply_summary.md'}")


if __name__ == "__main__":
    main()
