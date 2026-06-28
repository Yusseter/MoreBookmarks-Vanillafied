from pathlib import Path
from PIL import Image
import csv
import hashlib
import re
import sys
from collections import Counter, defaultdict

TARGET = Path(r"F:\Storage\Codding\git\Crusader Kings III\Yusseter MoreBookmarksPlus\BookmarksGit")
MPE = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\1158310\3726274827")
OVERLAY = TARGET / r"works\map_data_sources\MPE\provinces_mpe_add_1.png"
OUT = TARGET / r"works\analysis\generated\mpe_import_add_1"

MAP_OBJECT_FILES = [
    "activities.txt",
    "building_locators.txt",
    "combat_locators.txt",
    "player_stack_locators.txt",
    "siege_locators.txt",
    "special_building_locators.txt",
]

TERRAIN_BEGIN = "# Yusseter MPE ADD 1 TERRAIN BEGIN"
TERRAIN_END = "# Yusseter MPE ADD 1 TERRAIN END"
TECH_BEGIN = "# TECH PLACEHOLDER PROVINCES BEGIN"
TECH_END = "# TECH PLACEHOLDER PROVINCES END"


class Abort(Exception):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def tree_hash(root):
    h = hashlib.sha256()
    if not root.exists():
        return "MISSING"
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(p.relative_to(root).as_posix().encode("utf-8", "surrogateescape") + b"\0")
        h.update(bytes.fromhex(sha256(p)))
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


def write_csv(name, rows, fields):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_definition(path):
    lines, newline, bom, trailing = read_text_lines(path)
    by_id = {}
    by_rgb = defaultdict(list)
    rows = []
    line_by_id = {}
    for index, line in enumerate(lines):
        raw = line.lstrip("\ufeff").strip()
        if not raw or raw.startswith("#"):
            continue
        parts = raw.split(";")
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        try:
            province_id = int(parts[0])
            rgb = (int(parts[1]), int(parts[2]), int(parts[3]))
        except ValueError:
            continue
        rec = {
            "id": province_id,
            "rgb": rgb,
            "name": parts[4],
            "line_index": index,
            "line": line,
        }
        by_id[province_id] = rec
        by_rgb[rgb].append(rec)
        rows.append(rec)
        line_by_id[province_id] = index
    return {
        "path": path,
        "lines": lines,
        "newline": newline,
        "bom": bom,
        "trailing": trailing,
        "by_id": by_id,
        "by_rgb": by_rgb,
        "rows": rows,
        "line_by_id": line_by_id,
    }


def rgb_s(rgb):
    return f"{rgb[0]},{rgb[1]},{rgb[2]}"


def parse_default_ids(lines, only_tech=False):
    ids = set()
    records = []
    in_tech = False
    for index, line in enumerate(lines):
        if TECH_BEGIN in line:
            in_tech = True
            continue
        if TECH_END in line:
            in_tech = False
            continue
        if only_tech and not in_tech:
            continue
        match = re.search(r"\b([A-Za-z0-9_]+)\s*=\s*(RANGE|LIST)\s*\{([^}]*)\}", strip_comment(line))
        if not match:
            continue
        category, mode, body = match.group(1), match.group(2), match.group(3)
        nums = [int(x) for x in re.findall(r"\d+", body)]
        expanded = []
        if mode == "RANGE" and len(nums) >= 2:
            expanded = list(range(nums[0], nums[1] + 1))
        elif mode == "LIST":
            expanded = nums
        for province_id in expanded:
            ids.add(province_id)
            records.append(
                {
                    "line": index + 1,
                    "category": category,
                    "type": mode,
                    "id": province_id,
                }
            )
    return ids, records


def format_id_entries(ids, prefix="impassable_mountains"):
    ids = sorted(ids)
    ranges = []
    singles = []
    index = 0
    while index < len(ids):
        end = index
        while end + 1 < len(ids) and ids[end + 1] == ids[end] + 1:
            end += 1
        if end > index:
            ranges.append((ids[index], ids[end]))
        else:
            singles.append(ids[index])
        index = end + 1
    lines = [f"{prefix} = RANGE {{ {start} {end} }}" for start, end in ranges]
    for offset in range(0, len(singles), 20):
        chunk = singles[offset : offset + 20]
        lines.append(f"{prefix} = LIST {{ {' '.join(str(x) for x in chunk)} }}")
    return lines


def rewrite_default_tech_block(path, remove_ids):
    lines, newline, bom, trailing = read_text_lines(path)
    begin = next((i for i, line in enumerate(lines) if TECH_BEGIN in line), None)
    end = next((i for i, line in enumerate(lines) if TECH_END in line), None)
    if begin is None or end is None or begin >= end:
        raise Abort("default.map TECH placeholder block not found")
    tech_ids, _ = parse_default_ids(lines, only_tech=True)
    comments = []
    for line in lines[begin + 1 : end]:
        stripped = line.strip()
        if stripped.startswith("#"):
            comments.append(line)
    remaining = tech_ids - set(remove_ids)
    block = [lines[begin]] + comments + format_id_entries(remaining) + [lines[end]]
    write_text_lines(path, lines[:begin] + block + lines[end + 1 :], newline, bom, trailing)
    return sorted(tech_ids & set(remove_ids)), sorted(set(remove_ids) - tech_ids), len(tech_ids), len(remaining)


def parse_titles(path):
    lines, newline, bom, trailing = read_text_lines(path)
    title_re = re.compile(r"^\s*((?:e|k|d|c|b)_[A-Za-z0-9_']+)\s*=\s*\{")
    by_name = defaultdict(list)
    province_map = {}
    entries = []
    stack = []
    depth = 0
    for index, line in enumerate(lines):
        code = strip_comment(line)
        match = title_re.search(code)
        if match:
            name = match.group(1)
            entry = {
                "name": name,
                "tier": name[:1],
                "start": index,
                "end": None,
                "depth": depth,
                "parent_c": None,
            }
            for parent in reversed(stack):
                if parent["tier"] == "c":
                    entry["parent_c"] = parent["name"]
                    break
            stack.append(entry)
            by_name[name].append(entry)
            entries.append(entry)
        province_match = re.search(r"\bprovince\s*=\s*(\d+)\b", code)
        if province_match:
            current_b = next((entry for entry in reversed(stack) if entry["tier"] == "b"), None)
            current_c = next((entry for entry in reversed(stack) if entry["tier"] == "c"), None)
            if current_b:
                province_map[int(province_match.group(1))] = {
                    "barony": current_b["name"],
                    "county": current_c["name"] if current_c else "",
                    "line": index + 1,
                    "entry": current_b,
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
        "province_map": province_map,
        "entries": entries,
        "final_depth": depth,
    }


def province_in_title_block(lines, entry):
    for index in range(entry["start"], entry["end"] + 1):
        match = re.search(r"\bprovince\s*=\s*(\d+)\b", strip_comment(lines[index]))
        if match:
            return int(match.group(1)), index
    return None, None


def make_landed_block(source_lines, entry, old_id, new_id):
    block = list(source_lines[entry["start"] : entry["end"] + 1])
    for index, line in enumerate(block):
        if index == 0 and "# Yusseter" not in line:
            block[index] = re.sub(r"\{\s*(#.*)?$", "{ # Yusseter: MPE_" + str(old_id), line)
        if re.search(r"\bprovince\s*=\s*" + re.escape(str(old_id)) + r"\b", strip_comment(line)):
            block[index] = re.sub(r"(\bprovince\s*=\s*)\d+", r"\g<1>" + str(new_id), line, count=1)
    return block


def parse_terrain(path):
    lines, newline, bom, trailing = read_text_lines(path)
    rows = defaultdict(list)
    for index, line in enumerate(lines):
        match = re.search(r"^\s*(\d+)\s*=\s*([A-Za-z0-9_]+)", strip_comment(line))
        if match:
            rows[int(match.group(1))].append({"terrain": match.group(2), "line": index + 1})
    return {"lines": lines, "newline": newline, "bom": bom, "trailing": trailing, "rows": rows}


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


def find_locator_blocks(path):
    lines, newline, bom, trailing = read_text_lines(path)
    blocks = {}
    for index, line in enumerate(lines):
        match = re.search(r"\bid\s*=\s*(\d+)\b", strip_comment(line))
        if not match:
            continue
        province_id = int(match.group(1))
        start = index - 1
        while start >= 0 and "{" not in strip_comment(lines[start]):
            start -= 1
        if start < 0:
            continue
        depth = 0
        end = None
        for cursor in range(start, len(lines)):
            depth += strip_comment(lines[cursor]).count("{") - strip_comment(lines[cursor]).count("}")
            if depth == 0:
                end = cursor
                break
        if end is not None:
            blocks[province_id] = {"start": start, "end": end, "id_line": index}
    return {"lines": lines, "newline": newline, "bom": bom, "trailing": trailing, "blocks": blocks}


def normalize_block(lines):
    return [
        re.sub(r"\s+", " ", strip_comment(line)).strip()
        for line in lines
        if strip_comment(line).strip()
    ]


def make_locator_block(source_lines, block, old_id, new_id):
    out = list(source_lines[block["start"] : block["end"] + 1])
    if out and "# Yusseter" not in out[0]:
        out[0] = re.sub(r"\{\s*(#.*)?$", "{ # Yusseter: MPE_" + str(old_id), out[0])
    for index, line in enumerate(out):
        if re.search(r"\bid\s*=\s*" + re.escape(str(old_id)) + r"\b", strip_comment(line)):
            out[index] = re.sub(r"(\bid\s*=\s*)\d+", r"\g<1>" + str(new_id), line, count=1)
            break
    return out


def locator_insert_index(lines, blocks, target_id):
    larger = [(province_id, block["start"]) for province_id, block in blocks.items() if province_id > target_id]
    if larger:
        return min(larger, key=lambda pair: pair[0])[1]
    if len(lines) >= 2 and lines[-1].strip() == "}" and lines[-2].strip() == "}":
        return len(lines) - 2
    return len(lines)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    provinces_path = TARGET / r"map_data\provinces.png"
    test_root = TARGET / "test_files"
    before_provinces_hash = sha256(provinces_path) if provinces_path.exists() else "MISSING"
    before_test_hash = tree_hash(test_root)

    mpe_def = parse_definition(MPE / r"map_data\definition.csv")
    target_def = parse_definition(TARGET / r"map_data\definition.csv")
    default_lines, _, _, _ = read_text_lines(TARGET / r"map_data\default.map")
    tech_ids, _ = parse_default_ids(default_lines, only_tech=True)

    image = Image.open(OVERLAY).convert("RGB")
    overlay_rgbs = sorted({pixel for pixel in image.getdata() if pixel != (0, 0, 0)})

    rgb_inventory = []
    missing_mpe = []
    for rgb in overlay_rgbs:
        records = mpe_def["by_rgb"].get(rgb, [])
        if not records:
            missing_mpe.append(rgb)
            continue
        if len(records) > 1:
            raise Abort(f"MPE definition duplicate RGB for overlay color {rgb_s(rgb)}")
        record = records[0]
        rgb_inventory.append(
            {
                "rgb": rgb_s(rgb),
                "r": rgb[0],
                "g": rgb[1],
                "b": rgb[2],
                "mpe_id": record["id"],
                "mpe_name": record["name"],
            }
        )

    if missing_mpe:
        write_csv("mpe_rgb_inventory.csv", rgb_inventory, ["rgb", "r", "g", "b", "mpe_id", "mpe_name"])
        raise Abort(f"Overlay has {len(missing_mpe)} RGB values missing from MPE definition")

    placeholders = sorted(
        record["id"]
        for record in target_def["rows"]
        if record["id"] in tech_ids and record["name"].startswith("zz_placeholder_")
    )

    existing_rows = []
    new_needs = []
    fatal_conflicts = []
    for row in sorted(rgb_inventory, key=lambda item: int(item["mpe_id"])):
        rgb = tuple(int(part) for part in row["rgb"].split(","))
        target_records = target_def["by_rgb"].get(rgb, [])
        old_id = int(row["mpe_id"])
        if target_records:
            if len(target_records) > 1:
                fatal_conflicts.append(
                    {"rgb": row["rgb"], "mpe_id": old_id, "mpe_name": row["mpe_name"], "reason": "target_duplicate_rgb"}
                )
                continue
            target_record = target_records[0]
            if target_record["id"] == old_id:
                action = "target_same_id_skip"
            elif f"MPE_{old_id}" in target_record["name"]:
                action = "existing_manual_mpe_keep_target_id"
            else:
                action = "target_rgb_conflict_abort"
                fatal_conflicts.append(
                    {
                        "rgb": row["rgb"],
                        "mpe_id": old_id,
                        "mpe_name": row["mpe_name"],
                        "target_id": target_record["id"],
                        "target_name": target_record["name"],
                        "reason": action,
                    }
                )
            existing_rows.append(
                {
                    "rgb": row["rgb"],
                    "mpe_id": old_id,
                    "mpe_name": row["mpe_name"],
                    "target_id": target_record["id"],
                    "target_name": target_record["name"],
                    "action": action,
                }
            )
        else:
            new_needs.append(row)

    if fatal_conflicts:
        write_csv("mpe_rgb_inventory.csv", rgb_inventory, ["rgb", "r", "g", "b", "mpe_id", "mpe_name"])
        write_csv(
            "mpe_existing_target_rgb_check.csv",
            existing_rows + fatal_conflicts,
            ["rgb", "mpe_id", "mpe_name", "target_id", "target_name", "action", "reason"],
        )
        raise Abort(f"Target RGB conflicts found: {len(fatal_conflicts)}")

    if len(placeholders) < len(new_needs):
        raise Abort(f"Not enough TECH definition placeholders: need {len(new_needs)}, have {len(placeholders)}")

    id_map = []
    placeholder_iter = iter(placeholders)
    for row in sorted(rgb_inventory, key=lambda item: int(item["mpe_id"])):
        old_id = int(row["mpe_id"])
        rgb = tuple(int(part) for part in row["rgb"].split(","))
        target_records = target_def["by_rgb"].get(rgb, [])
        if target_records:
            target_record = target_records[0]
            if target_record["id"] == old_id:
                action = "target_same_id_skip"
                target_id = old_id
            else:
                action = "existing_manual_mpe_keep_target_id"
                target_id = target_record["id"]
        else:
            target_id = next(placeholder_iter)
            action = "new_placeholder_assignment"
        id_map.append(
            {
                "old_mpe_id": old_id,
                "target_id": target_id,
                "mpe_rgb": row["rgb"],
                "mpe_name": row["mpe_name"],
                "target_action": action,
            }
        )

    import_rows = [row for row in id_map if row["target_action"] != "target_same_id_skip"]
    old_to_new = {int(row["old_mpe_id"]): int(row["target_id"]) for row in import_rows}
    new_assignment_rows = [row for row in import_rows if row["target_action"] == "new_placeholder_assignment"]

    write_csv("mpe_rgb_inventory.csv", rgb_inventory, ["rgb", "r", "g", "b", "mpe_id", "mpe_name"])
    write_csv("mpe_existing_target_rgb_check.csv", existing_rows, ["rgb", "mpe_id", "mpe_name", "target_id", "target_name", "action"])
    write_csv("mpe_import_id_map.csv", id_map, ["old_mpe_id", "target_id", "mpe_rgb", "mpe_name", "target_action"])

    definition_changes = []
    for row in new_assignment_rows:
        old_id = int(row["old_mpe_id"])
        new_id = int(row["target_id"])
        rgb = tuple(int(part) for part in row["mpe_rgb"].split(","))
        if new_id not in target_def["line_by_id"]:
            raise Abort(f"Assigned target ID {new_id} is missing from target definition")
        line_index = target_def["line_by_id"][new_id]
        old_line = target_def["lines"][line_index]
        new_line = f"{new_id};{rgb[0]};{rgb[1]};{rgb[2]};{row['mpe_name']}, MPE_{old_id};x;"
        target_def["lines"][line_index] = new_line
        definition_changes.append(
            {
                "old_mpe_id": old_id,
                "target_id": new_id,
                "old_line": old_line,
                "new_line": new_line,
                "status": "rewritten_placeholder",
            }
        )
    for row in import_rows:
        if row["target_action"] == "existing_manual_mpe_keep_target_id":
            definition_changes.append(
                {
                    "old_mpe_id": row["old_mpe_id"],
                    "target_id": row["target_id"],
                    "old_line": "",
                    "new_line": "",
                    "status": "kept_existing_manual_definition",
                }
            )
    write_text_lines(target_def["path"], target_def["lines"], target_def["newline"], target_def["bom"], target_def["trailing"])
    write_csv("mpe_definition_changes.csv", definition_changes, ["old_mpe_id", "target_id", "old_line", "new_line", "status"])

    source_titles = parse_titles(MPE / r"common\landed_titles\00_landed_titles.txt")
    target_titles = parse_titles(TARGET / r"common\landed_titles\00_landed_titles.txt")
    landed_report = []
    insertions_by_county = defaultdict(list)
    for old_id, new_id in sorted(old_to_new.items()):
        source_barony = source_titles["province_map"].get(old_id)
        if not source_barony:
            landed_report.append({"old_mpe_id": old_id, "target_id": new_id, "status": "missing_source_barony"})
            continue
        barony = source_barony["barony"]
        county = source_barony["county"]
        existing_barony = target_titles["by_name"].get(barony, [])
        if existing_barony:
            if len(existing_barony) > 1:
                landed_report.append(
                    {
                        "old_mpe_id": old_id,
                        "target_id": new_id,
                        "barony": barony,
                        "county": county,
                        "status": "target_barony_duplicate_conflict",
                    }
                )
                continue
            current_province, province_line = province_in_title_block(target_titles["lines"], existing_barony[0])
            if current_province == new_id:
                status = "already_present"
            else:
                status = "target_barony_existing_province_conflict"
            landed_report.append(
                {
                    "old_mpe_id": old_id,
                    "target_id": new_id,
                    "barony": barony,
                    "county": county,
                    "existing_province": current_province,
                    "line": province_line + 1 if province_line is not None else "",
                    "status": status,
                }
            )
            continue
        county_entries = target_titles["by_name"].get(county, [])
        if len(county_entries) != 1:
            landed_report.append(
                {
                    "old_mpe_id": old_id,
                    "target_id": new_id,
                    "barony": barony,
                    "county": county,
                    "status": "missing_or_ambiguous_target_county",
                    "target_county_count": len(county_entries),
                }
            )
            continue
        block = make_landed_block(source_titles["lines"], source_barony["entry"], old_id, new_id)
        insertions_by_county[county_entries[0]["start"]].append(
            {
                "county_entry": county_entries[0],
                "block": block,
                "old_id": old_id,
                "new_id": new_id,
                "barony": barony,
                "county": county,
            }
        )
        landed_report.append({"old_mpe_id": old_id, "target_id": new_id, "barony": barony, "county": county, "status": "scheduled_add"})

    landed_lines = target_titles["lines"]
    for _, items in sorted(insertions_by_county.items(), key=lambda item: item[1][0]["county_entry"]["end"], reverse=True):
        county_entry = items[0]["county_entry"]
        insert_index = county_entry["end"]
        blocks = []
        for item in sorted(items, key=lambda value: value["old_id"]):
            blocks.extend(item["block"])
        landed_lines = landed_lines[:insert_index] + blocks + landed_lines[insert_index:]
    write_text_lines(TARGET / r"common\landed_titles\00_landed_titles.txt", landed_lines, target_titles["newline"], target_titles["bom"], target_titles["trailing"])
    for row in landed_report:
        if row.get("status") == "scheduled_add":
            row["status"] = "added"
    write_csv(
        "mpe_landed_titles_import_report.csv",
        landed_report,
        ["old_mpe_id", "target_id", "barony", "county", "status", "existing_province", "line", "target_county_count"],
    )

    source_terrain = parse_terrain(MPE / r"common\province_terrain\zz_MPE_province_terrain.txt")
    target_terrain_path = TARGET / r"common\province_terrain\00_province_terrain.txt"
    target_terrain = parse_terrain(target_terrain_path)
    terrain_lines = remove_managed_block(target_terrain["lines"], TERRAIN_BEGIN, TERRAIN_END)
    current_terrain_rows = defaultdict(list)
    for index, line in enumerate(terrain_lines):
        match = re.search(r"^\s*(\d+)\s*=\s*([A-Za-z0-9_]+)", strip_comment(line))
        if match:
            current_terrain_rows[int(match.group(1))].append({"terrain": match.group(2), "line": index + 1})
    terrain_report = []
    terrain_additions = []
    for old_id, new_id in sorted(old_to_new.items()):
        source_rows = source_terrain["rows"].get(old_id, [])
        if not source_rows:
            terrain_report.append({"old_mpe_id": old_id, "target_id": new_id, "status": "missing_source_terrain"})
            continue
        terrains = sorted({row["terrain"] for row in source_rows})
        terrain = terrains[0]
        if len(source_rows) > 1 and len(terrains) == 1:
            source_status = "source_duplicate_same"
        elif len(terrains) > 1:
            source_status = "source_duplicate_conflict"
        else:
            source_status = "source_single"
        target_rows = current_terrain_rows.get(new_id, [])
        if target_rows:
            target_terrains = sorted({row["terrain"] for row in target_rows})
            if terrain in target_terrains:
                terrain_report.append(
                    {
                        "old_mpe_id": old_id,
                        "target_id": new_id,
                        "terrain": terrain,
                        "status": "already_present",
                        "source_status": source_status,
                    }
                )
            else:
                terrain_report.append(
                    {
                        "old_mpe_id": old_id,
                        "target_id": new_id,
                        "terrain": terrain,
                        "existing_terrain": "|".join(target_terrains),
                        "status": "target_terrain_conflict",
                        "source_status": source_status,
                    }
                )
        else:
            terrain_additions.append((new_id, old_id, terrain))
            terrain_report.append(
                {
                    "old_mpe_id": old_id,
                    "target_id": new_id,
                    "terrain": terrain,
                    "status": "added",
                    "source_status": source_status,
                }
            )
    if terrain_additions:
        if terrain_lines and terrain_lines[-1].strip():
            terrain_lines.append("")
        terrain_lines.append(TERRAIN_BEGIN)
        for new_id, old_id, terrain in sorted(terrain_additions):
            terrain_lines.append(f"{new_id}={terrain} # Yusseter: MPE_{old_id}")
        terrain_lines.append(TERRAIN_END)
    write_text_lines(target_terrain_path, terrain_lines, target_terrain["newline"], target_terrain["bom"], target_terrain["trailing"])
    write_csv(
        "mpe_province_terrain_import_report.csv",
        terrain_report,
        ["old_mpe_id", "target_id", "terrain", "existing_terrain", "status", "source_status"],
    )

    map_object_report = []
    for filename in MAP_OBJECT_FILES:
        source_path = MPE / "gfx" / "map" / "map_object_data" / filename
        target_path = TARGET / "gfx" / "map" / "map_object_data" / filename
        source_locators = find_locator_blocks(source_path)
        target_locators = find_locator_blocks(target_path)
        grouped = defaultdict(list)
        for old_id, new_id in sorted(old_to_new.items()):
            source_block = source_locators["blocks"].get(old_id)
            if not source_block:
                map_object_report.append({"file": filename, "old_mpe_id": old_id, "target_id": new_id, "status": "missing_source_block"})
                continue
            new_block = make_locator_block(source_locators["lines"], source_block, old_id, new_id)
            target_block = target_locators["blocks"].get(new_id)
            if target_block:
                existing_block = target_locators["lines"][target_block["start"] : target_block["end"] + 1]
                status = "already_present" if normalize_block(existing_block) == normalize_block(new_block) else "target_block_exists_different"
                map_object_report.append({"file": filename, "old_mpe_id": old_id, "target_id": new_id, "status": status})
                continue
            insert_index = locator_insert_index(target_locators["lines"], target_locators["blocks"], new_id)
            grouped[insert_index].append((new_id, old_id, new_block))
            map_object_report.append({"file": filename, "old_mpe_id": old_id, "target_id": new_id, "status": "added"})
        lines = target_locators["lines"]
        for insert_index, blocks in sorted(grouped.items(), reverse=True):
            insert_lines = []
            for _, _, block in sorted(blocks):
                insert_lines.extend(block)
            lines = lines[:insert_index] + insert_lines + lines[insert_index:]
        write_text_lines(target_path, lines, target_locators["newline"], target_locators["bom"], target_locators["trailing"])
    write_csv("mpe_map_object_data_import_report.csv", map_object_report, ["file", "old_mpe_id", "target_id", "status"])

    remove_default_ids = set(old_to_new.values())
    removed_default_ids, missing_default_ids, tech_before_count, tech_after_count = rewrite_default_tech_block(
        TARGET / r"map_data\default.map",
        remove_default_ids,
    )
    post_default_lines, _, _, _ = read_text_lines(TARGET / r"map_data\default.map")
    _, all_default_records = parse_default_ids(post_default_lines, only_tech=False)
    default_rows = []
    for target_id in sorted(remove_default_ids):
        memberships = [record for record in all_default_records if record["id"] == target_id]
        if memberships:
            for membership in memberships:
                default_rows.append(
                    {
                        "target_id": target_id,
                        "status": "still_present_outside_or_other_block",
                        "category": membership["category"],
                        "line": membership["line"],
                    }
                )
        else:
            default_rows.append(
                {
                    "target_id": target_id,
                    "status": "removed_from_default_map_placeholder_scope",
                    "category": "",
                    "line": "",
                }
            )
    for target_id in missing_default_ids:
        default_rows.append(
            {
                "target_id": target_id,
                "status": "not_found_in_tech_placeholder_block_before_rewrite",
                "category": "",
                "line": "",
            }
        )
    write_csv("mpe_default_map_placeholder_update_report.csv", default_rows, ["target_id", "status", "category", "line"])

    allowed = {
        (MPE / r"map_data\definition.csv").relative_to(MPE).as_posix(): "handled_definition",
        (MPE / r"common\landed_titles\00_landed_titles.txt").relative_to(MPE).as_posix(): "handled_landed_titles",
        (MPE / r"common\province_terrain\zz_MPE_province_terrain.txt").relative_to(MPE).as_posix(): "handled_province_terrain",
        "history/provinces/z_MPE_province.txt": "report_only_history_provinces",
    }
    for filename in MAP_OBJECT_FILES:
        allowed[f"gfx/map/map_object_data/{filename}"] = "handled_map_object_data"

    usage_rows = []
    pattern = re.compile(r"(?<!\d)(" + "|".join(str(value) for value in sorted(old_to_new)) + r")(?!\d)")
    text_ext = {".txt", ".csv", ".map", ".gui", ".asset", ".info", ".mod", ".yml"}
    for path in sorted(MPE.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in text_ext:
            continue
        rel = path.relative_to(MPE).as_posix()
        try:
            source_lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except Exception:
            continue
        for line_number, line in enumerate(source_lines, 1):
            for match in pattern.finditer(line):
                old_id = int(match.group(1))
                usage_rows.append(
                    {
                        "file": rel,
                        "line": line_number,
                        "old_mpe_id": old_id,
                        "target_id": old_to_new[old_id],
                        "usage_status": allowed.get(rel, "unhandled_source_usage"),
                        "text": line.strip()[:240],
                    }
                )
    write_csv("mpe_unhandled_source_usages.csv", usage_rows, ["file", "line", "old_mpe_id", "target_id", "usage_status", "text"])

    validation = []
    post_def = parse_definition(TARGET / r"map_data\definition.csv")
    rgb_counter = Counter(record["rgb"] for record in post_def["rows"] if record["rgb"] != (0, 0, 0))
    duplicate_rgb = [rgb for rgb, count in rgb_counter.items() if count > 1]
    ids = sorted(post_def["by_id"])
    missing_ids = [province_id for province_id in range(ids[0], ids[-1] + 1) if province_id not in post_def["by_id"]]
    validation.append({"check": "definition_duplicate_nonblack_rgb", "status": "pass" if not duplicate_rgb else "fail", "detail": len(duplicate_rgb)})
    validation.append({"check": "definition_contiguous_ids", "status": "pass" if not missing_ids else "fail", "detail": len(missing_ids)})
    post_titles = parse_titles(TARGET / r"common\landed_titles\00_landed_titles.txt")
    validation.append({"check": "landed_titles_brace_depth", "status": "pass" if post_titles["final_depth"] == 0 else "fail", "detail": post_titles["final_depth"]})
    missing_import_definition_ids = [target_id for target_id in remove_default_ids if target_id not in post_def["by_id"]]
    validation.append(
        {
            "check": "import_target_ids_exist_in_definition",
            "status": "pass" if not missing_import_definition_ids else "fail",
            "detail": len(missing_import_definition_ids),
        }
    )
    post_default_lines, _, _, _ = read_text_lines(TARGET / r"map_data\default.map")
    post_tech_ids, _ = parse_default_ids(post_default_lines, only_tech=True)
    still_in_tech = sorted(remove_default_ids & post_tech_ids)
    validation.append(
        {
            "check": "import_target_ids_not_in_tech_placeholder_block",
            "status": "pass" if not still_in_tech else "fail",
            "detail": len(still_in_tech),
        }
    )
    after_provinces_hash = sha256(provinces_path) if provinces_path.exists() else "MISSING"
    after_test_hash = tree_hash(test_root)
    validation.append(
        {
            "check": "provinces_png_unchanged",
            "status": "pass" if before_provinces_hash == after_provinces_hash else "fail",
            "detail": after_provinces_hash,
        }
    )
    validation.append(
        {
            "check": "test_files_tree_unchanged",
            "status": "pass" if before_test_hash == after_test_hash else "fail",
            "detail": after_test_hash,
        }
    )
    write_csv("mpe_import_validation.csv", validation, ["check", "status", "detail"])

    summary_counts = {
        "overlay_nonblack_rgb": len(overlay_rgbs),
        "target_existing_rgb": len(existing_rows),
        "target_same_id_skip": sum(1 for row in id_map if row["target_action"] == "target_same_id_skip"),
        "existing_manual_mpe": sum(1 for row in id_map if row["target_action"] == "existing_manual_mpe_keep_target_id"),
        "new_placeholder_assignments": len(new_assignment_rows),
        "import_old_id_count": len(import_rows),
        "definition_rewritten_placeholders": sum(1 for row in definition_changes if row["status"] == "rewritten_placeholder"),
        "landed_titles_added": sum(1 for row in landed_report if row.get("status") == "added"),
        "terrain_added": sum(1 for row in terrain_report if row.get("status") == "added"),
        "map_object_added": sum(1 for row in map_object_report if row.get("status") == "added"),
        "default_tech_removed_ids": len(removed_default_ids),
        "unhandled_source_usage_rows": sum(1 for row in usage_rows if row["usage_status"] == "unhandled_source_usage"),
        "history_provinces_report_only_rows": sum(1 for row in usage_rows if row["usage_status"] == "report_only_history_provinces"),
        "validation_failures": sum(1 for row in validation if row["status"] != "pass"),
    }
    summary_lines = ["# MPE Import Add 1 Summary", ""]
    summary_lines.extend(f"- {key}: {value}" for key, value in summary_counts.items())
    summary_lines.extend(
        [
            "",
            f"- provinces_png_unchanged: {before_provinces_hash == after_provinces_hash}",
            f"- test_files_tree_unchanged: {before_test_hash == after_test_hash}",
        ]
    )
    (OUT / "mpe_import_add_1_summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    hafiza = TARGET / "hafiza.md"
    hafiza_lines, hafiza_newline, hafiza_bom, _ = read_text_lines(hafiza)
    header = "## 2026-05-15 MPE Province Add 1 Import"
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
            "- MPE kaynagi: `C:\\Program Files (x86)\\Steam\\steamapps\\workshop\\content\\1158310\\3726274827`.",
            "- Overlay kaynak: `works/map_data_sources/MPE/provinces_mpe_add_1.png`.",
            "- Bu turda `map_data/provinces.png` degistirilmedi; kullanici provinces.png final guncellemesini sonda yapacak.",
            "- Bu turda `test_files` senkronu yapilmadi.",
            f"- Overlay non-black RGB: `{summary_counts['overlay_nonblack_rgb']}`; MPE definition eksigi: `0`.",
            f"- Target definition icinde zaten olan RGB: `{summary_counts['target_existing_rgb']}`; same-id skip: `{summary_counts['target_same_id_skip']}`; mevcut manuel MPE mapping: `{summary_counts['existing_manual_mpe']}`.",
            f"- Yeni TECH placeholder assignment: `{summary_counts['new_placeholder_assignments']}`; import/remap toplam old MPE id: `{summary_counts['import_old_id_count']}`.",
            "- Yeni ID secimi sadece `map_data/default.map` icindeki `# TECH PLACEHOLDER PROVINCES` blogunda bulunan `zz_placeholder_*` definition satirlarindan yapildi.",
            f"- `map_data/definition.csv` icinde `{summary_counts['definition_rewritten_placeholders']}` placeholder MPE definition satirina cevrildi.",
            f"- `common/landed_titles/00_landed_titles.txt` icine `{summary_counts['landed_titles_added']}` MPE barony block'u eklendi; mevcut baronyler tekrar eklenmedi.",
            f"- `common/province_terrain/00_province_terrain.txt` icine `{summary_counts['terrain_added']}` MPE terrain satiri eklendi.",
            f"- 6 `gfx/map/map_object_data` dosyasina toplam `{summary_counts['map_object_added']}` locator/object block'u eklendi.",
            f"- `map_data/default.map` TECH placeholder blogundan `{summary_counts['default_tech_removed_ids']}` import target id cikarildi.",
            "- `history/provinces/z_MPE_province.txt` bu turda otomatik import edilmedi; source usage raporunda report-only tutuldu.",
            "- Rapor klasoru: `works/analysis/generated/mpe_import_add_1/`.",
            f"- Validation failures: `{summary_counts['validation_failures']}`; `provinces.png` unchanged: `{before_provinces_hash == after_provinces_hash}`; `test_files` unchanged: `{before_test_hash == after_test_hash}`.",
        ]
    )
    write_text_lines(hafiza, hafiza_lines, hafiza_newline, hafiza_bom, True)

    print("MPE import completed")
    for key, value in summary_counts.items():
        print(f"{key}: {value}")
    print(f"summary: {OUT / 'mpe_import_add_1_summary.md'}")
    if summary_counts["validation_failures"]:
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Abort as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        sys.exit(1)
