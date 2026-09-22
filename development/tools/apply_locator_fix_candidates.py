from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


CANDIDATE_FILE = "locator_fix_candidates_landed_problem_non_building.csv"
APPLY_REPORT_FILE = "locator_fix_candidates_high_apply_report.csv"
APPLY_SUMMARY_FILE = "locator_fix_candidates_high_apply_summary.md"
COMMENT_MARKER = "# Yusseter: Auto fixed from locator candidate"
BUILDING_FILE = "building_locators.txt"

LOCATOR_FILES = {
    "activities.txt",
    "combat_locators.txt",
    "player_stack_locators.txt",
    "siege_locators.txt",
    "special_building_locators.txt",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def is_excluded_building_file(file_name: str) -> bool:
    return file_name == BUILDING_FILE or (file_name.startswith("# Yusseter:") and BUILDING_FILE in file_name)


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def brace_delta(line: str) -> int:
    visible = strip_comment(line)
    return visible.count("{") - visible.count("}")


def parse_candidate_float(text: str) -> float:
    return float(text.strip())


def format_coord(value: float) -> str:
    if abs(value - round(value)) < 0.000001:
        return str(int(round(value)))
    return f"{value:.6f}"


def replace_position_line(line: str, x: float, y: float, z: float) -> str:
    newline = ""
    body = line
    if body.endswith("\r\n"):
        newline = "\r\n"
        body = body[:-2]
    elif body.endswith("\n"):
        newline = "\n"
        body = body[:-1]

    match = re.match(r"^(?P<indent>\s*)position\s*=\s*\{[^}]*\}(?P<suffix>.*)$", body)
    if not match:
        raise ValueError(f"Not a position line: {line!r}")

    indent = match.group("indent")
    suffix = match.group("suffix")
    existing_comment = ""
    if "#" in suffix:
        existing_comment = suffix[suffix.index("#") :].strip()

    comments: list[str] = []
    if existing_comment and COMMENT_MARKER not in existing_comment:
        comments.append(existing_comment)
    comments.append(COMMENT_MARKER)
    comment_text = " " + " ".join(comments)
    return (
        f"{indent}position={{ {format_coord(x)} {format_coord(y)} {format_coord(z)} }}"
        f"{comment_text}{newline}"
    )


def collect_instance_blocks(lines: list[str]) -> list[dict[str, int | None]]:
    blocks: list[dict[str, int | None]] = []
    index = 0
    while index < len(lines):
        visible = strip_comment(lines[index]).strip()
        if not visible.startswith("{"):
            index += 1
            continue

        start = index
        depth = 0
        id_line: int | None = None
        position_line: int | None = None
        province_id: int | None = None

        while index < len(lines):
            line = lines[index]
            if id_line is None:
                id_match = re.search(r"\bid\s*=\s*(-?\d+)\b", strip_comment(line))
                if id_match:
                    id_line = index
                    province_id = int(id_match.group(1))
            if position_line is None and re.search(r"\bposition\s*=", strip_comment(line)):
                position_line = index

            depth += brace_delta(line)
            if depth <= 0:
                break
            index += 1

        if province_id is not None and position_line is not None:
            blocks.append(
                {
                    "id": province_id,
                    "start": start,
                    "end": index,
                    "id_line": id_line,
                    "position_line": position_line,
                }
            )
        index += 1

    return blocks


def candidate_rows() -> list[dict[str, str]]:
    root = project_root()
    audit_dir = (
        root / "development" / "analysis" / "generated" / "map_object_locator_audit"
    )
    rows = read_csv(audit_dir / CANDIDATE_FILE)
    selected: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        file_name = row["file"]
        if is_excluded_building_file(file_name) or file_name not in LOCATOR_FILES:
            continue
        if row["confidence"] != "high" or row["candidate_status"] != "inside_exact":
            continue
        key = (file_name, row["province_id"])
        if key in seen:
            raise ValueError(f"Duplicate high-confidence candidate for {key}")
        seen.add(key)
        selected.append(row)
    return selected


def apply_candidates(apply: bool) -> dict[str, int]:
    root = project_root()
    audit_dir = (
        root / "development" / "analysis" / "generated" / "map_object_locator_audit"
    )
    locator_dir = root / "BookmarksGit" / "gfx" / "map" / "map_object_data"

    rows = candidate_rows()
    by_file: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_file[row["file"]].append(row)

    report_rows: list[dict[str, Any]] = []
    changed_total = 0
    skipped_total = 0

    for file_name, file_rows in sorted(by_file.items()):
        path = locator_dir / file_name
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        lines = text.splitlines(keepends=True)
        blocks = collect_instance_blocks(lines)
        by_id: dict[int, dict[str, int | None]] = {}
        duplicate_ids: set[int] = set()
        for block in blocks:
            province_id = int(block["id"])
            if province_id in by_id:
                duplicate_ids.add(province_id)
            by_id[province_id] = block

        for row in file_rows:
            province_id = int(row["province_id"])
            status = "pending"
            old_position = ""
            new_position = ""
            message = ""

            if province_id in duplicate_ids:
                status = "skipped_duplicate_id"
                message = "multiple instance blocks with same id"
                skipped_total += 1
            elif province_id not in by_id:
                status = "skipped_missing_id"
                message = "instance block was not found"
                skipped_total += 1
            else:
                block = by_id[province_id]
                position_index = int(block["position_line"])
                old_line = lines[position_index]
                try:
                    candidate_x = parse_candidate_float(row["candidate_x"])
                    candidate_y = parse_candidate_float(row["candidate_y"])
                    candidate_z = parse_candidate_float(row["candidate_z"])
                    lines[position_index] = replace_position_line(
                        old_line,
                        candidate_x,
                        candidate_y,
                        candidate_z,
                    )
                    status = "changed" if apply else "would_change"
                    old_position = old_line.strip()
                    new_position = lines[position_index].strip()
                    changed_total += 1
                except Exception as exc:  # noqa: BLE001 - report row should keep the exact failure.
                    status = "skipped_replace_error"
                    message = str(exc)
                    skipped_total += 1

            report_rows.append(
                {
                    "file": file_name,
                    "province_id": province_id,
                    "province_name": row["province_name"],
                    "confidence": row["confidence"],
                    "candidate_status": row["candidate_status"],
                    "status": status,
                    "old_position": old_position,
                    "new_position": new_position,
                    "message": message,
                }
            )

        if apply:
            path.write_text("".join(lines), encoding="utf-8")

    fieldnames = [
        "file",
        "province_id",
        "province_name",
        "confidence",
        "candidate_status",
        "status",
        "old_position",
        "new_position",
        "message",
    ]
    write_csv(audit_dir / APPLY_REPORT_FILE, report_rows, fieldnames)

    by_status = defaultdict(int)
    by_file_status = defaultdict(int)
    for row in report_rows:
        by_status[row["status"]] += 1
        by_file_status[(row["file"], row["status"])] += 1

    lines = [
        "# Locator Fix Candidate High-Confidence Apply Report",
        "",
        f"- source candidates: `{CANDIDATE_FILE}`",
        f"- output report: `{APPLY_REPORT_FILE}`",
        f"- apply mode: `{'apply' if apply else 'dry-run'}`",
        f"- selected high-confidence rows: `{len(rows)}`",
        f"- changed/would_change rows: `{changed_total}`",
        f"- skipped rows: `{skipped_total}`",
        f"- marker added to changed position lines: `{COMMENT_MARKER}`",
        f"- live locator files modified: `{len(by_file) if apply else 0}`",
        "",
        "## By Status",
        "",
    ]
    for status in sorted(by_status):
        lines.append(f"- `{status}`: `{by_status[status]}`")
    lines.extend(["", "## By File", ""])
    for file_name in sorted(by_file):
        parts = [
            f"{status}={by_file_status[(file_name, status)]}"
            for status in sorted(by_status)
            if by_file_status[(file_name, status)]
        ]
        lines.append(f"- `{file_name}`: " + ", ".join(parts))
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Only `confidence=high` and `candidate_status=inside_exact` rows are selected.",
            "- `building_locators.txt` and `# Yusseter: ... building_locators.txt` candidates are excluded.",
            "- Only the `position` line is changed; rotation, scale, comments on other lines, and block order are preserved.",
            "",
        ]
    )
    (audit_dir / APPLY_SUMMARY_FILE).write_text("\n".join(lines), encoding="utf-8")

    return {
        "selected": len(rows),
        "changed": changed_total,
        "skipped": skipped_total,
        "files": len(by_file) if apply else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Modify locator files. Without this, only dry-run.")
    args = parser.parse_args()

    stats = apply_candidates(apply=args.apply)
    mode = "apply" if args.apply else "dry-run"
    print(
        f"Locator high-confidence {mode}: "
        f"selected={stats['selected']} changed={stats['changed']} "
        f"skipped={stats['skipped']} files={stats['files']}"
    )


if __name__ == "__main__":
    main()
