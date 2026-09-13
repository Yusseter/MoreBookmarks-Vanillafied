from pathlib import Path
import csv
import hashlib
import re
from collections import Counter, defaultdict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TARGET = PROJECT_ROOT / "BookmarksGit"
MPE = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\1158310\3726274827")
OUT = PROJECT_ROOT / r".codex\works\analysis\generated\mpe_import_add_1"

SOURCE_REPORT = OUT / "mpe_landed_titles_hierarchy_import_report.csv"
DECISIONS = OUT / "mpe_landed_titles_conflict_decisions.csv"
SUMMARY = OUT / "mpe_landed_titles_conflict_decisions_summary.md"

CONFLICT_STATUSES = {
    "target_barony_existing_province_conflict",
    "county_child_existing_barony_conflict",
    "missing_source_barony",
    "county_child_removed_not_in_mpe_overlay",
}


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


def parse_definition(path):
    lines, _, _, _ = read_text_lines(path)
    by_id = {}
    by_name = defaultdict(list)
    for line in lines:
        raw = line.lstrip("\ufeff").strip()
        if not raw or raw.startswith("#"):
            continue
        parts = raw.split(";")
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        try:
            province_id = int(parts[0])
            rgb = f"{int(parts[1])},{int(parts[2])},{int(parts[3])}"
        except ValueError:
            continue
        row = {"id": province_id, "rgb": rgb, "name": parts[4]}
        by_id[province_id] = row
        by_name[parts[4]].append(row)
    return {"by_id": by_id, "by_name": by_name}


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


def one_entry(data, title):
    entries = data["by_name"].get(title, [])
    if len(entries) == 1:
        return entries[0]
    return None


def parse_numeric_history_ids(path):
    if not path.exists():
        return set()
    lines, _, _, _ = read_text_lines(path)
    ids = set()
    for line in lines:
        match = re.match(r"^\s*(\d+)\s*=\s*\{", strip_comment(line))
        if match:
            ids.add(int(match.group(1)))
    return ids


def parse_title_history_titles(path):
    if not path.exists():
        return set()
    lines, _, _, _ = read_text_lines(path)
    titles = set()
    for line in lines:
        match = re.match(r"^\s*((?:e|k|d|c|b)_[A-Za-z0-9_'\-]+)\s*=\s*\{", strip_comment(line))
        if match:
            titles.add(match.group(1))
    return titles


def source_history_comment_for_id(path, province_id):
    if not province_id:
        return ""
    lines, _, _, _ = read_text_lines(path)
    pattern = re.compile(r"^\s*" + re.escape(str(province_id)) + r"\s*=\s*\{\s*(#.*)?$")
    for line in lines:
        match = pattern.match(line)
        if match:
            return (match.group(1) or "").strip()
    return ""


def as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def suggested_action(status):
    if status in {"target_barony_existing_province_conflict", "county_child_existing_barony_conflict"}:
        return "manual_decide_keep_existing_or_retarget_or_rename_mpe_barony"
    if status == "missing_source_barony":
        return "manual_source_title_needed_or_history_only_keep"
    if status == "county_child_removed_not_in_mpe_overlay":
        return "defer_until_overlay_expands_or_manual_add_definition_province"
    return "manual_review"


def review_priority(status):
    if status == "missing_source_barony":
        return "high"
    if status in {"target_barony_existing_province_conflict", "county_child_existing_barony_conflict"}:
        return "high"
    if status == "county_child_removed_not_in_mpe_overlay":
        return "medium"
    return "medium"


def options_for_status(status):
    if status in {"target_barony_existing_province_conflict", "county_child_existing_barony_conflict"}:
        return "keep_existing_target_barony|retarget_existing_barony_to_mpe_final_id|create_or_rename_mpe_barony|drop_mpe_title_link_keep_history_only"
    if status == "missing_source_barony":
        return "create_manual_barony_block|leave_province_history_only|drop_from_mpe_title_scope"
    if status == "county_child_removed_not_in_mpe_overlay":
        return "leave_removed|expand_overlay_and_definition|manual_include_existing_province"
    return "manual_review"


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    before_hashes = {
        "landed_titles": sha256(TARGET / r"common\landed_titles\00_landed_titles.txt"),
    }

    source_rows = [row for row in read_csv(SOURCE_REPORT) if row.get("status") in CONFLICT_STATUSES]
    id_map_rows = read_csv(OUT / "mpe_import_id_map.csv")
    id_map = {as_int(row["old_mpe_id"]): row for row in id_map_rows if as_int(row["old_mpe_id"]) is not None}

    target_def = parse_definition(TARGET / r"map_data\definition.csv")
    mpe_def = parse_definition(MPE / r"map_data\definition.csv")
    target_titles = parse_landed_titles(TARGET / r"common\landed_titles\00_landed_titles.txt")
    source_titles = parse_landed_titles(MPE / r"common\landed_titles\00_landed_titles.txt")
    yb_history_ids = parse_numeric_history_ids(TARGET / r"history\provinces\00_yb_MPE_PROVINCES.txt")
    mb_history_ids = parse_numeric_history_ids(TARGET / r"history\provinces\00_MB_PROVINCES.txt")
    yb_title_history = parse_title_history_titles(TARGET / r"history\titles\00_YB_MPE.txt")
    source_province_history = MPE / r"history\provinces\z_MPE_province.txt"

    duplicate_key_counts = Counter()
    for row in source_rows:
        key = (row.get("status", ""), row.get("barony", ""), row.get("target_id", ""), row.get("existing_province", ""))
        duplicate_key_counts[key] += 1

    decisions = []
    for index, row in enumerate(source_rows, 1):
        status = row.get("status", "")
        old_id = as_int(row.get("old_mpe_id"))
        target_id = as_int(row.get("target_id"))
        existing_province = as_int(row.get("existing_province"))
        barony = row.get("barony") or (source_titles["province_to_barony"].get(old_id, "") if old_id is not None else "")
        source_entry = one_entry(source_titles, barony) if barony else None
        target_entry = one_entry(target_titles, barony) if barony else None
        target_current_province = target_titles["barony_to_province"].get(barony, "")
        if existing_province is None and isinstance(target_current_province, int):
            existing_province = target_current_province

        target_def_row = target_def["by_id"].get(target_id) if target_id is not None else None
        old_def_row = mpe_def["by_id"].get(old_id) if old_id is not None else None
        existing_def_row = target_def["by_id"].get(existing_province) if existing_province is not None else None
        source_comment = source_history_comment_for_id(source_province_history, old_id) if old_id is not None else ""
        dup_key = (status, row.get("barony", ""), row.get("target_id", ""), row.get("existing_province", ""))

        decisions.append(
            {
                "decision_id": f"MPE_LT_CONFLICT_{index:03d}",
                "source_status": status,
                "review_priority": review_priority(status),
                "safe_to_auto_apply": "no",
                "suggested_action": suggested_action(status),
                "decision_options": options_for_status(status),
                "old_mpe_id": old_id if old_id is not None else "",
                "target_id": target_id if target_id is not None else "",
                "old_mpe_name": old_def_row["name"] if old_def_row else "",
                "target_definition_name": target_def_row["name"] if target_def_row else "",
                "target_definition_rgb": target_def_row["rgb"] if target_def_row else "",
                "barony": barony,
                "source_title_path": entry_path(source_entry),
                "target_title_path": entry_path(target_entry),
                "source_county": source_entry["parents"].get("c", "") if source_entry else row.get("county", ""),
                "source_duchy": source_entry["parents"].get("d", "") if source_entry else row.get("duchy", ""),
                "target_current_county": target_entry["parents"].get("c", "") if target_entry else "",
                "target_current_duchy": target_entry["parents"].get("d", "") if target_entry else "",
                "target_existing_province": existing_province if existing_province is not None else "",
                "target_existing_province_name": existing_def_row["name"] if existing_def_row else "",
                "target_existing_province_rgb": existing_def_row["rgb"] if existing_def_row else "",
                "target_existing_line": (target_entry["start"] + 1) if target_entry else "",
                "source_history_comment": source_comment,
                "target_id_has_yb_mpe_province_history": "yes" if target_id in yb_history_ids else "no",
                "existing_id_has_mb_province_history": "yes" if existing_province in mb_history_ids else "no",
                "barony_has_yb_mpe_title_history": "yes" if barony in yb_title_history else "no",
                "target_action_from_id_map": id_map.get(old_id, {}).get("target_action", "") if old_id is not None else "",
                "duplicate_conflict_key_count": duplicate_key_counts[dup_key],
                "decision": "",
                "decision_notes": "",
            }
        )

    fields = [
        "decision_id",
        "source_status",
        "review_priority",
        "safe_to_auto_apply",
        "suggested_action",
        "decision_options",
        "old_mpe_id",
        "target_id",
        "old_mpe_name",
        "target_definition_name",
        "target_definition_rgb",
        "barony",
        "source_title_path",
        "target_title_path",
        "source_county",
        "source_duchy",
        "target_current_county",
        "target_current_duchy",
        "target_existing_province",
        "target_existing_province_name",
        "target_existing_province_rgb",
        "target_existing_line",
        "source_history_comment",
        "target_id_has_yb_mpe_province_history",
        "existing_id_has_mb_province_history",
        "barony_has_yb_mpe_title_history",
        "target_action_from_id_map",
        "duplicate_conflict_key_count",
        "decision",
        "decision_notes",
    ]
    write_csv(DECISIONS, decisions, fields)

    status_counts = Counter(row["source_status"] for row in decisions)
    action_counts = Counter(row["suggested_action"] for row in decisions)
    priority_counts = Counter(row["review_priority"] for row in decisions)
    unique_barony_count = len({row["barony"] for row in decisions if row["barony"]})
    duplicate_report_rows = sum(1 for row in decisions if int(row["duplicate_conflict_key_count"]) > 1)
    after_hashes = {
        "landed_titles": sha256(TARGET / r"common\landed_titles\00_landed_titles.txt"),
    }

    summary_lines = [
        "# MPE Landed Titles Conflict Decisions Summary",
        "",
        f"- conflict rows: {len(decisions)}",
        f"- unique conflict baronies: {unique_barony_count}",
        f"- duplicate-key report rows: {duplicate_report_rows}",
        f"- safe_to_auto_apply yes rows: 0",
        f"- landed_titles unchanged: {before_hashes['landed_titles'] == after_hashes['landed_titles']}",
        "",
        "## Status Counts",
        "",
    ]
    for key, value in sorted(status_counts.items()):
        summary_lines.append(f"- {key}: {value}")
    summary_lines.extend(["", "## Suggested Action Counts", ""])
    for key, value in sorted(action_counts.items()):
        summary_lines.append(f"- {key}: {value}")
    summary_lines.extend(["", "## Priority Counts", ""])
    for key, value in sorted(priority_counts.items()):
        summary_lines.append(f"- {key}: {value}")
    summary_lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `target_barony_existing_province_conflict` and `county_child_existing_barony_conflict` require a manual title/province identity decision.",
            "- `missing_source_barony` has no source landed-title block in MPE for the imported province and must not be guessed from history comments alone.",
            "- `county_child_removed_not_in_mpe_overlay` was intentionally left out because its source province was not part of the Add 1 overlay/import ID map.",
            f"- decision table: `{DECISIONS.relative_to(PROJECT_ROOT).as_posix()}`",
        ]
    )
    SUMMARY.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    hafiza = PROJECT_ROOT / ".codex" / "memory" / "project_memory.md"
    hafiza_lines, hafiza_newline, hafiza_bom, _ = read_text_lines(hafiza)
    header = "## 2026-05-15 MPE Landed Titles Conflict Decision Worklist"
    if header in hafiza_lines:
        start = hafiza_lines.index(header)
        end = len(hafiza_lines)
        for i in range(start + 1, len(hafiza_lines)):
            if hafiza_lines[i].startswith("## "):
                end = i
                break
        if start > 0 and hafiza_lines[start - 1] == "":
            start -= 1
        hafiza_lines = hafiza_lines[:start] + hafiza_lines[end:]
    hafiza_lines.extend(
        [
            "",
            header,
            "",
            "- MPE Add 1 landed_titles conflict havuzu canli dosyalar degistirilmeden karar tablosuna cevrildi.",
            f"- Karar tablosu: `.codex/works/analysis/generated/mpe_import_add_1/{DECISIONS.name}`.",
            f"- Ozet rapor: `.codex/works/analysis/generated/mpe_import_add_1/{SUMMARY.name}`.",
            f"- Toplam conflict satiri: `{len(decisions)}`; unique barony: `{unique_barony_count}`; duplicate-key report rows: `{duplicate_report_rows}`.",
            "- Otomatik uygulama guvenli satir yoktur; tum satirlar `safe_to_auto_apply = no` olarak isaretlendi.",
            f"- Status dagilimi: " + ", ".join(f"`{key}={value}`" for key, value in sorted(status_counts.items())) + ".",
            "- `target_barony_existing_province_conflict` ve `county_child_existing_barony_conflict` icin karar secenekleri: mevcut target barony'yi koru, mevcut barony'yi MPE final province'e retarget et, MPE barony'yi ayri/rename title olarak yasat, ya da MPE title linkini dusurup history-only birak.",
            "- `missing_source_barony` icin source landed-title blogu olmadigi icin title block tahmin edilmeyecek; manuel title gerekiyorsa ayrica kurulacak.",
            "- `county_child_removed_not_in_mpe_overlay` satirlari Add 1 overlay/import ID map disinda kaldigi icin simdilik disarida tutulacak; genisletme ancak overlay/definition kapsami buyutulurse yapilacak.",
            f"- `landed_titles` unchanged: `{before_hashes['landed_titles'] == after_hashes['landed_titles']}`.",
        ]
    )
    write_text_lines(hafiza, hafiza_lines, hafiza_newline, hafiza_bom, True)

    print("MPE landed title conflict decision worklist built")
    print(f"conflict rows: {len(decisions)}")
    print(f"unique conflict baronies: {unique_barony_count}")
    print(f"decision table: {DECISIONS}")
    print(f"summary: {SUMMARY}")


if __name__ == "__main__":
    main()
