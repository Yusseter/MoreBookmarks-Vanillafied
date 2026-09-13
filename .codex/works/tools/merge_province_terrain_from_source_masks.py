#!/usr/bin/env python3
import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image


PROJECT_ROOT_DEFAULT = Path(__file__).resolve().parents[3]
REPO_ROOT_DEFAULT = PROJECT_ROOT_DEFAULT / "BookmarksGit"
WORKS_ROOT_DEFAULT = PROJECT_ROOT_DEFAULT / ".codex" / "works"
SOURCE_MOD_ROOT_DEFAULT = (
    PROJECT_ROOT_DEFAULT.parent / "Leviathonlx MoreBookmarks-Plus" / "BookmarksGit"
)
VANILLA_ROOT_DEFAULT = Path(r"E:\XboxGames\Crusader Kings III\Content\game")

MASKS = {
    "modlu_kalan": Path(
        "pipeline_inputs/map/scopes/province_terrain_upstream_scope_2026-04-26.png"
    ),
    "orijinal_dogu": Path(
        "pipeline_inputs/map/scopes/province_terrain_vanilla_scope_2026-04-26.png"
    ),
}

PROVINCE_TERRAIN_REL = Path(r"common\province_terrain\00_province_terrain.txt")
PROVINCE_PROPERTIES_REL = Path(r"common\province_terrain\01_province_properties.txt")
FINAL_MASTER_REL = Path(
    r"analysis\generated\province_definition\final_master_preserve_old_ids.csv"
)
DEFINITION_REL = Path(r"map_data\definition.csv")
LEGACY_PLACEHOLDER_DEFINITION_REL = Path(
    r"analysis\generated\province_definition\definition_birlesim_final_preserve_old.csv"
)
GENERATED_REL = Path(r"analysis\generated\province_terrain_merge")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def brace_delta(line: str) -> int:
    visible = strip_comment(line)
    return visible.count("{") - visible.count("}")


def parse_definition(path: Path):
    rgb_to_ids = defaultdict(list)
    id_to_name = {}
    id_to_rgb = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(";")
            if len(parts) < 5:
                continue
            try:
                province_id = int(parts[0])
                rgb = (int(parts[1]), int(parts[2]), int(parts[3]))
            except ValueError:
                continue
            name = parts[4]
            rgb_to_ids[rgb].append(province_id)
            id_to_name[province_id] = name
            id_to_rgb[province_id] = rgb
    duplicate_rgbs = {rgb: ids for rgb, ids in rgb_to_ids.items() if len(ids) > 1}
    return rgb_to_ids, id_to_name, id_to_rgb, duplicate_rgbs


def parse_legacy_placeholder_rgbs(path: Path):
    if not path.exists():
        return {}

    legacy = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(";")
            if len(parts) < 5:
                continue
            try:
                province_id = int(parts[0])
                rgb = (int(parts[1]), int(parts[2]), int(parts[3]))
            except ValueError:
                continue
            if parts[4].startswith("zz_placeholder_"):
                legacy[rgb] = province_id
    return legacy


def is_current_definition_normal(final_id: int, id_to_name) -> bool:
    if final_id not in id_to_name:
        return False
    return not id_to_name.get(final_id, "").startswith("zz_placeholder_")


def parse_final_master(path: Path):
    rows_by_final_id = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            final_id = row.get("final_new_id", "").strip()
            if not final_id:
                continue
            rows_by_final_id[int(final_id)] = row
    return rows_by_final_id


def load_mask_rgbs(path: Path):
    counter = Counter()
    with Image.open(path) as image:
        image = image.convert("RGBA")
        for r, g, b, a in image.getdata():
            if a == 0:
                continue
            rgb = (r, g, b)
            if rgb == (0, 0, 0):
                continue
            counter[rgb] += 1
    return counter


def first_numeric_assignment_index(lines):
    for i, line in enumerate(lines):
        if re.match(r"^\s*\d+\s*=", line):
            return i
    return len(lines)


def parse_terrain_file(path: Path):
    lines = read_text(path).splitlines()
    first_index = first_numeric_assignment_index(lines)
    header = lines[:first_index]
    entries = {}
    duplicates = defaultdict(list)
    pattern = re.compile(r"^\s*(\d+)\s*=\s*([A-Za-z0-9_]+)")
    for line_no, line in enumerate(lines, start=1):
        match = pattern.match(line)
        if not match:
            continue
        province_id = int(match.group(1))
        terrain = match.group(2)
        if province_id in entries:
            duplicates[province_id].append(entries[province_id]["line_no"])
            duplicates[province_id].append(line_no)
        entries[province_id] = {
            "terrain": terrain,
            "line_no": line_no,
        }
    return header, entries, {k: sorted(set(v)) for k, v in duplicates.items()}


def parse_property_file(path: Path):
    lines = read_text(path).splitlines()
    first_index = first_numeric_assignment_index(lines)
    header = lines[:first_index]
    entries = {}
    duplicates = defaultdict(list)

    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r"^(\s*)(\d+)(\s*=\s*)(.*)$", line)
        if not match:
            i += 1
            continue

        province_id = int(match.group(2))
        start = i
        depth = brace_delta(line)
        while depth > 0 and i + 1 < len(lines):
            i += 1
            depth += brace_delta(lines[i])
        block_lines = lines[start : i + 1]
        if province_id in entries:
            duplicates[province_id].append(entries[province_id]["line_no"])
            duplicates[province_id].append(start + 1)
        entries[province_id] = {
            "lines": block_lines,
            "line_no": start + 1,
        }
        i += 1

    return header, entries, {k: sorted(set(v)) for k, v in duplicates.items()}


def rewrite_property_block(block_lines, final_id):
    if not block_lines:
        return []
    first = block_lines[0]
    rewritten_first = re.sub(r"^(\s*)\d+(\s*=\s*)", rf"\g<1>{final_id}\2", first, count=1)
    return [rewritten_first] + block_lines[1:]


def source_old_id_for(row, subset):
    if subset == "modlu_kalan":
        return row.get("modlu_old_id", "").strip()
    if subset == "orijinal_dogu":
        return row.get("orijinal_old_id", "").strip()
    return ""


def source_entry_maps(repo_root: Path, source_mod_root: Path, vanilla_root: Path):
    target_terrain_header, target_terrain, target_terrain_duplicates = parse_terrain_file(repo_root / PROVINCE_TERRAIN_REL)
    target_property_header, target_properties, target_property_duplicates = parse_property_file(repo_root / PROVINCE_PROPERTIES_REL)

    mod_terrain_header, mod_terrain, mod_terrain_duplicates = parse_terrain_file(source_mod_root / PROVINCE_TERRAIN_REL)
    vanilla_terrain_header, vanilla_terrain, vanilla_terrain_duplicates = parse_terrain_file(vanilla_root / PROVINCE_TERRAIN_REL)

    mod_property_header, mod_properties, mod_property_duplicates = parse_property_file(source_mod_root / PROVINCE_PROPERTIES_REL)
    vanilla_property_header, vanilla_properties, vanilla_property_duplicates = parse_property_file(vanilla_root / PROVINCE_PROPERTIES_REL)

    return {
        "headers": {
            "target_terrain": target_terrain_header,
            "target_properties": target_property_header,
        },
        "terrain": {
            "target": target_terrain,
            "modlu_kalan": mod_terrain,
            "orijinal_dogu": vanilla_terrain,
        },
        "properties": {
            "target": target_properties,
            "modlu_kalan": mod_properties,
            "orijinal_dogu": vanilla_properties,
        },
        "source_duplicates": {
            "target_terrain": target_terrain_duplicates,
            "target_properties": target_property_duplicates,
            "mod_terrain": mod_terrain_duplicates,
            "mod_properties": mod_property_duplicates,
            "vanilla_terrain": vanilla_terrain_duplicates,
            "vanilla_properties": vanilla_property_duplicates,
        },
    }


def build_merge_plan(
    repo_root: Path,
    works_root: Path,
    source_mod_root: Path,
    vanilla_root: Path,
):
    rgb_to_ids, id_to_name, id_to_rgb, duplicate_rgbs = parse_definition(repo_root / DEFINITION_REL)
    legacy_placeholder_rgbs = parse_legacy_placeholder_rgbs(
        works_root / LEGACY_PLACEHOLDER_DEFINITION_REL
    )
    final_rows = parse_final_master(works_root / FINAL_MASTER_REL)
    masks = {
        subset: load_mask_rgbs(works_root / rel_path)
        for subset, rel_path in MASKS.items()
    }
    entries = source_entry_maps(repo_root, source_mod_root, vanilla_root)

    rgb_membership = defaultdict(list)
    for subset, counter in masks.items():
        for rgb in counter:
            rgb_membership[rgb].append(subset)

    legacy_replaced_final_ids = set()
    for rgb in rgb_membership:
        if rgb in rgb_to_ids:
            continue
        legacy_final_id = legacy_placeholder_rgbs.get(rgb)
        if legacy_final_id and is_current_definition_normal(legacy_final_id, id_to_name):
            legacy_replaced_final_ids.add(legacy_final_id)

    plan = {}
    report_rows = []
    issue_rows = []

    for rgb, subsets in sorted(rgb_membership.items(), key=lambda item: item[0]):
        rgb_text = ",".join(str(part) for part in rgb)
        ids = rgb_to_ids.get(rgb, [])
        if not ids:
            legacy_final_id = legacy_placeholder_rgbs.get(rgb)
            if legacy_final_id and is_current_definition_normal(legacy_final_id, id_to_name):
                issue_rows.append({
                    "status": "info_legacy_placeholder_rgb_replaced_by_current_definition",
                    "final_id": legacy_final_id,
                    "rgb": rgb_text,
                    "mask_subset": "|".join(sorted(subsets)),
                    "source_old_id": "",
                    "message": "Legacy placeholder RGB is ignored because current definition.csv now has a normal province for this final id.",
                })
                continue
            issue_rows.append({
                "status": "warning_rgb_not_in_definition_skipped",
                "final_id": "",
                "rgb": rgb_text,
                "mask_subset": "|".join(sorted(subsets)),
                "source_old_id": "",
                "message": "Mask RGB is not present in final definition.csv.",
            })
            continue
        if len(ids) > 1:
            issue_rows.append({
                "status": "blocker_rgb_duplicate_in_definition",
                "final_id": "|".join(str(item) for item in ids),
                "rgb": rgb_text,
                "mask_subset": subset,
                "source_old_id": "",
                "message": "Mask RGB maps to multiple final province ids.",
            })
            continue

        final_id = ids[0]
        final_row = final_rows.get(final_id)
        definition_normal = final_id in legacy_replaced_final_ids
        if not final_row:
            issue_rows.append({
                "status": "blocker_missing_final_master_row",
                "final_id": final_id,
                "rgb": rgb_text,
                "mask_subset": subset,
                "source_old_id": "",
                "message": "Final province id has no candidate row in final_master_preserve_old_ids.csv.",
            })
            continue

        if final_row.get("row_type") != "candidate" and not definition_normal:
            report_rows.append({
                "final_id": final_id,
                "final_name": id_to_name.get(final_id, ""),
                "rgb": rgb_text,
                "mask_subset": "|".join(sorted(subsets)),
                "source_old_id": "",
                "source_terrain": "",
                "terrain_status": "skipped_non_candidate",
                "property_status": "skipped_non_candidate",
                "source_terrain_line": "",
                "source_property_line": "",
            })
            continue
        if final_row.get("row_type") != "candidate" and definition_normal:
            issue_rows.append({
                "status": "warning_final_master_placeholder_but_definition_normal",
                "final_id": final_id,
                "rgb": rgb_text,
                "mask_subset": "|".join(sorted(subsets)),
                "source_old_id": "",
                "message": "final_master still marks this id as placeholder, but current definition.csv contains a normal province row.",
            })

        preferred_subset = final_row.get("preferred_source_subset", "").strip()
        if len(subsets) > 1:
            if preferred_subset in subsets:
                subset = preferred_subset
                issue_rows.append({
                    "status": "warning_rgb_in_both_masks_resolved_by_final_master",
                    "final_id": final_id,
                    "rgb": rgb_text,
                    "mask_subset": "|".join(sorted(subsets)),
                    "source_old_id": "",
                    "message": f"RGB exists in both masks; resolved with preferred_source_subset={preferred_subset}.",
                })
            else:
                issue_rows.append({
                    "status": "blocker_rgb_in_both_masks_unresolved",
                    "final_id": final_id,
                    "rgb": rgb_text,
                    "mask_subset": "|".join(sorted(subsets)),
                    "source_old_id": "",
                    "message": "RGB exists in both source masks and final_master cannot resolve it.",
                })
                continue
        else:
            subset = subsets[0]

        source_old_id_text = source_old_id_for(final_row, subset)
        if not source_old_id_text:
            fallback_subset = preferred_subset
            fallback_source_old_id = source_old_id_for(final_row, fallback_subset) if fallback_subset else ""
            if fallback_subset and fallback_source_old_id:
                issue_rows.append({
                    "status": "warning_mask_subset_missing_source_id_resolved_by_final_master",
                    "final_id": final_id,
                    "rgb": rgb_text,
                    "mask_subset": subset,
                    "source_old_id": fallback_source_old_id,
                    "message": f"Mask subset has no source old id; resolved with preferred_source_subset={fallback_subset}.",
                })
                subset = fallback_subset
                source_old_id_text = fallback_source_old_id
            else:
                issue_rows.append({
                    "status": "warning_missing_source_old_id_for_definition_normal" if definition_normal else "blocker_missing_source_old_id",
                    "final_id": final_id,
                    "rgb": rgb_text,
                    "mask_subset": subset,
                    "source_old_id": "",
                    "message": "Final master row lacks source old id for the mask subset.",
                })
                if definition_normal:
                    report_rows.append({
                        "final_id": final_id,
                        "final_name": id_to_name.get(final_id, ""),
                        "rgb": rgb_text,
                        "mask_subset": subset,
                        "source_old_id": "",
                        "source_terrain": "",
                        "terrain_status": "warning_missing_source_old_id",
                        "property_status": "warning_missing_source_old_id",
                        "source_terrain_line": "",
                        "source_property_line": "",
                    })
                    continue
                continue

        if not source_old_id_text:
            issue_rows.append({
                "status": "warning_missing_source_old_id_for_definition_normal" if definition_normal else "blocker_missing_source_old_id",
                "final_id": final_id,
                "rgb": rgb_text,
                "mask_subset": subset,
                "source_old_id": "",
                "message": "Final master row lacks source old id for the mask subset.",
            })
            if definition_normal:
                report_rows.append({
                    "final_id": final_id,
                    "final_name": id_to_name.get(final_id, ""),
                    "rgb": rgb_text,
                    "mask_subset": subset,
                    "source_old_id": "",
                    "source_terrain": "",
                    "terrain_status": "warning_missing_source_old_id",
                    "property_status": "warning_missing_source_old_id",
                    "source_terrain_line": "",
                    "source_property_line": "",
                })
                continue
            continue
        source_old_id = int(source_old_id_text)

        if preferred_subset and preferred_subset != subset:
            issue_rows.append({
                "status": "warning_mask_subset_differs_from_final_master",
                "final_id": final_id,
                "rgb": rgb_text,
                "mask_subset": subset,
                "source_old_id": source_old_id,
                "message": f"final_master preferred_source_subset is {preferred_subset}.",
            })

        terrain_source = entries["terrain"][subset].get(source_old_id)
        property_source = entries["properties"][subset].get(source_old_id)

        terrain_status = "ok" if terrain_source else "warning_missing_source_terrain"
        property_status = "ok" if property_source else "warning_missing_source_property"

        report_rows.append({
            "final_id": final_id,
            "final_name": id_to_name.get(final_id, ""),
            "rgb": rgb_text,
            "mask_subset": subset,
            "source_old_id": source_old_id,
            "source_terrain": terrain_source["terrain"] if terrain_source else "",
            "terrain_status": terrain_status,
            "property_status": property_status,
            "source_terrain_line": terrain_source["line_no"] if terrain_source else "",
            "source_property_line": property_source["line_no"] if property_source else "",
        })

        plan[final_id] = {
            "final_id": final_id,
            "subset": subset,
            "source_old_id": source_old_id,
            "terrain": terrain_source,
            "property": property_source,
        }

    for rgb, ids in duplicate_rgbs.items():
        issue_rows.append({
            "status": "warning_duplicate_rgb_in_definition_global",
            "final_id": "|".join(str(item) for item in ids),
            "rgb": ",".join(str(part) for part in rgb),
            "mask_subset": "",
            "source_old_id": "",
            "message": "definition.csv has duplicate RGB outside or inside the selected masks.",
        })

    for key, duplicates in entries["source_duplicates"].items():
        for province_id, line_numbers in duplicates.items():
            issue_rows.append({
                "status": f"warning_duplicate_id_in_{key}",
                "final_id": "",
                "rgb": "",
                "mask_subset": "",
                "source_old_id": province_id,
                "message": "Duplicate province id lines: " + "|".join(str(item) for item in line_numbers),
            })

    return plan, report_rows, issue_rows, entries


def build_terrain_text(header, plan):
    lines = list(header)
    if lines and lines[-1] != "":
        lines.append("")
    for final_id in sorted(plan):
        terrain_source = plan[final_id]["terrain"]
        if not terrain_source:
            continue
        lines.append(f"{final_id}={terrain_source['terrain']}")
    return "\r\n".join(lines).rstrip() + "\r\n"


def build_property_text(header, plan):
    lines = list(header)
    if lines and lines[-1] != "":
        lines.append("")
    for final_id in sorted(plan):
        property_source = plan[final_id]["property"]
        if not property_source:
            continue
        lines.extend(rewrite_property_block(property_source["lines"], final_id))
    return "\r\n".join(lines).rstrip() + "\r\n"


def write_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def summarize(report_rows, issue_rows):
    blockers = [row for row in issue_rows if str(row["status"]).startswith("blocker_")]
    warnings = [row for row in issue_rows if str(row["status"]).startswith("warning_")]
    legacy_placeholder_ignored = sum(1 for row in issue_rows if row["status"] == "info_legacy_placeholder_rgb_replaced_by_current_definition")
    skipped_non_candidate = sum(1 for row in report_rows if row["terrain_status"] == "skipped_non_candidate")
    candidate_rows = len(report_rows) - skipped_non_candidate
    source_id_missing = sum(1 for row in report_rows if row["terrain_status"] == "warning_missing_source_old_id")
    terrain_ok = sum(1 for row in report_rows if row["terrain_status"] == "ok")
    terrain_missing = sum(1 for row in report_rows if row["terrain_status"] == "warning_missing_source_terrain")
    property_ok = sum(1 for row in report_rows if row["property_status"] == "ok")
    property_missing = sum(1 for row in report_rows if row["property_status"] == "warning_missing_source_property")
    return {
        "mask_rows_seen": len(report_rows),
        "candidate_rows": candidate_rows,
        "skipped_non_candidate": skipped_non_candidate,
        "legacy_placeholder_rgbs_ignored": legacy_placeholder_ignored,
        "blockers": len(blockers),
        "warnings": len(warnings),
        "source_id_missing": source_id_missing,
        "terrain_written": terrain_ok,
        "terrain_source_missing": terrain_missing,
        "property_written": property_ok,
        "property_source_missing": property_missing,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        "--mod-root",
        dest="repo_root",
        type=Path,
        default=REPO_ROOT_DEFAULT,
    )
    parser.add_argument("--works-root", type=Path, default=WORKS_ROOT_DEFAULT)
    parser.add_argument("--source-mod-root", type=Path, default=SOURCE_MOD_ROOT_DEFAULT)
    parser.add_argument("--vanilla-root", type=Path, default=VANILLA_ROOT_DEFAULT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--write-reports", action="store_true")
    args = parser.parse_args()

    plan, report_rows, issue_rows, entries = build_merge_plan(
        args.repo_root,
        args.works_root,
        args.source_mod_root,
        args.vanilla_root,
    )
    summary = summarize(report_rows, issue_rows)
    blockers = [row for row in issue_rows if str(row["status"]).startswith("blocker_")]

    print("province terrain merge")
    for key, value in summary.items():
        print(f"{key}: {value}")

    if blockers and args.write:
        print("write skipped because blockers exist")
        args.write = False

    generated_root = args.works_root / GENERATED_REL
    if args.write or args.write_reports:
        write_csv(
            generated_root / "province_terrain_merge_report.csv",
            report_rows,
            ["final_id", "final_name", "rgb", "mask_subset", "source_old_id", "source_terrain", "terrain_status", "property_status", "source_terrain_line", "source_property_line"],
        )
        write_csv(
            generated_root / "province_terrain_merge_issues.csv",
            issue_rows,
            ["status", "final_id", "rgb", "mask_subset", "source_old_id", "message"],
        )
        summary_lines = ["# Province Terrain Merge Summary", ""]
        for key, value in summary.items():
            summary_lines.append(f"- {key}: {value}")
        summary_lines.append("")
        summary_lines.append("- write_performed: " + ("yes" if args.write else "no"))
        write_text(generated_root / "province_terrain_merge_summary.md", "\n".join(summary_lines) + "\n")

    if args.write:
        terrain_text = build_terrain_text(entries["headers"]["target_terrain"], plan)
        property_text = build_property_text(entries["headers"]["target_properties"], plan)

        live_terrain = args.repo_root / PROVINCE_TERRAIN_REL
        live_properties = args.repo_root / PROVINCE_PROPERTIES_REL

        write_text(live_terrain, terrain_text)
        write_text(live_properties, property_text)


if __name__ == "__main__":
    main()
