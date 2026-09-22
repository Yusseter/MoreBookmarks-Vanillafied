from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT / "BookmarksGit"
WORKS_ROOT = PROJECT_ROOT / "development"
MPE_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\1158310\3726274827")
OUT_DIR = WORKS_ROOT / "analysis" / "generated" / "mpe_import_add_1" / "consistency_fix"
LAND_ROOT = ROOT / "common" / "landed_titles" / "00_landed_titles.txt"
YB_PROVINCES = ROOT / "history" / "provinces" / "00_yb_MPE_PROVINCES.txt"
YB_TITLES = ROOT / "history" / "titles" / "00_YB_MPE.txt"
MB_PROVINCES = ROOT / "history" / "provinces" / "00_MB_PROVINCES.txt"
MPE_PROVINCES = MPE_ROOT / "history" / "provinces" / "z_MPE_province.txt"
ID_MAP = WORKS_ROOT / "analysis" / "generated" / "mpe_import_add_1" / "mpe_import_id_map.csv"

TITLE_START_RE = re.compile(r"^\s*(?P<name>[ekdcb]_[A-Za-z0-9_\-']+)\s*=\s*\{")
PROVINCE_START_RE = re.compile(r"^\s*(?P<id>\d+)\s*=\s*\{")
CAPITAL_RE = re.compile(r"\bcapital\s*=\s*(?:title:)?(?P<name>[bcd]_[A-Za-z0-9_\-']+)")
PROVINCE_RE = re.compile(r"\bprovince\s*=\s*(?P<id>\d+)")

# User-supplied semantic donor map. Spellings normalized to current title ids.
COUNTY_DONOR = {
    "c_besinada": "c_don_portage",
    "c_alania": "c_don_portage",
    "c_digoria": "c_cabardinia",
    "c_iron": "c_cabardinia",
    "c_ossetia": "c_cabardinia",
    "c_durdzukia": "c_philan",
    "c_malkhia": "c_philan",
    "c_simsir": "c_philan",
    "c_balanjar": "c_samander",
    "c_gumik": "c_samander",
    "c_lazia": "c_samander",
    "c_samander": "c_samander",
    "c_ubykh": "c_jiqeti",
    "c_maskut": "c_derbent",
    "c_lezgin": "c_derbent",
    "c_darginia": "c_derbent",
    "c_avaria": "c_philan",
    "c_anket": "c_samiran",
    "c_peshe": "c_kuban",
    "c_kuma": "c_samiran",
    "c_guzliev": "c_kalos_limen",
    "c_theodoro": "c_kalos_limen",
    "c_crimea": "c_kalos_limen",
    "c_kyzyl_yar": "c_oleshye",
    "c_kamyan": "c_oleshye",
    "c_kalka": "c_khortytsia",
    "c_tokmak": "c_khortytsia",
    "c_lozova": "c_bakhmut",
    "c_taganrog": "c_tana",
    "c_aorsia": "c_maghas",
    "c_maikop": "c_maghas",
    "c_tapanta": "c_maghas",
    "c_skhimar": "c_maghas",
    "c_shapsug": "c_zichia",
    "c_abdzakh": "c_zichia",
    "c_kemirgho": "c_zichia",
}

# Title-history semantic remaps that are not simple same-title lookups.
TITLE_DONOR = {
    "c_korchev": "c_kerch",
}

@dataclass
class TitleEntry:
    name: str
    tier: str
    start: int
    end: int
    parents: Dict[str, str] = field(default_factory=dict)
    children: List[str] = field(default_factory=list)
    block_text: str = ""
    province: str = ""
    explicit_capital: str = ""

@dataclass
class HistoryBlock:
    key: str
    path: Path
    start: int
    end: int
    lines: List[str]
    has_holder: bool = False
    culture: str = ""
    religion: str = ""


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def read_lines(path: Path) -> List[str]:
    return path.read_text(encoding="utf-8-sig", errors="replace").splitlines()


def write_lines(path: Path, lines: List[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def find_block_end(lines: List[str], start: int) -> int:
    depth = 0
    for i in range(start, len(lines)):
        clean = strip_comment(lines[i])
        depth += clean.count("{") - clean.count("}")
        if i > start and depth <= 0:
            return i
    raise RuntimeError(f"Unclosed block at line {start + 1}")


def parse_titles(path: Path) -> Dict[str, TitleEntry]:
    lines = read_lines(path)
    entries: Dict[str, TitleEntry] = {}
    starts: List[TitleEntry] = []
    for i, line in enumerate(lines):
        m = TITLE_START_RE.match(strip_comment(line))
        if not m:
            continue
        name = m.group("name")
        end = find_block_end(lines, i)
        entry = TitleEntry(name=name, tier=name[0], start=i, end=end)
        entry.block_text = "\n".join(lines[i : end + 1])
        starts.append(entry)
        entries[name] = entry

    for entry in starts:
        parents = [p for p in starts if p.start < entry.start and p.end > entry.end]
        parents.sort(key=lambda p: p.start)
        entry.parents = {p.tier: p.name for p in parents}
        if parents:
            parents[-1].children.append(entry.name)

    for entry in starts:
        if entry.tier == "b":
            for line in lines[entry.start : entry.end + 1]:
                m = PROVINCE_RE.search(strip_comment(line))
                if m:
                    entry.province = m.group("id")
                    break
        elif entry.tier == "c":
            local_depth = 0
            for idx in range(entry.start, entry.end + 1):
                clean = strip_comment(lines[idx])
                if idx > entry.start and local_depth == 1:
                    m = CAPITAL_RE.search(clean)
                    if m and m.group("name").startswith("b_"):
                        entry.explicit_capital = m.group("name")
                        break
                local_depth += clean.count("{") - clean.count("}")
    return entries


def title_direct_children(entries: Dict[str, TitleEntry], name: str, tier: str) -> List[TitleEntry]:
    parent = entries.get(name)
    if not parent:
        return []
    children = [entries[c] for c in parent.children if entries[c].tier == tier]
    return sorted(children, key=lambda e: e.start)


def county_capital(entries: Dict[str, TitleEntry], county: str) -> Tuple[str, str]:
    c = entries.get(county)
    if not c:
        return "", ""
    if c.explicit_capital and c.explicit_capital in entries:
        b = entries[c.explicit_capital]
        return b.name, b.province
    children = title_direct_children(entries, county, "b")
    if not children:
        return "", ""
    return children[0].name, children[0].province


def parse_title_history_files() -> Dict[str, List[HistoryBlock]]:
    blocks: Dict[str, List[HistoryBlock]] = {}
    for path in sorted((ROOT / "history" / "titles").glob("*.txt")):
        lines = read_lines(path)
        i = 0
        while i < len(lines):
            m = TITLE_START_RE.match(strip_comment(lines[i]))
            if not m:
                i += 1
                continue
            name = m.group("name")
            end = find_block_end(lines, i)
            block_lines = lines[i : end + 1]
            text = "\n".join(block_lines)
            blocks.setdefault(name, []).append(
                HistoryBlock(
                    key=name,
                    path=path,
                    start=i,
                    end=end,
                    lines=block_lines,
                    has_holder=bool(re.search(r"^\s*holder\s*=", text, re.M)),
                )
            )
            i = end + 1
    return blocks


def parse_province_history_file(path: Path) -> Dict[str, HistoryBlock]:
    blocks: Dict[str, HistoryBlock] = {}
    if not path.exists():
        return blocks
    lines = read_lines(path)
    i = 0
    while i < len(lines):
        m = PROVINCE_START_RE.match(strip_comment(lines[i]))
        if not m:
            i += 1
            continue
        pid = m.group("id")
        end = find_block_end(lines, i)
        block_lines = lines[i : end + 1]
        culture = ""
        religion = ""
        depth = 0
        for j, line in enumerate(block_lines):
            clean = strip_comment(line)
            if j > 0 and depth == 1:
                cm = re.match(r"^\s*culture\s*=\s*([^\s#]+)", clean)
                rm = re.match(r"^\s*religion\s*=\s*([^\s#]+)", clean)
                if cm:
                    culture = cm.group(1)
                if rm:
                    religion = rm.group(1)
            depth += clean.count("{") - clean.count("}")
        blocks[pid] = HistoryBlock(pid, path, i, end, block_lines, culture=culture, religion=religion)
        i = end + 1
    return blocks


def parse_id_map() -> Tuple[Dict[str, str], Dict[str, str]]:
    target_to_old: Dict[str, str] = {}
    old_to_target: Dict[str, str] = {}
    with ID_MAP.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            old_id = row.get("old_mpe_id") or row.get("old_id") or ""
            target_id = row.get("target_id") or row.get("final_id") or ""
            if old_id and target_id:
                target_to_old[target_id] = old_id
                old_to_target[old_id] = target_id
    return target_to_old, old_to_target


def active_mpe_counties(entries: Dict[str, TitleEntry]) -> List[str]:
    result = []
    for entry in entries.values():
        if entry.tier != "c":
            continue
        if "Yusseter: MPE" in entry.block_text or "MPE_" in entry.block_text or entry.name in COUNTY_DONOR or entry.name in TITLE_DONOR:
            result.append(entry.name)
    return sorted(set(result))


def top_values_from_block(block: Optional[HistoryBlock]) -> Dict[str, str]:
    if not block:
        return {}
    values = {}
    if block.culture:
        values["culture"] = block.culture
    if block.religion:
        values["religion"] = block.religion
    return values


def insert_top_values(block_lines: List[str], values: Dict[str, str], note: str) -> List[str]:
    out: List[str] = []
    depth = 0
    inserted = False
    for idx, line in enumerate(block_lines):
        clean = strip_comment(line)
        if idx > 0 and depth == 1 and re.match(r"^\s*(culture|religion)\s*=", clean):
            depth += clean.count("{") - clean.count("}")
            continue
        out.append(line)
        if idx == 0 and not inserted:
            if values.get("culture"):
                out.append(f"\tculture = {values['culture']} # Yusseter: {note}")
            if values.get("religion"):
                out.append(f"\treligion = {values['religion']} # Yusseter: {note}")
            inserted = True
        depth += clean.count("{") - clean.count("}")
    return out


def rewrite_numeric_header(lines: List[str], pid: str, barony: str, note: str) -> List[str]:
    new = list(lines)
    new[0] = f"{pid} = {{ # {barony} # Yusseter: {note}"
    return new


def replace_block_in_file(path: Path, block: HistoryBlock, new_lines: List[str]) -> None:
    lines = read_lines(path)
    out = lines[: block.start] + new_lines + lines[block.end + 1 :]
    write_lines(path, out)


def append_block(path: Path, new_lines: List[str]) -> None:
    lines = read_lines(path) if path.exists() else []
    while lines and lines[-1].strip() == "":
        lines.pop()
    if lines:
        lines.append("")
    lines.extend(new_lines)
    lines.append("")
    write_lines(path, lines)


def clone_title_block(block: HistoryBlock, target_title: str, donor_title: str) -> List[str]:
    lines = list(block.lines)
    lines[0] = re.sub(r"^\s*[ekdcb]_[A-Za-z0-9_\-']+\s*=\s*\{", f"{target_title} = {{ # Yusseter: MPE title history donor {donor_title}", lines[0])
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    entries = parse_titles(LAND_ROOT)
    title_blocks = parse_title_history_files()
    yb_blocks = parse_province_history_file(YB_PROVINCES)
    mb_blocks = parse_province_history_file(MB_PROVINCES)
    mpe_blocks = parse_province_history_file(MPE_PROVINCES)
    target_to_old, _ = parse_id_map()

    def effective_province_values(pid: str) -> Dict[str, str]:
        return top_values_from_block(yb_blocks.get(pid)) or top_values_from_block(mb_blocks.get(pid))

    resolving: set[str] = set()
    value_cache: Dict[str, Tuple[Dict[str, str], str, str, str]] = {}

    def resolve_county_values(county: str) -> Tuple[Dict[str, str], str, str, str]:
        if county in value_cache:
            return value_cache[county]
        if county in resolving:
            return {}, "cycle", "", ""
        resolving.add(county)
        donor_county = COUNTY_DONOR.get(county)
        if donor_county and donor_county != county:
            values, source, donor_barony, donor_pid = resolve_county_values(donor_county)
            if values:
                result = (values, f"donor_county:{donor_county}:{source}", donor_barony, donor_pid)
                value_cache[county] = result
                resolving.remove(county)
                return result

        cap_barony, cap_pid = county_capital(entries, county)
        old_id = target_to_old.get(cap_pid, cap_pid)
        values = top_values_from_block(mpe_blocks.get(old_id))
        if values:
            result = (values, f"mpe_source:{old_id}", cap_barony, cap_pid)
            value_cache[county] = result
            resolving.remove(county)
            return result

        values = effective_province_values(cap_pid)
        if values:
            result = (values, "current_capital_history", cap_barony, cap_pid)
            value_cache[county] = result
            resolving.remove(county)
            return result

        # Last safe fallback: another direct barony in the same county that already has values.
        for child in title_direct_children(entries, county, "b"):
            values = effective_province_values(child.province)
            if values:
                result = (values, f"same_county_barony:{child.name}", child.name, child.province)
                value_cache[county] = result
                resolving.remove(county)
                return result
            old_child = target_to_old.get(child.province, child.province)
            values = top_values_from_block(mpe_blocks.get(old_child))
            if values:
                result = (values, f"same_county_mpe_source:{old_child}", child.name, child.province)
                value_cache[county] = result
                resolving.remove(county)
                return result

        result = ({}, "unresolved", cap_barony, cap_pid)
        value_cache[county] = result
        resolving.remove(county)
        return result

    county_rows = []
    province_repairs = []
    title_repairs = []

    for county in active_mpe_counties(entries):
        cap_barony, cap_pid = county_capital(entries, county)
        existing_values = effective_province_values(cap_pid) if cap_pid else {}
        missing_culture = bool(cap_pid) and not existing_values.get("culture")
        missing_religion = bool(cap_pid) and not existing_values.get("religion")
        holder_blocks = title_blocks.get(county, [])
        has_holder_anywhere = any(b.has_holder for b in holder_blocks)
        values, value_source, donor_barony, donor_pid = resolve_county_values(county)
        issues = []
        if not cap_barony:
            issues.append("missing_capital_barony")
        if not cap_pid:
            issues.append("missing_capital_province")
        if missing_culture:
            issues.append("capital_history_missing_culture")
        if missing_religion:
            issues.append("capital_history_missing_religion")
        if not has_holder_anywhere:
            issues.append("missing_title_holder_history")
        county_rows.append({
            "county": county,
            "path": entries[county].block_text.splitlines()[0].strip(),
            "capital_barony": cap_barony,
            "capital_province": cap_pid,
            "old_mpe_id": target_to_old.get(cap_pid, cap_pid),
            "existing_culture": existing_values.get("culture", ""),
            "existing_religion": existing_values.get("religion", ""),
            "resolved_culture": values.get("culture", ""),
            "resolved_religion": values.get("religion", ""),
            "value_source": value_source,
            "donor_barony": donor_barony,
            "donor_province": donor_pid,
            "title_holder_history": "yes" if has_holder_anywhere else "no",
            "issues": "|".join(issues),
        })
        if cap_pid and (missing_culture or missing_religion) and values.get("culture") and values.get("religion"):
            province_repairs.append((county, cap_barony, cap_pid, values, value_source, donor_barony, donor_pid))
        if not has_holder_anywhere:
            donor_title = TITLE_DONOR.get(county, COUNTY_DONOR.get(county, county))
            donor_block = next((b for b in title_blocks.get(donor_title, []) if b.has_holder), None)
            title_repairs.append((county, donor_title, donor_block))

    # Apply province history repairs.
    province_report = []
    if args.apply:
        for county, cap_barony, cap_pid, values, value_source, donor_barony, donor_pid in province_repairs:
            note = f"MPE county capital donor {value_source}"
            # Reparse immediately before every write. Earlier versions kept stale
            # line indexes across multiple replacements and could nest province blocks.
            current_yb_blocks = parse_province_history_file(YB_PROVINCES)
            target_block = current_yb_blocks.get(cap_pid)
            if target_block:
                new_lines = insert_top_values(target_block.lines, values, note)
                replace_block_in_file(target_block.path, target_block, new_lines)
                action = "updated_existing_yb_block"
            else:
                base = mb_blocks.get(cap_pid) or mpe_blocks.get(target_to_old.get(cap_pid, cap_pid))
                if base:
                    new_lines = rewrite_numeric_header(base.lines, cap_pid, cap_barony, note)
                    new_lines = insert_top_values(new_lines, values, note)
                else:
                    new_lines = [
                        f"{cap_pid} = {{ # {cap_barony} # Yusseter: {note}",
                        f"\tculture = {values['culture']} # Yusseter: {note}",
                        f"\treligion = {values['religion']} # Yusseter: {note}",
                        "}",
                    ]
                append_block(YB_PROVINCES, new_lines)
                action = "appended_yb_overlay_block"
            province_report.append({
                "county": county,
                "capital_barony": cap_barony,
                "capital_province": cap_pid,
                "culture": values["culture"],
                "religion": values["religion"],
                "value_source": value_source,
                "donor_barony": donor_barony,
                "donor_province": donor_pid,
                "action": action,
            })
        # Reparse title blocks is not needed; title repairs only append below.
        for county, donor_title, donor_block in title_repairs:
            if donor_block is None:
                title_repairs_action = "missing_donor_holder_history"
            else:
                append_block(YB_TITLES, clone_title_block(donor_block, county, donor_title))
                title_repairs_action = "appended_title_history_from_donor"
            # Store through a side list by replacing tuple with dict below would be more verbose.

    # Write reports.
    county_report_path = OUT_DIR / "mpe_county_history_gap_current_audit.csv"
    with county_report_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(county_rows[0].keys()) if county_rows else [])
        writer.writeheader()
        writer.writerows(county_rows)

    problem_rows = [r for r in county_rows if r["issues"]]
    problem_path = OUT_DIR / "mpe_county_history_gap_current_problem_rows.csv"
    with problem_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(county_rows[0].keys()) if county_rows else [])
        writer.writeheader()
        writer.writerows(problem_rows)

    repair_path = OUT_DIR / "mpe_county_history_gap_repair_report.csv"
    with repair_path.open("w", encoding="utf-8", newline="") as f:
        fields = ["county", "capital_barony", "capital_province", "culture", "religion", "value_source", "donor_barony", "donor_province", "action"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(province_report)

    issue_counts: Dict[str, int] = {}
    for row in county_rows:
        for issue in filter(None, row["issues"].split("|")):
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
    summary = OUT_DIR / "mpe_county_history_gap_current_summary.md"
    lines = [
        "# MPE County History Gap Current Audit",
        "",
        f"- apply mode: `{'yes' if args.apply else 'no'}`",
        f"- active MPE counties checked: `{len(county_rows)}`",
        f"- problem rows before apply: `{len(problem_rows)}`",
        f"- province repairs applied: `{len(province_report)}`",
        f"- title holder repair candidates: `{len(title_repairs)}`",
        "",
        "## Issue Counts",
    ]
    for key, value in sorted(issue_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{key}`: `{value}`")
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print({
        "apply": args.apply,
        "checked": len(county_rows),
        "problem_rows_before_apply": len(problem_rows),
        "province_repairs": len(province_report),
        "title_repair_candidates": len(title_repairs),
        "issue_counts": issue_counts,
    })
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
