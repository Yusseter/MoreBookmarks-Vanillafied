from __future__ import annotations

import argparse
import csv
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


TIGER_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "ck3_tiger_current_only_priority.csv"
)
SEMANTIC_TITLE_PATH = (
    ".codex/works/analysis/generated/repo_semantic_compatibility/"
    "source_shared_title_reference_candidates.csv"
)
IDENTITY_PATH = (
    ".codex/works/analysis/generated/landed_title_source_identity/"
    "landed_title_source_identity_audit.csv"
)
RELATION_PATH = (
    ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv"
)
LOCALIZATION_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "localization_requirements.csv"
)
RUNTIME_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "bookmark_runtime_static/bookmark_runtime_static_findings_compact.csv"
)
UPSTREAM_PATH = (
    ".codex/works/analysis/generated/repo_semantic_compatibility/"
    "upstream_since_last_merge.csv"
)
LANDED_PATH = "BookmarksGit/common/landed_titles/00_landed_titles.txt"
OUTPUT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "tiger_current_only_classification"
)
DEFAULT_ASIL_MOD_ROOT = (
    Path(__file__).resolve().parents[3].parent / "Leviathonlx MoreBookmarks-Plus"
)
DEFAULT_PREMERGE_REVISION = "09588cbb5212a31bc4a373b6990b2c4da1203a35"

TITLE_RE = re.compile(r"^[ekdcbh]_[A-Za-z0-9_]+$")
MISSING_TITLE_RE = re.compile(r"^title ([ekdcbh]_[A-Za-z0-9_]+) not defined")
MISSING_LOC_RE = re.compile(r"^missing english localization key (.+)$")
UNKNOWN_TITLE_TOKEN_RE = re.compile(r"^unknown token [`]([ekdcbh]_[A-Za-z0-9_]+)[`]$")
MISSING_CHARACTER_RE = re.compile(r"^character ([A-Za-z0-9_]+) not defined")
MISSING_FILE_RE = re.compile(r"^file (.+) does not exist$")
TITLE_MESSAGE_RE = re.compile(r"^([ekdcbh]_[A-Za-z0-9_]+) (?:has|is|does)\b")
TIER_RANK = {"b": 0, "c": 1, "d": 2, "k": 3, "e": 4, "h": 5}

# Review evidence only. These aliases are never applied by this audit tool.
KNOWN_CHARACTER_ALIAS_CANDIDATES = {
    "bohai_gao_275": (
        "han_3310",
        "same_historical_person:Gao_Pian; adjacent_same_date_assignments_use_candidate; "
        "asil_mod_history_uses_candidate",
    ),
}

# Line-specific integration evidence. These remain review candidates, not fixes.
KNOWN_TITLE_REFERENCE_LINE_CONTEXT = {
    **{
        (
            "BookmarksGit/map_data/geographical_regions/geographical_region.txt",
            line,
            "d_argun_china",
        ): (
            "stale_redundant_region_title_reference",
            "",
            "asil_mod_argun_is_distinct_from_current_hailar; source_county_footprint_maps_to_"
            "current_wasteland_1466; adjacent_d_SW_dashiweiguo_already_present_in_region",
            "high_context_review",
            "remove_stale_redundant_region_token_after_region_review",
        )
        for line in ("144", "612", "6825")
    },
    **{
        (
            "BookmarksGit/map_data/geographical_regions/geographical_region.txt",
            line,
            "d_argun_china",
        ): (
            "stale_region_title_no_exact_current_counterpart",
            "",
            "asil_mod_argun_is_distinct_from_current_hailar; source_county_footprint_maps_to_"
            "current_wasteland_1466; d_SW_dashiweiguo_is_adjacent_only_not_exact_counterpart",
            "high_no_counterpart_review",
            "remove_or_choose_adjacent_region_substitute_after_semantic_review",
        )
        for line in ("2405", "6169", "6860")
    },
}


# Path-specific integration evidence. These remain review candidates, not fixes.
KNOWN_TITLE_REFERENCE_CONTEXT = {
    (
        "BookmarksGit/localization/replace/english/RICE_tarim_basin_l_english.yml",
        "k_hexi",
    ): (
        "split_title_reference_review",
        "k_guishi | k_xia",
        "vanilla_hexi_children_split:d_guasha->d_guiyi->k_guishi; "
        "d_gansu->d_ganzhou->k_xia",
        "high_context_review",
        "remap_rice_hexi_context_to_current_split_titles",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify current-only CK3-Tiger findings using current audit evidence."
    )
    default_root = Path(__file__).resolve().parents[3]
    parser.add_argument("--repo-root", type=Path, default=default_root)
    parser.add_argument("--asil-mod-root", type=Path, default=DEFAULT_ASIL_MOD_ROOT)
    parser.add_argument("--premerge-revision", default=DEFAULT_PREMERGE_REVISION)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, skipinitialspace=True)]


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def split_tokens(value: str) -> list[str]:
    result = []
    for raw in re.split(r"[&;|]", value or ""):
        token = raw.replace("(second)", "").strip()
        if TITLE_RE.fullmatch(token):
            result.append(token)
    return result


def tier(title_id: str) -> str:
    return title_id.split("_", 1)[0] if "_" in title_id else ""


def load_landed_ids(path: Path) -> set[str]:
    pattern = re.compile(r"^\s*([ekdcbh]_[A-Za-z0-9_]+)\s*=\s*\{")
    result = set()
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        match = pattern.match(line.split("#", 1)[0])
        if match:
            result.add(match.group(1))
    return result


def load_file_lines(repo_root: Path):
    cache: dict[str, list[str]] = {}

    def line_at(relative: str, line_number: str) -> str:
        if relative not in cache:
            path = repo_root / relative
            cache[relative] = (
                path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
                if path.exists()
                else []
            )
        try:
            index = int(line_number) - 1
        except (TypeError, ValueError):
            return ""
        lines = cache[relative]
        return lines[index].strip()[:500] if 0 <= index < len(lines) else ""

    return line_at


def build_line_provenance(
    repo_root: Path, asil_mod_root: Path, premerge_revision: str
):
    premerge_cache: dict[str, list[str] | None] = {}
    asil_cache: dict[str, list[str] | None] = {}

    def premerge_lines(relative: str) -> list[str] | None:
        if relative not in premerge_cache:
            result = subprocess.run(
                ["git", "show", f"{premerge_revision}:{relative.replace(chr(92), '/')}"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            premerge_cache[relative] = result.stdout.splitlines() if result.returncode == 0 else None
        return premerge_cache[relative]

    def asil_lines(relative: str) -> list[str] | None:
        if relative not in asil_cache:
            path = asil_mod_root / relative
            asil_cache[relative] = (
                path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
                if path.exists()
                else None
            )
        return asil_cache[relative]

    def classify(relative: str, preview: str) -> tuple[str, str, str]:
        if not preview or preview in {"{", "}", "};"}:
            return "insufficient_line_signature", "0", "0"
        normalized = preview.strip()
        before = premerge_lines(relative)
        source = asil_lines(relative)
        before_count = sum(line.strip() == normalized for line in before or [])
        source_count = sum(line.strip() == normalized for line in source or [])
        if before_count and source_count:
            provenance = "shared_premerge_and_asil_line"
        elif before_count:
            provenance = "preexisting_yusseter_line"
        elif source_count:
            provenance = "post_premerge_asil_line"
        elif before is None:
            provenance = "path_absent_at_premerge"
        else:
            provenance = "current_only_or_adapted_line"
        return provenance, str(before_count), str(source_count)

    return classify


def ancestor_at_tier(
    title_id: str, target_tier: str, parent_by_title: dict[str, str]
) -> str:
    current = title_id
    seen = set()
    while current and current not in seen:
        seen.add(current)
        if tier(current) == target_tier:
            return current
        current_rank = TIER_RANK.get(tier(current), -1)
        target_rank = TIER_RANK.get(target_tier, -1)
        if current_rank > target_rank:
            return ""
        current = parent_by_title.get(current, "")
    return ""


def build_relation_maps(
    rows: list[dict[str, str]], current_ids: set[str]
) -> tuple[dict[str, set[str]], set[str]]:
    candidates: dict[str, set[str]] = defaultdict(set)
    no_counterpart: set[str] = set()
    for row in rows:
        current_raw = (row.get("source_title_id") or "").strip()
        source = split_tokens(row.get("mod_title_id") or "")
        current = split_tokens(current_raw)
        if not source:
            continue
        if not current:
            if current_raw.lower() in {"none", "*there_is_no*", "there_is_no"}:
                no_counterpart.update(source)
            continue
        if len(current) == len(source):
            pairs = zip(current, source, strict=True)
        elif len(current) == 1:
            pairs = ((current[0], item) for item in source)
        elif len(source) == 1:
            pairs = ((item, source[0]) for item in current)
        else:
            continue
        for current_id, source_id in pairs:
            if current_id in current_ids and tier(current_id) == tier(source_id):
                candidates[source_id].add(current_id)
    return candidates, no_counterpart


def build_identity_maps(
    rows: list[dict[str, str]], current_ids: set[str]
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[tuple[str, str], list[str]]]:
    parent_by_title = {
        row["title_id"]: row.get("current_parent", "")
        for row in rows
        if row.get("title_id") in current_ids
    }
    direct: dict[str, set[str]] = defaultdict(set)
    parent_derived: dict[str, set[str]] = defaultdict(set)
    evidence: dict[tuple[str, str], list[str]] = defaultdict(list)

    for row in rows:
        current = row.get("title_id", "")
        if current not in current_ids:
            continue
        source_tokens = {
            (source, "manual")
            for source in split_tokens(row.get("manual_mod_title_tokens", ""))
        }
        mod_best = row.get("mod_best_title", "")
        if TITLE_RE.fullmatch(mod_best or ""):
            source_tokens.add((mod_best, "asil_mod"))
        vanilla_best = row.get("vanilla_title", "")
        if TITLE_RE.fullmatch(vanilla_best or ""):
            source_tokens.add((vanilla_best, "vanilla"))

        for source, origin in source_tokens:
            candidate = ancestor_at_tier(current, tier(source), parent_by_title)
            if not candidate:
                continue
            bucket = direct if candidate == current and tier(candidate) == tier(source) else parent_derived
            bucket[source].add(candidate)
            evidence[(source, candidate)].append(
                f"{origin}_identity:{current}:{row.get('confidence', '')}:{row.get('source_decision', '')}"
            )

        current_parent = row.get("current_parent", "")
        for source_parent, source_child, origin in (
            (row.get("mod_best_parent", ""), mod_best, "asil_mod"),
            (row.get("vanilla_parent", ""), vanilla_best, "vanilla"),
        ):
            if (
                TITLE_RE.fullmatch(source_parent or "")
                and current_parent in current_ids
                and tier(source_parent) == tier(current_parent)
            ):
                parent_derived[source_parent].add(current_parent)
                evidence[(source_parent, current_parent)].append(
                    f"{origin}_child:{source_child or '?'}->{current}:{row.get('confidence', '')}"
                )
    return direct, parent_derived, evidence


def unique_candidate(candidates: set[str]) -> str:
    return next(iter(candidates)) if len(candidates) == 1 else ""


def title_resolution(
    row: dict[str, str],
    source_title: str,
    exact_semantic: dict[tuple[str, str, str], str],
    relation: dict[str, set[str]],
    identity_direct: dict[str, set[str]],
    identity_parent: dict[str, set[str]],
    identity_evidence: dict[tuple[str, str], list[str]],
    no_counterpart: set[str],
) -> tuple[str, str, str, str, str]:
    known = KNOWN_TITLE_REFERENCE_LINE_CONTEXT.get(
        (row["path"], row["line"], source_title)
    ) or KNOWN_TITLE_REFERENCE_CONTEXT.get((row["path"], source_title))
    if known:
        return known

    exact = exact_semantic.get((row["path"], row["line"], source_title), "")
    if exact and tier(exact) == tier(source_title):
        return (
            "mapped_title_reference_candidate",
            exact,
            "exact_path_line_semantic_mapping",
            "high_mapping_context_review",
            "review_reference_semantics_then_remap",
        )

    if exact:
        parent_candidates = identity_parent.get(source_title, set())
        parent_candidate = unique_candidate(parent_candidates)
        alternatives = [exact]
        if parent_candidate and parent_candidate != exact:
            alternatives.append(parent_candidate)
        return (
            "cross_tier_semantic_candidate_review",
            " | ".join(alternatives),
            f"exact_cross_tier:{source_title}->{exact}"
            + (f" | same_tier_parent:{parent_candidate}" if parent_candidate else ""),
            "medium_context_review",
            "choose_county_or_same_tier_parent_from_consuming_context",
        )

    relation_candidates = relation.get(source_title, set())
    relation_candidate = unique_candidate(relation_candidates)
    if relation_candidate:
        return (
            "mapped_title_reference_candidate",
            relation_candidate,
            "manual_title_relation",
            "high_mapping_context_review",
            "review_reference_semantics_then_remap",
        )
    if len(relation_candidates) > 1:
        return (
            "ambiguous_title_mapping_review",
            " | ".join(sorted(relation_candidates)),
            "manual_title_relation_multiple_candidates",
            "low",
            "manual_title_mapping_decision",
        )

    direct_candidates = identity_direct.get(source_title, set())
    direct_candidate = unique_candidate(direct_candidates)
    if direct_candidate:
        details = identity_evidence.get((source_title, direct_candidate), [])
        return (
            "identity_direct_title_candidate",
            direct_candidate,
            " | ".join(details[:8]),
            "medium_context_review",
            "verify_identity_then_remap",
        )
    if len(direct_candidates) > 1:
        return (
            "ambiguous_identity_mapping_review",
            " | ".join(sorted(direct_candidates)),
            "multiple_identity_direct_candidates",
            "low",
            "manual_title_mapping_decision",
        )

    parent_candidates = identity_parent.get(source_title, set())
    parent_candidate = unique_candidate(parent_candidates)
    if parent_candidate:
        details = identity_evidence.get((source_title, parent_candidate), [])
        return (
            "parent_derived_title_candidate",
            parent_candidate,
            " | ".join(details[:8]),
            "medium_context_review",
            "verify_region_or_script_semantics_then_remap",
        )
    if len(parent_candidates) > 1:
        return (
            "ambiguous_parent_derived_review",
            " | ".join(sorted(parent_candidates)),
            "multiple_parent_derived_candidates",
            "low",
            "manual_title_mapping_decision",
        )

    if source_title in no_counterpart:
        return (
            "explicit_no_current_counterpart_reference",
            "",
            "manual_relation_marks_no_current_counterpart",
            "high",
            "remove_or_redesign_reference_after_context_review",
        )
    return (
        "unresolved_missing_title_reference",
        "",
        "no_current_mapping_evidence",
        "none",
        "derive_mapping_or_remove_reference",
    )


def history_effect_title_resolution(
    row: dict[str, str],
    source_title: str,
    preview: str,
    current_ids: set[str],
    exact_semantic: dict[tuple[str, str, str], str],
    relation: dict[str, set[str]],
    identity_direct: dict[str, set[str]],
    identity_parent: dict[str, set[str]],
    identity_evidence: dict[tuple[str, str], list[str]],
    no_counterpart: set[str],
) -> tuple[str, str, str, str, str, str]:
    if "set_capital_county" in preview and source_title in current_ids:
        return (
            "history_effect_missing_title_scope_prefix",
            f"title:{source_title}",
            "current_title_exists; set_capital_county_requires_title_scope",
            "high",
            "add_title_scope_prefix_after_context_review",
            "P0",
        )

    classification, candidate, evidence, confidence, recommendation = title_resolution(
        row,
        source_title,
        exact_semantic,
        relation,
        identity_direct,
        identity_parent,
        identity_evidence,
        no_counterpart,
    )
    effect_kind = (
        "set_capital_county"
        if "set_capital_county" in preview
        else "set_coa"
        if "set_coa" in preview
        else "history_effect"
    )
    quoted = f'"{source_title}"' in preview
    evidence_parts = [f"effect={effect_kind}"]
    if quoted:
        evidence_parts.append("quoted_title_key")
    if evidence:
        evidence_parts.append(evidence)

    if classification in {
        "mapped_title_reference_candidate",
        "identity_direct_title_candidate",
        "parent_derived_title_candidate",
    }:
        classification = "history_effect_title_reference_candidate"
    elif classification in {
        "cross_tier_semantic_candidate_review",
        "ambiguous_title_mapping_review",
        "ambiguous_identity_mapping_review",
        "ambiguous_parent_derived_review",
    }:
        classification = "history_effect_title_reference_review"
    elif classification == "explicit_no_current_counterpart_reference":
        classification = "history_effect_no_current_counterpart"
    elif classification == "unresolved_missing_title_reference":
        classification = "unresolved_history_effect_title_reference"

    if effect_kind == "set_capital_county":
        recommendation = "select_current_title_then_use_title_scope_prefix"
    elif effect_kind == "set_coa":
        recommendation = "select_current_title_coa_key_then_update_effect"
    return (
        classification,
        candidate,
        "; ".join(evidence_parts),
        confidence,
        recommendation,
        "P0",
    )


def generic_classification(
    row: dict[str, str],
    localization: dict[str, dict[str, str]],
    pending_upstream_paths: set[str],
    pending_removed_missing_file_lines: set[tuple[str, str]],
    runtime_blocker_titles: set[str],
) -> tuple[str, str, str, str, str, str]:
    key = row["key"]
    message = row["message"]
    path = row["path"]

    if path in pending_upstream_paths and key in {"duplicate-character", "missing-item"}:
        return (
            "pending_asil_mod_fix",
            "",
            "latest_asil_mod_commit_changes_this_file",
            "high",
            "merge_pending_asil_mod_commit_then_retest",
            "P0",
        )

    if key == "missing-file" and (path, row.get("line", "")) in pending_removed_missing_file_lines:
        return (
            "pending_asil_mod_fix",
            "",
            "latest_asil_mod_commit_deactivates_missing_asset_consumer",
            "high",
            "merge_pending_asil_mod_commit_then_retest",
            "P1",
        )

    loc_match = MISSING_LOC_RE.match(message)
    if key == "missing-localization" and loc_match:
        loc_key = loc_match.group(1)
        requirement = localization.get(loc_key)
        if requirement:
            status = requirement.get("status", "")
            if status == "missing_effective_mapped_source_available":
                return (
                    "localization_mapped_source_candidate",
                    requirement.get("source_key", ""),
                    f"{requirement.get('source_origin', '')}:{requirement.get('source_path', '')}",
                    "high_source_context_review",
                    "review_and_copy_or_alias_localization",
                    "P1",
                )
            if status == "runtime_generated_noble_family_name":
                return (
                    "intentional_runtime_generated_localization",
                    "",
                    status,
                    "high",
                    "no_action",
                    "P3",
                )
            if status == "missing_everywhere":
                return (
                    "localization_missing_everywhere",
                    "",
                    status,
                    "high",
                    "author_localization_or_confirm_intent",
                    "P1",
                )
            return (
                "localization_requirement_review",
                requirement.get("source_key", ""),
                status,
                "medium",
                "review_localization_requirement",
                "P2",
            )
        if loc_key.startswith("zz_placeholder_"):
            return (
                "intentional_definition_placeholder_name",
                "",
                "placeholder_definition_name",
                "high",
                "no_action",
                "P3",
            )
        return (
            "definition_name_localization_review",
            "",
            "not_in_title_localization_closure",
            "medium",
            "review_definition_name_or_localization",
            "P2",
        )

    if key == "history":
        match = TITLE_MESSAGE_RE.match(message)
        history_title = match.group(1) if match else ""
        runtime = history_title in runtime_blocker_titles
        return (
            "temporal_history_runtime_overlap" if runtime else "temporal_history_quality_review",
            "",
            "bookmark_static_blocker_for_title" if runtime else "not_confirmed_as_current_only_bookmark_blocker",
            "medium" if runtime else "reasonable",
            "review_holder_lifespan_and_liege_timeline",
            "P1" if runtime else "P2",
        )

    character_match = MISSING_CHARACTER_RE.match(message)
    if key == "missing-item" and character_match:
        character_id = character_match.group(1)
        if character_id in KNOWN_CHARACTER_ALIAS_CANDIDATES:
            candidate, alias_evidence = KNOWN_CHARACTER_ALIAS_CANDIDATES[character_id]
            return (
                "stale_character_alias_candidate",
                candidate,
                alias_evidence,
                "high_context_review",
                "verify_same_person_then_replace_stale_holder_alias",
                "P0",
            )
        return (
            "missing_character_reference",
            "",
            "character_not_defined_in_effective_history",
            "high",
            "identify_character_alias_or_remove_stale_assignment",
            "P0",
        )
    if key == "missing-item" and "has no title history" in message:
        return (
            "missing_title_history_review",
            "",
            "referenced_title_has_no_history_block",
            "reasonable",
            "confirm_title_history_requirement",
            "P2",
        )
    if key in {"reader-directives", "validation"}:
        return (
            "undefined_reader_variable_or_numeric_value",
            "",
            message,
            "high",
            "restore_variable_definition_or_replace_with_number",
            "P0",
        )
    if key == "unknown-field" and "unknown token `@" in message:
        return (
            "undefined_reader_variable_or_numeric_value",
            "",
            message,
            "high",
            "restore_variable_definition_or_replace_with_number",
            "P0",
        )
    if key == "unknown-field" and re.search(r"unknown token `[ekdcbh]_[^`]+`", message):
        return (
            "orphan_or_unmapped_title_history_block",
            "",
            "title_token_parsed_as_field_inside_another_block",
            "high",
            "inspect_history_block_structure_and_title_mapping",
            "P0",
        )
    if key == "title-tier":
        return (
            "invalid_title_tier_relationship",
            "",
            message,
            "high",
            "repair_liege_mapping_or_history_structure",
            "P0",
        )
    if key == "parse-error":
        return (
            "parse_or_sentinel_order_error",
            "",
            message,
            "high",
            "repair_file_order_then_retest",
            "P0",
        )
    if key == "localization-key-collision":
        return (
            "localization_hash_collision_review",
            "",
            message,
            "high",
            "rename_local_key_only_after_reference_audit",
            "P1",
        )
    if key == "missing-file":
        return (
            "missing_asset_reference",
            "",
            message,
            "high",
            "restore_asset_or_remap_reference",
            "P1",
        )
    if key in {"duplicate-item", "exact-duplicate-item", "duplicate-field"}:
        return (
            "duplicate_definition_review",
            "",
            message,
            "medium",
            "compare_effective_override_intent",
            "P2",
        )
    if key in {"strict-scopes", "scopes"}:
        return (
            "scope_semantics_review",
            "",
            message,
            "medium",
            "validate_scope_against_current_schema_and_runtime",
            "P1" if key == "strict-scopes" else "P2",
        )
    if key == "missing-file":
        return ("missing_asset_reference", "", message, "high", "restore_asset_or_remap_reference", "P1")
    if key == "encoding":
        return ("encoding_quality_review", "", message, "high", "normalize_required_encoding", "P2")
    if key == "brace-placement":
        return ("brace_placement_review", "", message, "medium", "inspect_block_layout", "P2")
    if key == "colors":
        return ("color_formatting_quality", "", message, "reasonable", "optional_format_cleanup", "P3")
    if key == "suggest-localization":
        return ("localization_style_tip", "", message, "reasonable", "optional_style_review", "P3")
    return (
        "unclassified_tiger_review",
        "",
        message,
        "none",
        "manual_review",
        "P2",
    )


def build_root_causes(classified: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in classified:
        root_object = row.get("source_object") or row.get("message", "")
        key = (
            row.get("classification", ""),
            root_object,
            row.get("candidate_object", ""),
            row.get("line_provenance", ""),
            row.get("recommendation", ""),
        )
        grouped[key].append(row)

    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    ordered = sorted(
        grouped.items(),
        key=lambda item: (
            min(
                priority_rank.get(row.get("action_priority", "P3"), 9)
                for row in item[1]
            ),
            item[0],
        ),
    )
    root_causes = []
    for index, (group_key, rows) in enumerate(ordered, start=1):
        classification, source_object, candidate_object, provenance, recommendation = group_key
        paths = sorted({row.get("path", "") for row in rows if row.get("path")})
        locations = sorted(
            {
                f"{row.get('path', '')}:{row.get('line', '')}"
                for row in rows
                if row.get("path")
            }
        )
        priorities = sorted(
            {row.get("action_priority", "") for row in rows},
            key=lambda value: priority_rank.get(value, 9),
        )
        evidence = []
        for row in rows:
            value = row.get("evidence", "")
            if value and value not in evidence:
                evidence.append(value)
        root_causes.append(
            {
                "root_cause_id": f"RC{index:04d}",
                "action_priority": priorities[0] if priorities else "",
                "classification": classification,
                "line_provenance": provenance,
                "source_object": source_object,
                "candidate_object": candidate_object,
                "finding_count": str(len(rows)),
                "unique_path_count": str(len(paths)),
                "paths": " | ".join(paths),
                "locations": " | ".join(locations),
                "keys": " | ".join(sorted({row.get("key", "") for row in rows})),
                "message": rows[0].get("message", ""),
                "evidence": " || ".join(evidence[:12]),
                "recommendation": recommendation,
            }
        )
    return root_causes


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)

    tiger_rows = read_csv(repo_root / TIGER_PATH)
    semantic_rows = read_csv(repo_root / SEMANTIC_TITLE_PATH)
    identity_rows = read_csv(repo_root / IDENTITY_PATH)
    relation_rows = read_csv(repo_root / RELATION_PATH)
    localization_rows = read_csv(repo_root / LOCALIZATION_PATH)
    runtime_rows = read_csv(repo_root / RUNTIME_PATH)
    upstream_rows = read_csv(repo_root / UPSTREAM_PATH)
    current_ids = load_landed_ids(repo_root / LANDED_PATH)
    line_at = load_file_lines(repo_root)
    line_provenance = build_line_provenance(
        repo_root, args.asil_mod_root.resolve(), args.premerge_revision
    )

    exact_semantic = {
        (row["path"], row["line"], row["source_title_id"]): row["candidate_current_title_id"]
        for row in semantic_rows
        if row.get("candidate_current_title_id") in current_ids
    }
    relation, no_counterpart = build_relation_maps(relation_rows, current_ids)
    identity_direct, identity_parent, identity_evidence = build_identity_maps(
        identity_rows, current_ids
    )
    localization = {row["key"]: row for row in localization_rows}
    pending_upstream_paths = {
        row["path"] for row in upstream_rows if row.get("classification") == "new_upstream_not_in_current_merge"
    }
    pending_removed_missing_file_lines: set[tuple[str, str]] = set()
    active_asil_cache: dict[str, str] = {}
    for row in tiger_rows:
        if row.get("key") != "missing-file" or row.get("path") not in pending_upstream_paths:
            continue
        missing_match = MISSING_FILE_RE.match(row.get("message", ""))
        preview = line_at(row.get("path", ""), row.get("line", ""))
        quoted_values = re.findall(r'"([^"]+)"', preview)
        if not missing_match or not quoted_values:
            continue
        asset_stem = Path(missing_match.group(1)).stem
        if not any(asset_stem.endswith(value) for value in quoted_values):
            continue
        path = row["path"]
        if path not in active_asil_cache:
            asil_path = args.asil_mod_root.resolve() / path
            active_asil_cache[path] = "\n".join(
                line.split("#", 1)[0]
                for line in asil_path.read_text(
                    encoding="utf-8-sig", errors="replace"
                ).splitlines()
            ) if asil_path.exists() else ""
        if not any(f'"{value}"' in active_asil_cache[path] for value in quoted_values):
            pending_removed_missing_file_lines.add((path, row.get("line", "")))
    runtime_blocker_titles = {
        row.get("title_id", "")
        for row in runtime_rows
        if row.get("severity") == "blocker"
    }

    classified = []
    for row in tiger_rows:
        preview = line_at(row["path"], row["line"])
        source_title_match = MISSING_TITLE_RE.match(row["message"])
        unknown_title_match = (
            UNKNOWN_TITLE_TOKEN_RE.match(row["message"])
            if row["key"] == "unknown-field"
            else None
        )
        if source_title_match:
            source_title = source_title_match.group(1)
            classification, candidate, evidence, confidence, recommendation = title_resolution(
                row,
                source_title,
                exact_semantic,
                relation,
                identity_direct,
                identity_parent,
                identity_evidence,
                no_counterpart,
            )
            priority = "P0" if classification in {
                "unresolved_missing_title_reference",
                "ambiguous_title_mapping_review",
                "ambiguous_identity_mapping_review",
                "ambiguous_parent_derived_review",
                "stale_redundant_region_title_reference",
                "stale_region_title_no_exact_current_counterpart",
                "split_title_reference_review",
            } else "P1"
        elif unknown_title_match:
            source_title = unknown_title_match.group(1)
            (
                classification,
                candidate,
                evidence,
                confidence,
                recommendation,
                priority,
            ) = history_effect_title_resolution(
                row,
                source_title,
                preview,
                current_ids,
                exact_semantic,
                relation,
                identity_direct,
                identity_parent,
                identity_evidence,
                no_counterpart,
            )
        else:
            classification, candidate, evidence, confidence, recommendation, priority = generic_classification(
                row,
                localization,
                pending_upstream_paths,
                pending_removed_missing_file_lines,
                runtime_blocker_titles,
            )
            character_match = MISSING_CHARACTER_RE.match(row["message"])
            source_title = character_match.group(1) if character_match else ""
        provenance, premerge_occurrences, asil_occurrences = line_provenance(
            row["path"], preview
        )
        classified.append(
            {
                **row,
                "classification": classification,
                "action_priority": priority,
                "source_object": source_title,
                "candidate_object": candidate,
                "evidence": evidence,
                "classification_confidence": confidence,
                "recommendation": recommendation,
                "line_preview": preview,
                "line_provenance": provenance,
                "premerge_exact_line_occurrences": premerge_occurrences,
                "asil_mod_exact_line_occurrences": asil_occurrences,
            }
        )

    fields = list(tiger_rows[0]) + [
        "classification",
        "action_priority",
        "source_object",
        "candidate_object",
        "evidence",
        "classification_confidence",
        "recommendation",
        "line_preview",
        "line_provenance",
        "premerge_exact_line_occurrences",
        "asil_mod_exact_line_occurrences",
    ]
    write_csv(output_dir / "ck3_tiger_current_only_classified.csv", classified, fields)
    missing_title_rows = [
        row for row in classified if TITLE_RE.fullmatch(row["source_object"] or "")
    ]
    write_csv(
        output_dir / "ck3_tiger_missing_title_resolution_candidates.csv",
        missing_title_rows,
        fields,
    )
    root_causes = build_root_causes(classified)
    root_cause_fields = [
        "root_cause_id",
        "action_priority",
        "classification",
        "line_provenance",
        "source_object",
        "candidate_object",
        "finding_count",
        "unique_path_count",
        "paths",
        "locations",
        "keys",
        "message",
        "evidence",
        "recommendation",
    ]
    write_csv(
        output_dir / "ck3_tiger_current_only_root_causes.csv",
        root_causes,
        root_cause_fields,
    )

    class_counts = Counter(row["classification"] for row in classified)
    priority_counts = Counter(row["action_priority"] for row in classified)
    key_counts = Counter(row["key"] for row in classified)
    provenance_counts = Counter(row["line_provenance"] for row in classified)
    root_priority_counts = Counter(row["action_priority"] for row in root_causes)
    title_class_counts = Counter(row["classification"] for row in missing_title_rows)
    unique_title_classes: dict[str, set[str]] = defaultdict(set)
    for row in missing_title_rows:
        unique_title_classes[row["classification"]].add(row["source_object"])

    lines = [
        "# CK3-Tiger Current-Only Classification",
        "",
        f"- rows: `{len(classified)}`",
        f"- missing-title rows: `{len(missing_title_rows)}`",
        f"- unique missing title IDs: `{len({row['source_object'] for row in missing_title_rows})}`",
        f"- root causes after deduplication: `{len(root_causes)}`",
        "- live mod files changed: `no`",
        "- mapping candidates are review evidence, not automatic replacements",
        "",
        "## Action Priority",
        "",
    ]
    lines.extend(f"- `{name}`: `{count}`" for name, count in sorted(priority_counts.items()))
    lines.extend(["", "## Classification Counts", ""])
    lines.extend(
        f"- `{name}`: `{count}`" for name, count in class_counts.most_common()
    )
    lines.extend(["", "## Missing Title Resolution", ""])
    for name, count in title_class_counts.most_common():
        lines.append(
            f"- `{name}`: `{count}` rows / `{len(unique_title_classes[name])}` unique source IDs"
        )
    lines.extend(["", "## Tiger Key Counts", ""])
    lines.extend(f"- `{name}`: `{count}`" for name, count in key_counts.most_common())
    lines.extend(["", "## Exact Line Provenance", ""])
    lines.extend(
        f"- `{name}`: `{count}`" for name, count in provenance_counts.most_common()
    )
    lines.extend(["", "## Root Cause Priority", ""])
    lines.extend(
        f"- `{name}`: `{count}`"
        for name, count in sorted(root_priority_counts.items())
    )
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `ck3_tiger_current_only_classified.csv`",
            "- `ck3_tiger_missing_title_resolution_candidates.csv`",
            "- `ck3_tiger_current_only_root_causes.csv`",
        ]
    )
    (output_dir / "ck3_tiger_current_only_classification_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    print(f"rows={len(classified)}")
    print(f"missing_title_rows={len(missing_title_rows)}")
    print("priorities=" + ", ".join(f"{key}:{value}" for key, value in sorted(priority_counts.items())))
    print(f"summary={output_dir / 'ck3_tiger_current_only_classification_summary.md'}")


if __name__ == "__main__":
    main()
