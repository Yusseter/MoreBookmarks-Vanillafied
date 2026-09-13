from __future__ import annotations

import argparse
import csv
import hashlib
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import audit_upstream_province_history_merge as audit


BASE_REVISION = "35211ffab5d658e2b0074ef1042fe178a7a85430"
OURS_REVISION = "09588cbb5212a31bc4a373b6990b2c4da1203a35"
UPSTREAM_REVISION = "99493c7e88615d3f4001e1f85d5d47de7830a060"
OLD_PATHS = [
    "BookmarksGit/history/characters/00_SINOSPHERE_1.txt",
    "BookmarksGit/history/characters/00_SINOSPHERE_2.txt",
]
SINOSPHERE_PATH = "BookmarksGit/history/characters/00_ASIA_SINOSPHERE.txt"
INDOSPHERE_PATH = "BookmarksGit/history/characters/00_ASIA_INDOSPHERE.txt"
OUTPUT_DIR = ".codex/works/analysis/generated/upstream_merge_audit"

OURS_ONLY_IDS = {1400824, 1401460, 1403279, 1404569, 1406381}
BOTH_MODIFIED_REPLACEMENTS = {
    217722: {
        "title:d_youzhou_china": "title:d_youzhou",
        "title:d_yunzhong_china": "title:d_yunshuo",
        "title:k_yan_china": "title:k_youji",
        "title:k_yue_china": "title:k_liangzhe",
        "title:k_jin_china": "title:k_hedong",
        "title:d_fujian_china": "title:d_weiwu",
    },
    217728: {
        "title:d_youzhou_china": "title:d_youzhou",
        "title:d_yunzhong_china": "title:d_yunshuo",
        "title:k_yan_china": "title:k_youji",
    },
    1401283: {
        "title:d_huaixi_china": "title:d_huaixi",
        "title:d_huainan_china": "title:d_huainan",
    },
}
MOVED_OR_REPLACED_IDS = {421011, 1403799}
EXPECTED_RELATION_COUNTS = {
    "both_same": 5213,
    "keep_ours_change": 5,
    "manual_both_modified": 3,
    "manual_ours_modified_upstream_deleted": 2,
    "take_upstream_addition": 4969,
    "take_upstream_change": 1541,
    "take_upstream_deletion": 1600,
}


@dataclass(frozen=True)
class TextFormat:
    newline: str
    bom: bool
    trailing: bool


@dataclass(frozen=True)
class TextBlock:
    key: str
    start: int
    end: int
    lines: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]
    parser = argparse.ArgumentParser(
        description="Merge Yusseter SINOSPHERE character edits into upstream combined files."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def git_bytes(repo_root: Path, revision: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"cannot read {revision}:{relative_path}: {message}")
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


def combined_old_text(repo_root: Path, revision: str) -> str:
    parts = [git_bytes(repo_root, revision, path).decode("utf-8-sig") for path in OLD_PATHS]
    return "\n".join(part.rstrip("\r\n") for part in parts) + "\n"


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def find_block(lines: list[str], key: str) -> TextBlock:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*\{{")
    depth = 0
    found: list[TextBlock] = []
    index = 0
    while index < len(lines):
        visible = strip_comment(lines[index])
        match = pattern.match(visible) if depth == 0 else None
        if not match:
            depth += visible.count("{") - visible.count("}")
            index += 1
            continue
        start = index
        local_depth = visible.count("{") - visible.count("}")
        while local_depth > 0 and index + 1 < len(lines):
            index += 1
            visible = strip_comment(lines[index])
            local_depth += visible.count("{") - visible.count("}")
        if local_depth != 0:
            raise RuntimeError(f"unterminated block {key}")
        found.append(TextBlock(key, start, index + 1, tuple(lines[start : index + 1])))
        index += 1
    if len(found) != 1:
        raise RuntimeError(f"expected one block for {key}, found {len(found)}")
    return found[0]


def replace_tokens(lines: tuple[str, ...], replacements: dict[str, str], label: str) -> tuple[str, ...]:
    text = "\n".join(lines)
    for old, new in replacements.items():
        old_count = len(re.findall(rf"\b{re.escape(old)}\b", text))
        if old_count != 1:
            raise RuntimeError(f"{label}: expected one {old}, found {old_count}")
        if re.search(rf"\b{re.escape(new)}\b", text):
            raise RuntimeError(f"{label}: replacement token already exists: {new}")
        text = re.sub(rf"\b{re.escape(old)}\b", new, text, count=1)
    return tuple(text.split("\n"))


def apply_intervals(lines: list[str], intervals: list[tuple[int, int, tuple[str, ...], str]]) -> list[str]:
    result = list(lines)
    previous_start = len(lines) + 1
    for start, end, replacement, label in sorted(intervals, reverse=True):
        if end > previous_start:
            raise RuntimeError(f"overlapping replacement interval: {label}")
        result[start:end] = replacement
        previous_start = start
    return result


def join_lines(lines: list[str], fmt: TextFormat) -> str:
    text = fmt.newline.join(lines)
    if fmt.trailing:
        text += fmt.newline
    return text


def build_sinosphere(
    ours: audit.Snapshot,
    upstream: audit.Snapshot,
    upstream_text: str,
    fmt: TextFormat,
) -> str:
    lines = upstream_text.splitlines()
    intervals: list[tuple[int, int, tuple[str, ...], str]] = []

    for character_id in sorted(OURS_ONLY_IDS):
        source = ours.blocks[character_id]
        target = upstream.blocks[character_id]
        intervals.append(
            (target.start_line - 1, target.end_line, source.lines, f"ours-only {character_id}")
        )

    for character_id, replacements in BOTH_MODIFIED_REPLACEMENTS.items():
        target = upstream.blocks[character_id]
        merged = replace_tokens(target.lines, replacements, f"character {character_id}")
        intervals.append(
            (target.start_line - 1, target.end_line, merged, f"both-modified {character_id}")
        )

    huang = find_block(lines, "bookmark_huang_chao")
    merged_huang = replace_tokens(
        huang.lines,
        {"title:d_chenxu_china": "title:d_chenxu"},
        "bookmark_huang_chao",
    )
    intervals.append((huang.start, huang.end, merged_huang, "bookmark_huang_chao"))
    return join_lines(apply_intervals(lines, intervals), fmt)


def build_indosphere(upstream_text: str, fmt: TextFormat) -> str:
    lines = upstream_text.splitlines()
    character = find_block(lines, "421011")
    merged = replace_tokens(
        character.lines,
        {"title:c_con_linh": "title:c_binh_nguyen"},
        "character 421011",
    )
    return join_lines(
        apply_intervals(lines, [(character.start, character.end, merged, "character 421011")]),
        fmt,
    )


def assert_token_state(text: str, old: str, new: str, label: str) -> None:
    if re.search(rf"\b{re.escape(old)}\b", text):
        raise RuntimeError(f"{label}: old token remains: {old}")
    if not re.search(rf"\b{re.escape(new)}\b", text):
        raise RuntimeError(f"{label}: new token missing: {new}")


def validate(
    sinosphere_text: str,
    indosphere_text: str,
    ours: audit.Snapshot,
    upstream: audit.Snapshot,
) -> None:
    final = audit.parse_snapshot("final_sinosphere", sinosphere_text)
    if final.brace_delta != 0 or final.duplicate_counts:
        raise RuntimeError(
            f"invalid final Sinosphere: brace={final.brace_delta}, duplicates={dict(final.duplicate_counts)}"
        )
    if audit.CONFLICT_RE.search(sinosphere_text) or audit.CONFLICT_RE.search(indosphere_text):
        raise RuntimeError("conflict marker found in merged character files")
    if set(final.blocks) != set(upstream.blocks):
        raise RuntimeError("numeric character inventory differs from upstream combined file")

    for character_id in OURS_ONLY_IDS:
        if final.blocks[character_id].exact_key != ours.blocks[character_id].exact_key:
            raise RuntimeError(f"ours-only character block mismatch: {character_id}")

    for character_id, replacements in BOTH_MODIFIED_REPLACEMENTS.items():
        block_text = "\n".join(final.blocks[character_id].lines)
        for old, new in replacements.items():
            assert_token_state(block_text, old, new, f"character {character_id}")

    huang = find_block(sinosphere_text.splitlines(), "bookmark_huang_chao")
    assert_token_state(
        "\n".join(huang.lines),
        "title:d_chenxu_china",
        "title:d_chenxu",
        "bookmark_huang_chao",
    )
    if re.search(r"^\s*1403799\s*=\s*\{", sinosphere_text, re.MULTILINE):
        raise RuntimeError("obsolete numeric Huang Chao definition remains")

    moved = find_block(indosphere_text.splitlines(), "421011")
    assert_token_state(
        "\n".join(moved.lines),
        "title:c_con_linh",
        "title:c_binh_nguyen",
        "character 421011",
    )
    if sum(strip_comment(line).count("{") - strip_comment(line).count("}") for line in indosphere_text.splitlines()) != 0:
        raise RuntimeError("Indosphere brace delta is not zero")


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = repo_root / OUTPUT_DIR

    base = audit.parse_snapshot("base", combined_old_text(repo_root, BASE_REVISION))
    ours = audit.parse_snapshot("ours", combined_old_text(repo_root, OURS_REVISION))
    upstream_bytes = git_bytes(repo_root, UPSTREAM_REVISION, SINOSPHERE_PATH)
    upstream_text, sinosphere_fmt = decode(upstream_bytes)
    upstream = audit.parse_snapshot("upstream", upstream_text)
    indosphere_bytes = git_bytes(repo_root, UPSTREAM_REVISION, INDOSPHERE_PATH)
    indosphere_text, indosphere_fmt = decode(indosphere_bytes)

    rows = audit.build_rows(base, ours, upstream)
    counts = Counter(row["decision"] for row in rows)
    if dict(counts) != EXPECTED_RELATION_COUNTS:
        raise RuntimeError(f"unexpected relation counts: {dict(counts)}")
    if {int(row["province_id"]) for row in rows if row["decision"] == "keep_ours_change"} != OURS_ONLY_IDS:
        raise RuntimeError("ours-only character ID set changed")
    if {
        int(row["province_id"])
        for row in rows
        if row["decision"] == "manual_both_modified"
    } != set(BOTH_MODIFIED_REPLACEMENTS):
        raise RuntimeError("both-modified character ID set changed")
    if {
        int(row["province_id"])
        for row in rows
        if row["decision"] == "manual_ours_modified_upstream_deleted"
    } != MOVED_OR_REPLACED_IDS:
        raise RuntimeError("moved/replaced character ID set changed")

    expected_sinosphere = build_sinosphere(ours, upstream, upstream_text, sinosphere_fmt)
    expected_indosphere = build_indosphere(indosphere_text, indosphere_fmt)
    validate(expected_sinosphere, expected_indosphere, ours, upstream)

    target_sinosphere = repo_root / SINOSPHERE_PATH
    target_indosphere = repo_root / INDOSPHERE_PATH
    expected_sinosphere_bytes = encode(expected_sinosphere, sinosphere_fmt)
    expected_indosphere_bytes = encode(expected_indosphere, indosphere_fmt)
    sinosphere_status = (
        "already_applied"
        if target_sinosphere.read_bytes() == expected_sinosphere_bytes
        else "needs_apply"
    )
    indosphere_status = (
        "already_applied"
        if target_indosphere.read_bytes() == expected_indosphere_bytes
        else "needs_apply"
    )
    if args.apply:
        if sinosphere_status == "needs_apply":
            target_sinosphere.write_bytes(expected_sinosphere_bytes)
            sinosphere_status = "applied"
        if indosphere_status == "needs_apply":
            target_indosphere.write_bytes(expected_indosphere_bytes)
            indosphere_status = "applied"

    resolved_rows: list[dict[str, str]] = []
    for row in rows:
        decision = row["decision"]
        character_id = int(row["province_id"])
        if decision == "keep_ours_change":
            resolution = "transfer_ours_block"
        elif decision == "manual_both_modified":
            resolution = "merge_non_overlapping_changes"
        elif decision == "manual_ours_modified_upstream_deleted":
            resolution = (
                "transfer_to_indosphere" if character_id == 421011 else "transfer_to_named_replacement"
            )
        else:
            resolution = "accept_upstream_standard"
        resolved_rows.append({**row, "resolution": resolution})

    fields = list(resolved_rows[0])
    write_csv(output_dir / "sinosphere_character_merge_resolved.csv", resolved_rows, fields)
    write_csv(output_dir / "sinosphere_character_merge_requires_user_decision.csv", [], fields)

    summary = [
        "# Sinosphere Character Merge",
        "",
        f"- mode: `{'apply' if args.apply else 'dry-run'}`",
        f"- Sinosphere status: `{sinosphere_status}`",
        f"- Indosphere status: `{indosphere_status}`",
        "- user decisions required: `0`",
        f"- upstream combined numeric characters: `{len(upstream.blocks)}`",
        "- ours-only blocks transferred: `5`",
        "- both-modified blocks merged: `3`",
        "- moved/replaced remaps transferred: `2`",
        "- final duplicate numeric IDs: `0`",
        "- final conflict markers: `0`",
        f"- Sinosphere sha256: `{hashlib.sha256(expected_sinosphere_bytes).hexdigest()}`",
        f"- Indosphere sha256: `{hashlib.sha256(expected_indosphere_bytes).hexdigest()}`",
        "",
    ]
    (output_dir / "sinosphere_character_merge_summary.md").write_text(
        "\n".join(summary), encoding="utf-8"
    )
    print("\n".join(summary))


if __name__ == "__main__":
    main()
