from __future__ import annotations

import argparse
import csv
import hashlib
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import audit_bookmark_runtime_static as runtime
import audit_landed_title_source_identity as landed
import classify_p1_structural_localization_roots as p1


OUTPUT_ROOT = Path(
    ".codex/works/analysis/generated/repo_integration_closure/"
    "title_history_source_alignment"
)
IDENTITY_PATH = Path(
    ".codex/works/analysis/generated/landed_title_source_identity/"
    "landed_title_source_identity_audit.csv"
)
RELATION_PATH = Path(
    ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv"
)
TITLE_RE = re.compile(r"^[hekdcb]_[A-Za-z0-9_'\-]+$")
TITLE_TOKEN_RE = re.compile(r"\b([hekdcb]_[A-Za-z0-9_'\-]+)\b")
ADDITIVE_FIELDS = {"change_development_level"}
CONFLICT_SENSITIVE_FIELDS = {
    "government",
    "holder",
    "liege",
    "name",
    "reset_name",
    "set_de_jure_liege",
}


@dataclass(frozen=True)
class SourceChoice:
    title_id: str
    decision: str
    source_kind: str
    source_title_id: str
    status: str
    confidence: str
    evidence: str


@dataclass(frozen=True)
class ValueEvidence:
    value: str
    path: str
    line: int


@dataclass(frozen=True)
class MergeMilestone:
    merge_revision: str
    source_revision: str
    subject: str


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit East-Asia title history against the authoritative vanilla "
            "or asil-mod source selected by landed-title source identity."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument(
        "--asil-mod-repo", type=Path, default=p1.DEFAULT_ASIL_MOD_REPO
    )
    parser.add_argument(
        "--vanilla-game-root", type=Path, default=p1.DEFAULT_VANILLA_ROOT
    )
    parser.add_argument("--baseline-revision", default=p1.DEFAULT_BASELINE)
    parser.add_argument(
        "--merged-source-revision",
        default="",
        help=(
            "Asil-mod revision already merged into the current branch. "
            "Defaults to the second parent of the latest first-parent merge."
        ),
    )
    parser.add_argument(
        "--source-base-revision",
        default="",
        help=(
            "Common source revision before the audited merge range. "
            "Defaults to merge-base(baseline, merged source)."
        ),
    )
    parser.add_argument("--identity-csv", type=Path, default=None)
    parser.add_argument("--relation-csv", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {
                (key or "").strip(): (value or "").strip()
                for key, value in row.items()
            }
            for row in csv.DictReader(handle, skipinitialspace=True)
        ]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def git_text(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def latest_merge_second_parent(repo: Path) -> str:
    lines = git_text(repo, "rev-list", "--first-parent", "--merges", "--parents", "HEAD")
    for line in lines.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            return parts[2]
    raise RuntimeError(
        "Cannot infer merged source revision; pass --merged-source-revision"
    )


def source_delta_provenance(
    source_base: tuple[str, ...],
    merged_source: tuple[str, ...],
    latest_source: tuple[str, ...],
) -> str:
    if latest_source != merged_source:
        return "latest_asil_differs_from_merged_source"
    if merged_source == source_base:
        return "unchanged_since_source_base"
    if not source_base and merged_source:
        return "added_in_merged_source_range"
    if source_base and not merged_source:
        return "deleted_in_merged_source_range"
    return "changed_in_merged_source_range"


def git_is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def discover_source_milestones(
    repo: Path, baseline_revision: str, merged_source_revision: str
) -> list[MergeMilestone]:
    raw = git_text(
        repo,
        "log",
        "--first-parent",
        "--reverse",
        "--format=%H%x1f%P%x1f%s",
        f"{baseline_revision}..HEAD",
    )
    milestones: list[MergeMilestone] = []
    for line in raw.splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) != 3:
            continue
        merge_revision, parent_text, subject = parts
        parents = parent_text.split()
        if len(parents) < 2:
            continue
        source_revision = parents[1]
        if not git_is_ancestor(repo, source_revision, merged_source_revision):
            continue
        milestones.append(
            MergeMilestone(merge_revision, source_revision, subject)
        )
        if source_revision == merged_source_revision:
            break
    if not milestones or milestones[-1].source_revision != merged_source_revision:
        raise RuntimeError(
            "Merged source revision is not represented by a first-parent merge"
        )
    return milestones


def same_tier(left: str, right: str) -> bool:
    return bool(left and right and left[:2] == right[:2])


def relation_sources(
    relation_csv: Path,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    forward = p1.forward_title_relations(relation_csv)
    reverse: dict[str, set[str]] = defaultdict(set)
    for current_title, source_titles in forward.items():
        for source_title in source_titles:
            if TITLE_RE.fullmatch(source_title) and same_tier(
                current_title, source_title
            ):
                reverse[source_title].add(current_title)
    unique_reverse = {
        source_title: next(iter(current_titles))
        for source_title, current_titles in reverse.items()
        if len(current_titles) == 1
    }
    return forward, unique_reverse


def choose_sources(
    identity_rows: list[dict[str, str]],
    forward_relations: dict[str, list[str]],
    asil_history_ids: set[str],
    vanilla_history_ids: set[str],
    explicit_vanilla_roots: set[str],
) -> dict[str, SourceChoice]:
    choices: dict[str, SourceChoice] = {}
    for row in identity_rows:
        title_id = row["title_id"]
        decision = row.get("source_decision", "")
        confidence = row.get("confidence", "")
        vanilla_title = row.get("vanilla_title", "")
        if not TITLE_RE.fullmatch(vanilla_title or ""):
            vanilla_title = title_id
        if title_id in explicit_vanilla_roots and vanilla_title in vanilla_history_ids:
            choices[title_id] = SourceChoice(
                title_id,
                decision,
                "vanilla",
                vanilla_title,
                "resolved",
                confidence,
                "explicit_core_vanilla_history_root;"
                + row.get("decision_reason", ""),
            )
            continue
        preferred_asil = row.get("mod_best_title", "")
        if not (
            TITLE_RE.fullmatch(preferred_asil or "")
            and same_tier(title_id, preferred_asil)
            and preferred_asil in asil_history_ids
        ):
            preferred_asil = ""
        relation_candidates = sorted(
            {
                token
                for token in forward_relations.get(title_id, [])
                if TITLE_RE.fullmatch(token)
                and same_tier(title_id, token)
                and token in asil_history_ids
            }
        )
        if preferred_asil:
            source_title = preferred_asil
            evidence = "identity_mod_best_title_with_asil_history"
        elif len(relation_candidates) == 1:
            source_title = relation_candidates[0]
            evidence = f"unique_same_tier_asil_history:{source_title}"
        elif title_id in asil_history_ids:
            source_title = title_id
            evidence = "implicit_same_id_asil_history"
        else:
            source_title = ""
            evidence = "ambiguous_or_missing_same_tier_asil_history:" + ";".join(
                relation_candidates
            )
        if source_title:
            choices[title_id] = SourceChoice(
                title_id,
                decision,
                "asil_mod",
                source_title,
                "resolved",
                confidence,
                evidence + ";" + row.get("decision_reason", ""),
            )
            continue
        if vanilla_title in vanilla_history_ids:
            choices[title_id] = SourceChoice(
                title_id,
                decision,
                "vanilla",
                vanilla_title,
                "resolved",
                confidence,
                "vanilla_history_fallback;" + row.get("decision_reason", ""),
            )
            continue
        choices[title_id] = SourceChoice(
            title_id,
            decision or "manual_review",
            "",
            "",
            "unresolved_history_source",
            confidence,
            evidence + ";" + row.get("decision_reason", ""),
        )
    return choices


def normalized_value(value: str, title_mapping: dict[str, str]) -> str:
    remapped = TITLE_TOKEN_RE.sub(
        lambda match: title_mapping.get(match.group(1), match.group(1)),
        value,
    )
    return re.sub(r"\s+", " ", remapped).strip()


def value_index(
    blocks: list[runtime.Block], title_mapping: dict[str, str]
) -> dict[tuple[str, str], list[ValueEvidence]]:
    result: dict[tuple[str, str], list[ValueEvidence]] = defaultdict(list)
    for block in blocks:
        for entry in runtime.direct_entries(block):
            fields = p1.entry_field_map(entry.lines)
            additive_values: dict[str, list[str]] = defaultdict(list)
            for raw_line in entry.lines:
                code = raw_line.split("#", 1)[0]
                for field in ADDITIVE_FIELDS:
                    additive_values[field].extend(
                        re.findall(
                            rf"\b{re.escape(field)}\s*=\s*([^\s{{}}#]+)",
                            code,
                        )
                    )
            line = block.start_line + entry.relative_start
            path = block.path.split(":", 1)[-1]
            if not fields:
                canonical = normalized_value(
                    p1.canonical_lines(entry.lines), title_mapping
                )
                if canonical:
                    result[(entry.key, "__entry__")].append(
                        ValueEvidence(canonical, path, line)
                    )
                continue
            for field, field_values in sorted(fields.items()):
                ordered_values = (
                    additive_values[field]
                    if field in ADDITIVE_FIELDS and additive_values[field]
                    else sorted(field_values)
                )
                for value in ordered_values:
                    result[(entry.key, field)].append(
                        ValueEvidence(
                            normalized_value(value, title_mapping), path, line
                        )
                    )
    return dict(result)


def values(
    index: dict[tuple[str, str], list[ValueEvidence]],
    key: tuple[str, str],
) -> tuple[str, ...]:
    raw_values = [item.value for item in index.get(key, [])]
    if key[1] in ADDITIVE_FIELDS:
        return tuple(sorted(raw_values))
    return tuple(sorted(set(raw_values)))


def merged_additive_values(
    primary: tuple[str, ...], secondary: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(sorted(primary + secondary))


def related_source_role(
    primary_title: str,
    related_title: str,
    source_blocks: dict[str, landed.TitleBlock],
) -> str:
    primary = source_blocks.get(primary_title)
    related = source_blocks.get(related_title)
    if not primary or not related:
        return "missing_landed_hierarchy"
    primary_path = primary.path.split(" > ")
    related_path = related.path.split(" > ")
    if related_title in primary_path[:-1]:
        return "ancestor"
    if primary_title in related_path[:-1]:
        return "descendant"
    if primary.root_title == related.root_title:
        return "same_tree_other"
    return "separate_tree"


def locations(
    index: dict[tuple[str, str], list[ValueEvidence]], key: tuple[str, str]
) -> str:
    return " | ".join(
        f"{item.path}:{item.line}={item.value}"
        for item in sorted(
            index.get(key, []), key=lambda item: (item.path, item.line, item.value)
        )
    )


def timeline_metadata(
    snapshots: list[
        tuple[str, dict[tuple[str, str], list[ValueEvidence]]]
    ],
    key: tuple[str, str],
    target: tuple[str, ...],
) -> dict[str, str]:
    first_nonempty = ""
    target_transition = ""
    target_matches: list[str] = []
    changes: list[str] = []
    previous: tuple[str, ...] | None = None
    for revision, index in snapshots:
        snapshot_values = values(index, key)
        if snapshot_values and not first_nonempty:
            first_nonempty = revision
        if previous is None or snapshot_values != previous:
            changes.append(
                f"{revision[:12]}={joined(snapshot_values) or '<absent>'}"
            )
            if target and snapshot_values == target:
                target_transition = revision
        if target and snapshot_values == target:
            target_matches.append(revision)
        previous = snapshot_values
    return {
        "first_nonempty_revision": first_nonempty,
        "target_transition_revision": target_transition,
        "target_match_revisions": ";".join(target_matches),
        "timeline": " | ".join(changes),
    }


def game_path(labelled_path: str) -> str:
    relative = labelled_path.split(":", 1)[-1].replace("\\", "/")
    if relative.lower().startswith("bookmarksgit/"):
        relative = relative[len("BookmarksGit/") :]
    return relative.lower()


def effective_vanilla_texts(
    current_texts: dict[str, str], vanilla_texts: dict[str, str]
) -> dict[str, str]:
    overridden = {game_path(path) for path in current_texts}
    return {
        path: text
        for path, text in vanilla_texts.items()
        if game_path(path) not in overridden
    }


def classify_relation(
    choice: SourceChoice,
    field: str,
    current: tuple[str, ...],
    source: tuple[str, ...],
    baseline: tuple[str, ...],
    effective_source: tuple[str, ...],
    secondary_asil: tuple[str, ...],
    ancestor_asil: tuple[str, ...],
    other_related_asil: tuple[str, ...],
    effective_current_vanilla: tuple[str, ...],
) -> tuple[str, str, str, str, str]:
    baseline_match = current == baseline
    if field in ADDITIVE_FIELDS:
        if choice.source_kind == "asil_mod" and ancestor_asil:
            projected_values = merged_additive_values(source, ancestor_asil)
            if current == projected_values:
                return (
                    "additive_asil_projection_matches_ancestor_sources",
                    "preexisting_yusseter_additive_projection",
                    "review",
                    "P2",
                    "retain_after_source_ancestor_projection_review",
                )
            return (
                "additive_asil_ancestor_projection_divergence_review",
                (
                    "preexisting_yusseter_additive_projection"
                    if baseline_match
                    else "post_baseline_additive_projection_candidate"
                ),
                "review",
                "P2" if baseline_match else "P1",
                "review_primary_related_and_local_development_contributions",
            )
        if choice.source_kind == "asil_mod" and other_related_asil:
            return (
                "additive_nonancestor_relation_overlay_review",
                (
                    "preexisting_yusseter_additive_overlay"
                    if baseline_match
                    else "post_baseline_additive_overlay_candidate"
                ),
                "review",
                "P2" if baseline_match else "P1",
                "review_descendant_sibling_or_alternative_title_contributions",
            )
        if len(current) > 1 and current != source:
            return (
                "additive_development_overlay_review",
                (
                    "preexisting_yusseter_additive_overlay"
                    if baseline_match
                    else "post_baseline_additive_overlay_candidate"
                ),
                "review",
                "P2" if baseline_match else "P1",
                "review_additive_contributions_without_collapsing_duplicate_values",
            )
    if field in CONFLICT_SENSITIVE_FIELDS and len(current) > 1:
        if source and current == source:
            source_owner = (
                "shared_asil_mod_baseline"
                if choice.source_kind == "asil_mod"
                else "vanilla_source_baseline"
            )
            return (
                "authoritative_source_multi_value_review",
                source_owner,
                "deferred" if choice.source_kind == "asil_mod" else "review",
                "P1",
                (
                    "defer_to_final_shared_asil_mod_pass"
                    if choice.source_kind == "asil_mod"
                    else "review_vanilla_multi_value_history_semantics"
                ),
            )
        if secondary_asil and current == secondary_asil:
            return (
                "shared_secondary_asil_multi_value_deferred",
                "shared_asil_mod_baseline",
                "deferred",
                "P1",
                "defer_to_final_shared_asil_mod_pass",
            )
        if secondary_asil and secondary_asil < current:
            return (
                "current_multi_value_with_partial_asil_overlap",
                (
                    "preexisting_yusseter_history_conflict"
                    if baseline_match
                    else "post_baseline_current_history_conflict"
                ),
                "review",
                "P1",
                "consolidate_conflicting_current_entries_preserving_one_timeline",
            )
        return (
            "current_internal_multi_value_history_conflict",
            (
                "preexisting_yusseter_history_conflict"
                if baseline_match
                else "post_baseline_current_history_conflict"
            ),
            "review",
            "P1",
            "consolidate_conflicting_current_entries_preserving_one_timeline",
        )
    if choice.source_kind == "vanilla":
        if current and source:
            if current == source:
                if len(source) > 1:
                    return (
                        "shared_vanilla_source_multi_value_review",
                        "vanilla_source_baseline",
                        "review",
                        "P2",
                        "review_multi_value_source_semantics_without_auto_apply",
                    )
                if not effective_source:
                    return (
                        "aligned_replacement_of_shadowed_vanilla",
                        "yusseter_file_override_dependency",
                        "review",
                        "P2",
                        "retain_or_document_complete_shadowed_vanilla_replacement",
                    )
                return (
                    "aligned_redundant_vanilla_overlay",
                    "vanilla_runtime_source",
                    "info",
                    "P3",
                    "review_redundancy_only_if_file_is_touched",
                )
            if len(current) > 1:
                classification = "current_multi_value_conflict_against_vanilla"
            elif secondary_asil and current == secondary_asil:
                return (
                    "asil_history_overlay_on_vanilla_source",
                    "yusseter_history_source_design",
                    "review",
                    "P2",
                    "verify_asil_timeline_is_intentional_for_shadowed_vanilla_root",
                )
            else:
                classification = "authoritative_vanilla_source_divergence"
            if baseline_match:
                ownership = "preexisting_yusseter_design"
                priority = "P2"
            else:
                ownership = "yusseter_integration_candidate"
                priority = "P1"
            return (
                classification,
                ownership,
                "review",
                priority,
                "reconcile_against_vanilla_source_and_preserve_intentional_bookmarks",
            )
        if current:
            if secondary_asil and current == secondary_asil:
                if baseline_match:
                    classification = (
                        "preexisting_asil_history_extension_on_vanilla_title"
                    )
                    ownership = "preexisting_yusseter_design"
                    severity = "info"
                    priority = "P3"
                else:
                    classification = (
                        "post_baseline_asil_history_extension_on_vanilla_title"
                    )
                    ownership = "yusseter_integration_candidate"
                    severity = "review"
                    priority = "P2"
            else:
                if baseline_match:
                    classification = "preexisting_current_only_history_extension"
                    ownership = "preexisting_yusseter_design"
                    severity = "info"
                    priority = "P3"
                else:
                    classification = "post_baseline_current_only_history_extension"
                    ownership = "post_baseline_current_extension"
                    severity = "review"
                    priority = "P2"
            return (
                classification,
                ownership,
                severity,
                priority,
                "verify_extension_is_intentional_for_all_bookmark_dates",
            )
        if source:
            if source == effective_source:
                return (
                    "runtime_vanilla_source_only",
                    "vanilla_runtime_source",
                    "info",
                    "P3",
                    "none",
                )
            return (
                "shadowed_vanilla_source_not_carried_verbatim",
                "source_policy_coverage_review",
                "review",
                "P2",
                "review_file_level_source_coverage_and_alternate_timeline",
            )
    if choice.source_kind == "asil_mod":
        if current and source:
            if current == source:
                if len(source) > 1:
                    return (
                        "shared_asil_source_multi_value_deferred",
                        "shared_asil_mod_baseline",
                        "deferred",
                        "P2",
                        "defer_to_final_shared_asil_mod_pass",
                    )
                if (
                    effective_current_vanilla
                    and effective_current_vanilla != current
                ):
                    return (
                        "aligned_asil_with_effective_vanilla_conflict",
                        "yusseter_runtime_layering_candidate",
                        "review",
                        "P1",
                        "verify_file_override_or_explicitly_neutralize_vanilla_history",
                    )
                return (
                    "aligned_authoritative_asil",
                    "asil_mod_authoritative_source",
                    "info",
                    "P3",
                    "none",
                )
            classification = (
                "current_multi_value_conflict_against_asil"
                if len(current) > 1
                else "authoritative_asil_source_divergence"
            )
            ownership = (
                "preexisting_yusseter_design"
                if baseline_match
                else "post_baseline_current_divergence"
            )
            return (
                classification,
                ownership,
                "review",
                "P1",
                "reconcile_against_asil_source_without_discarding_local_history",
            )
        if current:
            if baseline_match:
                return (
                    "preexisting_current_only_history_extension",
                    "preexisting_yusseter_design",
                    "info",
                    "P3",
                    "verify_extension_only_if_title_is_touched",
                )
            return (
                "post_baseline_current_only_history_extension",
                "post_baseline_current_extension",
                "review",
                "P2",
                "verify_extension_is_intentional_for_all_bookmark_dates",
            )
        if source:
            return (
                "missing_authoritative_asil_entry_candidate",
                "yusseter_integration_gap_candidate",
                "review",
                "P1",
                "review_and_import_missing_source_entry_with_title_remap",
            )
        if effective_current_vanilla:
            return (
                "effective_vanilla_history_without_asil_source_entry",
                "yusseter_runtime_layering_candidate",
                "review",
                "P2",
                "verify_vanilla_history_is_valid_for_mod_retained_title",
            )
    return (
        "no_comparable_values",
        "not_applicable",
        "info",
        "P3",
        "none",
    )


def refine_asil_provenance(
    choice: SourceChoice,
    current: tuple[str, ...],
    merged_source: tuple[str, ...],
    baseline: tuple[str, ...],
    source_base: tuple[str, ...],
    latest_source: tuple[str, ...],
    result: tuple[str, str, str, str, str],
) -> tuple[str, str, str, str, str]:
    if choice.source_kind != "asil_mod":
        return result

    classification, ownership, severity, priority, recommendation = result
    current_matches_baseline = current == baseline
    source_changed_in_merge = merged_source != source_base

    if classification == "missing_authoritative_asil_entry_candidate":
        if not source_changed_in_merge:
            return (
                "preexisting_yusseter_source_omission_review",
                "preexisting_yusseter_design",
                "review",
                "P2",
                "review_preexisting_source_omission_only_when_title_is_touched",
            )
        if not source_base:
            return (
                "missing_merged_asil_addition_candidate",
                "upstream_merge_integration_gap_candidate",
                "review",
                "P1",
                "review_and_import_missing_merged_source_entry_with_title_remap",
            )
        return (
            "missing_merged_asil_changed_entry_candidate",
            "upstream_merge_integration_gap_candidate",
            "review",
            "P1",
            "review_changed_merged_source_entry_and_preserve_local_timeline",
        )

    if classification in {
        "authoritative_asil_source_divergence",
        "current_multi_value_conflict_against_asil",
    }:
        if current_matches_baseline and not source_changed_in_merge:
            return (
                "preexisting_yusseter_source_divergence_review",
                "preexisting_yusseter_design",
                "review",
                "P2",
                "review_preexisting_divergence_only_when_title_is_touched",
            )
        if current_matches_baseline and current == source_base:
            return (
                "missed_merged_asil_update_candidate",
                "upstream_merge_integration_gap_candidate",
                "review",
                "P1",
                "apply_merged_source_delta_after_title_remap_review",
            )
        if current_matches_baseline and source_changed_in_merge:
            return (
                "merged_asil_three_way_divergence_review",
                "upstream_merge_semantic_review",
                "review",
                "P1",
                "resolve_three_way_history_difference_without_discarding_local_design",
            )
        return (
            classification,
            "post_baseline_current_divergence",
            severity,
            priority,
            recommendation,
        )

    if classification in {
        "preexisting_current_only_history_extension",
        "post_baseline_current_only_history_extension",
    } and source_base and not merged_source:
        return (
            "retained_entry_after_merged_asil_deletion_review",
            (
                "preexisting_yusseter_design"
                if current_matches_baseline
                else "post_baseline_current_extension"
            ),
            "review",
            "P2",
            "verify_intentional_retention_after_asil_source_deletion",
        )

    if latest_source != merged_source:
        if current == merged_source:
            return (
                "aligned_merged_source_pending_latest_asil_change",
                "pending_asil_mod_update",
                "deferred",
                "P2",
                "inventory_latest_asil_change_before_next_merge",
            )
        if not current and not merged_source and latest_source:
            return (
                "pending_latest_asil_entry_not_merged",
                "pending_asil_mod_update",
                "deferred",
                "P2",
                "inventory_latest_asil_change_before_next_merge",
            )

    return result


def refine_current_milestone_provenance(
    current: tuple[str, ...],
    merged_source: tuple[str, ...],
    current_target_matches: str,
    result: tuple[str, str, str, str, str],
) -> tuple[str, str, str, str, str]:
    if (
        merged_source
        and current != merged_source
        and current_target_matches
        and result[1]
        in {
            "upstream_merge_integration_gap_candidate",
            "post_baseline_current_divergence",
        }
    ):
        return (
            "post_merge_title_history_regression_candidate",
            "post_merge_current_regression_candidate",
            "review",
            "P1",
            "restore_last_verified_merged_source_value_after_local_context_review",
        )
    return result


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def joined(items: tuple[str, ...] | set[str]) -> str:
    return ";".join(sorted(items))


def append_unresolved_finding(
    findings: list[dict[str, str]],
    choice: SourceChoice,
    current_blocks: list[runtime.Block],
    metadata: dict[str, str],
) -> None:
    if choice.status == "resolved" or not current_blocks:
        return
    findings.append(
        {
            "title_id": choice.title_id,
            "source_decision": choice.decision,
            "source_kind": choice.source_kind,
            "source_title_id": choice.source_title_id,
            "source_choice_status": choice.status,
            "source_confidence": choice.confidence,
            "source_choice_evidence": choice.evidence,
            "event_key": "",
            "field": "",
            "classification": "source_choice_unresolved_with_current_history",
            "ownership": "source_identity_review",
            "severity": "review",
            "priority": "P1",
            "recommendation": "resolve_landed_source_identity_before_history_edit",
            "current_values": "",
            "source_values": "",
            "baseline_values": "",
            "source_base_values": "",
            "latest_asil_values": "",
            "source_delta_provenance": "source_choice_unresolved",
            "effective_vanilla_values": "",
            "secondary_asil_values": "",
            "current_locations": " | ".join(
                f"{block.path.split(':', 1)[-1]}:{block.start_line}"
                for block in current_blocks
            ),
            "source_locations": "",
            "baseline_locations": "",
            "source_base_locations": "",
            "latest_asil_locations": "",
            "effective_vanilla_locations": "",
            "secondary_asil_locations": "",
            "current_matches_baseline": "",
            "current_matches_authoritative_source": "",
            "merged_source_matches_source_base": "",
            "latest_asil_matches_merged_source": "",
            "current_matches_secondary_asil": "",
            "auto_apply": "no",
            **metadata,
        }
    )


def texts_sha256(texts: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for path, text in sorted(texts.items()):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def block_locations(blocks: list[runtime.Block]) -> str:
    return " | ".join(
        f"{block.path.split(':', 1)[-1]}:{block.start_line}"
        for block in blocks
    )


def grouped_values(rows: list[dict[str, str]], field: str) -> str:
    return " | ".join(
        sorted({row.get(field, "") for row in rows if row.get(field, "")})
    )


def grouped_signatures(rows: list[dict[str, str]], field: str) -> str:
    signatures = {
        f"{row.get('event_key', '')}/{row.get('field', '')}={row.get(field, '')}"
        for row in rows
        if row.get(field, "")
    }
    return " | ".join(sorted(signatures))


def build_root_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (
            row.get("title_id", ""),
            row.get("source_kind", ""),
            row.get("source_title_id", ""),
            row.get("classification", ""),
            row.get("ownership", ""),
            row.get("severity", ""),
            row.get("priority", ""),
            row.get("recommendation", ""),
        )
        grouped[key].append(row)

    result: list[dict[str, str]] = []
    for key, group_rows in sorted(grouped.items()):
        first = group_rows[0]
        result.append(
            {
                "title_id": key[0],
                "source_kind": key[1],
                "source_title_id": key[2],
                "classification": key[3],
                "ownership": key[4],
                "severity": key[5],
                "priority": key[6],
                "recommendation": key[7],
                "raw_row_count": str(len(group_rows)),
                "event_keys": grouped_values(group_rows, "event_key"),
                "fields": grouped_values(group_rows, "field"),
                "source_delta_provenance": grouped_values(
                    group_rows, "source_delta_provenance"
                ),
                "source_first_nonempty_revisions": grouped_values(
                    group_rows, "source_first_nonempty_revision"
                ),
                "source_final_value_transition_revisions": grouped_values(
                    group_rows, "source_final_value_transition_revision"
                ),
                "current_authoritative_match_revisions": grouped_values(
                    group_rows, "current_authoritative_match_revisions"
                ),
                "source_value_timelines": grouped_values(
                    group_rows, "source_value_timeline"
                ),
                "current_value_timelines": grouped_values(
                    group_rows, "current_value_timeline"
                ),
                "current_signatures": grouped_signatures(
                    group_rows, "current_values"
                ),
                "merged_source_signatures": grouped_signatures(
                    group_rows, "source_values"
                ),
                "source_base_signatures": grouped_signatures(
                    group_rows, "source_base_values"
                ),
                "latest_asil_signatures": grouped_signatures(
                    group_rows, "latest_asil_values"
                ),
                "current_locations": grouped_values(
                    group_rows, "current_locations"
                ),
                "merged_source_locations": grouped_values(
                    group_rows, "source_locations"
                ),
                "source_base_locations": grouped_values(
                    group_rows, "source_base_locations"
                ),
                "latest_asil_locations": grouped_values(
                    group_rows, "latest_asil_locations"
                ),
                "auto_apply": "no",
                "current_revision": first.get("current_revision", ""),
                "baseline_revision": first.get("baseline_revision", ""),
                "source_base_revision": first.get("source_base_revision", ""),
                "merged_source_revision": first.get("merged_source_revision", ""),
                "asil_mod_revision": first.get("asil_mod_revision", ""),
                "identity_sha256": first.get("identity_sha256", ""),
                "relation_sha256": first.get("relation_sha256", ""),
            }
        )
    return result


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    asil_repo = args.asil_mod_repo.resolve()
    vanilla_root = args.vanilla_game_root.resolve()
    identity_csv = (
        args.identity_csv.resolve()
        if args.identity_csv
        else repo_root / IDENTITY_PATH
    )
    relation_csv = (
        args.relation_csv.resolve()
        if args.relation_csv
        else repo_root / RELATION_PATH
    )
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else repo_root / OUTPUT_ROOT
    )
    merged_source_revision = (
        args.merged_source_revision
        or latest_merge_second_parent(repo_root)
    )
    source_base_revision = (
        args.source_base_revision
        or git_text(
            repo_root,
            "merge-base",
            args.baseline_revision,
            merged_source_revision,
        )
    )
    milestones = discover_source_milestones(
        repo_root, args.baseline_revision, merged_source_revision
    )

    identity_rows = read_csv(identity_csv)
    identity_by_title = {row["title_id"]: row for row in identity_rows}
    forward_relations, reverse_relations = relation_sources(relation_csv)
    core_import_path = (
        repo_root
        / ".codex/works/analysis/generated/core_province_integration/"
        "history_titles_merge_report.csv"
    )
    core_import_roots: dict[str, set[str]] = defaultdict(set)
    explicit_vanilla_roots: set[str] = set()
    if core_import_path.is_file():
        for row in read_csv(core_import_path):
            root = row.get("root", "")
            core_import_roots[row.get("source_file", "")].add(root)
            if root:
                explicit_vanilla_roots.add(root)
    current_texts = runtime.read_layer_texts(
        repo_root, "BookmarksGit/history/titles", "current"
    )
    baseline_texts = runtime.read_git_texts(
        repo_root, args.baseline_revision, "history/titles", "baseline"
    )
    vanilla_texts = runtime.read_layer_texts(
        vanilla_root, "history/titles", "vanilla"
    )
    merged_asil_texts = runtime.read_git_texts(
        repo_root,
        merged_source_revision,
        "history/titles",
        "merged_asil",
    )
    source_base_asil_texts = runtime.read_git_texts(
        repo_root,
        source_base_revision,
        "history/titles",
        "source_base_asil",
    )
    latest_asil_texts = runtime.read_layer_texts(
        asil_repo, "BookmarksGit/history/titles", "latest_asil"
    )
    asil_landed_texts = runtime.read_layer_texts(
        asil_repo,
        "BookmarksGit/common/landed_titles",
        "latest_asil_landed",
    )
    asil_landed_blocks = landed.parse_landed_titles_path(
        asil_repo / "BookmarksGit/common/landed_titles"
    )
    effective_vanilla = effective_vanilla_texts(current_texts, vanilla_texts)
    vanilla_blocks = runtime.parse_blocks(
        vanilla_texts, runtime.TITLE_HEADER_RE
    )
    merged_asil_blocks = runtime.parse_blocks(
        merged_asil_texts, runtime.TITLE_HEADER_RE
    )
    source_base_asil_blocks = runtime.parse_blocks(
        source_base_asil_texts, runtime.TITLE_HEADER_RE
    )
    latest_asil_blocks = runtime.parse_blocks(
        latest_asil_texts, runtime.TITLE_HEADER_RE
    )
    choices = choose_sources(
        identity_rows,
        forward_relations,
        set(merged_asil_blocks),
        set(vanilla_blocks),
        explicit_vanilla_roots,
    )
    current_ids = set(choices)
    source_history_ids = {
        choice.source_title_id
        for choice in choices.values()
        if choice.source_kind == "asil_mod" and choice.source_title_id
    }
    source_milestone_blocks: list[
        tuple[MergeMilestone, dict[str, list[runtime.Block]]]
    ] = []
    current_milestone_blocks: list[
        tuple[MergeMilestone, dict[str, list[runtime.Block]]]
    ] = []
    milestone_manifest_rows: list[dict[str, str]] = []
    for milestone in milestones:
        if milestone.source_revision == merged_source_revision:
            milestone_source_texts = merged_asil_texts
            milestone_source_blocks = {
                title_id: blocks
                for title_id, blocks in merged_asil_blocks.items()
                if title_id in source_history_ids
            }
        else:
            milestone_source_texts = runtime.read_git_texts(
                repo_root,
                milestone.source_revision,
                "history/titles",
                f"source_{milestone.source_revision[:12]}",
            )
            milestone_source_blocks = runtime.parse_blocks(
                milestone_source_texts,
                runtime.TITLE_HEADER_RE,
                source_history_ids,
            )
        milestone_current_texts = runtime.read_git_texts(
            repo_root,
            milestone.merge_revision,
            "history/titles",
            f"current_{milestone.merge_revision[:12]}",
        )
        milestone_current_blocks = runtime.parse_blocks(
            milestone_current_texts,
            runtime.TITLE_HEADER_RE,
            current_ids,
        )
        source_milestone_blocks.append(
            (milestone, milestone_source_blocks)
        )
        current_milestone_blocks.append(
            (milestone, milestone_current_blocks)
        )
        milestone_manifest_rows.extend(
            [
                {
                    "input": "source_milestone_title_history",
                    "path": milestone.source_revision,
                    "sha256": texts_sha256(milestone_source_texts),
                },
                {
                    "input": "current_merge_milestone_title_history",
                    "path": milestone.merge_revision,
                    "sha256": texts_sha256(milestone_current_texts),
                },
            ]
        )
    related_asil_candidates = {
        title_id: sorted(
            {
                source_title
                for source_title in forward_relations.get(title_id, [])
                if TITLE_RE.fullmatch(source_title)
                and source_title in merged_asil_blocks
            }
        )
        for title_id in current_ids
    }
    current_blocks = runtime.parse_blocks(
        current_texts, runtime.TITLE_HEADER_RE, current_ids
    )
    baseline_blocks = runtime.parse_blocks(
        baseline_texts, runtime.TITLE_HEADER_RE, current_ids
    )
    effective_vanilla_blocks = runtime.parse_blocks(
        effective_vanilla, runtime.TITLE_HEADER_RE
    )

    metadata = {
        "current_revision": git_revision(repo_root),
        "asil_mod_revision": git_revision(asil_repo),
        "baseline_revision": args.baseline_revision,
        "source_base_revision": source_base_revision,
        "merged_source_revision": merged_source_revision,
        "identity_sha256": file_sha256(identity_csv),
        "relation_sha256": file_sha256(relation_csv),
        "asil_landed_sha256": texts_sha256(asil_landed_texts),
    }
    current_text_by_game_path = {
        game_path(path): text for path, text in current_texts.items()
    }
    vanilla_text_by_game_path = {
        game_path(path): text for path, text in vanilla_texts.items()
    }
    entry_rows: list[dict[str, str]] = []
    findings: list[dict[str, str]] = []
    title_rows: list[dict[str, str]] = []
    vanilla_file_stats: dict[str, dict[str, object]] = {}

    for title_id in sorted(current_ids):
        choice = choices[title_id]
        current_title_blocks = current_blocks.get(title_id, [])
        baseline_title_blocks = baseline_blocks.get(title_id, [])
        append_unresolved_finding(
            findings, choice, current_title_blocks, metadata
        )
        if choice.status != "resolved":
            title_rows.append(
                {
                    "title_id": title_id,
                    "source_decision": choice.decision,
                    "source_kind": choice.source_kind,
                    "source_title_id": choice.source_title_id,
                    "source_choice_status": choice.status,
                    "source_confidence": choice.confidence,
                    "source_choice_evidence": choice.evidence,
                    "current_block_count": str(len(current_title_blocks)),
                    "source_block_count": "0",
                    "baseline_block_count": str(len(baseline_title_blocks)),
                    "effective_vanilla_block_count": str(
                        len(effective_vanilla_blocks.get(title_id, []))
                    ),
                    "secondary_asil_block_count": "0",
                    "comparison_key_count": "0",
                    "finding_count": (
                        "1" if current_title_blocks else "0"
                    ),
                    "classification_counts": "",
                    "current_locations": block_locations(current_title_blocks),
                    "source_locations": "",
                    **metadata,
                }
            )
            continue

        source_token_map: dict[str, str] = {}
        source_title_blocks: list[runtime.Block]
        effective_source_blocks: list[runtime.Block]
        source_base_title_blocks: list[runtime.Block] = []
        latest_asil_title_blocks: list[runtime.Block] = []
        if choice.source_kind == "vanilla":
            source_title_blocks = vanilla_blocks.get(
                choice.source_title_id, []
            )
            effective_source_blocks = effective_vanilla_blocks.get(
                choice.source_title_id, []
            )
        else:
            source_token_map = dict(reverse_relations)
            source_token_map[choice.source_title_id] = title_id
            source_title_blocks = merged_asil_blocks.get(
                choice.source_title_id, []
            )
            source_base_title_blocks = source_base_asil_blocks.get(
                choice.source_title_id, []
            )
            latest_asil_title_blocks = latest_asil_blocks.get(
                choice.source_title_id, []
            )
            effective_source_blocks = []

        secondary_sources = [
            source_title
            for source_title in related_asil_candidates.get(title_id, [])
            if not (
                choice.source_kind == "asil_mod"
                and source_title == choice.source_title_id
            )
        ]
        related_roles = {
            source_title: (
                related_source_role(
                    choice.source_title_id,
                    source_title,
                    asil_landed_blocks,
                )
                if choice.source_kind == "asil_mod"
                else "asil_overlay_on_vanilla_source"
            )
            for source_title in secondary_sources
        }
        ancestor_sources = [
            source_title
            for source_title in secondary_sources
            if related_roles[source_title] == "ancestor"
        ]
        other_related_sources = [
            source_title
            for source_title in secondary_sources
            if related_roles[source_title] != "ancestor"
        ]
        secondary_token_map = dict(reverse_relations)
        for source_title in secondary_sources:
            secondary_token_map[source_title] = title_id
        secondary_asil_blocks = [
            block
            for source_title in secondary_sources
            for block in merged_asil_blocks.get(source_title, [])
        ]
        ancestor_asil_blocks = [
            block
            for source_title in ancestor_sources
            for block in merged_asil_blocks.get(source_title, [])
        ]
        other_related_asil_blocks = [
            block
            for source_title in other_related_sources
            for block in merged_asil_blocks.get(source_title, [])
        ]

        current_index = value_index(current_title_blocks, {})
        baseline_index = value_index(baseline_title_blocks, {})
        source_index = value_index(source_title_blocks, source_token_map)
        source_base_index = value_index(
            source_base_title_blocks, source_token_map
        )
        latest_asil_index = value_index(
            latest_asil_title_blocks, source_token_map
        )
        source_milestone_indexes = [
            (
                milestone.source_revision,
                value_index(
                    milestone_blocks.get(choice.source_title_id, []),
                    source_token_map,
                ),
            )
            for milestone, milestone_blocks in source_milestone_blocks
        ]
        current_milestone_indexes = [
            (
                milestone.merge_revision,
                value_index(milestone_blocks.get(title_id, []), {}),
            )
            for milestone, milestone_blocks in current_milestone_blocks
        ]
        effective_source_index = value_index(
            effective_source_blocks, source_token_map
        )
        secondary_asil_index = value_index(
            secondary_asil_blocks, secondary_token_map
        )
        ancestor_asil_index = value_index(
            ancestor_asil_blocks, secondary_token_map
        )
        other_related_asil_index = value_index(
            other_related_asil_blocks, secondary_token_map
        )
        effective_current_vanilla_index = value_index(
            effective_vanilla_blocks.get(title_id, []), {}
        )

        keyspace = (
            set(current_index)
            | set(source_index)
            | set(source_base_index)
            | set(latest_asil_index)
        )
        if choice.source_kind == "asil_mod":
            keyspace.update(effective_current_vanilla_index)
        keyspace.update(
            key
            for key in secondary_asil_index
            if key[1] in ADDITIVE_FIELDS
        )
        class_counts: Counter[str] = Counter()
        title_priority_counts: Counter[str] = Counter()
        title_finding_count = 0
        for event_key, field in sorted(keyspace):
            key = (event_key, field)
            current_values = values(current_index, key)
            source_values = values(source_index, key)
            baseline_values = values(baseline_index, key)
            source_base_values = values(source_base_index, key)
            latest_asil_values = values(latest_asil_index, key)
            effective_source_values = values(effective_source_index, key)
            secondary_asil_values = values(secondary_asil_index, key)
            ancestor_asil_values = values(ancestor_asil_index, key)
            other_related_asil_values = values(
                other_related_asil_index, key
            )
            effective_current_vanilla_values = values(
                effective_current_vanilla_index, key
            )
            authoritative_current_target = (
                merged_additive_values(source_values, ancestor_asil_values)
                if field in ADDITIVE_FIELDS and ancestor_asil_values
                else source_values
            )
            source_timeline = timeline_metadata(
                [(source_base_revision, source_base_index)]
                + source_milestone_indexes,
                key,
                source_values,
            )
            current_timeline = timeline_metadata(
                [(args.baseline_revision, baseline_index)]
                + current_milestone_indexes
                + [("WORKTREE", current_index)],
                key,
                authoritative_current_target,
            )
            result = (
                classification,
                ownership,
                severity,
                priority,
                recommendation,
            ) = classify_relation(
                choice,
                field,
                current_values,
                source_values,
                baseline_values,
                effective_source_values,
                secondary_asil_values,
                ancestor_asil_values,
                other_related_asil_values,
                effective_current_vanilla_values,
            )
            (
                classification,
                ownership,
                severity,
                priority,
                recommendation,
            ) = refine_asil_provenance(
                choice,
                current_values,
                source_values,
                baseline_values,
                source_base_values,
                latest_asil_values,
                result,
            )
            result = (
                classification,
                ownership,
                severity,
                priority,
                recommendation,
            )
            (
                classification,
                ownership,
                severity,
                priority,
                recommendation,
            ) = refine_current_milestone_provenance(
                current_values,
                authoritative_current_target,
                current_timeline["target_match_revisions"],
                result,
            )
            class_counts[classification] += 1
            title_priority_counts[priority] += 1
            row = {
                "title_id": title_id,
                "source_decision": choice.decision,
                "source_kind": choice.source_kind,
                "source_title_id": choice.source_title_id,
                "source_choice_status": choice.status,
                "source_confidence": choice.confidence,
                "source_choice_evidence": choice.evidence,
                "event_key": event_key,
                "field": field,
                "classification": classification,
                "ownership": ownership,
                "severity": severity,
                "priority": priority,
                "recommendation": recommendation,
                "current_values": joined(current_values),
                "source_values": joined(source_values),
                "baseline_values": joined(baseline_values),
                "source_base_values": joined(source_base_values),
                "latest_asil_values": joined(latest_asil_values),
                "source_delta_provenance": source_delta_provenance(
                    source_base_values,
                    source_values,
                    latest_asil_values,
                ),
                "source_first_nonempty_revision": source_timeline[
                    "first_nonempty_revision"
                ],
                "source_final_value_transition_revision": source_timeline[
                    "target_transition_revision"
                ],
                "source_value_timeline": source_timeline["timeline"],
                "current_first_authoritative_match_revision": (
                    current_timeline["target_match_revisions"].split(";", 1)[0]
                    if current_timeline["target_match_revisions"]
                    else ""
                ),
                "current_authoritative_match_revisions": current_timeline[
                    "target_match_revisions"
                ],
                "current_value_timeline": current_timeline["timeline"],
                "effective_vanilla_values": joined(
                    effective_current_vanilla_values
                ),
                "secondary_asil_values": joined(secondary_asil_values),
                "related_asil_sources": ";".join(secondary_sources),
                "related_asil_source_roles": ";".join(
                    f"{source_title}={related_roles[source_title]}"
                    for source_title in secondary_sources
                ),
                "ancestor_asil_values": joined(ancestor_asil_values),
                "other_related_asil_values": joined(
                    other_related_asil_values
                ),
                "current_locations": locations(current_index, key),
                "source_locations": locations(source_index, key),
                "baseline_locations": locations(baseline_index, key),
                "source_base_locations": locations(source_base_index, key),
                "latest_asil_locations": locations(latest_asil_index, key),
                "effective_vanilla_locations": locations(
                    effective_current_vanilla_index, key
                ),
                "secondary_asil_locations": locations(
                    secondary_asil_index, key
                ),
                "ancestor_asil_locations": locations(
                    ancestor_asil_index, key
                ),
                "other_related_asil_locations": locations(
                    other_related_asil_index, key
                ),
                "current_matches_baseline": (
                    "yes"
                    if current_values == baseline_values
                    else "no"
                ),
                "current_matches_authoritative_source": (
                    "yes"
                    if current_values
                    and current_values == authoritative_current_target
                    else "no"
                ),
                "merged_source_matches_source_base": (
                    "yes" if source_values == source_base_values else "no"
                ),
                "latest_asil_matches_merged_source": (
                    "yes" if latest_asil_values == source_values else "no"
                ),
                "current_matches_secondary_asil": (
                    "yes"
                    if current_values
                    and current_values == secondary_asil_values
                    else "no"
                ),
                "auto_apply": "no",
                **metadata,
            }
            entry_rows.append(row)
            if priority == "P1" or severity == "deferred":
                findings.append(dict(row))
                title_finding_count += 1

        identity_row = identity_by_title[title_id]
        vanilla_identity_title = identity_row.get("vanilla_title", "")
        if not TITLE_RE.fullmatch(vanilla_identity_title or ""):
            vanilla_identity_title = title_id
        vanilla_identity_blocks = vanilla_blocks.get(vanilla_identity_title, [])
        if choice.decision == "orijinal_dogu" and vanilla_identity_blocks:
            vanilla_identity_index = value_index(vanilla_identity_blocks, {})
            source_files = sorted(
                {game_path(block.path) for block in vanilla_identity_blocks}
            )
            source_file_key = ";".join(source_files)
            stats = vanilla_file_stats.setdefault(
                source_file_key,
                {
                    "source_files": source_file_key,
                    "titles": set(),
                    "titles_with_current_history": set(),
                    "raw_vanilla_key_count": 0,
                    "high_priority_key_count": 0,
                    "not_carried_verbatim_key_count": 0,
                    "exact_current_key_count": 0,
                    "conflicting_current_key_count": 0,
                    "selected_history_source_counts": Counter(),
                },
            )
            stats["titles"].add(title_id)
            if current_title_blocks:
                stats["titles_with_current_history"].add(title_id)
            stats["raw_vanilla_key_count"] += len(vanilla_identity_index)
            stats["high_priority_key_count"] += title_priority_counts["P1"]
            stats["selected_history_source_counts"][choice.source_kind] += 1
            for coverage_key in vanilla_identity_index:
                vanilla_values = values(vanilla_identity_index, coverage_key)
                current_coverage_values = values(current_index, coverage_key)
                if current_coverage_values == vanilla_values:
                    stats["exact_current_key_count"] += 1
                elif current_coverage_values:
                    stats["conflicting_current_key_count"] += 1
                else:
                    stats["not_carried_verbatim_key_count"] += 1

        title_rows.append(
            {
                "title_id": title_id,
                "source_decision": choice.decision,
                "source_kind": choice.source_kind,
                "source_title_id": choice.source_title_id,
                "source_choice_status": choice.status,
                "source_confidence": choice.confidence,
                "source_choice_evidence": choice.evidence,
                "current_block_count": str(len(current_title_blocks)),
                "source_block_count": str(len(source_title_blocks)),
                "source_base_block_count": str(
                    len(source_base_title_blocks)
                ),
                "latest_asil_block_count": str(
                    len(latest_asil_title_blocks)
                ),
                "merge_milestone_count": str(len(milestones)),
                "baseline_block_count": str(len(baseline_title_blocks)),
                "effective_vanilla_block_count": str(
                    len(effective_vanilla_blocks.get(title_id, []))
                ),
                "secondary_asil_block_count": str(
                    len(secondary_asil_blocks)
                ),
                "related_asil_sources": ";".join(secondary_sources),
                "related_asil_source_roles": ";".join(
                    f"{source_title}={related_roles[source_title]}"
                    for source_title in secondary_sources
                ),
                "comparison_key_count": str(len(keyspace)),
                "finding_count": str(title_finding_count),
                "classification_counts": ";".join(
                    f"{key}:{value}" for key, value in sorted(class_counts.items())
                ),
                "current_locations": block_locations(current_title_blocks),
                "source_locations": block_locations(source_title_blocks),
                **metadata,
            }
        )

    entry_rows.sort(
        key=lambda row: (row["title_id"], row["event_key"], row["field"])
    )
    findings.sort(
        key=lambda row: (
            row["priority"],
            row["title_id"],
            row["event_key"],
            row["field"],
        )
    )
    title_rows.sort(key=lambda row: row["title_id"])
    root_inputs = [
        row
        for row in entry_rows
        if row["severity"] in {"review", "deferred"}
    ]
    root_inputs.extend(
        row
        for row in findings
        if row["classification"]
        == "source_choice_unresolved_with_current_history"
    )
    root_rows = build_root_rows(root_inputs)
    write_csv(output_dir / "title_history_source_alignment_entries.csv", entry_rows)
    write_csv(output_dir / "title_history_source_alignment_findings.csv", findings)
    write_csv(output_dir / "title_history_source_alignment_roots.csv", root_rows)
    write_csv(output_dir / "title_history_source_alignment_titles.csv", title_rows)

    vanilla_file_rows: list[dict[str, str]] = []
    for source_file_key, stats in sorted(vanilla_file_stats.items()):
        source_files = source_file_key.split(";") if source_file_key else []
        titles = stats["titles"]
        titles_with_current = stats["titles_with_current_history"]
        imported_roots = sorted(
            {
                root
                for source_file in source_files
                for root in core_import_roots.get(Path(source_file).name, set())
                if root
            }
        )
        current_override_files = [
            source_file
            for source_file in source_files
            if source_file in current_text_by_game_path
        ]
        vanilla_file_rows.append(
            {
                "source_files": source_file_key,
                "source_title_count": str(len(titles)),
                "source_titles": ";".join(sorted(titles)),
                "titles_with_current_history": str(len(titles_with_current)),
                "titles_without_current_history": str(
                    len(titles - titles_with_current)
                ),
                "same_path_current_override": (
                    "yes" if current_override_files else "no"
                ),
                "same_path_current_override_files": ";".join(
                    current_override_files
                ),
                "same_path_current_override_bytes": str(
                    sum(
                        len(current_text_by_game_path[path].encode("utf-8"))
                        for path in current_override_files
                    )
                ),
                "raw_vanilla_bytes": str(
                    sum(
                        len(vanilla_text_by_game_path.get(path, "").encode("utf-8"))
                        for path in source_files
                    )
                ),
                "core_import_root_count": str(len(imported_roots)),
                "core_import_roots": ";".join(imported_roots),
                "raw_vanilla_key_count": str(stats["raw_vanilla_key_count"]),
                "exact_current_key_count": str(
                    stats["exact_current_key_count"]
                ),
                "conflicting_current_key_count": str(
                    stats["conflicting_current_key_count"]
                ),
                "not_carried_verbatim_key_count": str(
                    stats["not_carried_verbatim_key_count"]
                ),
                "high_priority_key_count": str(
                    stats["high_priority_key_count"]
                ),
                "selected_history_source_counts": ";".join(
                    f"{key}:{value}"
                    for key, value in sorted(
                        stats["selected_history_source_counts"].items()
                    )
                ),
                **metadata,
            }
        )
    write_csv(
        output_dir / "title_history_vanilla_file_override_coverage.csv",
        vanilla_file_rows,
    )

    manifest = [
        {
            "input": "identity_csv",
            "path": str(identity_csv),
            "sha256": file_sha256(identity_csv),
        },
        {
            "input": "relation_csv",
            "path": str(relation_csv),
            "sha256": file_sha256(relation_csv),
        },
        {
            "input": "current_title_history",
            "path": str(repo_root / "BookmarksGit/history/titles"),
            "sha256": texts_sha256(current_texts),
        },
        {
            "input": "baseline_title_history",
            "path": args.baseline_revision,
            "sha256": texts_sha256(baseline_texts),
        },
        {
            "input": "source_base_asil_title_history",
            "path": source_base_revision,
            "sha256": texts_sha256(source_base_asil_texts),
        },
        {
            "input": "merged_asil_title_history",
            "path": merged_source_revision,
            "sha256": texts_sha256(merged_asil_texts),
        },
        {
            "input": "latest_asil_title_history",
            "path": str(asil_repo / "BookmarksGit/history/titles"),
            "sha256": texts_sha256(latest_asil_texts),
        },
        {
            "input": "latest_asil_landed_titles",
            "path": str(asil_repo / "BookmarksGit/common/landed_titles"),
            "sha256": texts_sha256(asil_landed_texts),
        },
        {
            "input": "vanilla_title_history",
            "path": str(vanilla_root / "history/titles"),
            "sha256": texts_sha256(vanilla_texts),
        },
    ]
    manifest.extend(milestone_manifest_rows)
    write_csv(output_dir / "title_history_source_alignment_manifest.csv", manifest)

    choice_counts = Counter(choice.status for choice in choices.values())
    decision_counts = Counter(choice.decision for choice in choices.values())
    history_source_counts = Counter(choice.source_kind for choice in choices.values())
    class_counts = Counter(row["classification"] for row in entry_rows)
    ownership_counts = Counter(row["ownership"] for row in findings)
    priority_counts = Counter(row["priority"] for row in findings)
    root_priority_counts = Counter(row["priority"] for row in root_rows)
    root_ownership_counts = Counter(row["ownership"] for row in root_rows)
    overridden_vanilla_files = sum(
        row["same_path_current_override"] == "yes"
        for row in vanilla_file_rows
    )
    root_only_import_files = sum(
        row["same_path_current_override"] == "yes"
        and int(row["source_title_count"]) > int(row["core_import_root_count"])
        for row in vanilla_file_rows
    )
    summary = [
        "# Title History Source Alignment",
        "",
        f"- titles in source-identity scope: `{len(choices)}`",
        f"- resolved source choices: `{choice_counts['resolved']}`",
        f"- unresolved source choices: `{len(choices) - choice_counts['resolved']}`",
        f"- compared date/field keys: `{len(entry_rows)}`",
        f"- high-priority/deferred findings: `{len(findings)}`",
        f"- review/deferred decision roots: `{len(root_rows)}`",
        f"- source base revision: `{source_base_revision}`",
        f"- merged source revision: `{merged_source_revision}`",
        f"- latest asil-mod revision: `{metadata['asil_mod_revision']}`",
        f"- upstream merge milestones: `{len(milestones)}`",
        f"- vanilla source file groups: `{len(vanilla_file_rows)}`",
        f"- same-path vanilla files overridden by current: `{overridden_vanilla_files}`",
        f"- overridden files with root-only import coverage: `{root_only_import_files}`",
        "",
        "## Landed Source Decisions",
        "",
        *[
            f"- `{key}`: `{value}`"
            for key, value in sorted(decision_counts.items())
        ],
        "",
        "## Selected History Sources",
        "",
        *[
            f"- `{key or 'unresolved'}`: `{value}`"
            for key, value in sorted(history_source_counts.items())
        ],
        "",
        "## Comparison Classes",
        "",
        *[
            f"- `{key}`: `{value}`"
            for key, value in sorted(class_counts.items())
        ],
        "",
        "## Finding Ownership",
        "",
        *[
            f"- `{key}`: `{value}`"
            for key, value in sorted(ownership_counts.items())
        ],
        "",
        "## Finding Priorities",
        "",
        *[
            f"- `{key}`: `{value}`"
            for key, value in sorted(priority_counts.items())
        ],
        "",
        "## Decision Root Priorities",
        "",
        *[
            f"- `{key}`: `{value}`"
            for key, value in sorted(root_priority_counts.items())
        ],
        "",
        "## Decision Root Ownership",
        "",
        *[
            f"- `{key}`: `{value}`"
            for key, value in sorted(root_ownership_counts.items())
        ],
        "",
        "## Safety",
        "",
        "- Explicit core-import roots use vanilla title history.",
        "- Other titles prefer a unique same-tier asil-mod history source.",
        "- Vanilla is a fallback when no usable asil-mod history exists.",
        "- Landed source identity and title-history source are reported separately.",
        "- Additive development projections distinguish source ancestors from other relations.",
        "- Same-path vanilla file shadowing remains a separate coverage inventory.",
        "- P2/P3 differences remain in the full entries and per-title reports.",
        "- All rows are audit-only and carry `auto_apply=no`.",
        "- Multi-value and source-only rows require semantic review before edits.",
        "- Milestone timelines distinguish never-integrated gaps from later regressions.",
        "",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "title_history_source_alignment_summary.md").write_text(
        "\n".join(summary), encoding="utf-8"
    )

    print(f"titles={len(choices)}")
    print(f"resolved={choice_counts['resolved']}")
    print(f"entry_rows={len(entry_rows)}")
    print(f"findings={len(findings)}")
    print(f"roots={len(root_rows)}")
    print(f"output_dir={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
