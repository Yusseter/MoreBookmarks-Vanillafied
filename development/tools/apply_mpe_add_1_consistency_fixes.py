from pathlib import Path
import csv
import hashlib
import re
import shutil
from collections import Counter, defaultdict

from apply_mpe_landed_title_relocations import (
    PROJECT_ROOT,
    TARGET,
    MPE,
    OUT as MPE_OUT,
    LANDED,
    parse_titles,
    one_entry,
    immediate_children,
    province_in_entry,
    entry_path,
    read_text_lines,
    write_text_lines,
    read_csv,
    write_csv,
    sha256,
    strip_comment,
    PROVINCE_RE,
)


LEVI = PROJECT_ROOT.parent / "Leviathonlx MoreBookmarks-Plus" / "BookmarksGit"
CONSISTENCY_OUT = MPE_OUT / "consistency_fix"

TITLE_HISTORY_OUT = TARGET / r"history\titles\00_YB_MPE.txt"
PROVINCE_HISTORY_MPE = TARGET / r"history\provinces\00_yb_MPE_PROVINCES.txt"
PROVINCE_HISTORY_MAIN = TARGET / r"history\provinces\00_MB_PROVINCES.txt"
DEFINITION = TARGET / r"map_data\definition.csv"

MPE_HISTORY_DONOR_MAP = CONSISTENCY_OUT / "mpe_history_donor_map.csv"
MPE_ALIAS_LOCATOR_MAP = CONSISTENCY_OUT / "mpe_barony_alias_locator_map.csv"
MPE_TITLE_STRUCTURE_FIX_MAP = CONSISTENCY_OUT / "mpe_title_structure_fix_map.csv"

LOCATOR_FILES = [
    "activities.txt",
    "building_locators.txt",
    "combat_locators.txt",
    "player_stack_locators.txt",
    "siege_locators.txt",
    "special_building_locators.txt",
]

HISTORY_DONORS = [
    ("c_besinada", "c_don_portage"),
    ("c_majar", "c_don_portage"),
    ("c_alania", "c_don_portage"),
    ("c_digoria", "c_cabardinia"),
    ("c_iron", "c_cabardinia"),
    ("c_ossetia", "c_cabardinia"),
    ("c_durdzukia", "c_philan"),
    ("c_malkhia", "c_philan"),
    ("c_simsir", "c_philan"),
    ("c_balanjar", "c_samander"),
    ("c_gumik", "c_samander"),
    ("c_lazia", "c_samander"),
    ("c_peshe", "c_kuban"),
    ("c_guzliev", "c_kalos_limen"),
    ("c_theodoro", "c_kalos_limen"),
    ("c_crimea", "c_kalos_limen"),
    ("c_kyzyl_yar", "c_oleshye"),
    ("c_kamyan", "c_oleshye"),
    ("c_kalka", "c_khortytsia"),
    ("c_tokmak", "c_khortytsia"),
    ("c_lozova", "c_bakhmut"),
    ("c_taganrog", "c_tana"),
    ("c_aorsia", "c_maghas"),
    ("c_maikop", "c_maghas"),
    ("c_tapanta", "c_maghas"),
    ("c_skhimar", "c_maghas"),
    ("c_shapsug", "c_zichia"),
    ("c_abdzakh", "c_zichia"),
    ("c_kemirgho", "c_zichia"),
]

ALIAS_MAPPINGS = [
    {
        "old_mpe_barony": "b_gialta",
        "replacement_barony": "b_yalta",
        "old_mpe_id": 22830,
        "donor_final_id": 13359,
        "target_old_id": 9837,
        "target_county": "c_kerch",
    },
    {
        "old_mpe_barony": "b_symbolon",
        "replacement_barony": "b_yamboli",
        "old_mpe_id": 22831,
        "donor_final_id": 13360,
        "target_old_id": 9836,
        "target_county": "c_kerch",
    },
    {
        "old_mpe_barony": "b_phoros",
        "replacement_barony": "b_mangup",
        "old_mpe_id": 22832,
        "donor_final_id": 13361,
        "target_old_id": 9835,
        "target_county": "c_kerch",
    },
    {
        "old_mpe_barony": "b_anapa",
        "replacement_barony": "b_batacrim",
        "old_mpe_id": 21385,
        "donor_final_id": 12922,
        "target_old_id": 9838,
        "target_county": "c_tmutarakan",
    },
    {
        "old_mpe_barony": "b_soldaia",
        "replacement_barony": "b_sukdak",
        "old_mpe_id": 22833,
        "donor_final_id": 13362,
        "target_old_id": 9833,
        "target_county": "c_theodosia",
    },
]

STRUCTURE_ACTIONS = [
    {
        "action": "alias_replace",
        "description": "Replace MPE alias barony keys with old Levi barony keys while preserving old province IDs.",
    },
    {
        "action": "kerch_semantic_remap",
        "description": "Move MPE c_kerch content into active c_korchev; keep current c_kerch as old Levi c_cherson/c_kerch identity.",
    },
    {
        "action": "move_barony",
        "source_title": "b_targim",
        "target_county": "c_ossetia",
        "description": "User b_targin note resolves to active b_targim; move it under c_ossetia.",
    },
    {
        "action": "move_county_children",
        "source_county": "c_lazia",
        "target_county": "c_avaria",
        "description": "Move immediate c_lazia barony children into c_avaria, then disable empty c_lazia.",
    },
]

TITLE_RE = re.compile(r"^\s*((?:e|k|d|c|b)_[A-Za-z0-9_'\-]+)\s*=\s*\{")
COLOR_RE = re.compile(r"(\bcolor\s*=\s*\{\s*)[0-9]+\s+[0-9]+\s+[0-9]+(\s*\})")
CAPITAL_RE = re.compile(r"\bcapital\s*=\s*(b_[A-Za-z0-9_'\-]+)\b")
HISTORY_HEADER_RE = re.compile(r"^\s*([A-Za-z0-9_'\-]+)\s*=\s*\{")
PROVINCE_HISTORY_HEADER_RE = re.compile(r"^\s*(\d+)\s*=\s*\{")
ID_RE = re.compile(r"\bid\s*=\s*(\d+)\b")


def ensure_out():
    CONSISTENCY_OUT.mkdir(parents=True, exist_ok=True)


def write_rows(path, rows, fields):
    write_csv(path, rows, fields)


def parse_definition():
    out = {}
    if not DEFINITION.exists():
        return out
    for line in DEFINITION.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split(";")
        if len(parts) >= 5 and parts[0].isdigit():
            out[int(parts[0])] = {
                "rgb": ",".join(parts[1:4]),
                "name": parts[4],
            }
    return out


class LandedDoc:
    def __init__(self, path):
        self.path = path
        self.lines, self.newline, self.bom, self.trailing = read_text_lines(path)
        self.refresh()

    def refresh(self):
        data = parse_titles(self.path)
        data["lines"] = self.lines
        self.data = data
        return data

    def save(self):
        write_text_lines(self.path, self.lines, self.newline, self.bom, self.trailing)
        self.refresh()

    def one(self, title):
        return one_entry(self.data, title)

    def block(self, title):
        entry = self.one(title)
        if not entry:
            return None
        return list(self.lines[entry["start"]: entry["end"] + 1])

    def remove(self, title):
        entry = self.one(title)
        if not entry:
            return None
        block = list(self.lines[entry["start"]: entry["end"] + 1])
        del self.lines[entry["start"]: entry["end"] + 1]
        self.refresh()
        return block

    def insert_before_end(self, parent_title, block):
        parent = self.one(parent_title)
        if not parent:
            return False
        self.lines[parent["end"]:parent["end"]] = block
        self.refresh()
        return True

    def province(self, title):
        entry = self.one(title)
        return province_in_entry(self.lines, entry) if entry else None

    def children(self, title, tier=None):
        entry = self.one(title)
        if not entry:
            return []
        return immediate_children(self.data, entry, tier)

    def path(self, title):
        entry = self.one(title)
        return entry_path(entry) if entry else ""

    def final_depth(self):
        self.refresh()
        return self.data["final_depth"]


def set_open_comment(block, comment):
    if not block:
        return block
    block = list(block)
    block[0] = re.sub(r"\{\s*(#.*)?$", "{ # " + comment, block[0], count=1)
    return block


def rewrite_first_province(block, new_id):
    out = []
    changed = False
    for line in block:
        if not changed and PROVINCE_RE.search(strip_comment(line)):
            out.append(re.sub(r"(\bprovince\s*=\s*)\d+", r"\g<1>" + str(new_id), line, count=1))
            changed = True
        else:
            out.append(line)
    if not changed and out:
        indent = re.match(r"^(\s*)", out[0]).group(1) + "\t"
        out.insert(1, f"{indent}province = {new_id}")
    return out


def get_color(doc, title):
    entry = doc.one(title)
    if not entry:
        return ""
    for i in range(entry["start"] + 1, entry["end"] + 1):
        line = strip_comment(doc.lines[i])
        m = COLOR_RE.search(line)
        if m:
            return re.search(r"\{\s*([0-9]+\s+[0-9]+\s+[0-9]+)\s*\}", line).group(1)
    return ""


def set_color(doc, title, color):
    if not color:
        return False
    entry = doc.one(title)
    if not entry:
        return False
    for i in range(entry["start"] + 1, entry["end"] + 1):
        if COLOR_RE.search(strip_comment(doc.lines[i])):
            doc.lines[i] = COLOR_RE.sub(r"\g<1>" + color + r"\g<2>", doc.lines[i], count=1)
            doc.refresh()
            return True
    return False


def capital_barony(doc, county_title):
    entry = doc.one(county_title)
    if not entry:
        return ""
    for i in range(entry["start"] + 1, entry["end"] + 1):
        m = CAPITAL_RE.search(strip_comment(doc.lines[i]))
        if m:
            return m.group(1)
    children = doc.children(county_title, "b")
    return children[0]["name"] if children else ""


def make_mapping_csvs():
    ensure_out()
    write_rows(
        MPE_HISTORY_DONOR_MAP,
        [
            {
                "target_county": target,
                "donor_county": donor,
                "donor_source_rule": "Levi for c_don_portage; otherwise current/Levi/MPE fallback",
            }
            for target, donor in HISTORY_DONORS
        ],
        ["target_county", "donor_county", "donor_source_rule"],
    )
    write_rows(
        MPE_ALIAS_LOCATOR_MAP,
        ALIAS_MAPPINGS,
        [
            "old_mpe_barony",
            "replacement_barony",
            "old_mpe_id",
            "donor_final_id",
            "target_old_id",
            "target_county",
        ],
    )
    write_rows(
        MPE_TITLE_STRUCTURE_FIX_MAP,
        STRUCTURE_ACTIONS,
        ["action", "source_title", "source_county", "target_county", "description"],
    )


def apply_landed_structure():
    report = []
    doc = LandedDoc(LANDED)
    levi_doc = LandedDoc(LEVI / r"common\landed_titles\00_landed_titles.txt")

    for item in ALIAS_MAPPINGS:
        block = doc.remove(item["replacement_barony"])
        if block:
            block = set_open_comment(block, f"Yusseter: MPE alias donor {item['old_mpe_id']}")
            block = rewrite_first_province(block, item["target_old_id"])
            ok = doc.insert_before_end(item["target_county"], block)
            report.append({**item, "action": "alias_target_reinserted", "status": "ok" if ok else "missing_target_county"})
        else:
            report.append({**item, "action": "alias_target_reinserted", "status": "missing_replacement_barony"})

        donor_block = doc.remove(item["old_mpe_barony"])
        report.append({**item, "action": "remove_mpe_alias_barony", "status": "removed" if donor_block else "not_present"})

    # Keep old Kerch identity and move MPE c_kerch content to c_korchev.
    chersonesus = doc.remove("b_chersonesus")
    if chersonesus:
        chersonesus = set_open_comment(chersonesus, "Yusseter: MPE semantic remap c_cherson_to_c_kerch")
        doc.insert_before_end("c_kerch", chersonesus)
        report.append({"action": "move_b_chersonesus", "status": "ok"})
    else:
        report.append({"action": "move_b_chersonesus", "status": "not_present"})

    korchev_children = []
    for child in ["b_kerch", "b_bosporos", "b_kimmerikon", "b_sauromateion", "b_arabat", "b_kazeka"]:
        block = doc.remove(child)
        if block:
            korchev_children.extend(set_open_comment(block, "Yusseter: MPE c_kerch content moved to c_korchev"))
            report.append({"action": "collect_c_korchev_child", "title": child, "status": "ok"})
        else:
            report.append({"action": "collect_c_korchev_child", "title": child, "status": "not_present"})

    doc.remove("c_korchev")
    korchev_color = get_color(levi_doc, "c_korchev") or "208 189 155"
    korchev_block = [
        "\t\t\tc_korchev = { # Yusseter: MPE semantic remap from source c_kerch",
        f"\t\t\t\tcolor = {{ {korchev_color} }}",
    ]
    korchev_block.extend(korchev_children)
    korchev_block.append("\t\t\t}")
    ok = doc.insert_before_end("d_tmutarakan", korchev_block)
    report.append({"action": "create_active_c_korchev", "status": "ok" if ok else "missing_d_tmutarakan"})

    if not doc.children("c_cherson", "b"):
        removed = doc.remove("c_cherson")
        report.append({"action": "remove_empty_c_cherson", "status": "removed" if removed else "not_present"})
    if not doc.children("d_klimata", "c"):
        removed = doc.remove("d_klimata")
        report.append({"action": "remove_empty_d_klimata", "status": "removed" if removed else "not_present"})

    targim = doc.remove("b_targim")
    if targim:
        targim = set_open_comment(targim, "Yusseter: moved from c_dvaletia by MPE consistency plan")
        ok = doc.insert_before_end("c_ossetia", targim)
        report.append({"action": "move_b_targim_to_c_ossetia", "status": "ok" if ok else "missing_c_ossetia"})
    else:
        report.append({"action": "move_b_targim_to_c_ossetia", "status": "not_present"})
    if not doc.children("c_dvaletia", "b"):
        removed = doc.remove("c_dvaletia")
        report.append({"action": "remove_empty_c_dvaletia", "status": "removed" if removed else "not_present"})

    lazia_children = [child["name"] for child in doc.children("c_lazia", "b")]
    for child in lazia_children:
        block = doc.remove(child)
        if block:
            block = set_open_comment(block, "Yusseter: moved from c_lazia to c_avaria by MPE consistency plan")
            ok = doc.insert_before_end("c_avaria", block)
            report.append({"action": "move_lazia_child_to_c_avaria", "title": child, "status": "ok" if ok else "missing_c_avaria"})
    if not doc.children("c_lazia", "b"):
        removed = doc.remove("c_lazia")
        report.append({"action": "remove_empty_c_lazia", "status": "removed" if removed else "not_present"})

    titles_for_color_restore = sorted({
        "c_perekop",
        "c_khortytsia",
        "c_kalos_limen",
        "c_kerch",
        "c_korchev",
        "c_cherson",
        "c_tmutarakan",
        "c_theodosia",
    })
    for title in titles_for_color_restore:
        color = get_color(levi_doc, title)
        if color:
            changed = set_color(doc, title, color)
            report.append({"action": "restore_levi_color", "title": title, "color": color, "status": "changed" if changed else "target_missing_or_no_color"})

    doc.save()
    write_rows(
        CONSISTENCY_OUT / "mpe_landed_titles_structure_apply_report.csv",
        report,
        ["action", "title", "old_mpe_barony", "replacement_barony", "old_mpe_id", "donor_final_id", "target_old_id", "target_county", "color", "status"],
    )
    return report


def parse_history_blocks(path, header_re):
    lines, newline, bom, trailing = read_text_lines(path)
    blocks = {}
    depth = 0
    current = None
    start = None
    for i, line in enumerate(lines):
        code = strip_comment(line)
        if current is None:
            m = header_re.match(code)
            if m:
                current = m.group(1)
                start = i
        depth += code.count("{") - code.count("}")
        if current is not None and depth == 0:
            blocks[current] = (start, i)
            current = None
            start = None
    return lines, newline, bom, trailing, blocks


def find_title_history(title, prefer_levi=False):
    roots = []
    if prefer_levi:
        roots.append(LEVI)
    roots.extend([TARGET, LEVI, MPE])
    seen = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        folder = root / "history" / "titles"
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.txt")):
            lines, _nl, _bom, _tr, blocks = parse_history_blocks(path, HISTORY_HEADER_RE)
            if title in blocks:
                s, e = blocks[title]
                return path, list(lines[s:e + 1])
    return None, None


def find_province_history(province_id, prefer_levi=False):
    roots = []
    if prefer_levi:
        roots.append(LEVI)
    roots.extend([TARGET, LEVI, MPE])
    seen = set()
    key = str(province_id)
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        folder = root / "history" / "provinces"
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.txt")):
            lines, _nl, _bom, _tr, blocks = parse_history_blocks(path, PROVINCE_HISTORY_HEADER_RE)
            if key in blocks:
                s, e = blocks[key]
                return path, list(lines[s:e + 1])
    return None, None


def rewrite_history_root(block, old_root, new_root, comment):
    out = list(block)
    if not out:
        return out
    out[0] = re.sub(r"^(\s*)" + re.escape(str(old_root)) + r"(\s*=\s*\{.*)$", r"\g<1>" + str(new_root) + r"\g<2>", out[0], count=1)
    if "#" in out[0]:
        out[0] = out[0].split("#", 1)[0].rstrip() + " # " + comment
    else:
        out[0] = out[0].rstrip() + " # " + comment
    return out


def replace_or_append_block(path, key, block, header_re):
    lines, newline, bom, trailing, blocks = parse_history_blocks(path, header_re)
    if key in blocks:
        s, e = blocks[key]
        lines[s:e + 1] = block
        status = "replaced"
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(block)
        status = "appended"
    write_text_lines(path, lines, newline, bom, trailing=True)
    return status


def remove_top_level_culture_religion(block):
    out = []
    depth = 0
    removed = []
    for line in block:
        code = strip_comment(line)
        if depth == 1 and re.search(r"^\s*(culture|religion)\s*=", code):
            removed.append(code.strip())
        else:
            out.append(line)
        depth += code.count("{") - code.count("}")
    return out, removed


def clean_noncapital_province_history(province_id):
    key = str(province_id)
    for path in [PROVINCE_HISTORY_MPE, PROVINCE_HISTORY_MAIN]:
        if not path.exists():
            continue
        lines, newline, bom, trailing, blocks = parse_history_blocks(path, PROVINCE_HISTORY_HEADER_RE)
        if key not in blocks:
            continue
        s, e = blocks[key]
        block, removed = remove_top_level_culture_religion(lines[s:e + 1])
        if removed:
            lines[s:e + 1] = block
            write_text_lines(path, lines, newline, bom, trailing)
        return path, removed
    return None, []


def apply_title_history():
    ensure_out()
    doc = LandedDoc(LANDED)
    report = []
    target_lines, target_nl, target_bom, target_tr, target_blocks = parse_history_blocks(TITLE_HISTORY_OUT, HISTORY_HEADER_RE)
    for target, donor in HISTORY_DONORS:
        if not doc.one(target):
            report.append({"target_county": target, "donor_county": donor, "status": "skipped_target_not_active"})
            continue
        source_path, donor_block = find_title_history(donor, prefer_levi=(donor == "c_don_portage"))
        if not donor_block:
            report.append({"target_county": target, "donor_county": donor, "status": "missing_donor_history"})
            continue
        new_block = rewrite_history_root(donor_block, donor, target, f"Yusseter: MPE title history donor {donor}")
        target_blocks = parse_history_blocks(TITLE_HISTORY_OUT, HISTORY_HEADER_RE)[4]
        status = replace_or_append_block(TITLE_HISTORY_OUT, target, new_block, HISTORY_HEADER_RE)
        report.append({"target_county": target, "donor_county": donor, "source_file": str(source_path), "status": status})
    write_rows(
        CONSISTENCY_OUT / "mpe_title_history_donor_apply_report.csv",
        report,
        ["target_county", "donor_county", "source_file", "status"],
    )
    return report


def apply_province_history():
    ensure_out()
    target_doc = LandedDoc(LANDED)
    levi_doc = LandedDoc(LEVI / r"common\landed_titles\00_landed_titles.txt")
    mpe_doc = LandedDoc(MPE / r"common\landed_titles\00_landed_titles.txt")
    report = []
    clean_report = []

    for target, donor in HISTORY_DONORS:
        if not target_doc.one(target):
            report.append({"target_county": target, "donor_county": donor, "status": "skipped_target_not_active"})
            continue
        target_capital = capital_barony(target_doc, target)
        target_province = target_doc.province(target_capital) if target_capital else None
        donor_doc = levi_doc if donor == "c_don_portage" else target_doc
        if not donor_doc.one(donor):
            donor_doc = levi_doc if levi_doc.one(donor) else mpe_doc
        donor_capital = capital_barony(donor_doc, donor)
        donor_province = donor_doc.province(donor_capital) if donor_capital else None
        if not target_province or not donor_province:
            report.append({
                "target_county": target,
                "donor_county": donor,
                "target_capital_barony": target_capital,
                "donor_capital_barony": donor_capital,
                "status": "missing_capital_or_province",
            })
            continue
        source_path, donor_block = find_province_history(donor_province, prefer_levi=(donor == "c_don_portage"))
        if not donor_block:
            report.append({
                "target_county": target,
                "donor_county": donor,
                "target_capital_barony": target_capital,
                "target_province": target_province,
                "donor_capital_barony": donor_capital,
                "donor_province": donor_province,
                "status": "missing_donor_province_history",
            })
            continue
        new_block = rewrite_history_root(
            donor_block,
            donor_province,
            target_province,
            f"{target_capital} # Yusseter: MPE province history donor {donor}/{donor_province}",
        )
        status = replace_or_append_block(PROVINCE_HISTORY_MPE, str(target_province), new_block, PROVINCE_HISTORY_HEADER_RE)
        report.append({
            "target_county": target,
            "donor_county": donor,
            "target_capital_barony": target_capital,
            "target_province": target_province,
            "donor_capital_barony": donor_capital,
            "donor_province": donor_province,
            "source_file": str(source_path),
            "status": status,
        })

        for child in target_doc.children(target, "b"):
            barony = child["name"]
            province = target_doc.province(barony)
            if province and province != target_province:
                path, removed = clean_noncapital_province_history(province)
                clean_report.append({
                    "target_county": target,
                    "barony": barony,
                    "province": province,
                    "history_file": str(path) if path else "",
                    "removed": " | ".join(removed),
                    "status": "removed_culture_religion" if removed else "no_top_level_culture_religion",
                })

    write_rows(
        CONSISTENCY_OUT / "mpe_province_history_donor_apply_report.csv",
        report,
        ["target_county", "donor_county", "target_capital_barony", "target_province", "donor_capital_barony", "donor_province", "source_file", "status"],
    )
    write_rows(
        CONSISTENCY_OUT / "mpe_province_history_noncapital_cleanup_report.csv",
        clean_report,
        ["target_county", "barony", "province", "history_file", "removed", "status"],
    )
    return report, clean_report


def extract_locator_block(lines, province_id):
    current_start = None
    depth = 0
    for i, line in enumerate(lines):
        code = strip_comment(line)
        if current_start is None and re.match(r"^\s*\{\s*(?:#.*)?$", line):
            current_start = i
            depth = code.count("{") - code.count("}")
            continue
        if current_start is not None:
            depth += code.count("{") - code.count("}")
            if depth == 0:
                block = lines[current_start:i + 1]
                if any(ID_RE.search(strip_comment(x)) and int(ID_RE.search(strip_comment(x)).group(1)) == province_id for x in block):
                    return current_start, i, list(block)
                current_start = None
    return None


def rewrite_locator_block(block, new_id, old_mpe_id):
    out = list(block)
    out[0] = re.sub(r"\{\s*(#.*)?$", "{ # Yusseter: MPE alias donor " + str(old_mpe_id), out[0], count=1)
    replaced = False
    for i, line in enumerate(out):
        if ID_RE.search(strip_comment(line)):
            out[i] = re.sub(r"(\bid\s*=\s*)\d+", r"\g<1>" + str(new_id), line, count=1)
            replaced = True
            break
    if not replaced:
        out.insert(1, f"\t\t\tid={new_id}")
    return out


def apply_locator_aliases():
    report = []
    for file_name in LOCATOR_FILES:
        path = TARGET / "gfx" / "map" / "map_object_data" / file_name
        lines, newline, bom, trailing = read_text_lines(path)
        changed = False
        for item in ALIAS_MAPPINGS:
            donor = extract_locator_block(lines, item["donor_final_id"])
            target = extract_locator_block(lines, item["target_old_id"])
            if not donor or not target:
                report.append({**item, "file": file_name, "status": "missing_donor_or_target_block"})
                continue
            new_block = rewrite_locator_block(donor[2], item["target_old_id"], item["old_mpe_id"])
            s, e, _old = target
            lines[s:e + 1] = new_block
            changed = True
            report.append({**item, "file": file_name, "status": "target_replaced_from_donor"})
        if changed:
            write_text_lines(path, lines, newline, bom, trailing)
    write_rows(
        CONSISTENCY_OUT / "mpe_alias_locator_apply_report.csv",
        report,
        ["file", "old_mpe_barony", "replacement_barony", "old_mpe_id", "donor_final_id", "target_old_id", "target_county", "status"],
    )
    return report


def load_localization_keys(root):
    keys = set()
    loc_root = root / "localization"
    if not loc_root.exists():
        return keys
    for path in loc_root.rglob("*.yml"):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = re.match(r"^\s*([A-Za-z0-9_'\-]+):(?:\d+)?\s", line)
            if m:
                keys.add(m.group(1))
    return keys


def active_title_names(doc, tiers=("b", "c", "d")):
    return {entry["name"] for entry in doc.data["entries"] if entry["tier"] in tiers}


def localization_audit(doc):
    current_keys = load_localization_keys(TARGET)
    mpe_keys = load_localization_keys(MPE)
    levi_keys = load_localization_keys(LEVI)
    touched = set()
    for row in read_csv(MPE_OUT / "mpe_landed_titles_hierarchy_import_report.csv"):
        for col in ["barony", "county", "duchy"]:
            val = row.get(col, "")
            if val.startswith(("b_", "c_", "d_")):
                touched.add(val)
    touched.update(["b_khunzakh", "c_majar", "cn_iryston"])
    touched = {key for key in touched if key.startswith(("b_", "c_", "d_", "cn_"))}
    rows = []
    for key in sorted(touched):
        rows.append({
            "key": key,
            "active_in_landed_titles": "yes" if key in active_title_names(doc) else "no",
            "in_current": "yes" if key in current_keys else "no",
            "in_mpe": "yes" if key in mpe_keys else "no",
            "in_levi": "yes" if key in levi_keys else "no",
            "status": "missing_all_sources" if key not in current_keys and key not in mpe_keys and key not in levi_keys else "source_available_or_current_present",
        })
    return rows


def duplicate_title_rows(doc):
    c = Counter(entry["name"] for entry in doc.data["entries"])
    return [{"title": title, "count": count} for title, count in sorted(c.items()) if count > 1]


def duplicate_province_rows(doc):
    rows = []
    by_province = defaultdict(list)
    for entry in doc.data["entries"]:
        if entry["tier"] != "b":
            continue
        province = province_in_entry(doc.lines, entry)
        if province is not None:
            by_province[province].append(entry_path(entry))
    for province, paths in sorted(by_province.items()):
        if len(paths) > 1:
            rows.append({"province": province, "baronies": " | ".join(paths)})
    return rows


def locator_audit():
    rows = []
    for file_name in LOCATOR_FILES:
        path = TARGET / "gfx" / "map" / "map_object_data" / file_name
        lines, _nl, _bom, _tr = read_text_lines(path)
        for item in ALIAS_MAPPINGS:
            target = extract_locator_block(lines, item["target_old_id"])
            donor = extract_locator_block(lines, item["donor_final_id"])
            comment_ok = "no"
            if target and any(f"MPE alias donor {item['old_mpe_id']}" in line for line in target[2]):
                comment_ok = "yes"
            rows.append({
                "file": file_name,
                "target_old_id": item["target_old_id"],
                "donor_final_id": item["donor_final_id"],
                "old_mpe_id": item["old_mpe_id"],
                "target_block_exists": "yes" if target else "no",
                "donor_block_exists": "yes" if donor else "no",
                "target_has_alias_comment": comment_ok,
            })
    return rows


def history_audit(doc):
    rows = []
    title_lines, _nl, _bom, _tr, title_blocks = parse_history_blocks(TITLE_HISTORY_OUT, HISTORY_HEADER_RE)
    yb_lines, _nl2, _bom2, _tr2, yb_blocks = parse_history_blocks(PROVINCE_HISTORY_MPE, PROVINCE_HISTORY_HEADER_RE)
    mb_lines, _nl3, _bom3, _tr3, mb_blocks = parse_history_blocks(PROVINCE_HISTORY_MAIN, PROVINCE_HISTORY_HEADER_RE)
    for target, donor in HISTORY_DONORS:
        active = doc.one(target) is not None
        capital = capital_barony(doc, target) if active else ""
        province = doc.province(capital) if capital else None
        rows.append({
            "target_county": target,
            "donor_county": donor,
            "active": "yes" if active else "no",
            "capital_barony": capital,
            "capital_province": province or "",
            "title_history_in_00_YB": "yes" if target in title_blocks else "no",
            "capital_province_history_file": "00_yb_MPE_PROVINCES.txt" if province and str(province) in yb_blocks else ("00_MB_PROVINCES.txt" if province and str(province) in mb_blocks else "missing"),
        })
    return rows


def default_map_category_ids():
    path = TARGET / "map_data" / "default.map"
    categories = defaultdict(set)
    if not path.exists():
        return categories
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        code = strip_comment(line)
        m = re.match(r"\s*(sea_zones|river_provinces|lakes|impassable_mountains|impassable_seas)\s*=\s*(LIST|RANGE)\s*\{([^}]*)\}", code)
        if not m:
            continue
        category, mode, body = m.groups()
        nums = [int(x) for x in re.findall(r"\d+", body)]
        if mode == "RANGE" and len(nums) >= 2:
            for value in range(nums[0], nums[1] + 1):
                categories[value].add(category)
        else:
            for value in nums:
                categories[value].add(category)
    return categories


def alias_audit(doc):
    definition = parse_definition()
    default_categories = default_map_category_ids()
    rows = []
    for item in ALIAS_MAPPINGS:
        target_entries = doc.data["by_name"].get(item["replacement_barony"], [])
        donor_entries = doc.data["by_name"].get(item["old_mpe_barony"], [])
        donor_province_paths = []
        for entry in doc.data["entries"]:
            if entry["tier"] != "b":
                continue
            province = province_in_entry(doc.lines, entry)
            if province == item["donor_final_id"]:
                donor_province_paths.append(entry_path(entry))
        donor_categories = sorted(default_categories.get(item["donor_final_id"], set()))
        if donor_entries or donor_province_paths:
            status = "blocker_donor_still_title_associated"
        elif not donor_categories:
            status = "blocker_donor_playable_no_title"
        else:
            status = "ok"
        rows.append({
            **item,
            "target_title_count": len(target_entries),
            "target_active_province": doc.province(item["replacement_barony"]) or "",
            "target_definition_name": definition.get(item["target_old_id"], {}).get("name", ""),
            "donor_title_count": len(donor_entries),
            "donor_active_title_paths": " | ".join(donor_province_paths),
            "donor_default_map_categories": " | ".join(donor_categories),
            "donor_definition_name": definition.get(item["donor_final_id"], {}).get("name", ""),
            "status": status,
        })
    return rows


def run_audit(label="manual", write=True):
    ensure_out()
    doc = LandedDoc(LANDED)
    loc_rows = localization_audit(doc)
    dup_titles = duplicate_title_rows(doc)
    dup_provinces = duplicate_province_rows(doc)
    locators = locator_audit()
    histories = history_audit(doc)
    aliases = alias_audit(doc)
    if write:
        write_rows(CONSISTENCY_OUT / f"mpe_consistency_localization_audit_{label}.csv", loc_rows, ["key", "active_in_landed_titles", "in_current", "in_mpe", "in_levi", "status"])
        write_rows(CONSISTENCY_OUT / f"mpe_consistency_duplicate_titles_{label}.csv", dup_titles, ["title", "count"])
        write_rows(CONSISTENCY_OUT / f"mpe_consistency_duplicate_provinces_{label}.csv", dup_provinces, ["province", "baronies"])
        write_rows(CONSISTENCY_OUT / f"mpe_consistency_locator_audit_{label}.csv", locators, ["file", "target_old_id", "donor_final_id", "old_mpe_id", "target_block_exists", "donor_block_exists", "target_has_alias_comment"])
        write_rows(CONSISTENCY_OUT / f"mpe_consistency_history_audit_{label}.csv", histories, ["target_county", "donor_county", "active", "capital_barony", "capital_province", "title_history_in_00_YB", "capital_province_history_file"])
        write_rows(CONSISTENCY_OUT / f"mpe_consistency_alias_audit_{label}.csv", aliases, ["old_mpe_barony", "replacement_barony", "old_mpe_id", "donor_final_id", "target_old_id", "target_county", "target_title_count", "target_active_province", "target_definition_name", "donor_title_count", "donor_active_title_paths", "donor_default_map_categories", "donor_definition_name", "status"])
    missing_loc = [row for row in loc_rows if row["status"] == "missing_all_sources"]
    alias_blockers = [row for row in aliases if row["status"].startswith("blocker")]
    locator_bad = [row for row in locators if row["target_block_exists"] != "yes" or row["target_has_alias_comment"] != "yes"]
    history_bad = [row for row in histories if row["active"] == "yes" and (row["title_history_in_00_YB"] != "yes" or row["capital_province_history_file"] == "missing")]
    summary = [
        f"# MPE Add 1 Consistency Audit ({label})",
        "",
        f"- landed_titles brace depth: `{doc.final_depth()}`",
        f"- duplicate title rows: `{len(dup_titles)}`",
        f"- duplicate province rows: `{len(dup_provinces)}`",
        f"- alias donor active title blockers: `{len(alias_blockers)}`",
        f"- locator target/comment issues: `{len(locator_bad)}`",
        f"- active history issues: `{len(history_bad)}`",
        f"- localization missing in all sources: `{len(missing_loc)}`",
        "",
        "## Known Localization Checks",
        "",
    ]
    for key in ["b_khunzakh", "c_majar", "cn_iryston"]:
        row = next((item for item in loc_rows if item["key"] == key), None)
        if row:
            summary.append(f"- `{key}`: `{row['status']}`")
    if write:
        (CONSISTENCY_OUT / f"mpe_consistency_audit_summary_{label}.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return {
        "brace_depth": doc.final_depth(),
        "duplicate_titles": len(dup_titles),
        "duplicate_provinces": len(dup_provinces),
        "alias_blockers": len(alias_blockers),
        "locator_issues": len(locator_bad),
        "history_issues": len(history_bad),
        "missing_localization": len(missing_loc),
    }


def apply_all():
    ensure_out()
    before_landed_hash = sha256(LANDED)
    before_definition_hash = sha256(DEFINITION)
    make_mapping_csvs()
    pre = run_audit("pre_apply", write=True)
    landed_report = apply_landed_structure()
    title_report = apply_title_history()
    province_report, cleanup_report = apply_province_history()
    locator_report = apply_locator_aliases()
    post = run_audit("post_apply", write=True)
    after_landed_hash = sha256(LANDED)
    after_definition_hash = sha256(DEFINITION)
    summary = [
        "# MPE Add 1 Consistency Fix Apply Summary",
        "",
        f"- landed_titles changed: `{before_landed_hash != after_landed_hash}`",
        f"- definition.csv changed: `{before_definition_hash != after_definition_hash}`",
        f"- structure action rows: `{len(landed_report)}`",
        f"- title history donor rows: `{len(title_report)}`",
        f"- province history donor rows: `{len(province_report)}`",
        f"- noncapital province cleanup rows: `{len(cleanup_report)}`",
        f"- locator apply rows: `{len(locator_report)}`",
        "",
        "## Pre/Post Audit",
        "",
    ]
    for key in ["brace_depth", "duplicate_titles", "duplicate_provinces", "alias_blockers", "locator_issues", "history_issues", "missing_localization"]:
        summary.append(f"- `{key}`: `{pre[key]}` -> `{post[key]}`")
    (CONSISTENCY_OUT / "mpe_consistency_fix_apply_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("MPE Add 1 consistency fixes applied")
    print(f"summary: {CONSISTENCY_OUT / 'mpe_consistency_fix_apply_summary.md'}")
    print(f"post: {post}")


if __name__ == "__main__":
    apply_all()
