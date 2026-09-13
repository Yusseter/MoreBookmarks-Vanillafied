from __future__ import annotations

import argparse
import csv
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


INPUT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "repo_integration_closure_findings.csv"
)
OUTPUT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "review_surface_triage"
)
DEFAULT_ASIL_MOD_REPO = (
    Path(__file__).resolve().parents[3].parent / "Leviathonlx MoreBookmarks-Plus"
)


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Group and triage all repo closure review findings."
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument(
        "--asil-mod-repo", type=Path, default=DEFAULT_ASIL_MOD_REPO
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.stat().st_size == 0:
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


def classify(
    domain: str, classification: str, provenance: str
) -> tuple[str, str, str, str]:
    confirmed_p0 = {
        "history_effect_missing_title_scope_prefix",
        "history_effect_title_reference_candidate",
        "invalid_title_tier_relationship",
        "parse_or_sentinel_order_error",
        "pending_asil_mod_fix",
        "stale_character_alias_candidate",
        "stale_redundant_region_title_reference",
        "undefined_reader_variable_or_numeric_value",
    }
    if domain == "ck3_tiger" and classification in confirmed_p0:
        return (
            "confirmed_live_error_candidate",
            "P0",
            "yes_after_candidate_review",
            "use the Tiger P0 root triage for the exact candidate and provenance",
        )

    quality_classes = {
        ("binary_map", "multipart_map_geometry_review"),
        ("ck3_tiger", "color_formatting_quality"),
        ("ck3_tiger", "localization_hash_collision_review"),
        ("ck3_tiger", "temporal_history_quality_review"),
        ("localization", "internal_color_template_title_review"),
        ("localization", "internal_null_sentinel_title_review"),
        ("localization", "obsolete_unreferenced_title_localization_review"),
        ("province_history", "missing_explicit_history_noncapital"),
        ("runtime", "effective_holder_dead_before_bookmark"),
    }
    if (domain, classification) in quality_classes:
        bucket = (
            "accepted_non_required_history_pattern"
            if classification == "missing_explicit_history_noncapital"
            else "non_blocking_quality_or_runtime_pattern"
        )
        return (
            bucket,
            "P3",
            "no_unless_runtime_or_visual_evidence_fails",
            "retain as non-blocking evidence; sample only if a runtime symptom appears",
        )

    if domain == "binary_map":
        if classification in {
            "missing_pixels_non_geometry_reference_review",
            "semantic_reference_missing_pixels_unmapped_review",
        }:
            return (
                "map_identity_cleanup_candidate",
                "P1",
                "yes",
                "resolve the live non-geometry reference or document the placeholder intent",
            )
        if classification == "tiny_map_geometry_review":
            return (
                "map_geometry_quality_review",
                "P2",
                "sample_review",
                "inspect only the tiny playable components, excluding palette placeholders",
            )
        return (
            "map_identity_mapping_review",
            "P2",
            "yes_for_relation_decision",
            "validate each source relation before any remap",
        )

    if domain == "localization":
        if classification == "missing_effective_mapped_source_available":
            return (
                "mapped_localization_authoring_candidate",
                "P1",
                "yes",
                "copy the verified mapped source value after key/context review",
            )
        if classification == "missing_everywhere":
            priority = "P1" if provenance == "yusseter_current_only" else "P2"
            return (
                "missing_localization_authoring_gap",
                priority,
                "yes",
                "author the missing value or prove the key is internal-only",
            )
        if classification == "conflicting_duplicate_key":
            return (
                "localization_override_conflict_review",
                "P1",
                "yes",
                "resolve effective load order and keep one intentional final value",
            )
        return (
            "localization_dependency_or_stale_reference_review",
            "P2",
            "yes",
            "decide dependency, remap, authoring, or cleanup from the exact consumer",
        )

    if domain == "mpe_add_1":
        return (
            "mpe_adj_localization_authoring_gap",
            "P1",
            "yes",
            "recover or author the missing adjective localization for active MPE titles",
        )

    if domain == "province_history":
        if classification == "duplicate_province_block":
            return (
                "province_history_duplicate_structure_review",
                "P1",
                "yes",
                "compare effective duplicate blocks and consolidate only when semantics match",
            )
        return (
            "province_history_runtime_or_source_decision",
            "P2",
            "yes",
            "review capital holding or authoritative source state at all bookmark dates",
        )

    if domain == "title_history":
        priority = "P1" if classification == "duplicate_title_block_same_layer" else "P2"
        return (
            "title_history_structure_or_source_overwrite_review",
            priority,
            "yes",
            "compare complete dated chains before consolidating or taking source changes",
        )

    if domain == "runtime":
        return (
            "runtime_design_or_bookmark_smoke_test_review",
            "P2",
            "runtime_decision",
            "confirm intended independence, featured holder, succession and government in game",
        )

    if domain == "ck3_tiger" and classification == "localization_mapped_source_candidate":
        return (
            "mapped_localization_cross_audit_overlap",
            "P1",
            "use_localization_closure_candidate",
            "do not count separately; resolve the matching localization mapped-source finding",
        )

    if domain == "ck3_tiger" and classification == "localization_missing_everywhere":
        return (
            "missing_localization_cross_audit_overlap",
            "P2",
            "use_localization_closure_authoring_gap",
            "do not count separately; resolve the matching localization missing-everywhere finding",
        )

    if domain == "ck3_tiger" and classification == "definition_name_localization_review":
        return (
            "definition_name_localization_authoring_review",
            "P2",
            "yes",
            "review the definition name key and add or remap its localization",
        )

    if domain == "ck3_tiger" and classification == "temporal_history_runtime_overlap":
        return (
            "temporal_history_cross_audit_overlap",
            "P2",
            "use_runtime_and_title_history_evidence",
            "do not count separately; inspect the matching runtime/title-history root",
        )

    if domain == "ck3_tiger" and classification == "missing_title_history_review":
        return (
            "missing_title_history_authoring_review",
            "P2",
            "yes",
            "verify the title is active and author history only if gameplay requires it",
        )

    identity_classes = {
        "ambiguous_parent_derived_review",
        "cross_tier_semantic_candidate_review",
        "explicit_no_current_counterpart_reference",
        "mapped_title_reference_candidate",
        "parent_derived_title_candidate",
        "split_title_reference_review",
        "stale_region_title_no_exact_current_counterpart",
        "unresolved_missing_title_reference",
    }
    if domain == "ck3_tiger" and classification in identity_classes:
        return (
            "title_identity_mapping_decision",
            "P1" if classification == "unresolved_missing_title_reference" else "P2",
            "yes",
            "select an exact current counterpart, external dependency, or removal",
        )

    if domain == "ck3_tiger":
        if classification == "missing_asset_reference":
            return (
                "structural_or_asset_error_candidate",
                "P1",
                "yes",
                "inspect the exact file and repair the structural or missing-asset cause",
            )
        if classification in {
            "brace_placement_review",
            "duplicate_definition_review",
            "encoding_quality_review",
        }:
            return (
                "structural_quality_or_duplicate_review",
                "P2",
                "yes",
                "inspect structure and effective duplicate semantics before cleanup",
            )
        return (
            "tiger_semantic_or_temporal_review",
            "P2",
            "yes",
            "use exact Tiger context plus source/runtime evidence before editing",
        )

    if domain in {
        "source_shared_title_reference",
        "source_shared_province_reference",
    }:
        return (
            "source_integration_candidate_review",
            "P2",
            "yes",
            "review the mapped source change against current hierarchy and map identity",
        )

    if domain == "silk_road_market":
        if classification == "decision_destination_differs_from_market_province":
            return (
                "silk_road_market_destination_runtime_review",
                "P2",
                "runtime_decision",
                (
                    "confirm whether the county-capital travel destination is an "
                    "intentional extra-barony design after the market binding is fixed"
                ),
            )
        if classification == "decision_localization_references_wrong_market":
            return (
                "silk_road_market_decision_localization_review",
                "P1",
                "yes",
                (
                    "replace the reused Dvin market label with a subregion-specific "
                    "market localization key after reviewing all three consumers"
                ),
            )
        return (
            "silk_road_market_design_review",
            "P1",
            "yes",
            "use the linked Silk Road market closure root before editing",
        )

    if domain == "map_regions":
        return (
            "map_region_title_identity_review",
            "P1",
            "yes",
            "resolve the undefined region title reference",
        )

    return (
        "unclassified_review_group",
        "P2",
        "manual_review",
        "classify this review family before any source edit",
    )


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    review_rows = [
        row for row in read_csv(repo_root / INPUT_PATH)
        if row.get("severity") == "review"
    ]
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in review_rows:
        grouped[(
            row.get("domain", ""),
            row.get("classification", ""),
            row.get("provenance", ""),
        )].append(row)

    yusseter_revision = git_revision(repo_root)
    current_asil_revision = git_revision(args.asil_mod_repo.resolve())
    rows: list[dict[str, str]] = []
    for index, (key, values) in enumerate(sorted(grouped.items()), start=1):
        domain, classification, provenance = key
        bucket, priority, decision, recommendation = classify(
            domain, classification, provenance
        )
        objects = sorted({row.get("object", "") for row in values if row.get("object")})
        paths = sorted({row.get("path", "") for row in values if row.get("path")})
        candidates = [row for row in values if row.get("candidate_value")]
        source_reports = sorted({
            row.get("source_report", "") for row in values
            if row.get("source_report")
        })
        rows.append({
            "review_group_id": f"RSG{index:03d}",
            "domain": domain,
            "classification": classification,
            "provenance": provenance,
            "finding_count": str(len(values)),
            "unique_object_count": str(len(objects)),
            "unique_path_count": str(len(paths)),
            "candidate_count": str(len(candidates)),
            "sample_objects": " | ".join(objects[:12]),
            "sample_paths": " | ".join(paths[:8]),
            "triage_bucket": bucket,
            "priority": priority,
            "decision_needed": decision,
            "recommendation": recommendation,
            "source_reports": " | ".join(source_reports),
            "yusseter_revision": yusseter_revision,
            "current_asil_revision": current_asil_revision,
        })

    output_csv = output_dir / "repo_review_surface_triage.csv"
    write_csv(output_csv, rows)
    bucket_counts = Counter()
    priority_counts = Counter()
    for row in rows:
        count = int(row["finding_count"])
        bucket_counts[row["triage_bucket"]] += count
        priority_counts[row["priority"]] += count
    fallback_groups = sum(
        row["triage_bucket"] == "unclassified_review_group" for row in rows
    )
    summary = [
        "# Repo Review Surface Triage",
        "",
        f"- raw review findings: `{len(review_rows)}`",
        f"- grouped review families: `{len(rows)}`",
        f"- unclassified groups: `{fallback_groups}`",
        "",
        "## Priority By Raw Finding Count",
        "",
        *[f"- {name}: `{count}`" for name, count in sorted(priority_counts.items())],
        "",
        "## Triage Buckets By Raw Finding Count",
        "",
        *[f"- {name}: `{count}`" for name, count in bucket_counts.most_common()],
        "",
        "## Interpretation",
        "",
        "- Counts are evidence rows, not independent root-cause counts.",
        "- Cross-audit overlap remains visible and must not be double-counted as separate fixes.",
        "- P3 quality/runtime patterns are not blockers without additional runtime or visual evidence.",
        "- This report does not modify BookmarksGit source files.",
    ]
    (output_dir / "repo_review_surface_triage_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print(f"raw_reviews={len(review_rows)}")
    print(f"groups={len(rows)}")
    print(f"fallback_groups={fallback_groups}")
    print(f"priority={dict(sorted(priority_counts.items()))}")
    print(f"output={output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
