from __future__ import annotations

import argparse
import csv
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from audit_landed_title_source_identity import parse_landed_titles_path


INPUT_PATH = (
    "development/analysis/generated/repo_integration_closure/"
    "tiger_current_only_classification/ck3_tiger_current_only_root_causes.csv"
)
OUTPUT_PATH = (
    "development/analysis/generated/repo_integration_closure/"
    "tiger_p0_root_triage"
)
DEFAULT_ASIL_MOD_REPO = (
    Path(__file__).resolve().parents[2].parent / "Leviathonlx MoreBookmarks-Plus"
)
DEFAULT_PREMERGE_REVISION = "09588cbb5212a31bc4a373b6990b2c4da1203a35"
PROVINCE_RELATION_REFRESH_PATH = (
    "development/analysis/generated/province_relation_mapping/"
    "current_state_refresh/province_relation_master.csv"
)
CANONICAL_PROVINCE_RELATION_PATH = (
    "development/pipeline_inputs/province_relations/"
    "province_relation_baseline.csv"
)
TITLE_RELATION_PATH = (
    "development/pipeline_inputs/title_relations/curated_title_relations.csv"
)
HIGHER_TITLE_NO_CANDIDATE_STATUSES = {
    "source_title_not_defined_in_current_asil_mod",
    "source_title_has_no_descendant_province_footprint",
    "source_footprint_absent_from_relation_refresh",
    "resolved_targets_have_no_same_tier_landed_candidate",
}


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Triage P0 current-only Tiger root causes without applying fixes."
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument(
        "--asil-mod-repo", type=Path, default=DEFAULT_ASIL_MOD_REPO
    )
    parser.add_argument(
        "--premerge-revision", default=DEFAULT_PREMERGE_REVISION
    )
    parser.add_argument(
        "--province-relation-report",
        type=Path,
        default=Path(PROVINCE_RELATION_REFRESH_PATH),
    )
    parser.add_argument(
        "--canonical-province-relation",
        type=Path,
        default=Path(CANONICAL_PROVINCE_RELATION_PATH),
    )
    parser.add_argument(
        "--title-relation",
        type=Path,
        default=Path(TITLE_RELATION_PATH),
    )
    parser.add_argument("--source-landed-titles", type=Path, default=None)
    parser.add_argument("--current-landed-titles", type=Path, default=None)
    parser.add_argument(
        "--target-tracking",
        type=Path,
        default=Path(
            "development/analysis/generated/province_definition/"
            "final_orijinal_tracking_preserve_old_ids.csv"
        ),
    )
    parser.add_argument(
        "--target-image",
        type=Path,
        default=Path("BookmarksGit/map_data/provinces.png"),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_title_relation_reverse(path: Path) -> dict[str, list[str]]:
    reverse: dict[str, set[str]] = defaultdict(set)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle, skipinitialspace=True):
            row = {
                (key or "").strip(): (value or "").strip()
                for key, value in raw.items()
            }
            current_titles = [
                token.strip()
                for token in re.split(r"[&;]", row.get("source_title_id", ""))
                if token.strip()
            ]
            source_titles = [
                token.replace("(second)", "").strip()
                for token in re.split(r"[&;]", row.get("mod_title_id", ""))
                if token.replace("(second)", "").strip()
            ]
            for source_title in source_titles:
                reverse[source_title].update(current_titles)
    return {
        source_title: sorted(current_titles)
        for source_title, current_titles in reverse.items()
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def git_revision(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def resolve_repo_path(repo_root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def classify(row: dict[str, str]) -> dict[str, str]:
    classification = row.get("classification", "")
    provenance = row.get("line_provenance", "")
    source_object = row.get("source_object", "")
    candidate = row.get("candidate_object", "")

    confirmed: dict[str, tuple[str, str]] = {
        "history_effect_title_reference_candidate": (
            "confirmed_history_effect_title_remap_candidate",
            "replace the obsolete set_coa title key with the reviewed current title",
        ),
        "history_effect_missing_title_scope_prefix": (
            "confirmed_history_effect_scope_prefix_candidate",
            "add the required title: scope prefix and rerun Tiger",
        ),
        "undefined_reader_variable_or_numeric_value": (
            "confirmed_reader_variable_definition_error",
            "restore the reader variable definition or replace it with a reviewed number",
        ),
        "invalid_title_tier_relationship": (
            "confirmed_title_history_tier_error",
            "repair the liege mapping so the liege is strictly higher tier",
        ),
        "parse_or_sentinel_order_error": (
            "confirmed_file_sentinel_order_error",
            "move the all--1 adjacency sentinel to the final data row",
        ),
        "stale_character_alias_candidate": (
            "confirmed_stale_character_alias_candidate",
            "verify the same-person evidence, then replace the stale holder alias",
        ),
        "stale_redundant_region_title_reference": (
            "confirmed_redundant_region_reference_candidate",
            "remove the redundant undefined region token after region membership review",
        ),
    }
    if classification in confirmed:
        recovery, recommendation = confirmed[classification]
        return {
            "issue_status": "verified_live_error",
            "resolution_status": "concrete_fix_candidate_requires_review",
            "recommended_severity": "blocker",
            "confidence": "high",
            "recovery_classification": recovery,
            "reason": (
                f"Tiger reports a concrete invalid construct for {source_object}; "
                f"the current candidate is {candidate or 'structural rather than identity-based'}"
            ),
            "recommendation": recommendation,
        }

    if classification == "pending_asil_mod_fix":
        return {
            "issue_status": "verified_live_error",
            "resolution_status": "pending_asil_mod_merge",
            "recommended_severity": "blocker",
            "confidence": "high",
            "recovery_classification": "take_pending_asil_mod_fix_then_reaudit",
            "reason": (
                "the current asıl mod already changes this exact file and the pending "
                "commit addresses the reported character inconsistency"
            ),
            "recommendation": "merge the pending asıl-mod commit and rerun the same Tiger comparison",
        }

    if classification == "unresolved_missing_title_reference":
        origin = (
            "shared_source" if provenance == "shared_premerge_and_asil_line"
            else "preexisting_yusseter"
        )
        return {
            "issue_status": "verified_undefined_title_reference",
            "resolution_status": "no_safe_identity_mapping_yet",
            "recommended_severity": "review",
            "confidence": "high_error_low_resolution",
            "recovery_classification": f"{origin}_undefined_title_identity_debt",
            "reason": (
                f"{source_object} is undefined in current landed titles, but no exact "
                "single current counterpart is proven"
            ),
            "recommendation": "decide exact counterpart, external dependency, or removal before editing",
        }

    manual: dict[str, tuple[str, str]] = {
        "ambiguous_parent_derived_review": (
            "ambiguous_parent_derived_title_identity_review",
            "choose among the same-tier parent-derived candidates using region semantics",
        ),
        "split_title_reference_review": (
            "split_title_identity_context_review",
            "resolve each localization context against the two current successor titles",
        ),
        "stale_region_title_no_exact_current_counterpart": (
            "region_reference_without_exact_counterpart_review",
            "remove the stale token or select an adjacent substitute only after region review",
        ),
    }
    if classification in manual:
        recovery, recommendation = manual[classification]
        return {
            "issue_status": "verified_undefined_title_reference",
            "resolution_status": "manual_semantic_choice_required",
            "recommended_severity": "review",
            "confidence": "medium",
            "recovery_classification": recovery,
            "reason": (
                f"{source_object} is undefined, but the evidence yields "
                f"{candidate or 'no exact'} counterpart rather than one safe replacement"
            ),
            "recommendation": recommendation,
        }

    return {
        "issue_status": "unclassified_p0",
        "resolution_status": "manual_review_required",
        "recommended_severity": "review",
        "confidence": "low",
        "recovery_classification": "manual_unclassified_p0_review",
        "reason": row.get("message", ""),
        "recommendation": row.get("recommendation", "manual review"),
    }


def split_pipe(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]


def joined(rows: list[dict[str, str]], key: str) -> str:
    return " | ".join(sorted({row.get(key, "") for row in rows if row.get(key)}))


def reader_variable_name(row: dict[str, str]) -> str:
    source_object = row.get("source_object", "")
    match = re.search(r"reader variable ([A-Za-z0-9_]+)", source_object)
    if not match:
        match = re.search(r"@([A-Za-z0-9_]+)", source_object)
    return match.group(1) if match else ""


def integration_responsibility(rows: list[dict[str, str]]) -> str:
    if any(row.get("resolution_status") == "pending_asil_mod_merge" for row in rows):
        return "pending_asil_mod_merge"
    provenance = {row.get("line_provenance", "") for row in rows}
    if "current_only_or_adapted_line" in provenance:
        return "yusseter_current_adaptation_error"
    if provenance <= {"preexisting_yusseter_line"}:
        return "preexisting_yusseter_live_error"
    if provenance & {"path_absent_at_premerge", "post_premerge_asil_line"}:
        return "upstream_integration_error_or_pending_fix"
    return "mixed_provenance_live_error"


def build_live_error_record(
    root_family: str,
    primary_object: str,
    rows: list[dict[str, str]],
    locations: set[str] | None = None,
    raw_tiger_report_count: int | None = None,
) -> dict[str, str]:
    effective_locations = locations or {
        location
        for row in rows
        for location in split_pipe(row.get("locations", ""))
    }
    root_ids = sorted({row.get("root_cause_id", "") for row in rows if row.get("root_cause_id")})
    raw_count = raw_tiger_report_count
    if raw_count is None:
        raw_count = sum(int(row.get("finding_count") or 0) for row in rows)
    return {
        "independent_root_id": "",
        "root_family": root_family,
        "primary_object": primary_object,
        "source_objects": joined(rows, "source_object"),
        "p0_root_ids": " | ".join(root_ids),
        "source_p0_root_count": str(len(root_ids)),
        "raw_tiger_report_count": str(raw_count),
        "unique_source_location_count": str(len(effective_locations)),
        "paths": joined(rows, "paths"),
        "locations": " | ".join(sorted(effective_locations)),
        "line_provenance": joined(rows, "line_provenance"),
        "integration_responsibility": integration_responsibility(rows),
        "resolution_status": joined(rows, "resolution_status"),
        "candidate_objects": joined(rows, "candidate_object"),
        "recovery_classification": joined(rows, "recovery_classification"),
        "confidence": joined(rows, "confidence"),
        "reason": joined(rows, "reason"),
        "recommendation": joined(rows, "recommendation"),
        "source_evidence": joined(rows, "source_evidence"),
        "auto_apply": "no",
        "yusseter_revision": rows[0].get("yusseter_revision", ""),
        "current_asil_revision": rows[0].get("current_asil_revision", ""),
        "premerge_revision": rows[0].get("premerge_revision", ""),
        "source_report": "tiger_p0_root_triage.csv",
    }


def consolidate_verified_live_errors(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    live_rows = [row for row in rows if row.get("issue_status") == "verified_live_error"]
    records: list[dict[str, str]] = []

    reader_rows = [
        row
        for row in live_rows
        if row.get("recovery_classification")
        == "confirmed_reader_variable_definition_error"
    ]
    generic_number_rows = [
        row for row in reader_rows if row.get("source_object") == "expected number"
    ]
    named_reader_groups: dict[str, list[dict[str, str]]] = {}
    for row in reader_rows:
        variable = reader_variable_name(row)
        if variable:
            named_reader_groups.setdefault(variable, []).append(row)

    allocated_generic_locations: set[str] = set()
    for variable, named_rows in sorted(named_reader_groups.items()):
        named_locations = {
            location
            for row in named_rows
            for location in split_pipe(row.get("locations", ""))
        }
        support_rows = list(named_rows)
        generic_report_count = 0
        for generic_row in generic_number_rows:
            overlaps = named_locations & set(split_pipe(generic_row.get("locations", "")))
            if overlaps:
                support_rows.append(generic_row)
                generic_report_count += len(overlaps)
                allocated_generic_locations.update(overlaps)
        records.append(build_live_error_record(
            "reader_variable_definition",
            variable,
            support_rows,
            locations=named_locations,
            raw_tiger_report_count=(
                sum(int(row.get("finding_count") or 0) for row in named_rows)
                + generic_report_count
            ),
        ))

    for generic_row in generic_number_rows:
        remaining = set(split_pipe(generic_row.get("locations", ""))) - allocated_generic_locations
        if remaining:
            records.append(build_live_error_record(
                "unattributed_numeric_reader_error",
                "expected number",
                [generic_row],
                locations=remaining,
                raw_tiger_report_count=len(remaining),
            ))

    pending_groups: dict[str, list[dict[str, str]]] = {}
    for row in live_rows:
        if row.get("resolution_status") == "pending_asil_mod_merge":
            pending_groups.setdefault(row.get("paths", ""), []).append(row)
    for path, group in sorted(pending_groups.items()):
        records.append(build_live_error_record(
            "pending_asil_mod_character_fix",
            Path(path).name if path else joined(group, "source_object"),
            group,
        ))

    family_names = {
        "confirmed_history_effect_title_remap_candidate": "history_effect_title_remap",
        "confirmed_history_effect_scope_prefix_candidate": "history_effect_scope_prefix",
        "confirmed_title_history_tier_error": "title_history_tier_relationship",
        "confirmed_file_sentinel_order_error": "file_sentinel_order",
        "confirmed_stale_character_alias_candidate": "stale_character_alias",
        "confirmed_redundant_region_reference_candidate": "redundant_region_title_reference",
    }
    for row in live_rows:
        recovery = row.get("recovery_classification", "")
        if recovery == "confirmed_reader_variable_definition_error":
            continue
        if row.get("resolution_status") == "pending_asil_mod_merge":
            continue
        records.append(build_live_error_record(
            family_names.get(recovery, recovery or "unclassified_live_error"),
            row.get("source_object", ""),
            [row],
        ))

    records.sort(key=lambda row: (
        row.get("root_family", ""),
        row.get("primary_object", ""),
        row.get("locations", ""),
    ))
    for index, record in enumerate(records, start=1):
        record["independent_root_id"] = f"VLR{index:04d}"
    return records


def parse_top_candidate_ids(value: str) -> list[str]:
    candidates: list[str] = []
    for item in split_pipe(value):
        parts = item.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            candidates.append(parts[1])
    return candidates


def build_undefined_barony_identity_candidates(
    rows: list[dict[str, str]],
    current_blocks: dict,
    source_blocks: dict,
    relation_rows: list[dict[str, str]],
    canonical_relation_rows: list[dict[str, str]],
    relation_report: Path,
    target_tracking_stale: bool,
) -> list[dict[str, str]]:
    relation_by_source = {
        row.get("source_province_id", ""): row
        for row in relation_rows
        if row.get("source_province_id")
    }
    canonical_by_source = {
        row.get("source_province_id", ""): row
        for row in canonical_relation_rows
        if row.get("source_province_id")
    }
    current_baronies_by_province: dict[str, list] = {}
    for block in current_blocks.values():
        if not block.title_id.startswith("b_"):
            continue
        for province_id in block.direct_province_ids:
            current_baronies_by_province.setdefault(str(province_id), []).append(block)

    output: list[dict[str, str]] = []
    for row in rows:
        source_title = row.get("source_object", "")
        if (
            row.get("issue_status") != "verified_undefined_title_reference"
            or not source_title.startswith("b_")
        ):
            continue
        source_block = source_blocks.get(source_title)
        source_province_ids = (
            [str(value) for value in source_block.direct_province_ids]
            if source_block else []
        )
        source_province_id = (
            source_province_ids[0] if len(source_province_ids) == 1 else ""
        )
        relation = relation_by_source.get(source_province_id, {})
        canonical = canonical_by_source.get(source_province_id, {})
        target_province_id = relation.get("target_province_id", "")
        target_blocks = current_baronies_by_province.get(target_province_id, [])
        same_id_blocks = current_baronies_by_province.get(source_province_id, [])
        top_candidate_ids = parse_top_candidate_ids(relation.get("top_candidates", ""))
        geometry_titles: list[str] = []
        geometry_evidence: list[str] = []
        for candidate_id in top_candidate_ids:
            owners = current_baronies_by_province.get(candidate_id, [])
            if owners:
                geometry_titles.extend(block.title_id for block in owners)
                geometry_evidence.extend(
                    f"{candidate_id}:{block.title_id}" for block in owners
                )

        unique_geometry_titles = sorted(set(geometry_titles))

        if not source_block:
            status = "source_barony_not_defined_in_current_asil_mod"
            recommendation = "identify the authoritative source title before remapping"
        elif len(source_province_ids) != 1:
            status = "source_barony_missing_or_multiple_province_ids"
            recommendation = "review the source barony block structure"
        elif not relation:
            status = "source_province_absent_from_relation_refresh"
            recommendation = "extend the province relation scope before title remapping"
        elif not target_province_id:
            status = "relation_has_no_target_province"
            recommendation = "resolve the source province geometry before title remapping"
        elif len(target_blocks) == 1 and relation.get("classification") == "exact":
            status = "single_exact_primary_target_landed_candidate_tracking_stale"
            recommendation = "refresh target tracking, then review the single landed candidate"
        elif len(target_blocks) == 1:
            status = "single_primary_target_landed_candidate_requires_review"
            recommendation = "review split/merge geometry and context before remapping"
        elif len(target_blocks) > 1:
            status = "target_province_has_multiple_landed_baronies"
            recommendation = "resolve duplicate landed ownership before remapping"
        elif len(unique_geometry_titles) == 1:
            status = "primary_target_nonlanded_single_alternative_landed_candidate"
            recommendation = "review the single alternative geometry candidate and title context"
        elif len(unique_geometry_titles) > 1:
            status = "primary_target_nonlanded_multiple_alternative_landed_candidates"
            recommendation = "select among alternative geometry candidates using title context"
        else:
            status = "primary_target_nonlanded_no_alternative_landed_candidate"
            recommendation = "derive a title-level candidate or remove the stale reference"

        output.append({
            "root_cause_id": row.get("root_cause_id", ""),
            "source_title": source_title,
            "source_parent": source_block.parent_id if source_block else "",
            "source_path": source_block.path if source_block else "",
            "source_landed_file": source_block.source_file if source_block else "",
            "source_landed_line": str(source_block.start_line) if source_block else "",
            "source_province_ids": " | ".join(source_province_ids),
            "relation_target_province_id": target_province_id,
            "relation_target_name": relation.get("target_name", ""),
            "relation_classification": relation.get("classification", ""),
            "relation_confidence": relation.get("confidence", ""),
            "relation_status": relation.get("status", ""),
            "relation_apply_to_history": relation.get("apply_to_history", ""),
            "relation_top_candidates": relation.get("top_candidates", ""),
            "canonical_target_province_id": canonical.get("target_province_id", ""),
            "relation_target_changed_from_canonical": (
                "yes"
                if canonical
                and canonical.get("target_province_id", "") != target_province_id
                else "no"
            ),
            "current_candidate_titles": " | ".join(
                sorted({block.title_id for block in target_blocks})
            ),
            "current_candidate_parents": " | ".join(
                sorted({block.parent_id for block in target_blocks if block.parent_id})
            ),
            "current_candidate_paths": " | ".join(
                sorted({block.path for block in target_blocks})
            ),
            "same_province_id_current_titles": " | ".join(
                sorted({block.title_id for block in same_id_blocks})
            ),
            "geometry_candidate_titles": " | ".join(sorted(set(geometry_titles))),
            "geometry_candidate_evidence": " | ".join(sorted(set(geometry_evidence))),
            "primary_target_landed_title_count": str(len(target_blocks)),
            "alternative_geometry_landed_title_count": str(
                len(unique_geometry_titles) if not target_blocks else 0
            ),
            "candidate_status": status,
            "target_tracking_stale": "yes" if target_tracking_stale else "no",
            "confidence_ceiling": (
                "medium_pending_tracking_refresh"
                if target_tracking_stale
                else "review_relation_classification"
            ),
            "line_provenance": row.get("line_provenance", ""),
            "finding_count": row.get("finding_count", ""),
            "reference_paths": row.get("paths", ""),
            "reference_locations": row.get("locations", ""),
            "recommendation": recommendation,
            "auto_apply": "no",
            "yusseter_revision": row.get("yusseter_revision", ""),
            "current_asil_revision": row.get("current_asil_revision", ""),
            "premerge_revision": row.get("premerge_revision", ""),
            "relation_report": str(relation_report),
            "source_report": "tiger_p0_root_triage.csv",
        })

    output.sort(key=lambda item: item.get("source_title", ""))
    return output


def higher_title_usage_context(
    source_title: str, reference_paths: str
) -> dict[str, str]:
    paths = [path.replace("\\", "/") for path in split_pipe(reference_paths)]

    if any("common/religion/holy_site_types/" in path for path in paths):
        return {
            "usage_context_family": "holy_site_county_reference",
            "usage_context_decision": "valid_single_county_successor_required",
            "context_recommendation": (
                "identify the current county containing the holy-site location; "
                "do not remove or guess from an unrelated nearby title"
            ),
        }
    if any(path.endswith("10_natural_disaster_regions.txt") for path in paths):
        return {
            "usage_context_family": "natural_disaster_region_title_reference",
            "usage_context_decision": "region_membership_split_or_successor_review",
            "context_recommendation": (
                "decide whether the obsolete kingdom footprint is represented by one "
                "or several current kingdoms before changing disaster coverage"
            ),
        }
    if (
        source_title == "c_yang_wen_dun"
        and any("map_data/geographical_regions/" in path for path in paths)
    ):
        return {
            "usage_context_family": "ordered_silk_road_county_reference",
            "usage_context_decision": "ordered_route_successor_required",
            "context_recommendation": (
                "select a valid route county and recheck route order and geometry; "
                "do not simply delete an ordered node"
            ),
        }
    if any(path.endswith("RICE_geographical_region.txt") for path in paths):
        return {
            "usage_context_family": "compatibility_geographical_region_title_reference",
            "usage_context_decision": "compatibility_region_membership_review",
            "context_recommendation": (
                "review the RICE compatibility region against the current hierarchy "
                "before removing or replacing the title"
            ),
        }
    if any("map_data/geographical_regions/" in path for path in paths):
        return {
            "usage_context_family": "geographical_region_title_reference",
            "usage_context_decision": "region_membership_remove_or_remap_review",
            "context_recommendation": (
                "compare neighboring region members and current hierarchy before "
                "removing the stale token or choosing a successor"
            ),
        }
    if any("localization/" in path for path in paths):
        return {
            "usage_context_family": "dynamic_localization_title_reference",
            "usage_context_decision": "split_or_literal_text_rewrite_required",
            "context_recommendation": (
                "rewrite the text for the intended successor or use a literal regional "
                "name when one source title split into multiple current titles"
            ),
        }
    if any("history/titles/" in path for path in paths):
        return {
            "usage_context_family": "title_history_liege_reference",
            "usage_context_decision": "single_valid_higher_tier_title_required",
            "context_recommendation": (
                "choose one valid current higher-tier liege for the dated history effect; "
                "do not remove it without checking the de-jure transition"
            ),
        }
    if any("common/legends/legend_seeds/" in path for path in paths):
        return {
            "usage_context_family": "legend_seed_title_trigger_reference",
            "usage_context_decision": "trigger_remove_or_successor_review",
            "context_recommendation": (
                "decide whether the obsolete title condition is redundant or needs a "
                "current successor while preserving legend availability"
            ),
        }
    return {
        "usage_context_family": "other_title_reference",
        "usage_context_decision": "context_specific_manual_review",
        "context_recommendation": (
            "inspect the consuming CK3 system before selecting, splitting, or removing "
            "the obsolete title reference"
        ),
    }


def strip_ck3_brace_text(line: str) -> str:
    output: list[str] = []
    in_quote = False
    escaped = False
    for char in line:
        if in_quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_quote = False
            continue
        if char == '"':
            in_quote = True
            continue
        if char == "#":
            break
        output.append(char)
    return "".join(output)


def strip_ck3_comment(line: str) -> str:
    output: list[str] = []
    in_quote = False
    escaped = False
    for char in line:
        if in_quote:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_quote = False
            continue
        if char == '"':
            in_quote = True
            output.append(char)
            continue
        if char == "#":
            break
        output.append(char)
    return "".join(output)


def smallest_enclosing_scope(
    lines: list[str], target_index: int
) -> tuple[int, int]:
    stack: list[int] = []
    enclosing: list[tuple[int, int]] = []
    for line_index, line in enumerate(lines):
        for char in strip_ck3_brace_text(line):
            if char == "{":
                stack.append(line_index)
            elif char == "}" and stack:
                start_index = stack.pop()
                if start_index <= target_index <= line_index:
                    enclosing.append((start_index, line_index))
    if enclosing:
        return min(
            enclosing,
            key=lambda scope: (scope[1] - scope[0], -scope[0]),
        )
    return max(0, target_index - 2), min(len(lines) - 1, target_index + 2)


def compact_context_line(line: str, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", line.strip())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."


def higher_title_reference_context(
    repo_root: Path,
    source_title: str,
    preferred_candidate: str,
    reference_locations: str,
) -> dict[str, str]:
    locations = sorted(set(split_pipe(reference_locations)))
    readable_count = 0
    candidate_match_count = 0
    scope_labels: list[str] = []
    excerpts: list[str] = []
    context_block_keys: set[str] = set()
    explicit_baronies: set[str] = set()
    source_pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(source_title)}(?![A-Za-z0-9_])"
    )
    candidate_pattern = (
        re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(preferred_candidate)}"
            r"(?![A-Za-z0-9_])"
        )
        if preferred_candidate
        else None
    )

    for location in locations:
        try:
            path_text, line_text = location.rsplit(":", 1)
            line_number = int(line_text)
        except (ValueError, TypeError):
            continue
        path = Path(path_text)
        if not path.is_absolute():
            path = repo_root / path
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        target_index = line_number - 1
        if target_index < 0 or target_index >= len(lines):
            continue

        readable_count += 1
        scope_start, scope_end = smallest_enclosing_scope(lines, target_index)
        scope_text = "\n".join(lines[scope_start: scope_end + 1])
        active_scope_text = "\n".join(
            strip_ck3_comment(line)
            for line in lines[scope_start: scope_end + 1]
        )
        block_match = re.match(
            r"\s*([A-Za-z0-9_]+)\s*=\s*\{",
            strip_ck3_brace_text(lines[scope_start]),
        )
        if block_match:
            context_block_keys.add(block_match.group(1))
        explicit_baronies.update(re.findall(
            r"\bbarony\s*=\s*(b_[A-Za-z0-9_]+)",
            active_scope_text,
        ))
        if candidate_pattern and candidate_pattern.search(active_scope_text):
            candidate_match_count += 1
        relative_path = (
            path.resolve().relative_to(repo_root.resolve()).as_posix()
            if path.resolve().is_relative_to(repo_root.resolve())
            else path.resolve().as_posix()
        )
        source_found = "yes" if source_pattern.search(active_scope_text) else "no"
        scope_labels.append(
            f"{relative_path}:{scope_start + 1}-{scope_end + 1}:"
            f"source_present={source_found}"
        )
        excerpt_start = max(scope_start, target_index - 2)
        excerpt_end = min(scope_end, target_index + 2)
        excerpt = " || ".join(
            f"{index + 1}:{compact_context_line(lines[index])}"
            for index in range(excerpt_start, excerpt_end + 1)
        )
        excerpts.append(f"{relative_path}:{line_number} => {excerpt}")

    if not preferred_candidate:
        candidate_present = "not_applicable"
    elif candidate_match_count:
        candidate_present = "yes"
    else:
        candidate_present = "no"
    if readable_count == len(locations) and readable_count:
        context_status = "complete"
    elif readable_count:
        context_status = "partial"
    else:
        context_status = "unavailable"
    return {
        "reference_context_status": context_status,
        "reference_context_location_count": str(len(locations)),
        "reference_context_readable_count": str(readable_count),
        "reference_context_scopes": " | ".join(scope_labels),
        "reference_context_excerpt": " | ".join(excerpts),
        "reference_context_block_keys": " | ".join(sorted(context_block_keys)),
        "reference_context_explicit_baronies": " | ".join(
            sorted(explicit_baronies)
        ),
        "preferred_candidate_context_match_count": str(candidate_match_count),
        "preferred_candidate_present_near_reference": candidate_present,
    }


def contextual_holy_site_county_candidates(
    source_block,
    source_blocks: dict,
    current_blocks: dict,
    relation_by_source: dict[str, dict[str, str]],
    current_ancestors_by_province: dict[str, dict[str, set[str]]],
    title_relation_reverse: dict[str, list[str]],
    usage_context: dict[str, str],
    reference_context: dict[str, str],
) -> dict[str, str]:
    if usage_context["usage_context_family"] != "holy_site_county_reference":
        return {
            "context_location_basis": "not_applicable",
            "context_location_source_baronies": "",
            "context_location_source_province_ids": "",
            "context_location_relation_evidence": "",
            "context_location_current_county_candidates": "",
            "context_location_candidate_status": "not_applicable",
            "context_location_preferred_candidate": "",
        }

    explicit_baronies = split_pipe(
        reference_context.get("reference_context_explicit_baronies", "")
    )
    source_county_baronies = sorted(
        (
            block
            for block in source_blocks.values()
            if block.title_id.startswith("b_")
            and source_block
            and block.parent_id == source_block.title_id
        ),
        key=lambda block: (block.source_file, block.start_line, block.title_id),
    )
    if explicit_baronies:
        location_basis = "explicit_holy_site_barony"
        source_baronies = explicit_baronies
    elif source_county_baronies:
        location_basis = "source_county_first_barony"
        source_baronies = [source_county_baronies[0].title_id]
    else:
        location_basis = "source_location_unavailable"
        source_baronies = []

    identity_candidates: set[str] = set()
    primary_candidates: set[str] = set()
    alternative_candidates: set[str] = set()
    source_province_ids: set[str] = set()
    relation_evidence: list[str] = []

    for source_barony in source_baronies:
        current_barony_candidates = sorted({
            candidate
            for candidate in (
                [source_barony] if source_barony in current_blocks else []
            ) + title_relation_reverse.get(source_barony, [])
            if candidate in current_blocks
        })
        for current_barony in current_barony_candidates:
            identity_candidates.update(
                title
                for title in current_blocks[current_barony].path.split(" > ")
                if title.startswith("c_")
            )

        source_barony_block = source_blocks.get(source_barony)
        province_ids = (
            [str(value) for value in source_barony_block.direct_province_ids]
            if source_barony_block else []
        )
        source_province_ids.update(province_ids)
        if not province_ids:
            relation_evidence.append(f"{source_barony}:no_source_province")
            continue
        for source_province_id in province_ids:
            relation = relation_by_source.get(source_province_id, {})
            target_province_id = relation.get("target_province_id", "")
            direct = sorted(
                current_ancestors_by_province.get(target_province_id, {}).get(
                    "c_", set()
                )
            )
            primary_candidates.update(direct)
            alternative: set[str] = set()
            for candidate_id in parse_top_candidate_ids(
                relation.get("top_candidates", "")
            ):
                alternative.update(
                    current_ancestors_by_province.get(candidate_id, {}).get(
                        "c_", set()
                    )
                )
            alternative_candidates.update(alternative)
            relation_evidence.append(
                f"{source_barony}:{source_province_id}->{target_province_id or 'none'}:"
                f"primary={','.join(direct) if direct else 'none'}:"
                f"alternative={','.join(sorted(alternative)) if alternative else 'none'}"
            )

    if identity_candidates:
        candidates = sorted(identity_candidates)
        candidate_source = "title_identity"
    elif primary_candidates:
        candidates = sorted(primary_candidates)
        candidate_source = "primary_relation_target"
    else:
        candidates = sorted(alternative_candidates)
        candidate_source = "alternative_relation_geometry"

    if not source_baronies:
        status = "source_location_barony_unavailable"
        preferred_candidate = ""
    elif len(candidates) == 1:
        status = f"single_{candidate_source}_county_candidate_requires_review"
        preferred_candidate = candidates[0]
    elif len(candidates) > 1:
        status = f"multiple_{candidate_source}_county_candidates_review"
        preferred_candidate = ""
    else:
        status = "source_location_has_no_current_county_candidate"
        preferred_candidate = ""
    return {
        "context_location_basis": location_basis,
        "context_location_source_baronies": " | ".join(source_baronies),
        "context_location_source_province_ids": " | ".join(
            sorted(source_province_ids, key=lambda value: int(value))
        ),
        "context_location_relation_evidence": " | ".join(relation_evidence),
        "context_location_current_county_candidates": " | ".join(candidates),
        "context_location_candidate_status": status,
        "context_location_preferred_candidate": preferred_candidate,
    }


def descendant_title_identity_candidates(
    source_block,
    source_blocks: dict,
    current_blocks: dict,
    title_relation_reverse: dict[str, list[str]],
) -> dict[str, str]:
    if not source_block:
        return {
            "identity_descendant_source_titles": "",
            "identity_descendant_mapped_source_count": "0",
            "identity_descendant_same_tier_candidates": "",
            "identity_descendant_candidate_evidence": "",
            "identity_descendant_candidate_status": "source_title_unavailable",
            "identity_descendant_preferred_candidate": "",
        }
    source_tier = source_block.title_id[:2]
    child_tier = {"c_": "b_", "d_": "c_", "k_": "d_"}.get(source_tier, "")
    source_children = sorted(
        (
            block
            for block in source_blocks.values()
            if child_tier
            and block.title_id.startswith(child_tier)
            and block.parent_id == source_block.title_id
        ),
        key=lambda block: (block.source_file, block.start_line, block.title_id),
    )
    candidate_counts: Counter[str] = Counter()
    mapped_source_count = 0
    evidence: list[str] = []
    for source_child in source_children:
        mapped_children = sorted({
            candidate
            for candidate in (
                [source_child.title_id]
                if source_child.title_id in current_blocks else []
            ) + title_relation_reverse.get(source_child.title_id, [])
            if candidate in current_blocks
        })
        same_tier_parents: set[str] = set()
        for mapped_child in mapped_children:
            same_tier_parents.update(
                title
                for title in current_blocks[mapped_child].path.split(" > ")
                if title.startswith(source_tier)
            )
        if same_tier_parents:
            mapped_source_count += 1
            for candidate in same_tier_parents:
                candidate_counts[candidate] += 1
        evidence.append(
            f"{source_child.title_id}->"
            f"{','.join(mapped_children) if mapped_children else 'unmapped'}:"
            f"parents={','.join(sorted(same_tier_parents)) if same_tier_parents else 'none'}"
        )

    ranked_candidates = sorted(
        candidate_counts,
        key=lambda title: (-candidate_counts[title], title),
    )
    top_count = candidate_counts.get(ranked_candidates[0], 0) if ranked_candidates else 0
    second_count = candidate_counts.get(ranked_candidates[1], 0) if len(ranked_candidates) > 1 else 0
    if not source_children:
        status = "source_title_has_no_direct_lower_tier_children"
        preferred_candidate = ""
    elif not mapped_source_count:
        status = "source_children_have_no_current_identity_mapping"
        preferred_candidate = ""
    elif len(ranked_candidates) == 1 and mapped_source_count == len(source_children):
        status = "single_full_descendant_identity_candidate_requires_review"
        preferred_candidate = ranked_candidates[0]
    elif len(ranked_candidates) == 1:
        status = "single_partial_descendant_identity_candidate_requires_review"
        preferred_candidate = ranked_candidates[0]
    elif top_count == second_count:
        status = "multiple_descendant_identity_candidates_tied_review"
        preferred_candidate = ""
    else:
        status = "split_descendant_identity_candidates_review"
        preferred_candidate = ""
    return {
        "identity_descendant_source_titles": " | ".join(
            block.title_id for block in source_children
        ),
        "identity_descendant_mapped_source_count": str(mapped_source_count),
        "identity_descendant_same_tier_candidates": " | ".join(
            ranked_candidates
        ),
        "identity_descendant_candidate_evidence": " | ".join(evidence),
        "identity_descendant_candidate_status": status,
        "identity_descendant_preferred_candidate": preferred_candidate,
    }


def refine_higher_title_usage_context(
    usage_context: dict[str, str],
    preferred_candidate: str,
    preferred_candidate_source: str,
    reference_context: dict[str, str],
    context_location: dict[str, str],
    identity_descendant: dict[str, str],
) -> dict[str, str]:
    output = dict(usage_context)
    family = output["usage_context_family"]
    candidate_present = reference_context[
        "preferred_candidate_present_near_reference"
    ]
    location_status = context_location["context_location_candidate_status"]
    if family == "holy_site_county_reference" and location_status.startswith(
        "single_"
    ):
        output.update({
            "usage_context_decision": "single_holy_site_county_candidate_requires_review",
            "context_recommendation": (
                f"review {preferred_candidate} as the current county containing the mapped "
                "holy-site location barony; stale relation tracking prevents auto-apply"
            ),
        })
        return output
    if family == "holy_site_county_reference" and location_status.startswith(
        "multiple_"
    ):
        output.update({
            "usage_context_decision": "multiple_holy_site_county_candidates_review",
            "context_recommendation": (
                "choose among the counties reached from the holy-site location barony; "
                "do not infer the replacement from the obsolete county name"
            ),
        })
        return output
    if (
        family == "holy_site_county_reference"
        and location_status == "source_location_has_no_current_county_candidate"
    ):
        output.update({
            "usage_context_decision": "holy_site_location_not_preserved_design_review",
            "context_recommendation": (
                "the source holy-site barony resolves only to non-landed target geometry "
                "with no landed county alternative; manually relocate or retire the holy "
                "site instead of guessing a county"
            ),
        })
        return output
    if (
        family == "holy_site_county_reference"
        and location_status == "source_location_barony_unavailable"
    ):
        output.update({
            "usage_context_decision": "holy_site_source_location_missing_review",
            "context_recommendation": (
                "the source holy-site block has no resolvable explicit or first county "
                "barony; identify the intended site before changing the county reference"
            ),
        })
        return output
    identity_candidates = split_pipe(
        identity_descendant["identity_descendant_same_tier_candidates"]
    )
    if family == "natural_disaster_region_title_reference" and len(
        identity_candidates
    ) > 1:
        output.update({
            "usage_context_decision": "split_disaster_region_membership_review",
            "context_recommendation": (
                "the source kingdom descendants map across multiple current kingdoms; "
                "review the full successor set before changing disaster coverage"
            ),
        })
        return output
    if family in {
        "geographical_region_title_reference",
        "compatibility_geographical_region_title_reference",
    } and len(identity_candidates) > 1:
        output.update({
            "usage_context_decision": "split_region_membership_rewrite_review",
            "context_recommendation": (
                "the source descendants map across multiple current same-tier titles; "
                "review which successors belong in this specific region"
            ),
        })
        return output
    if (
        preferred_candidate
        and preferred_candidate_source in {
            "descendant_title_identity",
            "geometry_descendant_identity_overlap",
        }
        and family == "ordered_silk_road_county_reference"
    ):
        output.update({
            "usage_context_decision": "single_ordered_route_successor_review",
            "context_recommendation": (
                f"review {preferred_candidate} as the mapped route county, then recheck "
                "node order and route geometry before changing the ordered list"
            ),
        })
        return output
    if (
        preferred_candidate
        and preferred_candidate_source in {
            "descendant_title_identity",
            "geometry_descendant_identity_overlap",
        }
        and family in {
            "geographical_region_title_reference",
            "compatibility_geographical_region_title_reference",
        }
        and candidate_present == "no"
    ):
        output.update({
            "usage_context_decision": "single_region_successor_replacement_review",
            "context_recommendation": (
                f"review {preferred_candidate} as the descendant-identity successor for "
                "this region; do not apply it outside the verified consuming context"
            ),
        })
        return output
    if preferred_candidate and candidate_present == "yes":
        if family == "legend_seed_title_trigger_reference":
            output.update({
                "usage_context_decision": "redundant_trigger_condition_remove_review",
                "context_recommendation": (
                    f"{preferred_candidate} already appears in the same trigger scope; "
                    "review removing the obsolete condition instead of adding a duplicate "
                    "replacement, then retest legend availability"
                ),
            })
        elif family in {
            "geographical_region_title_reference",
            "compatibility_geographical_region_title_reference",
        }:
            output.update({
                "usage_context_decision": "redundant_region_reference_remove_review",
                "context_recommendation": (
                    f"{preferred_candidate} already appears in the same region scope; "
                    "review removing the obsolete token instead of duplicating the successor"
                ),
            })
        else:
            output.update({
                "usage_context_decision": "preferred_candidate_already_present_context_review",
                "context_recommendation": (
                    f"{preferred_candidate} already appears in the same consuming scope; "
                    "review whether the obsolete reference is redundant before replacing it"
                ),
            })
    elif preferred_candidate and family == "title_history_liege_reference":
        output.update({
            "usage_context_decision": "single_contextual_replacement_review",
            "context_recommendation": (
                f"review {preferred_candidate} as the dated de-jure liege replacement; "
                "capital identity supports the candidate but does not prove the transition"
            ),
        })
    elif preferred_candidate and family == "legend_seed_title_trigger_reference":
        output.update({
            "usage_context_decision": "single_successor_trigger_replacement_review",
            "context_recommendation": (
                f"review {preferred_candidate} as the successor trigger condition and retest "
                "legend availability at supported bookmark dates"
            ),
        })
    return output


def build_undefined_higher_title_identity_candidates(
    repo_root: Path,
    rows: list[dict[str, str]],
    current_blocks: dict,
    source_blocks: dict,
    relation_rows: list[dict[str, str]],
    title_relation_reverse: dict[str, list[str]],
    relation_report: Path,
    target_tracking_stale: bool,
) -> list[dict[str, str]]:
    relation_by_source = {
        row.get("source_province_id", ""): row
        for row in relation_rows
        if row.get("source_province_id")
    }
    current_ancestors_by_province: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for block in current_blocks.values():
        if not block.title_id.startswith("b_"):
            continue
        path_titles = block.path.split(" > ")
        ancestors = {
            title[:2]: title
            for title in path_titles
            if title.startswith(("c_", "d_", "k_"))
        }
        for province_id in block.direct_province_ids:
            for tier, title in ancestors.items():
                current_ancestors_by_province[str(province_id)][tier].add(title)

    output: list[dict[str, str]] = []
    for row in rows:
        source_title = row.get("source_object", "")
        tier = source_title[:2]
        if (
            row.get("issue_status") != "verified_undefined_title_reference"
            or tier not in {"c_", "d_", "k_"}
        ):
            continue

        source_block = source_blocks.get(source_title)
        source_descendant_province_ids = sorted({
            str(value)
            for value in (
                source_block.descendant_province_ids if source_block else []
            )
        }, key=lambda value: int(value))
        source_capital_title = (
            source_block.effective_capital if source_block else ""
        )
        source_capital_block = source_blocks.get(source_capital_title)
        source_capital_province_ids = sorted({
            str(value)
            for value in (
                source_capital_block.descendant_province_ids
                if source_capital_block else []
            )
        }, key=lambda value: int(value))
        if source_descendant_province_ids:
            footprint_basis = "source_descendant_provinces"
            source_province_ids = source_descendant_province_ids
        elif source_capital_province_ids:
            footprint_basis = "source_capital_county"
            source_province_ids = source_capital_province_ids
        else:
            footprint_basis = "unavailable"
            source_province_ids = []
        source_capital_current_candidates = sorted({
            candidate
            for candidate in (
                [source_capital_title]
                if source_capital_title in current_blocks else []
            ) + title_relation_reverse.get(source_capital_title, [])
            if candidate in current_blocks
        })
        source_capital_same_tier_candidates: set[str] = set()
        for current_capital in source_capital_current_candidates:
            current_capital_block = current_blocks[current_capital]
            source_capital_same_tier_candidates.update(
                title
                for title in current_capital_block.path.split(" > ")
                if title.startswith(tier)
            )
        ranked_source_capital_same_tier_candidates = sorted(
            source_capital_same_tier_candidates
        )
        if not source_capital_title:
            source_capital_identity_status = "source_title_has_no_capital"
        elif not source_capital_current_candidates:
            source_capital_identity_status = "source_capital_has_no_current_identity"
        elif len(ranked_source_capital_same_tier_candidates) == 1:
            source_capital_identity_status = (
                "single_current_capital_same_tier_parent_candidate"
            )
        elif ranked_source_capital_same_tier_candidates:
            source_capital_identity_status = (
                "multiple_current_capital_same_tier_parent_candidates"
            )
        else:
            source_capital_identity_status = (
                "current_capital_identity_has_no_same_tier_parent"
            )
        candidate_source_counts: Counter[str] = Counter()
        candidate_target_provinces: dict[str, set[str]] = defaultdict(set)
        relation_class_counts: Counter[str] = Counter()
        relation_confidences: list[float] = []
        relation_evidence: list[str] = []
        unresolved_source_ids: list[str] = []
        target_without_same_tier: list[str] = []
        resolved_relation_source_ids: set[str] = set()
        same_tier_resolved_source_ids: set[str] = set()

        for source_province_id in source_province_ids:
            relation = relation_by_source.get(source_province_id, {})
            target_province_id = relation.get("target_province_id", "")
            if not relation or not target_province_id:
                unresolved_source_ids.append(source_province_id)
                continue
            resolved_relation_source_ids.add(source_province_id)
            relation_class_counts[relation.get("classification", "unknown")] += 1
            try:
                relation_confidences.append(float(relation.get("confidence", "0")))
            except ValueError:
                relation_confidences.append(0.0)
            candidates = sorted(
                current_ancestors_by_province.get(target_province_id, {}).get(
                    tier, set()
                )
            )
            relation_evidence.append(
                f"{source_province_id}->{target_province_id}:"
                f"{','.join(candidates) if candidates else 'no_same_tier_title'}"
            )
            if not candidates:
                target_without_same_tier.append(target_province_id)
                continue
            same_tier_resolved_source_ids.add(source_province_id)
            for candidate in candidates:
                candidate_source_counts[candidate] += 1
                candidate_target_provinces[candidate].add(target_province_id)

        ranked_candidates = sorted(
            candidate_source_counts,
            key=lambda title: (-candidate_source_counts[title], title),
        )
        total_source_count = len(source_province_ids)
        top_candidate = ranked_candidates[0] if ranked_candidates else ""
        top_count = candidate_source_counts.get(top_candidate, 0)
        second_count = (
            candidate_source_counts[ranked_candidates[1]]
            if len(ranked_candidates) > 1 else 0
        )
        top_share = top_count / total_source_count if total_source_count else 0.0
        ranked_evidence = []
        for candidate in ranked_candidates:
            count = candidate_source_counts[candidate]
            share = count / total_source_count if total_source_count else 0.0
            targets = ",".join(sorted(
                candidate_target_provinces[candidate], key=lambda value: int(value)
            ))
            ranked_evidence.append(
                f"{candidate}:{count}/{total_source_count}:{share:.4f}:"
                f"targets={targets}"
            )

        average_relation_confidence = (
            sum(relation_confidences) / len(relation_confidences)
            if relation_confidences else 0.0
        )
        non_exact_relation_count = sum(
            count
            for name, count in relation_class_counts.items()
            if name != "exact"
        )
        if not resolved_relation_source_ids:
            relation_evidence_quality = "unavailable"
        elif non_exact_relation_count == 0 and average_relation_confidence >= 0.80:
            relation_evidence_quality = "strong_exact_geometry"
        elif non_exact_relation_count > 0:
            relation_evidence_quality = "review_only_split_merge_geometry"
        else:
            relation_evidence_quality = "medium_geometry"

        declared_candidates = split_pipe(row.get("candidate_object", ""))
        declared_set = set(declared_candidates)
        footprint_set = set(ranked_candidates)
        if not declared_set:
            declared_candidate_status = "no_declared_candidate"
        elif not footprint_set:
            declared_candidate_status = "declared_candidates_not_testable_from_footprint"
        elif declared_set == footprint_set:
            declared_candidate_status = "declared_candidates_match_footprint_set"
        elif top_candidate and top_candidate in declared_set:
            declared_candidate_status = "declared_candidates_include_top_footprint"
        elif declared_set & footprint_set:
            declared_candidate_status = "declared_candidates_partially_overlap_footprint"
        elif relation_evidence_quality == "review_only_split_merge_geometry":
            declared_candidate_status = (
                "declared_candidates_conflict_with_review_only_footprint"
            )
        else:
            declared_candidate_status = "declared_candidates_do_not_match_footprint"

        if not source_block:
            status = "source_title_not_defined_in_current_asil_mod"
            recommendation = "identify the authoritative source title before remapping"
        elif (
            not source_descendant_province_ids
            and len(ranked_source_capital_same_tier_candidates) == 1
        ):
            status = "single_capital_identity_same_tier_candidate_requires_review"
            recommendation = (
                "review the current parent of the mapped source capital; capital "
                "identity is strong context evidence but not automatic de-jure proof"
            )
        elif (
            not source_descendant_province_ids
            and len(ranked_source_capital_same_tier_candidates) > 1
        ):
            status = "multiple_capital_identity_same_tier_candidates_review"
            recommendation = (
                "choose among the current parents of the mapped source capital "
                "using the consuming history or trigger context"
            )
        elif not source_province_ids:
            status = "source_title_has_no_descendant_province_footprint"
            recommendation = (
                "review the titular title semantics or an explicit split mapping "
                "before changing the reference"
            )
        elif not resolved_relation_source_ids:
            status = "source_footprint_absent_from_relation_refresh"
            recommendation = "extend the province relation scope before title remapping"
        elif not ranked_candidates:
            status = "resolved_targets_have_no_same_tier_landed_candidate"
            recommendation = "remove the stale reference or select a contextual title manually"
        elif len(ranked_candidates) == 1 and top_count == total_source_count:
            status = "single_full_same_tier_footprint_candidate_requires_review"
            recommendation = "review the full-footprint same-tier candidate in each usage context"
        elif len(ranked_candidates) == 1 and top_share >= 0.75:
            status = "single_dominant_partial_footprint_candidate_requires_review"
            recommendation = "review the dominant partial-footprint candidate and unresolved targets"
        elif len(ranked_candidates) == 1:
            status = "single_low_coverage_footprint_candidate_requires_review"
            recommendation = "treat the low-coverage candidate as weak context evidence only"
        elif top_count == second_count:
            status = "multiple_same_tier_footprint_candidates_tied"
            recommendation = "resolve the tied same-tier candidates by usage context"
        elif top_share >= 0.75 and (top_count - second_count) >= 2:
            status = "dominant_same_tier_candidate_with_secondary_footprint_review"
            recommendation = "review the dominant candidate and secondary footprint before remapping"
        else:
            status = "split_across_multiple_same_tier_footprint_candidates"
            recommendation = "select among split same-tier candidates by usage context"

        if footprint_basis == "source_capital_county" and ranked_candidates:
            recommendation = (
                "review the capital-derived same-tier candidate in its usage context; "
                "a capital match is geographic evidence, not de-jure identity proof"
            )

        top_block = current_blocks.get(top_candidate) if top_candidate else None
        usage_context = higher_title_usage_context(
            source_title, row.get("paths", "")
        )
        reference_context = higher_title_reference_context(
            repo_root,
            source_title,
            "",
            row.get("locations", ""),
        )
        context_location = contextual_holy_site_county_candidates(
            source_block,
            source_blocks,
            current_blocks,
            relation_by_source,
            current_ancestors_by_province,
            title_relation_reverse,
            usage_context,
            reference_context,
        )
        identity_descendant = descendant_title_identity_candidates(
            source_block,
            source_blocks,
            current_blocks,
            title_relation_reverse,
        )
        geometry_candidate_set = set(ranked_candidates)
        identity_candidate_set = set(split_pipe(
            identity_descendant["identity_descendant_same_tier_candidates"]
        ))
        identity_geometry_overlap = sorted(
            geometry_candidate_set & identity_candidate_set
        )
        if geometry_candidate_set and identity_candidate_set:
            if geometry_candidate_set == identity_candidate_set:
                identity_geometry_comparison = "exact_candidate_set_match"
            elif identity_geometry_overlap:
                identity_geometry_comparison = "partial_candidate_set_overlap"
            else:
                identity_geometry_comparison = "disjoint_candidate_sets_review"
        elif geometry_candidate_set:
            identity_geometry_comparison = "geometry_only"
        elif identity_candidate_set:
            identity_geometry_comparison = "descendant_identity_only"
        else:
            identity_geometry_comparison = "both_unavailable"

        preferred_candidate = ""
        preferred_candidate_source = ""
        if (
            len(ranked_source_capital_same_tier_candidates) == 1
            and not source_descendant_province_ids
        ):
            preferred_candidate = ranked_source_capital_same_tier_candidates[0]
            preferred_candidate_source = "source_capital_identity"
        elif context_location["context_location_preferred_candidate"]:
            preferred_candidate = context_location[
                "context_location_preferred_candidate"
            ]
            preferred_candidate_source = "holy_site_location_context"
        elif len(identity_geometry_overlap) == 1:
            preferred_candidate = identity_geometry_overlap[0]
            preferred_candidate_source = "geometry_descendant_identity_overlap"
        elif top_candidate and top_candidate in identity_geometry_overlap:
            preferred_candidate = top_candidate
            preferred_candidate_source = "geometry_descendant_identity_overlap"
        elif geometry_candidate_set and not identity_candidate_set:
            preferred_candidate = top_candidate
            preferred_candidate_source = "footprint_top_candidate"
        elif (
            not geometry_candidate_set
            and identity_descendant["identity_descendant_preferred_candidate"]
        ):
            preferred_candidate = identity_descendant[
                "identity_descendant_preferred_candidate"
            ]
            preferred_candidate_source = "descendant_title_identity"
        if preferred_candidate:
            reference_context = higher_title_reference_context(
                repo_root,
                source_title,
                preferred_candidate,
                row.get("locations", ""),
            )
        usage_context = refine_higher_title_usage_context(
            usage_context,
            preferred_candidate,
            preferred_candidate_source,
            reference_context,
            context_location,
            identity_descendant,
        )
        output.append({
            "root_cause_id": row.get("root_cause_id", ""),
            "source_title": source_title,
            "source_tier": tier,
            "source_parent": source_block.parent_id if source_block else "",
            "source_path": source_block.path if source_block else "",
            "source_landed_file": source_block.source_file if source_block else "",
            "source_landed_line": str(source_block.start_line) if source_block else "",
            "source_descendant_province_count": str(
                len(source_descendant_province_ids)
            ),
            "source_descendant_province_ids": " | ".join(
                source_descendant_province_ids
            ),
            "source_capital_title": source_capital_title,
            "source_capital_source": (
                source_block.effective_capital_source if source_block else ""
            ),
            "source_capital_province_ids": " | ".join(
                source_capital_province_ids
            ),
            "source_capital_current_candidates": " | ".join(
                source_capital_current_candidates
            ),
            "source_capital_same_tier_candidates": " | ".join(
                ranked_source_capital_same_tier_candidates
            ),
            "source_capital_identity_status": source_capital_identity_status,
            "candidate_footprint_basis": footprint_basis,
            "candidate_footprint_province_count": str(total_source_count),
            "candidate_footprint_province_ids": " | ".join(
                source_province_ids
            ),
            "relation_resolved_source_count": str(len(resolved_relation_source_ids)),
            "same_tier_resolved_source_count": str(len(same_tier_resolved_source_ids)),
            "unresolved_source_province_ids": " | ".join(unresolved_source_ids),
            "target_provinces_without_same_tier_title": " | ".join(sorted(
                set(target_without_same_tier), key=lambda value: int(value)
            )),
            "relation_classification_counts": " | ".join(
                f"{name}:{count}"
                for name, count in sorted(relation_class_counts.items())
            ),
            "average_relation_confidence": f"{average_relation_confidence:.6f}",
            "relation_evidence_quality": relation_evidence_quality,
            "relation_evidence": " | ".join(relation_evidence),
            "same_tier_candidate_count": str(len(ranked_candidates)),
            "top_candidate_title": top_candidate,
            "top_candidate_source_count": str(top_count),
            "top_candidate_source_share": f"{top_share:.6f}",
            "top_candidate_parent": top_block.parent_id if top_block else "",
            "top_candidate_path": top_block.path if top_block else "",
            "ranked_candidate_evidence": " | ".join(ranked_evidence),
            "identity_geometry_comparison": identity_geometry_comparison,
            "identity_geometry_overlap_titles": " | ".join(
                identity_geometry_overlap
            ),
            "preferred_candidate_title": preferred_candidate,
            "preferred_candidate_source": preferred_candidate_source,
            "declared_candidates": " | ".join(declared_candidates),
            "declared_candidate_status": declared_candidate_status,
            "candidate_status": status,
            "target_tracking_stale": "yes" if target_tracking_stale else "no",
            "confidence_ceiling": (
                "medium_pending_tracking_refresh"
                if target_tracking_stale
                else "review_footprint_and_usage_context"
            ),
            "line_provenance": row.get("line_provenance", ""),
            "finding_count": row.get("finding_count", ""),
            "reference_paths": row.get("paths", ""),
            "reference_locations": row.get("locations", ""),
            **usage_context,
            **reference_context,
            **context_location,
            **identity_descendant,
            "recommendation": recommendation,
            "auto_apply": "no",
            "yusseter_revision": row.get("yusseter_revision", ""),
            "current_asil_revision": row.get("current_asil_revision", ""),
            "premerge_revision": row.get("premerge_revision", ""),
            "relation_report": str(relation_report),
            "source_report": "tiger_p0_root_triage.csv",
        })

    output.sort(key=lambda item: (
        item.get("source_title", ""), item.get("root_cause_id", "")
    ))
    return output


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    roots = [
        row for row in read_csv(repo_root / INPUT_PATH)
        if row.get("action_priority") == "P0"
    ]
    yusseter_revision = git_revision(repo_root)
    asil_mod_repo = args.asil_mod_repo.resolve()
    current_asil_revision = git_revision(asil_mod_repo)
    rows: list[dict[str, str]] = []
    for root in roots:
        rows.append({
            "root_cause_id": root.get("root_cause_id", ""),
            "root_classification": root.get("classification", ""),
            "line_provenance": root.get("line_provenance", ""),
            "source_object": root.get("source_object", ""),
            "candidate_object": root.get("candidate_object", ""),
            "finding_count": root.get("finding_count", ""),
            "paths": root.get("paths", ""),
            "locations": root.get("locations", ""),
            "keys": root.get("keys", ""),
            "source_message": root.get("message", ""),
            "source_evidence": root.get("evidence", ""),
            "yusseter_revision": yusseter_revision,
            "current_asil_revision": current_asil_revision,
            "premerge_revision": args.premerge_revision,
            **classify(root),
            "source_report": INPUT_PATH,
        })

    output_csv = output_dir / "tiger_p0_root_triage.csv"
    write_csv(output_csv, rows)
    live_error_roots = consolidate_verified_live_errors(rows)
    live_error_output = output_dir / "tiger_p0_verified_live_error_roots.csv"
    write_csv(live_error_output, live_error_roots)
    province_relation_report = resolve_repo_path(
        repo_root, args.province_relation_report
    )
    canonical_province_relation = resolve_repo_path(
        repo_root, args.canonical_province_relation
    )
    title_relation = resolve_repo_path(repo_root, args.title_relation)
    current_landed_titles = (
        resolve_repo_path(repo_root, args.current_landed_titles)
        if args.current_landed_titles
        else repo_root / "BookmarksGit" / "common" / "landed_titles"
    )
    source_landed_titles = (
        resolve_repo_path(repo_root, args.source_landed_titles)
        if args.source_landed_titles
        else (
            asil_mod_repo
            / "BookmarksGit"
            / "common"
            / "landed_titles"
            / "00_landed_titles.txt"
        )
    )
    target_tracking = resolve_repo_path(repo_root, args.target_tracking)
    target_image = resolve_repo_path(repo_root, args.target_image)
    required_identity_inputs = [
        province_relation_report,
        canonical_province_relation,
        title_relation,
        current_landed_titles,
        source_landed_titles,
        target_tracking,
        target_image,
    ]
    missing_identity_inputs = [
        path for path in required_identity_inputs if not path.exists()
    ]
    if missing_identity_inputs:
        raise FileNotFoundError(
            "Missing undefined-barony identity input(s): "
            + " | ".join(str(path) for path in missing_identity_inputs)
        )
    current_blocks = parse_landed_titles_path(current_landed_titles)
    source_blocks = parse_landed_titles_path(source_landed_titles)
    target_tracking_stale = (
        target_tracking.stat().st_mtime < target_image.stat().st_mtime
    )
    province_relation_rows = read_csv(province_relation_report)
    title_relation_reverse = read_title_relation_reverse(title_relation)
    undefined_barony_rows = build_undefined_barony_identity_candidates(
        rows,
        current_blocks,
        source_blocks,
        province_relation_rows,
        read_csv(canonical_province_relation),
        province_relation_report,
        target_tracking_stale,
    )
    undefined_barony_output = (
        output_dir / "tiger_p0_undefined_barony_identity_candidates.csv"
    )
    write_csv(undefined_barony_output, undefined_barony_rows)
    undefined_higher_title_rows = build_undefined_higher_title_identity_candidates(
        repo_root,
        rows,
        current_blocks,
        source_blocks,
        province_relation_rows,
        title_relation_reverse,
        province_relation_report,
        target_tracking_stale,
    )
    undefined_higher_title_output = (
        output_dir / "tiger_p0_undefined_higher_title_identity_candidates.csv"
    )
    write_csv(undefined_higher_title_output, undefined_higher_title_rows)
    undefined_higher_no_candidate_rows = [
        row
        for row in undefined_higher_title_rows
        if row.get("candidate_status") in HIGHER_TITLE_NO_CANDIDATE_STATUSES
    ]
    undefined_higher_no_candidate_output = (
        output_dir / "tiger_p0_undefined_higher_title_no_candidate_context.csv"
    )
    write_csv(
        undefined_higher_no_candidate_output,
        undefined_higher_no_candidate_rows,
    )
    issue_counts = Counter(row["issue_status"] for row in rows)
    resolution_counts = Counter(row["resolution_status"] for row in rows)
    severity_counts = Counter(row["recommended_severity"] for row in rows)
    live_family_counts = Counter(row["root_family"] for row in live_error_roots)
    live_responsibility_counts = Counter(
        row["integration_responsibility"] for row in live_error_roots
    )
    undefined_barony_status_counts = Counter(
        row["candidate_status"] for row in undefined_barony_rows
    )
    undefined_higher_status_counts = Counter(
        row["candidate_status"] for row in undefined_higher_title_rows
    )
    undefined_higher_declared_counts = Counter(
        row["declared_candidate_status"] for row in undefined_higher_title_rows
    )
    undefined_higher_footprint_basis_counts = Counter(
        row["candidate_footprint_basis"] for row in undefined_higher_title_rows
    )
    undefined_higher_descendant_identity_counts = Counter(
        row["identity_descendant_candidate_status"]
        for row in undefined_higher_title_rows
    )
    undefined_higher_identity_geometry_counts = Counter(
        row["identity_geometry_comparison"] for row in undefined_higher_title_rows
    )
    undefined_higher_preferred_source_counts = Counter(
        row["preferred_candidate_source"]
        for row in undefined_higher_title_rows
        if row["preferred_candidate_source"]
    )
    undefined_higher_no_candidate_context_counts = Counter(
        row["usage_context_family"]
        for row in undefined_higher_no_candidate_rows
    )
    undefined_holy_site_location_basis_counts = Counter(
        row["context_location_basis"]
        for row in undefined_higher_no_candidate_rows
        if row["usage_context_family"] == "holy_site_county_reference"
    )
    undefined_holy_site_location_status_counts = Counter(
        row["context_location_candidate_status"]
        for row in undefined_higher_no_candidate_rows
        if row["usage_context_family"] == "holy_site_county_reference"
    )
    verified_live_raw_count = sum(
        int(row.get("finding_count") or 0)
        for row in rows
        if row.get("issue_status") == "verified_live_error"
    )
    consolidated_live_raw_count = sum(
        int(row.get("raw_tiger_report_count") or 0) for row in live_error_roots
    )
    if verified_live_raw_count != consolidated_live_raw_count:
        raise RuntimeError(
            "Verified live-error consolidation changed represented Tiger row count: "
            f"{verified_live_raw_count} != {consolidated_live_raw_count}"
        )
    fallback_count = sum(
        row["recovery_classification"] == "manual_unclassified_p0_review"
        for row in rows
    )
    summary = [
        "# Tiger P0 Root Triage",
        "",
        f"- roots: `{len(rows)}`",
        f"- represented raw Tiger rows: `{sum(int(row['finding_count']) for row in rows)}`",
        f"- unclassified fallback: `{fallback_count}`",
        "",
        "## Issue Status",
        "",
        *[f"- {name}: `{count}`" for name, count in issue_counts.most_common()],
        "",
        "## Resolution Status",
        "",
        *[f"- {name}: `{count}`" for name, count in resolution_counts.most_common()],
        "",
        "## Recommended Severity",
        "",
        *[f"- {name}: `{count}`" for name, count in severity_counts.most_common()],
        "",
        "## Independent Verified Live-Error Roots",
        "",
        f"- P0 triage rows: `{issue_counts.get('verified_live_error', 0)}`",
        f"- Independent remediation roots: `{len(live_error_roots)}`",
        f"- Represented raw Tiger rows: `{consolidated_live_raw_count}`",
        *[
            f"- family {name}: `{count}`"
            for name, count in live_family_counts.most_common()
        ],
        *[
            f"- responsibility {name}: `{count}`"
            for name, count in live_responsibility_counts.most_common()
        ],
        "",
        "## Undefined Barony Province-Identity Candidates",
        "",
        f"- Undefined barony roots: `{len(undefined_barony_rows)}`",
        f"- Target tracking stale: `{'yes' if target_tracking_stale else 'no'}`",
        *[
            f"- status {name}: `{count}`"
            for name, count in undefined_barony_status_counts.most_common()
        ],
        "- All geometry candidates remain manual review; none are auto-applied.",
        "",
        "## Undefined Higher-Title Footprint Candidates",
        "",
        f"- Undefined county/duchy/kingdom roots: `{len(undefined_higher_title_rows)}`",
        f"- Target tracking stale: `{'yes' if target_tracking_stale else 'no'}`",
        *[
            f"- status {name}: `{count}`"
            for name, count in undefined_higher_status_counts.most_common()
        ],
        *[
            f"- declared candidate {name}: `{count}`"
            for name, count in undefined_higher_declared_counts.most_common()
        ],
        *[
            f"- footprint basis {name}: `{count}`"
            for name, count in undefined_higher_footprint_basis_counts.most_common()
        ],
        *[
            f"- descendant identity {name}: `{count}`"
            for name, count
            in undefined_higher_descendant_identity_counts.most_common()
        ],
        *[
            f"- identity versus geometry {name}: `{count}`"
            for name, count in undefined_higher_identity_geometry_counts.most_common()
        ],
        *[
            f"- preferred candidate source {name}: `{count}`"
            for name, count in undefined_higher_preferred_source_counts.most_common()
        ],
        (
            "- Higher-title roots without a same-tier candidate: "
            f"`{len(undefined_higher_no_candidate_rows)}`"
        ),
        *[
            f"- no-candidate context {name}: `{count}`"
            for name, count
            in undefined_higher_no_candidate_context_counts.most_common()
        ],
        *[
            f"- holy-site location basis {name}: `{count}`"
            for name, count in undefined_holy_site_location_basis_counts.most_common()
        ],
        *[
            f"- holy-site location status {name}: `{count}`"
            for name, count in undefined_holy_site_location_status_counts.most_common()
        ],
        "- Footprint candidates are same-tier evidence only and are never auto-applied.",
        "",
        "## Safety",
        "",
        "- This report does not modify BookmarksGit source files.",
        "- A verified error can still remain review-only when no safe identity mapping exists.",
        "- Candidate mappings are not automatically applied.",
    ]
    (output_dir / "tiger_p0_root_triage_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print(f"roots={len(rows)}")
    print(f"raw={sum(int(row['finding_count']) for row in rows)}")
    print(f"issue={dict(sorted(issue_counts.items()))}")
    print(f"resolution={dict(sorted(resolution_counts.items()))}")
    print(f"verified_live_error_roots={len(live_error_roots)}")
    print(f"verified_live_error_raw={consolidated_live_raw_count}")
    print(f"undefined_barony_roots={len(undefined_barony_rows)}")
    print(f"undefined_barony_status={dict(sorted(undefined_barony_status_counts.items()))}")
    print(f"undefined_higher_title_roots={len(undefined_higher_title_rows)}")
    print(f"undefined_higher_title_status={dict(sorted(undefined_higher_status_counts.items()))}")
    print(f"undefined_higher_declared={dict(sorted(undefined_higher_declared_counts.items()))}")
    print(f"undefined_higher_footprint_basis={dict(sorted(undefined_higher_footprint_basis_counts.items()))}")
    print(f"undefined_higher_descendant_identity={dict(sorted(undefined_higher_descendant_identity_counts.items()))}")
    print(f"undefined_higher_identity_geometry={dict(sorted(undefined_higher_identity_geometry_counts.items()))}")
    print(f"undefined_higher_preferred_source={dict(sorted(undefined_higher_preferred_source_counts.items()))}")
    print(f"undefined_higher_no_candidate_roots={len(undefined_higher_no_candidate_rows)}")
    print(f"undefined_higher_no_candidate_context={dict(sorted(undefined_higher_no_candidate_context_counts.items()))}")
    print(f"undefined_holy_site_location_basis={dict(sorted(undefined_holy_site_location_basis_counts.items()))}")
    print(f"undefined_holy_site_location_status={dict(sorted(undefined_holy_site_location_status_counts.items()))}")
    print(f"fallback={fallback_count}")
    print(f"output={output_csv}")
    print(f"live_error_output={live_error_output}")
    print(f"undefined_barony_output={undefined_barony_output}")
    print(f"undefined_higher_title_output={undefined_higher_title_output}")
    print(f"undefined_higher_no_candidate_output={undefined_higher_no_candidate_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
