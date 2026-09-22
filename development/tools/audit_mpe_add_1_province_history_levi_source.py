from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TARGET = PROJECT_ROOT / "BookmarksGit"
LEVI = PROJECT_ROOT.parent / "Leviathonlx MoreBookmarks-Plus" / "BookmarksGit"
OUT_DIR = PROJECT_ROOT / r"development\analysis\generated\mpe_import_add_1\closure_audit"
PROVINCE_IMPORT_CSV = PROJECT_ROOT / r"development\analysis\generated\mpe_import_add_1\mpe_province_history_import_report.csv"

REPORT_CSV = OUT_DIR / "mpe_add_1_province_history_levi_source_audit.csv"
SUMMARY_MD = OUT_DIR / "mpe_add_1_province_history_levi_source_audit_summary.md"
CANDIDATE_CSV = OUT_DIR / "mpe_add_1_province_history_capital_fix_candidates.csv"

FIELDS = [
    "barony",
    "target_province_id",
    "active_province_id",
    "current_county",
    "current_capital_barony",
    "is_county_capital",
    "expected_culture",
    "expected_religion",
    "actual_culture",
    "actual_religion",
    "levi_source_type",
    "levi_source_id",
    "levi_source_title",
    "donor_comment_id",
    "donor_comment_raw",
    "donor_resolution",
    "yusseter_blocks",
    "source_match_status",
    "issue",
    "recommendation",
]

TITLE_RE = re.compile(r"^\s*((?:e|k|d|c|b)_[A-Za-z0-9_'\-]+)\s*=\s*\{")
PROVINCE_RE = re.compile(r"\bprovince\s*=\s*(\d+)\b")
CAPITAL_RE = re.compile(r"^\s*capital\s*=\s*(b_[A-Za-z0-9_'\-]+)\b")
HISTORY_RE = re.compile(r"^\s*(\d+)\s*=\s*\{")
ASSIGN_RE = re.compile(r"^\s*(culture|religion)\s*=\s*([A-Za-z0-9_:\-]+)\b")
DONOR_RE = re.compile(r"\bdonor\b[^#\n]*/(\d+)\b")


def read_text(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str] = FIELDS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


class LandedDoc:
    def __init__(self, path: Path) -> None:
        self.lines = read_text(path).splitlines()
        self.entries: list[dict[str, object]] = []
        self.by_name: dict[str, list[dict[str, object]]] = {}
        self.barony_to_province: dict[str, int] = {}
        self.province_to_barony: dict[int, str] = {}
        self._parse()

    def _parse(self) -> None:
        stack: list[dict[str, object]] = []
        depth = 0
        for index, line in enumerate(self.lines):
            code = strip_comment(line)
            match = TITLE_RE.search(code)
            if match:
                title = match.group(1)
                parents = {str(item["tier"]): str(item["name"]) for item in stack}
                entry: dict[str, object] = {
                    "name": title,
                    "tier": title[0],
                    "start": index,
                    "end": len(self.lines) - 1,
                    "depth": depth,
                    "parents": parents,
                }
                self.entries.append(entry)
                self.by_name.setdefault(title, []).append(entry)
                stack.append(entry)

            province_match = PROVINCE_RE.search(code)
            if province_match:
                current_barony = next((item for item in reversed(stack) if item["tier"] == "b"), None)
                if current_barony:
                    province_id = int(province_match.group(1))
                    barony = str(current_barony["name"])
                    self.barony_to_province[barony] = province_id
                    self.province_to_barony[province_id] = barony

            new_depth = depth + code.count("{") - code.count("}")
            while stack and new_depth <= int(stack[-1]["depth"]):
                stack[-1]["end"] = index
                stack.pop()
            depth = new_depth

    def entries_for(self, title: str) -> list[dict[str, object]]:
        return self.by_name.get(title, [])

    def entry_for_barony(self, barony: str, province_id: int | None) -> dict[str, object] | None:
        entries = [entry for entry in self.entries_for(barony) if entry.get("tier") == "b"]
        if province_id is not None:
            matches = [entry for entry in entries if self.barony_to_province.get(barony) == province_id]
            if matches:
                return matches[0]
        return entries[0] if len(entries) == 1 else None

    def county_entry(self, county: str) -> dict[str, object] | None:
        entries = [entry for entry in self.entries_for(county) if entry.get("tier") == "c"]
        return entries[0] if entries else None

    def explicit_county_capital(self, county_entry: dict[str, object]) -> str:
        start = int(county_entry["start"])
        end = int(county_entry["end"])
        depth = 1
        for line in self.lines[start + 1 : end + 1]:
            code = strip_comment(line)
            if depth == 1:
                match = CAPITAL_RE.match(code)
                if match:
                    return match.group(1)
            depth += code.count("{") - code.count("}")
        return ""

    def first_county_barony(self, county: str) -> str:
        children = [
            entry
            for entry in self.entries
            if entry.get("tier") == "b" and dict(entry.get("parents", {})).get("c") == county
        ]
        children.sort(key=lambda entry: int(entry["start"]))
        return str(children[0]["name"]) if children else ""

    def capital_barony_for_county(self, county: str) -> str:
        county_entry = self.county_entry(county)
        if not county_entry:
            return ""
        explicit = self.explicit_county_capital(county_entry)
        return explicit or self.first_county_barony(county)


class HistoryIndex:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.blocks: dict[int, list[dict[str, object]]] = {}
        self._parse_folder(root / "history" / "provinces")

    def _parse_folder(self, folder: Path) -> None:
        if not folder.exists():
            return
        for path in sorted(folder.glob("*.txt")):
            lines = read_text(path).splitlines()
            index = 0
            while index < len(lines):
                code = strip_comment(lines[index])
                match = HISTORY_RE.match(code)
                if not match:
                    index += 1
                    continue
                province_id = int(match.group(1))
                start = index
                depth = code.count("{") - code.count("}")
                while depth > 0 and index + 1 < len(lines):
                    index += 1
                    depth += strip_comment(lines[index]).count("{") - strip_comment(lines[index]).count("}")
                end = index
                block_lines = lines[start : end + 1]
                self.blocks.setdefault(province_id, []).append(
                    {
                        "province": province_id,
                        "path": path,
                        "start": start + 1,
                        "end": end + 1,
                        "lines": block_lines,
                        "title_guess": guess_title(block_lines[0]),
                        "header": block_lines[0],
                    }
                )
                index += 1

    def get(self, province_id: int | None) -> list[dict[str, object]]:
        return [] if province_id is None else self.blocks.get(province_id, [])


def guess_title(header: str) -> str:
    match = re.search(r"#\s*((?:b|c)_[A-Za-z0-9_'\-]+)\b", header)
    return match.group(1) if match else ""


def rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def block_ref(root: Path, block: dict[str, object]) -> str:
    title = str(block.get("title_guess") or "")
    suffix = f":{title}" if title else ""
    return f"{rel(root, Path(block['path']))}:{block['start']}-{block['end']}{suffix}"


def top_level_culture_religion(blocks: list[dict[str, object]]) -> tuple[str, str]:
    culture = ""
    religion = ""
    for block in blocks:
        depth = 0
        for index, line in enumerate(block["lines"]):
            code = strip_comment(str(line))
            if index == 0:
                depth += code.count("{") - code.count("}")
                continue
            if depth == 1:
                match = ASSIGN_RE.match(code)
                if match and match.group(1) == "culture" and not culture:
                    culture = match.group(2)
                if match and match.group(1) == "religion" and not religion:
                    religion = match.group(2)
            depth += code.count("{") - code.count("}")
    return culture, religion


def imported_rows() -> list[dict[str, str]]:
    rows = []
    for row in read_csv(PROVINCE_IMPORT_CSV):
        if row.get("status") not in {"added", "updated", "kept"}:
            continue
        if not row.get("barony") or not row.get("target_id"):
            continue
        rows.append(row)
    return rows


def parse_donor_comment(blocks: list[dict[str, object]]) -> tuple[int | None, str]:
    for block in blocks:
        header = str(block.get("header", ""))
        comment = header.split("#", 1)[1].strip() if "#" in header else ""
        match = DONOR_RE.search(comment)
        if match:
            return int(match.group(1)), comment
    return None, ""


def path_name(block: dict[str, object]) -> str:
    return Path(block["path"]).name


def choose_donor_blocks(donor_id: int | None, donor_raw: str, target_history: HistoryIndex, levi_history: HistoryIndex) -> tuple[list[dict[str, object]], str]:
    if donor_id is None:
        return [], "none"

    target_blocks = target_history.get(donor_id)
    levi_blocks = levi_history.get(donor_id)
    raw_lower = donor_raw.lower()

    def has_values(block: dict[str, object]) -> bool:
        culture, religion = top_level_culture_religion([block])
        return bool(culture or religion)

    if "asil_mod" in raw_lower:
        mb_blocks = [block for block in target_blocks if path_name(block) == "00_MB_PROVINCES.txt"]
        if mb_blocks:
            return mb_blocks, "explicit_comment_00_MB_PROVINCES"
        if levi_blocks:
            return levi_blocks, "explicit_comment_levi_history"

    valued_target_blocks = [block for block in target_blocks if has_values(block)]
    if valued_target_blocks:
        return valued_target_blocks, "explicit_comment_current_history"
    if target_blocks:
        return target_blocks, "explicit_comment_current_history_no_top_level_values"
    if levi_blocks:
        return levi_blocks, "explicit_comment_levi_history"
    return [], "explicit_comment_missing_history_block"


def classify_row(row: dict[str, str], target_doc: LandedDoc, target_history: HistoryIndex, levi_history: HistoryIndex) -> dict[str, str]:
    barony = row["barony"]
    target_id = int(row["target_id"])
    y_blocks = target_history.get(target_id)
    active_province = target_doc.barony_to_province.get(barony)
    y_ref = " | ".join(block_ref(TARGET, block) for block in y_blocks)
    actual_culture, actual_religion = top_level_culture_religion(y_blocks)

    barony_entry = target_doc.entry_for_barony(barony, active_province)
    current_county = ""
    if barony_entry:
        current_county = str(dict(barony_entry.get("parents", {})).get("c", ""))
    current_capital = target_doc.capital_barony_for_county(current_county) if current_county else ""
    is_capital = "yes" if current_capital and current_capital == barony else "no"

    donor_id, donor_raw = parse_donor_comment(y_blocks)
    donor_blocks, donor_resolution = choose_donor_blocks(donor_id, donor_raw, target_history, levi_history)
    donor_culture, donor_religion = top_level_culture_religion(donor_blocks)

    expected_culture = donor_culture
    expected_religion = donor_religion
    source_type = donor_resolution
    source_id = str(donor_id or "")
    source_title = ""
    if donor_blocks:
        source_title = str(donor_blocks[0].get("title_guess") or target_doc.province_to_barony.get(donor_id or -1, ""))

    if not donor_id and is_capital == "yes":
        expected_culture = row.get("culture", "")
        expected_religion = row.get("religion", "")
        source_type = "import_report_fallback"
        source_id = row.get("donor_province_id", "")
        source_title = row.get("donor_barony") or row.get("donor_county", "")

    base = {
        "barony": barony,
        "target_province_id": str(target_id),
        "active_province_id": str(active_province or ""),
        "current_county": current_county,
        "current_capital_barony": current_capital,
        "is_county_capital": is_capital,
        "expected_culture": expected_culture,
        "expected_religion": expected_religion,
        "actual_culture": actual_culture,
        "actual_religion": actual_religion,
        "levi_source_type": source_type,
        "levi_source_id": source_id,
        "levi_source_title": source_title,
        "donor_comment_id": str(donor_id or ""),
        "donor_comment_raw": donor_raw,
        "donor_resolution": donor_resolution,
        "yusseter_blocks": y_ref,
    }

    if active_province != target_id:
        return {
            **base,
            "source_match_status": "scope_excluded_or_retargeted",
            "issue": "active_landed_province_differs",
            "recommendation": f"Import row target is {target_id}, active landed province is {active_province}; review alias/relocation reports, not province history donor.",
        }

    if is_capital != "yes":
        if not y_blocks:
            return {
                **base,
                "source_match_status": "missing_yusseter_block",
                "issue": "missing_non_capital_history_block",
                "recommendation": "Non-capital province history is allowed to be holding-only, but the imported target block is missing.",
            }
        if actual_culture or actual_religion:
            return {
                **base,
                "source_match_status": "accepted_deviation",
                "issue": "non_capital_culture_religion_accepted",
                "recommendation": "Accepted by project decision: non-capital culture/religion is not a blocker in this MPE closure pass.",
            }
        return {
            **base,
            "source_match_status": "not_checked",
            "issue": "non_capital_holding_history_ok",
            "recommendation": "No donor validation required for non-capital holding-only history.",
        }

    if not y_blocks:
        return {
            **base,
            "source_match_status": "missing_yusseter_block",
            "issue": "missing_capital_history_block",
            "recommendation": "Create the capital province history block with expected culture/religion once donor is confirmed.",
        }

    if donor_id and not donor_blocks:
        return {
            **base,
            "source_match_status": "needs_manual_review",
            "issue": "explicit_donor_missing_history_block",
            "recommendation": "Explicit donor comment exists, but no matching current/Levi province history block was found; do not auto-fix.",
        }

    if donor_id and not expected_culture and not expected_religion:
        return {
            **base,
            "source_match_status": "needs_manual_review",
            "issue": "explicit_donor_has_no_top_level_culture_religion",
            "recommendation": "Explicit donor exists but has no top-level culture/religion; keep visible for manual interpretation, not auto-fix.",
        }

    if expected_culture and actual_culture != expected_culture:
        return {
            **base,
            "source_match_status": "missing_or_mismatch",
            "issue": "capital_culture_mismatch",
            "recommendation": "Set top-level culture only after confirming the explicit/current donor is correct.",
        }

    if expected_religion and actual_religion != expected_religion:
        return {
            **base,
            "source_match_status": "missing_or_mismatch",
            "issue": "capital_religion_mismatch",
            "recommendation": "Set top-level religion only after confirming the explicit/current donor is correct.",
        }

    if not expected_culture or not expected_religion:
        return {
            **base,
            "source_match_status": "needs_manual_review",
            "issue": "capital_missing_expected_culture_or_religion",
            "recommendation": "Resolve the donor rule for this current county capital before treating it as fixed or broken.",
        }

    if source_type == "import_report_fallback" or source_type.endswith("no_top_level_values"):
        return {
            **base,
            "source_match_status": "matches_source_with_review_note",
            "issue": "fallback_or_weak_source_used_for_capital",
            "recommendation": "Values match, but source provenance should remain visible in review.",
        }

    return {
        **base,
        "source_match_status": "matches_source",
        "issue": "ok",
        "recommendation": "No action needed.",
    }


def build_rows() -> list[dict[str, str]]:
    target_doc = LandedDoc(TARGET / r"common\landed_titles\00_landed_titles.txt")
    target_history = HistoryIndex(TARGET)
    levi_history = HistoryIndex(LEVI)
    return [classify_row(row, target_doc, target_history, levi_history) for row in imported_rows()]


def write_summary(rows: list[dict[str, str]]) -> None:
    by_status = Counter(row["source_match_status"] for row in rows)
    by_issue = Counter(row["issue"] for row in rows)
    capital_rows = [row for row in rows if row["is_county_capital"] == "yes"]
    noncapital_rows = [row for row in rows if row["is_county_capital"] != "yes"]
    candidates = [row for row in rows if row["source_match_status"] == "missing_or_mismatch"]

    lines = [
        "# MPE Add 1 Province History Current-State Donor Audit",
        "",
        f"- rows: `{len(rows)}`",
        f"- current county capital rows: `{len(capital_rows)}`",
        f"- current non-capital rows: `{len(noncapital_rows)}`",
        f"- missing/mismatch candidates: `{len(candidates)}`",
        f"- target repo: `{TARGET}`",
        f"- authoritative base repo for explicit `asil_mod` donor fallback: `{LEVI}`",
        "",
        "## By source_match_status",
        "",
    ]
    lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(by_status.items()))
    lines.extend(["", "## By issue", ""])
    lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(by_issue.items()))
    lines.extend(["", "## Rule", ""])
    lines.append("- County capital status is recalculated from current `common/landed_titles/00_landed_titles.txt`.")
    lines.append("- Explicit `# Yusseter: ... donor .../ID` comments in current province history override stale import-report donors.")
    lines.append("- Non-capital culture/religion is accepted by project decision and is not a blocker.")
    lines.append("- Donors with no top-level culture/religion are manual-review rows, not auto-fix candidates.")
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = build_rows()
    candidates = [row for row in rows if row["source_match_status"] == "missing_or_mismatch"]
    write_csv(REPORT_CSV, rows)
    write_csv(CANDIDATE_CSV, candidates)
    write_summary(rows)
    print(f"wrote {REPORT_CSV}")
    print(f"wrote {CANDIDATE_CSV}")
    print(f"wrote {SUMMARY_MD}")
    print(dict(Counter(row["source_match_status"] for row in rows)))


if __name__ == "__main__":
    main()
