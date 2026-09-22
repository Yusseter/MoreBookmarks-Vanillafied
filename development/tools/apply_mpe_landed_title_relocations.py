from pathlib import Path
import csv
import hashlib
import re
from collections import defaultdict, Counter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TARGET = PROJECT_ROOT / "BookmarksGit"
MPE = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\1158310\3726274827")
OUT = PROJECT_ROOT / r"development\analysis\generated\mpe_import_add_1"

LANDED = TARGET / r"common\landed_titles\00_landed_titles.txt"
SOURCE_LANDED = MPE / r"common\landed_titles\00_landed_titles.txt"
HIERARCHY_REPORT = OUT / "mpe_landed_titles_hierarchy_import_report.csv"
COMPACT_DECISIONS = OUT / "mpe_landed_titles_conflict_decisions_compact.csv"
DETAILED_DECISIONS = OUT / "mpe_landed_titles_conflict_decisions.csv"
APPLY_REPORT = OUT / "mpe_landed_titles_relocation_apply_report.csv"
RELOCATION_PLAN = OUT / "mpe_landed_titles_relocation_plan.csv"
SUMMARY = OUT / "mpe_landed_titles_relocation_apply_summary.md"

MOVE_DECISION = "MOVE_BARONY_TO_MPE_PATH"
IGNORE_DECISION = "IGNORE_NOT_IN_MPE_ADD_1_OVERLAY"

TITLE_RE = re.compile(r"^\s*((?:e|k|d|c|b)_[A-Za-z0-9_'\-]+)\s*=\s*\{")
PROVINCE_RE = re.compile(r"\bprovince\s*=\s*(\d+)\b")


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
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
    trailing = text.endswith(("\n", "\r"))
    return text.splitlines(), newline, bom, trailing


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


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def as_int(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(str(value).strip())
    except ValueError:
        return None


def parse_province_token(value):
    if not value:
        return None
    left = str(value).split("|", 1)[0].strip()
    return as_int(left)


def parse_title_path(value):
    parts = [part.strip() for part in str(value or "").split(">") if part.strip()]
    result = {"path": " > ".join(parts)}
    for part in parts:
        if re.match(r"^[ekdcb]_", part):
            result[part[0]] = part
    return result


def parse_titles(path):
    lines, newline, bom, trailing = read_text_lines(path)
    entries = []
    by_name = defaultdict(list)
    province_map = {}
    stack = []
    depth = 0

    for index, line in enumerate(lines):
        code = strip_comment(line)
        match = TITLE_RE.search(code)
        if match:
            name = match.group(1)
            parents = {parent["tier"]: parent["name"] for parent in stack}
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

        province_match = PROVINCE_RE.search(code)
        if province_match:
            current_b = next((item for item in reversed(stack) if item["tier"] == "b"), None)
            if current_b:
                province_map[int(province_match.group(1))] = current_b

        new_depth = depth + code.count("{") - code.count("}")
        while stack and new_depth <= stack[-1]["depth"]:
            stack[-1]["end"] = index
            stack.pop()
        depth = new_depth

    for entry in entries:
        if entry["end"] is None:
            entry["end"] = len(lines) - 1

    return {
        "lines": lines,
        "newline": newline,
        "bom": bom,
        "trailing": trailing,
        "entries": entries,
        "by_name": by_name,
        "province_map": province_map,
        "final_depth": depth,
    }


def one_entry(data, title):
    entries = data["by_name"].get(title, [])
    if len(entries) == 1:
        return entries[0]
    return None


def entry_path(entry):
    if not entry:
        return ""
    parts = []
    for tier in ("e", "k", "d", "c"):
        parent = entry["parents"].get(tier)
        if parent:
            parts.append(parent)
    parts.append(entry["name"])
    return " > ".join(parts)


def province_in_entry(lines, entry):
    if not entry:
        return None
    for index in range(entry["start"], entry["end"] + 1):
        match = PROVINCE_RE.search(strip_comment(lines[index]))
        if match:
            return int(match.group(1))
    return None


def immediate_children(data, entry, tier=None):
    children = []
    for child in data["entries"]:
        if child["start"] <= entry["start"] or child["end"] >= entry["end"]:
            continue
        if child["depth"] != entry["depth"] + 1:
            continue
        if tier is not None and child["tier"] != tier:
            continue
        children.append(child)
    return children


def add_open_comment(line, old_id):
    comment = f"Yusseter: MPE_{old_id}"
    if "Yusseter: MPE_" in line:
        return line
    return re.sub(r"\{\s*(#.*)?$", "{ # " + comment, line, count=1)


def rewrite_first_province_line(block, new_id):
    out = []
    changed = False
    for line in block:
        if not changed and PROVINCE_RE.search(strip_comment(line)):
            out.append(re.sub(r"(\bprovince\s*=\s*)\d+", r"\g<1>" + str(new_id), line, count=1))
            changed = True
        else:
            out.append(line)
    if not changed and len(out) >= 1:
        indent_match = re.match(r"^(\s*)", out[0])
        indent = (indent_match.group(1) if indent_match else "") + "\t"
        out.insert(1, f"{indent}province = {new_id}")
    return out


def make_barony_block(source_data, target_data, item):
    source_entry = one_entry(source_data, item["barony"])
    source_label = "mpe_source"
    if source_entry:
        block = list(source_data["lines"][source_entry["start"] : source_entry["end"] + 1])
    else:
        source_label = "target_existing_fallback"
        block = list(target_data["lines"][item["current_entry"]["start"] : item["current_entry"]["end"] + 1])
    if block:
        block[0] = add_open_comment(block[0], item["old_id"])
    block = rewrite_first_province_line(block, item["target_id"])
    return block, source_label


def make_county_block(source_data, county_entry, county_items, target_data):
    source_lines = source_data["lines"]
    source_ids = "/".join(str(item["old_id"]) for item in sorted(county_items, key=lambda row: row["source_order"]))
    block = [re.sub(r"\{\s*(#.*)?$", "{ # Yusseter: MPE relocation county source provinces " + source_ids, source_lines[county_entry["start"]], count=1)]

    children = immediate_children(source_data, county_entry, "b")
    first_child = min((child["start"] for child in children), default=county_entry["end"])
    for index in range(county_entry["start"] + 1, first_child):
        line = source_lines[index]
        # County capital metadata can point at omitted baronies; skip b_* capital lines that are not in this reduced county.
        capital_match = re.search(r"\bcapital\s*=\s*(b_[A-Za-z0-9_'\-]+)\b", strip_comment(line))
        if capital_match and capital_match.group(1) not in {item["barony"] for item in county_items}:
            continue
        block.append(line)

    by_barony = {item["barony"]: item for item in county_items}
    for child in children:
        item = by_barony.get(child["name"])
        if not item:
            continue
        barony_block, source_label = make_barony_block(source_data, target_data, item)
        item["block_source"] = source_label
        block.extend(barony_block)
    block.append(source_lines[county_entry["end"]])
    return block


def load_plans(target_data, source_data):
    compact_rows = read_csv(COMPACT_DECISIONS)
    hierarchy_rows = read_csv(HIERARCHY_REPORT)

    ignore_baronies = {row["barony"] for row in compact_rows if row.get("your_decision") == IGNORE_DECISION}
    plans = {}
    report_by_barony = defaultdict(list)
    for row in hierarchy_rows:
        if row.get("barony"):
            report_by_barony[row["barony"]].append(row)

    def add_plan(barony, target_id, old_id, path_info, status, source):
        if not barony or barony in ignore_baronies:
            return
        if not target_id or not old_id:
            return
        current_entries = target_data["by_name"].get(barony, [])
        if len(current_entries) != 1:
            plans.setdefault(barony, {
                "barony": barony,
                "status": "blocked_current_barony_count",
                "block_reason": str(len(current_entries)),
                "sources": [],
            })["sources"].append(source)
            return
        target_county = path_info.get("c") or ""
        target_duchy = path_info.get("d") or ""
        if not target_county:
            return
        current_entry = current_entries[0]
        current_province = province_in_entry(target_data["lines"], current_entry)
        existing = plans.get(barony)
        if existing and existing.get("status") != "blocked_current_barony_count":
            if existing["target_county"] != target_county or existing["target_id"] != target_id:
                existing["status"] = "blocked_conflicting_plan"
                existing["block_reason"] = f"{existing['target_county']}/{existing['target_id']} vs {target_county}/{target_id}"
            existing["sources"].append(source)
            return
        source_entry = one_entry(source_data, barony)
        source_order = source_entry["start"] if source_entry else 10**9
        plans[barony] = {
            "barony": barony,
            "old_id": old_id,
            "target_id": target_id,
            "target_county": target_county,
            "target_duchy": target_duchy,
            "target_path": path_info.get("path", ""),
            "current_county": current_entry["parents"].get("c", ""),
            "current_path": entry_path(current_entry),
            "current_province": current_province,
            "current_entry": current_entry,
            "source_order": source_order,
            "status": "planned",
            "sources": [source],
            "source_statuses": [status],
        }

    for row in compact_rows:
        if row.get("your_decision") != MOVE_DECISION:
            continue
        path_info = parse_title_path(row.get("mpe_location", ""))
        add_plan(
            row.get("barony", ""),
            parse_province_token(row.get("final_target_province", "")),
            parse_province_token(row.get("mpe_province", "")),
            path_info,
            row.get("conflict_type", ""),
            row.get("decision_id", "compact"),
        )

    # The user rule also covers same-ID Add 1 baronies that were skipped as already_present but are in a different c_*.
    ignored_statuses = {"county_child_removed_not_in_mpe_overlay"}
    for row in hierarchy_rows:
        status = row.get("status", "")
        if status in ignored_statuses:
            continue
        barony = row.get("barony", "")
        county = row.get("county", "")
        if not barony.startswith("b_") or not county.startswith("c_"):
            continue
        if barony in ignore_baronies:
            continue
        current_entries = target_data["by_name"].get(barony, [])
        if len(current_entries) != 1:
            continue
        current_county = current_entries[0]["parents"].get("c", "")
        if current_county == county and status not in {"target_barony_existing_province_conflict", "county_child_existing_barony_conflict", "missing_source_barony"}:
            continue
        path_info = {"c": county, "d": row.get("duchy", ""), "path": ""}
        old_id = as_int(row.get("old_mpe_id"))
        target_id = as_int(row.get("target_id"))
        add_plan(barony, target_id, old_id, path_info, status, "hierarchy_report")

    return plans, ignore_baronies


def update_decision_csvs():
    for path in (COMPACT_DECISIONS, DETAILED_DECISIONS):
        if not path.exists():
            continue
        rows = read_csv(path)
        changed = False
        for row in rows:
            status = row.get("conflict_type") or row.get("source_status")
            if status == "county_child_removed_not_in_mpe_overlay":
                decision_field = "your_decision" if "your_decision" in row else "decision"
                if row.get(decision_field) != IGNORE_DECISION:
                    row[decision_field] = IGNORE_DECISION
                    changed = True
                if "notes" in row and not row.get("notes"):
                    row["notes"] = "User decision 2026-05-15: treat as non-existent for this Add 1 import."
                if "decision_notes" in row and not row.get("decision_notes"):
                    row["decision_notes"] = "User decision 2026-05-15: treat as non-existent for this Add 1 import."
            elif status in {"target_barony_existing_province_conflict", "county_child_existing_barony_conflict", "missing_source_barony"}:
                decision_field = "your_decision" if "your_decision" in row else "decision"
                if row.get(decision_field) != MOVE_DECISION:
                    row[decision_field] = MOVE_DECISION
                    changed = True
        if changed:
            write_csv(path, rows, rows[0].keys())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before_hash = sha256(LANDED)

    update_decision_csvs()

    target_data = parse_titles(LANDED)
    source_data = parse_titles(SOURCE_LANDED)
    plans, ignore_baronies = load_plans(target_data, source_data)

    apply_rows = []
    executable = []
    for barony, plan in sorted(plans.items()):
        if plan.get("status") != "planned":
            apply_rows.append({
                "barony": barony,
                "action": plan.get("status", "blocked"),
                "reason": plan.get("block_reason", ""),
                "sources": ";".join(plan.get("sources", [])),
            })
            continue
        target_county_entry = one_entry(target_data, plan["target_county"])
        target_duchy_entry = one_entry(target_data, plan["target_duchy"])
        source_county_entry = one_entry(source_data, plan["target_county"])
        if not target_county_entry and not target_duchy_entry:
            apply_rows.append({**plan, "action": "blocked_missing_target_county_and_duchy"})
            continue
        if not target_county_entry and not source_county_entry:
            apply_rows.append({**plan, "action": "blocked_missing_source_county_for_creation"})
            continue
        executable.append(plan)

    by_target_county = defaultdict(list)
    for item in executable:
        by_target_county[item["target_county"]].append(item)

    insertions = defaultdict(list)
    deletions = []

    for county, items in sorted(by_target_county.items()):
        target_county_entry = one_entry(target_data, county)
        if target_county_entry:
            for item in sorted(items, key=lambda row: row["source_order"]):
                block, source_label = make_barony_block(source_data, target_data, item)
                insertions[target_county_entry["end"]].append(block)
                deletions.append((item["current_entry"]["start"], item["current_entry"]["end"], item["barony"]))
                apply_rows.append({
                    "barony": item["barony"],
                    "action": "replace_or_move_barony_to_existing_county",
                    "old_id": item["old_id"],
                    "target_id": item["target_id"],
                    "current_province": item["current_province"],
                    "current_county": item["current_county"],
                    "target_county": item["target_county"],
                    "current_path": item["current_path"],
                    "target_path": item["target_path"],
                    "block_source": source_label,
                    "sources": ";".join(item.get("sources", [])),
                    "source_statuses": ";".join(item.get("source_statuses", [])),
                })
            continue

        # Missing county: create a reduced MPE county containing only planned moved baronies.
        source_county_entry = one_entry(source_data, county)
        duchy = items[0]["target_duchy"]
        target_duchy_entry = one_entry(target_data, duchy)
        county_block = make_county_block(source_data, source_county_entry, sorted(items, key=lambda row: row["source_order"]), target_data)
        insertions[target_duchy_entry["end"]].append(county_block)
        for item in sorted(items, key=lambda row: row["source_order"]):
            deletions.append((item["current_entry"]["start"], item["current_entry"]["end"], item["barony"]))
            apply_rows.append({
                "barony": item["barony"],
                "action": "move_barony_into_created_county",
                "old_id": item["old_id"],
                "target_id": item["target_id"],
                "current_province": item["current_province"],
                "current_county": item["current_county"],
                "target_county": item["target_county"],
                "current_path": item["current_path"],
                "target_path": item["target_path"],
                "block_source": item.get("block_source", "mpe_source"),
                "sources": ";".join(item.get("sources", [])),
                "source_statuses": ";".join(item.get("source_statuses", [])),
            })

    # Apply insertions and deletions on original indexes. Insertions are before closing braces.
    lines = list(target_data["lines"])
    operations = []
    for index, blocks in insertions.items():
        insert_lines = []
        for block in blocks:
            insert_lines.extend(block)
        operations.append((index, "insert", insert_lines, None))
    for start, end, barony in deletions:
        operations.append((start, "delete", None, end))

    for index, op, payload, end in sorted(operations, key=lambda row: (row[0], 0 if row[1] == "insert" else 1), reverse=True):
        if op == "insert":
            lines = lines[:index] + payload + lines[index:]
        else:
            lines = lines[:index] + lines[end + 1 :]

    write_text_lines(LANDED, lines, target_data["newline"], target_data["bom"], target_data["trailing"])

    post_data = parse_titles(LANDED)
    validation_rows = []
    validation_errors = []
    for row in apply_rows:
        barony = row.get("barony", "")
        if not barony or not row.get("target_county"):
            continue
        entries = post_data["by_name"].get(barony, [])
        province = province_in_entry(post_data["lines"], entries[0]) if len(entries) == 1 else None
        ok = len(entries) == 1 and entries[0]["parents"].get("c") == row.get("target_county") and province == as_int(row.get("target_id"))
        validation_rows.append({
            "barony": barony,
            "expected_county": row.get("target_county", ""),
            "actual_county": entries[0]["parents"].get("c", "") if len(entries) == 1 else "",
            "expected_province": row.get("target_id", ""),
            "actual_province": province or "",
            "entry_count": len(entries),
            "ok": "yes" if ok else "no",
        })
        if not ok:
            validation_errors.append(barony)

    province_to_baronies = defaultdict(list)
    for entry in post_data["entries"]:
        if entry["tier"] != "b":
            continue
        province = province_in_entry(post_data["lines"], entry)
        if province is not None:
            province_to_baronies[province].append(entry["name"])
    duplicate_province_rows = [
        {"province": province, "baronies": "|".join(names), "count": len(names)}
        for province, names in sorted(province_to_baronies.items())
        if len(names) > 1
    ]

    for barony in sorted(ignore_baronies):
        apply_rows.append({"barony": barony, "action": "ignored_not_in_mpe_add_1_overlay"})

    report_fields = [
        "barony", "action", "old_id", "target_id", "current_province", "current_county", "target_county",
        "current_path", "target_path", "block_source", "reason", "sources", "source_statuses"
    ]
    write_csv(APPLY_REPORT, apply_rows, report_fields)
    write_csv(RELOCATION_PLAN, validation_rows, ["barony", "expected_county", "actual_county", "expected_province", "actual_province", "entry_count", "ok"])
    if duplicate_province_rows:
        write_csv(OUT / "mpe_landed_titles_relocation_duplicate_provinces.csv", duplicate_province_rows, ["province", "baronies", "count"])

    after_hash = sha256(LANDED)
    action_counts = Counter(row.get("action", "") for row in apply_rows)

    summary = [
        "# MPE Landed Titles Relocation Apply Summary",
        "",
        f"- planned barony rows: `{len(plans)}`",
        f"- executable barony rows: `{len(executable)}`",
        f"- ignored not-in-overlay baronies: `{len(ignore_baronies)}`",
        f"- validation errors: `{len(validation_errors)}`",
        f"- duplicate province assignment rows: `{len(duplicate_province_rows)}`",
        f"- final landed_titles brace depth: `{post_data['final_depth']}`",
        f"- landed_titles changed: `{before_hash != after_hash}`",
        "",
        "## Action Counts",
        "",
    ]
    for action, count in sorted(action_counts.items()):
        summary.append(f"- `{action}`: `{count}`")
    if validation_errors:
        summary.extend(["", "## Validation Errors", ""])
        for barony in validation_errors:
            summary.append(f"- `{barony}`")
    if duplicate_province_rows:
        summary.extend(["", "## Duplicate Province Assignments", ""])
        for row in duplicate_province_rows[:50]:
            summary.append(f"- `{row['province']}`: `{row['baronies']}`")
    SUMMARY.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print("MPE landed title relocations applied")
    print(f"planned: {len(plans)}")
    print(f"executable: {len(executable)}")
    print(f"ignored: {len(ignore_baronies)}")
    print(f"validation_errors: {len(validation_errors)}")
    print(f"duplicate_province_rows: {len(duplicate_province_rows)}")
    print(f"brace_depth: {post_data['final_depth']}")
    print(f"summary: {SUMMARY}")


if __name__ == "__main__":
    main()
