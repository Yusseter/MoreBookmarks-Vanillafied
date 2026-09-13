from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Iterable

from apply_county_source_fix_plan import (
    TextFile,
    TitleBlock,
    make_replacement,
    normalize_block,
    normalize_newlines,
    parse_title_blocks,
    pick_source_block,
    read_text_file,
    reindent_block,
    single_target_block,
    split_lines_keepends,
    split_source_location,
    write_csv,
    write_text_file,
)


COLOR_RE = re.compile(r"^\s*color\s*=")
PROVINCE_VALUE_RE = re.compile(r"\bprovince\s*=\s*\d+\b")


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[3]
    mod_root = project_root / "BookmarksGit"
    codex_root = project_root / ".codex"
    output_dir = (
        codex_root / "works/analysis/generated/landed_titles_source_audit"
    )
    parser = argparse.ArgumentParser(
        description="Apply only provably safe county source cosmetic fixes."
    )
    parser.add_argument("--fix-plan", type=Path, default=output_dir / "county_source_fix_plan.csv")
    parser.add_argument("--audit-csv", type=Path, default=output_dir / "county_source_audit.csv")
    parser.add_argument(
        "--current-landed-titles",
        type=Path,
        default=mod_root / "common/landed_titles/00_landed_titles.txt",
    )
    parser.add_argument("--output-dir", type=Path, default=output_dir)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def is_color_line(line: str) -> bool:
    return bool(COLOR_RE.match(strip_comment(line).strip()))


def normalize_without_color(text: str) -> str:
    lines = []
    for line in text.splitlines():
        clean = strip_comment(line).strip()
        if not clean or is_color_line(line):
            continue
        clean = re.sub(r"\s+", " ", clean)
        lines.append(clean)
    return "\n".join(lines)


def normalize_with_masked_province_ids(text: str) -> str:
    lines = []
    for line in text.splitlines():
        clean = strip_comment(line).strip()
        if not clean:
            continue
        clean = PROVINCE_VALUE_RE.sub("province = <id>", clean)
        clean = re.sub(r"\s+", " ", clean)
        lines.append(clean)
    return "\n".join(lines)


def color_lines(text: str) -> list[str]:
    return [strip_comment(line).strip() for line in text.splitlines() if is_color_line(line)]


def read_fix_plan(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.DictReader(handle)]


def read_csv_by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row[key]: row for row in csv.DictReader(handle)}


def load_source_block(
    source_block_path: str,
    county_id: str,
    source_files: dict[Path, TextFile],
    source_blocks_by_file: dict[Path, dict[str, list[TitleBlock]]],
) -> TitleBlock | None:
    if not source_block_path:
        return None
    source_path, source_line = split_source_location(source_block_path)
    if source_path not in source_files:
        source_files[source_path] = read_text_file(source_path)
        source_blocks_by_file[source_path] = parse_title_blocks(source_files[source_path].text)
    return pick_source_block(source_blocks_by_file[source_path], county_id, source_line)


def colors_are_composite(current_colors: list[str], left_colors: list[str], right_colors: list[str]) -> bool:
    if not current_colors:
        return False
    if len(current_colors) != len(left_colors) or len(current_colors) != len(right_colors):
        return False
    for current, left, right in zip(current_colors, left_colors, right_colors):
        if current != left and current != right:
            return False
    return True


def replace_color_lines(target_text: str, source_text: str, newline: str) -> str:
    target_lines = split_lines_keepends(target_text)
    source_color_bodies = []
    for source_line in split_lines_keepends(source_text):
        if not is_color_line(source_line):
            continue
        body = source_line.rstrip("\r\n")
        source_color_bodies.append(body.lstrip(" \t"))

    color_index = 0
    for index, target_line in enumerate(target_lines):
        if not is_color_line(target_line):
            continue
        if color_index >= len(source_color_bodies):
            raise RuntimeError("source color line count changed during replacement")
        line_ending = ""
        body = target_line
        if body.endswith("\r\n"):
            body = body[:-2]
            line_ending = "\r\n"
        elif body.endswith("\n"):
            body = body[:-1]
            line_ending = "\n"
        elif body.endswith("\r"):
            body = body[:-1]
            line_ending = "\r"

        indent = re.match(r"^[ \t]*", body).group(0)
        target_lines[index] = indent + source_color_bodies[color_index] + line_ending
        color_index += 1

    return normalize_newlines("".join(target_lines), newline)


def apply_replacements(target_file: TextFile, target_blocks: dict[str, list[TitleBlock]], replacements: dict[str, str]) -> None:
    lines = split_lines_keepends(target_file.text)
    changes: list[tuple[int, int, str]] = []
    for county_id, replacement in replacements.items():
        block = single_target_block(target_blocks, county_id)
        if block is None:
            raise RuntimeError(f"Target block not found exactly once in {target_file.path}: {county_id}")
        changes.append((block.start_index, block.end_index, replacement))

    for start_index, end_index, replacement in sorted(changes, reverse=True):
        lines[start_index : end_index + 1] = replacement.splitlines(keepends=True)

    write_text_file(target_file, "".join(lines))


def row_for_report(
    plan_row: dict[str, str],
    decision: str,
    reason: str,
    source_block: TitleBlock | None,
    current_block: TitleBlock | None,
) -> dict[str, object]:
    source_colors = color_lines(source_block.text) if source_block else []
    current_colors = color_lines(current_block.text) if current_block else []
    return {
        "county_id": plan_row.get("county_id", ""),
        "decision": decision,
        "reason": reason,
        "expected_source": plan_row.get("expected_source", ""),
        "current_block_source": plan_row.get("current_block_source", ""),
        "source_block_path": plan_row.get("source_block_path", ""),
        "current_start_line": current_block.start_line if current_block else "",
        "current_end_line": current_block.end_line if current_block else "",
        "source_start_line": source_block.start_line if source_block else "",
        "source_end_line": source_block.end_line if source_block else "",
        "current_province_ids": " ".join(str(value) for value in current_block.province_ids) if current_block else "",
        "source_province_ids": " ".join(str(value) for value in source_block.province_ids) if source_block else "",
        "current_color_count": len(current_colors),
        "source_color_count": len(source_colors),
        "color_change_count": sum(1 for current, source in zip(current_colors, source_colors) if current != source),
    }


def main() -> int:
    args = parse_args()
    plan_rows = read_fix_plan(args.fix_plan)
    audit_by_county = read_csv_by_key(args.audit_csv, "county_id")
    current_file = read_text_file(args.current_landed_titles)
    current_blocks = parse_title_blocks(current_file.text)

    source_files: dict[Path, TextFile] = {}
    source_blocks_by_file: dict[Path, dict[str, list[TitleBlock]]] = {}
    report_rows: list[dict[str, object]] = []
    current_replacements: dict[str, str] = {}

    for plan_row in plan_rows:
        county_id = plan_row["county_id"]
        action = plan_row.get("action", "")
        expected_source = plan_row.get("expected_source", "")
        source_block_path = plan_row.get("source_block_path", "")

        source_block: TitleBlock | None = None
        current_block = single_target_block(current_blocks, county_id)

        if action != "manual_review":
            report_rows.append(row_for_report(plan_row, "skip", f"action={action}", source_block, current_block))
            continue
        if expected_source == "mixed":
            audit_row = audit_by_county.get(county_id, {})
            if current_block is None:
                report_rows.append(row_for_report(plan_row, "manual", "current_block_not_found_once", source_block, current_block))
                continue

            vanilla_block = load_source_block(
                audit_row.get("vanilla_best_match", ""),
                county_id,
                source_files,
                source_blocks_by_file,
            )
            mod_block = load_source_block(
                audit_row.get("mod_best_match", ""),
                county_id,
                source_files,
                source_blocks_by_file,
            )
            if vanilla_block is None or mod_block is None:
                report_rows.append(row_for_report(plan_row, "manual", "mixed_source_block_not_found", source_block, current_block))
                continue

            source_block = vanilla_block
            if current_block.normalized_hash == vanilla_block.normalized_hash and current_block.normalized_hash == mod_block.normalized_hash:
                report_rows.append(
                    row_for_report(
                        plan_row,
                        "accept_mixed_current_matches_both_sources",
                        "mixed_current_matches_both_sources",
                        source_block,
                        current_block,
                    )
                )
                continue

            same_provinces = (
                current_block.province_ids == vanilla_block.province_ids
                and current_block.province_ids == mod_block.province_ids
            )
            same_non_color = (
                normalize_without_color(current_block.text)
                == normalize_without_color(vanilla_block.text)
                == normalize_without_color(mod_block.text)
            )
            current_colors = color_lines(current_block.text)
            vanilla_colors = color_lines(vanilla_block.text)
            mod_colors = color_lines(mod_block.text)
            if same_provinces and same_non_color and colors_are_composite(current_colors, vanilla_colors, mod_colors):
                report_rows.append(
                    row_for_report(
                        plan_row,
                        "accept_mixed_color_composite",
                        "mixed_same_non_color_current_colors_from_sources",
                        source_block,
                        current_block,
                    )
                )
                continue

            report_rows.append(row_for_report(plan_row, "manual", "expected_source=mixed", source_block, current_block))
            continue
        if expected_source not in {"vanilla", "mod"}:
            report_rows.append(
                row_for_report(plan_row, "manual", f"expected_source={expected_source}", source_block, current_block)
            )
            continue
        if not source_block_path:
            report_rows.append(row_for_report(plan_row, "manual", "no_source_block_path", source_block, current_block))
            continue
        if current_block is None:
            report_rows.append(row_for_report(plan_row, "manual", "current_block_not_found_once", source_block, current_block))
            continue

        source_block = load_source_block(source_block_path, county_id, source_files, source_blocks_by_file)
        if source_block is None:
            report_rows.append(row_for_report(plan_row, "manual", "source_block_not_found", source_block, current_block))
            continue
        same_except_province_ids = (
            len(current_block.province_ids) == len(source_block.province_ids)
            and normalize_with_masked_province_ids(current_block.text)
            == normalize_with_masked_province_ids(source_block.text)
        )
        if same_except_province_ids and current_block.province_ids != source_block.province_ids:
            report_rows.append(
                row_for_report(
                    plan_row,
                    "accept_only_province_ids_differ",
                    "same_block_after_masking_province_ids",
                    source_block,
                    current_block,
                )
            )
            continue
        if current_block.province_ids != source_block.province_ids:
            report_rows.append(row_for_report(plan_row, "manual", "province_ids_differ", source_block, current_block))
            continue

        source_no_color = normalize_without_color(source_block.text)
        current_no_color = normalize_without_color(current_block.text)
        if current_no_color != source_no_color:
            report_rows.append(row_for_report(plan_row, "manual", "non_color_content_differs", source_block, current_block))
            continue

        source_colors = color_lines(source_block.text)
        current_colors = color_lines(current_block.text)
        if not source_colors:
            report_rows.append(row_for_report(plan_row, "noop", "no_color_lines", source_block, current_block))
            continue
        if len(source_colors) != len(current_colors):
            report_rows.append(row_for_report(plan_row, "manual", "color_line_count_differs", source_block, current_block))
            continue
        if source_colors == current_colors:
            report_rows.append(row_for_report(plan_row, "noop", "colors_already_match", source_block, current_block))
            continue

        current_replacements[county_id] = replace_color_lines(current_block.text, source_block.text, current_file.newline)
        report_rows.append(row_for_report(plan_row, "apply_color_only", "safe_color_only", source_block, current_block))

    fieldnames = [
        "county_id",
        "decision",
        "reason",
        "expected_source",
        "current_block_source",
        "source_block_path",
        "current_start_line",
        "current_end_line",
        "source_start_line",
        "source_end_line",
        "current_province_ids",
        "source_province_ids",
        "current_color_count",
        "source_color_count",
        "color_change_count",
    ]
    classification_path = args.output_dir / "county_source_safe_cosmetic_classification.csv"
    simple_candidates_path = args.output_dir / "county_source_simple_resolution_candidates.csv"
    report_path = args.output_dir / "county_source_safe_color_only_apply_report.csv"
    write_csv(classification_path, report_rows, fieldnames)
    write_csv(
        simple_candidates_path,
        [row for row in report_rows if str(row["decision"]).startswith("accept_") or row["decision"] == "apply_color_only"],
        fieldnames,
    )

    if args.apply and current_replacements:
        apply_replacements(current_file, current_blocks, current_replacements)
        write_csv(report_path, [row for row in report_rows if row["decision"] == "apply_color_only"], fieldnames)

    print(f"classification: {classification_path}")
    print(f"simple candidates: {simple_candidates_path}")
    print(f"safe color-only rows: {len(current_replacements)}")
    print(f"applied: {'yes' if args.apply else 'no'}")
    if args.apply:
        print(f"apply report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
