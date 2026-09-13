from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from PIL import Image, ImageDraw, ImageFont

from audit_geographical_region_closure import (
    Block,
    Entry,
    RegionResolver,
    SILK_COLORS,
    SourceText,
    bare_tokens,
    bookmarks_root,
    collect_effective_sources,
    collect_git_sources,
    collect_plain_sources,
    current_landed_province_ids,
    file_sha256,
    git_revision,
    load_effective_titles,
    parse_definition,
    parse_region_source_set,
    parse_top_level,
    read_text,
    render_province_overlay,
    scan_map_geometry,
    write_csv,
)


SITUATION_RELATIVE = Path("common/situation/situations/tgp_silk_road.txt")
DECISION_RELATIVE = Path(
    "common/decisions/dlc_decisions/tgp/tgp_silk_road_decisions.txt"
)
GUI_RELATIVES = (
    Path("gui/window_silk_road.gui"),
    Path("gui/shared/misc_components.gui"),
)
SILK_PREFIX = "region_silk_road_proper_"
SUFFIX_ORDER = (
    "china",
    "tibet",
    "india",
    "central_asia",
    "transcaspia",
    "occident",
    "middle_east",
    "sea",
)
CURRENT_SCOPE_EXCLUSIONS = {
    "sea": {
        "reason": "vanilla_east_policy_excludes_asil_mod_sea_extension",
        "building_ids": ("angkor_market_01", "angkor_market_02"),
    },
}
ACTIVE_SUFFIX_ORDER = tuple(
    suffix for suffix in SUFFIX_ORDER if suffix not in CURRENT_SCOPE_EXCLUSIONS
)
REGION_SUFFIX = {"middle_east": "mideast"}
LOC_LINE_RE = re.compile(
    r"^\s*([A-Za-z0-9_.\-']+)(?::\d+)?\s*:\s*(.*)$"
)
TITLE_SCOPE_RE = re.compile(r"^title:(c_[A-Za-z0-9_'\-]+)$")
BUILDING_LOC_REF_RE = re.compile(r"\$(building_[A-Za-z0-9_'\-]+)\$")
SPECIAL_BUILDING_ACTIONS = {
    "add_special_building",
    "add_special_building_slot",
    "special_building",
}
SPECIAL_BUILDING_KEYS = SPECIAL_BUILDING_ACTIONS | {"special_building_slot"}


@dataclass
class BuildingDefinition:
    building_id: str
    path: str
    line: int
    source_layer: str
    flags: list[str]
    building_type: str
    next_building: str
    signature_sha256: str
    provenance: str = ""


@dataclass
class Placement:
    province_id: int
    building_id: str
    action: str
    path: str
    line: int
    source_layer: str
    context: str


@dataclass
class LocalizationValue:
    key: str
    value: str
    path: str
    line: int
    source_layer: str
    quote_status: str


@dataclass
class Subregion:
    key: str
    suffix: str
    region_names: list[str]
    center_id: int
    path: str
    line: int


@dataclass
class DecisionItem:
    suffix: str
    county_titles: list[str]
    localization_key: str
    line: int


@dataclass
class ProvinceRelation:
    source_id: int
    target_id: int
    classification: str
    confidence: str
    overlap_score: str
    source_name: str
    target_name: str
    top_candidates: str


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[3]
    projects_root = repo_root.parent
    parser = argparse.ArgumentParser(
        description=(
            "Audit the complete Silk Road subregion center, market building, "
            "province history, decision, localization, locator, and static GUI "
            "chain without editing live CK3 mod content."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--asil-mod-root",
        type=Path,
        default=projects_root / "Leviathonlx MoreBookmarks-Plus",
    )
    parser.add_argument(
        "--vanilla-root",
        type=Path,
        default=Path(
            r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
        ),
    )
    parser.add_argument("--premerge-revision", default="09588cbb5")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--relation-csv",
        type=Path,
        default=None,
        help="Current-state asil-mod to Yusseter province relation CSV.",
    )
    parser.add_argument(
        "--locator-audit-csv",
        type=Path,
        default=None,
        help="Latest map-object locator audit CSV.",
    )
    parser.add_argument("--skip-control-png", action="store_true")
    return parser.parse_args()


def normalized_suffix(value: str) -> str:
    return value.strip().lower().replace("mideast", "middle_east")


def region_name_for_suffix(suffix: str) -> str:
    return f"tgp_silk_road_{REGION_SUFFIX.get(suffix, suffix)}_region"


def block_signature(block: Block) -> str:
    def serialize(current: Block) -> str:
        chunks: list[str] = []
        for entry in current.entries:
            key = entry.key or ""
            value = serialize(entry.value) if isinstance(entry.value, Block) else str(entry.value)
            chunks.append(f"{key}={value}")
        return "{" + "|".join(chunks) + "}"

    return hashlib.sha256(serialize(block).encode("utf-8")).hexdigest()


def walk_block(
    block: Block,
    parents: tuple[str, ...] = (),
) -> Iterator[tuple[Entry, tuple[str, ...]]]:
    for entry in block.entries:
        yield entry, parents
        if isinstance(entry.value, Block):
            next_parents = parents + ((entry.key or "{}"),)
            yield from walk_block(entry.value, next_parents)


def direct_values(block: Block, key: str) -> list[tuple[str, int]]:
    return [
        (str(entry.value), entry.line)
        for entry in block.entries
        if entry.key == key and isinstance(entry.value, str)
    ]


def recursive_values(block: Block, key: str) -> list[tuple[str, int]]:
    return [
        (str(entry.value), entry.line)
        for entry, _ in walk_block(block)
        if entry.key == key and isinstance(entry.value, str)
    ]


def git_text(repo_root: Path, revision: str, relative_path: Path) -> str:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path.as_posix()}"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout if result.returncode == 0 else ""


def stable_finding_id(classification: str, suffix: str, obj: str) -> str:
    raw = f"{classification}|{suffix}|{obj}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def make_finding(
    classification: str,
    severity: str,
    confidence: str,
    suffix: str,
    path: str,
    line: int,
    obj: str,
    reason: str,
    recommendation: str,
    *,
    root_cause_key: str = "",
    current_value: str = "",
    candidate_value: str = "",
    provenance: str = "",
    evidence: str = "",
) -> dict[str, str]:
    return {
        "finding_id": stable_finding_id(classification, suffix, obj),
        "classification": classification,
        "root_cause_key": root_cause_key or f"{classification}:{suffix}:{obj}",
        "severity": severity,
        "confidence": confidence,
        "subregion": suffix,
        "path": path,
        "line": str(line),
        "object": obj,
        "current_value": current_value,
        "candidate_value": candidate_value,
        "reason": reason,
        "recommendation": recommendation,
        "provenance": provenance,
        "evidence": evidence,
    }


def parse_building_sources(
    sources: Iterable[SourceText],
) -> tuple[
    dict[str, BuildingDefinition],
    dict[str, list[BuildingDefinition]],
    list[str],
]:
    all_definitions: dict[str, list[BuildingDefinition]] = defaultdict(list)
    diagnostics: list[str] = []
    for source in sources:
        entries, source_diagnostics = parse_top_level(source.text)
        if not entries and source_diagnostics:
            diagnostics.append(
                f"{source.source_layer}:{source.relative_path}:no_top_level_building_blocks"
            )
        for entry in entries:
            if not entry.key or not isinstance(entry.value, Block):
                continue
            flags = [value for value, _ in direct_values(entry.value, "flag")]
            type_values = direct_values(entry.value, "type")
            next_values = direct_values(entry.value, "next_building")
            all_definitions[entry.key].append(
                BuildingDefinition(
                    building_id=entry.key,
                    path=source.relative_path,
                    line=entry.line,
                    source_layer=source.source_layer,
                    flags=flags,
                    building_type=type_values[-1][0] if type_values else "",
                    next_building=next_values[-1][0] if next_values else "",
                    signature_sha256=block_signature(entry.value),
                )
            )
    effective = {
        key: definitions[-1]
        for key, definitions in sorted(all_definitions.items())
    }
    return effective, dict(all_definitions), diagnostics


def apply_building_provenance(
    current: dict[str, BuildingDefinition],
    premerge: dict[str, BuildingDefinition],
    asil: dict[str, BuildingDefinition],
    vanilla: dict[str, BuildingDefinition],
) -> None:
    for building_id, definition in current.items():
        if definition.source_layer == "vanilla_fallback":
            definition.provenance = "vanilla_effective_fallback"
            continue
        same_premerge = (
            building_id in premerge
            and definition.signature_sha256 == premerge[building_id].signature_sha256
        )
        same_asil = (
            building_id in asil
            and definition.signature_sha256 == asil[building_id].signature_sha256
        )
        same_vanilla = (
            building_id in vanilla
            and definition.signature_sha256 == vanilla[building_id].signature_sha256
        )
        if same_premerge and same_asil:
            definition.provenance = "shared_premerge_and_asil"
        elif same_premerge:
            definition.provenance = "preexisting_yusseter"
        elif same_asil:
            definition.provenance = "shared_asil_mod"
        elif same_vanilla:
            definition.provenance = "shared_vanilla"
        elif building_id in premerge or building_id in asil or building_id in vanilla:
            definition.provenance = "yusseter_adapted"
        else:
            definition.provenance = "yusseter_current_only"


def parse_history_placements(
    sources: Iterable[SourceText],
) -> tuple[list[Placement], list[str]]:
    placements: list[Placement] = []
    diagnostics: list[str] = []
    for source in sources:
        entries, source_diagnostics = parse_top_level(source.text)
        diagnostics.extend(
            f"{source.source_layer}:{source.relative_path}:{item}"
            for item in source_diagnostics
        )
        for entry in entries:
            if not entry.key or not entry.key.isdigit() or not isinstance(entry.value, Block):
                continue
            province_id = int(entry.key)
            for child, parents in walk_block(entry.value):
                if (
                    child.key in SPECIAL_BUILDING_KEYS
                    and isinstance(child.value, str)
                ):
                    placements.append(
                        Placement(
                            province_id=province_id,
                            building_id=str(child.value),
                            action=str(child.key),
                            path=source.relative_path,
                            line=child.line,
                            source_layer=source.source_layer,
                            context=" > ".join(parents),
                        )
                    )
    return placements, diagnostics


def parse_situation_text(text: str, path: str) -> tuple[dict[str, Subregion], list[str]]:
    entries, diagnostics = parse_top_level(text)
    situation = next(
        (
            entry.value
            for entry in entries
            if entry.key == "silk_road_situation" and isinstance(entry.value, Block)
        ),
        None,
    )
    if situation is None:
        return {}, diagnostics + [f"{path}:missing_silk_road_situation"]
    subregions_block = next(
        (
            entry.value
            for entry in situation.entries
            if entry.key == "sub_regions" and isinstance(entry.value, Block)
        ),
        None,
    )
    if subregions_block is None:
        return {}, diagnostics + [f"{path}:missing_sub_regions"]
    result: dict[str, Subregion] = {}
    for entry in subregions_block.entries:
        if (
            not entry.key
            or not entry.key.startswith(SILK_PREFIX)
            or not isinstance(entry.value, Block)
        ):
            continue
        suffix = normalized_suffix(entry.key[len(SILK_PREFIX) :])
        center_values = direct_values(entry.value, "capital_province")
        region_block = next(
            (
                child.value
                for child in entry.value.entries
                if child.key == "geographical_regions" and isinstance(child.value, Block)
            ),
            None,
        )
        region_names = [value for value, _ in bare_tokens(region_block)] if region_block else []
        center_id = 0
        if center_values and center_values[-1][0].isdigit():
            center_id = int(center_values[-1][0])
        result[suffix] = Subregion(
            key=entry.key,
            suffix=suffix,
            region_names=region_names,
            center_id=center_id,
            path=path,
            line=center_values[-1][1] if center_values else entry.line,
        )
    return result, []


def parse_decision_text(text: str) -> tuple[dict[str, DecisionItem], list[str]]:
    entries, diagnostics = parse_top_level(text)
    decision = next(
        (
            entry.value
            for entry in entries
            if entry.key == "visit_silk_road_market_decision"
            and isinstance(entry.value, Block)
        ),
        None,
    )
    if decision is None:
        return {}, diagnostics + ["missing_visit_silk_road_market_decision"]
    result: dict[str, DecisionItem] = {}
    for item, _ in walk_block(decision):
        if item.key != "item" or not isinstance(item.value, Block):
            continue
        suffix_values = recursive_values(item.value, "SUB_REGION")
        if not suffix_values:
            continue
        suffix = normalized_suffix(suffix_values[0][0])
        title_scopes: set[str] = set()
        for child, _ in walk_block(item.value):
            if not child.key:
                continue
            match = TITLE_SCOPE_RE.match(child.key)
            if match:
                title_scopes.add(match.group(1))
        localization_values = direct_values(item.value, "localization")
        result[suffix] = DecisionItem(
            suffix=suffix,
            county_titles=sorted(title_scopes),
            localization_key=(
                localization_values[-1][0] if localization_values else ""
            ),
            line=item.line,
        )
    return result, []


def localization_file_order(
    current_mod: Path,
    vanilla_root: Path,
) -> list[tuple[str, Path, Path]]:
    ordered: list[tuple[str, Path, Path]] = []
    vanilla_loc = vanilla_root / "localization"
    if vanilla_loc.exists():
        ordered.extend(
            ("vanilla", path, vanilla_loc)
            for path in sorted(vanilla_loc.rglob("*.yml"))
        )
    current_loc = current_mod / "localization"
    if current_loc.exists():
        regular = [
            path
            for path in current_loc.rglob("*.yml")
            if "replace" not in path.relative_to(current_loc).parts
        ]
        replace_root = current_loc / "replace"
        replacement = sorted(replace_root.rglob("*.yml")) if replace_root.exists() else []
        ordered.extend(("current_mod", path, current_mod) for path in sorted(regular))
        ordered.extend(("current_replace", path, current_mod) for path in replacement)
    return ordered


def parse_localization(
    files: Iterable[tuple[str, Path, Path]],
) -> tuple[
    dict[str, LocalizationValue],
    dict[str, list[LocalizationValue]],
    list[dict[str, object]],
]:
    all_values: dict[str, list[LocalizationValue]] = defaultdict(list)
    diagnostics: list[dict[str, object]] = []
    for layer, path, display_root in files:
        text = read_text(path)
        lines = text.splitlines()
        first_content = next(
            (line.strip().lstrip("\ufeff") for line in lines if line.strip()),
            "",
        )
        if first_content != "l_english:":
            if path.name.endswith("_l_english.yml") and layer.startswith("current"):
                diagnostics.append(
                    {
                        "source": "localization",
                        "path": path.relative_to(display_root).as_posix(),
                        "line": 1,
                        "diagnostic": "missing_or_displaced_l_english_header",
                    }
                )
            continue
        for line_number, raw_line in enumerate(lines, start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or stripped == "l_english:":
                continue
            match = LOC_LINE_RE.match(raw_line)
            if not match:
                continue
            key = match.group(1)
            raw_value = match.group(2).strip()
            quote_status = "not_quoted"
            value = raw_value
            if raw_value.startswith('"'):
                last_quote = raw_value.rfind('"')
                trailing = raw_value[last_quote + 1 :].strip() if last_quote > 0 else ""
                quote_status = (
                    "valid"
                    if last_quote > 0 and (not trailing or trailing.startswith("#"))
                    else "missing_end_quote"
                )
                if quote_status == "valid":
                    value = raw_value[1:last_quote]
                else:
                    value = raw_value[1:]
                    if layer.startswith("current"):
                        diagnostics.append(
                            {
                                "source": "localization",
                                "path": path.relative_to(display_root).as_posix(),
                                "line": line_number,
                                "diagnostic": f"missing_end_quote:{key}",
                            }
                        )
            item = LocalizationValue(
                key=key,
                value=value,
                path=path.relative_to(display_root).as_posix(),
                line=line_number,
                source_layer=layer,
                quote_status=quote_status,
            )
            all_values[key].append(item)
    effective = {key: values[-1] for key, values in sorted(all_values.items())}
    return effective, dict(all_values), diagnostics


def localization_raw_signature(text: str, key: str) -> str:
    for raw_line in text.splitlines():
        match = LOC_LINE_RE.match(raw_line)
        if match and match.group(1) == key:
            return match.group(2).strip()
    return ""


def localization_entry_provenance(
    item: LocalizationValue | None,
    *,
    current_mod: Path,
    repo_root: Path,
    premerge_revision: str,
    asil_mod: Path,
) -> str:
    if item is None:
        return "missing_current"
    if not item.source_layer.startswith("current"):
        return item.source_layer
    relative = Path(item.path)
    current_path = current_mod / relative
    current_signature = localization_raw_signature(
        read_text(current_path) if current_path.is_file() else "",
        item.key,
    )
    premerge_signature = localization_raw_signature(
        git_text(
            repo_root,
            premerge_revision,
            Path("BookmarksGit") / relative,
        ),
        item.key,
    )
    asil_path = asil_mod / relative
    asil_signature = localization_raw_signature(
        read_text(asil_path) if asil_path.is_file() else "",
        item.key,
    )
    same_premerge = bool(current_signature) and current_signature == premerge_signature
    same_asil = bool(current_signature) and current_signature == asil_signature
    if same_premerge and same_asil:
        return "shared_premerge_and_asil"
    if same_premerge:
        return "preexisting_yusseter"
    if same_asil:
        return "shared_asil_mod"
    if premerge_signature or asil_signature:
        return "yusseter_adapted"
    return "yusseter_current_only"


def load_relations(path: Path) -> dict[int, ProvinceRelation]:
    if not path.exists():
        return {}
    result: dict[int, ProvinceRelation] = {}
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for raw_row in csv.DictReader(handle):
            row = {(key or "").strip(): (value or "").strip() for key, value in raw_row.items()}
            if not row.get("source_province_id", "").isdigit():
                continue
            source_id = int(row["source_province_id"])
            target_id = int(row["target_province_id"]) if row.get("target_province_id", "").isdigit() else 0
            result[source_id] = ProvinceRelation(
                source_id=source_id,
                target_id=target_id,
                classification=row.get("classification", ""),
                confidence=row.get("confidence", ""),
                overlap_score=row.get("overlap_score", ""),
                source_name=row.get("source_name", ""),
                target_name=row.get("target_name", ""),
                top_candidates=row.get("top_candidates", ""),
            )
    return result


def load_locator_rows(path: Path) -> dict[int, list[dict[str, str]]]:
    if not path.exists():
        return {}
    result: dict[int, list[dict[str, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("file") != "special_building_locators.txt":
                continue
            value = row.get("province_id", "")
            if value.isdigit():
                result[int(value)].append(dict(row))
    return dict(result)


def active_placements(placements: Iterable[Placement]) -> list[Placement]:
    return [
        item
        for item in placements
        if item.action in {"add_special_building", "special_building"}
    ]


def index_placements(
    placements: Iterable[Placement],
) -> tuple[dict[str, list[Placement]], dict[int, list[Placement]]]:
    by_building: dict[str, list[Placement]] = defaultdict(list)
    by_province: dict[int, list[Placement]] = defaultdict(list)
    seen: set[tuple[int, str, str, str, int]] = set()
    for item in active_placements(placements):
        key = (item.province_id, item.building_id, item.action, item.path, item.line)
        if key in seen:
            continue
        seen.add(key)
        by_building[item.building_id].append(item)
        by_province[item.province_id].append(item)
    return dict(by_building), dict(by_province)


def build_title_indexes(
    titles: dict[str, object],
) -> tuple[
    dict[int, list[str]],
    dict[str, str],
    dict[str, int],
    dict[str, set[int]],
]:
    province_to_baronies: dict[int, list[str]] = defaultdict(list)
    barony_to_county: dict[str, str] = {}
    county_capital: dict[str, int] = {}
    county_provinces: dict[str, set[int]] = {}
    county_baronies: dict[str, list[object]] = defaultdict(list)
    for title_id, block in titles.items():
        if title_id.startswith("b_"):
            for province_id in block.direct_province_ids:
                province_to_baronies[province_id].append(title_id)
            parent = block.parent_id
            while parent and not parent.startswith("c_"):
                parent_block = titles.get(parent)
                parent = parent_block.parent_id if parent_block else ""
            if parent:
                barony_to_county[title_id] = parent
                county_baronies[parent].append(block)
        elif title_id.startswith("c_"):
            county_provinces[title_id] = set(block.descendant_province_ids)
    for county_id, baronies in county_baronies.items():
        county = titles.get(county_id)
        direct_capital = county.direct_capital if county else ""
        capital_block = titles.get(direct_capital) if direct_capital.startswith("b_") else None
        if capital_block and capital_block.direct_province_ids:
            county_capital[county_id] = capital_block.direct_province_ids[0]
            continue
        first = min(
            (barony for barony in baronies if barony.direct_province_ids),
            key=lambda block: (block.source_file, block.start_line),
            default=None,
        )
        if first:
            county_capital[county_id] = first.direct_province_ids[0]
    return (
        {key: sorted(values) for key, values in province_to_baronies.items()},
        barony_to_county,
        county_capital,
        county_provinces,
    )


def center_provenance(
    suffix: str,
    current: dict[str, Subregion],
    premerge: dict[str, Subregion],
    asil: dict[str, Subregion],
) -> str:
    current_item = current.get(suffix)
    if not current_item:
        return "missing_current"
    same_premerge = suffix in premerge and premerge[suffix].center_id == current_item.center_id
    same_asil = suffix in asil and asil[suffix].center_id == current_item.center_id
    if same_premerge and same_asil:
        return "shared_premerge_and_asil"
    if same_premerge:
        return "preexisting_yusseter"
    if same_asil:
        return "shared_asil_mod"
    if suffix in premerge or suffix in asil:
        return "yusseter_adapted"
    return "yusseter_current_only"


def ids(values: Iterable[int]) -> str:
    return " ".join(str(value) for value in sorted(set(values)))


def placement_evidence(values: Iterable[Placement]) -> str:
    return " | ".join(
        f"{item.province_id}:{item.building_id}:{item.path}:{item.line}"
        for item in sorted(
            values,
            key=lambda row: (row.province_id, row.building_id, row.path, row.line),
        )
    )


def localization_status(value: LocalizationValue | None) -> str:
    if value is None:
        return "missing"
    if value.quote_status == "missing_end_quote":
        return "malformed_missing_end_quote"
    return "present"


def locator_status(
    province_id: int,
    locator_rows: dict[int, list[dict[str, str]]],
) -> tuple[str, str]:
    rows = locator_rows.get(province_id, [])
    if not rows:
        return "missing", ""
    statuses = sorted({row.get("status", "") for row in rows})
    evidence = " | ".join(
        f"{row.get('file')}:{row.get('line')}:{row.get('status')}"
        for row in rows
    )
    if "inside_exact" in statuses:
        return "inside_exact", evidence
    return "+".join(statuses), evidence


def resolve_expected_buildings(
    current_subregions: dict[str, Subregion],
    asil_subregions: dict[str, Subregion],
    asil_placements_by_province: dict[int, list[Placement]],
    asil_buildings: dict[str, BuildingDefinition],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for suffix in current_subregions:
        source_center = asil_subregions.get(suffix, current_subregions[suffix]).center_id
        candidates = [
            item.building_id
            for item in asil_placements_by_province.get(source_center, [])
            if item.building_id in asil_buildings
            and "silk_road_node" in asil_buildings[item.building_id].flags
        ]
        result[suffix] = sorted(set(candidates))
    return result


def build_market_audit(
    *,
    current_subregions: dict[str, Subregion],
    premerge_subregions: dict[str, Subregion],
    asil_subregions: dict[str, Subregion],
    decisions: dict[str, DecisionItem],
    current_buildings: dict[str, BuildingDefinition],
    all_current_buildings: dict[str, list[BuildingDefinition]],
    asil_buildings: dict[str, BuildingDefinition],
    current_placements: list[Placement],
    premerge_placements: list[Placement],
    asil_placements: list[Placement],
    localizations: dict[str, LocalizationValue],
    all_localizations: dict[str, list[LocalizationValue]],
    titles: dict[str, object],
    definition: dict[int, dict[str, object]],
    geometry: object,
    resolver: RegionResolver,
    relations: dict[int, ProvinceRelation],
    locator_rows: dict[int, list[dict[str, str]]],
    current_mod: Path,
    repo_root: Path,
    premerge_revision: str,
    asil_mod: Path,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, str]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    inventory: list[dict[str, object]] = []
    findings: list[dict[str, str]] = []
    localization_rows: list[dict[str, object]] = []
    runtime_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    current_by_building, current_by_province = index_placements(current_placements)
    current_claims_by_province: dict[int, list[Placement]] = defaultdict(list)
    for placement in current_placements:
        current_claims_by_province[placement.province_id].append(placement)
    premerge_by_building, _ = index_placements(premerge_placements)
    asil_by_building, asil_by_province = index_placements(asil_placements)
    expected = resolve_expected_buildings(
        current_subregions,
        asil_subregions,
        asil_by_province,
        asil_buildings,
    )
    (
        province_to_baronies,
        barony_to_county,
        county_capital,
        county_provinces,
    ) = build_title_indexes(titles)
    landed_ids = current_landed_province_ids(titles, set(definition))

    for suffix in SUFFIX_ORDER:
        subregion = current_subregions.get(suffix)
        exclusion = CURRENT_SCOPE_EXCLUSIONS.get(suffix)
        if exclusion:
            artifacts: list[str] = []
            if subregion:
                artifacts.append(subregion.key)
            if suffix in decisions:
                artifacts.append(f"decision_item:{suffix}")
            for building_id in exclusion["building_ids"]:
                if building_id in current_buildings:
                    artifacts.append(f"building_definition:{building_id}")
                if current_by_building.get(building_id):
                    artifacts.append(f"building_placement:{building_id}")
            if artifacts:
                findings.append(
                    make_finding(
                        "intentionally_excluded_subregion_artifact_present",
                        "blocker",
                        "high",
                        suffix,
                        SITUATION_RELATIVE.as_posix(),
                        subregion.line if subregion else 0,
                        ";".join(artifacts),
                        str(exclusion["reason"]),
                        "remove_the_excluded_subregion_and_all_market_consumers",
                    )
                )
            continue
        if not subregion:
            findings.append(
                make_finding(
                    "missing_silk_road_subregion", "blocker", "high", suffix,
                    SITUATION_RELATIVE.as_posix(), 0, suffix,
                    "The expected Silk Road subregion is not defined.",
                    "restore_or_explicitly_remove_the_subregion_and_all_consumers",
                )
            )
            continue
        item = decisions.get(suffix)
        decision_counties = item.county_titles if item else []
        decision_county = decision_counties[0] if len(decision_counties) == 1 else ""
        decision_provinces = county_provinces.get(decision_county, set())
        decision_capital = county_capital.get(decision_county, 0)
        source_center = asil_subregions.get(suffix, subregion).center_id
        relation = relations.get(source_center)
        expected_buildings = expected.get(suffix, [])
        expected_building = expected_buildings[0] if len(expected_buildings) == 1 else ""
        expected_definition = current_buildings.get(expected_building)
        expected_places = current_by_building.get(expected_building, [])
        expected_place_ids = sorted({place.province_id for place in expected_places})
        source_place_ids = sorted({place.province_id for place in asil_by_building.get(expected_building, [])})
        premerge_place_ids = sorted({place.province_id for place in premerge_by_building.get(expected_building, [])})
        center_market_buildings = sorted(
            {
                place.building_id
                for place in current_by_province.get(subregion.center_id, [])
                if place.building_id in current_buildings
                and "silk_road_node" in current_buildings[place.building_id].flags
            }
        )
        center_meta = definition.get(subregion.center_id, {})
        pixel_count = geometry.pixel_count[subregion.center_id] if subregion.center_id < len(geometry.pixel_count) else 0
        center_baronies = province_to_baronies.get(subregion.center_id, [])
        center_counties = sorted(
            {
                barony_to_county.get(barony, "")
                for barony in center_baronies
                if barony_to_county.get(barony, "")
            }
        )
        region_members: set[int] = set()
        for region_name in subregion.region_names:
            region_members.update(resolver.resolve(region_name))
        center_in_region = subregion.center_id in region_members
        relation_target = relation.target_id if relation else 0
        places_in_county = [province_id for province_id in expected_place_ids if province_id in decision_provinces]
        relation_target_claims = sorted({
            placement.building_id
            for placement in current_claims_by_province.get(relation_target, [])
            if placement.building_id != expected_building
        })
        candidate_alternatives: list[tuple[bool, float, int, str]] = []
        candidate_origin = relation_target or decision_capital
        if not expected_place_ids and decision_provinces:
            origin_center = (
                geometry.center(candidate_origin)
                if candidate_origin
                and candidate_origin < len(geometry.pixel_count)
                and geometry.pixel_count[candidate_origin]
                else None
            )
            for province_id in sorted(decision_provinces):
                claims = sorted({
                    placement.building_id
                    for placement in current_claims_by_province.get(province_id, [])
                    if placement.building_id != expected_building
                })
                locator_state, _ = locator_status(province_id, locator_rows)
                has_pixels = (
                    province_id < len(geometry.pixel_count)
                    and geometry.pixel_count[province_id] > 0
                )
                eligible = (
                    province_id in landed_ids
                    and province_id in region_members
                    and has_pixels
                    and not claims
                    and locator_state == "inside_exact"
                )
                distance = 0.0
                if origin_center and has_pixels:
                    candidate_point = geometry.center(province_id)
                    distance = (
                        (candidate_point[0] - origin_center[0]) ** 2
                        + (candidate_point[1] - origin_center[1]) ** 2
                    ) ** 0.5
                details = (
                    f"{province_id}:{'/'.join(province_to_baronies.get(province_id, [])) or '-'}:"
                    f"distance={distance:.2f}:locator={locator_state or 'missing'}:"
                    f"slots={','.join(claims) or 'none'}:eligible={'yes' if eligible else 'no'}"
                )
                candidate_alternatives.append((eligible, distance, province_id, details))
            candidate_alternatives.sort(
                key=lambda row: (not row[0], row[1], row[2])
            )
        candidate_center = 0
        candidate_reason = ""
        if len(places_in_county) == 1:
            candidate_center = places_in_county[0]
            candidate_reason = "existing_expected_market_placement_in_decision_county"
        elif len(expected_place_ids) == 1:
            candidate_center = expected_place_ids[0]
            candidate_reason = "existing_unique_expected_market_placement"
        elif (
            relation_target
            and relation_target in decision_provinces
            and not relation_target_claims
        ):
            candidate_center = relation_target
            candidate_reason = "asil_mod_center_relation_target_in_decision_county"
        elif candidate_alternatives and candidate_alternatives[0][0]:
            candidate_center = candidate_alternatives[0][2]
            candidate_reason = (
                "nearest_slot_free_barony_in_decision_county_to_relation_target"
            )
        elif decision_capital:
            candidate_center = decision_capital
            candidate_reason = "decision_county_capital_fallback"
        candidate_locator_status, candidate_locator_evidence = locator_status(candidate_center, locator_rows) if candidate_center else ("", "")
        center_locator_status, center_locator_evidence = locator_status(subregion.center_id, locator_rows)

        candidate_roles: dict[int, set[str]] = defaultdict(set)
        candidate_roles[subregion.center_id].add("current_center")
        if relation_target:
            candidate_roles[relation_target].add("relation_target")
        if decision_capital:
            candidate_roles[decision_capital].add("decision_county_capital")
        for province_id in expected_place_ids:
            candidate_roles[province_id].add("existing_expected_market_placement")
        for _, _, province_id, _ in candidate_alternatives:
            candidate_roles[province_id].add("slot_candidate")
        if candidate_center:
            candidate_roles[candidate_center].add("selected_candidate")

        origin_center = (
            geometry.center(candidate_origin)
            if candidate_origin
            and candidate_origin < len(geometry.pixel_count)
            and geometry.pixel_count[candidate_origin]
            else None
        )
        for province_id, roles in sorted(candidate_roles.items()):
            meta = definition.get(province_id, {})
            province_claims = sorted({
                placement.building_id
                for placement in current_claims_by_province.get(province_id, [])
                if placement.building_id != expected_building
            })
            province_market_buildings = sorted({
                placement.building_id
                for placement in current_by_province.get(province_id, [])
                if placement.building_id in current_buildings
                and "silk_road_node" in current_buildings[placement.building_id].flags
            })
            province_locator_status, province_locator_evidence = locator_status(
                province_id, locator_rows
            )
            province_has_pixels = (
                province_id < len(geometry.pixel_count)
                and geometry.pixel_count[province_id] > 0
            )
            distance = ""
            if origin_center and province_has_pixels:
                province_center = geometry.center(province_id)
                distance = f"{((province_center[0] - origin_center[0]) ** 2 + (province_center[1] - origin_center[1]) ** 2) ** 0.5:.2f}"
            eligible = (
                province_id in landed_ids
                and province_id in region_members
                and province_has_pixels
                and (not province_claims or province_id in expected_place_ids)
                and province_locator_status == "inside_exact"
            )
            rejection_reasons: list[str] = []
            if province_id not in landed_ids:
                rejection_reasons.append("not_landed")
            if province_id not in region_members:
                rejection_reasons.append("outside_subregion")
            if not province_has_pixels:
                rejection_reasons.append("missing_pixels")
            if province_claims and province_id not in expected_place_ids:
                rejection_reasons.append("other_special_building_slot_claim")
            if province_locator_status != "inside_exact":
                rejection_reasons.append("special_building_locator_not_inside_exact")
            candidate_rows.append({
                "subregion": suffix,
                "province_id": province_id,
                "definition_name": meta.get("name", ""),
                "baronies": " ".join(province_to_baronies.get(province_id, [])),
                "counties": " ".join(sorted({
                    barony_to_county.get(barony, "")
                    for barony in province_to_baronies.get(province_id, [])
                    if barony_to_county.get(barony, "")
                })),
                "roles": " ".join(sorted(roles)),
                "landed": "yes" if province_id in landed_ids else "no",
                "pixel_count": geometry.pixel_count[province_id]
                if province_id < len(geometry.pixel_count) else 0,
                "in_subregion": "yes" if province_id in region_members else "no",
                "expected_market_present": "yes" if province_id in expected_place_ids else "no",
                "silk_road_node_buildings": " ".join(province_market_buildings),
                "other_special_building_claims": " ".join(province_claims),
                "locator_status": province_locator_status,
                "locator_evidence": province_locator_evidence,
                "distance_to_relation_target": distance,
                "eligible_as_market_host": "yes" if eligible else "no",
                "rejection_reasons": " ".join(rejection_reasons),
                "selected": "yes" if province_id == candidate_center else "no",
                "selection_reason": candidate_reason if province_id == candidate_center else "",
                "candidate_confidence": (
                    "high" if province_id == candidate_center and province_id in expected_place_ids
                    else "medium" if province_id == candidate_center
                    else ""
                ),
                "auto_apply": "no",
            })
        building_loc_key = f"building_{expected_building}" if expected_building else ""
        building_desc_key = f"building_{expected_building}_desc" if expected_building else ""
        type_loc_key = f"building_type_{expected_building}" if expected_building else ""
        building_loc = localizations.get(building_loc_key)
        building_desc_loc = localizations.get(building_desc_key)
        type_loc = localizations.get(type_loc_key)
        decision_loc = localizations.get(item.localization_key) if item else None
        decision_loc_refs = BUILDING_LOC_REF_RE.findall(decision_loc.value) if decision_loc else []
        provenance = center_provenance(suffix, current_subregions, premerge_subregions, asil_subregions)
        start_finding_count = len(findings)
        root_binding = f"subregion_center_market_binding:{suffix}"

        if subregion.center_id not in definition or pixel_count == 0:
            findings.append(
                make_finding(
                    "center_missing_definition_or_pixels", "blocker", "high", suffix,
                    subregion.path, subregion.line, str(subregion.center_id),
                    "The situation center has no usable current map province.",
                    "choose_a_current_landed_market_province_after_semantic_review",
                    root_cause_key=root_binding,
                    current_value=str(subregion.center_id),
                    candidate_value=str(candidate_center), provenance=provenance,
                )
            )
        if subregion.center_id not in landed_ids:
            findings.append(
                make_finding(
                    "center_not_landed", "blocker", "high", suffix,
                    subregion.path, subregion.line, str(subregion.center_id),
                    "The situation center is not owned by any live landed barony.",
                    "remap_center_to_the_reviewed_current_market_province",
                    root_cause_key=root_binding,
                    current_value=str(subregion.center_id),
                    candidate_value=str(candidate_center), provenance=provenance,
                )
            )
        if not center_in_region:
            findings.append(
                make_finding(
                    "center_outside_own_subregion", "blocker", "high", suffix,
                    subregion.path, subregion.line, str(subregion.center_id),
                    "The center province is not resolved inside its declared geographical region.",
                    "align_the_center_and_region_membership_after_reviewing_the_market_location",
                    root_cause_key=root_binding,
                    current_value=str(subregion.center_id),
                    candidate_value=str(candidate_center), provenance=provenance,
                )
            )
        if not center_market_buildings:
            findings.append(
                make_finding(
                    "center_has_no_silk_road_node", "blocker", "high", suffix,
                    subregion.path, subregion.line, str(subregion.center_id),
                    "SituationSubRegion.GetBazaarBuilding cannot resolve a silk-road-node building at the center; this is the static cause of a building_ GUI label.",
                    "set_the_center_to_the_reviewed_market_placement_or_place_the_expected_market_at_the_center",
                    root_cause_key=root_binding,
                    current_value=str(subregion.center_id),
                    candidate_value=str(candidate_center), provenance=provenance,
                    evidence=placement_evidence(current_by_province.get(subregion.center_id, [])),
                )
            )
        if len(expected_buildings) != 1:
            findings.append(
                make_finding(
                    "ambiguous_or_missing_expected_market_source", "blocker", "high", suffix,
                    "history/provinces", 0, suffix,
                    f"The asil-mod source center resolves {len(expected_buildings)} silk-road-node buildings.",
                    "review_source_history_and_select_one_expected_market_building",
                    current_value=" ".join(expected_buildings), provenance="asil_mod_source",
                )
            )
        elif expected_definition is None:
            findings.append(
                make_finding(
                    "expected_market_building_undefined", "blocker", "high", suffix,
                    "common/buildings", 0, expected_building,
                    "The expected source market building has no effective current definition.",
                    "restore_or_semantically_replace_the_building_definition",
                    provenance="asil_mod_source",
                )
            )
        elif "silk_road_node" not in expected_definition.flags:
            findings.append(
                make_finding(
                    "expected_market_missing_silk_road_node_flag", "blocker", "high", suffix,
                    expected_definition.path, expected_definition.line, expected_building,
                    "The expected market definition lacks flag = silk_road_node.",
                    "review_and_restore_the_required_building_flag",
                    provenance=expected_definition.provenance,
                )
            )
        if expected_building and not expected_places:
            findings.append(
                make_finding(
                    "expected_market_not_placed", "blocker", "high", suffix,
                    "history/provinces", 0, expected_building,
                    "The expected market is defined but never placed by current province history.",
                    "place_the_market_at_the_reviewed_current_province_with_its_slot_and_DLC_guard",
                    root_cause_key=f"missing_market_history_placement:{suffix}",
                    candidate_value=str(candidate_center),
                    provenance="missing_after_asil_mod_source" if source_place_ids else "missing_in_all_sources",
                    evidence=placement_evidence(asil_by_building.get(expected_building, [])),
                )
            )
        if expected_places and not places_in_county:
            findings.append(
                make_finding(
                    "expected_market_outside_decision_county", "blocker", "high", suffix,
                    expected_places[0].path, expected_places[0].line, expected_building,
                    "The decision checks its county for a silk-road-node building, but the expected market is outside that county.",
                    "move_or_rebind_the_market_and_decision_as_one_reviewed_change",
                    current_value=ids(expected_place_ids), candidate_value=str(decision_capital),
                    evidence=f"decision_county={decision_county}; county_provinces={ids(decision_provinces)}",
                )
            )
        if relation and relation.target_id != subregion.center_id and not center_market_buildings:
            findings.append(
                make_finding(
                    "center_id_not_semantically_remapped", "blocker", "high", suffix,
                    subregion.path, subregion.line, str(subregion.center_id),
                    "The numeric asil-mod center ID was retained although its current province meaning changed.",
                    "review_the_existing_market_placement_and_relation_candidates_before_changing_the_center",
                    root_cause_key=root_binding,
                    current_value=str(subregion.center_id),
                    candidate_value=str(candidate_center or relation.target_id), provenance=provenance,
                    evidence=(
                        f"source={relation.source_id}:{relation.source_name}; relation_target="
                        f"{relation.target_id}:{relation.target_name}; classification="
                        f"{relation.classification}; confidence={relation.confidence}; top={relation.top_candidates}"
                    ),
                )
            )
        if not item or len(decision_counties) != 1 or decision_county not in titles:
            findings.append(
                make_finding(
                    "decision_market_county_missing_or_ambiguous", "blocker", "high", suffix,
                    DECISION_RELATIVE.as_posix(), item.line if item else 0, suffix,
                    "The market decision does not resolve exactly one live county title.",
                    "repair_the_decision_item_county_binding",
                    current_value=" ".join(decision_counties),
                )
            )
        if item and localization_status(decision_loc) != "present":
            findings.append(
                make_finding(
                    "decision_market_localization_missing_or_malformed", "blocker", "high", suffix,
                    decision_loc.path if decision_loc else DECISION_RELATIVE.as_posix(),
                    decision_loc.line if decision_loc else item.line,
                    item.localization_key,
                    "The decision market option localization is missing or malformed.",
                    "add_or_repair_the_English_localization_entry",
                    current_value=localization_status(decision_loc),
                )
            )
        expected_loc_ref = f"building_{expected_building}" if expected_building else ""
        if decision_loc and expected_loc_ref not in decision_loc_refs:
            findings.append(
                make_finding(
                    "decision_localization_references_wrong_market", "review", "high", suffix,
                    decision_loc.path, decision_loc.line,
                    item.localization_key if item else suffix,
                    "The decision option text references another market building name.",
                    "create_or_select_a_subregion_specific_decision_localization_key",
                    current_value=" ".join(decision_loc_refs), candidate_value=expected_loc_ref,
                    provenance=decision_loc.source_layer, evidence=decision_loc.value,
                )
            )
        for loc_key, loc_value, purpose in (
            (building_loc_key, building_loc, "name"),
            (building_desc_key, building_desc_loc, "description"),
            (type_loc_key, type_loc, "type_name"),
        ):
            if not loc_key:
                continue
            status = localization_status(loc_value)
            localization_rows.append(
                {
                    "subregion": suffix,
                    "purpose": purpose,
                    "key": loc_key,
                    "status": status,
                    "value": loc_value.value if loc_value else "",
                    "path": loc_value.path if loc_value else "",
                    "line": loc_value.line if loc_value else "",
                    "source_layer": loc_value.source_layer if loc_value else "",
                    "definition_count": len(all_localizations.get(loc_key, [])),
                }
            )
            if status != "present":
                findings.append(
                    make_finding(
                        "market_building_localization_missing_or_malformed",
                        "blocker", "high", suffix,
                        loc_value.path if loc_value else "localization",
                        loc_value.line if loc_value else 0, loc_key,
                        f"The expected market {purpose} localization is {status}.",
                        "add_or_repair_the_English_localization_entry",
                        current_value=status,
                        provenance=localization_entry_provenance(
                            loc_value,
                            current_mod=current_mod,
                            repo_root=repo_root,
                            premerge_revision=premerge_revision,
                            asil_mod=asil_mod,
                        ) if loc_value else "missing_everywhere",
                    )
                )
        for province_id in expected_place_ids:
            status, evidence = locator_status(province_id, locator_rows)
            if status == "missing":
                findings.append(
                    make_finding(
                        "market_special_building_locator_missing", "review", "high", suffix,
                        "gfx/map/map_object_data/special_building_locators.txt", 0,
                        str(province_id),
                        "The placed market has no special-building locator entry.",
                        "add_a_reviewed_locator_before_runtime_visual_signoff",
                        current_value=status,
                    )
                )
            elif status != "inside_exact":
                findings.append(
                    make_finding(
                        "market_special_building_locator_geometry_review", "review", "high", suffix,
                        "gfx/map/map_object_data/special_building_locators.txt", 0,
                        str(province_id),
                        "The market locator is not confirmed inside_exact.",
                        "review_locator_geometry_before_runtime_visual_signoff",
                        current_value=status, evidence=evidence,
                    )
                )
        if expected_place_ids and decision_capital and decision_capital not in expected_place_ids:
            findings.append(
                make_finding(
                    "decision_destination_differs_from_market_province", "review", "medium", suffix,
                    DECISION_RELATIVE.as_posix(), item.line if item else 0,
                    decision_county,
                    "The decision travels to the county title province while the market is in another barony province.",
                    "confirm_in_game_that_the_travel_destination_is_intentional",
                    current_value=str(decision_capital), candidate_value=ids(expected_place_ids),
                    provenance="current_design_requires_runtime_review",
                    evidence="This can be an intentional extra-barony design and is not auto-fixable.",
                )
            )

        suffix_findings = findings[start_finding_count:]
        severities = Counter(row["severity"] for row in suffix_findings)
        inventory.append(
            {
                "subregion": suffix,
                "subregion_key": subregion.key,
                "situation_path": subregion.path,
                "situation_line": subregion.line,
                "center_id": subregion.center_id,
                "center_definition_name": center_meta.get("name", ""),
                "center_pixel_count": pixel_count,
                "center_landed": "yes" if subregion.center_id in landed_ids else "no",
                "center_baronies": " ".join(center_baronies),
                "center_counties": " ".join(center_counties),
                "center_in_subregion": "yes" if center_in_region else "no",
                "center_market_buildings": " ".join(center_market_buildings),
                "center_locator_status": center_locator_status,
                "center_locator_evidence": center_locator_evidence,
                "center_provenance": provenance,
                "asil_mod_center_id": source_center,
                "relation_target_id": relation_target,
                "relation_target_existing_special_buildings": ids([]) if not relation_target_claims else " ".join(relation_target_claims),
                "relation_target_slot_conflict": "yes" if relation_target_claims else "no",
                "relation_classification": relation.classification if relation else "",
                "relation_confidence": relation.confidence if relation else "",
                "relation_top_candidates": relation.top_candidates if relation else "",
                "expected_building": expected_building,
                "expected_building_definition": "yes" if expected_definition else "no",
                "expected_building_provenance": expected_definition.provenance if expected_definition else "",
                "expected_current_placements": ids(expected_place_ids),
                "expected_premerge_placements": ids(premerge_place_ids),
                "expected_asil_mod_placements": ids(source_place_ids),
                "placements_in_decision_county": ids(places_in_county),
                "decision_county": decision_county,
                "decision_county_capital_id": decision_capital,
                "decision_localization_key": item.localization_key if item else "",
                "decision_localization_value": decision_loc.value if decision_loc else "",
                "decision_localization_market_refs": " ".join(decision_loc_refs),
                "building_name_status": localization_status(building_loc),
                "building_name_value": building_loc.value if building_loc else "",
                "building_description_status": localization_status(building_desc_loc),
                "candidate_center_id": candidate_center,
                "candidate_reason": candidate_reason,
                "candidate_alternatives": " | ".join(
                    row[3] for row in candidate_alternatives
                ),
                "candidate_locator_status": candidate_locator_status,
                "candidate_locator_evidence": candidate_locator_evidence,
                "blockers": severities.get("blocker", 0),
                "reviews": severities.get("review", 0),
                "overall_status": "blocker" if severities.get("blocker", 0) else ("review" if severities.get("review", 0) else "clean"),
            }
        )
        runtime_rows.append(
            {
                "bookmark_date": "1178.10.1",
                "subregion": suffix,
                "expected_building": expected_building,
                "expected_gui_name": building_loc.value if building_loc else "",
                "static_center_id": subregion.center_id,
                "reviewed_candidate_center_id": candidate_center,
                "check_gui_name_not_building_fallback": "pending_manual_runtime_test",
                "check_market_icon_at_expected_location": "pending_manual_runtime_test",
                "check_visit_decision_option_name": "pending_manual_runtime_test",
                "check_travel_destination": "pending_manual_runtime_test",
                "user_result": "",
                "user_comment": "",
            }
        )

    expected_by_building: dict[str, list[str]] = defaultdict(list)
    for suffix, values in expected.items():
        for building_id in values:
            expected_by_building[building_id].append(suffix)
    building_rows: list[dict[str, object]] = []
    for building_id, definition_item in sorted(current_buildings.items()):
        if "silk_road_node" not in definition_item.flags:
            continue
        placements = current_by_building.get(building_id, [])
        placement_ids = sorted({item.province_id for item in placements})
        name_key = f"building_{building_id}"
        desc_key = f"building_{building_id}_desc"
        name_loc = localizations.get(name_key)
        desc_loc = localizations.get(desc_key)
        expected_suffixes = expected_by_building.get(building_id, [])
        definition_count = len(all_current_buildings.get(building_id, []))
        signature_count = len({item.signature_sha256 for item in all_current_buildings.get(building_id, [])})
        status = "clean"
        if expected_suffixes and not placement_ids:
            status = "blocker_unplaced_expected"
        elif localization_status(name_loc) != "present":
            status = "blocker_name_localization"
        elif building_id.endswith("_01") and not placement_ids:
            status = "review_unplaced_initial_tier"
        elif definition_count > 1 and signature_count > 1:
            status = "review_conflicting_definitions"
        building_rows.append(
            {
                "building_id": building_id,
                "path": definition_item.path,
                "line": definition_item.line,
                "source_layer": definition_item.source_layer,
                "provenance": definition_item.provenance,
                "type": definition_item.building_type,
                "flags": " ".join(definition_item.flags),
                "next_building": definition_item.next_building,
                "definition_count": definition_count,
                "definition_signature_count": signature_count,
                "expected_by_subregions": " ".join(expected_suffixes),
                "placement_count": len(placement_ids),
                "placement_provinces": ids(placement_ids),
                "placement_evidence": placement_evidence(placements),
                "name_localization_status": localization_status(name_loc),
                "name_localization_value": name_loc.value if name_loc else "",
                "description_localization_status": localization_status(desc_loc),
                "status": status,
            }
        )
        if status == "review_unplaced_initial_tier":
            findings.append(
                make_finding(
                    "unplaced_silk_road_node_initial_tier", "review", "medium", "global",
                    definition_item.path, definition_item.line, building_id,
                    "An initial-tier silk-road-node building is defined but not placed by current province history.",
                    "confirm_that_the_building_is_constructible_or_intentionally_unused",
                    provenance=definition_item.provenance,
                )
            )
        if definition_count > 1 and signature_count > 1:
            findings.append(
                make_finding(
                    "conflicting_silk_road_node_building_definitions", "review", "high", "global",
                    definition_item.path, definition_item.line, building_id,
                    "Multiple effective-layer definitions of this silk-road-node building differ.",
                    "review_file_load_order_and_keep_or_document_one_effective_definition",
                    provenance=definition_item.provenance,
                    evidence=" | ".join(
                        f"{item.source_layer}:{item.path}:{item.line}:{item.signature_sha256[:12]}"
                        for item in all_current_buildings.get(building_id, [])
                    ),
                )
            )

    for placement in active_placements(current_placements):
        if placement.building_id in current_buildings:
            continue
        if not re.search(r"(?:market|bazaar|shuka)", placement.building_id):
            continue
        findings.append(
            make_finding(
                "market_history_references_undefined_building", "blocker", "high", "global",
                placement.path, placement.line, placement.building_id,
                "Province history places a market-like building with no effective definition.",
                "restore_or_replace_the_building_definition_after_source_review",
                current_value=str(placement.province_id), provenance=placement.source_layer,
            )
        )

    findings_by_id: dict[str, dict[str, str]] = {}
    for row in findings:
        findings_by_id.setdefault(row["finding_id"], row)
    ordered_findings = sorted(
        findings_by_id.values(),
        key=lambda row: (
            {"blocker": 0, "review": 1, "info": 2}.get(row["severity"], 9),
            row["classification"], row["subregion"], row["path"], int(row["line"] or 0),
        ),
    )
    return (
        inventory,
        ordered_findings,
        building_rows,
        localization_rows,
        runtime_rows,
        sorted(candidate_rows, key=lambda row: (str(row["subregion"]), int(row["province_id"]))),
    )


def merge_user_columns(
    path: Path,
    rows: list[dict[str, object]],
    key_field: str,
    user_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    previous: dict[str, dict[str, str]] = {}
    if path.exists():
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                key = row.get(key_field, "")
                if key:
                    previous[key] = row
    merged: list[dict[str, object]] = []
    for raw_row in rows:
        row = dict(raw_row)
        old = previous.get(str(row.get(key_field, "")), {})
        for field_name in user_fields:
            row[field_name] = old.get(field_name, str(row.get(field_name, "")))
        merged.append(row)
    return merged


def build_root_cause_rows(
    findings: list[dict[str, str]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in findings:
        grouped[row["root_cause_key"]].append(row)
    severity_order = {"blocker": 0, "review": 1, "info": 2}
    result: list[dict[str, object]] = []
    for root_key, rows in grouped.items():
        severity = min(
            (row["severity"] for row in rows),
            key=lambda value: severity_order.get(value, 9),
        )
        result.append(
            {
                "root_cause_key": root_key,
                "severity": severity,
                "confidence": min(
                    (row["confidence"] for row in rows),
                    key=lambda value: {"high": 0, "medium": 1, "low": 2}.get(value, 9),
                ),
                "subregions": " ".join(sorted({row["subregion"] for row in rows})),
                "classifications": " | ".join(sorted({row["classification"] for row in rows})),
                "raw_finding_count": len(rows),
                "objects": " | ".join(sorted({row["object"] for row in rows})),
                "current_values": " | ".join(sorted({row["current_value"] for row in rows if row["current_value"]})),
                "candidate_values": " | ".join(sorted({row["candidate_value"] for row in rows if row["candidate_value"]})),
                "provenance": " | ".join(sorted({row["provenance"] for row in rows if row["provenance"]})),
                "reasons": " | ".join(dict.fromkeys(row["reason"] for row in rows)),
                "recommendations": " | ".join(dict.fromkeys(row["recommendation"] for row in rows)),
                "finding_ids": " ".join(row["finding_id"] for row in rows),
                "auto_apply": "no",
            }
        )
    return sorted(
        result,
        key=lambda row: (
            severity_order.get(str(row["severity"]), 9),
            str(row["root_cause_key"]),
        ),
    )


def build_province_block_index(
    sources: Iterable[SourceText],
) -> dict[int, tuple[str, int]]:
    result: dict[int, tuple[str, int]] = {}
    for source in sources:
        entries, _ = parse_top_level(source.text)
        for entry in entries:
            if (
                entry.key
                and entry.key.isdigit()
                and isinstance(entry.value, Block)
            ):
                relative_path = source.relative_path.replace("\\", "/")
                if not relative_path.startswith("history/provinces/"):
                    relative_path = f"history/provinces/{relative_path}"
                result[int(entry.key)] = (relative_path, entry.line)
    return result


def build_fix_design_rows(
    *,
    inventory: list[dict[str, object]],
    root_rows: list[dict[str, object]],
    province_blocks: dict[int, tuple[str, int]],
    localizations: dict[str, LocalizationValue],
    current_mod: Path,
) -> list[dict[str, object]]:
    roots = {str(row["root_cause_key"]): row for row in root_rows}
    by_suffix = {str(row["subregion"]): row for row in inventory}
    rows: list[dict[str, object]] = []

    def add_action(
        *,
        action_id: str,
        apply_group: str,
        action_type: str,
        root_key: str,
        source_path: str,
        source_line: int | str,
        current_value: str,
        proposed_value: str,
        current_snippet: str,
        proposed_snippet: str,
        confidence: str,
        design_status: str,
        requires_user_decision: str,
        depends_on: str,
        reason: str,
        validation: str,
    ) -> None:
        root = roots.get(root_key)
        if not root:
            return
        rows.append({
            "action_id": action_id,
            "apply_group": apply_group,
            "action_type": action_type,
            "linked_root_cause_key": root_key,
            "root_classification": root_key.split(":", 1)[0],
            "root_object": str(root.get("objects", "")),
            "source_path": source_path,
            "source_line": source_line,
            "current_value": current_value,
            "proposed_value": proposed_value,
            "current_snippet": current_snippet,
            "proposed_snippet": proposed_snippet,
            "confidence": confidence,
            "design_status": design_status,
            "requires_user_decision": requires_user_decision,
            "depends_on_action_id": depends_on,
            "reason": reason,
            "validation_after_apply": validation,
            "source_provenance": str(root.get("provenance", "")),
            "apply_authorization_required": "yes",
            "auto_apply": "no",
        })

    china = by_suffix.get("china", {})
    china_candidate = int(china.get("candidate_center_id") or 0)
    if china_candidate:
        add_action(
            action_id="SRM001",
            apply_group="china_market_binding",
            action_type="replace_situation_center",
            root_key="subregion_center_market_binding:china",
            source_path=f"BookmarksGit/{china.get('situation_path', '')}",
            source_line=china.get("situation_line", ""),
            current_value=str(china.get("center_id", "")),
            proposed_value=str(china_candidate),
            current_snippet=f"capital_province = {china.get('center_id', '')}",
            proposed_snippet=(
                f"capital_province = {china_candidate} # Yusseter: "
                "Chang'an market center (Zhouzhi)"
            ),
            confidence="high",
            design_status="resolved_static",
            requires_user_decision="no",
            depends_on="",
            reason=(
                "the reviewed candidate already contains changan_market_01, belongs "
                "to c_jingzhao and the China Silk Road region, and has an "
                "inside_exact special-building locator; the relation target 10430 "
                "already uses giant_wild_goose_pagoda_01"
            ),
            validation=(
                "rerun market closure; China center must be landed, inside its "
                "subregion, resolve changan_market_01 and no longer produce building_"
            ),
        )

    sea = by_suffix.get("sea", {})
    sea_candidate = int(sea.get("candidate_center_id") or 0)
    sea_root = "missing_market_history_placement:sea"
    if sea_candidate and sea_root in roots:
        history_path, history_line = province_blocks.get(sea_candidate, ("", 0))
        add_action(
            action_id="SRM002",
            apply_group="sea_market_binding",
            action_type="insert_guarded_market_history",
            root_key=sea_root,
            source_path=f"BookmarksGit/{history_path}" if history_path else "",
            source_line=history_line,
            current_value="no angkor_market_01 placement",
            proposed_value=f"province:{sea_candidate}:angkor_market_01",
            current_snippet=f"{sea_candidate} province block has no Silk Road market",
            proposed_snippet=(
                "\teffect = { # Yusseter: Angkor Silk Road market\n"
                "\t\tif = {\n"
                "\t\t\tlimit = {\n"
                "\t\t\t\thas_tgp_dlc_trigger = yes\n"
                "\t\t\t}\n"
                "\t\t\tadd_special_building_slot = angkor_market_01\n"
                "\t\t\tadd_special_building = angkor_market_01\n"
                "\t\t}\n"
                "\t}"
            ),
            confidence="medium",
            design_status="manual_design_review_required",
            requires_user_decision="yes",
            depends_on="",
            reason=(
                "source center relation target 10816 already uses angkor_wat_01; "
                "10819 is the nearest slot-free same-county landed province, lies "
                "inside the SEA region and has an inside_exact locator"
            ),
            validation=(
                "rerun market closure and Tiger; province 10819 must contain exactly "
                "one guarded angkor_market_01 placement without replacing Angkor Wat"
            ),
        )
    if sea_candidate:
        add_action(
            action_id="SRM003",
            apply_group="sea_market_binding",
            action_type="replace_situation_center",
            root_key="subregion_center_market_binding:sea",
            source_path=f"BookmarksGit/{sea.get('situation_path', '')}",
            source_line=sea.get("situation_line", ""),
            current_value=str(sea.get("center_id", "")),
            proposed_value=str(sea_candidate),
            current_snippet=f"capital_province = {sea.get('center_id', '')}",
            proposed_snippet=(
                f"capital_province = {sea_candidate} # Yusseter: "
                "Angkor market center (Banteay Chhmar)"
            ),
            confidence="medium",
            design_status="manual_design_review_required",
            requires_user_decision="yes",
            depends_on="SRM002",
            reason=(
                "11451 is current b_pak_beng and outside the SEA Silk Road region; "
                "the center must move together with the reviewed Angkor market host"
            ),
            validation=(
                "rerun market closure; SEA center must be landed, inside its region, "
                "resolve angkor_market_01 and no longer produce building_"
            ),
        )

    localization_key = "building_constantinople_market_01_desc"
    localization_root = (
        "market_building_localization_missing_or_malformed:occident:"
        f"{localization_key}"
    )
    localization = localizations.get(localization_key)
    if localization and localization_root in roots:
        source_file = current_mod / localization.path
        source_lines = read_text(source_file).splitlines() if source_file.is_file() else []
        current_line = (
            source_lines[localization.line - 1]
            if 0 < localization.line <= len(source_lines)
            else ""
        )
        proposed_line = current_line + '"' if current_line and not current_line.rstrip().endswith('"') else current_line
        add_action(
            action_id="SRM004",
            apply_group="occident_market_localization",
            action_type="repair_localization_end_quote",
            root_key=localization_root,
            source_path=f"BookmarksGit/{localization.path}",
            source_line=localization.line,
            current_value="malformed_missing_end_quote",
            proposed_value="present",
            current_snippet=current_line,
            proposed_snippet=proposed_line,
            confidence="high",
            design_status="resolved_static",
            requires_user_decision="no",
            depends_on="",
            reason=(
                "the localization value has an opening quote but no closing quote; "
                "the same malformed line is shared by premerge Yusseter and asıl mod"
            ),
            validation=(
                "rerun market closure and Tiger; the key must parse as present and "
                "the localization diagnostic must disappear"
            ),
        )
    return rows


def _brace_delta(line: str) -> int:
    quoted = False
    escaped = False
    delta = 0
    for char in line:
        if char == "\\" and quoted:
            escaped = not escaped
            continue
        if char == '"' and not escaped:
            quoted = not quoted
        escaped = False
        if char == "#" and not quoted:
            break
        if not quoted:
            delta += (char == "{") - (char == "}")
    return delta


def _province_block_end(lines: list[str], start_line: int) -> int:
    depth = 0
    for index in range(start_line - 1, len(lines)):
        depth += _brace_delta(lines[index])
        if depth == 0 and index >= start_line - 1:
            return index
    raise ValueError(f"province block at line {start_line} is not closed")


def write_fix_preview(
    path: Path,
    *,
    current_mod: Path,
    design_rows: list[dict[str, object]],
) -> None:
    by_path: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in design_rows:
        source_path = str(row.get("source_path", ""))
        if source_path:
            by_path[source_path].append(row)
    diff_sections: list[bytes] = []
    for source_path, actions in sorted(by_path.items()):
        relative = source_path.removeprefix("BookmarksGit/")
        file_path = current_mod / relative
        source_bytes = file_path.read_bytes()
        output_newline = b"\r\n" if b"\r\n" in source_bytes else b"\n"
        original = read_text(file_path).splitlines()
        modified = list(original)
        replacement_actions = [
            row for row in actions
            if str(row.get("action_type", ""))
            in {"replace_situation_center", "repair_localization_end_quote"}
        ]
        for row in sorted(
            replacement_actions,
            key=lambda item: int(item.get("source_line") or 0),
            reverse=True,
        ):
            line_number = int(row.get("source_line") or 0)
            if not 0 < line_number <= len(modified):
                raise ValueError(f"invalid preview line {source_path}:{line_number}")
            proposed = str(row.get("proposed_snippet", ""))
            indent = modified[line_number - 1][
                : len(modified[line_number - 1]) - len(modified[line_number - 1].lstrip())
            ]
            modified[line_number - 1] = indent + proposed.lstrip()
        insert_actions = [
            row for row in actions
            if row.get("action_type") == "insert_guarded_market_history"
        ]
        for row in sorted(
            insert_actions,
            key=lambda item: int(item.get("source_line") or 0),
            reverse=True,
        ):
            line_number = int(row.get("source_line") or 0)
            end_index = _province_block_end(modified, line_number)
            snippet = str(row.get("proposed_snippet", "")).splitlines()
            modified[end_index:end_index] = [""] + snippet
        file_diff = list(difflib.unified_diff(
            original,
            modified,
            fromfile=f"a/{source_path}",
            tofile=f"b/{source_path}",
            lineterm="",
        ))
        if file_diff:
            section_lines = [f"diff --git a/{source_path} b/{source_path}", *file_diff]
            diff_sections.append(
                output_newline.join(line.encode("utf-8") for line in section_lines)
                + output_newline
            )
    path.write_bytes(b"".join(diff_sections))


def render_market_control_png(
    *,
    image_path: Path,
    by_rgb: dict[tuple[int, int, int], list[int]],
    landed: set[int],
    subregions: dict[str, Subregion],
    resolver: RegionResolver,
    inventory: list[dict[str, object]],
    geometry: object,
    output_path: Path,
) -> None:
    province_colors: dict[int, tuple[int, int, int, int]] = {}
    legend: list[tuple[tuple[int, int, int, int], str]] = []
    for suffix, color in zip(SUFFIX_ORDER, SILK_COLORS):
        subregion = subregions.get(suffix)
        if not subregion:
            continue
        members: set[int] = set()
        for region_name in subregion.region_names:
            members.update(resolver.resolve(region_name))
        for province_id in members & landed:
            province_colors[province_id] = color
        legend.append((color, suffix))
    render_province_overlay(
        image_path,
        by_rgb,
        landed,
        province_colors,
        output_path,
        "Silk Road market closure: centers, market placements, and candidates",
        legend
        + [
            ((255, 45, 45, 255), "X = current situation center"),
            ((45, 235, 105, 255), "circle = current expected market placement"),
            ((45, 205, 255, 255), "square = reviewed candidate center"),
        ],
    )
    image = Image.open(output_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    scale_x = image.width / geometry.width
    scale_y = image.height / geometry.height

    def point(province_id: int) -> tuple[int, int] | None:
        if province_id <= 0 or province_id >= len(geometry.pixel_count):
            return None
        if not geometry.pixel_count[province_id]:
            return None
        x, y = geometry.center(province_id)
        return round(x * scale_x), round(y * scale_y)

    for row in inventory:
        suffix = str(row["subregion"])
        center_id = int(row["center_id"] or 0)
        candidate_id = int(row["candidate_center_id"] or 0)
        placement_ids = [
            int(value)
            for value in str(row["expected_current_placements"]).split()
            if value.isdigit()
        ]
        center = point(center_id)
        placements = [value for value in (point(item) for item in placement_ids) if value]
        candidate = point(candidate_id)
        if center:
            for placement in placements:
                draw.line((center, placement), fill=(255, 190, 45), width=3)
            if not placements and candidate:
                draw.line((center, candidate), fill=(45, 205, 255), width=3)
            x, y = center
            radius = 8
            draw.line((x - radius, y - radius, x + radius, y + radius), fill=(255, 45, 45), width=4)
            draw.line((x - radius, y + radius, x + radius, y - radius), fill=(255, 45, 45), width=4)
            label = f"{suffix} center={center_id}"
            draw.rectangle((x + 10, y - 10, x + 12 + len(label) * 6, y + 5), fill=(16, 18, 22))
            draw.text((x + 12, y - 9), label, fill=(255, 255, 255), font=font)
        for placement in placements:
            x, y = placement
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), outline=(45, 235, 105), width=4)
        if candidate and candidate_id != center_id:
            x, y = candidate
            draw.rectangle((x - 7, y - 7, x + 7, y + 7), outline=(45, 205, 255), width=4)
    image.save(output_path, optimize=True)


def directory_digest(path: Path, patterns: tuple[str, ...]) -> tuple[str, int]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(path.rglob(pattern) if path.exists() else [])
    unique = sorted(set(file for file in files if file.is_file()))
    digest = hashlib.sha256()
    for file in unique:
        digest.update(file.relative_to(path).as_posix().encode("utf-8"))
        digest.update(file_sha256(file).encode("ascii"))
    return digest.hexdigest(), len(unique)


def build_manifest(
    repo_root: Path,
    current_mod: Path,
    asil_mod: Path,
    vanilla_root: Path,
    premerge_revision: str,
    relation_csv: Path,
    locator_csv: Path,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {"input": "current_revision", "path": str(repo_root), "sha256_or_revision": git_revision(repo_root), "file_count": ""},
        {"input": "premerge_revision", "path": str(repo_root), "sha256_or_revision": git_revision(repo_root, premerge_revision), "file_count": ""},
        {"input": "asil_mod_revision", "path": str(asil_mod.parent), "sha256_or_revision": git_revision(asil_mod.parent), "file_count": ""},
    ]
    trees = (
        ("current_buildings", current_mod / "common/buildings", ("*.txt",)),
        ("current_province_history", current_mod / "history/provinces", ("*.txt",)),
        ("current_localization", current_mod / "localization", ("*.yml",)),
        ("current_regions", current_mod / "map_data/geographical_regions", ("*.txt",)),
        ("current_landed_titles", current_mod / "common/landed_titles", ("*.txt",)),
        ("asil_mod_buildings", asil_mod / "common/buildings", ("*.txt",)),
        ("asil_mod_province_history", asil_mod / "history/provinces", ("*.txt",)),
        ("vanilla_buildings", vanilla_root / "common/buildings", ("*.txt",)),
        ("vanilla_localization", vanilla_root / "localization", ("*.yml",)),
    )
    for label, path, patterns in trees:
        digest, count = directory_digest(path, patterns)
        rows.append({"input": label, "path": str(path), "sha256_or_revision": digest, "file_count": count})
    for label, path in (
        ("situation", current_mod / SITUATION_RELATIVE),
        ("decision", current_mod / DECISION_RELATIVE),
        ("definition", current_mod / "map_data/definition.csv"),
        ("provinces", current_mod / "map_data/provinces.png"),
        ("special_building_locators", current_mod / "gfx/map/map_object_data/special_building_locators.txt"),
        ("relation_csv", relation_csv),
        ("locator_audit_csv", locator_csv),
    ):
        rows.append(
            {
                "input": label,
                "path": str(path),
                "sha256_or_revision": file_sha256(path) if path.exists() else "missing",
                "file_count": 1 if path.exists() else 0,
            }
        )
    return rows


def build_coverage(
    *,
    inventory: list[dict[str, object]],
    parser_diagnostics: int,
    gui_binding_ok: bool,
    locator_csv: Path,
    locator_inputs: list[Path],
) -> list[dict[str, object]]:
    locator_exists = locator_csv.exists()
    newest_input = max(
        (path.stat().st_mtime_ns for path in locator_inputs if path.exists()),
        default=0,
    )
    locator_fresh = locator_exists and locator_csv.stat().st_mtime_ns >= newest_input
    expected_source_complete = (
        len(inventory) == len(ACTIVE_SUFFIX_ORDER)
        and all(str(row.get("expected_building", "")) for row in inventory)
    )
    return [
        {
            "system": "silk_road_subregion_center_inventory",
            "coverage": "full" if len(inventory) == len(ACTIVE_SUFFIX_ORDER) else "partial",
            "evidence": (
                f"{len(inventory)}/{len(ACTIVE_SUFFIX_ORDER)} active expected subregions; "
                f"intentional exclusions={','.join(CURRENT_SCOPE_EXCLUSIONS)}"
            ),
            "remaining_manual": "none for static inventory",
        },
        {
            "system": "asil_mod_market_source_resolution",
            "coverage": "full" if expected_source_complete else "partial",
            "evidence": "source center history plus effective silk-road-node definitions",
            "remaining_manual": "ambiguous source rows require review" if not expected_source_complete else "none",
        },
        {
            "system": "current_market_history_placement",
            "coverage": "full",
            "evidence": "all effective current province-history text files parsed recursively",
            "remaining_manual": "none for static presence; fixes are not applied",
        },
        {
            "system": "silk_road_node_building_definitions",
            "coverage": "full",
            "evidence": "effective current, premerge, asil_mod, and vanilla building layers",
            "remaining_manual": "conflicting or unplaced definitions remain review items",
        },
        {
            "system": "market_decision_binding",
            "coverage": "full",
            "evidence": "all visit_silk_road_market_decision item blocks",
            "remaining_manual": "travel-destination intent requires runtime confirmation",
        },
        {
            "system": "English_market_localization",
            "coverage": "full",
            "evidence": "vanilla, current localization, and current replace layers with quote validation",
            "remaining_manual": "non-English languages are outside this pass",
        },
        {
            "system": "static_GUI_market_name_chain",
            "coverage": "full" if gui_binding_ok else "partial",
            "evidence": "SituationSubRegion.GetBazaarBuilding -> Building.GetName",
            "remaining_manual": "repair or locate changed GUI binding" if not gui_binding_ok else "none",
        },
        {
            "system": "special_building_locator_geometry",
            "coverage": "full" if locator_fresh else "partial",
            "evidence": str(locator_csv),
            "remaining_manual": "regenerate locator audit" if not locator_fresh else "none",
        },
        {
            "system": "relevant_input_format_validation",
            "coverage": "full",
            "evidence": f"diagnostics={parser_diagnostics}",
            "remaining_manual": "resolve findings in diagnostics.csv" if parser_diagnostics else "none",
        },
        {
            "system": "1178.10.1_runtime_GUI_and_travel",
            "coverage": "partial",
            "evidence": "runtime_smoke_test_checklist.csv",
            "remaining_manual": "launch bookmark and record GUI name, icon, decision label, and destination",
        },
    ]


def write_summary(
    path: Path,
    *,
    repo_root: Path,
    current_revision: str,
    asil_revision: str,
    premerge_revision: str,
    inventory: list[dict[str, object]],
    findings: list[dict[str, str]],
    root_rows: list[dict[str, object]],
    fix_design_rows: list[dict[str, object]],
    building_rows: list[dict[str, object]],
    coverage: list[dict[str, object]],
    diagnostics_count: int,
) -> None:
    severity = Counter(row["severity"] for row in findings)
    root_severity = Counter(str(row["severity"]) for row in root_rows)
    classifications = Counter(row["classification"] for row in findings)
    exclusion_summary = ", ".join(
        f"{suffix} ({details['reason']})"
        for suffix, details in CURRENT_SCOPE_EXCLUSIONS.items()
    )
    lines = [
        "# Silk Road Market / Building / GUI Closure Audit",
        "",
        "This is a read-only detection and classification pass. It does not edit live CK3 content.",
        "",
        "## Scope",
        "",
        f"- Current revision: `{current_revision}`",
        f"- Premerge revision: `{premerge_revision}`",
        f"- Asil-mod revision: `{asil_revision}`",
        f"- Active subregions audited: {len(inventory)}/{len(ACTIVE_SUFFIX_ORDER)}",
        f"- Intentional current-scope exclusions: {exclusion_summary}",
        f"- Effective silk-road-node building definitions: {len(building_rows)}",
        f"- Raw findings: {len(findings)} (blocker={severity['blocker']}, review={severity['review']}, info={severity['info']})",
        f"- Independent root causes: {len(root_rows)} (blocker={root_severity['blocker']}, review={root_severity['review']}, info={root_severity['info']})",
        f"- Dry-run fix-design actions: {len(fix_design_rows)} (auto-apply=0)",
        f"- Parser diagnostics: {diagnostics_count}",
        "",
        "## Subregion Status",
        "",
        "| Subregion | Center | Expected market | Current placement | Candidate | Status |",
        "|---|---:|---|---|---:|---|",
    ]
    for row in inventory:
        lines.append(
            "| {subregion} | {center_id} ({center_definition_name}) | {expected_building} | "
            "{expected_current_placements} | {candidate_center_id} | {overall_status} |".format(**row)
        )
    lines.extend(["", "## Finding Classes", ""])
    for classification, count in sorted(classifications.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{classification}`: {count}")
    lines.extend(
        [
            "",
            "## Coverage",
            "",
            "| System | Coverage | Evidence | Remaining manual work |",
            "|---|---|---|---|",
        ]
    )
    for row in coverage:
        lines.append(
            f"| {row['system']} | {row['coverage']} | {row['evidence']} | {row['remaining_manual']} |"
        )
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `silk_road_market_inventory.csv`: one complete chain per subregion.",
            "- `silk_road_market_findings.csv`: static blockers and review findings.",
            "- `silk_road_market_root_causes.csv`: independent remediation roots without raw-row double counting.",
            "- `silk_road_market_root_review.csv`: persistent root-level user decisions; auto-apply is disabled.",
            "- `silk_road_market_manual_review.csv`: persistent user decisions; auto-apply is disabled.",
            "- `silk_road_market_candidate_provinces.csv`: evidence for every reviewed center/market-host candidate.",
            "- `silk_road_market_fix_design.csv`: linked source-edit design; every action remains auto_apply=no.",
            "- `silk_road_market_fix_preview.patch`: unapplied unified-diff preview for the four blocker roots.",
            "- `silk_road_node_building_inventory.csv`: all effective silk-road-node definitions and placements.",
            "- `silk_road_market_localization_audit.csv`: expected market localization keys.",
            "- `silk_road_market_control.png`: region, center, placement, and candidate map.",
            "- `runtime_smoke_test_checklist.csv`: reusable 1178.10.1 in-game signoff sheet.",
            "- `coverage.csv`, `input_manifest.csv`, `diagnostics.csv`: reproducibility evidence.",
            "",
            f"Project root: `{repo_root}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    current_mod = bookmarks_root(repo_root)
    asil_mod = bookmarks_root(args.asil_mod_root.resolve())
    vanilla_root = args.vanilla_root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else repo_root
        / ".codex/works/analysis/generated/repo_integration_closure"
        / "silk_road_market_closure"
    )
    relation_csv = (
        args.relation_csv.resolve()
        if args.relation_csv is not None
        else repo_root
        / ".codex/works/analysis/generated/province_relation_mapping"
        / "current_state_refresh/province_relation_master.csv"
    )
    locator_csv = (
        args.locator_audit_csv.resolve()
        if args.locator_audit_csv is not None
        else repo_root
        / ".codex/works/analysis/generated/map_object_locator_audit"
        / "locator_position_audit.csv"
    )
    required = [
        current_mod / SITUATION_RELATIVE,
        current_mod / DECISION_RELATIVE,
        current_mod / "map_data/definition.csv",
        current_mod / "map_data/provinces.png",
        current_mod / "map_data/geographical_regions",
        current_mod / "common/landed_titles",
        asil_mod / SITUATION_RELATIVE,
        vanilla_root / "common/buildings",
        relation_csv,
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        for path in missing:
            print(f"missing required input: {path}", file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)

    current_subregions, current_situation_diagnostics = parse_situation_text(
        read_text(current_mod / SITUATION_RELATIVE),
        SITUATION_RELATIVE.as_posix(),
    )
    premerge_subregions, premerge_situation_diagnostics = parse_situation_text(
        git_text(repo_root, args.premerge_revision, Path("BookmarksGit") / SITUATION_RELATIVE),
        f"{args.premerge_revision}:{SITUATION_RELATIVE.as_posix()}",
    )
    asil_subregions, asil_situation_diagnostics = parse_situation_text(
        read_text(asil_mod / SITUATION_RELATIVE),
        SITUATION_RELATIVE.as_posix(),
    )
    decisions, decision_diagnostics = parse_decision_text(
        read_text(current_mod / DECISION_RELATIVE)
    )

    current_building_sources = collect_effective_sources(
        current_mod / "common/buildings",
        vanilla_root / "common/buildings",
    )
    premerge_building_sources, premerge_building_git_diagnostics = collect_git_sources(
        repo_root,
        args.premerge_revision,
        "BookmarksGit/common/buildings",
    )
    asil_building_sources = collect_effective_sources(
        asil_mod / "common/buildings",
        vanilla_root / "common/buildings",
    )
    vanilla_building_sources = collect_plain_sources(
        vanilla_root / "common/buildings", "vanilla"
    )
    current_buildings, all_current_buildings, current_building_diagnostics = parse_building_sources(current_building_sources)
    premerge_buildings, _, premerge_building_diagnostics = parse_building_sources(premerge_building_sources)
    asil_buildings, _, asil_building_diagnostics = parse_building_sources(asil_building_sources)
    vanilla_buildings, _, vanilla_building_diagnostics = parse_building_sources(vanilla_building_sources)
    apply_building_provenance(
        current_buildings,
        premerge_buildings,
        asil_buildings,
        vanilla_buildings,
    )

    current_history_sources = collect_effective_sources(
        current_mod / "history/provinces",
        vanilla_root / "history/provinces",
    )
    premerge_history_sources, premerge_history_git_diagnostics = collect_git_sources(
        repo_root,
        args.premerge_revision,
        "BookmarksGit/history/provinces",
    )
    asil_history_sources = collect_effective_sources(
        asil_mod / "history/provinces",
        vanilla_root / "history/provinces",
    )
    current_placements, current_history_diagnostics = parse_history_placements(current_history_sources)
    premerge_placements, premerge_history_diagnostics = parse_history_placements(premerge_history_sources)
    asil_placements, asil_history_diagnostics = parse_history_placements(asil_history_sources)

    localization_files = localization_file_order(current_mod, vanilla_root)
    localizations, all_localizations, localization_diagnostics = parse_localization(localization_files)
    titles = load_effective_titles(
        current_mod / "common/landed_titles",
        vanilla_root / "common/landed_titles",
    )
    definition, by_rgb = parse_definition(current_mod / "map_data/definition.csv")
    geometry, _ = scan_map_geometry(
        current_mod / "map_data/provinces.png",
        definition,
        by_rgb,
    )
    current_region_sources = collect_effective_sources(
        current_mod / "map_data/geographical_regions",
        vanilla_root / "map_data/geographical_regions",
    )
    current_regions, _, region_diagnostics = parse_region_source_set(current_region_sources)
    resolver = RegionResolver(current_regions, titles, set(definition))
    relations = load_relations(relation_csv)
    locator_rows = load_locator_rows(locator_csv)

    (
        inventory,
        findings,
        building_rows,
        localization_rows,
        runtime_rows,
        candidate_rows,
    ) = build_market_audit(
        current_subregions=current_subregions,
        premerge_subregions=premerge_subregions,
        asil_subregions=asil_subregions,
        decisions=decisions,
        current_buildings=current_buildings,
        all_current_buildings=all_current_buildings,
        asil_buildings=asil_buildings,
        current_placements=current_placements,
        premerge_placements=premerge_placements,
        asil_placements=asil_placements,
        localizations=localizations,
        all_localizations=all_localizations,
        titles=titles,
        definition=definition,
        geometry=geometry,
        resolver=resolver,
        relations=relations,
        locator_rows=locator_rows,
        current_mod=current_mod,
        repo_root=repo_root,
        premerge_revision=args.premerge_revision,
        asil_mod=asil_mod,
    )

    gui_files: list[Path] = []
    for relative in GUI_RELATIVES:
        current_path = current_mod / relative
        gui_files.append(current_path if current_path.exists() else vanilla_root / relative)
    gui_texts = [read_text(path) if path.exists() else "" for path in gui_files]
    gui_binding_ok = (
        "SituationSubRegion.GetBazaarBuilding" in gui_texts[0]
        and "Building.GetName" in gui_texts[1]
    )
    if not gui_binding_ok:
        findings.append(
            make_finding(
                "silk_road_GUI_market_binding_missing", "blocker", "high", "global",
                "gui/window_silk_road.gui", 0, "GetBazaarBuilding_to_Building.GetName",
                "The expected static GUI market-name chain could not be verified.",
                "review_effective_GUI_overrides_before_interpreting_building_labels",
                evidence=" | ".join(str(path) for path in gui_files),
            )
        )
    findings_by_id = {row["finding_id"]: row for row in findings}
    findings = sorted(
        findings_by_id.values(),
        key=lambda row: (
            {"blocker": 0, "review": 1, "info": 2}.get(row["severity"], 9),
            row["classification"], row["subregion"], row["path"], int(row["line"] or 0),
        ),
    )

    root_rows = build_root_cause_rows(findings)
    province_blocks = build_province_block_index(current_history_sources)
    fix_design_rows = build_fix_design_rows(
        inventory=inventory,
        root_rows=root_rows,
        province_blocks=province_blocks,
        localizations=localizations,
        current_mod=current_mod,
    )
    relevant_localization_keys = {
        str(row["key"])
        for row in localization_rows
        if row.get("key")
    }
    relevant_localization_keys.update(
        item.localization_key
        for item in decisions.values()
        if item.localization_key
    )
    for row in building_rows:
        building_id = str(row["building_id"])
        relevant_localization_keys.update(
            {
                f"building_{building_id}",
                f"building_{building_id}_desc",
                f"building_type_{building_id}",
                f"building_type_{building_id}_desc",
            }
        )
    localization_diagnostics = [
        row
        for row in localization_diagnostics
        if str(row.get("diagnostic", "")).split(":", 1)[-1]
        in relevant_localization_keys
    ]

    diagnostic_rows: list[dict[str, object]] = list(localization_diagnostics)
    diagnostic_groups = (
        ("current_situation", current_situation_diagnostics),
        ("premerge_situation", premerge_situation_diagnostics),
        ("asil_situation", asil_situation_diagnostics),
        ("decision", decision_diagnostics),
        ("current_buildings", current_building_diagnostics),
        ("premerge_buildings_git", premerge_building_git_diagnostics),
        ("premerge_buildings", premerge_building_diagnostics),
        ("asil_buildings", asil_building_diagnostics),
        ("vanilla_buildings", vanilla_building_diagnostics),
        ("current_history", current_history_diagnostics),
        ("premerge_history_git", premerge_history_git_diagnostics),
        ("premerge_history", premerge_history_diagnostics),
        ("asil_history", asil_history_diagnostics),
        ("regions", region_diagnostics),
    )
    for source, values in diagnostic_groups:
        diagnostic_rows.extend(
            {"source": source, "path": "", "line": "", "diagnostic": value}
            for value in values
        )

    locator_inputs = [
        current_mod / "gfx/map/map_object_data/special_building_locators.txt",
        current_mod / "map_data/definition.csv",
        current_mod / "map_data/provinces.png",
    ]
    coverage = build_coverage(
        inventory=inventory,
        parser_diagnostics=len(diagnostic_rows),
        gui_binding_ok=gui_binding_ok,
        locator_csv=locator_csv,
        locator_inputs=locator_inputs,
    )
    manifest = build_manifest(
        repo_root,
        current_mod,
        asil_mod,
        vanilla_root,
        args.premerge_revision,
        relation_csv,
        locator_csv,
    )

    finding_rows = [dict(row, auto_apply="no") for row in findings]
    write_csv(output_dir / "silk_road_market_inventory.csv", inventory)
    write_csv(output_dir / "silk_road_market_findings.csv", finding_rows)
    write_csv(output_dir / "silk_road_market_root_causes.csv", root_rows)
    write_csv(output_dir / "silk_road_market_candidate_provinces.csv", candidate_rows)
    write_csv(output_dir / "silk_road_node_building_inventory.csv", building_rows)
    write_csv(output_dir / "silk_road_market_localization_audit.csv", localization_rows)
    write_csv(output_dir / "coverage.csv", coverage)
    write_csv(output_dir / "input_manifest.csv", manifest)
    write_csv(output_dir / "diagnostics.csv", diagnostic_rows)

    fix_design_path = output_dir / "silk_road_market_fix_design.csv"
    fix_design_rows = merge_user_columns(
        fix_design_path,
        fix_design_rows,
        "action_id",
        ("user_decision", "user_comment"),
    )
    write_csv(fix_design_path, fix_design_rows)
    write_fix_preview(
        output_dir / "silk_road_market_fix_preview.patch",
        current_mod=current_mod,
        design_rows=fix_design_rows,
    )

    manual_path = output_dir / "silk_road_market_manual_review.csv"
    manual_rows = merge_user_columns(
        manual_path,
        finding_rows,
        "finding_id",
        ("user_decision", "user_comment"),
    )
    write_csv(manual_path, manual_rows)
    root_review_path = output_dir / "silk_road_market_root_review.csv"
    root_review_rows = merge_user_columns(
        root_review_path,
        root_rows,
        "root_cause_key",
        ("user_decision", "user_comment"),
    )
    write_csv(root_review_path, root_review_rows)
    runtime_path = output_dir / "runtime_smoke_test_checklist.csv"
    runtime_rows = merge_user_columns(
        runtime_path,
        runtime_rows,
        "subregion",
        ("user_result", "user_comment"),
    )
    write_csv(runtime_path, runtime_rows)

    if not args.skip_control_png:
        render_market_control_png(
            image_path=current_mod / "map_data/provinces.png",
            by_rgb=by_rgb,
            landed=current_landed_province_ids(titles, set(definition)),
            subregions=current_subregions,
            resolver=resolver,
            inventory=inventory,
            geometry=geometry,
            output_path=output_dir / "silk_road_market_control.png",
        )

    asil_repo = asil_mod.parent if asil_mod.name == "BookmarksGit" else args.asil_mod_root.resolve()
    write_summary(
        output_dir / "silk_road_market_closure_summary.md",
        repo_root=repo_root,
        current_revision=git_revision(repo_root),
        asil_revision=git_revision(asil_repo),
        premerge_revision=git_revision(repo_root, args.premerge_revision),
        inventory=inventory,
        findings=findings,
        root_rows=root_rows,
        fix_design_rows=fix_design_rows,
        building_rows=building_rows,
        coverage=coverage,
        diagnostics_count=len(diagnostic_rows),
    )
    severity = Counter(row["severity"] for row in findings)
    print(f"subregions: {len(inventory)}")
    print(f"silk-road-node buildings: {len(building_rows)}")
    print(f"findings: {len(findings)}")
    print(f"independent roots: {len(root_rows)}")
    print(f"blockers: {severity['blocker']}")
    print(f"reviews: {severity['review']}")
    print(f"diagnostics: {len(diagnostic_rows)}")
    print(f"output: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
