from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import audit_repo_semantic_compatibility as semantic
import audit_upstream_merge_state as merge_state


DEFAULT_ASIL_MOD_REPO = (
    Path(__file__).resolve().parents[3].parent / "Leviathonlx MoreBookmarks-Plus"
)
DEFAULT_VANILLA_GAME_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
)
OUTPUT_PATH = ".codex/works/analysis/generated/repo_integration_closure"
SEMANTIC_PATH = ".codex/works/analysis/generated/repo_semantic_compatibility"
DEFERRED_BLOCKER_PROVENANCES = {"shared_asil_mod_baseline"}
DEFERRED_SOURCE_ORIGINS = {"asil_mod_source_native_broken_holder_chain"}
RUNTIME_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "bookmark_runtime_static"
)
TITLE_HOLDER_PROVENANCE_REPORT = (
    f"{RUNTIME_PATH}/title_holder_reference_provenance.csv"
)
PROVINCE_SEMANTICS_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "province_history_bookmark_semantics"
)
TIGER_CLASSIFICATION_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "tiger_current_only_classification"
)
TIGER_CURRENT_PRIORITY_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "ck3_tiger_current_only_priority.csv"
)
TIGER_P0_TRIAGE_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "tiger_p0_root_triage"
)
TITLE_RELATION_PATH = (
    ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv"
)
TIGER_P0_HIGHER_NO_CANDIDATE_STATUSES = {
    "source_title_not_defined_in_current_asil_mod",
    "source_title_has_no_descendant_province_footprint",
    "source_footprint_absent_from_relation_refresh",
    "resolved_targets_have_no_same_tier_landed_candidate",
}
REVIEW_SURFACE_TRIAGE_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "review_surface_triage"
)
P1_STRUCTURAL_LOCALIZATION_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "p1_structural_localization_roots"
)
DYNAMIC_TITLE_REFERENCE_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "dynamic_title_references"
)
LOCALIZATION_VISIBILITY_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "localization_visibility"
)
UPSTREAM_CHARACTER_ROOT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "upstream_integration_character_roots"
)
LOCAL_MIXED_CHARACTER_ROOT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "local_mixed_character_roots"
)
SHARED_ASIL_CHARACTER_ROOT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "shared_asil_mod_character_roots"
)
NON_CHARACTER_ROOT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "non_character_blocker_roots"
)
GEOGRAPHICAL_REGION_CLOSURE_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "geographical_region_closure"
)
SILK_ROAD_MARKET_CLOSURE_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "silk_road_market_closure"
)
LANDED_PATH = "BookmarksGit/common/landed_titles/00_landed_titles.txt"
DEFINITION_PATH = "BookmarksGit/map_data/definition.csv"

TITLE_RE = re.compile(r"\b([hekdcb]_[A-Za-z0-9_'\-]+)\b")
CN_RE = re.compile(r"\b(cn_[A-Za-z0-9_'\-]+)\b")
NUMERIC_HEADER_RE = re.compile(r"^\s*(\d+)\s*=\s*\{")
TITLE_HEADER_RE = re.compile(r"^\s*([hekdcb]_[A-Za-z0-9_'\-]+)\s*=\s*\{")
HOLDER_RE = re.compile(r"^\s*holder\s*=\s*([A-Za-z0-9_.\-]+)\b")
LOCATOR_ID_RE = re.compile(r"^\s*id\s*=\s*(\d+)\b")
NUMERIC_ASSIGNMENT_RE = re.compile(r"^\s*(\d+)\s*=")
LOC_KEY_RE = re.compile(r"^\s*([^\s:#][^:]*?):(?:\d+)?\s+(.+?)\s*$")
FILE_REF_RE = re.compile(r'^\s*([A-Za-z0-9_]+)\s*=\s*"([^"]+)"')
PROVINCE_SET_RE = re.compile(
    r"^\s*([A-Za-z0-9_]+)\s*=\s*(LIST|RANGE)\s*\{([^}]*)\}"
)


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a coverage-aware CK3 repo integration closure audit"
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument("--asil-mod-repo", type=Path, default=DEFAULT_ASIL_MOD_REPO)
    parser.add_argument(
        "--vanilla-game-root", type=Path, default=DEFAULT_VANILLA_GAME_ROOT
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--skip-semantic-refresh", action="store_true")
    return parser.parse_args()


def strip_comment(line: str) -> str:
    quoted = False
    escaped = False
    result: list[str] = []
    for char in line:
        if char == "\\" and quoted:
            escaped = not escaped
            result.append(char)
            continue
        if char == '"' and not escaped:
            quoted = not quoted
        escaped = False
        if char == "#" and not quoted:
            break
        result.append(char)
    return "".join(result)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        payload = b""
        if not path.exists() or path.read_bytes() != payload:
            path.write_bytes(payload)
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")
    if not path.exists() or path.read_bytes() != payload:
        path.write_bytes(payload)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finding(
    domain: str,
    subdomain: str,
    classification: str,
    severity: str,
    confidence: str,
    path: str,
    line: int | str,
    obj: str,
    reason: str,
    recommendation: str,
    current_value: str = "",
    candidate_value: str = "",
    source_report: str = "current_state",
    provenance: str = "current_state_unclassified",
) -> dict[str, str]:
    return {
        "domain": domain,
        "subdomain": subdomain,
        "classification": classification,
        "severity": severity,
        "confidence": confidence,
        "path": path,
        "line": str(line),
        "object": obj,
        "current_value": current_value,
        "candidate_value": candidate_value,
        "reason": reason,
        "recommendation": recommendation,
        "source_report": source_report,
        "provenance": provenance,
    }


def parse_definition_file(
    path: Path, label: str, findings: list[dict[str, str]] | None = None
) -> tuple[dict[int, dict[str, object]], dict[tuple[int, int, int], list[int]]]:
    by_id: dict[int, dict[str, object]] = {}
    by_rgb: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    seen_ids: dict[int, int] = {}
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for line_number, row in enumerate(csv.reader(handle, delimiter=";"), start=1):
            if not row or not row[0].strip().isdigit():
                continue
            try:
                province_id = int(row[0].strip())
                rgb = tuple(int(value.strip()) for value in row[1:4])
            except (ValueError, IndexError):
                if findings is not None:
                    findings.append(finding(
                        "map_identity", "definition", "invalid_definition_row",
                        "blocker", "high", label, line_number,
                        row[0].strip() if row else "", "definition row cannot be parsed",
                        "repair_definition_row",
                    ))
                continue
            if len(rgb) != 3:
                continue
            name = row[4].strip() if len(row) > 4 else ""
            if province_id in seen_ids and findings is not None:
                findings.append(finding(
                    "map_identity", "definition", "duplicate_province_id",
                    "blocker", "high", label, line_number, str(province_id),
                    f"province ID already defined at line {seen_ids[province_id]}",
                    "keep_one_definition_per_id",
                ))
            seen_ids[province_id] = line_number
            by_id[province_id] = {
                "id": province_id,
                "rgb": rgb,
                "name": name,
                "line": line_number,
            }
            by_rgb[rgb].append(province_id)
    if findings is not None:
        for rgb, ids in sorted(by_rgb.items()):
            unique_ids = sorted(set(ids))
            if len(unique_ids) > 1:
                findings.append(finding(
                    "map_identity", "definition", "duplicate_rgb",
                    "blocker", "high", label, by_id[unique_ids[-1]]["line"],
                    ",".join(map(str, rgb)),
                    f"RGB is assigned to province IDs {' | '.join(map(str, unique_ids))}",
                    "assign_unique_rgb_per_province",
                ))
    return by_id, dict(by_rgb)


def audit_default_map(
    repo_root: Path,
    vanilla_root: Path,
    definition: dict[int, dict[str, object]],
) -> list[dict[str, str]]:
    path = repo_root / "BookmarksGit/map_data/default.map"
    relative = "BookmarksGit/map_data/default.map"
    rows: list[dict[str, str]] = []
    vanilla_default = vanilla_root / "map_data/default.map"
    vanilla_references = set()
    if vanilla_default.exists():
        for raw in read_text(vanilla_default).splitlines():
            match = FILE_REF_RE.match(strip_comment(raw))
            if match:
                vanilla_references.add(match.groups())
    for line_number, raw in enumerate(read_text(path).splitlines(), start=1):
        clean = strip_comment(raw)
        file_match = FILE_REF_RE.match(clean)
        if file_match:
            key, value = file_match.groups()
            mod_path = repo_root / "BookmarksGit/map_data" / value
            vanilla_path = vanilla_root / "map_data" / value
            if not mod_path.exists() and not vanilla_path.exists():
                is_vanilla_baseline = (key, value) in vanilla_references
                rows.append(finding(
                    "map_identity", "default_map",
                    "vanilla_baseline_missing_reference" if is_vanilla_baseline
                    else "missing_referenced_file",
                    "info" if is_vanilla_baseline else "blocker",
                    "high", relative, line_number, key,
                    f"{value} exists in neither mod nor vanilla map_data",
                    "no_yusseter_action" if is_vanilla_baseline
                    else "restore_or_correct_default_map_reference",
                    current_value=value,
                ))
        set_match = PROVINCE_SET_RE.match(clean)
        if not set_match:
            continue
        key, mode, body = set_match.groups()
        numbers = [int(value) for value in re.findall(r"\d+", body)]
        if mode == "RANGE" and len(numbers) == 2:
            numbers = list(range(numbers[0], numbers[1] + 1))
        for province_id in numbers:
            if province_id not in definition:
                rows.append(finding(
                    "map_identity", "default_map", "undefined_province_reference",
                    "blocker", "high", relative, line_number,
                    f"{key}:{province_id}", "province ID is absent from definition.csv",
                    "remove_or_remap_default_map_province",
                    current_value=str(province_id),
                ))
    return rows


def audit_adjacencies(
    repo_root: Path, definition: dict[int, dict[str, object]]
) -> list[dict[str, str]]:
    path = repo_root / "BookmarksGit/map_data/adjacencies.csv"
    relative = "BookmarksGit/map_data/adjacencies.csv"
    rows: list[dict[str, str]] = []
    active_lines = [
        line for line in read_text(path).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    seen: dict[tuple[str, str, str, str], int] = {}
    for row_number, row in enumerate(csv.DictReader(active_lines, delimiter=";"), start=2):
        values = {str(key).strip(): (value or "").strip() for key, value in row.items()}
        signature = (
            values.get("From", ""), values.get("To", ""),
            values.get("Type", ""), values.get("Through", ""),
        )
        if signature in seen:
            rows.append(finding(
                "map_identity", "adjacencies", "duplicate_adjacency",
                "review", "high", relative, row_number,
                "->".join(signature[:2]),
                f"same adjacency first appears at active row {seen[signature]}",
                "verify_duplicate_then_remove_if_redundant",
            ))
        else:
            seen[signature] = row_number
        for field in ("From", "To", "Through"):
            raw = values.get(field, "")
            if raw in {"", "-1"}:
                continue
            if not raw.isdigit() or int(raw) not in definition:
                rows.append(finding(
                    "map_identity", "adjacencies", "undefined_province_reference",
                    "blocker", "high", relative, row_number,
                    f"{field}:{raw}", "adjacency endpoint is absent from definition.csv",
                    "remove_or_remap_adjacency_province",
                    current_value=raw,
                ))
    return rows


def audit_numeric_assignment_files(
    repo_root: Path,
    relative_dir: str,
    definition: dict[int, dict[str, object]],
    domain: str,
    subdomain: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    directory = repo_root / relative_dir
    for path in sorted(directory.rglob("*.txt")):
        relative = path.relative_to(repo_root).as_posix()
        seen: dict[int, int] = {}
        for line_number, raw in enumerate(read_text(path).splitlines(), start=1):
            match = NUMERIC_ASSIGNMENT_RE.match(strip_comment(raw))
            if not match:
                continue
            province_id = int(match.group(1))
            if province_id not in definition:
                rows.append(finding(
                    domain, subdomain, "undefined_province_reference",
                    "blocker", "high", relative, line_number, str(province_id),
                    "numeric province key is absent from definition.csv",
                    "remove_or_remap_province_key",
                ))
            if province_id in seen:
                rows.append(finding(
                    domain, subdomain, "duplicate_province_assignment",
                    "review", "high", relative, line_number, str(province_id),
                    f"same province first assigned at line {seen[province_id]}",
                    "verify_duplicate_assignment_semantics",
                ))
            else:
                seen[province_id] = line_number
    return rows


def audit_locator_ids(
    repo_root: Path, definition: dict[int, dict[str, object]]
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    directory = repo_root / "BookmarksGit/gfx/map/map_object_data"
    for path in sorted(directory.glob("*.txt")):
        if path.name == "game_object_layers.txt":
            continue
        relative = path.relative_to(repo_root).as_posix()
        seen: dict[int, int] = {}
        for line_number, raw in enumerate(read_text(path).splitlines(), start=1):
            match = LOCATOR_ID_RE.match(strip_comment(raw))
            if not match:
                continue
            province_id = int(match.group(1))
            if province_id not in definition:
                rows.append(finding(
                    "map_objects", "locator_identity", "undefined_province_reference",
                    "blocker", "high", relative, line_number, str(province_id),
                    "locator ID is absent from definition.csv",
                    "remove_or_remap_locator_id",
                ))
            if province_id in seen:
                rows.append(finding(
                    "map_objects", "locator_identity", "duplicate_locator_id",
                    "review", "high", relative, line_number, str(province_id),
                    f"same file first defines this ID at line {seen[province_id]}",
                    "verify_duplicate_locator",
                ))
            else:
                seen[province_id] = line_number
    return rows


def parse_top_level_headers(
    paths: list[Path], root: Path, pattern: re.Pattern[str]
) -> tuple[dict[str, list[tuple[str, int]]], list[dict[str, str]]]:
    found: dict[str, list[tuple[str, int]]] = defaultdict(list)
    brace_rows: list[dict[str, str]] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        depth = 0
        for line_number, raw in enumerate(read_text(path).splitlines(), start=1):
            clean = strip_comment(raw)
            if depth == 0:
                match = pattern.match(clean)
                if match:
                    found[match.group(1)].append((relative, line_number))
            depth += clean.count("{") - clean.count("}")
            if depth < 0:
                brace_rows.append(finding(
                    "structure", "history", "negative_brace_depth",
                    "blocker", "high", relative, line_number, "}",
                    "closing brace appears before a matching opening brace",
                    "repair_brace_structure",
                ))
                depth = 0
        if depth != 0:
            brace_rows.append(finding(
                "structure", "history", "brace_mismatch",
                "blocker", "high", relative, "", str(depth),
                "file ends with a non-zero brace depth",
                "repair_brace_structure",
            ))
    return dict(found), brace_rows


def audit_landed_titles(
    repo_root: Path,
    vanilla_root: Path,
    definition: dict[int, dict[str, object]],
) -> tuple[
    set[str], dict[int, list[str]], set[int], set[str], set[str],
    list[dict[str, str]]
]:
    directory = repo_root / "BookmarksGit/common/landed_titles"
    title_ids: set[str] = set()
    title_locations: dict[str, list[tuple[str, int]]] = defaultdict(list)
    province_baronies: dict[int, list[str]] = defaultdict(list)
    barony_provinces: dict[str, int] = {}
    county_capital_baronies: set[str] = set()
    cultural_names: set[str] = set()
    noble_family_titles: set[str] = set()
    pending_capitals: list[tuple[str, int, str, str]] = []
    rows: list[dict[str, str]] = []

    for path in sorted(directory.glob("*.txt")):
        relative = path.relative_to(repo_root).as_posix()
        snapshot = merge_state.build_snapshot(relative, read_text(path))
        for title_id, block in snapshot.titles.items():
            title_ids.add(title_id)
            title_locations[title_id].append((relative, block.start_line))
            properties = snapshot.properties.get(title_id, {})
            for prop in properties.get("province", []):
                match = re.search(r"\bprovince\s*=\s*(\d+)\b", prop.raw)
                if not match:
                    continue
                province_id = int(match.group(1))
                if title_id.startswith("b_"):
                    province_baronies[province_id].append(title_id)
                    barony_provinces[title_id] = province_id
                if province_id not in definition:
                    rows.append(finding(
                        "landed_titles", "province_reference",
                        "undefined_province_reference", "blocker", "high",
                        relative, prop.start_line, title_id,
                        "landed title province is absent from definition.csv",
                        "remap_or_restore_province_definition",
                        current_value=str(province_id),
                    ))
            for prop in properties.get("capital", []):
                match = TITLE_RE.search(strip_comment(prop.raw))
                if match:
                    pending_capitals.append(
                        (relative, prop.start_line, title_id, match.group(1))
                    )
            for prop in properties.get("cultural_names", []):
                cultural_names.update(CN_RE.findall(prop.raw))
            if any(
                re.search(r"\bnoble_family\s*=\s*yes\b", strip_comment(prop.raw))
                for prop in properties.get("noble_family", [])
            ):
                noble_family_titles.add(title_id)
        for title_id, context in snapshot.contexts.items():
            if not title_id.startswith("c_"):
                continue
            explicit = ""
            for prop in snapshot.properties.get(title_id, {}).get("capital", []):
                match = TITLE_RE.search(strip_comment(prop.raw))
                if match and match.group(1).startswith("b_"):
                    explicit = match.group(1)
                    break
            if explicit:
                county_capital_baronies.add(explicit)
                continue
            first_barony = next(
                (child for child in context.child_ids if child.startswith("b_")),
                "",
            )
            if first_barony:
                county_capital_baronies.add(first_barony)

    mod_relatives = {
        path.relative_to(directory).as_posix().lower()
        for path in directory.rglob("*.txt")
    }
    vanilla_directory = vanilla_root / "common/landed_titles"
    if vanilla_directory.is_dir():
        for path in sorted(vanilla_directory.rglob("*.txt")):
            relative = path.relative_to(vanilla_directory).as_posix().lower()
            if relative in mod_relatives:
                continue
            snapshot = merge_state.build_snapshot(
                f"vanilla/{relative}", read_text(path)
            )
            title_ids.update(snapshot.titles)
            for title_id in snapshot.titles:
                properties = snapshot.properties.get(title_id, {})
                if any(
                    re.search(
                        r"\bnoble_family\s*=\s*yes\b",
                        strip_comment(prop.raw),
                    )
                    for prop in properties.get("noble_family", [])
                ):
                    noble_family_titles.add(title_id)

    for title_id, locations in sorted(title_locations.items()):
        if len(locations) > 1:
            rows.append(finding(
                "landed_titles", "identity", "duplicate_title_definition",
                "review", "high", locations[-1][0], locations[-1][1], title_id,
                "title is defined more than once in mod landed-title files",
                "verify_override_or_keep_single_definition",
                current_value=" | ".join(f"{path}:{line}" for path, line in locations),
            ))
    for relative, line_number, owner, capital in pending_capitals:
        if capital not in title_ids:
            rows.append(finding(
                "landed_titles", "capital_reference", "undefined_title_reference",
                "blocker", "high", relative, line_number, owner,
                "capital title is absent from current landed titles",
                "remap_or_restore_capital_title",
                current_value=capital,
            ))
    for province_id, baronies in sorted(province_baronies.items()):
        if len(baronies) > 1:
            rows.append(finding(
                "landed_titles", "province_reference",
                "duplicate_barony_province", "blocker", "high",
                LANDED_PATH, "", str(province_id),
                "multiple baronies directly use the same province ID",
                "assign_one_active_barony_per_province",
                current_value=" | ".join(sorted(baronies)),
            ))
    capital_provinces = {
        barony_provinces[barony]
        for barony in county_capital_baronies
        if barony in barony_provinces
    }
    return (
        title_ids, dict(province_baronies), capital_provinces,
        cultural_names, noble_family_titles, rows,
    )


def collect_effective_title_ids(project_root: Path, vanilla_root: Path) -> set[str]:
    mod_directory = project_root / "BookmarksGit/common/landed_titles"
    mod_paths = sorted(mod_directory.rglob("*.txt"))
    mod_relatives = {
        path.relative_to(mod_directory).as_posix().lower() for path in mod_paths
    }
    result: set[str] = set()
    for path in mod_paths:
        result.update(merge_state.build_snapshot("mod", read_text(path)).titles)
    vanilla_directory = vanilla_root / "common/landed_titles"
    for path in sorted(vanilla_directory.rglob("*.txt")):
        relative = path.relative_to(vanilla_directory).as_posix().lower()
        if relative in mod_relatives:
            continue
        result.update(merge_state.build_snapshot("vanilla", read_text(path)).titles)
    return result


def collect_effective_province_history_ids(
    project_root: Path, vanilla_root: Path
) -> set[int]:
    mod_directory = project_root / "BookmarksGit/history/provinces"
    mod_paths = sorted(mod_directory.rglob("*.txt"))
    mod_relatives = {
        path.relative_to(mod_directory).as_posix().lower() for path in mod_paths
    }
    vanilla_directory = vanilla_root / "history/provinces"
    vanilla_paths = [
        path for path in sorted(vanilla_directory.rglob("*.txt"))
        if path.relative_to(vanilla_directory).as_posix().lower()
        not in mod_relatives
    ]
    mod_headers, _ = parse_top_level_headers(
        mod_paths, project_root, NUMERIC_HEADER_RE
    )
    vanilla_headers, _ = parse_top_level_headers(
        vanilla_paths, vanilla_root, NUMERIC_HEADER_RE
    )
    return {int(value) for value in set(mod_headers) | set(vanilla_headers)}


def collect_effective_province_mapping_ids(
    project_root: Path, vanilla_root: Path
) -> set[int]:
    mod_directory = project_root / "BookmarksGit/history/province_mapping"
    vanilla_directory = vanilla_root / "history/province_mapping"
    mod_paths = sorted(mod_directory.rglob("*.txt")) if mod_directory.is_dir() else []
    mod_relatives = {
        path.relative_to(mod_directory).as_posix().lower() for path in mod_paths
    }
    vanilla_paths = [
        path for path in sorted(vanilla_directory.rglob("*.txt"))
        if path.relative_to(vanilla_directory).as_posix().lower()
        not in mod_relatives
    ] if vanilla_directory.is_dir() else []
    targets: set[int] = set()
    for path in mod_paths + vanilla_paths:
        for raw in read_text(path).splitlines():
            match = re.fullmatch(r"\s*(\d+)\s*=\s*(\d+)\s*", strip_comment(raw))
            if match:
                targets.add(int(match.group(1)))
    return targets


def classify_source_provenance(
    findings: list[dict[str, str]],
    repo_root: Path,
    asil_mod_repo: Path,
    vanilla_root: Path,
    current_definition: dict[int, dict[str, object]],
) -> None:
    source_definition, _ = parse_definition_file(
        asil_mod_repo / DEFINITION_PATH,
        "asil_mod/BookmarksGit/map_data/definition.csv",
    )
    source_titles = collect_effective_title_ids(asil_mod_repo, vanilla_root)
    source_history_ids = collect_effective_province_history_ids(
        asil_mod_repo, vanilla_root
    )
    source_cultural_names: set[str] = set()
    source_landed_directory = asil_mod_repo / "BookmarksGit/common/landed_titles"
    for path in source_landed_directory.rglob("*.txt"):
        source_cultural_names.update(CN_RE.findall(read_text(path)))

    for row in findings:
        if row["provenance"] != "current_state_unclassified":
            continue
        if row["domain"] == "province_history" and row["subdomain"] == "landed_coverage":
            if not row["object"].isdigit():
                continue
            province_id = int(row["object"])
            current_meta = current_definition.get(province_id)
            source_meta = source_definition.get(province_id)
            same_semantics = bool(
                current_meta and source_meta
                and current_meta["rgb"] == source_meta["rgb"]
                and current_meta["name"] == source_meta["name"]
            )
            row["provenance"] = (
                "shared_asil_mod_baseline"
                if same_semantics and province_id not in source_history_ids
                else "yusseter_current_only"
            )
        elif row["domain"] == "localization" and row["classification"] == "missing_everywhere":
            if row["subdomain"] in {"title_base", "title_adj"}:
                title_id = (
                    row["object"][:-4]
                    if row["subdomain"] == "title_adj"
                    else row["object"]
                )
                row["provenance"] = (
                    "shared_asil_mod_baseline"
                    if title_id in source_titles
                    else "yusseter_current_only"
                )
            elif row["subdomain"] == "cultural_name":
                row["provenance"] = (
                    "shared_asil_mod_baseline"
                    if row["object"] in source_cultural_names
                    else "yusseter_current_only"
                )


def apply_tiger_overlap_provenance(
    findings: list[dict[str, str]], overlaps: list[dict[str, str]]
) -> None:
    evidence: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for row in overlaps:
        evidence[(
            normalize_tiger_path(row["path"]).lower(),
            row["line"],
            row["static_classification"],
            row["static_object"],
        )].add(row["tiger_provenance"])
    for row in findings:
        if row["provenance"] != "current_state_unclassified":
            continue
        provenances = evidence.get((
            normalize_tiger_path(row["path"]).lower(),
            row["line"], row["classification"], row["object"],
        ), set())
        if provenances == {"shared_asil_mod_baseline"}:
            row["provenance"] = "shared_asil_mod_baseline"
        elif "yusseter_current_only" in provenances:
            row["provenance"] = "yusseter_current_only"


def audit_province_history(
    repo_root: Path,
    vanilla_root: Path,
    definition: dict[int, dict[str, object]],
    vanilla_definition: dict[int, dict[str, object]],
    province_baronies: dict[int, list[str]],
    capital_provinces: set[int],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    mod_paths = sorted((repo_root / "BookmarksGit/history/provinces").rglob("*.txt"))
    mod_directory = repo_root / "BookmarksGit/history/provinces"
    vanilla_directory = vanilla_root / "history/provinces"
    mod_relatives = {
        path.relative_to(mod_directory).as_posix().lower() for path in mod_paths
    }
    vanilla_paths = [
        path for path in sorted(vanilla_directory.rglob("*.txt"))
        if path.relative_to(vanilla_directory).as_posix().lower()
        not in mod_relatives
    ]
    mod_headers, brace_rows = parse_top_level_headers(
        mod_paths, repo_root, NUMERIC_HEADER_RE
    )
    vanilla_headers, _ = parse_top_level_headers(
        vanilla_paths, vanilla_root, NUMERIC_HEADER_RE
    )
    rows.extend(brace_rows)

    for raw_id, locations in sorted(mod_headers.items(), key=lambda item: int(item[0])):
        province_id = int(raw_id)
        if province_id not in definition:
            for relative, line_number in locations:
                rows.append(finding(
                    "province_history", "identity", "undefined_province_block",
                    "blocker", "high", relative, line_number, raw_id,
                    "province-history block is absent from definition.csv",
                    "remove_or_remap_province_history_block",
                ))
        if len(locations) > 1:
            rows.append(finding(
                "province_history", "identity", "duplicate_province_block",
                "review", "high", locations[-1][0], locations[-1][1], raw_id,
                "province has multiple mod history blocks and effective load order matters",
                "compare_blocks_and_keep_intentional_override_only",
                current_value=" | ".join(f"{path}:{line}" for path, line in locations),
            ))

    mod_ids = {int(value) for value in mod_headers}
    vanilla_ids = {int(value) for value in vanilla_headers}
    mapping_ids = collect_effective_province_mapping_ids(repo_root, vanilla_root)
    for province_id, baronies in sorted(province_baronies.items()):
        if province_id in mod_ids or province_id in mapping_ids:
            continue
        current_meta = definition.get(province_id)
        vanilla_meta = vanilla_definition.get(province_id)
        if province_id not in vanilla_ids:
            is_capital = province_id in capital_provinces
            rows.append(finding(
                "province_history", "landed_coverage",
                "missing_effective_history_capital" if is_capital
                else "missing_explicit_history_noncapital",
                "blocker" if is_capital else "review",
                "high" if is_capital else "medium",
                LANDED_PATH, "", str(province_id),
                "landed province has no mod or vanilla province-history block",
                "add_province_history_block",
                current_value=" | ".join(sorted(baronies)),
            ))
            continue
        same_semantics = bool(
            current_meta and vanilla_meta
            and current_meta["rgb"] == vanilla_meta["rgb"]
            and current_meta["name"] == vanilla_meta["name"]
        )
        if not same_semantics:
            is_capital = province_id in capital_provinces
            rows.append(finding(
                "province_history", "landed_coverage",
                "repurposed_capital_inherits_vanilla_history" if is_capital
                else "repurposed_noncapital_inherits_vanilla_history",
                "blocker" if is_capital else "review",
                "high" if is_capital else "medium",
                LANDED_PATH, "", str(province_id),
                "landed province semantics differ from vanilla but no mod history override exists",
                "add_current_semantics_province_history",
                current_value=str(current_meta["name"] if current_meta else ""),
                candidate_value=str(vanilla_meta["name"] if vanilla_meta else ""),
            ))
    return rows


def audit_title_history(
    repo_root: Path,
    vanilla_root: Path,
    title_ids: set[str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    paths = sorted((repo_root / "BookmarksGit/history/titles").rglob("*.txt"))
    headers, brace_rows = parse_top_level_headers(paths, repo_root, TITLE_HEADER_RE)
    rows.extend(brace_rows)
    character_ids = semantic.collect_current_character_ids(repo_root, vanilla_root)

    for title_id, locations in sorted(headers.items()):
        if title_id not in title_ids:
            for relative, line_number in locations:
                rows.append(finding(
                    "title_history", "identity", "undefined_title_block",
                    "blocker", "high", relative, line_number, title_id,
                    "title-history block is absent from current landed titles",
                    "remove_or_remap_title_history_block",
                ))
        by_layer: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for location in locations:
            layer = (
                "development"
                if location[0].endswith("z00_ADEVELOPMENT.txt")
                else "regional"
            )
            by_layer[layer].append(location)
        for layer, layer_locations in by_layer.items():
            if len(layer_locations) > 1:
                rows.append(finding(
                    "title_history", "identity", "duplicate_title_block_same_layer",
                    "review", "medium", layer_locations[-1][0],
                    layer_locations[-1][1], title_id,
                    f"title has multiple {layer} history blocks",
                    "verify_same_layer_override_or_keep_one_block",
                    current_value=" | ".join(
                        f"{path}:{line}" for path, line in layer_locations
                    ),
                ))

    for path in paths:
        relative = path.relative_to(repo_root).as_posix()
        for line_number, raw in enumerate(read_text(path).splitlines(), start=1):
            match = HOLDER_RE.match(strip_comment(raw))
            if not match:
                continue
            holder = match.group(1)
            if holder not in character_ids:
                rows.append(finding(
                    "title_history", "holder_reference", "undefined_holder",
                    "blocker", "high", relative, line_number, holder,
                    "holder is absent from vanilla plus current mod character history",
                    "restore_character_or_replace_holder",
                    current_value=holder,
                ))
    return rows


def apply_title_holder_reference_provenance(
    rows: list[dict[str, str]], repo_root: Path
) -> None:
    report = repo_root / TITLE_HOLDER_PROVENANCE_REPORT
    evidence = {
        (
            row.get("path", "").replace("\\", "/"),
            row.get("line", ""),
            row.get("holder", ""),
        ): row
        for row in read_csv(report)
    }
    for row in rows:
        if (
            row.get("domain") != "title_history"
            or row.get("classification") != "undefined_holder"
        ):
            continue
        match = evidence.get((row["path"], row["line"], row["object"]))
        if not match:
            continue
        row["provenance"] = match["provenance"]
        row["reason"] = (
            f"{match['classification']}: {match['reason']}"
        )
        row["recommendation"] = match["recommendation"]
        candidates = (
            match.get("candidate_defined_premerge_holders", "")
            or match.get("candidate_defined_source_holders", "")
        )
        row["candidate_value"] = candidates
        row["source_report"] = TITLE_HOLDER_PROVENANCE_REPORT


def first_meaningful_line(lines: list[str]) -> str:
    for line in lines:
        clean = line.lstrip("\ufeff").strip()
        if clean and not clean.startswith("#"):
            return clean
    return ""


def scan_localization(
    directory: Path, root: Path, label: str
) -> tuple[
    dict[str, list[dict[str, str]]], list[dict[str, str]], list[dict[str, str]]
]:
    keys: dict[str, list[dict[str, str]]] = defaultdict(list)
    files: list[dict[str, str]] = []
    rows: list[dict[str, str]] = []
    if not directory.is_dir():
        return {}, files, rows
    for path in sorted(directory.rglob("*.yml")):
        lines = read_text(path).splitlines()
        header = first_meaningful_line(lines)
        by_name = path.name.lower().endswith("_l_english.yml")
        by_header = header == "l_english:"
        if not by_name and not by_header:
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.as_posix()
        display = relative if label == "mod" else f"{label}/{relative}"
        files.append({
            "source": label,
            "path": display,
            "matched_by_name": "yes" if by_name else "no",
            "matched_by_header": "yes" if by_header else "no",
        })
        if not by_header:
            rows.append(finding(
                "localization", "english_files", "missing_english_header",
                "blocker", "high", display, 1, path.name,
                "English localization filename has no l_english: header",
                "add_or_correct_english_header",
            ))
        for line_number, raw in enumerate(lines, start=1):
            match = LOC_KEY_RE.match(strip_comment(raw).rstrip())
            if not match:
                continue
            key, value = match.groups()
            keys[key].append({
                "source": label,
                "path": display,
                "line": str(line_number),
                "value": value.strip(),
            })
    return dict(keys), files, rows


def localization_precedence(path: str) -> int:
    normalized = "/" + path.replace("\\", "/").lower().strip("/") + "/"
    if "/localization/replace/" in normalized:
        return 2
    if "/localization/english/replace/" in normalized:
        return 1
    return 0


def localization_literal(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def effective_localization_literal(
    mod_entries: list[dict[str, str]],
    vanilla_entries: list[dict[str, str]],
) -> str:
    if mod_entries:
        rank = max(localization_precedence(entry["path"]) for entry in mod_entries)
        entries = [
            entry for entry in mod_entries
            if localization_precedence(entry["path"]) == rank
        ]
    else:
        entries = vanilla_entries
    values = {localization_literal(entry["value"]) for entry in entries}
    return next(iter(values)) if len(values) == 1 else ""


def collect_raw_vanilla_title_ids(vanilla_root: Path) -> set[str]:
    result: set[str] = set()
    directory = vanilla_root / "common/landed_titles"
    for path in sorted(directory.rglob("*.txt")):
        snapshot = merge_state.build_snapshot(
            f"vanilla/{path.relative_to(directory).as_posix()}",
            read_text(path),
        )
        result.update(snapshot.titles)
    return result


def load_title_relation_map(path: Path) -> dict[str, str]:
    relations: dict[str, str] = {}
    if not path.is_file():
        return relations
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw_row in csv.DictReader(handle):
            row = {
                (key or "").strip(): (value or "").strip()
                for key, value in raw_row.items()
            }
            current_tokens = [
                token.replace("(second)", "").strip()
                for token in re.split(r"[&;]", row.get("source_title_id", ""))
                if TITLE_RE.fullmatch(token.replace("(second)", "").strip())
            ]
            source_tokens = [
                token.replace("(second)", "").strip()
                for token in re.split(r"[&;]", row.get("mod_title_id", ""))
                if TITLE_RE.fullmatch(token.replace("(second)", "").strip())
            ]
            if len(current_tokens) == len(source_tokens):
                pairs = zip(current_tokens, source_tokens, strict=True)
            elif len(source_tokens) == 1:
                pairs = ((current, source_tokens[0]) for current in current_tokens)
            else:
                continue
            for current_title, asil_mod_title in pairs:
                relations[current_title] = asil_mod_title
    return relations


def mapped_localization_key(key: str, title_relations: dict[str, str]) -> str:
    if key.endswith("_adj"):
        mapped_title = title_relations.get(key[:-4], "")
        return f"{mapped_title}_adj" if mapped_title else ""
    return title_relations.get(key, "")


def title_name_fallback_candidate(
    key: str,
    mod_keys: dict[str, list[dict[str, str]]],
    vanilla_keys: dict[str, list[dict[str, str]]],
    source_keys: dict[str, list[dict[str, str]]],
    title_relations: dict[str, str],
) -> tuple[str, str, str, str, str]:
    direct_sources = (
        ("mod", mod_keys),
        ("vanilla", vanilla_keys),
        ("asil_mod", source_keys),
    )
    for origin, candidates in direct_sources:
        entries = candidates.get(key, [])
        if not entries:
            continue
        values = {entry["value"] for entry in entries}
        if len(values) != 1:
            return "", "", key, origin, "conflicting_direct_title_name"
        value = next(iter(values))
        source = next(
            entry for entry in reversed(entries) if entry["value"] == value
        )
        return value, source["path"], key, origin, "direct_title_name"

    mapped_key = mapped_localization_key(key, title_relations)
    if not mapped_key or mapped_key == key:
        return "", "", "", "", ""
    for origin, candidates in direct_sources:
        entries = candidates.get(mapped_key, [])
        if not entries:
            continue
        values = {entry["value"] for entry in entries}
        if len(values) != 1:
            return "", "", mapped_key, origin, "conflicting_mapped_title_name"
        value = next(iter(values))
        source = next(
            entry for entry in reversed(entries) if entry["value"] == value
        )
        return value, source["path"], mapped_key, origin, "mapped_title_name"
    return "", "", mapped_key, "", "mapped_title_name_missing"


def localization_status(
    key: str,
    mod_keys: dict[str, list[dict[str, str]]],
    vanilla_keys: dict[str, list[dict[str, str]]],
    source_keys: dict[str, list[dict[str, str]]],
    title_relations: dict[str, str],
) -> tuple[str, str, str, str, str]:
    if key in mod_keys:
        return "mod", "", "", key, "mod"
    if key in vanilla_keys:
        return "vanilla_inherited", "", "", key, "vanilla"
    if key in source_keys:
        source = source_keys[key][0]
        return (
            "missing_effective_source_available", source["value"],
            source["path"], key, "asil_mod",
        )
    mapped_key = mapped_localization_key(key, title_relations)
    if mapped_key and mapped_key != key:
        for origin, candidates in (
            ("mod", mod_keys),
            ("vanilla", vanilla_keys),
            ("asil_mod", source_keys),
        ):
            if mapped_key not in candidates:
                continue
            source = candidates[mapped_key][0]
            return (
                "missing_effective_mapped_source_available", source["value"],
                source["path"], mapped_key, origin,
            )
    return "missing_everywhere", "", "", "", ""


def audit_localization(
    repo_root: Path,
    vanilla_root: Path,
    asil_mod_repo: Path,
    title_ids: set[str],
    cultural_names: set[str],
    noble_family_titles: set[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    mod_keys, mod_files, rows = scan_localization(
        repo_root / "BookmarksGit/localization", repo_root, "mod"
    )
    vanilla_keys, vanilla_files, vanilla_rows = scan_localization(
        vanilla_root / "localization", vanilla_root, "vanilla"
    )
    source_keys, source_files, source_rows = scan_localization(
        asil_mod_repo / "BookmarksGit/localization", asil_mod_repo, "asil_mod"
    )
    title_relations = load_title_relation_map(
        repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv"
    )
    vanilla_title_ids = collect_raw_vanilla_title_ids(vanilla_root)
    requirements: list[dict[str, str]] = []

    for key, entries in sorted(mod_keys.items()):
        values = {entry["value"] for entry in entries}
        if len(entries) > 1 and len(values) > 1:
            source_entries = source_keys.get(key, [])
            source_values = {entry["value"] for entry in source_entries}
            if len(source_values) > 1 and values == source_values:
                duplicate_provenance = "shared_asil_mod_baseline"
            elif source_values and source_values < values:
                duplicate_provenance = "mixed_yusseter_and_asil_mod"
            else:
                duplicate_provenance = "yusseter_current_only"
            rows.append(finding(
                "localization", "duplicate_keys", "conflicting_duplicate_key",
                "review", "high", entries[-1]["path"], entries[-1]["line"], key,
                "same mod localization key has differing values",
                "verify_intended_load_order_or_keep_one_value",
                current_value=" | ".join(sorted(values)),
                provenance=duplicate_provenance,
            ))

    requirement_specs = [
        (title_id, "title_base", "blocker") for title_id in sorted(title_ids)
    ]
    requirement_specs.extend(
        (key, "cultural_name", "blocker") for key in sorted(cultural_names)
    )
    requirement_specs.extend(
        (f"{title_id}_adj", "title_adj", "review")
        for title_id in sorted(title_ids)
        if title_id.startswith(("e_", "k_", "d_", "c_"))
    )
    for key, requirement, missing_severity in requirement_specs:
        (
            status, source_value, source_path, source_key, source_origin,
        ) = localization_status(
            key, mod_keys, vanilla_keys, source_keys, title_relations
        )
        title_key = key[:-4] if requirement == "title_adj" else key
        current_base_value = ""
        vanilla_base_value = ""
        if (
            requirement == "title_adj"
            and status == "missing_effective_mapped_source_available"
            and title_key in vanilla_title_ids
        ):
            current_base_value = effective_localization_literal(
                mod_keys.get(title_key, []),
                vanilla_keys.get(title_key, []),
            )
            vanilla_base_value = effective_localization_literal(
                [], vanilla_keys.get(title_key, [])
            )
            if current_base_value and current_base_value == vanilla_base_value:
                status = "vanilla_native_title_adjective_gap"
        if status.startswith("missing_") and title_key in noble_family_titles:
            status = "runtime_generated_noble_family_name"
            source_value = ""
            source_path = ""
            source_key = title_key
            source_origin = "runtime"
        fallback_value = ""
        fallback_path = ""
        fallback_key = ""
        fallback_origin = ""
        fallback_basis = ""
        if status == "missing_everywhere" and requirement == "title_adj":
            (
                fallback_value,
                fallback_path,
                fallback_key,
                fallback_origin,
                fallback_basis,
            ) = title_name_fallback_candidate(
                title_key,
                mod_keys,
                vanilla_keys,
                source_keys,
                title_relations,
            )
        requirements.append({
            "key": key,
            "requirement": requirement,
            "status": status,
            "source_value": source_value,
            "source_path": source_path,
            "source_key": source_key,
            "source_origin": source_origin,
            "fallback_candidate_value": fallback_value,
            "fallback_candidate_path": fallback_path,
            "fallback_candidate_key": fallback_key,
            "fallback_candidate_origin": fallback_origin,
            "fallback_candidate_basis": fallback_basis,
            "current_base_value": current_base_value,
            "vanilla_base_value": vanilla_base_value,
            "vanilla_title_defined": (
                "yes" if title_key in vanilla_title_ids else "no"
            ),
        })
        if status.startswith("missing_"):
            mapped_source = source_key and source_key != key
            base_name_fallback = bool(fallback_value)
            rows.append(finding(
                "localization", requirement, status,
                missing_severity,
                "high" if missing_severity == "blocker" else "medium",
                "BookmarksGit/localization", "", key,
                (
                    "required key is absent from effective mod plus vanilla "
                    f"localization; mapped source key is {source_key}"
                    if mapped_source else (
                        "required key is absent from effective mod plus vanilla "
                        f"localization; conservative base-title fallback is "
                        f"{fallback_key} from {fallback_origin}"
                        if base_name_fallback else
                        "required key is absent from effective mod plus vanilla localization"
                    )
                ),
                (
                    "copy_or_alias_mapped_localization_after_review"
                    if mapped_source else
                    ("copy_from_asil_mod_after_review" if source_value else (
                        "author_title_adj_from_base_name_after_review"
                        if base_name_fallback else "author_localization"
                    ))
                ),
                current_value=(f"mapped_source_key={source_key}" if mapped_source else ""),
                candidate_value=source_value or fallback_value,
                source_report=source_path or fallback_path or "current_state",
            ))
    files = mod_files + vanilla_files + source_files
    return requirements, files, rows


def audit_geographical_regions(
    repo_root: Path,
    definition: dict[int, dict[str, object]],
    title_ids: set[str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    directory = repo_root / "BookmarksGit/map_data/geographical_regions"
    for path in sorted(directory.rglob("*.txt")):
        relative = path.relative_to(repo_root).as_posix()
        raw_lines = read_text(path).splitlines()
        clean_text = "\n".join(strip_comment(line) for line in raw_lines)
        for match in re.finditer(r"\bprovinces\s*=\s*\{([^{}]*)\}", clean_text, re.DOTALL):
            line_number = clean_text.count("\n", 0, match.start()) + 1
            for raw_id in re.findall(r"\b\d+\b", match.group(1)):
                province_id = int(raw_id)
                if province_id not in definition:
                    rows.append(finding(
                        "map_regions", "province_reference",
                        "undefined_province_reference", "blocker", "high",
                        relative, line_number, raw_id,
                        "geographical region province is absent from definition.csv",
                        "remove_or_remap_region_province",
                    ))
        for line_number, line in enumerate(clean_text.splitlines(), start=1):
            for title_id in TITLE_RE.findall(line):
                if title_id not in title_ids:
                    rows.append(finding(
                        "map_regions", "title_reference",
                        "undefined_title_reference", "review", "medium",
                        relative, line_number, title_id,
                        "geographical region title is absent from current landed titles",
                        "verify_external_or_stale_title_reference",
                    ))
    return rows


def refresh_semantic_audit(
    repo_root: Path, asil_mod_repo: Path, vanilla_root: Path
) -> str:
    script = repo_root / ".codex/works/tools/audit_repo_semantic_compatibility.py"
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo-root", str(repo_root),
            "--asil-mod-repo", str(asil_mod_repo),
            "--vanilla-game-root", str(vanilla_root),
        ],
        cwd=repo_root,
        env=env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=300,
    )
    if result.returncode:
        raise RuntimeError(
            "semantic audit failed: " + (result.stderr.strip() or result.stdout.strip())
        )
    return result.stdout.strip()


def load_semantic_findings(repo_root: Path) -> list[dict[str, str]]:
    report = repo_root / SEMANTIC_PATH / "repo_semantic_compatibility_findings.csv"
    rows: list[dict[str, str]] = []
    for raw in read_csv(report):
        domain = raw.get("domain", "semantic_provenance")
        severity = raw.get("severity", "review")
        if severity not in {"blocker", "review", "info"}:
            severity = "review"
        rows.append(finding(
            domain,
            "source_provenance" if domain == "title_history" else domain,
            raw.get("classification", "semantic_candidate"),
            severity,
            raw.get("confidence", "review"),
            raw.get("path", ""),
            raw.get("line", ""),
            raw.get("object", ""),
            raw.get("reason", ""),
            raw.get("recommendation", ""),
            raw.get("current_value", ""),
            raw.get("candidate_value", ""),
            source_report=(Path(SEMANTIC_PATH) / report.name).as_posix(),
            provenance=(
                "yusseter_merge_regression_from_asil_mod"
                if raw.get("classification") == "merge_regression"
                else "yusseter_integration_bug"
                if raw.get("classification") == "yusseter_integration_bug"
                else "asil_mod_semantic_review"
            ),
        ))
    return rows


def load_binary_map_findings(repo_root: Path) -> list[dict[str, str]]:
    report = repo_root / (
        ".codex/works/analysis/generated/repo_integration_closure/"
        "map_definition_pixel_audit/binary_map_findings.csv"
    )
    rows: list[dict[str, str]] = []
    recommendations = {
        "source_semantic_reference_requires_remap": (
            "review_relation_candidate_then_remap_source_references"
        ),
        "source_semantic_reference_relation_review": (
            "prove_relation_candidate_before_remapping_source_references"
        ),
        "semantic_reference_missing_pixels_unmapped_review": (
            "review_stale_geometry_registration_or_resolve_mapping"
        ),
        "current_content_reference_missing_pixels": (
            "restore_pixels_or_remove_stale_history_locator_references"
        ),
        "multipart_map_geometry_review": (
            "compare_components_with_intended_islands_and_premerge_map"
        ),
        "tiny_map_geometry_review": "manually_review_tiny_map_geometry",
        "missing_pixels_non_geometry_reference_review": (
            "remove_or_remap_stale_non_geometry_reference"
        ),
    }
    for row in read_csv(report):
        classification = row.get("classification", "binary_map_finding")
        province_id = row.get("province_id", "")
        rgb = row.get("rgb", "")
        rows.append(finding(
            "binary_map",
            "provinces_png",
            classification,
            row.get("severity", "review"),
            "high" if row.get("severity") == "blocker" else "reasonable",
            "BookmarksGit/map_data/provinces.png",
            "",
            province_id or rgb,
            row.get("details", "binary map audit finding"),
            recommendations.get(classification, "review_binary_map_finding"),
            current_value=rgb,
            source_report=report.relative_to(repo_root).as_posix(),
            provenance=row.get("provenance", "current_state_unclassified"),
        ))
    return rows


def normalize_runtime_path(value: str) -> str:
    path = value.replace("\\", "/").strip()
    for prefix in ("current:", "mod:"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    path = path.lstrip("./")
    if path and not path.lower().startswith("bookmarksgit/"):
        path = "BookmarksGit/" + path
    return path


def load_bookmark_runtime_findings(repo_root: Path) -> list[dict[str, str]]:
    report = repo_root / RUNTIME_PATH / "bookmark_runtime_static_findings_compact.csv"
    if not report.exists():
        return []
    rows: list[dict[str, str]] = []
    for row in read_csv(report):
        title_id = row.get("title_id", "")
        holder = row.get("holder", "")
        bookmark_date = row.get("bookmark_date", "")
        holder_status = row.get("holder_status", "")
        occurrence_count = row.get("occurrence_count", "1")
        state_bits = [
            f"bookmark={bookmark_date}",
            f"holder={holder}",
            f"status={holder_status}",
            f"occurrences={occurrence_count}",
        ]
        if row.get("liege"):
            state_bits.append(f"liege={row['liege']}")
        if row.get("government"):
            state_bits.append(f"government={row['government']}")
        rows.append(finding(
            "runtime",
            "bookmarks",
            row.get("issue", "bookmark_static_finding"),
            row.get("severity", "review"),
            row.get("confidence", "reasonable"),
            normalize_runtime_path(row.get("path", "")),
            row.get("line", ""),
            title_id or holder,
            f"{row.get('reason', 'bookmark static audit finding')}; "
            + "; ".join(state_bits),
            row.get("recommendation", "review_bookmark_static_finding"),
            current_value=row.get("current_signature", "") or "; ".join(state_bits),
            candidate_value=row.get("asil_mod_signature", ""),
            source_report=report.relative_to(repo_root).as_posix(),
            provenance=row.get("provenance", "current_state_unclassified"),
        ))
    return rows


def load_province_history_semantic_findings(
    repo_root: Path,
) -> list[dict[str, str]]:
    report = (
        repo_root / PROVINCE_SEMANTICS_PATH /
        "province_history_semantic_findings_compact.csv"
    )
    if not report.exists():
        return []
    rows: list[dict[str, str]] = []
    for row in read_csv(report):
        state_bits = [
            f"bookmark={row.get('bookmark_date', '')}",
            f"province={row.get('province_id', '')}",
            f"barony={row.get('barony_id', '')}",
            f"occurrences={row.get('occurrence_count', '1')}",
        ]
        if row.get("mapped_from_province"):
            state_bits.append(
                f"mapped_from={row['mapped_from_province']}"
            )
        rows.append(finding(
            "province_history",
            "bookmark_semantics",
            row.get("issue", "province_history_semantic_finding"),
            row.get("severity", "review"),
            row.get("confidence", "reasonable"),
            normalize_runtime_path(row.get("path", "")),
            row.get("line", ""),
            row.get("province_id", "") or row.get("barony_id", ""),
            f"{row.get('reason', 'province-history semantic finding')}; "
            + "; ".join(state_bits),
            row.get("recommendation", "review_province_history_semantics"),
            current_value=row.get("current_signature", ""),
            candidate_value=row.get("source_signature", ""),
            source_report=report.relative_to(repo_root).as_posix(),
            provenance=row.get("provenance", "current_state_unclassified"),
        ))
    return rows


def normalize_tiger_path(value: str) -> str:
    path = value.replace("\\", "/").lstrip("./")
    if path and not path.lower().startswith("bookmarksgit/"):
        path = "BookmarksGit/" + path
    return path


def normalize_region_audit_path(repo_root: Path, value: str) -> str:
    path = value.replace("\\", "/").lstrip("./")
    if path.lower().startswith("bookmarksgit/"):
        return path
    if path.startswith("map_data/geographical_regions/"):
        return "BookmarksGit/" + path
    region_root = repo_root / "BookmarksGit/map_data/geographical_regions"
    direct = region_root / path
    if direct.is_file():
        return direct.relative_to(repo_root).as_posix()
    matches = sorted(region_root.rglob(Path(path).name)) if region_root.is_dir() else []
    if len(matches) == 1:
        return matches[0].relative_to(repo_root).as_posix()
    return "BookmarksGit/map_data/geographical_regions/" + path


def load_silk_road_market_closure(
    repo_root: Path,
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    audit_root = repo_root / SILK_ROAD_MARKET_CLOSURE_PATH
    root_report = audit_root / "silk_road_market_root_causes.csv"
    finding_report = audit_root / "silk_road_market_findings.csv"
    design_report = audit_root / "silk_road_market_fix_design.csv"
    root_rows = read_csv(root_report)
    raw_rows = read_csv(finding_report)
    design_rows = read_csv(design_report)
    raw_by_root: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in raw_rows:
        raw_by_root[row.get("root_cause_key", "")].append(row)
    design_by_root = {
        row.get("linked_root_cause_key", ""): row
        for row in design_rows
        if row.get("linked_root_cause_key")
    }
    provenance_map = {
        "shared_premerge_and_asil": "shared_asil_mod_baseline",
        "missing_after_asil_mod_source": (
            "preexisting_yusseter_source_integration_gap"
        ),
        "vanilla": "shared_vanilla_baseline",
    }
    findings: list[dict[str, str]] = []
    for root in root_rows:
        root_key = root.get("root_cause_key", "")
        if not root_key or root.get("severity") not in {"blocker", "review"}:
            continue
        design = design_by_root.get(root_key, {})
        representatives = sorted(
            raw_by_root.get(root_key, []),
            key=lambda row: (
                not bool(row.get("line")),
                row.get("path", ""),
                int(row.get("line") or 0),
            ),
        )
        representative = representatives[0] if representatives else {}
        source_path = design.get("source_path", "") or normalize_runtime_path(
            representative.get("path", "")
        )
        source_line = design.get("source_line", "") or representative.get("line", "")
        provenance = root.get("provenance", "")
        provenance = provenance_map.get(provenance, provenance or "current_state_unclassified")
        reason = root.get("reasons", "")
        if design.get("reason"):
            reason = f"{reason}; fix-design evidence: {design['reason']}"
        item = finding(
            "silk_road_market",
            "market_building_gui_closure",
            root_key.split(":", 1)[0],
            root.get("severity", "review"),
            design.get("confidence", "") or root.get("confidence", "medium"),
            source_path,
            source_line,
            root.get("objects", "") or root_key,
            reason,
            root.get("recommendations", "") or "review_silk_road_market_root",
            current_value=root.get("current_values", ""),
            candidate_value=(
                design.get("proposed_value", "")
                or root.get("candidate_values", "")
            ),
            source_report=" | ".join(filter(None, (
                root_report.relative_to(repo_root).as_posix(),
                design_report.relative_to(repo_root).as_posix() if design else "",
            ))),
            provenance=provenance,
        )
        item["external_root_cause_key"] = root_key
        item["auto_apply"] = "no"
        findings.append(item)
    return findings, root_rows, design_rows


def build_external_closure_links(
    repo_root: Path,
    findings: list[dict[str, str]],
    market_root_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    main_by_location: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in findings:
        key = (
            normalize_tiger_path(row.get("path", "")),
            row.get("line", ""),
            row.get("object", ""),
        )
        main_by_location[key].append(row)

    links: list[dict[str, str]] = []
    region_report = (
        repo_root / GEOGRAPHICAL_REGION_CLOSURE_PATH
        / "geographical_region_findings.csv"
    )
    region_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(region_report):
        region_groups[row.get("root_cause_key", "")].append(row)
    region_exact_roots = 0
    region_external_roots = 0
    for root_key, rows in sorted(region_groups.items()):
        matches: list[dict[str, str]] = []
        normalized_locations: set[str] = set()
        for row in rows:
            path = normalize_region_audit_path(repo_root, row.get("path", ""))
            line = row.get("line", "")
            obj = row.get("object", "")
            normalized_locations.add(f"{path}:{line}:{obj}")
            matches.extend(main_by_location.get((path, line, obj), []))
        if matches:
            link_status = "linked_existing_main_finding"
            region_exact_roots += 1
        else:
            link_status = "external_review_root_not_materialized"
            region_external_roots += 1
        links.append({
            "external_system": "geographical_region_closure",
            "external_root_cause_key": root_key,
            "severity": rows[0].get("severity", "review"),
            "confidence": rows[0].get("confidence", ""),
            "classifications": joined_values({
                row.get("classification", "") for row in rows
            }),
            "provenance": joined_values({row.get("provenance", "") for row in rows}),
            "raw_finding_count": str(len(rows)),
            "normalized_locations": joined_values(normalized_locations),
            "link_status": link_status,
            "main_match_count": str(len(matches)),
            "main_match_domains": joined_values({row.get("domain", "") for row in matches}),
            "main_match_classifications": joined_values({
                row.get("classification", "") for row in matches
            }),
            "main_match_objects": joined_values({row.get("object", "") for row in matches}),
            "source_report": region_report.relative_to(repo_root).as_posix(),
            "recommendation": joined_values({
                row.get("recommendation", "") for row in rows
            }),
            "auto_apply": "no",
        })

    market_report = (
        repo_root / SILK_ROAD_MARKET_CLOSURE_PATH
        / "silk_road_market_root_causes.csv"
    )
    market_main = defaultdict(list)
    for row in findings:
        if row.get("domain") == "silk_road_market":
            market_main[row.get("external_root_cause_key", "")].append(row)
    for root in sorted(market_root_rows, key=lambda row: row.get("root_cause_key", "")):
        root_key = root.get("root_cause_key", "")
        matches = market_main.get(root_key, [])
        links.append({
            "external_system": "silk_road_market_closure",
            "external_root_cause_key": root_key,
            "severity": root.get("severity", ""),
            "confidence": root.get("confidence", ""),
            "classifications": root.get("classifications", ""),
            "provenance": root.get("provenance", ""),
            "raw_finding_count": root.get("raw_finding_count", ""),
            "normalized_locations": joined_values({
                f"{row.get('path', '')}:{row.get('line', '')}:{row.get('object', '')}"
                for row in matches
            }),
            "link_status": (
                "materialized_once_in_main_closure"
                if len(matches) == 1 else "market_materialization_mismatch"
            ),
            "main_match_count": str(len(matches)),
            "main_match_domains": joined_values({row.get("domain", "") for row in matches}),
            "main_match_classifications": joined_values({
                row.get("classification", "") for row in matches
            }),
            "main_match_objects": joined_values({row.get("object", "") for row in matches}),
            "source_report": market_report.relative_to(repo_root).as_posix(),
            "recommendation": root.get("recommendations", ""),
            "auto_apply": "no",
        })
    stats = {
        "region_root_count": len(region_groups),
        "region_exact_root_count": region_exact_roots,
        "region_external_root_count": region_external_roots,
        "market_root_count": len(market_root_rows),
        "market_materialized_root_count": sum(
            row.get("external_system") == "silk_road_market_closure"
            and row.get("link_status") == "materialized_once_in_main_closure"
            for row in links
        ),
    }
    return links, stats


LINE_PROVENANCE_MAP = {
    "shared_premerge_and_asil_line": "shared_asil_mod_baseline",
    "preexisting_yusseter_line": "preexisting_yusseter",
    "post_premerge_asil_line": "upstream_integration",
    "path_absent_at_premerge": "upstream_integration",
    "current_only_or_adapted_line": "yusseter_current_only_or_adapted",
    "insufficient_line_signature": "current_state_unclassified",
}


def normalized_line_provenance(value: str) -> str:
    return LINE_PROVENANCE_MAP.get(value, value or "current_state_unclassified")


def split_first_location(value: str) -> tuple[str, str]:
    first = (value or "").split(" | ", 1)[0]
    path, separator, line = first.rpartition(":")
    return (path, line) if separator else (first, "")


def load_tiger_root_cause_findings(repo_root: Path) -> list[dict[str, str]]:
    report = (
        repo_root / TIGER_CLASSIFICATION_PATH
        / "ck3_tiger_current_only_root_causes.csv"
    )
    rows = []
    info_classes = {
        "intentional_definition_placeholder_name",
        "intentional_runtime_generated_localization",
        "localization_style_tip",
    }
    for raw in read_csv(report):
        path, line = split_first_location(raw.get("locations", ""))
        classification = raw.get("classification", "classified_tiger_root_cause")
        reason_bits = [
            f"action_priority={raw.get('action_priority', '')}",
            f"finding_count={raw.get('finding_count', '')}",
            raw.get("message", ""),
            raw.get("evidence", ""),
        ]
        rows.append(finding(
            "ck3_tiger",
            "current_only_root_cause",
            classification,
            "info" if classification in info_classes else "review",
            "high" if raw.get("action_priority") == "P0" else "reasonable",
            path,
            line,
            raw.get("source_object", "") or raw.get("root_cause_id", ""),
            "; ".join(bit for bit in reason_bits if bit),
            raw.get("recommendation", "review_classified_tiger_root_cause"),
            current_value=raw.get("source_object", ""),
            candidate_value=raw.get("candidate_object", ""),
            source_report=report.relative_to(repo_root).as_posix(),
            provenance=normalized_line_provenance(
                raw.get("line_provenance", "")
            ),
        ))
    return rows


def load_tiger_classified_locations(
    repo_root: Path,
) -> set[tuple[str, str, str]]:
    report = (
        repo_root / TIGER_CLASSIFICATION_PATH
        / "ck3_tiger_current_only_classified.csv"
    )
    return {
        (
            normalize_tiger_path(row.get("path", "")),
            row.get("line", ""),
            row.get("source_object", ""),
        )
        for row in read_csv(report)
        if row.get("source_object")
    }


def load_dynamic_title_reference_findings(
    repo_root: Path,
    tiger_locations: set[tuple[str, str, str]],
) -> tuple[list[dict[str, str]], int, int]:
    directory = repo_root / DYNAMIC_TITLE_REFERENCE_PATH
    report = directory / "dynamic_title_reference_findings.csv"
    raw_rows = read_csv(report)
    overlaps = 0
    rows = []
    for raw in raw_rows:
        key = (
            normalize_tiger_path(raw.get("path", "")),
            raw.get("line", ""),
            raw.get("title_id", ""),
        )
        if key in tiger_locations:
            overlaps += 1
            continue
        reason_bits = [
            raw.get("evidence", ""),
            f"consumer={raw.get('consumer_token', '')}",
            f"dependency_context={raw.get('dependency_context', '')}",
        ]
        rows.append(finding(
            "localization",
            "dynamic_title_reference",
            raw.get("classification", "dynamic_title_reference_review"),
            raw.get("severity", "review"),
            raw.get("confidence", "reasonable"),
            normalize_tiger_path(raw.get("path", "")),
            raw.get("line", ""),
            raw.get("title_id", ""),
            "; ".join(bit for bit in reason_bits if bit),
            raw.get("recommendation", "review_dynamic_title_reference"),
            current_value=raw.get("title_id", ""),
            candidate_value=raw.get("candidate_titles", ""),
            source_report=report.relative_to(repo_root).as_posix(),
            provenance=normalized_line_provenance(
                raw.get("line_provenance", "")
            ),
        ))
    return rows, len(raw_rows), overlaps


def tiger_signature(report: dict[str, object]) -> tuple[object, ...]:
    locations = report.get("locations") or []
    paths = tuple(sorted({
        normalize_tiger_path(str(location.get("path") or location.get("fullpath") or "")).lower()
        for location in locations
        if isinstance(location, dict) and location.get("from") == "MOD"
    }))
    return (
        report.get("severity", ""),
        report.get("confidence", ""),
        report.get("key", ""),
        report.get("message", ""),
        paths,
    )


def analyze_tiger_reports(
    current_path: Path,
    source_path: Path,
    static_findings: list[dict[str, str]],
) -> tuple[
    list[dict[str, str]], list[dict[str, str]],
    list[dict[str, str]], list[dict[str, str]],
]:
    if not current_path.exists() or not source_path.exists():
        return [], [], [], []
    current = json.loads(current_path.read_text(encoding="utf-8-sig"))
    source = json.loads(source_path.read_text(encoding="utf-8-sig"))
    source_counts = Counter(tiger_signature(report) for report in source)
    static_by_location: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in static_findings:
        if row["severity"] != "blocker" or not row["path"] or not row["line"]:
            continue
        static_by_location[
            (normalize_tiger_path(row["path"]).lower(), row["line"])
        ].append(row)

    comparison: list[dict[str, str]] = []
    summary_counts: Counter[tuple[str, str, str, str]] = Counter()
    current_only_findings: list[dict[str, str]] = []
    overlaps: list[dict[str, str]] = []
    for index, report in enumerate(current, start=1):
        signature = tiger_signature(report)
        if source_counts[signature] > 0:
            provenance = "shared_asil_mod_baseline"
            source_counts[signature] -= 1
        else:
            provenance = "yusseter_current_only"
        locations = [
            location for location in (report.get("locations") or [])
            if isinstance(location, dict) and location.get("from") == "MOD"
        ]
        primary = locations[0] if locations else {}
        display_path = normalize_tiger_path(
            str(primary.get("path") or primary.get("fullpath") or "")
        )
        line_number = str(primary.get("linenr") or "")
        row = {
            "report_id": str(index),
            "provenance": provenance,
            "severity": str(report.get("severity", "")),
            "confidence": str(report.get("confidence", "")),
            "key": str(report.get("key", "")),
            "message": str(report.get("message", "")),
            "path": display_path,
            "line": line_number,
            "location_count": str(len(locations)),
        }
        comparison.append(row)
        summary_counts[(
            provenance, row["severity"], row["key"], row["confidence"]
        )] += 1
        if provenance == "yusseter_current_only":
            current_only_findings.append(finding(
                "ck3_tiger", row["key"], "current_only_tiger_report",
                "review", row["confidence"], display_path, line_number,
                row["key"], row["message"],
                "classify_against_yusseter_intent_before_fix",
                source_report=current_path.name,
                provenance="yusseter_current_only",
            ))
        for location in locations:
            location_path = normalize_tiger_path(
                str(location.get("path") or location.get("fullpath") or "")
            )
            location_line = str(location.get("linenr") or "")
            for static in static_by_location.get(
                (location_path.lower(), location_line), []
            ):
                overlaps.append({
                    "tiger_report_id": str(index),
                    "tiger_provenance": provenance,
                    "tiger_severity": row["severity"],
                    "tiger_confidence": row["confidence"],
                    "tiger_key": row["key"],
                    "tiger_message": row["message"],
                    "path": location_path,
                    "line": location_line,
                    "static_domain": static["domain"],
                    "static_classification": static["classification"],
                    "static_object": static["object"],
                })
    summary = [
        {
            "provenance": key[0],
            "severity": key[1],
            "key": key[2],
            "confidence": key[3],
            "count": str(count),
        }
        for key, count in sorted(
            summary_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    return comparison, summary, current_only_findings, overlaps


def compare_tiger_config_runs(
    label: str,
    standard_path: Path,
    minimal_path: Path,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    if not standard_path.exists() or not minimal_path.exists():
        return [], {}
    standard = json.loads(standard_path.read_text(encoding="utf-8-sig"))
    minimal = json.loads(minimal_path.read_text(encoding="utf-8-sig"))
    standard_counts = Counter(
        (
            str(row.get("severity", "")),
            str(row.get("confidence", "")),
            str(row.get("key", "")),
        )
        for row in standard
    )
    minimal_counts = Counter(
        (
            str(row.get("severity", "")),
            str(row.get("confidence", "")),
            str(row.get("key", "")),
        )
        for row in minimal
    )
    rows: list[dict[str, str]] = []
    for severity, confidence, key in sorted(
        set(standard_counts) | set(minimal_counts)
    ):
        standard_count = standard_counts[(severity, confidence, key)]
        minimal_count = minimal_counts[(severity, confidence, key)]
        if standard_count == minimal_count:
            continue
        rows.append({
            "mod": label,
            "severity": severity,
            "confidence": confidence,
            "key": key,
            "standard_count": str(standard_count),
            "minimal_config_count": str(minimal_count),
            "delta": str(minimal_count - standard_count),
        })
    return rows, {
        "standard_total": len(standard),
        "minimal_total": len(minimal),
        "changed_key_classes": len(rows),
    }


def newest_mtime(paths: list[Path]) -> float:
    values = [path.stat().st_mtime for path in paths if path.exists() and path.is_file()]
    return max(values, default=0.0)


def report_freshness(report: Path, sources: list[Path]) -> tuple[str, str]:
    if not report.exists():
        return "no", "unknown"
    source_newer = newest_mtime(sources) > report.stat().st_mtime
    return "yes", "yes" if source_newer else "no"


def joined_values(values: list[str] | set[str]) -> str:
    return " | ".join(sorted({value for value in values if value}))


def build_blocker_root_causes(
    repo_root: Path,
    findings: list[dict[str, str]],
) -> list[dict[str, str]]:
    runtime_dir = repo_root / RUNTIME_PATH
    static_report = runtime_dir / "title_holder_reference_provenance.csv"
    runtime_report = runtime_dir / "bookmark_runtime_static_findings_compact.csv"
    static_rows = read_csv(static_report)
    runtime_rows = [
        row for row in read_csv(runtime_report)
        if row.get("severity") == "blocker"
    ]

    runtime_undefined_by_holder: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in runtime_rows:
        if row.get("issue") == "effective_holder_undefined":
            runtime_undefined_by_holder[row.get("holder", "")].append(row)

    static_by_holder: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in static_rows:
        static_by_holder[row.get("holder", "")].append(row)

    roots: list[dict[str, str]] = []
    consumed_runtime_rows: set[int] = set()
    for holder, assignments in static_by_holder.items():
        runtime_impacts = runtime_undefined_by_holder.get(holder, [])
        consumed_runtime_rows.update(id(row) for row in runtime_impacts)
        classifications = {row.get("classification", "") for row in assignments}
        provenances = {row.get("provenance", "") for row in assignments}
        recommendations = {
            row.get("recommendation", "") for row in assignments
        }
        if len(classifications) == 1:
            classification = next(iter(classifications))
        else:
            classification = "undefined_holder_multiple_assignment_origins"
        provenance = (
            next(iter(provenances))
            if len(provenances) == 1
            else "mixed_provenance"
        )
        paths = {
            normalize_runtime_path(row.get("path", ""))
            for row in assignments + runtime_impacts
        }
        locations = {
            f"{normalize_runtime_path(row.get('path', ''))}:{row.get('line', '')}"
            for row in assignments + runtime_impacts
        }
        titles = {
            row.get("title_id", "") for row in assignments + runtime_impacts
        }
        dates = {
            row.get("bookmark_date", "") for row in runtime_impacts
        }
        roots.append({
            "subsystem": "character_title_history",
            "classification": classification,
            "severity": "blocker",
            "confidence": "high",
            "primary_object": holder,
            "provenance": provenance,
            "raw_finding_count": str(len(assignments) + len(runtime_impacts)),
            "static_assignment_count": str(len(assignments)),
            "runtime_impact_count": str(len(runtime_impacts)),
            "runtime_occurrence_count": str(sum(
                int(row.get("occurrence_count") or 1) for row in runtime_impacts
            )),
            "impacted_titles": joined_values(titles),
            "bookmark_dates": joined_values(dates),
            "paths": joined_values(paths),
            "locations": joined_values(locations),
            "reason": (
                f"undefined character referenced by {len(assignments)} title-history "
                f"assignments and {len(runtime_impacts)} compact bookmark states; "
                f"assignment classifications={joined_values(classifications)}"
            ),
            "recommendation": joined_values(recommendations),
            "source_reports": joined_values({
                static_report.relative_to(repo_root).as_posix(),
                runtime_report.relative_to(repo_root).as_posix()
                if runtime_impacts else "",
            }),
        })

    remaining_runtime: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in runtime_rows:
        if id(row) in consumed_runtime_rows:
            continue
        remaining_runtime[
            (row.get("issue", ""), row.get("holder", ""))
        ].append(row)
    for (issue, holder), rows in remaining_runtime.items():
        provenances = {row.get("provenance", "") for row in rows}
        recommendations = {row.get("recommendation", "") for row in rows}
        paths = {
            normalize_runtime_path(row.get("path", "")) for row in rows
        }
        locations = {
            f"{normalize_runtime_path(row.get('path', ''))}:{row.get('line', '')}"
            for row in rows
        }
        roots.append({
            "subsystem": "bookmark_runtime",
            "classification": issue,
            "severity": "blocker",
            "confidence": "high",
            "primary_object": holder,
            "provenance": (
                next(iter(provenances))
                if len(provenances) == 1 else "mixed_provenance"
            ),
            "raw_finding_count": str(len(rows)),
            "static_assignment_count": "0",
            "runtime_impact_count": str(len(rows)),
            "runtime_occurrence_count": str(sum(
                int(row.get("occurrence_count") or 1) for row in rows
            )),
            "impacted_titles": joined_values({
                row.get("title_id", "") for row in rows
            }),
            "bookmark_dates": joined_values({
                row.get("bookmark_date", "") for row in rows
            }),
            "paths": joined_values(paths),
            "locations": joined_values(locations),
            "reason": joined_values({row.get("reason", "") for row in rows}),
            "recommendation": joined_values(recommendations),
            "source_reports": runtime_report.relative_to(repo_root).as_posix(),
        })

    folded_classes = {
        ("title_history", "undefined_holder"),
        ("runtime", "effective_holder_undefined"),
        ("runtime", "effective_holder_born_after_bookmark"),
        ("runtime", "featured_character_undefined"),
        ("runtime", "featured_character_dead_before_bookmark"),
    }
    for row in findings:
        if row.get("severity") != "blocker":
            continue
        if (row.get("domain", ""), row.get("classification", "")) in folded_classes:
            continue
        roots.append({
            "subsystem": row.get("domain", ""),
            "classification": row.get("classification", ""),
            "severity": "blocker",
            "confidence": row.get("confidence", ""),
            "primary_object": row.get("object", ""),
            "provenance": row.get("provenance", ""),
            "raw_finding_count": "1",
            "static_assignment_count": "0",
            "runtime_impact_count": "0",
            "runtime_occurrence_count": "0",
            "impacted_titles": row.get("object", "")
            if row.get("domain") == "localization" else "",
            "bookmark_dates": "",
            "paths": row.get("path", ""),
            "locations": (
                f"{row.get('path', '')}:{row.get('line', '')}"
                if row.get("path") else ""
            ),
            "reason": row.get("reason", ""),
            "recommendation": row.get("recommendation", ""),
            "source_reports": row.get("source_report", ""),
        })

    roots.sort(key=lambda row: (
        row["subsystem"],
        row["classification"],
        row["primary_object"],
        row["locations"],
    ))
    for index, row in enumerate(roots, start=1):
        row["root_cause_id"] = f"BRC{index:04d}"
    return roots


def apply_localization_visibility(
    findings: list[dict[str, str]],
    visibility_rows: list[dict[str, str]],
    source_report: str,
) -> Counter[str]:
    by_key = {
        row.get("title_id", ""): row
        for row in visibility_rows
        if row.get("title_id")
    }
    applied: Counter[str] = Counter()
    for row in findings:
        if not (
            row.get("domain") == "localization"
            and row.get("subdomain") == "title_base"
            and row.get("classification") == "missing_everywhere"
        ):
            continue
        visibility = by_key.get(row.get("object", ""))
        if not visibility:
            continue
        row["current_value"] = "raw_localization_status=missing_everywhere"
        row["classification"] = visibility["visibility_classification"]
        row["severity"] = visibility["classified_severity"]
        row["confidence"] = visibility["confidence"]
        row["reason"] = visibility["reason"]
        row["recommendation"] = visibility["recommendation"]
        row["source_report"] = source_report
        applied[row["severity"]] += 1
    return applied


def apply_upstream_character_root_classification(
    root_causes: list[dict[str, str]],
    audit_rows: list[dict[str, str]],
    source_report: str,
) -> Counter[str]:
    by_key = {
        (row.get("root_classification", ""), row.get("character_id", "")): row
        for row in audit_rows
        if row.get("root_classification") and row.get("character_id")
    }
    applied: Counter[str] = Counter()
    for root in root_causes:
        key = (root.get("classification", ""), root.get("primary_object", ""))
        audit = by_key.get(key)
        if not audit:
            continue
        recovery = audit.get("recovery_classification", "")
        root["recovery_classification"] = recovery
        root["recovery_confidence"] = audit.get("confidence", "")
        root["recovery_reason"] = audit.get("reason", "")
        root["recovery_recommendation"] = audit.get("recommendation", "")
        root["historical_asil_found"] = audit.get(
            "historical_asil_found", ""
        )
        root["historical_asil_revision"] = audit.get(
            "historical_asil_revision", ""
        )
        root["historical_asil_path"] = audit.get("historical_asil_path", "")
        root["historical_asil_line"] = audit.get("historical_asil_line", "")
        root["source_origin_classification"] = audit.get(
            "source_origin_classification", ""
        )
        root["source_origin_evidence"] = audit.get(
            "source_origin_evidence", ""
        )
        root["recovery_source_report"] = source_report
        root["source_reports"] = joined_values({
            root.get("source_reports", ""), source_report,
        })
        applied[recovery] += 1
    return applied


def apply_non_character_root_classification(
    root_causes: list[dict[str, str]],
    audit_rows: list[dict[str, str]],
    source_report: str,
) -> Counter[str]:
    by_key = {
        (
            row.get("root_classification", ""),
            row.get("primary_object", ""),
        ): row
        for row in audit_rows
        if row.get("root_classification") and row.get("primary_object")
    }
    applied: Counter[str] = Counter()
    for root in root_causes:
        key = (root.get("classification", ""), root.get("primary_object", ""))
        audit = by_key.get(key)
        if not audit:
            continue
        recovery = audit.get("recovery_classification", "")
        root["recovery_classification"] = recovery
        root["recovery_confidence"] = audit.get("confidence", "")
        root["recovery_reason"] = audit.get("reason", "")
        root["recovery_recommendation"] = audit.get("recommendation", "")
        root["recovery_candidate_value"] = audit.get("candidate_value", "")
        root["recovery_candidate_source_key"] = audit.get(
            "candidate_source_key", ""
        )
        root["recovery_candidate_source_path"] = audit.get(
            "candidate_source_path", ""
        )
        root["recovery_candidate_source_line"] = audit.get(
            "candidate_source_line", ""
        )
        root["recovery_evidence_status"] = audit.get("evidence_status", "")
        root["recovery_evidence_sources"] = audit.get(
            "evidence_sources", ""
        )
        root["recovery_source_report"] = source_report
        root["source_reports"] = joined_values({
            root.get("source_reports", ""), source_report,
        })
        applied[recovery] += 1
    return applied


def coverage_row(
    domain: str,
    subdomain: str,
    scope: str,
    file_count: int,
    method: str,
    status: str,
    report_path: str,
    findings: list[dict[str, str]],
    report_exists: str = "yes",
    source_newer: str = "no",
    notes: str = "",
) -> dict[str, str]:
    relevant = [
        row for row in findings
        if row["domain"] == domain
        and (not subdomain or row["subdomain"] == subdomain)
    ]
    return {
        "domain": domain,
        "subdomain": subdomain,
        "scope": scope,
        "file_count": str(file_count),
        "audit_method": method,
        "coverage_status": status,
        "report_path": report_path,
        "report_exists": report_exists,
        "source_newer_than_report": source_newer,
        "blocker_count": str(sum(row["severity"] == "blocker" for row in relevant)),
        "review_count": str(sum(row["severity"] == "review" for row in relevant)),
        "notes": notes,
    }


def git_revision(repo_root: Path, revision: str = "HEAD") -> str:
    result = subprocess.run(
        ["git", "rev-parse", revision], cwd=repo_root, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    return result.stdout.strip()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    asil_mod_repo = args.asil_mod_repo.resolve()
    vanilla_root = args.vanilla_game_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    semantic_stdout = "skipped"
    if not args.skip_semantic_refresh:
        semantic_stdout = refresh_semantic_audit(
            repo_root, asil_mod_repo, vanilla_root
        )
    semantic_evidence = (
        "existing_current_report_reused"
        if args.skip_semantic_refresh
        else (semantic_stdout.splitlines()[-1] if semantic_stdout else "completed")
    )

    findings: list[dict[str, str]] = []
    definition_path = repo_root / DEFINITION_PATH
    definition, _ = parse_definition_file(
        definition_path, DEFINITION_PATH, findings
    )
    vanilla_definition_path = vanilla_root / "map_data/definition.csv"
    vanilla_definition, _ = parse_definition_file(
        vanilla_definition_path, "vanilla/map_data/definition.csv"
    )

    findings.extend(audit_default_map(repo_root, vanilla_root, definition))
    findings.extend(audit_adjacencies(repo_root, definition))
    findings.extend(audit_numeric_assignment_files(
        repo_root, "BookmarksGit/common/province_terrain", definition,
        "map_identity", "province_terrain",
    ))
    findings.extend(audit_locator_ids(repo_root, definition))

    (
        title_ids, province_baronies, capital_provinces,
        cultural_names, noble_family_titles, landed_rows,
    ) = audit_landed_titles(
        repo_root, vanilla_root, definition
    )
    findings.extend(landed_rows)
    findings.extend(audit_province_history(
        repo_root, vanilla_root, definition, vanilla_definition,
        province_baronies, capital_provinces,
    ))
    title_history_rows = audit_title_history(repo_root, vanilla_root, title_ids)
    apply_title_holder_reference_provenance(title_history_rows, repo_root)
    findings.extend(title_history_rows)
    findings.extend(audit_geographical_regions(repo_root, definition, title_ids))

    localization_requirements, localization_files, localization_rows = audit_localization(
        repo_root, vanilla_root, asil_mod_repo, title_ids, cultural_names,
        noble_family_titles,
    )
    findings.extend(localization_rows)
    findings.extend(load_semantic_findings(repo_root))
    classify_source_provenance(
        findings, repo_root, asil_mod_repo, vanilla_root, definition
    )
    localization_visibility_report = (
        repo_root / LOCALIZATION_VISIBILITY_PATH
        / "missing_title_localization_visibility.csv"
    )
    localization_visibility_rows = read_csv(localization_visibility_report)
    expected_visibility_keys = {
        row["key"] for row in localization_requirements
        if row.get("requirement") == "title_base"
        and row.get("status") == "missing_everywhere"
    }
    reported_visibility_keys = {
        row.get("title_id", "") for row in localization_visibility_rows
        if row.get("title_id")
    }
    localization_visibility_sources = [
        repo_root
        / ".codex/works/tools/audit_missing_title_localization_visibility.py"
    ]
    for relative_root in (
        "BookmarksGit/common", "BookmarksGit/events", "BookmarksGit/history",
        "BookmarksGit/map_data", "BookmarksGit/gui", "BookmarksGit/gfx",
    ):
        source_root = repo_root / relative_root
        if not source_root.is_dir():
            continue
        localization_visibility_sources.extend(
            path for path in source_root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".txt", ".gui", ".asset", ".gfx", ".info", ".csv"}
        )
    (
        localization_visibility_exists,
        localization_visibility_stale,
    ) = report_freshness(
        localization_visibility_report, localization_visibility_sources
    )
    localization_visibility_key_match = (
        expected_visibility_keys == reported_visibility_keys
    )
    localization_visibility_status = (
        "full"
        if localization_visibility_exists == "yes"
        and localization_visibility_stale == "no"
        and localization_visibility_key_match
        else (
            "stale"
            if localization_visibility_exists == "yes"
            else "not_audited"
        )
    )
    localization_visibility_applied = Counter()
    if localization_visibility_status == "full":
        localization_visibility_applied = apply_localization_visibility(
            findings,
            localization_visibility_rows,
            localization_visibility_report.relative_to(repo_root).as_posix(),
        )
    findings.extend(load_binary_map_findings(repo_root))
    runtime_findings = load_bookmark_runtime_findings(repo_root)
    findings.extend(runtime_findings)
    province_semantic_findings = load_province_history_semantic_findings(repo_root)
    findings.extend(province_semantic_findings)

    tiger_current_path = output_dir / "ck3_tiger_current.json"
    tiger_source_path = output_dir / "ck3_tiger_asil_mod.json"
    (
        tiger_comparison, tiger_summary, tiger_findings, tiger_overlaps,
    ) = analyze_tiger_reports(
        tiger_current_path, tiger_source_path, findings
    )
    current_config_delta, current_config_meta = compare_tiger_config_runs(
        "yusseter",
        tiger_current_path,
        output_dir / "ck3_tiger_unfiltered_current.json",
    )
    source_config_delta, source_config_meta = compare_tiger_config_runs(
        "asil_mod",
        tiger_source_path,
        output_dir / "ck3_tiger_unfiltered_asil_mod.json",
    )
    tiger_config_delta = current_config_delta + source_config_delta
    apply_tiger_overlap_provenance(findings, tiger_overlaps)
    tiger_classified_locations = load_tiger_classified_locations(repo_root)
    superseded_generic_classes = {
        ("map_regions", "title_reference", "undefined_title_reference"),
        (
            "source_shared_title_reference",
            "source_shared_title_reference",
            "integration_candidate",
        ),
    }
    retained_findings = []
    tiger_superseded_generic_count = 0
    for existing in findings:
        location_key = (
            normalize_tiger_path(existing.get("path", "")),
            existing.get("line", ""),
            existing.get("object", ""),
        )
        class_key = (
            existing.get("domain", ""),
            existing.get("subdomain", ""),
            existing.get("classification", ""),
        )
        if (
            class_key in superseded_generic_classes
            and location_key in tiger_classified_locations
        ):
            tiger_superseded_generic_count += 1
            continue
        retained_findings.append(existing)
    findings = retained_findings
    tiger_root_findings = load_tiger_root_cause_findings(repo_root)
    if tiger_root_findings:
        findings.extend(tiger_root_findings)
        tiger_finding_mode = "classified_root_causes"
    else:
        findings.extend(tiger_findings)
        tiger_finding_mode = "raw_current_only_fallback"
    (
        dynamic_title_findings,
        dynamic_title_raw_count,
        dynamic_title_tiger_overlap_count,
    ) = load_dynamic_title_reference_findings(
        repo_root, tiger_classified_locations
    )
    findings.extend(dynamic_title_findings)
    (
        silk_road_market_findings,
        silk_road_market_root_rows,
        silk_road_market_design_rows,
    ) = load_silk_road_market_closure(repo_root)
    findings.extend(silk_road_market_findings)
    priority_rank = {
        ("error", "strong"): "P0",
        ("error", "reasonable"): "P1",
        ("error", "weak"): "P1",
        ("warning", "strong"): "P2",
        ("warning", "reasonable"): "P3",
        ("warning", "weak"): "P3",
    }
    tiger_current_only_priority = []
    for row in tiger_comparison:
        if row["provenance"] != "yusseter_current_only":
            continue
        item = dict(row)
        item["priority"] = priority_rank.get(
            (row["severity"], row["confidence"]), "P4"
        )
        tiger_current_only_priority.append(item)
    tiger_current_only_priority.sort(
        key=lambda row: (
            row["priority"], row["key"], row["path"],
            int(row["line"]) if row["line"].isdigit() else 0,
        )
    )

    map_findings = [
        row for row in findings
        if row["domain"] in {"map_identity", "map_objects", "map_regions", "landed_titles"}
    ]
    history_findings = [
        row for row in findings
        if row["domain"] in {"province_history", "title_history", "structure"}
    ]
    localization_findings = [
        row for row in findings if row["domain"] == "localization"
    ]

    semantic_report = (
        Path(SEMANTIC_PATH) / "repo_semantic_compatibility_findings.csv"
    ).as_posix()
    closure_report = (
        Path(OUTPUT_PATH) / "repo_integration_closure_findings.csv"
    ).as_posix()
    locator_report = repo_root / (
        ".codex/works/analysis/generated/map_object_locator_audit/"
        "locator_position_audit.csv"
    )
    locator_sources = [definition_path, repo_root / "BookmarksGit/map_data/provinces.png"]
    locator_sources.extend(
        (repo_root / "BookmarksGit/gfx/map/map_object_data").glob("*.txt")
    )
    locator_exists, locator_stale = report_freshness(
        locator_report, list(locator_sources)
    )
    locator_status = (
        "stale" if locator_stale == "yes"
        else ("full" if locator_exists == "yes" else "not_audited")
    )

    binary_map_report = repo_root / (
        ".codex/works/analysis/generated/repo_integration_closure/"
        "map_definition_pixel_audit/binary_map_findings.csv"
    )
    binary_map_sources = [
        definition_path,
        repo_root / "BookmarksGit/map_data/provinces.png",
        repo_root / "BookmarksGit/map_data/default.map",
        repo_root
        / ".codex/works/pipeline_inputs/province_relations/province_relation_baseline.csv",
    ]
    binary_map_sources.extend(
        (repo_root / "BookmarksGit/map_data/geographical_regions").rglob("*.txt")
    )
    binary_map_exists, binary_map_stale = report_freshness(
        binary_map_report, list(binary_map_sources)
    )
    binary_map_status = (
        "stale" if binary_map_stale == "yes"
        else ("full" if binary_map_exists == "yes" else "not_audited")
    )

    runtime_dir = repo_root / RUNTIME_PATH
    runtime_report = runtime_dir / "bookmark_runtime_static_findings_compact.csv"
    title_holder_provenance_report = (
        runtime_dir / "title_holder_reference_provenance.csv"
    )
    runtime_dates_report = runtime_dir / "bookmark_dates.csv"
    runtime_featured_report = runtime_dir / "bookmark_featured_character_state.csv"
    runtime_state_report = runtime_dir / "county_effective_state_by_bookmark.csv"
    runtime_current_sources = [repo_root / LANDED_PATH]
    for relative in (
        "BookmarksGit/common/bookmarks",
        "BookmarksGit/history/titles",
        "BookmarksGit/history/characters",
    ):
        runtime_current_sources.extend((repo_root / relative).rglob("*.txt"))
    runtime_source_sources = [
        asil_mod_repo / "BookmarksGit/common/landed_titles/00_landed_titles.txt"
    ]
    for relative in (
        "BookmarksGit/common/bookmarks",
        "BookmarksGit/history/titles",
        "BookmarksGit/history/characters",
    ):
        runtime_source_sources.extend((asil_mod_repo / relative).rglob("*.txt"))
    runtime_sources = runtime_current_sources + runtime_source_sources + [
        repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv"
    ]
    runtime_exists, runtime_stale = report_freshness(runtime_report, runtime_sources)
    runtime_status = (
        "stale" if runtime_stale == "yes"
        else ("partial" if runtime_exists == "yes" else "not_audited")
    )
    title_holder_exists, title_holder_stale = report_freshness(
        title_holder_provenance_report, runtime_sources
    )
    title_holder_status = (
        "stale" if title_holder_stale == "yes"
        else ("full" if title_holder_exists == "yes" else "not_audited")
    )
    runtime_dates = read_csv(runtime_dates_report)
    runtime_state_rows = read_csv(runtime_state_report)
    runtime_date_count = len({row.get("start_date", "") for row in runtime_dates})
    runtime_county_count = len({row.get("title_id", "") for row in runtime_state_rows})
    runtime_featured_count = len(read_csv(runtime_featured_report))

    province_semantics_dir = repo_root / PROVINCE_SEMANTICS_PATH
    province_semantics_report = (
        province_semantics_dir / "province_history_semantic_findings_compact.csv"
    )
    province_semantics_state_report = (
        province_semantics_dir / "county_capital_state_by_bookmark.csv"
    )
    province_semantics_sources = [repo_root / LANDED_PATH]
    for root, relatives in (
        (repo_root / "BookmarksGit", (
            "common/bookmarks", "common/culture/cultures",
            "common/religion/religion_types", "common/holdings",
            "history/provinces", "history/province_mapping",
        )),
        (asil_mod_repo / "BookmarksGit", (
            "history/provinces", "history/province_mapping",
        )),
        (vanilla_root, (
            "history/provinces", "history/province_mapping",
        )),
    ):
        for relative in relatives:
            directory = root / relative
            if directory.is_dir():
                province_semantics_sources.extend(directory.rglob("*.txt"))
    province_semantics_exists, province_semantics_stale = report_freshness(
        province_semantics_report, province_semantics_sources
    )
    province_semantics_status = (
        "stale" if province_semantics_stale == "yes"
        else ("full" if province_semantics_exists == "yes" else "not_audited")
    )
    province_semantics_states = read_csv(province_semantics_state_report)
    province_semantics_date_count = len({
        row.get("bookmark_date", "") for row in province_semantics_states
    })
    province_semantics_capital_count = len({
        row.get("province_id", "") for row in province_semantics_states
    })

    mpe_report = repo_root / (
        ".codex/works/analysis/generated/mpe_import_add_1/closure_audit/"
        "mpe_add_1_current_closure_findings.csv"
    )
    mpe_scope_report = repo_root / (
        ".codex/works/analysis/generated/mpe_import_add_1/closure_audit/"
        "mpe_add_1_current_scope.csv"
    )
    mpe_sources = [
        repo_root / LANDED_PATH,
        definition_path,
        repo_root / "BookmarksGit/map_data/default.map",
        repo_root / "BookmarksGit/map_data/provinces.png",
    ]
    mpe_sources.extend((repo_root / "BookmarksGit/history").rglob("*.txt"))
    mpe_sources.extend(
        (repo_root / "BookmarksGit/localization").rglob("*.yml")
    )
    mpe_sources.extend(
        (repo_root / "BookmarksGit/common/province_terrain").rglob("*.txt")
    )
    mpe_sources.extend(
        (repo_root / "BookmarksGit/gfx/map/map_object_data").rglob("*.txt")
    )
    mpe_exists, mpe_stale = report_freshness(mpe_report, list(mpe_sources))
    mpe_status = (
        "stale" if mpe_stale == "yes"
        else ("full" if mpe_exists == "yes" else "not_audited")
    )
    mpe_scope = read_csv(mpe_scope_report)
    for row in read_csv(mpe_report):
        if row.get("covered_by_repo_closure") == "yes":
            continue
        findings.append(row)
    tiger_sources = [
        path for path in (repo_root / "BookmarksGit").rglob("*")
        if path.is_file() and ".codex" not in path.parts
    ]
    tiger_exists, tiger_stale = report_freshness(
        tiger_current_path, tiger_sources
    )
    tiger_status = (
        "stale" if tiger_stale == "yes"
        else ("full" if tiger_exists == "yes" and tiger_source_path.exists()
              else "not_audited")
    )
    tiger_classification_report = (
        repo_root / TIGER_CLASSIFICATION_PATH
        / "ck3_tiger_current_only_root_causes.csv"
    )
    tiger_classification_sources = [
        repo_root / ".codex/works/tools/classify_ck3_tiger_current_only.py",
        repo_root / TIGER_CURRENT_PRIORITY_PATH,
        tiger_current_path,
        repo_root / LANDED_PATH,
        repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv",
        repo_root / (
            ".codex/works/analysis/generated/landed_title_source_identity/"
            "landed_title_source_identity_audit.csv"
        ),
        repo_root / (
            ".codex/works/analysis/generated/repo_semantic_compatibility/"
            "source_shared_title_reference_candidates.csv"
        ),
        repo_root / (
            ".codex/works/analysis/generated/repo_integration_closure/"
            "localization_requirements.csv"
        ),
        repo_root / (
            ".codex/works/analysis/generated/repo_integration_closure/"
            "bookmark_runtime_static/bookmark_runtime_static_findings_compact.csv"
        ),
        repo_root / (
            ".codex/works/analysis/generated/repo_semantic_compatibility/"
            "upstream_since_last_merge.csv"
        ),
    ]
    tiger_classification_exists, tiger_classification_stale = report_freshness(
        tiger_classification_report, tiger_classification_sources
    )
    tiger_classification_status = (
        "stale" if tiger_classification_stale == "yes"
        else ("full" if tiger_classification_exists == "yes" else "not_audited")
    )
    dynamic_title_report = (
        repo_root / DYNAMIC_TITLE_REFERENCE_PATH
        / "dynamic_title_reference_findings.csv"
    )
    dynamic_title_inventory_report = (
        repo_root / DYNAMIC_TITLE_REFERENCE_PATH
        / "dynamic_title_reference_inventory.csv"
    )
    dynamic_title_sources = [
        repo_root / ".codex/works/tools/audit_dynamic_title_references.py",
        repo_root / LANDED_PATH,
        repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv",
    ] + [
        repo_root / row["path"] for row in localization_files
        if row.get("source") == "mod" and row.get("path")
    ]
    dynamic_title_exists, dynamic_title_stale = report_freshness(
        dynamic_title_report, dynamic_title_sources
    )
    dynamic_title_status = (
        "stale" if dynamic_title_stale == "yes"
        else ("full" if dynamic_title_exists == "yes" else "not_audited")
    )
    dynamic_title_inventory_count = len(read_csv(dynamic_title_inventory_report))

    external_closure_links, external_closure_stats = build_external_closure_links(
        repo_root,
        findings,
        silk_road_market_root_rows,
    )

    region_closure_root = repo_root / GEOGRAPHICAL_REGION_CLOSURE_PATH
    region_closure_report = region_closure_root / "geographical_region_findings.csv"
    region_closure_sources = [
        repo_root / ".codex/works/tools/audit_geographical_region_closure.py",
        repo_root / LANDED_PATH,
        definition_path,
        repo_root / "BookmarksGit/map_data/provinces.png",
    ]
    region_closure_sources.extend(
        sorted((repo_root / "BookmarksGit/map_data/geographical_regions").rglob("*.txt"))
    )
    region_closure_exists, region_closure_stale = report_freshness(
        region_closure_report, region_closure_sources
    )
    region_link_complete = (
        external_closure_stats["region_root_count"] > 0
        and external_closure_stats["region_exact_root_count"]
        + external_closure_stats["region_external_root_count"]
        == external_closure_stats["region_root_count"]
    )
    region_closure_status = (
        "full"
        if region_closure_exists == "yes"
        and region_closure_stale == "no"
        and region_link_complete
        else (
            "stale" if region_closure_exists == "yes" else "not_audited"
        )
    )

    market_closure_root = repo_root / SILK_ROAD_MARKET_CLOSURE_PATH
    market_closure_report = market_closure_root / "silk_road_market_root_causes.csv"
    market_fix_design_report = market_closure_root / "silk_road_market_fix_design.csv"
    market_runtime_report = market_closure_root / "runtime_smoke_test_checklist.csv"
    market_closure_sources = [
        repo_root / ".codex/works/tools/audit_silk_road_market_closure.py",
        repo_root / "BookmarksGit/common/situation/situations/tgp_silk_road.txt",
        repo_root / (
            "BookmarksGit/common/decisions/dlc_decisions/tgp/"
            "tgp_silk_road_decisions.txt"
        ),
        definition_path,
        repo_root / "BookmarksGit/map_data/provinces.png",
        repo_root / (
            ".codex/works/analysis/generated/province_relation_mapping/"
            "current_state_refresh/province_relation_master.csv"
        ),
        locator_report,
    ]
    for relative in (
        "BookmarksGit/common/buildings",
        "BookmarksGit/history/provinces",
        "BookmarksGit/localization",
        "BookmarksGit/map_data/geographical_regions",
    ):
        source_dir = repo_root / relative
        if source_dir.is_dir():
            market_closure_sources.extend(
                sorted(path for path in source_dir.rglob("*") if path.is_file())
            )
    market_closure_exists, market_closure_stale = report_freshness(
        market_closure_report, market_closure_sources
    )
    market_root_keys = {
        row.get("root_cause_key", "") for row in silk_road_market_root_rows
        if row.get("root_cause_key")
    }
    market_blocker_keys = {
        row.get("root_cause_key", "") for row in silk_road_market_root_rows
        if row.get("severity") == "blocker"
    }
    market_design_keys = {
        row.get("linked_root_cause_key", "") for row in silk_road_market_design_rows
        if row.get("linked_root_cause_key")
    }
    market_design_complete = (
        market_blocker_keys == market_design_keys
        and len(silk_road_market_design_rows) == len(market_blocker_keys)
        and all(row.get("auto_apply") == "no" for row in silk_road_market_design_rows)
    )
    market_materialization_complete = (
        external_closure_stats["market_root_count"] == len(market_root_keys)
        and external_closure_stats["market_materialized_root_count"]
        == len(market_root_keys)
    )
    market_closure_status = (
        "full"
        if market_closure_exists == "yes"
        and market_closure_stale == "no"
        and market_design_complete
        and market_materialization_complete
        else (
            "stale" if market_closure_exists == "yes" else "not_audited"
        )
    )

    blocker_root_causes = build_blocker_root_causes(repo_root, findings)
    upstream_character_report = (
        repo_root / UPSTREAM_CHARACTER_ROOT_PATH
        / "upstream_integration_character_root_audit.csv"
    )
    upstream_character_rows = read_csv(upstream_character_report)
    asil_tiger_undefined_characters: set[str] = set()
    if tiger_source_path.is_file() and tiger_source_path.stat().st_size:
        source_tiger_reports = json.loads(
            tiger_source_path.read_text(encoding="utf-8-sig")
        )
        undefined_character_pattern = re.compile(
            r"^character ([A-Za-z0-9_.:\-]+) not defined in history/characters/$"
        )
        for report in source_tiger_reports:
            if report.get("key") != "missing-item":
                continue
            match = undefined_character_pattern.fullmatch(
                report.get("message") or ""
            )
            if match:
                asil_tiger_undefined_characters.add(match.group(1))
    expected_upstream_character_keys = {
        (row.get("classification", ""), row.get("primary_object", ""))
        for row in blocker_root_causes
        if row.get("subsystem") in {
            "character_title_history", "bookmark_runtime"
        }
        and (
            row.get("provenance") == "upstream_integration"
            or (
                row.get("classification")
                == "yusseter_current_only_undefined_holder"
                and row.get("primary_object")
                in asil_tiger_undefined_characters
            )
        )
    }
    reported_upstream_character_keys = {
        (
            row.get("root_classification", ""),
            row.get("character_id", ""),
        )
        for row in upstream_character_rows
        if row.get("root_classification") and row.get("character_id")
    }
    upstream_character_sources = [
        repo_root
        / ".codex/works/tools/classify_upstream_integration_character_roots.py",
        title_holder_provenance_report,
        runtime_report,
        tiger_source_path,
    ]
    (
        upstream_character_exists,
        upstream_character_stale,
    ) = report_freshness(upstream_character_report, upstream_character_sources)
    yusseter_revision = git_revision(repo_root)
    current_asil_revision = git_revision(asil_mod_repo)
    upstream_character_revision_match = bool(upstream_character_rows) and all(
        row.get("yusseter_revision") == yusseter_revision
        and row.get("current_asil_revision") == current_asil_revision
        and row.get("baseline_revision")
        and row.get("merged_source_revision")
        for row in upstream_character_rows
    )
    upstream_character_key_match = (
        expected_upstream_character_keys == reported_upstream_character_keys
    )
    upstream_character_status = (
        "full"
        if upstream_character_exists == "yes"
        and upstream_character_stale == "no"
        and upstream_character_key_match
        and upstream_character_revision_match
        and title_holder_status == "full"
        and runtime_stale == "no"
        else (
            "stale"
            if upstream_character_exists == "yes"
            else "not_audited"
        )
    )
    upstream_character_applied: Counter[str] = Counter()
    if upstream_character_status == "full":
        upstream_character_applied = apply_upstream_character_root_classification(
            blocker_root_causes,
            upstream_character_rows,
            upstream_character_report.relative_to(repo_root).as_posix(),
        )
    upstream_character_raw_count = sum(
        int(row.get("raw_finding_count") or 0)
        for row in upstream_character_rows
    )

    local_mixed_character_report = (
        repo_root / LOCAL_MIXED_CHARACTER_ROOT_PATH
        / "local_mixed_character_root_audit.csv"
    )
    local_mixed_character_rows = read_csv(local_mixed_character_report)
    expected_local_mixed_character_keys = {
        (row.get("classification", ""), row.get("primary_object", ""))
        for row in blocker_root_causes
        if row.get("provenance") in {
            "preexisting_yusseter", "mixed_provenance"
        }
        and row.get("subsystem") in {
            "character_title_history", "bookmark_runtime"
        }
    }
    reported_local_mixed_character_keys = {
        (
            row.get("root_classification", ""),
            row.get("character_id", ""),
        )
        for row in local_mixed_character_rows
        if row.get("root_classification") and row.get("character_id")
    }
    local_mixed_character_sources = [
        repo_root
        / ".codex/works/tools/classify_local_mixed_character_roots.py",
        title_holder_provenance_report,
        runtime_report,
    ]
    (
        local_mixed_character_exists,
        local_mixed_character_stale,
    ) = report_freshness(
        local_mixed_character_report, local_mixed_character_sources
    )
    local_mixed_character_revision_match = bool(
        local_mixed_character_rows
    ) and all(
        row.get("yusseter_revision") == yusseter_revision
        and row.get("current_asil_revision") == current_asil_revision
        and row.get("baseline_revision")
        and row.get("merged_source_revision")
        for row in local_mixed_character_rows
    )
    local_mixed_character_key_match = (
        expected_local_mixed_character_keys
        == reported_local_mixed_character_keys
    )
    local_mixed_character_status = (
        "full"
        if local_mixed_character_exists == "yes"
        and local_mixed_character_stale == "no"
        and local_mixed_character_key_match
        and local_mixed_character_revision_match
        and title_holder_status == "full"
        and runtime_stale == "no"
        else (
            "stale"
            if local_mixed_character_exists == "yes"
            else "not_audited"
        )
    )
    local_mixed_character_applied: Counter[str] = Counter()
    if local_mixed_character_status == "full":
        local_mixed_character_applied = (
            apply_upstream_character_root_classification(
                blocker_root_causes,
                local_mixed_character_rows,
                local_mixed_character_report.relative_to(repo_root).as_posix(),
            )
        )
    local_mixed_character_raw_count = sum(
        int(row.get("raw_finding_count") or 0)
        for row in local_mixed_character_rows
    )

    shared_asil_character_report = (
        repo_root / SHARED_ASIL_CHARACTER_ROOT_PATH
        / "shared_asil_mod_character_root_audit.csv"
    )
    shared_asil_character_rows = read_csv(shared_asil_character_report)
    expected_shared_asil_character_keys = {
        (row.get("classification", ""), row.get("primary_object", ""))
        for row in blocker_root_causes
        if row.get("provenance") == "shared_asil_mod_baseline"
        and row.get("subsystem") in {
            "character_title_history", "bookmark_runtime"
        }
    }
    reported_shared_asil_character_keys = {
        (
            row.get("root_classification", ""),
            row.get("character_id", ""),
        )
        for row in shared_asil_character_rows
        if row.get("root_classification") and row.get("character_id")
    }
    shared_asil_character_sources = [
        repo_root
        / ".codex/works/tools/classify_shared_asil_mod_character_roots.py",
        repo_root
        / ".codex/works/tools/classify_local_mixed_character_roots.py",
        title_holder_provenance_report,
        runtime_report,
    ]
    (
        shared_asil_character_exists,
        shared_asil_character_stale,
    ) = report_freshness(
        shared_asil_character_report, shared_asil_character_sources
    )
    shared_asil_character_revision_match = bool(
        shared_asil_character_rows
    ) and all(
        row.get("yusseter_revision") == yusseter_revision
        and row.get("current_asil_revision") == current_asil_revision
        and row.get("baseline_revision")
        and row.get("merged_source_revision")
        for row in shared_asil_character_rows
    )
    shared_asil_character_key_match = (
        expected_shared_asil_character_keys
        == reported_shared_asil_character_keys
    )
    shared_asil_character_status = (
        "full"
        if shared_asil_character_exists == "yes"
        and shared_asil_character_stale == "no"
        and shared_asil_character_key_match
        and shared_asil_character_revision_match
        and title_holder_status == "full"
        and runtime_stale == "no"
        else (
            "stale"
            if shared_asil_character_exists == "yes"
            else "not_audited"
        )
    )
    shared_asil_character_applied: Counter[str] = Counter()
    if shared_asil_character_status == "full":
        shared_asil_character_applied = (
            apply_upstream_character_root_classification(
                blocker_root_causes,
                shared_asil_character_rows,
                shared_asil_character_report.relative_to(repo_root).as_posix(),
            )
        )
    shared_asil_character_raw_count = sum(
        int(row.get("raw_finding_count") or 0)
        for row in shared_asil_character_rows
    )

    non_character_report = (
        repo_root / NON_CHARACTER_ROOT_PATH
        / "non_character_blocker_root_audit.csv"
    )
    non_character_rows = read_csv(non_character_report)
    character_subsystems = {"character_title_history", "bookmark_runtime"}
    expected_non_character_keys = {
        (row.get("classification", ""), row.get("primary_object", ""))
        for row in blocker_root_causes
        if row.get("subsystem") not in character_subsystems
    }
    reported_non_character_keys = {
        (
            row.get("root_classification", ""),
            row.get("primary_object", ""),
        )
        for row in non_character_rows
        if row.get("root_classification") and row.get("primary_object")
    }
    non_character_sources = [
        repo_root / ".codex/works/tools/classify_non_character_blocker_roots.py",
        repo_root / ".codex/works/tools/audit_repo_integration_closure.py",
        repo_root / ".codex/works/tools/audit_map_definition_pixels.py",
        repo_root / ".codex/works/tools/audit_mpe_add_1_closure_current.py",
        repo_root / ".codex/works/tools/audit_missing_title_localization_visibility.py",
        repo_root / ".codex/works/tools/audit_province_history_bookmark_semantics.py",
        repo_root / ".codex/works/tools/audit_silk_road_market_closure.py",
        market_fix_design_report,
        repo_root / LANDED_PATH,
        repo_root / DEFINITION_PATH,
        repo_root / "BookmarksGit/map_data/provinces.png",
        repo_root / "BookmarksGit/map_data/default.map",
        repo_root / "BookmarksGit/history/provinces/00_MB_PROVINCES.txt",
        repo_root / "BookmarksGit/history/provinces/00_yb_MPE_PROVINCES.txt",
        repo_root
        / "BookmarksGit/localization/replace/english/bookmark/MB_Bookmarks_l_english.yml",
        repo_root
        / "BookmarksGit/localization/replace/english/z_MB_titles_l_english.yml",
    ]
    non_character_sources.extend(
        sorted((repo_root / "BookmarksGit/common/province_terrain").rglob("*.txt"))
    )
    non_character_sources.extend(
        sorted((repo_root / "BookmarksGit/gfx/map/map_object_data").glob("*.txt"))
    )
    (
        non_character_exists,
        non_character_stale,
    ) = report_freshness(non_character_report, non_character_sources)
    non_character_revision_match = bool(non_character_rows) and all(
        row.get("yusseter_revision") == yusseter_revision
        and row.get("current_asil_revision") == current_asil_revision
        and row.get("baseline_revision")
        and row.get("merged_source_revision")
        for row in non_character_rows
    )
    non_character_key_match = (
        expected_non_character_keys == reported_non_character_keys
    )
    non_character_status = (
        "full"
        if non_character_exists == "yes"
        and non_character_stale == "no"
        and non_character_key_match
        and non_character_revision_match
        and binary_map_status == "full"
        and province_semantics_status == "full"
        and localization_visibility_status == "full"
        and mpe_status == "full"
        and market_closure_status == "full"
        else (
            "stale" if non_character_exists == "yes" else "not_audited"
        )
    )
    non_character_applied: Counter[str] = Counter()
    if non_character_status == "full":
        non_character_applied = apply_non_character_root_classification(
            blocker_root_causes,
            non_character_rows,
            non_character_report.relative_to(repo_root).as_posix(),
        )
    non_character_raw_count = sum(
        int(row.get("raw_finding_count") or 0)
        for row in non_character_rows
    )

    tiger_p0_report = (
        repo_root / TIGER_P0_TRIAGE_PATH / "tiger_p0_root_triage.csv"
    )
    tiger_p0_live_report = (
        repo_root / TIGER_P0_TRIAGE_PATH
        / "tiger_p0_verified_live_error_roots.csv"
    )
    tiger_p0_barony_report = (
        repo_root / TIGER_P0_TRIAGE_PATH
        / "tiger_p0_undefined_barony_identity_candidates.csv"
    )
    tiger_p0_higher_title_report = (
        repo_root / TIGER_P0_TRIAGE_PATH
        / "tiger_p0_undefined_higher_title_identity_candidates.csv"
    )
    tiger_p0_higher_no_candidate_report = (
        repo_root / TIGER_P0_TRIAGE_PATH
        / "tiger_p0_undefined_higher_title_no_candidate_context.csv"
    )
    tiger_p0_rows = read_csv(tiger_p0_report)
    tiger_p0_live_rows = read_csv(tiger_p0_live_report)
    tiger_p0_barony_rows = read_csv(tiger_p0_barony_report)
    tiger_p0_higher_title_rows = read_csv(tiger_p0_higher_title_report)
    tiger_p0_higher_no_candidate_rows = read_csv(
        tiger_p0_higher_no_candidate_report
    )
    tiger_classification_rows = read_csv(tiger_classification_report)

    relation_refresh_dir = (
        repo_root
        / ".codex/works/analysis/generated/province_relation_mapping/"
        "current_state_refresh"
    )
    relation_refresh_report = relation_refresh_dir / "province_relation_master.csv"
    relation_refresh_coverage_report = (
        relation_refresh_dir / "province_relation_coverage.csv"
    )
    relation_refresh_manual_report = (
        relation_refresh_dir / "province_relation_manual_review.csv"
    )
    relation_refresh_preview_report = (
        relation_refresh_dir / "province_relation_split_merge_preview.csv"
    )
    relation_refresh_summary = relation_refresh_dir / "province_relation_summary.md"
    relation_refresh_manifest = (
        relation_refresh_dir / "province_relation_input_manifest.csv"
    )
    relation_refresh_outputs = [
        relation_refresh_report,
        relation_refresh_coverage_report,
        relation_refresh_manual_report,
        relation_refresh_preview_report,
        relation_refresh_summary,
        relation_refresh_manifest,
    ]
    relation_refresh_rows = read_csv(relation_refresh_report)
    relation_refresh_coverage_rows = read_csv(relation_refresh_coverage_report)
    relation_refresh_manual_rows = read_csv(relation_refresh_manual_report)
    relation_refresh_manifest_rows = read_csv(relation_refresh_manifest)
    relation_manifest_by_role = {
        row.get("role", ""): row
        for row in relation_refresh_manifest_rows
        if row.get("role")
    }
    required_relation_roles = {
        "source_image",
        "target_image",
        "source_definition",
        "target_definition",
        "target_tracking",
        "source_landed_titles",
        "existing_manual_master",
    }
    relation_manifest_role_match = (
        set(relation_manifest_by_role) == required_relation_roles
    )
    relation_manifest_hash_match = relation_manifest_role_match and all(
        Path(row.get("path", "")).is_file()
        and file_sha256(Path(row["path"])) == row.get("sha256", "")
        for row in relation_refresh_manifest_rows
    )
    relation_manifest_paths = [
        Path(row["path"])
        for row in relation_refresh_manifest_rows
        if row.get("path") and Path(row["path"]).is_file()
    ]
    relation_refresh_sources = [
        repo_root / ".codex/works/tools/build_province_relation_master.py",
        *relation_manifest_paths,
    ]
    relation_refresh_freshness = [
        report_freshness(report, relation_refresh_sources)
        for report in relation_refresh_outputs
    ]
    relation_refresh_exists = (
        "yes"
        if all(value[0] == "yes" for value in relation_refresh_freshness)
        else "no"
    )
    relation_refresh_stale = (
        "yes"
        if any(value[1] == "yes" for value in relation_refresh_freshness)
        else "no"
    )
    target_tracking_manifest_row = relation_manifest_by_role.get("target_tracking", {})
    target_image_manifest_row = relation_manifest_by_role.get("target_image", {})
    target_tracking_path = Path(target_tracking_manifest_row.get("path", ""))
    target_image_path = Path(target_image_manifest_row.get("path", ""))
    relation_target_tracking_stale = (
        target_tracking_path.is_file()
        and target_image_path.is_file()
        and target_tracking_path.stat().st_mtime < target_image_path.stat().st_mtime
    )
    canonical_manifest_row = relation_manifest_by_role.get(
        "existing_manual_master", {}
    )
    canonical_relation_path = Path(canonical_manifest_row.get("path", ""))
    relation_canonical_unchanged = (
        canonical_relation_path.is_file()
        and file_sha256(canonical_relation_path)
        == canonical_manifest_row.get("sha256", "")
    )
    relation_status_whitespace_count = sum(
        row.get("status", "") != row.get("status", "").strip()
        for row in relation_refresh_rows
    )
    relation_refresh_consistent = (
        bool(relation_refresh_rows)
        and len(relation_refresh_rows) == len(relation_refresh_coverage_rows)
        and len(relation_refresh_manual_rows)
        == sum(
            row.get("status") != "mapped"
            for row in relation_refresh_rows
        )
        and relation_status_whitespace_count == 0
    )
    relation_refresh_status = (
        "partial"
        if relation_refresh_exists == "yes"
        and relation_refresh_stale == "no"
        and relation_manifest_hash_match
        and relation_canonical_unchanged
        and relation_refresh_consistent
        and relation_target_tracking_stale
        else (
            "full"
            if relation_refresh_exists == "yes"
            and relation_refresh_stale == "no"
            and relation_manifest_hash_match
            and relation_canonical_unchanged
            and relation_refresh_consistent
            else (
                "stale" if relation_refresh_exists == "yes" else "not_audited"
            )
        )
    )
    expected_tiger_p0_keys = {
        (row.get("root_cause_id", ""), row.get("classification", ""))
        for row in tiger_classification_rows
        if row.get("action_priority") == "P0"
    }
    reported_tiger_p0_keys = {
        (row.get("root_cause_id", ""), row.get("root_classification", ""))
        for row in tiger_p0_rows
        if row.get("root_cause_id") and row.get("root_classification")
    }
    expected_tiger_p0_live_ids = {
        row.get("root_cause_id", "")
        for row in tiger_p0_rows
        if row.get("issue_status") == "verified_live_error"
    }
    reported_tiger_p0_live_ids = {
        root_id
        for row in tiger_p0_live_rows
        for root_id in row.get("p0_root_ids", "").split(" | ")
        if root_id
    }
    expected_tiger_p0_barony_ids = {
        row.get("root_cause_id", "")
        for row in tiger_p0_rows
        if row.get("issue_status") == "verified_undefined_title_reference"
        and row.get("source_object", "").startswith("b_")
    }
    reported_tiger_p0_barony_ids = {
        row.get("root_cause_id", "")
        for row in tiger_p0_barony_rows
        if row.get("root_cause_id")
    }
    expected_tiger_p0_higher_title_ids = {
        row.get("root_cause_id", "")
        for row in tiger_p0_rows
        if row.get("issue_status") == "verified_undefined_title_reference"
        and row.get("source_object", "").startswith(("c_", "d_", "k_"))
    }
    reported_tiger_p0_higher_title_ids = {
        row.get("root_cause_id", "")
        for row in tiger_p0_higher_title_rows
        if row.get("root_cause_id")
    }
    expected_tiger_p0_higher_no_candidate_ids = {
        row.get("root_cause_id", "")
        for row in tiger_p0_higher_title_rows
        if row.get("candidate_status")
        in TIGER_P0_HIGHER_NO_CANDIDATE_STATUSES
    }
    reported_tiger_p0_higher_no_candidate_ids = {
        row.get("root_cause_id", "")
        for row in tiger_p0_higher_no_candidate_rows
        if row.get("root_cause_id")
    }
    title_relation_report = repo_root / TITLE_RELATION_PATH
    tiger_p0_reference_sources = sorted({
        repo_root / path
        for row in tiger_p0_higher_title_rows
        for path in row.get("reference_paths", "").split(" | ")
        if path
    })
    tiger_p0_sources = [
        repo_root / ".codex/works/tools/classify_tiger_p0_roots.py",
        tiger_classification_report,
    ]
    tiger_p0_freshness = [
        report_freshness(report, tiger_p0_sources)
        for report in [tiger_p0_report, tiger_p0_live_report]
    ]
    tiger_p0_freshness.append(report_freshness(
        tiger_p0_barony_report,
        [
            *tiger_p0_sources,
            relation_refresh_report,
            canonical_relation_path,
            target_tracking_path,
            target_image_path,
            Path(tiger_p0_barony_rows[0].get("source_landed_file", ""))
            if tiger_p0_barony_rows else Path(),
            repo_root / "BookmarksGit/common/landed_titles/00_landed_titles.txt",
        ],
    ))
    tiger_p0_freshness.append(report_freshness(
        tiger_p0_higher_title_report,
        [
            *tiger_p0_sources,
            relation_refresh_report,
            canonical_relation_path,
            target_tracking_path,
            target_image_path,
            title_relation_report,
            Path(tiger_p0_higher_title_rows[0].get("source_landed_file", ""))
            if tiger_p0_higher_title_rows else Path(),
            repo_root / "BookmarksGit/common/landed_titles/00_landed_titles.txt",
            *tiger_p0_reference_sources,
        ],
    ))
    tiger_p0_freshness.append(report_freshness(
        tiger_p0_higher_no_candidate_report,
        [
            *tiger_p0_sources,
            tiger_p0_higher_title_report,
            relation_refresh_report,
            title_relation_report,
            *tiger_p0_reference_sources,
        ],
    ))
    tiger_p0_exists = (
        "yes" if all(value[0] == "yes" for value in tiger_p0_freshness) else "no"
    )
    tiger_p0_stale = (
        "yes" if any(value[1] == "yes" for value in tiger_p0_freshness) else "no"
    )
    tiger_p0_revision_match = (
        bool(tiger_p0_rows)
        and (
            not expected_tiger_p0_live_ids
            or bool(tiger_p0_live_rows)
        )
        and bool(tiger_p0_barony_rows)
        and bool(tiger_p0_higher_title_rows)
        and bool(tiger_p0_higher_no_candidate_rows)
        and all(
        row.get("yusseter_revision") == yusseter_revision
        and row.get("current_asil_revision") == current_asil_revision
        and row.get("premerge_revision")
        for row in (
            tiger_p0_rows
            + tiger_p0_live_rows
            + tiger_p0_barony_rows
            + tiger_p0_higher_title_rows
            + tiger_p0_higher_no_candidate_rows
        )
        )
    )
    tiger_p0_key_match = expected_tiger_p0_keys == reported_tiger_p0_keys
    tiger_p0_live_key_match = (
        expected_tiger_p0_live_ids == reported_tiger_p0_live_ids
    )
    tiger_p0_barony_key_match = (
        expected_tiger_p0_barony_ids == reported_tiger_p0_barony_ids
        and len(tiger_p0_barony_rows) == len(expected_tiger_p0_barony_ids)
    )
    tiger_p0_higher_title_key_match = (
        expected_tiger_p0_higher_title_ids
        == reported_tiger_p0_higher_title_ids
        and len(tiger_p0_higher_title_rows)
        == len(expected_tiger_p0_higher_title_ids)
    )
    tiger_p0_higher_no_candidate_key_match = (
        expected_tiger_p0_higher_no_candidate_ids
        == reported_tiger_p0_higher_no_candidate_ids
        and len(tiger_p0_higher_no_candidate_rows)
        == len(expected_tiger_p0_higher_no_candidate_ids)
    )
    tiger_p0_live_complete = (
        not expected_tiger_p0_live_ids
        and not tiger_p0_live_rows
    ) or (
        bool(tiger_p0_live_rows)
        and all(
            row.get("independent_root_id")
            and row.get("root_family")
            and row.get("primary_object")
            and row.get("integration_responsibility")
            and row.get("recommendation")
            and row.get("auto_apply") == "no"
            for row in tiger_p0_live_rows
        )
    )
    tiger_p0_barony_complete = bool(tiger_p0_barony_rows) and all(
        row.get("source_title", "").startswith("b_")
        and row.get("source_parent")
        and row.get("source_path")
        and row.get("source_province_ids")
        and row.get("relation_target_province_id")
        and row.get("relation_classification")
        and row.get("relation_confidence")
        and row.get("candidate_status")
        and row.get("confidence_ceiling")
        and row.get("recommendation")
        and row.get("auto_apply") == "no"
        and Path(row.get("relation_report", "")).resolve()
        == relation_refresh_report.resolve()
        and row.get("target_tracking_stale")
        == ("yes" if relation_target_tracking_stale else "no")
        for row in tiger_p0_barony_rows
    )
    tiger_p0_higher_title_complete = bool(tiger_p0_higher_title_rows) and all(
        row.get("root_cause_id")
        and row.get("source_title", "").startswith(("c_", "d_", "k_"))
        and row.get("source_tier") in {"c_", "d_", "k_"}
        and row.get("source_parent")
        and row.get("source_path")
        and row.get("source_landed_file")
        and row.get("source_landed_line")
        and row.get("candidate_status")
        and row.get("candidate_footprint_basis")
        and row.get("source_capital_identity_status")
        and row.get("relation_evidence_quality")
        and row.get("confidence_ceiling")
        and row.get("usage_context_family")
        and row.get("usage_context_decision")
        and row.get("context_recommendation")
        and row.get("reference_context_status") == "complete"
        and row.get("reference_context_location_count")
        and row.get("reference_context_readable_count")
        and row.get("reference_context_scopes")
        and row.get("reference_context_excerpt")
        and row.get("context_location_basis")
        and row.get("context_location_candidate_status")
        and row.get("identity_descendant_candidate_status")
        and row.get("identity_descendant_mapped_source_count")
        and row.get("identity_geometry_comparison")
        and row.get("preferred_candidate_present_near_reference")
        in {"yes", "no", "not_applicable"}
        and row.get("recommendation")
        and row.get("source_report")
        and row.get("auto_apply") == "no"
        and (
            row.get("candidate_status")
            == "source_title_has_no_descendant_province_footprint"
            or row.get("candidate_footprint_province_ids")
        )
        and (
            not row.get("top_candidate_title")
            or row.get("top_candidate_title", "").startswith(
                row.get("source_tier", "")
            )
        )
        and all(
            candidate.startswith(row.get("source_tier", ""))
            for candidate in re.findall(
                r"(?<![A-Za-z0-9_])([cdk]_[A-Za-z0-9_]+)",
                row.get("ranked_candidate_evidence", ""),
            )
        )
        and (
            not row.get("preferred_candidate_title")
            or row.get("preferred_candidate_title", "").startswith(
                row.get("source_tier", "")
            )
        )
        and (
            (
                row.get("preferred_candidate_title")
                and row.get("preferred_candidate_present_near_reference")
                in {"yes", "no"}
            )
            or (
                not row.get("preferred_candidate_title")
                and row.get("preferred_candidate_present_near_reference")
                == "not_applicable"
            )
        )
        and (
            not row.get("preferred_candidate_title")
            or row.get("preferred_candidate_source")
        )
        and (
            row.get("identity_descendant_candidate_status")
            == "source_title_has_no_direct_lower_tier_children"
            or row.get("identity_descendant_source_titles")
        )
        and (
            row.get("identity_descendant_mapped_source_count") == "0"
            or (
                row.get("identity_descendant_same_tier_candidates")
                and row.get("identity_descendant_candidate_evidence")
            )
        )
        and (
            row.get("identity_geometry_comparison")
            not in {"exact_candidate_set_match", "partial_candidate_set_overlap"}
            or row.get("identity_geometry_overlap_titles")
        )
        and (
            row.get("identity_geometry_comparison")
            != "disjoint_candidate_sets_review"
            or not row.get("preferred_candidate_title")
        )
        and (
            row.get("usage_context_family") != "holy_site_county_reference"
            or (
                row.get("context_location_basis") != "not_applicable"
                and row.get("context_location_source_baronies")
                and row.get("context_location_source_province_ids")
                and row.get("context_location_relation_evidence")
            )
        )
        and Path(row.get("relation_report", "")).resolve()
        == relation_refresh_report.resolve()
        and row.get("target_tracking_stale")
        == ("yes" if relation_target_tracking_stale else "no")
        for row in tiger_p0_higher_title_rows
    )
    tiger_p0_higher_no_candidate_complete = (
        bool(tiger_p0_higher_no_candidate_rows)
        and all(
            row.get("root_cause_id")
            and row.get("source_title", "").startswith(("c_", "d_", "k_"))
            and row.get("candidate_status")
            in TIGER_P0_HIGHER_NO_CANDIDATE_STATUSES
            and row.get("usage_context_family")
            and row.get("usage_context_decision")
            and row.get("context_recommendation")
            and row.get("reference_context_status") == "complete"
            and row.get("reference_context_scopes")
            and row.get("reference_context_excerpt")
            and row.get("context_location_basis")
            and row.get("context_location_candidate_status")
            and row.get("identity_descendant_candidate_status")
            and row.get("identity_descendant_mapped_source_count")
            and row.get("identity_geometry_comparison")
            and (
                row.get("identity_descendant_candidate_status")
                == "source_title_has_no_direct_lower_tier_children"
                or row.get("identity_descendant_source_titles")
            )
            and (
                row.get("identity_descendant_mapped_source_count") == "0"
                or (
                    row.get("identity_descendant_same_tier_candidates")
                    and row.get("identity_descendant_candidate_evidence")
                )
            )
            and (
                row.get("identity_geometry_comparison")
                not in {"exact_candidate_set_match", "partial_candidate_set_overlap"}
                or row.get("identity_geometry_overlap_titles")
            )
            and (
                row.get("identity_geometry_comparison")
                != "disjoint_candidate_sets_review"
                or not row.get("preferred_candidate_title")
            )
            and (
                row.get("usage_context_family") != "holy_site_county_reference"
                or (
                    row.get("context_location_source_baronies")
                    and row.get("context_location_source_province_ids")
                    and row.get("context_location_relation_evidence")
                )
            )
            and row.get("auto_apply") == "no"
            for row in tiger_p0_higher_no_candidate_rows
        )
    )
    tiger_p0_fallback_count = sum(
        row.get("recovery_classification") == "manual_unclassified_p0_review"
        for row in tiger_p0_rows
    )
    tiger_p0_status = (
        "full"
        if tiger_p0_exists == "yes"
        and tiger_p0_stale == "no"
        and tiger_p0_key_match
        and tiger_p0_live_key_match
        and tiger_p0_barony_key_match
        and tiger_p0_higher_title_key_match
        and tiger_p0_higher_no_candidate_key_match
        and tiger_p0_live_complete
        and tiger_p0_barony_complete
        and tiger_p0_higher_title_complete
        and tiger_p0_higher_no_candidate_complete
        and tiger_p0_revision_match
        and tiger_p0_fallback_count == 0
        and tiger_classification_status == "full"
        and relation_refresh_status in {"full", "partial"}
        else (
            "stale" if tiger_p0_exists == "yes" else "not_audited"
        )
    )
    tiger_p0_raw_count = sum(
        int(row.get("finding_count") or 0) for row in tiger_p0_rows
    )
    tiger_p0_verified_live_raw_count = sum(
        int(row.get("finding_count") or 0)
        for row in tiger_p0_rows
        if row.get("issue_status") == "verified_live_error"
    )
    tiger_p0_live_raw_count = sum(
        int(row.get("raw_tiger_report_count") or 0)
        for row in tiger_p0_live_rows
    )
    if tiger_p0_verified_live_raw_count != tiger_p0_live_raw_count:
        tiger_p0_status = "stale"

    p1_root = repo_root / P1_STRUCTURAL_LOCALIZATION_PATH
    p1_history_report = p1_root / "history_duplicate_block_audit.csv"
    p1_history_rows = read_csv(p1_history_report)
    p1_history_evidence = {
        (row.get("domain", ""), row.get("object", "")): row
        for row in p1_history_rows
    }
    for row in findings:
        if row.get("classification") not in {
            "duplicate_title_block_same_layer",
            "duplicate_province_block",
        }:
            continue
        evidence = p1_history_evidence.get(
            (row.get("domain", ""), row.get("object", ""))
        )
        if evidence and evidence.get("semantic_source_provenance"):
            row["provenance"] = evidence["semantic_source_provenance"]

    review_surface_report = (
        repo_root / REVIEW_SURFACE_TRIAGE_PATH
        / "repo_review_surface_triage.csv"
    )
    review_surface_rows = read_csv(review_surface_report)
    expected_review_surface_counts = Counter(
        (
            row.get("domain", ""),
            row.get("classification", ""),
            row.get("provenance", ""),
        )
        for row in findings
        if row.get("severity") == "review"
    )
    reported_review_surface_counts = {
        (
            row.get("domain", ""),
            row.get("classification", ""),
            row.get("provenance", ""),
        ): int(row.get("finding_count") or 0)
        for row in review_surface_rows
    }
    review_surface_sources = [
        repo_root / ".codex/works/tools/classify_repo_review_surface.py",
        repo_root
        / ".codex/works/tools/classify_p1_structural_localization_roots.py",
        repo_root / ".codex/works/tools/audit_repo_integration_closure.py",
        p1_history_report,
        *tiger_sources,
    ]
    review_surface_exists, review_surface_stale = report_freshness(
        review_surface_report, review_surface_sources
    )
    review_surface_revision_match = bool(review_surface_rows) and all(
        row.get("yusseter_revision") == yusseter_revision
        and row.get("current_asil_revision") == current_asil_revision
        for row in review_surface_rows
    )
    review_surface_count_match = (
        dict(expected_review_surface_counts) == reported_review_surface_counts
    )
    review_surface_fallback_count = sum(
        row.get("triage_bucket") == "unclassified_review_group"
        for row in review_surface_rows
    )
    review_surface_status = (
        "full"
        if review_surface_exists == "yes"
        and review_surface_stale == "no"
        and review_surface_revision_match
        and review_surface_count_match
        and review_surface_fallback_count == 0
        and tiger_p0_status == "full"
        else (
            "stale" if review_surface_exists == "yes" else "not_audited"
        )
    )
    review_surface_raw_count = sum(
        int(row.get("finding_count") or 0) for row in review_surface_rows
    )

    p1_asset_report = p1_root / "missing_asset_reference_audit.csv"
    p1_localization_report = p1_root / "localization_duplicate_key_audit.csv"
    p1_mapped_report = p1_root / "mapped_localization_candidate_audit.csv"
    p1_ancillary_report = p1_root / "ancillary_structural_audit.csv"
    p1_region_report = p1_root / "map_region_title_reference_audit.csv"
    p1_reports = [
        p1_history_report,
        p1_asset_report,
        p1_localization_report,
        p1_mapped_report,
        p1_ancillary_report,
        p1_region_report,
    ]
    p1_asset_rows = read_csv(p1_asset_report)
    p1_localization_rows = read_csv(p1_localization_report)
    p1_mapped_rows = read_csv(p1_mapped_report)
    p1_ancillary_rows = read_csv(p1_ancillary_report)
    p1_region_rows = read_csv(p1_region_report)
    expected_p1_history_keys = {
        (row.get("domain", ""), row.get("object", ""))
        for row in findings
        if row.get("severity") == "review"
        and row.get("classification") in {
            "duplicate_title_block_same_layer",
            "duplicate_province_block",
        }
    }
    reported_p1_history_keys = {
        (row.get("domain", ""), row.get("object", ""))
        for row in p1_history_rows
    }
    expected_p1_asset_keys = {
        row.get("object", "")
        for row in findings
        if row.get("severity") == "review"
        and row.get("domain") == "ck3_tiger"
        and row.get("classification") == "missing_asset_reference"
    }
    reported_p1_asset_keys = {
        row.get("source_finding_object", "") for row in p1_asset_rows
    }
    expected_p1_localization_keys = {
        row.get("object", "")
        for row in findings
        if row.get("severity") == "review"
        and row.get("domain") == "localization"
        and row.get("classification") == "conflicting_duplicate_key"
    }
    reported_p1_localization_keys = {
        row.get("key", "") for row in p1_localization_rows
    }
    expected_p1_mapped_keys = {
        (
            row.get("key", ""),
            row.get("requirement", ""),
            row.get("source_key", ""),
        )
        for row in localization_requirements
        if row.get("status") == "missing_effective_mapped_source_available"
    }
    reported_p1_mapped_keys = {
        (
            row.get("target_key", ""),
            row.get("requirement", ""),
            row.get("source_key", ""),
        )
        for row in p1_mapped_rows
    }
    expected_p1_region_keys = {
        (row.get("object", ""), row.get("path", ""), row.get("line", ""))
        for row in findings
        if row.get("domain") == "map_regions"
        and row.get("classification") == "undefined_title_reference"
    }
    reported_p1_region_keys = {
        (
            row.get("undefined_title", ""),
            row.get("path", ""),
            row.get("line", ""),
        )
        for row in p1_region_rows
    }
    p1_ancillary_complete = bool(p1_ancillary_rows) and all(
        row.get("structural_family")
        and row.get("object")
        and row.get("status")
        and row.get("provenance")
        and row.get("recommended_action")
        and (
            row.get("structural_family")
            != "coat_of_arms_duplicate_definition"
            or row.get("identity_status")
        )
        for row in p1_ancillary_rows
    )
    p1_key_match = all((
        expected_p1_history_keys == reported_p1_history_keys,
        expected_p1_asset_keys == reported_p1_asset_keys,
        expected_p1_localization_keys == reported_p1_localization_keys,
        expected_p1_mapped_keys == reported_p1_mapped_keys,
        expected_p1_region_keys == reported_p1_region_keys,
        p1_ancillary_complete,
    ))
    p1_sources = [
        repo_root
        / ".codex/works/tools/classify_p1_structural_localization_roots.py",
        repo_root / ".codex/works/tools/audit_repo_integration_closure.py",
        repo_root / LANDED_PATH,
    ]
    p1_sources.extend(sorted((repo_root / "BookmarksGit").rglob("*.txt")))
    p1_sources.extend(
        sorted((repo_root / "BookmarksGit/localization").rglob("*.yml"))
    )
    p1_sources.append(repo_root / "BookmarksGit/fonts/fonts.font")
    p1_freshness = [report_freshness(report, p1_sources) for report in p1_reports]
    p1_exists = "yes" if all(value[0] == "yes" for value in p1_freshness) else "no"
    p1_stale = "yes" if any(value[1] == "yes" for value in p1_freshness) else "no"
    p1_all_rows = (
        p1_history_rows
        + p1_asset_rows
        + p1_localization_rows
        + p1_mapped_rows
        + p1_ancillary_rows
        + p1_region_rows
    )
    p1_revision_match = bool(p1_all_rows) and all(
        row.get("yusseter_revision") == yusseter_revision
        and row.get("current_asil_revision") == current_asil_revision
        and row.get("baseline_revision")
        for row in p1_all_rows
    )
    p1_fallback_count = sum(
        not row.get("comparison") for row in p1_history_rows
    ) + sum(
        not row.get("asset_status") for row in p1_asset_rows
    ) + sum(
        not row.get("conflict_type") for row in p1_localization_rows
    ) + sum(
        not row.get("recommended_action") for row in p1_mapped_rows
    ) + sum(
        not row.get("status")
        or not row.get("provenance")
        or not row.get("recommended_action")
        or (
            row.get("structural_family")
            == "coat_of_arms_duplicate_definition"
            and not row.get("identity_status")
        )
        for row in p1_ancillary_rows
    ) + sum(
        not row.get("status") or not row.get("recommended_action")
        for row in p1_region_rows
    )
    p1_status = (
        "full"
        if p1_exists == "yes"
        and p1_stale == "no"
        and p1_key_match
        and p1_revision_match
        and p1_fallback_count == 0
        and review_surface_status == "full"
        else ("stale" if p1_exists == "yes" else "not_audited")
    )
    p1_audited_row_count = len(p1_all_rows)
    p1_coa_rows = [
        row
        for row in p1_ancillary_rows
        if row.get("structural_family") == "coat_of_arms_duplicate_definition"
    ]
    p1_ancillary_review_count = sum(
        row.get("recommended_priority") != "P3" for row in p1_ancillary_rows
    )

    coverage = [
        coverage_row("landed_titles", "", "all mod landed-title files", len(list((repo_root / "BookmarksGit/common/landed_titles").glob("*.txt"))), "parsed structure and direct cross-references", "full", closure_report, findings),
        coverage_row("map_identity", "definition", "definition ID and RGB uniqueness", 1, "current-state CSV parse", "full", closure_report, findings),
        coverage_row("map_identity", "default_map", "file and province references", 1, "mod plus vanilla fallback resolution", "full", closure_report, findings),
        coverage_row("map_identity", "adjacencies", "all active adjacency rows", 1, "definition endpoint validation", "full", closure_report, findings),
        coverage_row("map_identity", "province_terrain", "all numeric terrain/property assignments", len(list((repo_root / "BookmarksGit/common/province_terrain").rglob("*.txt"))), "definition key validation", "full", closure_report, findings),
        coverage_row("map_objects", "locator_identity", "all top-level map-object locator files", len(list((repo_root / "BookmarksGit/gfx/map/map_object_data").glob("*.txt"))), "definition ID validation", "full", closure_report, findings),
        coverage_row("map_objects", "locator_geometry", "pixel position and province containment", len(list((repo_root / "BookmarksGit/gfx/map/map_object_data").glob("*.txt"))), "existing raster position audit", locator_status, locator_report.relative_to(repo_root).as_posix() if locator_report.exists() else "", findings, locator_exists, locator_stale, "not rerun by closure orchestrator"),
        coverage_row("map_regions", "", "all geographical-region text files", len(list((repo_root / "BookmarksGit/map_data/geographical_regions").rglob("*.txt"))), "explicit province and title reference validation", "full", closure_report, findings),
        coverage_row("province_history", "identity", "all mod province-history blocks", len(list((repo_root / "BookmarksGit/history/provinces").rglob("*.txt"))), "definition identity, duplicate blocks and brace validation", "full", closure_report, findings),
        coverage_row(
            "province_history", "landed_coverage",
            f"all {len(province_baronies)} landed barony provinces; "
            f"{province_semantics_capital_count} county capitals across "
            f"{province_semantics_date_count} bookmark dates",
            len(province_baronies),
            "file-override and province-mapping-aware effective culture/religion/holding audit",
            province_semantics_status,
            province_semantics_report.relative_to(repo_root).as_posix()
            if province_semantics_report.exists() else "",
            findings,
            province_semantics_exists,
            province_semantics_stale,
            "static bookmark semantics covered; holding auto-generation still needs runtime smoke testing",
        ),
        coverage_row("title_history", "identity", "all mod title-history files", len(list((repo_root / "BookmarksGit/history/titles").rglob("*.txt"))), "landed identity, layer duplicates and effective holder resolution", "full", closure_report, findings),
        coverage_row("title_history", "holder_reference", "all explicit current holder assignments", len(list((repo_root / "BookmarksGit/history/titles").rglob("*.txt"))), "current/premerge/merged-source assignment and character-definition comparison", title_holder_status, title_holder_provenance_report.relative_to(repo_root).as_posix() if title_holder_provenance_report.exists() else "", findings, title_holder_exists, title_holder_stale),
        coverage_row("title_history", "source_provenance", "four-way source overwrite comparison", len(list((repo_root / "BookmarksGit/history/titles").rglob("*.txt"))), "premerge/current/asıl-mod semantic comparison", "full", semantic_report, findings),
        coverage_row("localization", "", "English-by-name or l_english-header files", len([row for row in localization_files if row["source"] == "mod"]), "effective mod plus vanilla requirements with asıl-mod source lookup", "full", closure_report, findings),
        coverage_row("connection_arrows", "", "all Silk Road province references", 1, "source/current semantic province mapping", "full", semantic_report, findings),
        coverage_row("source_shared_title_reference", "", "source-shared text under common/events/history/map/gui/map objects", 4723, "four-way exact/source-line scan", "full", semantic_report, findings),
        coverage_row("source_shared_province_reference", "", "source-shared explicit province references", 4723, "four-way semantic province scan", "full", semantic_report, findings),
        coverage_row("binary_map", "provinces_png", "global RGB pixel presence, reserved palette filtering, provenance and four-neighbor topology", 1, "current map plus premerge/asıl-mod identity and active-reference audit", binary_map_status, binary_map_report.relative_to(repo_root).as_posix() if binary_map_report.exists() else "", findings, binary_map_exists, binary_map_stale, "source-remap candidates are evidence; relation targets still require review"),
        coverage_row(
            "runtime", "bookmarks",
            f"{runtime_date_count} unique bookmark dates; all {runtime_county_count} landed counties and {runtime_featured_count} featured-character rows",
            len(runtime_current_sources),
            "static effective holder/liege/government and character-life audit with current/premerge/asıl-mod provenance",
            runtime_status,
            runtime_report.relative_to(repo_root).as_posix() if runtime_report.exists() else "",
            findings,
            runtime_exists,
            runtime_stale,
            "static startup state covered; succession, startup effects, government fallback and UI still require game smoke tests",
        ),
        coverage_row("ck3_tiger", "", "current mod versus asıl-mod baseline", len(tiger_comparison), "same-version same-config JSON multiset comparison", tiger_status, (Path(OUTPUT_PATH) / "ck3_tiger_comparison.csv").as_posix() if tiger_comparison else "", findings, tiger_exists, tiger_stale, "current-only reports require intent classification; shared reports are baseline"),
        coverage_row(
            "ck3_tiger", "current_only_root_cause",
            f"{len(tiger_comparison)} compared reports; "
            f"{len(tiger_root_findings)} deduplicated current-only root causes",
            len(tiger_root_findings),
            "exact-line provenance, title identity and semantic-context classification",
            tiger_classification_status,
            tiger_classification_report.relative_to(repo_root).as_posix()
            if tiger_classification_report.exists() else "",
            findings,
            tiger_classification_exists,
            tiger_classification_stale,
            f"finding mode: {tiger_finding_mode}; candidates remain review evidence",
        ),
        coverage_row(
            "localization", "dynamic_title_reference",
            f"{dynamic_title_inventory_count} GetTitleByKey references; "
            f"{dynamic_title_raw_count} undefined-title findings",
            len(localization_files),
            "dynamic GetTitleByKey extraction plus current/asıl-mod/vanilla identity resolution",
            dynamic_title_status,
            dynamic_title_report.relative_to(repo_root).as_posix()
            if dynamic_title_report.exists() else "",
            findings,
            dynamic_title_exists,
            dynamic_title_stale,
            f"{dynamic_title_tiger_overlap_count} exact Tiger overlaps excluded from closure findings",
        ),
        coverage_row(
            "mpe_add_1", "closure",
            f"{len(mpe_scope)} current scoped barony rows plus exclusions and superseded IDs",
            len(mpe_scope),
            "current landed, map identity/pixels, locators, history, terrain, localization and residue audit",
            mpe_status,
            mpe_report.relative_to(repo_root).as_posix()
            if mpe_report.exists() else "",
            findings,
            mpe_exists,
            mpe_stale,
            "findings already covered by repo-wide root causes are linked but not double-counted",
        ),
    ]
    region_spatial_coverage = coverage_row(
        "map_regions",
        "spatial_closure",
        (
            f"{external_closure_stats['region_root_count']} independent region "
            "review roots across all effective geographical-region files"
        ),
        len(list((repo_root / "BookmarksGit/map_data/geographical_regions").rglob("*.txt"))),
        (
            "effective file-override parse, recursive region resolution, raster-land "
            "components, internal gaps, nested overlap and exact main-closure linking"
        ),
        region_closure_status,
        region_closure_report.relative_to(repo_root).as_posix()
        if region_closure_report.exists() else "",
        findings,
        region_closure_exists,
        region_closure_stale,
        (
            f"exact_existing_main_roots={external_closure_stats['region_exact_root_count']}; "
            f"external_review_roots={external_closure_stats['region_external_root_count']}; "
            "external roots remain review evidence and are not duplicated in main findings"
        ),
    )
    region_spatial_coverage["blocker_count"] = "0"
    region_spatial_coverage["review_count"] = str(
        external_closure_stats["region_root_count"]
    )
    coverage.append(region_spatial_coverage)

    market_static_coverage = coverage_row(
        "silk_road_market",
        "market_building_gui_closure",
        (
            f"{len(silk_road_market_root_rows)} independent market roots across "
            "all active current-scope Silk Road subregions"
        ),
        len(silk_road_market_root_rows),
        (
            "center, region, expected building, province history, decision, English "
            "localization, locator and static GUI binding audit"
        ),
        market_closure_status,
        market_closure_report.relative_to(repo_root).as_posix()
        if market_closure_report.exists() else "",
        findings,
        market_closure_exists,
        market_closure_stale,
        (
            f"materialized_roots={external_closure_stats['market_materialized_root_count']}; "
            f"fix_design_blockers={len(market_design_keys)}; auto_apply=0"
        ),
    )
    coverage.append(market_static_coverage)
    coverage.append(coverage_row(
        "silk_road_market",
        "runtime_smoke_test",
        "1178.10.1 GUI market names, icons, decision labels and destinations",
        len(read_csv(market_runtime_report)),
        "reusable in-game smoke-test checklist",
        "partial" if market_runtime_report.exists() else "not_audited",
        market_runtime_report.relative_to(repo_root).as_posix()
        if market_runtime_report.exists() else "",
        findings,
        "yes" if market_runtime_report.exists() else "no",
        "no",
        "requires user in-game signoff after any approved source edit",
    ))
    localization_visibility_coverage = coverage_row(
        "localization",
        "title_visibility",
        f"{len(expected_visibility_keys)} missing-everywhere landed-title base keys",
        len(localization_visibility_rows),
        "landed hierarchy, title properties, history assignment, runtime consumer and section-role classification",
        localization_visibility_status,
        localization_visibility_report.relative_to(repo_root).as_posix()
        if localization_visibility_report.exists() else "",
        findings,
        localization_visibility_exists,
        localization_visibility_stale,
        (
            f"exact_key_set_match={'yes' if localization_visibility_key_match else 'no'}; "
            f"blocker={localization_visibility_applied['blocker']}; "
            f"review={localization_visibility_applied['review']}; "
            f"info={localization_visibility_applied['info']}"
        ),
    )
    localization_visibility_coverage["blocker_count"] = str(
        localization_visibility_applied["blocker"]
    )
    localization_visibility_coverage["review_count"] = str(
        localization_visibility_applied["review"]
    )
    coverage.append(localization_visibility_coverage)
    coverage.append(coverage_row(
        "character_title_history",
        "upstream_integration_recovery",
        (
            f"{len(expected_upstream_character_keys)} upstream-integration "
            "character/bookmark blocker roots"
        ),
        len(upstream_character_rows),
        (
            "current/premerge/merged-source/current-source/vanilla character "
            "identity plus batched asıl-mod Git-history recovery audit"
        ),
        upstream_character_status,
        upstream_character_report.relative_to(repo_root).as_posix()
        if upstream_character_report.exists() else "",
        findings,
        upstream_character_exists,
        upstream_character_stale,
        (
            f"exact_key_set_match={'yes' if upstream_character_key_match else 'no'}; "
            f"revision_match={'yes' if upstream_character_revision_match else 'no'}; "
            f"represented_raw_blockers={upstream_character_raw_count}; "
            "recovery candidates remain blockers until separately applied and validated"
        ),
    ))
    coverage.append(coverage_row(
        "character_title_history",
        "local_mixed_recovery",
        (
            f"{len(expected_local_mixed_character_keys)} local or "
            "mixed-provenance character/bookmark blocker roots"
        ),
        len(local_mixed_character_rows),
        (
            "current/premerge/merged-source/current-source/vanilla character "
            "identity, holder-assignment life range and asıl-mod Git-history audit"
        ),
        local_mixed_character_status,
        local_mixed_character_report.relative_to(repo_root).as_posix()
        if local_mixed_character_report.exists() else "",
        findings,
        local_mixed_character_exists,
        local_mixed_character_stale,
        (
            f"exact_key_set_match={'yes' if local_mixed_character_key_match else 'no'}; "
            f"revision_match={'yes' if local_mixed_character_revision_match else 'no'}; "
            f"represented_raw_blockers={local_mixed_character_raw_count}; "
            "recovery candidates remain blockers until separately applied and validated"
        ),
    ))
    coverage.append(coverage_row(
        "character_title_history",
        "shared_asil_mod_recovery",
        (
            f"{len(expected_shared_asil_character_keys)} shared asıl-mod "
            "character/bookmark blocker roots"
        ),
        len(shared_asil_character_rows),
        (
            "current/premerge/merged-source/current-source/vanilla character "
            "identity, holder/bookmark life range and asıl-mod Git-history audit"
        ),
        shared_asil_character_status,
        shared_asil_character_report.relative_to(repo_root).as_posix()
        if shared_asil_character_report.exists() else "",
        findings,
        shared_asil_character_exists,
        shared_asil_character_stale,
        (
            f"exact_key_set_match={'yes' if shared_asil_character_key_match else 'no'}; "
            f"revision_match={'yes' if shared_asil_character_revision_match else 'no'}; "
            f"represented_raw_blockers={shared_asil_character_raw_count}; "
            "shared-source recovery candidates remain blockers until separately applied and validated"
        ),
    ))
    coverage.append(coverage_row(
        "repo_closure",
        "non_character_blocker_recovery",
        (
            f"{len(expected_non_character_keys)} non-character blocker roots "
            "across localization, binary map and province history"
        ),
        len(non_character_rows),
        (
            "exact root-key classification using localization source/visibility, "
            "MPE current-state residue, binary-map and province semantic evidence"
        ),
        non_character_status,
        non_character_report.relative_to(repo_root).as_posix()
        if non_character_report.exists() else "",
        findings,
        non_character_exists,
        non_character_stale,
        (
            f"exact_key_set_match={'yes' if non_character_key_match else 'no'}; "
            f"revision_match={'yes' if non_character_revision_match else 'no'}; "
            f"represented_raw_blockers={non_character_raw_count}; "
            "recovery candidates remain blockers until separately applied and validated"
        ),
    ))
    tiger_p0_coverage = coverage_row(
        "ck3_tiger",
        "p0_root_triage",
        (
            f"{len(expected_tiger_p0_keys)} P0 current-only Tiger triage rows; "
            f"{len(tiger_p0_live_rows)} independent verified live-error roots; "
            f"{len(tiger_p0_barony_rows)} undefined-barony identity candidates; "
            f"{len(tiger_p0_higher_title_rows)} undefined higher-title "
            f"identity candidates; {len(tiger_p0_higher_no_candidate_rows)} "
            "higher-title no-candidate context decisions; "
            f"{sum(row.get('usage_context_family') == 'holy_site_county_reference' for row in tiger_p0_higher_no_candidate_rows)} "
            "holy-site location resolutions; descendant-title identity evidence "
            f"for {len(tiger_p0_higher_title_rows)} higher-title roots"
        ),
        len(tiger_p0_rows),
        (
            "exact P0 root-key triage separating verified live errors, pending "
            "source fixes and title-identity decisions, plus overlapping Tiger "
            "message consolidation without automatic edits"
        ),
        tiger_p0_status,
        (repo_root / TIGER_P0_TRIAGE_PATH).relative_to(repo_root).as_posix()
        if (repo_root / TIGER_P0_TRIAGE_PATH).exists() else "",
        findings,
        tiger_p0_exists,
        tiger_p0_stale,
        (
            f"exact_key_set_match={'yes' if tiger_p0_key_match else 'no'}; "
            f"live_root_ids_match={'yes' if tiger_p0_live_key_match else 'no'}; "
            f"barony_root_ids_match={'yes' if tiger_p0_barony_key_match else 'no'}; "
            "higher_title_root_ids_match="
            f"{'yes' if tiger_p0_higher_title_key_match else 'no'}; "
            "higher_title_no_candidate_ids_match="
            f"{'yes' if tiger_p0_higher_no_candidate_key_match else 'no'}; "
            f"live_roots_complete={'yes' if tiger_p0_live_complete else 'no'}; "
            f"barony_candidates_complete={'yes' if tiger_p0_barony_complete else 'no'}; "
            "higher_title_candidates_complete="
            f"{'yes' if tiger_p0_higher_title_complete else 'no'}; "
            "higher_title_no_candidate_context_complete="
            f"{'yes' if tiger_p0_higher_no_candidate_complete else 'no'}; "
            f"revision_match={'yes' if tiger_p0_revision_match else 'no'}; "
            f"represented_raw_tiger_rows={tiger_p0_raw_count}; "
            f"verified_live_raw_rows={tiger_p0_live_raw_count}; "
            f"fallback={tiger_p0_fallback_count}; relation_evidence="
            f"{relation_refresh_status}; candidates are not auto-applied"
        ),
    )
    tiger_p0_coverage["blocker_count"] = str(sum(
        row.get("recommended_severity") == "blocker" for row in tiger_p0_rows
    ))
    tiger_p0_coverage["review_count"] = str(sum(
        row.get("recommended_severity") == "review" for row in tiger_p0_rows
    ))
    coverage.append(tiger_p0_coverage)
    relation_refresh_coverage = coverage_row(
        "source_shared_province_reference",
        "province_relation_current_refresh",
        (
            f"{len(relation_refresh_rows)} source provinces; "
            f"{len(relation_refresh_manual_rows)} manual-review relations"
        ),
        len(relation_refresh_outputs),
        (
            "current source/target definition and raster geometry, authoritative "
            "source landed titles, canonical manual evidence and SHA-256 input manifest"
        ),
        relation_refresh_status,
        relation_refresh_report.relative_to(repo_root).as_posix()
        if relation_refresh_report.exists() else "",
        findings,
        relation_refresh_exists,
        relation_refresh_stale,
        (
            f"manifest_roles_match={'yes' if relation_manifest_role_match else 'no'}; "
            f"manifest_hash_match={'yes' if relation_manifest_hash_match else 'no'}; "
            f"canonical_master_unchanged={'yes' if relation_canonical_unchanged else 'no'}; "
            f"report_rows_consistent={'yes' if relation_refresh_consistent else 'no'}; "
            f"status_whitespace_anomalies={relation_status_whitespace_count}; "
            f"target_tracking_older_than_target_image="
            f"{'yes' if relation_target_tracking_stale else 'no'}; "
            "all relation candidates remain manual while tracking is stale"
        ),
    )
    relation_refresh_coverage["blocker_count"] = "0"
    relation_refresh_coverage["review_count"] = str(
        len(relation_refresh_manual_rows)
    )
    coverage.append(relation_refresh_coverage)
    review_surface_coverage = coverage_row(
        "repo_closure",
        "review_surface_triage",
        (
            f"{review_surface_raw_count} raw review findings grouped into "
            f"{len(review_surface_rows)} provenance-aware families"
        ),
        len(review_surface_rows),
        (
            "exact domain/classification/provenance counts with priority, decision "
            "and cross-audit-overlap triage"
        ),
        review_surface_status,
        review_surface_report.relative_to(repo_root).as_posix()
        if review_surface_report.exists() else "",
        findings,
        review_surface_exists,
        review_surface_stale,
        (
            f"exact_group_counts_match={'yes' if review_surface_count_match else 'no'}; "
            f"revision_match={'yes' if review_surface_revision_match else 'no'}; "
            f"fallback={review_surface_fallback_count}; raw review rows are not "
            "independent root-cause counts"
        ),
    )
    review_surface_coverage["blocker_count"] = "0"
    review_surface_coverage["review_count"] = str(review_surface_raw_count)
    coverage.append(review_surface_coverage)
    p1_coverage = coverage_row(
        "repo_closure",
        "p1_structural_localization_root_audit",
        (
            f"{len(expected_p1_history_keys)} duplicate history roots, "
            f"{len(expected_p1_asset_keys)} missing assets, "
            f"{len(expected_p1_localization_keys)} conflicting localization keys "
            f"and {len(expected_p1_mapped_keys)} mapped localization candidates; "
            f"{len(p1_ancillary_rows)} ancillary structural roots including "
            f"{len(p1_coa_rows)} duplicate CoA identities; "
            f"{len(expected_p1_region_keys)} undefined map-region title references"
        ),
        p1_audited_row_count,
        (
            "full-block and field-level history comparison, current/premerge/"
            "asıl-mod/vanilla asset provenance, quote-aware localization conflict "
            "and mapped-source classification, CoA identity/provenance resolution, "
            "and relation-aware map-region title review"
        ),
        p1_status,
        p1_root.relative_to(repo_root).as_posix() if p1_root.exists() else "",
        findings,
        p1_exists,
        p1_stale,
        (
            f"exact_key_sets_match={'yes' if p1_key_match else 'no'}; "
            f"revision_match={'yes' if p1_revision_match else 'no'}; "
            f"ancillary_complete={'yes' if p1_ancillary_complete else 'no'}; "
            f"fallback={p1_fallback_count}; no candidate is auto-applied"
        ),
    )
    p1_coverage["blocker_count"] = "0"
    p1_coverage["review_count"] = str(
        len(expected_p1_history_keys)
        + len(expected_p1_asset_keys)
        + len(expected_p1_localization_keys)
        + len(expected_p1_mapped_keys)
        + p1_ancillary_review_count
        + len(expected_p1_region_keys)
    )
    coverage.append(p1_coverage)

    for root in blocker_root_causes:
        if root.get("provenance", "") in DEFERRED_BLOCKER_PROVENANCES:
            root["work_phase"] = "deferred_asil_mod_final_pass"
            root["work_priority"] = "last"
            root["work_defer_basis"] = "shared_asil_mod_baseline"
            root["work_reason"] = (
                "same blocker root exists in the asıl-mod baseline; keep visible "
                "but do not modify during the current integration/Yusseter pass"
            )
        elif root.get("source_origin_classification", "") in DEFERRED_SOURCE_ORIGINS:
            root["work_phase"] = "deferred_asil_mod_final_pass"
            root["work_priority"] = "last"
            root["work_defer_basis"] = "asil_mod_source_native_regression"
            root["work_reason"] = (
                "the broken holder chain is already present inside the asıl-mod "
                "source; retain it for the final source-baseline cleanup pass"
            )
        else:
            root["work_phase"] = "active_integration_and_yusseter"
            root["work_priority"] = "current"
            root["work_defer_basis"] = ""
            root["work_reason"] = (
                "not a shared asıl-mod baseline root; classify and resolve in the "
                "current integration/Yusseter pass"
            )

    active_blocker_roots = [
        row for row in blocker_root_causes
        if row["work_phase"] == "active_integration_and_yusseter"
    ]
    deferred_asil_mod_roots = [
        row for row in blocker_root_causes
        if row["work_phase"] == "deferred_asil_mod_final_pass"
    ]

    write_csv(output_dir / "repo_integration_closure_findings.csv", findings)
    write_csv(
        output_dir / "repo_integration_blocker_root_causes.csv",
        blocker_root_causes,
    )
    write_csv(
        output_dir / "repo_integration_active_blocker_roots.csv",
        active_blocker_roots,
    )
    write_csv(
        output_dir / "repo_integration_deferred_asil_mod_roots.csv",
        deferred_asil_mod_roots,
    )
    write_csv(output_dir / "repo_integration_closure_coverage.csv", coverage)
    write_csv(
        output_dir / "repo_integration_external_closure_links.csv",
        external_closure_links,
    )
    write_csv(output_dir / "map_identity_findings.csv", map_findings)
    write_csv(output_dir / "history_identity_findings.csv", history_findings)
    write_csv(output_dir / "localization_findings.csv", localization_findings)
    write_csv(output_dir / "localization_requirements.csv", localization_requirements)
    write_csv(output_dir / "localization_english_file_inventory.csv", localization_files)
    write_csv(output_dir / "ck3_tiger_comparison.csv", tiger_comparison)
    write_csv(output_dir / "ck3_tiger_comparison_summary.csv", tiger_summary)
    write_csv(output_dir / "ck3_tiger_static_blocker_overlap.csv", tiger_overlaps)
    write_csv(output_dir / "ck3_tiger_config_equivalence.csv", tiger_config_delta)
    write_csv(
        output_dir / "ck3_tiger_current_only_priority.csv",
        tiger_current_only_priority,
    )

    severity_counts = Counter(row["severity"] for row in findings)
    classification_counts = Counter(
        (row["domain"], row["classification"])
        for row in findings
    )
    coverage_counts = Counter(row["coverage_status"] for row in coverage)
    blockers = [row for row in findings if row["severity"] == "blocker"]
    blocker_classes = Counter(
        (row["domain"], row["classification"]) for row in blockers
    )
    blocker_provenance = Counter(row["provenance"] for row in blockers)
    blocker_root_classes = Counter(
        (row["subsystem"], row["classification"])
        for row in blocker_root_causes
    )
    blocker_root_provenance = Counter(
        row["provenance"] for row in blocker_root_causes
    )
    blocker_root_raw_count = sum(
        int(row["raw_finding_count"]) for row in blocker_root_causes
    )
    active_blocker_raw_count = sum(
        int(row["raw_finding_count"]) for row in active_blocker_roots
    )
    deferred_asil_mod_raw_count = sum(
        int(row["raw_finding_count"]) for row in deferred_asil_mod_roots
    )
    deferred_basis_counts = Counter(
        row.get("work_defer_basis", "") for row in deferred_asil_mod_roots
    )
    incomplete = [
        row for row in coverage if row["coverage_status"] != "full"
    ]
    tiger_provenance_counts = Counter(
        row["provenance"] for row in tiger_comparison
    )
    tiger_priority_counts = Counter(
        row["priority"] for row in tiger_current_only_priority
    )
    tiger_root_rows = read_csv(tiger_classification_report)
    tiger_root_priority_counts = Counter(
        row.get("action_priority", "") for row in tiger_root_rows
    )
    tiger_root_provenance_counts = Counter(
        row["provenance"] for row in tiger_root_findings
    )
    dynamic_title_class_counts = Counter(
        row["classification"] for row in dynamic_title_findings
    )
    localization_visibility_class_counts = Counter(
        row.get("visibility_classification", "")
        for row in localization_visibility_rows
        if row.get("visibility_classification")
    )
    upstream_character_class_counts = Counter(
        row.get("recovery_classification", "")
        for row in upstream_character_rows
        if row.get("recovery_classification")
    )
    non_character_class_counts = Counter(
        row.get("recovery_classification", "")
        for row in non_character_rows
        if row.get("recovery_classification")
    )
    tiger_p0_issue_counts = Counter(
        row.get("issue_status", "")
        for row in tiger_p0_rows
        if row.get("issue_status")
    )
    tiger_p0_resolution_counts = Counter(
        row.get("resolution_status", "")
        for row in tiger_p0_rows
        if row.get("resolution_status")
    )
    tiger_p0_live_family_counts = Counter(
        row.get("root_family", "")
        for row in tiger_p0_live_rows
        if row.get("root_family")
    )
    tiger_p0_live_responsibility_counts = Counter(
        row.get("integration_responsibility", "")
        for row in tiger_p0_live_rows
        if row.get("integration_responsibility")
    )
    tiger_p0_barony_status_counts = Counter(
        row.get("candidate_status", "")
        for row in tiger_p0_barony_rows
        if row.get("candidate_status")
    )
    tiger_p0_higher_title_status_counts = Counter(
        row.get("candidate_status", "")
        for row in tiger_p0_higher_title_rows
        if row.get("candidate_status")
    )
    tiger_p0_higher_title_relation_quality_counts = Counter(
        row.get("relation_evidence_quality", "")
        for row in tiger_p0_higher_title_rows
        if row.get("relation_evidence_quality")
    )
    tiger_p0_higher_title_declared_status_counts = Counter(
        row.get("declared_candidate_status", "")
        for row in tiger_p0_higher_title_rows
        if row.get("declared_candidate_status")
    )
    tiger_p0_higher_title_footprint_basis_counts = Counter(
        row.get("candidate_footprint_basis", "")
        for row in tiger_p0_higher_title_rows
        if row.get("candidate_footprint_basis")
    )
    tiger_p0_higher_title_capital_identity_counts = Counter(
        row.get("source_capital_identity_status", "")
        for row in tiger_p0_higher_title_rows
        if row.get("source_capital_identity_status")
    )
    tiger_p0_higher_title_context_action_counts = Counter(
        row.get("usage_context_decision", "")
        for row in tiger_p0_higher_title_rows
        if row.get("usage_context_decision")
    )
    tiger_p0_higher_title_descendant_identity_counts = Counter(
        row.get("identity_descendant_candidate_status", "")
        for row in tiger_p0_higher_title_rows
        if row.get("identity_descendant_candidate_status")
    )
    tiger_p0_higher_title_identity_geometry_counts = Counter(
        row.get("identity_geometry_comparison", "")
        for row in tiger_p0_higher_title_rows
        if row.get("identity_geometry_comparison")
    )
    tiger_p0_higher_title_preferred_source_counts = Counter(
        row.get("preferred_candidate_source", "")
        for row in tiger_p0_higher_title_rows
        if row.get("preferred_candidate_source")
    )
    tiger_p0_higher_no_candidate_context_counts = Counter(
        row.get("usage_context_family", "")
        for row in tiger_p0_higher_no_candidate_rows
        if row.get("usage_context_family")
    )
    tiger_p0_holy_site_location_basis_counts = Counter(
        row.get("context_location_basis", "")
        for row in tiger_p0_higher_no_candidate_rows
        if row.get("usage_context_family") == "holy_site_county_reference"
        and row.get("context_location_basis")
    )
    tiger_p0_holy_site_location_status_counts = Counter(
        row.get("context_location_candidate_status", "")
        for row in tiger_p0_higher_no_candidate_rows
        if row.get("usage_context_family") == "holy_site_county_reference"
        and row.get("context_location_candidate_status")
    )
    relation_refresh_class_counts = Counter(
        row.get("classification", "")
        for row in relation_refresh_rows
        if row.get("classification")
    )
    review_surface_priority_counts: Counter[str] = Counter()
    review_surface_bucket_counts: Counter[str] = Counter()
    for row in review_surface_rows:
        count = int(row.get("finding_count") or 0)
        review_surface_priority_counts[row.get("priority", "")] += count
        review_surface_bucket_counts[row.get("triage_bucket", "")] += count
    runtime_provenance_counts = Counter(
        row["provenance"] for row in runtime_findings
    )
    province_semantic_provenance_counts = Counter(
        row["provenance"] for row in province_semantic_findings
    )
    tiger_config_changed_keys = sorted({
        row["key"] for row in tiger_config_delta
    })
    summary = [
        "# Repo Integration Closure Audit", "",
        "## Revisions", "",
        f"- Yusseter HEAD: `{git_revision(repo_root)}`",
        f"- current asıl mod HEAD: `{git_revision(asil_mod_repo)}`",
        "", "## Findings", "",
        f"- total: `{len(findings)}`",
        f"- blockers: `{severity_counts['blocker']}`",
        f"- reviews: `{severity_counts['review']}`",
        f"- info: `{severity_counts['info']}`",
        "", "### Blocker Classes", "",
        *[
            f"- {domain} / {classification}: `{count}`"
            for (domain, classification), count in blocker_classes.most_common()
        ],
        "", "### Blocker Provenance", "",
        *[
            f"- {provenance}: `{count}`"
            for provenance, count in blocker_provenance.most_common()
        ],
        "", "### Blocker Root Causes", "",
        f"- independent root causes: `{len(blocker_root_causes)}`",
        f"- represented raw blocker rows: `{blocker_root_raw_count}`",
        *[
            f"- {subsystem} / {classification}: `{count}`"
            for (subsystem, classification), count
            in blocker_root_classes.most_common()
        ],
        "", "### Root-Cause Provenance", "",
        *[
            f"- {provenance}: `{count}`"
            for provenance, count in blocker_root_provenance.most_common()
        ],
        "", "### Work Queue Policy", "",
        (
            f"- active integration/Yusseter roots: "
            f"`{len(active_blocker_roots)}` roots / "
            f"`{active_blocker_raw_count}` raw blocker rows"
        ),
        (
            f"- deferred shared asıl-mod roots: "
            f"`{len(deferred_asil_mod_roots)}` roots / "
            f"`{deferred_asil_mod_raw_count}` raw blocker rows"
        ),
        "- Deferred roots retain blocker severity and remain in the canonical root report.",
        "- Deferred roots are revisited only in the final asıl-mod baseline cleanup pass.",
        *[
            f"- deferred basis {basis}: `{count}`"
            for basis, count in deferred_basis_counts.most_common()
        ],
        "", "## Coverage", "",
        *[f"- {status}: `{count}`" for status, count in sorted(coverage_counts.items())],
        "", "### Incomplete Or Stale Areas", "",
        *[
            f"- {row['domain']} / {row['subdomain'] or 'all'}: "
            f"`{row['coverage_status']}` - {row['notes']}"
            for row in incomplete
        ],
        "", "## Evidence", "",
        f"- semantic input: `{semantic_evidence}`",
        f"- finding classes: `{len(classification_counts)}`",
        f"- effective localization requirements: `{len(localization_requirements)}`",
        (
            f"- Missing title-base visibility classification: "
            f"`{localization_visibility_status}`; "
            f"blocker `{localization_visibility_applied['blocker']}`, "
            f"review `{localization_visibility_applied['review']}`, "
            f"info `{localization_visibility_applied['info']}`"
        ),
        *[
            f"- Missing title-base visibility {classification}: `{count}`"
            for classification, count
            in localization_visibility_class_counts.most_common()
        ],
        (
            f"- Upstream-integration character recovery classification: "
            f"`{upstream_character_status}`; roots "
            f"`{len(upstream_character_rows)}`; represented raw blockers "
            f"`{upstream_character_raw_count}`"
        ),
        *[
            f"- Upstream character recovery {classification}: `{count}`"
            for classification, count
            in upstream_character_class_counts.most_common()
        ],
        (
            f"- Non-character blocker recovery classification: "
            f"`{non_character_status}`; roots `{len(non_character_rows)}`; "
            f"represented raw blockers `{non_character_raw_count}`"
        ),
        *[
            f"- Non-character recovery {classification}: `{count}`"
            for classification, count
            in non_character_class_counts.most_common()
        ],
        (
            f"- Tiger P0 root triage: `{tiger_p0_status}`; roots "
            f"`{len(tiger_p0_rows)}`; represented raw rows "
            f"`{tiger_p0_raw_count}`; independent verified live-error roots "
            f"`{len(tiger_p0_live_rows)}`; verified live raw rows "
            f"`{tiger_p0_live_raw_count}`; undefined-barony candidates "
            f"`{len(tiger_p0_barony_rows)}`; undefined higher-title candidates "
            f"`{len(tiger_p0_higher_title_rows)}`; higher-title no-candidate "
            f"context decisions `{len(tiger_p0_higher_no_candidate_rows)}`; fallback "
            f"`{tiger_p0_fallback_count}`"
        ),
        *[
            f"- Tiger P0 issue {status}: `{count}`"
            for status, count in tiger_p0_issue_counts.most_common()
        ],
        *[
            f"- Tiger P0 resolution {status}: `{count}`"
            for status, count in tiger_p0_resolution_counts.most_common()
        ],
        *[
            f"- Tiger P0 live-error family {family}: `{count}`"
            for family, count in tiger_p0_live_family_counts.most_common()
        ],
        *[
            f"- Tiger P0 live-error responsibility {responsibility}: `{count}`"
            for responsibility, count
            in tiger_p0_live_responsibility_counts.most_common()
        ],
        *[
            f"- Tiger P0 undefined-barony {status}: `{count}`"
            for status, count in tiger_p0_barony_status_counts.most_common()
        ],
        *[
            f"- Tiger P0 undefined higher-title {status}: `{count}`"
            for status, count
            in tiger_p0_higher_title_status_counts.most_common()
        ],
        *[
            f"- Tiger P0 higher-title relation quality {quality}: `{count}`"
            for quality, count
            in tiger_p0_higher_title_relation_quality_counts.most_common()
        ],
        *[
            f"- Tiger P0 higher-title declared status {status}: `{count}`"
            for status, count
            in tiger_p0_higher_title_declared_status_counts.most_common()
        ],
        *[
            f"- Tiger P0 higher-title footprint basis {basis}: `{count}`"
            for basis, count
            in tiger_p0_higher_title_footprint_basis_counts.most_common()
        ],
        *[
            f"- Tiger P0 higher-title capital identity {status}: `{count}`"
            for status, count
            in tiger_p0_higher_title_capital_identity_counts.most_common()
        ],
        *[
            f"- Tiger P0 higher-title context action {action}: `{count}`"
            for action, count
            in tiger_p0_higher_title_context_action_counts.most_common()
        ],
        *[
            f"- Tiger P0 higher-title descendant identity {status}: `{count}`"
            for status, count
            in tiger_p0_higher_title_descendant_identity_counts.most_common()
        ],
        *[
            f"- Tiger P0 higher-title identity versus geometry {status}: `{count}`"
            for status, count
            in tiger_p0_higher_title_identity_geometry_counts.most_common()
        ],
        *[
            f"- Tiger P0 higher-title preferred candidate source {source}: `{count}`"
            for source, count
            in tiger_p0_higher_title_preferred_source_counts.most_common()
        ],
        *[
            f"- Tiger P0 higher-title no-candidate context {context}: `{count}`"
            for context, count
            in tiger_p0_higher_no_candidate_context_counts.most_common()
        ],
        *[
            f"- Tiger P0 holy-site location basis {basis}: `{count}`"
            for basis, count
            in tiger_p0_holy_site_location_basis_counts.most_common()
        ],
        *[
            f"- Tiger P0 holy-site location status {status}: `{count}`"
            for status, count
            in tiger_p0_holy_site_location_status_counts.most_common()
        ],
        (
            f"- Province relation current refresh: `{relation_refresh_status}`; "
            f"rows `{len(relation_refresh_rows)}`; manual review "
            f"`{len(relation_refresh_manual_rows)}`; manifest exact "
            f"`{'yes' if relation_manifest_hash_match else 'no'}`; target "
            f"tracking stale `{'yes' if relation_target_tracking_stale else 'no'}`; "
            f"status whitespace anomalies `{relation_status_whitespace_count}`"
        ),
        *[
            f"- Province relation {classification}: `{count}`"
            for classification, count in relation_refresh_class_counts.most_common()
        ],
        (
            f"- Review-surface triage: `{review_surface_status}`; raw rows "
            f"`{review_surface_raw_count}`; groups `{len(review_surface_rows)}`; "
            f"fallback `{review_surface_fallback_count}`"
        ),
        *[
            f"- Review-surface priority {priority}: `{count}`"
            for priority, count in sorted(review_surface_priority_counts.items())
        ],
        *[
            f"- Review-surface bucket {bucket}: `{count}`"
            for bucket, count in review_surface_bucket_counts.most_common()
        ],
        f"- Tiger shared asıl-mod baseline: `{tiger_provenance_counts['shared_asil_mod_baseline']}`",
        f"- Tiger Yusseter current-only: `{tiger_provenance_counts['yusseter_current_only']}`",
        *[
            f"- Tiger current-only {priority}: `{count}`"
            for priority, count in sorted(tiger_priority_counts.items())
        ],
        (
            f"- Tiger current-only classified root causes: "
            f"`{len(tiger_root_rows)}` from `{len(tiger_current_only_priority)}` raw rows"
        ),
        (
            f"- Generic findings superseded by exact Tiger root-cause evidence: "
            f"`{tiger_superseded_generic_count}`"
        ),
        *[
            f"- Tiger classified root-cause {priority}: `{count}`"
            for priority, count in sorted(tiger_root_priority_counts.items())
        ],
        *[
            f"- Tiger classified root-cause {provenance}: `{count}`"
            for provenance, count in tiger_root_provenance_counts.most_common()
        ],
        f"- Tiger/static blocker exact-line overlaps: `{len(tiger_overlaps)}`",
        (
            f"- Dynamic GetTitleByKey inventory: `{dynamic_title_inventory_count}`; "
            f"undefined findings: `{dynamic_title_raw_count}`; "
            f"unique closure findings: `{len(dynamic_title_findings)}`; "
            f"exact Tiger overlaps excluded: `{dynamic_title_tiger_overlap_count}`"
        ),
        *[
            f"- Dynamic title-reference {classification}: `{count}`"
            for classification, count in dynamic_title_class_counts.most_common()
        ],
        f"- Bookmark/runtime compact findings: `{len(runtime_findings)}` across `{runtime_date_count}` dates",
        *[
            f"- Bookmark/runtime {provenance}: `{count}`"
            for provenance, count in runtime_provenance_counts.most_common()
        ],
        (
            f"- Province-history semantic compact findings: "
            f"`{len(province_semantic_findings)}` across "
            f"`{province_semantics_date_count}` dates"
        ),
        *[
            f"- Province-history semantics {provenance}: `{count}`"
            for provenance, count in province_semantic_provenance_counts.most_common()
        ],
        (
            "- Tiger minimal-config equivalence: "
            f"Yusseter `{current_config_meta.get('standard_total', 0)}` -> "
            f"`{current_config_meta.get('minimal_total', 0)}`; asıl mod "
            f"`{source_config_meta.get('standard_total', 0)}` -> "
            f"`{source_config_meta.get('minimal_total', 0)}`"
        ),
        (
            "- Tiger minimal-config changed key classes: `"
            + (" | ".join(tiger_config_changed_keys) or "none") + "`"
        ),
        "- No live BookmarksGit source file is modified by this audit.", "",
    ]
    (output_dir / "repo_integration_closure_summary.md").write_text(
        "\n".join(summary), encoding="utf-8"
    )

    print(f"output: {output_dir}")
    print(f"findings: {len(findings)}; severity: {dict(severity_counts)}")
    print(f"coverage: {dict(coverage_counts)}")
    print(f"localization requirements: {len(localization_requirements)}")
    print(f"Tiger provenance: {dict(tiger_provenance_counts)}")
    print(f"Tiger/static overlaps: {len(tiger_overlaps)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
