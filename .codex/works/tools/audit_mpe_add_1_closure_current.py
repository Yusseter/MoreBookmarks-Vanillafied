from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import audit_mpe_add_1_province_history_levi_source as province_history_audit
import audit_repo_integration_closure as closure
from apply_mpe_add_1_consistency_fixes import default_map_category_ids


DEFAULT_VANILLA_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
)
OUTPUT_RELATIVE = Path(
    ".codex/works/analysis/generated/mpe_import_add_1/closure_audit"
)
IMPORT_RELATIVE = Path(
    ".codex/works/analysis/generated/mpe_import_add_1"
)
LOCATOR_FILES = (
    "activities.txt",
    "building_locators.txt",
    "combat_locators.txt",
    "player_stack_locators.txt",
    "siege_locators.txt",
    "special_building_locators.txt",
)
SCOPE_TITLE_FIELDS = (
    "barony",
    "county",
    "duchy",
    "parent_title",
    "related_title",
    "title",
)
ID_RE = re.compile(r"^\s*id\s*=\s*(\d+)\b")
TERRAIN_RE = re.compile(r"^\s*(\d+)\s*=")

# These remaps are the recorded result of the MPE consistency/structure pass.
# The current landed hierarchy is canonical; the original import report remains
# provenance evidence, not an instruction to move these titles back.
ACCEPTED_PARENT_REMAPS = {
    ("county", "c_cherson", "c_kerch"),
    ("county", "c_dvaletia", "c_ossetia"),
    ("county", "c_kerch", "c_korchev"),
    ("county", "c_lazia", "c_avaria"),
    ("county", "c_majar", "c_don_portage"),
    ("duchy", "d_azov", "d_khazaria"),
    ("duchy", "d_klimata", "d_cherson"),
    ("duchy", "d_klimata", "d_tmutarakan"),
    ("duchy", "d_sarir", "d_derbent"),
    ("duchy", "d_sarir", "d_simsir"),
}


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a current-state MPE Add 1 closure audit"
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument(
        "--vanilla-game-root", type=Path, default=DEFAULT_VANILLA_ROOT
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def finding(
    subdomain: str,
    classification: str,
    severity: str,
    confidence: str,
    path: str,
    line: str | int,
    object_id: str,
    reason: str,
    recommendation: str,
    *,
    current_value: str = "",
    candidate_value: str = "",
    provenance: str = "mpe_add_1_integration",
    covered_by_repo_closure: str = "no",
) -> dict[str, str]:
    return {
        "domain": "mpe_add_1",
        "subdomain": subdomain,
        "classification": classification,
        "severity": severity,
        "confidence": confidence,
        "path": path,
        "line": str(line),
        "object": object_id,
        "current_value": current_value,
        "candidate_value": candidate_value,
        "reason": reason,
        "recommendation": recommendation,
        "source_report": (
            ".codex/works/analysis/generated/mpe_import_add_1/"
            "mpe_landed_titles_hierarchy_import_report.csv"
        ),
        "provenance": provenance,
        "covered_by_repo_closure": covered_by_repo_closure,
    }


def title_values(row: dict[str, str]) -> set[str]:
    return {
        row.get(field, "").strip()
        for field in SCOPE_TITLE_FIELDS
        if row.get(field, "").strip().startswith(("e_", "k_", "d_", "c_", "b_"))
    }


def intentional_exclusions(path: Path) -> set[str]:
    return {
        row.get("item", "")
        for row in read_csv(path)
        if row.get("category") == "scope_excluded_title"
        and row.get("current_classification", "").startswith(
            "scope_excluded_intentional"
        )
    }


def parse_locator_inventory(mod_root: Path) -> dict[int, list[str]]:
    result: dict[int, list[str]] = defaultdict(list)
    root = mod_root / "gfx/map/map_object_data"
    for file_name in LOCATOR_FILES:
        path = root / file_name
        if not path.exists():
            continue
        for line_number, raw in enumerate(
            path.read_text(encoding="utf-8-sig", errors="replace").splitlines(),
            start=1,
        ):
            match = ID_RE.match(closure.strip_comment(raw))
            if match:
                result[int(match.group(1))].append(
                    f"BookmarksGit/gfx/map/map_object_data/{file_name}:{line_number}"
                )
    return dict(result)


def parse_terrain_inventory(mod_root: Path) -> dict[int, list[str]]:
    result: dict[int, list[str]] = defaultdict(list)
    root = mod_root / "common/province_terrain"
    for path in sorted(root.rglob("*.txt")):
        relative = path.relative_to(mod_root.parent).as_posix()
        for line_number, raw in enumerate(
            path.read_text(encoding="utf-8-sig", errors="replace").splitlines(),
            start=1,
        ):
            match = TERRAIN_RE.match(closure.strip_comment(raw))
            if match:
                result[int(match.group(1))].append(f"{relative}:{line_number}")
    return dict(result)


def parse_history_inventory(
    repo_root: Path, relative: str, header: re.Pattern[str]
) -> tuple[dict[str, list[tuple[str, int]]], list[dict[str, str]]]:
    paths = sorted((repo_root / relative).rglob("*.txt"))
    return closure.parse_top_level_headers(paths, repo_root, header)


def main_closure_rows(repo_root: Path) -> list[dict[str, str]]:
    path = (
        repo_root
        / ".codex/works/analysis/generated/repo_integration_closure/"
        "repo_integration_closure_findings.csv"
    )
    return [row for row in read_csv(path) if row.get("domain") != "mpe_add_1"]


def has_repo_cover(
    rows: list[dict[str, str]], object_id: str, domains: set[str]
) -> bool:
    return any(
        row.get("severity") == "blocker"
        and row.get("object") == object_id
        and row.get("domain") in domains
        for row in rows
    )


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    mod_root = repo_root / "BookmarksGit"
    vanilla_root = args.vanilla_game_root.resolve()
    import_dir = repo_root / IMPORT_RELATIVE
    output_dir = args.output_dir or (repo_root / OUTPUT_RELATIVE)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    hierarchy_path = import_dir / "mpe_landed_titles_hierarchy_import_report.csv"
    hierarchy_rows = read_csv(hierarchy_path)
    old_classification_path = (
        output_dir / "mpe_add_1_closure_issue_classification_current.csv"
    )
    excluded_intent = intentional_exclusions(old_classification_path)
    repo_findings = main_closure_rows(repo_root)

    landed_path = mod_root / "common/landed_titles/00_landed_titles.txt"
    landed_doc = province_history_audit.LandedDoc(landed_path)
    current_titles = set(landed_doc.by_name)
    scope_titles = set().union(*(title_values(row) for row in hierarchy_rows))
    active_titles = scope_titles & current_titles
    inactive_titles = scope_titles - current_titles

    rows_by_barony: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in hierarchy_rows:
        barony = row.get("barony", "").strip()
        if barony:
            rows_by_barony[barony].append(row)

    definition, _ = closure.parse_definition_file(
        mod_root / "map_data/definition.csv",
        "BookmarksGit/map_data/definition.csv",
    )
    pixel_inventory = {
        int(row["province_id"]): row
        for row in read_csv(
            repo_root
            / ".codex/works/analysis/generated/repo_integration_closure/"
            "map_definition_pixel_audit/definition_pixel_inventory.csv"
        )
        if row.get("province_id", "").isdigit()
    }
    locator_inventory = parse_locator_inventory(mod_root)
    terrain_inventory = parse_terrain_inventory(mod_root)
    province_history, province_braces = parse_history_inventory(
        repo_root, "BookmarksGit/history/provinces", closure.NUMERIC_HEADER_RE
    )
    title_history, title_braces = parse_history_inventory(
        repo_root, "BookmarksGit/history/titles", closure.TITLE_HEADER_RE
    )
    effective_history_ids = closure.collect_effective_province_history_ids(
        repo_root, vanilla_root
    )
    default_categories = default_map_category_ids()
    mod_loc, _, _ = closure.scan_localization(
        mod_root / "localization", repo_root, "mod"
    )
    vanilla_loc, _, _ = closure.scan_localization(
        vanilla_root / "localization", vanilla_root, "vanilla"
    )
    effective_loc = set(mod_loc) | set(vanilla_loc)

    current_owner = dict(landed_doc.province_to_barony)
    active_provinces = {
        province_id
        for title, province_id in landed_doc.barony_to_province.items()
        if title in active_titles
    }
    findings: list[dict[str, str]] = []
    findings.extend(province_braces)
    findings.extend(title_braces)
    scope_rows: list[dict[str, str]] = []

    for title in sorted(inactive_titles):
        intentional = title in excluded_intent
        if not intentional:
            findings.append(finding(
                "landed_titles",
                "scope_title_missing_without_exclusion_decision",
                "blocker",
                "high",
                "BookmarksGit/common/landed_titles/00_landed_titles.txt",
                "",
                title,
                "title from the MPE Add 1 hierarchy scope is absent without a recorded exclusion decision",
                "restore_title_or_record_an_explicit_scope_exclusion",
            ))
        if title in title_history:
            locations = " | ".join(
                f"{path}:{line}" for path, line in title_history[title]
            )
            findings.append(finding(
                "title_history",
                "scope_excluded_title_history_residue",
                "blocker",
                "high",
                title_history[title][0][0],
                title_history[title][0][1],
                title,
                "title is intentionally outside the live scope but still has title history",
                "remove_or_remap_excluded_title_history",
                current_value=locations,
                covered_by_repo_closure=(
                    "yes" if has_repo_cover(
                        repo_findings, title, {"title_history"}
                    ) else "no"
                ),
            ))

    for title in sorted(active_titles):
        if title not in effective_loc:
            findings.append(finding(
                "localization",
                "active_scope_title_missing_localization",
                "blocker",
                "high",
                "BookmarksGit/localization",
                "",
                title,
                "active MPE scope title has no effective English localization",
                "add_english_localization_from_an_authoritative_source",
                covered_by_repo_closure=(
                    "yes" if has_repo_cover(
                        repo_findings, title, {"localization"}
                    ) else "no"
                ),
            ))
        if title.startswith(("e_", "k_", "d_", "c_")):
            adj = f"{title}_adj"
            if adj not in effective_loc:
                findings.append(finding(
                    "localization",
                    "active_scope_title_missing_adj_localization",
                    "review",
                    "high",
                    "BookmarksGit/localization",
                    "",
                    adj,
                    "active MPE scope title has no effective English adjective localization",
                    "add_or_confirm_adj_localization",
                    covered_by_repo_closure=(
                        "yes" if has_repo_cover(
                            repo_findings, adj, {"localization"}
                        ) else "no"
                    ),
                ))

    scoped_cultural_names: set[str] = set()
    for title in active_titles:
        for entry in landed_doc.entries_for(title):
            start = int(entry["start"])
            end = int(entry["end"])
            scoped_cultural_names.update(
                closure.CN_RE.findall("\n".join(landed_doc.lines[start : end + 1]))
            )
    for key in sorted(scoped_cultural_names):
        if key not in effective_loc:
            findings.append(finding(
                "localization",
                "active_scope_cultural_name_missing_localization",
                "blocker",
                "high",
                "BookmarksGit/localization",
                "",
                key,
                "cultural_names key used by an active MPE scope title is not localized",
                "add_english_cultural_name_localization",
                covered_by_repo_closure=(
                    "yes" if has_repo_cover(
                        repo_findings, key, {"localization"}
                    ) else "no"
                ),
            ))

    checked_residue_ids: set[tuple[str, int]] = set()
    for barony, source_rows in sorted(rows_by_barony.items()):
        active = barony in current_titles
        current_province = landed_doc.barony_to_province.get(barony)
        entry = (
            landed_doc.entry_for_barony(barony, current_province)
            if current_province is not None else None
        )
        parents = dict(entry.get("parents", {})) if entry else {}
        target_ids = {
            int(row["target_id"])
            for row in source_rows
            if row.get("target_id", "").isdigit()
        }
        existing_ids = {
            int(row["existing_province"])
            for row in source_rows
            if row.get("existing_province", "").isdigit()
        }
        old_ids = {
            int(row["old_mpe_id"])
            for row in source_rows
            if row.get("old_mpe_id", "").isdigit()
        }
        source_counties = sorted({
            row.get("county", "") for row in source_rows if row.get("county", "")
        })
        source_duchies = sorted({
            row.get("duchy", "") for row in source_rows if row.get("duchy", "")
        })
        scope_rows.append({
            "barony": barony,
            "scope_status": "active" if active else "excluded",
            "intentional_exclusion": "yes" if barony in excluded_intent else "no",
            "current_province_id": str(current_province or ""),
            "current_county": str(parents.get("c", "")),
            "current_duchy": str(parents.get("d", "")),
            "source_counties": " | ".join(source_counties),
            "source_duchies": " | ".join(source_duchies),
            "target_ids": " | ".join(map(str, sorted(target_ids))),
            "existing_ids": " | ".join(map(str, sorted(existing_ids))),
            "old_mpe_ids": " | ".join(map(str, sorted(old_ids))),
        })

        if active:
            if current_province is None:
                findings.append(finding(
                    "landed_titles",
                    "active_scope_barony_missing_province",
                    "blocker",
                    "high",
                    "BookmarksGit/common/landed_titles/00_landed_titles.txt",
                    entry.get("start", "") if entry else "",
                    barony,
                    "active MPE barony has no province assignment",
                    "assign_a_valid_current_province",
                ))
                continue
            meta = definition.get(current_province)
            pixel_row = pixel_inventory.get(current_province, {})
            pixel_count = int(pixel_row.get("map_pixel_count", "0") or 0)
            if not meta:
                findings.append(finding(
                    "definition",
                    "active_scope_province_missing_definition",
                    "blocker",
                    "high",
                    "BookmarksGit/map_data/definition.csv",
                    "",
                    str(current_province),
                    f"active MPE barony {barony} references a missing definition ID",
                    "add_or_restore_definition_row",
                    covered_by_repo_closure=(
                        "yes" if has_repo_cover(
                            repo_findings, str(current_province), {"map_identity"}
                        ) else "no"
                    ),
                ))
            else:
                name = str(meta.get("name", ""))
                if name.startswith("zz_placeholder_"):
                    findings.append(finding(
                        "definition",
                        "active_scope_province_uses_placeholder_definition",
                        "blocker",
                        "high",
                        "BookmarksGit/map_data/definition.csv",
                        meta.get("line", ""),
                        str(current_province),
                        f"active MPE barony {barony} still uses a placeholder definition",
                        "restore_imported_definition_identity",
                    ))
            if pixel_count == 0:
                findings.append(finding(
                    "provinces_png",
                    "active_scope_province_missing_pixels",
                    "blocker",
                    "high",
                    "BookmarksGit/map_data/provinces.png",
                    "",
                    str(current_province),
                    f"active MPE barony {barony} has no pixels in provinces.png",
                    "restore_or_remap_province_geometry",
                    covered_by_repo_closure=(
                        "yes" if has_repo_cover(
                            repo_findings, str(current_province), {"binary_map"}
                        ) else "no"
                    ),
                ))
            bad_categories = sorted(default_categories.get(current_province, set()))
            if bad_categories:
                findings.append(finding(
                    "default_map",
                    "active_scope_land_province_in_nonland_category",
                    "blocker",
                    "high",
                    "BookmarksGit/map_data/default.map",
                    "",
                    str(current_province),
                    f"active MPE land barony {barony} is registered as {' | '.join(bad_categories)}",
                    "remove_active_land_province_from_nonland_default_map_category",
                    current_value=" | ".join(bad_categories),
                ))
            locator_locations = locator_inventory.get(current_province, [])
            present_locator_files = {
                value.split("/")[-1].split(":", 1)[0]
                for value in locator_locations
            }
            missing_locators = sorted(set(LOCATOR_FILES) - present_locator_files)
            if missing_locators:
                findings.append(finding(
                    "map_object_locators",
                    "active_scope_province_missing_locator_blocks",
                    "blocker",
                    "high",
                    "BookmarksGit/gfx/map/map_object_data",
                    "",
                    str(current_province),
                    f"active MPE barony {barony} lacks locator blocks in some required files",
                    "restore_missing_locator_blocks_from_valid_current_geometry",
                    current_value=" | ".join(sorted(present_locator_files)),
                    candidate_value=" | ".join(missing_locators),
                ))
            current_county = str(parents.get("c", ""))
            county_capital = (
                landed_doc.capital_barony_for_county(current_county)
                if current_county else ""
            )
            if (
                current_province not in effective_history_ids
                and county_capital == barony
            ):
                findings.append(finding(
                    "province_history",
                    "active_scope_county_capital_missing_effective_history",
                    "blocker",
                    "high",
                    "BookmarksGit/history/provinces",
                    "",
                    str(current_province),
                    f"active MPE county capital {barony} has no effective province-history block",
                    "add_or_restore_county_capital_province_history",
                    covered_by_repo_closure=(
                        "yes" if has_repo_cover(
                            repo_findings, str(current_province), {"province_history"}
                        ) else "no"
                    ),
                ))
            if current_province not in terrain_inventory:
                findings.append(finding(
                    "province_terrain",
                    "active_scope_province_missing_explicit_terrain",
                    "review",
                    "medium",
                    "BookmarksGit/common/province_terrain",
                    "",
                    str(current_province),
                    f"active MPE barony {barony} has no explicit mod terrain assignment",
                    "confirm_vanilla_fallback_or_add_explicit_terrain",
                ))
            expected_counties = set(source_counties)
            expected_duchies = set(source_duchies)
            current_duchy = str(parents.get("d", ""))
            if expected_counties and current_county not in expected_counties:
                accepted = any(
                    ("county", source, current_county) in ACCEPTED_PARENT_REMAPS
                    for source in expected_counties
                )
                findings.append(finding(
                    "landed_titles",
                    (
                        "accepted_current_hierarchy_relocation"
                        if accepted
                        else "active_scope_county_path_differs_from_import"
                    ),
                    "info" if accepted else "review",
                    "high" if accepted else "medium",
                    "BookmarksGit/common/landed_titles/00_landed_titles.txt",
                    int(entry["start"]) + 1 if entry else "",
                    barony,
                    (
                        "current county placement is a recorded MPE consistency relocation"
                        if accepted
                        else "current county placement differs from the original MPE hierarchy report"
                    ),
                    (
                        "none_current_hierarchy_is_canonical"
                        if accepted
                        else "confirm_intentional_relocation"
                    ),
                    current_value=current_county,
                    candidate_value=" | ".join(source_counties),
                ))
            if expected_duchies and current_duchy not in expected_duchies:
                accepted = any(
                    ("duchy", source, current_duchy) in ACCEPTED_PARENT_REMAPS
                    for source in expected_duchies
                )
                findings.append(finding(
                    "landed_titles",
                    (
                        "accepted_current_hierarchy_relocation"
                        if accepted
                        else "active_scope_duchy_path_differs_from_import"
                    ),
                    "info" if accepted else "review",
                    "high" if accepted else "medium",
                    "BookmarksGit/common/landed_titles/00_landed_titles.txt",
                    int(entry["start"]) + 1 if entry else "",
                    barony,
                    (
                        "current duchy placement is a recorded MPE consistency relocation"
                        if accepted
                        else "current duchy placement differs from the original MPE hierarchy report"
                    ),
                    (
                        "none_current_hierarchy_is_canonical"
                        if accepted
                        else "confirm_intentional_relocation"
                    ),
                    current_value=current_duchy,
                    candidate_value=" | ".join(source_duchies),
                ))

        candidate_ids = target_ids | existing_ids | old_ids
        if current_province is not None:
            candidate_ids.discard(current_province)
        for candidate_id in sorted(candidate_ids):
            residue_key = (barony, candidate_id)
            if residue_key in checked_residue_ids:
                continue
            checked_residue_ids.add(residue_key)
            owner = current_owner.get(candidate_id, "")
            if owner:
                continue
            pixel_row = pixel_inventory.get(candidate_id, {})
            runtime_locations = (
                locator_inventory.get(candidate_id, [])
                + [
                    f"{path}:{line}"
                    for path, line in province_history.get(str(candidate_id), [])
                ]
                + terrain_inventory.get(candidate_id, [])
            )
            map_pixels = int(pixel_row.get("map_pixel_count", "0") or 0)
            if runtime_locations or map_pixels:
                classification = (
                    "scope_excluded_province_runtime_residue"
                    if not active
                    else "superseded_province_runtime_residue"
                )
                covered = has_repo_cover(
                    repo_findings,
                    str(candidate_id),
                    {"binary_map", "map_objects", "province_history", "map_identity"},
                )
                findings.append(finding(
                    "alias_placeholder_cleanup",
                    classification,
                    "blocker",
                    "high",
                    runtime_locations[0].rsplit(":", 1)[0]
                    if runtime_locations else "BookmarksGit/map_data/provinces.png",
                    runtime_locations[0].rsplit(":", 1)[1]
                    if runtime_locations else "",
                    str(candidate_id),
                    f"province ID associated with {barony} has no live landed owner but still has runtime content",
                    "remove_or_remap_stale_runtime_references_without_reactivating_the_excluded_title",
                    current_value=(
                        " | ".join(runtime_locations)
                        + (f" | map_pixels={map_pixels}" if map_pixels else "")
                    ).strip(" |"),
                    candidate_value=str(current_province or "scope_excluded"),
                    covered_by_repo_closure="yes" if covered else "no",
                ))

    summary_counts = Counter(row["severity"] for row in findings)
    class_counts = Counter(row["classification"] for row in findings)
    uncovered_blockers = [
        row for row in findings
        if row["severity"] == "blocker"
        and row.get("covered_by_repo_closure") != "yes"
    ]
    write_csv(output_dir / "mpe_add_1_current_closure_findings.csv", findings)
    write_csv(output_dir / "mpe_add_1_current_scope.csv", scope_rows)

    summary = [
        "# MPE Add 1 Current Closure Audit",
        "",
        f"- hierarchy rows: `{len(hierarchy_rows)}`",
        f"- scoped titles: `{len(scope_titles)}`",
        f"- active scoped titles: `{len(active_titles)}`",
        f"- intentionally excluded scoped titles: `{len(inactive_titles & excluded_intent)}`",
        f"- active scoped baronies: `{sum(row['scope_status'] == 'active' for row in scope_rows)}`",
        f"- active scoped provinces: `{len(active_provinces)}`",
        f"- findings: `{len(findings)}`",
        f"- blockers: `{summary_counts['blocker']}`",
        f"- reviews: `{summary_counts['review']}`",
        f"- infos: `{summary_counts['info']}`",
        f"- blockers not already represented in repo closure: `{len(uncovered_blockers)}`",
        "",
        "## Finding Classes",
        "",
    ]
    summary.extend(
        f"- `{name}`: `{count}`" for name, count in class_counts.most_common()
    )
    summary.extend([
        "",
        "## Rules",
        "",
        "- Current landed ownership is canonical after recorded MPE relocations.",
        "- An excluded title may leave localization, but not runtime title/province history, locators, terrain, or map pixels.",
        "- Placeholder definition/default.map registration alone is not a residue blocker.",
        "- Findings already represented by the repo-wide closure remain linked instead of being treated as a second root cause.",
        "- No live BookmarksGit source file is modified by this audit.",
    ])
    (output_dir / "mpe_add_1_current_closure_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print(f"scope_titles={len(scope_titles)}")
    print(f"active_baronies={sum(row['scope_status'] == 'active' for row in scope_rows)}")
    print(f"findings={len(findings)}")
    print(f"blockers={summary_counts['blocker']}")
    print(f"uncovered_blockers={len(uncovered_blockers)}")
    print(f"summary={output_dir / 'mpe_add_1_current_closure_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
