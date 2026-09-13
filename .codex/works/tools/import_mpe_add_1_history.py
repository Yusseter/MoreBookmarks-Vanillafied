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

PROVINCE_HISTORY_OUT = TARGET / r"history\provinces\00_yb_MPE_PROVINCES.txt"
TITLE_HISTORY_OUT = TARGET / r"history\titles\00_YB_MPE.txt"

PROVINCE_REPORT = OUT / "mpe_province_history_import_report.csv"
TITLE_REPORT = OUT / "mpe_title_history_import_report.csv"
SUMMARY = OUT / "mpe_history_import_summary.md"


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
    try:
        text = data.decode("utf-8-sig" if bom else "utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
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


def parse_landed_titles(path):
    lines, newline, bom, trailing = read_text_lines(path)
    title_re = re.compile(r"^\s*((?:e|k|d|c|b)_[A-Za-z0-9_'\-]+)\s*=\s*\{")
    entries = []
    by_name = defaultdict(list)
    province_to_barony = {}
    barony_to_province = {}
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
            current_b = next((item for item in reversed(stack) if item["tier"] == "b"), None)
            if current_b:
                province_id = int(province_match.group(1))
                province_to_barony[province_id] = current_b["name"]
                barony_to_province[current_b["name"]] = province_id

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
        "entries": entries,
        "by_name": by_name,
        "province_to_barony": province_to_barony,
        "barony_to_province": barony_to_province,
        "final_depth": depth,
    }


def one_entry(data, title):
    entries = data["by_name"].get(title, [])
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


def direct_capital(data, entry, tier):
    # Only consider properties directly inside this title block.
    wanted = f"{tier}_"
    depth = entry["depth"] + 1
    current = depth
    for index in range(entry["start"] + 1, entry["end"]):
        code = strip_comment(data["lines"][index])
        match = re.search(r"\bcapital\s*=\s*(?:title:)?((?:e|k|d|c|b)_[A-Za-z0-9_'\-]+)\b", code)
        if current == depth and match and match.group(1).startswith(wanted):
            return match.group(1)
        current += code.count("{") - code.count("}")
    return ""


def county_capital_barony(data, county):
    county_entry = one_entry(data, county)
    if not county_entry:
        return ""
    explicit = direct_capital(data, county_entry, "b")
    if explicit:
        return explicit
    children = immediate_children(data, county_entry, "b")
    return children[0]["name"] if children else ""


def duchy_capital_county(data, duchy):
    duchy_entry = one_entry(data, duchy)
    if not duchy_entry:
        return ""
    explicit = direct_capital(data, duchy_entry, "c")
    if explicit:
        return explicit
    children = immediate_children(data, duchy_entry, "c")
    return children[0]["name"] if children else ""


def parse_numeric_history_file(path):
    lines, newline, bom, trailing = read_text_lines(path)
    blocks = {}
    header_re = re.compile(r"^\s*(\d+)\s*=\s*\{")
    index = 0
    while index < len(lines):
        code = strip_comment(lines[index])
        match = header_re.match(code)
        if not match:
            index += 1
            continue
        key = int(match.group(1))
        start = index
        depth = code.count("{") - code.count("}")
        while depth > 0 and index + 1 < len(lines):
            index += 1
            depth += strip_comment(lines[index]).count("{") - strip_comment(lines[index]).count("}")
        end = index
        blocks[key] = {"key": key, "start": start, "end": end, "lines": lines[start : end + 1], "path": path}
        index += 1
    return {"lines": lines, "newline": newline, "bom": bom, "trailing": trailing, "blocks": blocks}


def parse_title_history_files(root, exclude=None):
    exclude = exclude or set()
    title_re = re.compile(r"^\s*((?:e|k|d|c|b)_[A-Za-z0-9_'\-]+)\s*=\s*\{")
    out = defaultdict(list)
    for path in sorted(root.glob("*.txt")):
        if path in exclude:
            continue
        lines, _, _, _ = read_text_lines(path)
        index = 0
        while index < len(lines):
            code = strip_comment(lines[index])
            match = title_re.match(code)
            if not match:
                index += 1
                continue
            title = match.group(1)
            start = index
            depth = code.count("{") - code.count("}")
            while depth > 0 and index + 1 < len(lines):
                index += 1
                depth += strip_comment(lines[index]).count("{") - strip_comment(lines[index]).count("}")
            end = index
            out[title].append({"title": title, "start": start, "end": end, "lines": lines[start : end + 1], "path": path})
            index += 1
    return out


def choose_title_block(blocks):
    if not blocks:
        return None
    mpe_blocks = [block for block in blocks if "_MPE" in block["path"].stem]
    return sorted(mpe_blocks or blocks, key=lambda block: block["path"].as_posix())[0]


def top_level_culture_religion(block_lines):
    values = {}
    depth = 0
    for line in block_lines:
        code = strip_comment(line)
        match = re.match(r"^\s*(culture|religion|faith)\s*=\s*([A-Za-z0-9_:\-]+)\b", code)
        if depth == 1 and match:
            values[match.group(1)] = match.group(2)
        depth += code.count("{") - code.count("}")
    if "religion" not in values and "faith" in values:
        values["religion"] = values["faith"]
    return {key: values[key] for key in ("culture", "religion") if key in values}


def remove_culture_religion_lines(block_lines):
    filtered = [
        line
        for line in block_lines
        if not re.match(r"^\s*(culture|religion|faith)\s*=", strip_comment(line))
    ]
    return remove_empty_date_blocks(filtered)


def remove_empty_date_blocks(lines):
    out = []
    index = 0
    date_re = re.compile(r"^\s*\d+\.\d+\.\d+\s*=\s*\{")
    while index < len(lines):
        code = strip_comment(lines[index])
        if not date_re.match(code):
            out.append(lines[index])
            index += 1
            continue
        start = index
        depth = code.count("{") - code.count("}")
        while depth > 0 and index + 1 < len(lines):
            index += 1
            depth += strip_comment(lines[index]).count("{") - strip_comment(lines[index]).count("}")
        end = index
        body = [
            strip_comment(line).strip()
            for line in lines[start + 1 : end]
            if strip_comment(line).strip() and strip_comment(line).strip() not in {"{", "}"}
        ]
        if body:
            out.extend(lines[start : end + 1])
        index += 1
    return out


def rewrite_numeric_header(line, old_id, new_id):
    rewritten = re.sub(r"^(\s*)\d+(\s*=\s*\{)", rf"\g<1>{new_id}\g<2>", line, count=1)
    if "Yusseter:" not in rewritten:
        rewritten = rewritten.rstrip() + f" # Yusseter: MPE_{old_id}"
    return rewritten


def rewrite_title_header(line, new_title, note):
    rewritten = re.sub(
        r"^(\s*)((?:e|k|d|c|b)_[A-Za-z0-9_'\-]+)(\s*=\s*\{)",
        rf"\g<1>{new_title}\g<3>",
        line,
        count=1,
    )
    if "Yusseter:" not in rewritten:
        rewritten = rewritten.rstrip() + f" # Yusseter: {note}"
    return rewritten


def build_province_block(source_block, old_id, new_id, culture_religion):
    lines = list(source_block["lines"])
    lines[0] = rewrite_numeric_header(lines[0], old_id, new_id)
    lines = remove_culture_religion_lines(lines)
    if culture_religion:
        insert = []
        if "culture" in culture_religion:
            insert.append(f"\tculture = {culture_religion['culture']}")
        if "religion" in culture_religion:
            insert.append(f"\treligion = {culture_religion['religion']}")
        lines = lines[:1] + insert + lines[1:]
    return lines


def successful_import_baronies(id_map, source_titles, target_titles):
    rows = []
    for old_id, row in sorted(id_map.items()):
        if row["target_action"] == "target_same_id_skip":
            continue
        new_id = row["target_id"]
        source_barony = source_titles["province_to_barony"].get(old_id, "")
        if not source_barony:
            continue
        target_province = target_titles["barony_to_province"].get(source_barony)
        if target_province == new_id:
            entry = one_entry(target_titles, source_barony)
            rows.append(
                {
                    "old_id": old_id,
                    "new_id": new_id,
                    "barony": source_barony,
                    "county": entry["parents"].get("c", "") if entry else "",
                    "duchy": entry["parents"].get("d", "") if entry else "",
                }
            )
    return rows


def choose_same_duchy_donor(duchy, target_titles, new_counties, mb_history):
    duchy_entry = one_entry(target_titles, duchy)
    if not duchy_entry:
        return None
    candidates = []
    capital_county = duchy_capital_county(target_titles, duchy)
    if capital_county:
        candidates.append(capital_county)
    candidates.extend(child["name"] for child in immediate_children(target_titles, duchy_entry, "c"))
    seen = set()
    for county in candidates:
        if county in seen:
            continue
        seen.add(county)
        capital_barony = county_capital_barony(target_titles, county)
        province_id = target_titles["barony_to_province"].get(capital_barony)
        if province_id is None:
            continue
        block = mb_history["blocks"].get(province_id)
        if not block:
            continue
        values = top_level_culture_religion(block["lines"])
        if "culture" in values and "religion" in values:
            return {
                "donor_county": county,
                "donor_barony": capital_barony,
                "donor_province_id": province_id,
                "values": values,
                "source": "same_duchy_existing_00_MB_PROVINCES",
            }
    return None


def choose_same_duchy_mpe_donor(duchy, source_titles, source_history):
    duchy_entry = one_entry(source_titles, duchy)
    if not duchy_entry:
        return None
    candidates = []
    capital_county = duchy_capital_county(source_titles, duchy)
    if capital_county:
        candidates.append(capital_county)
    candidates.extend(child["name"] for child in immediate_children(source_titles, duchy_entry, "c"))
    seen = set()
    for county in candidates:
        if county in seen:
            continue
        seen.add(county)
        capital_barony = county_capital_barony(source_titles, county)
        old_id = source_titles["barony_to_province"].get(capital_barony)
        if old_id is None:
            continue
        block = source_history["blocks"].get(old_id)
        if not block:
            continue
        values = top_level_culture_religion(block["lines"])
        if "culture" in values and "religion" in values:
            return {
                "donor_county": county,
                "donor_barony": capital_barony,
                "donor_province_id": old_id,
                "values": values,
                "source": "fallback_same_duchy_mpe_source",
            }
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    before_province_out_hash = sha256(PROVINCE_HISTORY_OUT) if PROVINCE_HISTORY_OUT.exists() else "MISSING"
    before_title_out_hash = sha256(TITLE_HISTORY_OUT) if TITLE_HISTORY_OUT.exists() else "MISSING"

    source_titles = parse_landed_titles(MPE / r"common\landed_titles\00_landed_titles.txt")
    target_titles = parse_landed_titles(TARGET / r"common\landed_titles\00_landed_titles.txt")

    id_rows = read_csv(OUT / "mpe_import_id_map.csv")
    id_map = {
        int(row["old_mpe_id"]): {
            "target_id": int(row["target_id"]),
            "target_action": row["target_action"],
            "mpe_name": row.get("mpe_name", ""),
        }
        for row in id_rows
    }
    import_map = {
        old_id: row
        for old_id, row in id_map.items()
        if row["target_action"] != "target_same_id_skip"
    }

    hierarchy_rows = read_csv(OUT / "mpe_landed_titles_hierarchy_import_report.csv")
    new_counties = {
        row["county"]
        for row in hierarchy_rows
        if row["status"] in {"added_county_under_existing_duchy", "added_duchy_under_existing_parent"} and row["county"]
    }
    new_duchies = {
        row["duchy"]
        for row in hierarchy_rows
        if row["status"] == "added_duchy_under_existing_parent" and row["duchy"]
    }

    source_province_history = parse_numeric_history_file(MPE / r"history\provinces\z_MPE_province.txt")
    mb_history = parse_numeric_history_file(TARGET / r"history\provinces\00_MB_PROVINCES.txt")

    successful_baronies = successful_import_baronies(id_map, source_titles, target_titles)
    successful_by_new_id = {row["new_id"]: row for row in successful_baronies}
    capital_target_ids = set()
    county_to_capital_target_id = {}
    for row in successful_baronies:
        county = row["county"]
        capital_barony = county_capital_barony(target_titles, county)
        capital_id = target_titles["barony_to_province"].get(capital_barony)
        if capital_id is not None:
            county_to_capital_target_id[county] = capital_id
            if capital_id == row["new_id"]:
                capital_target_ids.add(row["new_id"])

    county_culture_cache = {}
    province_report = []
    province_blocks = []

    for old_id, row in sorted(import_map.items(), key=lambda item: item[1]["target_id"]):
        new_id = row["target_id"]
        source_block = source_province_history["blocks"].get(old_id)
        if not source_block:
            province_report.append(
                {
                    "old_mpe_id": old_id,
                    "target_id": new_id,
                    "status": "missing_source_province_history",
                }
            )
            continue

        success = successful_by_new_id.get(new_id)
        county = success["county"] if success else ""
        duchy = success["duchy"] if success else ""
        barony = success["barony"] if success else source_titles["province_to_barony"].get(old_id, "")
        is_capital = new_id in capital_target_ids
        culture_religion = {}
        donor_status = "not_county_capital"
        donor_county = ""
        donor_barony = ""
        donor_province_id = ""

        if is_capital:
            if county in new_counties:
                if county not in county_culture_cache:
                    donor = choose_same_duchy_donor(duchy, target_titles, new_counties, mb_history)
                    if donor:
                        county_culture_cache[county] = donor
                    else:
                        mpe_donor = choose_same_duchy_mpe_donor(duchy, source_titles, source_province_history)
                        if mpe_donor:
                            county_culture_cache[county] = mpe_donor
                        else:
                            fallback = top_level_culture_religion(source_block["lines"])
                            county_culture_cache[county] = {
                                "donor_county": "",
                                "donor_barony": "",
                                "donor_province_id": "",
                                "values": fallback,
                                "source": "fallback_mpe_source_no_same_duchy_donor",
                            }
                donor = county_culture_cache[county]
                culture_religion = donor["values"]
                donor_status = donor["source"]
                donor_county = donor["donor_county"]
                donor_barony = donor["donor_barony"]
                donor_province_id = donor["donor_province_id"]
            else:
                culture_religion = top_level_culture_religion(source_block["lines"])
                donor_status = "source_mpe_capital_province"

        block = build_province_block(source_block, old_id, new_id, culture_religion)
        province_blocks.extend(block)
        province_blocks.append("")
        province_report.append(
            {
                "old_mpe_id": old_id,
                "target_id": new_id,
                "barony": barony,
                "county": county,
                "duchy": duchy,
                "is_county_capital": "yes" if is_capital else "no",
                "culture": culture_religion.get("culture", ""),
                "religion": culture_religion.get("religion", ""),
                "culture_religion_status": donor_status,
                "donor_county": donor_county,
                "donor_barony": donor_barony,
                "donor_province_id": donor_province_id,
                "status": "added",
            }
        )

    if province_blocks and province_blocks[-1] == "":
        province_blocks.pop()
    write_text_lines(PROVINCE_HISTORY_OUT, province_blocks, "\r\n", False, True)

    source_title_blocks = parse_title_history_files(MPE / r"history\titles")
    target_title_blocks = parse_title_history_files(TARGET / r"history\titles", exclude={TITLE_HISTORY_OUT})

    title_report = []
    title_blocks = []

    requested_baronies = sorted({row["barony"] for row in successful_baronies if row["barony"]})
    requested_counties = sorted(new_counties)
    requested_duchies = sorted(new_duchies)

    def add_title_block(title, block, note, source_title, status, method):
        new_block = list(block["lines"])
        new_block[0] = rewrite_title_header(new_block[0], title, note)
        title_blocks.extend(new_block)
        title_blocks.append("")
        title_report.append(
            {
                "title": title,
                "source_title": source_title,
                "source_file": str(block["path"]),
                "status": status,
                "method": method,
            }
        )

    for title in requested_baronies:
        if title in target_title_blocks:
            title_report.append({"title": title, "status": "target_history_already_exists", "method": "barony"})
            continue
        source = choose_title_block(source_title_blocks.get(title, []))
        if not source:
            title_report.append({"title": title, "status": "missing_source_title_history", "method": "barony"})
            continue
        add_title_block(title, source, "MPE barony title history", title, "added", "source_barony")

    for title in requested_duchies:
        if title in target_title_blocks:
            title_report.append({"title": title, "status": "target_history_already_exists", "method": "duchy"})
            continue
        source = choose_title_block(source_title_blocks.get(title, []))
        if not source:
            title_report.append({"title": title, "status": "missing_source_title_history", "method": "duchy"})
            continue
        add_title_block(title, source, "MPE duchy title history", title, "added", "source_duchy")

    for title in requested_counties:
        if title in target_title_blocks:
            title_report.append({"title": title, "status": "target_history_already_exists", "method": "county"})
            continue
        entry = one_entry(target_titles, title)
        duchy = entry["parents"].get("d", "") if entry else ""
        donor_county = duchy_capital_county(target_titles, duchy) if duchy else ""
        method = "source_duchy_capital_county"
        source = choose_title_block(source_title_blocks.get(donor_county, [])) if donor_county else None
        source_title = donor_county
        if not source and donor_county:
            source = choose_title_block(target_title_blocks.get(donor_county, []))
            method = "target_duchy_capital_county"
        if not source:
            source = choose_title_block(source_title_blocks.get(title, []))
            source_title = title
            method = "source_own_county_fallback"
        if not source:
            title_report.append(
                {
                    "title": title,
                    "source_title": donor_county,
                    "status": "missing_source_title_history",
                    "method": "county",
                    "duchy": duchy,
                }
            )
            continue
        add_title_block(title, source, f"MPE county title history cloned from {source_title}", source_title, "added", method)

    if title_blocks and title_blocks[-1] == "":
        title_blocks.pop()
    write_text_lines(TITLE_HISTORY_OUT, title_blocks, "\r\n", False, True)

    after_province_out_hash = sha256(PROVINCE_HISTORY_OUT) if PROVINCE_HISTORY_OUT.exists() else "MISSING"
    after_title_out_hash = sha256(TITLE_HISTORY_OUT) if TITLE_HISTORY_OUT.exists() else "MISSING"

    write_csv(
        PROVINCE_REPORT,
        province_report,
        [
            "old_mpe_id",
            "target_id",
            "barony",
            "county",
            "duchy",
            "is_county_capital",
            "culture",
            "religion",
            "culture_religion_status",
            "donor_county",
            "donor_barony",
            "donor_province_id",
            "status",
        ],
    )
    write_csv(TITLE_REPORT, title_report, ["title", "source_title", "source_file", "status", "method", "duchy"])

    province_counts = Counter(row["status"] for row in province_report)
    culture_counts = Counter(row["culture_religion_status"] for row in province_report)
    title_counts = Counter(row["status"] for row in title_report)
    title_method_counts = Counter(row.get("method", "") for row in title_report if row["status"] == "added")

    summary_lines = [
        "# MPE Add 1 History Import Summary",
        "",
        f"- province history source blocks requested: {len(import_map)}",
        f"- province history blocks added: {province_counts.get('added', 0)}",
        f"- county-capital province blocks with culture/religion: {sum(1 for row in province_report if row['is_county_capital'] == 'yes' and row['culture'])}",
        f"- province history output changed: {before_province_out_hash != after_province_out_hash}",
        f"- title history output changed: {before_title_out_hash != after_title_out_hash}",
        "",
        "## Province Culture/Religion Source Counts",
        "",
    ]
    for key, value in sorted(culture_counts.items()):
        summary_lines.append(f"- {key}: {value}")
    summary_lines.extend(["", "## Title History Status Counts", ""])
    for key, value in sorted(title_counts.items()):
        summary_lines.append(f"- {key}: {value}")
    summary_lines.extend(["", "## Added Title History Method Counts", ""])
    for key, value in sorted(title_method_counts.items()):
        summary_lines.append(f"- {key}: {value}")
    summary_lines.extend(
        [
            "",
            f"- province report: `{PROVINCE_REPORT.relative_to(PROJECT_ROOT).as_posix()}`",
            f"- title report: `{TITLE_REPORT.relative_to(PROJECT_ROOT).as_posix()}`",
        ]
    )
    SUMMARY.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    hafiza = PROJECT_ROOT / ".codex" / "memory" / "project_memory.md"
    hafiza_lines, hafiza_newline, hafiza_bom, _ = read_text_lines(hafiza)
    header = "## 2026-05-15 MPE Add 1 History Import"
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
            "- MPE Add 1 icin province history artik `history/provinces/00_yb_MPE_PROVINCES.txt` icine ayri dosya olarak aktarildi.",
            "- Province history source: `C:\\Program Files (x86)\\Steam\\steamapps\\workshop\\content\\1158310\\3726274827\\history\\provinces\\z_MPE_province.txt`.",
            "- Province history importunda MPE old id header'lari final target id'lere cevrildi.",
            "- Province history kuralı: `culture` ve `religion` yalnizca county capital barony province'inde tutulur; county icinde explicit `capital = b_*` yoksa en ustteki `b_*` capital kabul edilir.",
            "- Yeni MPE county'lerinin capital province culture/religion'u once ayni `d_*` icindeki mevcut ve `00_MB_PROVINCES.txt`te tanimli capital-province donor'undan alinir; donor yoksa MPE source fallback kullanilir ve raporda gorunur.",
            "- Yeni MPE title history output dosyasi: `history/titles/00_YB_MPE.txt`.",
            "- Yeni MPE county title historyleri ayni duchy'nin capital county history'sinden clone edilir; kaynak yoksa kendi MPE county history'si fallback olarak kullanilir.",
            f"- Province history blocks added: `{province_counts.get('added', 0)}` / requested `{len(import_map)}`.",
            f"- Title history added: `{title_counts.get('added', 0)}`; missing source title history: `{title_counts.get('missing_source_title_history', 0)}`.",
            "- Landed_titles conflict havuzu bu islemden sonra ayrica ele alinacak; bu turda conflict barony kararlarina dokunulmadi.",
            "- Raporlar:",
            "  - `.codex/works/analysis/generated/mpe_import_add_1/mpe_history_import_summary.md`",
            "  - `.codex/works/analysis/generated/mpe_import_add_1/mpe_province_history_import_report.csv`",
            "  - `.codex/works/analysis/generated/mpe_import_add_1/mpe_title_history_import_report.csv`",
        ]
    )
    write_text_lines(hafiza, hafiza_lines, hafiza_newline, hafiza_bom, True)

    print("MPE history import completed")
    print(f"province history blocks added: {province_counts.get('added', 0)}")
    print(f"title history blocks added: {title_counts.get('added', 0)}")
    print(f"missing source title histories: {title_counts.get('missing_source_title_history', 0)}")
    print(f"summary: {SUMMARY}")


if __name__ == "__main__":
    try:
        main()
    except Abort as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        sys.exit(1)
