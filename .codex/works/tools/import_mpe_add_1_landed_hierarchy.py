from pathlib import Path
import csv
import hashlib
import re
import sys
from collections import Counter, defaultdict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TARGET = PROJECT_ROOT / "BookmarksGit"
MPE = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\1158310\3726274827")
OUT = PROJECT_ROOT / r".codex\works\analysis\generated\mpe_import_add_1"

REPORT_PATH = OUT / "mpe_landed_titles_hierarchy_import_report.csv"
LOC_REPORT_PATH = OUT / "mpe_landed_titles_hierarchy_localization_report.csv"
SUMMARY_PATH = OUT / "mpe_landed_titles_hierarchy_import_summary.md"

LOC_BEGIN = "# Yusseter MPE ADD 1 LAND TITLE LOCALIZATION BEGIN"
LOC_END = "# Yusseter MPE ADD 1 LAND TITLE LOCALIZATION END"


class Abort(Exception):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def read_text_lines(path):
    data = path.read_bytes()
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig" if bom else "utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.splitlines(), newline, bom, text.endswith(("\n", "\r"))


def write_text_lines(path, lines, newline="\r\n", bom=False, trailing=True):
    text = newline.join(lines)
    if trailing:
        text += newline
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def strip_comment(line):
    return line.split("#", 1)[0]


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def parse_definition_ids(path):
    lines, _, _, _ = read_text_lines(path)
    ids = set()
    for line in lines:
        raw = line.lstrip("\ufeff").strip()
        if not raw or raw.startswith("#"):
            continue
        parts = raw.split(";")
        if parts and parts[0].isdigit():
            ids.add(int(parts[0]))
    return ids


def parse_titles(path):
    lines, newline, bom, trailing = read_text_lines(path)
    title_re = re.compile(r"^\s*((?:e|k|d|c|b)_[A-Za-z0-9_']+)\s*=\s*\{")
    by_name = defaultdict(list)
    entries = []
    province_map = {}
    stack = []
    depth = 0

    for index, line in enumerate(lines):
        code = strip_comment(line)
        match = title_re.search(code)
        if match:
            name = match.group(1)
            parents = {}
            for parent in stack:
                parents[parent["tier"]] = parent["name"]
            entry = {
                "name": name,
                "tier": name[0],
                "start": index,
                "end": None,
                "depth": depth,
                "parents": parents,
            }
            entries.append(entry)
            by_name[name].append(entry)
            stack.append(entry)

        province_match = re.search(r"\bprovince\s*=\s*(\d+)\b", code)
        if province_match:
            current_b = next((entry for entry in reversed(stack) if entry["tier"] == "b"), None)
            if current_b:
                province_map[int(province_match.group(1))] = {
                    "barony": current_b["name"],
                    "county": current_b["parents"].get("c", ""),
                    "duchy": current_b["parents"].get("d", ""),
                    "kingdom": current_b["parents"].get("k", ""),
                    "empire": current_b["parents"].get("e", ""),
                    "entry": current_b,
                    "line": index + 1,
                }

        new_depth = depth + code.count("{") - code.count("}")
        while stack and new_depth <= stack[-1]["depth"]:
            stack[-1]["end"] = index
            stack.pop()
        depth = new_depth

    for entry in entries:
        if entry["end"] is None:
            entry["end"] = len(lines) - 1

    return {
        "path": path,
        "lines": lines,
        "newline": newline,
        "bom": bom,
        "trailing": trailing,
        "by_name": by_name,
        "entries": entries,
        "province_map": province_map,
        "final_depth": depth,
    }


def title_entry(data, name):
    entries = data["by_name"].get(name, [])
    if len(entries) == 1:
        return entries[0]
    return None


def immediate_children(data, parent, tier):
    return [
        entry
        for entry in data["entries"]
        if entry["tier"] == tier
        and entry["start"] > parent["start"]
        and entry["end"] < parent["end"]
        and entry["depth"] == parent["depth"] + 1
    ]


def province_in_entry(lines, entry):
    for index in range(entry["start"], entry["end"] + 1):
        match = re.search(r"\bprovince\s*=\s*(\d+)\b", strip_comment(lines[index]))
        if match:
            return int(match.group(1)), index
    return None, None


def add_open_comment(line, comment):
    if "# Yusseter" in line:
        return line
    return re.sub(r"\{\s*(#.*)?$", "{ # Yusseter: " + comment, line)


def rewrite_province_line(line, old_id, new_id):
    if re.search(r"\bprovince\s*=\s*" + re.escape(str(old_id)) + r"\b", strip_comment(line)):
        return re.sub(r"(\bprovince\s*=\s*)\d+", r"\g<1>" + str(new_id), line, count=1)
    return line


def make_barony_block(source_lines, entry, old_id, new_id):
    block = list(source_lines[entry["start"] : entry["end"] + 1])
    if block:
        block[0] = add_open_comment(block[0], f"MPE_{old_id}")
    return [rewrite_province_line(line, old_id, new_id) for line in block]


def prefix_before_first_child(source_data, entry, child_tiers, created_counties, existing_counties, report_rows):
    children = [
        child
        for child in source_data["entries"]
        if child["start"] > entry["start"]
        and child["end"] < entry["end"]
        and child["depth"] == entry["depth"] + 1
        and child["tier"] in child_tiers
    ]
    first_child_start = min((child["start"] for child in children), default=entry["end"])
    out = []
    for index in range(entry["start"] + 1, first_child_start):
        line = source_data["lines"][index]
        match = re.search(r"\bcapital\s*=\s*((?:c|d|k|e)_[A-Za-z0-9_']+)\b", strip_comment(line))
        if match:
            target = match.group(1)
            if target.startswith("c_") and target not in created_counties and target not in existing_counties:
                report_rows.append(
                    {
                        "status": "metadata_capital_omitted",
                        "title": entry["name"],
                        "related_title": target,
                        "note": "capital county is not created or already present in target",
                    }
                )
                continue
        out.append(line)
    return out


def make_county_block(source_data, county_entry, barony_items, target_counties, report_rows):
    source_lines = source_data["lines"]
    barony_blocks = {item["entry"]["start"]: item for item in barony_items}
    source_ids = sorted(item["old_id"] for item in barony_items)
    block = [add_open_comment(source_lines[county_entry["start"]], "MPE county source provinces " + "/".join(str(x) for x in source_ids))]
    block.extend(
        prefix_before_first_child(
            source_data,
            county_entry,
            {"b"},
            created_counties=set(),
            existing_counties=target_counties,
            report_rows=report_rows,
        )
    )

    for child in immediate_children(source_data, county_entry, "b"):
        item = barony_blocks.get(child["start"])
        if not item:
            continue
        block.extend(make_barony_block(source_lines, child, item["old_id"], item["new_id"]))

    block.append(source_lines[county_entry["end"]])
    return block


def make_duchy_block(source_data, duchy_entry, county_blocks, target_counties, report_rows):
    source_ids = []
    created_counties = set()
    for item in county_blocks:
        source_ids.extend(item["source_ids"])
        created_counties.add(item["county"])
    source_ids = sorted(set(source_ids))
    block = [add_open_comment(source_data["lines"][duchy_entry["start"]], "MPE duchy source provinces " + "/".join(str(x) for x in source_ids))]
    block.extend(
        prefix_before_first_child(
            source_data,
            duchy_entry,
            {"c"},
            created_counties=created_counties,
            existing_counties=target_counties,
            report_rows=report_rows,
        )
    )
    for item in sorted(county_blocks, key=lambda row: row["county_start"]):
        block.extend(item["block"])
    block.append(source_data["lines"][duchy_entry["end"]])
    return block


def parse_localization_lines(lines, path):
    values = {}
    loc_re = re.compile(r"^\s*([A-Za-z0-9_']+):(?:\d+)?\s*\"(.*)\"\s*(?:#.*)?$")
    for index, line in enumerate(lines):
        match = loc_re.match(line)
        if match:
            values.setdefault(match.group(1), {"value": match.group(2), "path": path, "line": index + 1})
    return values


def parse_localization_file(path):
    lines, newline, bom, trailing = read_text_lines(path)
    values = parse_localization_lines(lines, path)
    return values, lines, newline, bom, trailing


def parse_localization_tree(root):
    values = {}
    if not root.exists():
        return values
    priority = []
    preferred = [
        root / r"localization\english\replace\titles_l_english.yml",
        root / r"localization\english\replace\older_titles_l_english.yml",
    ]
    for path in preferred:
        if path.exists():
            priority.append(path)
    for path in sorted((root / r"localization\english").rglob("*.yml")):
        if path not in priority:
            priority.append(path)
    for path in priority:
        file_values, _, _, _, _ = parse_localization_file(path)
        for key, value in file_values.items():
            values.setdefault(key, value)
    return values


def target_localization_keys(root, managed_path=None):
    values = {}
    loc_root = root / "localization"
    if not loc_root.exists():
        return values
    for path in sorted(loc_root.rglob("*.yml")):
        if managed_path is not None and path == managed_path:
            lines, _, _, _ = read_text_lines(path)
            lines = remove_managed_block(lines, LOC_BEGIN, LOC_END)
            file_values = parse_localization_lines(lines, path)
        else:
            file_values, _, _, _, _ = parse_localization_file(path)
        for key, value in file_values.items():
            values.setdefault(key, value)
    return values


def remove_managed_block(lines, begin_marker, end_marker):
    kept = []
    inside = False
    for line in lines:
        if begin_marker in line:
            inside = True
            continue
        if end_marker in line:
            inside = False
            continue
        if not inside:
            kept.append(line)
    return kept


def write_localization(created_titles, report_rows):
    target_loc_path = TARGET / r"localization\replace\english\z_MB_titles_l_english.yml"
    source_loc = parse_localization_tree(MPE)
    existing_target_loc = target_localization_keys(TARGET, managed_path=target_loc_path)
    file_values, target_lines, newline, bom, trailing = parse_localization_file(target_loc_path)

    # Rebuild only our managed block, preserving user-owned localization.
    target_lines = remove_managed_block(target_lines, LOC_BEGIN, LOC_END)

    additions = []
    for title in sorted(created_titles):
        if title in existing_target_loc:
            report_rows.append(
                {
                    "title": title,
                    "status": "already_present",
                    "value": existing_target_loc[title]["value"],
                    "source_file": str(existing_target_loc[title]["path"]),
                    "line": existing_target_loc[title]["line"],
                }
            )
            continue
        source = source_loc.get(title)
        if not source:
            report_rows.append({"title": title, "status": "missing_source_localization"})
            continue
        additions.append((title, source["value"], source))
        report_rows.append(
            {
                "title": title,
                "status": "added",
                "value": source["value"],
                "source_file": str(source["path"]),
                "line": source["line"],
            }
        )

    if additions:
        while target_lines and target_lines[-1] == "":
            target_lines.pop()
        target_lines.append("")
        target_lines.append(LOC_BEGIN)
        for title, value, _ in additions:
            escaped = value.replace('"', '\\"')
            target_lines.append(f' {title}: "{escaped}"')
        target_lines.append(LOC_END)

    write_text_lines(target_loc_path, target_lines, newline, bom, trailing)


def row_status_counter(rows):
    return Counter(row.get("status", "") for row in rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    landed_path = TARGET / r"common\landed_titles\00_landed_titles.txt"
    loc_path = TARGET / r"localization\replace\english\z_MB_titles_l_english.yml"
    provinces_path = TARGET / r"map_data\provinces.png"
    definition_path = TARGET / r"map_data\definition.csv"

    before_landed_hash = sha256(landed_path)
    before_loc_hash = sha256(loc_path)
    before_provinces_hash = sha256(provinces_path)
    before_definition_hash = sha256(definition_path)

    id_rows = read_csv(OUT / "mpe_import_id_map.csv")
    id_map = {int(row["old_mpe_id"]): int(row["target_id"]) for row in id_rows}
    action_by_old = {int(row["old_mpe_id"]): row["target_action"] for row in id_rows}
    target_definition_ids = parse_definition_ids(definition_path)

    source_titles = parse_titles(MPE / r"common\landed_titles\00_landed_titles.txt")
    target_titles = parse_titles(landed_path)
    original_target_counties = set(target_titles["by_name"].keys())

    report_rows = []
    candidate_counties = defaultdict(dict)

    for old_id, new_id in sorted(id_map.items()):
        source_barony = source_titles["province_map"].get(old_id)
        if not source_barony:
            report_rows.append(
                {
                    "old_mpe_id": old_id,
                    "target_id": new_id,
                    "status": "missing_source_barony",
                    "target_action": action_by_old.get(old_id, ""),
                }
            )
            continue

        barony = source_barony["barony"]
        county = source_barony["county"]
        duchy = source_barony["duchy"]
        existing_barony_entries = target_titles["by_name"].get(barony, [])
        if existing_barony_entries:
            if len(existing_barony_entries) > 1:
                report_rows.append(
                    {
                        "old_mpe_id": old_id,
                        "target_id": new_id,
                        "barony": barony,
                        "county": county,
                        "duchy": duchy,
                        "status": "target_barony_duplicate_conflict",
                        "target_action": action_by_old.get(old_id, ""),
                    }
                )
                continue
            current_province, province_line = province_in_entry(target_titles["lines"], existing_barony_entries[0])
            status = "already_present" if current_province == new_id else "target_barony_existing_province_conflict"
            report_rows.append(
                {
                    "old_mpe_id": old_id,
                    "target_id": new_id,
                    "barony": barony,
                    "county": county,
                    "duchy": duchy,
                    "existing_province": current_province,
                    "line": province_line + 1 if province_line is not None else "",
                    "status": status,
                    "target_action": action_by_old.get(old_id, ""),
                }
            )
            continue

        if new_id not in target_definition_ids:
            report_rows.append(
                {
                    "old_mpe_id": old_id,
                    "target_id": new_id,
                    "barony": barony,
                    "county": county,
                    "duchy": duchy,
                    "status": "missing_target_definition_id",
                    "target_action": action_by_old.get(old_id, ""),
                }
            )
            continue

        county_entry = title_entry(source_titles, county)
        if not county_entry:
            report_rows.append(
                {
                    "old_mpe_id": old_id,
                    "target_id": new_id,
                    "barony": barony,
                    "county": county,
                    "duchy": duchy,
                    "status": "missing_source_county",
                    "target_action": action_by_old.get(old_id, ""),
                }
            )
            continue
        candidate_counties[county][old_id] = {
            "old_id": old_id,
            "new_id": new_id,
            "barony": barony,
            "county": county,
            "duchy": duchy,
            "entry": source_barony["entry"],
            "target_action": action_by_old.get(old_id, ""),
        }

    county_blocks = {}
    insertions = defaultdict(list)
    duchy_create_groups = defaultdict(list)
    created_titles = set()

    for county, seed_items in sorted(candidate_counties.items()):
        county_entry = title_entry(source_titles, county)
        if not county_entry:
            continue
        source_child_baronies = immediate_children(source_titles, county_entry, "b")
        included = []
        source_ids_in_county = []
        for child in source_child_baronies:
            old_id, _ = province_in_entry(source_titles["lines"], child)
            if old_id is None:
                report_rows.append({"barony": child["name"], "county": county, "status": "source_barony_no_province"})
                continue
            source_ids_in_county.append(old_id)
            if old_id not in id_map:
                report_rows.append(
                    {
                        "old_mpe_id": old_id,
                        "barony": child["name"],
                        "county": county,
                        "status": "county_child_removed_not_in_mpe_overlay",
                    }
                )
                continue
            new_id = id_map[old_id]
            if new_id not in target_definition_ids:
                report_rows.append(
                    {
                        "old_mpe_id": old_id,
                        "target_id": new_id,
                        "barony": child["name"],
                        "county": county,
                        "status": "county_child_removed_missing_target_definition_id",
                    }
                )
                continue
            existing_barony_entries = target_titles["by_name"].get(child["name"], [])
            if existing_barony_entries:
                existing_province = None
                if len(existing_barony_entries) == 1:
                    existing_province, _ = province_in_entry(target_titles["lines"], existing_barony_entries[0])
                status = "county_child_already_present" if existing_province == new_id else "county_child_existing_barony_conflict"
                report_rows.append(
                    {
                        "old_mpe_id": old_id,
                        "target_id": new_id,
                        "barony": child["name"],
                        "county": county,
                        "existing_province": existing_province,
                        "status": status,
                        "target_action": action_by_old.get(old_id, ""),
                    }
                )
                continue
            included.append(
                {
                    "old_id": old_id,
                    "new_id": new_id,
                    "barony": child["name"],
                    "entry": child,
                    "target_action": action_by_old.get(old_id, ""),
                }
            )

        if not included:
            report_rows.append(
                {
                    "county": county,
                    "duchy": county_entry["parents"].get("d", ""),
                    "status": "county_not_created_no_new_barony",
                    "note": "all source child baronies were skipped or already present",
                }
            )
            continue

        target_county_entries = target_titles["by_name"].get(county, [])
        block = make_county_block(source_titles, county_entry, included, original_target_counties, report_rows)
        county_blocks[county] = {
            "county": county,
            "county_start": county_entry["start"],
            "block": block,
            "source_ids": [item["old_id"] for item in included],
            "duchy": county_entry["parents"].get("d", ""),
            "kingdom": county_entry["parents"].get("k", ""),
            "empire": county_entry["parents"].get("e", ""),
            "included": included,
        }

        if len(target_county_entries) == 1:
            insertions[target_county_entries[0]["end"]].append(block[1:-1])
            for item in included:
                created_titles.add(item["barony"])
                report_rows.append(
                    {
                        "old_mpe_id": item["old_id"],
                        "target_id": item["new_id"],
                        "barony": item["barony"],
                        "county": county,
                        "duchy": county_entry["parents"].get("d", ""),
                        "status": "scheduled_barony_add_to_existing_county",
                        "target_action": item["target_action"],
                    }
                )
            continue

        if len(target_county_entries) > 1:
            report_rows.append(
                {
                    "county": county,
                    "status": "target_county_duplicate_conflict",
                    "target_county_count": len(target_county_entries),
                }
            )
            continue

        duchy = county_entry["parents"].get("d", "")
        duchy_entries = target_titles["by_name"].get(duchy, [])
        if len(duchy_entries) == 1:
            insertions[duchy_entries[0]["end"]].append(block)
            created_titles.add(county)
            for item in included:
                created_titles.add(item["barony"])
                report_rows.append(
                    {
                        "old_mpe_id": item["old_id"],
                        "target_id": item["new_id"],
                        "barony": item["barony"],
                        "county": county,
                        "duchy": duchy,
                        "status": "scheduled_county_create_under_existing_duchy",
                        "target_action": item["target_action"],
                    }
                )
            continue

        if len(duchy_entries) > 1:
            report_rows.append(
                {
                    "county": county,
                    "duchy": duchy,
                    "status": "target_duchy_duplicate_conflict",
                    "target_duchy_count": len(duchy_entries),
                }
            )
            continue

        duchy_create_groups[duchy].append(county_blocks[county])

    target_county_names = set(target_titles["by_name"].keys()) | {name for name in created_titles if name.startswith("c_")}

    for duchy, county_items in sorted(duchy_create_groups.items()):
        duchy_entry = title_entry(source_titles, duchy)
        if not duchy_entry:
            for county_item in county_items:
                report_rows.append({"county": county_item["county"], "duchy": duchy, "status": "missing_source_duchy"})
            continue
        parent_title = duchy_entry["parents"].get("k") or duchy_entry["parents"].get("e") or ""
        parent_entries = target_titles["by_name"].get(parent_title, [])
        if len(parent_entries) != 1:
            for county_item in county_items:
                report_rows.append(
                    {
                        "county": county_item["county"],
                        "duchy": duchy,
                        "parent_title": parent_title,
                        "status": "missing_or_ambiguous_target_parent_title",
                        "target_parent_count": len(parent_entries),
                        "note": "k/e parent was not auto-created",
                    }
                )
            continue

        d_block = make_duchy_block(source_titles, duchy_entry, county_items, target_county_names, report_rows)
        insertions[parent_entries[0]["end"]].append(d_block)
        created_titles.add(duchy)
        for county_item in county_items:
            created_titles.add(county_item["county"])
            for item in county_item["included"]:
                created_titles.add(item["barony"])
                report_rows.append(
                    {
                        "old_mpe_id": item["old_id"],
                        "target_id": item["new_id"],
                        "barony": item["barony"],
                        "county": county_item["county"],
                        "duchy": duchy,
                        "parent_title": parent_title,
                        "status": "scheduled_duchy_create_under_existing_parent",
                        "target_action": item["target_action"],
                    }
                )

    landed_lines = target_titles["lines"]
    for insert_index, blocks in sorted(insertions.items(), reverse=True):
        insert_lines = []
        for block in blocks:
            insert_lines.extend(block)
        landed_lines = landed_lines[:insert_index] + insert_lines + landed_lines[insert_index:]

    write_text_lines(landed_path, landed_lines, target_titles["newline"], target_titles["bom"], target_titles["trailing"])

    for row in report_rows:
        if row.get("status") == "scheduled_barony_add_to_existing_county":
            row["status"] = "added_barony_to_existing_county"
        elif row.get("status") == "scheduled_county_create_under_existing_duchy":
            row["status"] = "added_county_under_existing_duchy"
        elif row.get("status") == "scheduled_duchy_create_under_existing_parent":
            row["status"] = "added_duchy_under_existing_parent"

    loc_rows = []
    write_localization(created_titles, loc_rows)

    post_titles = parse_titles(landed_path)
    after_landed_hash = sha256(landed_path)
    after_loc_hash = sha256(loc_path)
    after_provinces_hash = sha256(provinces_path)
    after_definition_hash = sha256(definition_path)

    validation_rows = [
        {
            "status": "validation",
            "note": "landed_titles_brace_depth",
            "line": post_titles["final_depth"],
            "target_action": "pass" if post_titles["final_depth"] == 0 else "fail",
        },
        {
            "status": "validation",
            "note": "provinces_png_unchanged",
            "target_action": "pass" if before_provinces_hash == after_provinces_hash else "fail",
        },
        {
            "status": "validation",
            "note": "definition_csv_unchanged",
            "target_action": "pass" if before_definition_hash == after_definition_hash else "fail",
        },
    ]
    report_rows.extend(validation_rows)

    write_csv(
        REPORT_PATH,
        report_rows,
        [
            "old_mpe_id",
            "target_id",
            "barony",
            "county",
            "duchy",
            "parent_title",
            "related_title",
            "existing_province",
            "line",
            "status",
            "target_action",
            "target_county_count",
            "target_duchy_count",
            "target_parent_count",
            "title",
            "note",
        ],
    )
    write_csv(LOC_REPORT_PATH, loc_rows, ["title", "status", "value", "source_file", "line"])

    status_counts = row_status_counter(report_rows)
    loc_counts = row_status_counter(loc_rows)
    created_counties = sorted(title for title in created_titles if title.startswith("c_"))
    created_duchies = sorted(title for title in created_titles if title.startswith("d_"))
    created_baronies = sorted(title for title in created_titles if title.startswith("b_"))

    summary_lines = [
        "# MPE Add 1 Landed Hierarchy Import Summary",
        "",
        f"- created duchies: {len(created_duchies)}",
        f"- created counties: {len(created_counties)}",
        f"- created/imported baronies: {len(created_baronies)}",
        f"- localization added: {loc_counts.get('added', 0)}",
        f"- localization already present: {loc_counts.get('already_present', 0)}",
        f"- localization missing source: {loc_counts.get('missing_source_localization', 0)}",
        f"- landed_titles changed: {before_landed_hash != after_landed_hash}",
        f"- localization changed: {before_loc_hash != after_loc_hash}",
        f"- provinces.png unchanged: {before_provinces_hash == after_provinces_hash}",
        f"- definition.csv unchanged: {before_definition_hash == after_definition_hash}",
        f"- landed_titles brace depth: {post_titles['final_depth']}",
        "",
        "## Status Counts",
        "",
    ]
    for key, value in sorted(status_counts.items()):
        summary_lines.append(f"- {key}: {value}")
    summary_lines.extend(["", "## Created Duchies", ""])
    summary_lines.extend([f"- `{title}`" for title in created_duchies] or ["- none"])
    summary_lines.extend(["", "## Created Counties", ""])
    summary_lines.extend([f"- `{title}`" for title in created_counties] or ["- none"])
    SUMMARY_PATH.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    hafiza = PROJECT_ROOT / ".codex" / "memory" / "project_memory.md"
    hafiza_lines, hafiza_newline, hafiza_bom, _ = read_text_lines(hafiza)
    header = "## 2026-05-15 MPE Add 1 Landed Hierarchy Import"
    if header in hafiza_lines:
        start = hafiza_lines.index(header)
        end = len(hafiza_lines)
        for index in range(start + 1, len(hafiza_lines)):
            if hafiza_lines[index].startswith("## "):
                end = index
                break
        if start > 0 and hafiza_lines[start - 1] == "":
            start -= 1
        hafiza_lines = hafiza_lines[:start] + hafiza_lines[end:]
    hafiza_lines.extend(
        [
            "",
            header,
            "",
            "- Kullanici onceki `parent d_* yoksa otomatik d_ olusturmayalim` yaklasimini degistirdi.",
            "- Yeni kural: MPE province/title importunda eksik `c_*` county bloklari olusturulabilir; parent `d_*` duchy yoksa uygun mevcut `k_*`/`e_*` altinda `d_*` de olusturulabilir.",
            "- Sinir: parent `k_*`/`e_*` hedef landed_titles icinde yoksa otomatik root/subtree migration yapilmaz; satir rapora dusurulur.",
            "- `c_*` ve `d_*` acilis satirlarina `# Yusseter: MPE ... source provinces ...` yorumu eklenecek; `b_*` acilis satirlarinda `# Yusseter: MPE_<old_id>` yorumu korunacak.",
            "- Bu tur icin yeni arac: `.codex/works/tools/import_mpe_add_1_landed_hierarchy.py`.",
            "- Arac `map_data/provinces.png` ve `map_data/definition.csv` dosyalarini degistirmez; yalniz eksik landed_titles hiyerarsisini ve localization'i tamamlar.",
            f"- Olusturulan duchy: `{len(created_duchies)}`; county: `{len(created_counties)}`; barony: `{len(created_baronies)}`.",
            f"- Localization eklenen title: `{loc_counts.get('added', 0)}`; source localization bulunamayan: `{loc_counts.get('missing_source_localization', 0)}`.",
            f"- `provinces.png` unchanged: `{before_provinces_hash == after_provinces_hash}`; `definition.csv` unchanged: `{before_definition_hash == after_definition_hash}`.",
            f"- Landed_titles brace depth: `{post_titles['final_depth']}`.",
            "- Raporlar:",
            "  - `.codex/works/analysis/generated/mpe_import_add_1/mpe_landed_titles_hierarchy_import_report.csv`",
            "  - `.codex/works/analysis/generated/mpe_import_add_1/mpe_landed_titles_hierarchy_localization_report.csv`",
            "  - `.codex/works/analysis/generated/mpe_import_add_1/mpe_landed_titles_hierarchy_import_summary.md`",
        ]
    )
    write_text_lines(hafiza, hafiza_lines, hafiza_newline, hafiza_bom, True)

    print("MPE landed hierarchy import completed")
    print(f"created duchies: {len(created_duchies)}")
    print(f"created counties: {len(created_counties)}")
    print(f"created baronies: {len(created_baronies)}")
    print(f"localization added: {loc_counts.get('added', 0)}")
    print(f"summary: {SUMMARY_PATH}")

    failures = [row for row in validation_rows if row["target_action"] != "pass"]
    if post_titles["final_depth"] != 0 or failures:
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Abort as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        sys.exit(1)
