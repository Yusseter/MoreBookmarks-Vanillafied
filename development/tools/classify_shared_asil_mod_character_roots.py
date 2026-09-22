from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import audit_bookmark_runtime_static as runtime
import classify_local_mixed_character_roots as local_mixed
import classify_upstream_integration_character_roots as upstream


OUTPUT_PATH = (
    "development/analysis/generated/repo_integration_closure/"
    "shared_asil_mod_character_roots"
)
ROOT_REPORT = (
    "development/analysis/generated/repo_integration_closure/"
    "repo_integration_blocker_root_causes.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify shared asıl-mod baseline character blocker roots."
    )
    parser.add_argument(
        "--repo-root", type=Path, default=runtime.find_project_root()
    )
    parser.add_argument(
        "--asil-mod-repo", type=Path, default=runtime.DEFAULT_ASIL_MOD_REPO
    )
    parser.add_argument(
        "--vanilla-game-root",
        type=Path,
        default=runtime.DEFAULT_VANILLA_GAME_ROOT,
    )
    parser.add_argument(
        "--baseline-revision", default=runtime.DEFAULT_BASELINE
    )
    parser.add_argument(
        "--merged-source-revision", default=runtime.DEFAULT_MERGED_SOURCE
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def in_scope(row: dict[str, str]) -> bool:
    return (
        row.get("severity") == "blocker"
        and row.get("provenance") == "shared_asil_mod_baseline"
        and row.get("subsystem") in {
            "character_title_history", "bookmark_runtime"
        }
    )


def bookmark_dates(root: dict[str, str]) -> list[runtime.Date]:
    parsed: list[runtime.Date] = []
    for value in root.get("bookmark_dates", "").split("|"):
        date = runtime.parse_date(value.strip())
        if date is not None:
            parsed.append(date)
    return parsed


def classify_recovery(
    root: dict[str, str],
    current_blocks: list[runtime.Block],
    premerge_blocks: list[runtime.Block],
    merged_source_blocks: list[runtime.Block],
    current_source_blocks: list[runtime.Block],
    vanilla_blocks: list[runtime.Block],
    historical: dict[str, str],
    reference_dates: list[runtime.Date],
) -> tuple[str, str, str, str]:
    character_id = root.get("primary_object", "")
    current_life = upstream.block_life(current_blocks, character_id)
    current_status = local_mixed.assignment_life_status(
        current_life, reference_dates
    )
    vanilla_status = local_mixed.assignment_life_status(
        upstream.block_life(vanilla_blocks, character_id), reference_dates
    )
    historical_status = local_mixed.assignment_life_status(
        local_mixed.historical_life(historical, character_id),
        reference_dates,
    )
    source_match = local_mixed.same_block(
        current_blocks, current_source_blocks
    )
    merged_match = local_mixed.same_block(
        current_blocks, merged_source_blocks
    )

    if root.get("classification") == "shared_asil_mod_baseline_undefined_holder":
        if vanilla_blocks:
            historical_note = (
                "; a historical asıl-mod block also exists"
                if historical.get("historical_asil_found") == "yes"
                else ""
            )
            return (
                "shadowed_vanilla_character_candidate",
                "high" if vanilla_status == "valid_at_all_assignments" else "medium",
                (
                    "the exact undefined holder exists in raw vanilla but is hidden "
                    "from effective current history by file override; "
                    f"life-to-reference status is {vanilla_status}{historical_note}"
                ),
                "review_file_override_then_restore_or_merge_the_vanilla_character_block",
            )
        if historical.get("historical_asil_found") == "yes":
            return (
                "restore_historical_asil_character_candidate",
                "high" if historical_status == "valid_at_all_assignments" else "medium",
                (
                    "the exact undefined holder has a historical asıl-mod character "
                    f"block; life-to-reference status is {historical_status}"
                ),
                "review_identity_then_restore_the_historical_character_block_and_reaudit_all_references",
            )
        return (
            "shared_source_holder_chain_without_character_candidate",
            "low",
            (
                "the shared title chain references a holder with no current, "
                "pre-merge, source, vanilla, or historical character definition"
            ),
            "reconstruct_the_character_or_replace_the_shared_source_holder_reference",
        )

    if root.get("classification") == "effective_holder_born_after_bookmark":
        if current_status == "assignment_before_birth":
            return (
                "shared_source_title_character_identity_collision_review",
                "high" if source_match or merged_match else "medium",
                (
                    "the defined character is born after the holder assignment used at "
                    "a bookmark; the same character block is shared with the source, "
                    "so changing the birth date automatically would corrupt identity"
                ),
                "identify_the_intended_historical_holder_then_remap_or_split_the_character_id",
            )

    if root.get("classification") == "featured_character_dead_before_bookmark":
        if current_status == "assignment_at_or_after_death":
            return (
                "shared_source_featured_character_life_collision_review",
                "high" if source_match or merged_match else "medium",
                (
                    "the featured character dies before the bookmark date and the same "
                    "life definition is shared with the source"
                ),
                "review_the_featured_character_identity_or_bookmark_date_without_auto_extending_life",
            )

    return (
        "manual_shared_source_character_review",
        "medium",
        "shared source character issue needs identity-level review",
        "review_character_life_and_all_title_or_bookmark_references_together",
    )


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    mod_root = repo_root / "BookmarksGit"
    asil_repo = args.asil_mod_repo.resolve()
    asil_mod_root = asil_repo / "BookmarksGit"
    vanilla_root = args.vanilla_game_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    root_rows = [
        row
        for row in local_mixed.read_csv(repo_root / ROOT_REPORT)
        if in_scope(row)
    ]
    wanted = {row["primary_object"] for row in root_rows}

    vanilla_character_texts = runtime.read_layer_texts(
        vanilla_root, "history/characters", "vanilla"
    )
    current_character_texts = runtime.read_layer_texts(
        mod_root, "history/characters", "current"
    )
    premerge_character_texts = runtime.read_git_texts(
        repo_root,
        args.baseline_revision,
        "history/characters",
        "premerge",
    )
    merged_source_character_texts = runtime.read_git_texts(
        repo_root,
        args.merged_source_revision,
        "history/characters",
        "merged_asil_mod",
    )
    current_source_character_texts = runtime.read_layer_texts(
        asil_mod_root, "history/characters", "asil_current"
    )

    current = upstream.effective_blocks(
        wanted, current_character_texts, vanilla_character_texts
    )
    premerge = upstream.effective_blocks(
        wanted, premerge_character_texts, vanilla_character_texts
    )
    merged_source = upstream.effective_blocks(
        wanted, merged_source_character_texts, vanilla_character_texts
    )
    current_source = upstream.effective_blocks(
        wanted, current_source_character_texts, vanilla_character_texts
    )
    vanilla_raw = runtime.parse_blocks(
        vanilla_character_texts, runtime.GENERIC_HEADER_RE, wanted
    )

    vanilla_title_texts = runtime.read_layer_texts(
        vanilla_root, "history/titles", "vanilla"
    )
    current_title_texts = runtime.read_layer_texts(
        mod_root, "history/titles", "current"
    )
    current_title_dataset = runtime.build_title_dataset(
        "current", current_title_texts, vanilla_title_texts
    )
    assignments: dict[str, list[dict[str, object]]] = defaultdict(list)
    seen_assignments: set[tuple[str, runtime.Date, str]] = set()
    for assignment in runtime.holder_assignments(current_title_dataset):
        holder = str(assignment["holder"])
        if holder not in wanted:
            continue
        key = (str(assignment["title_id"]), assignment["date"], holder)
        assignments[holder].append(assignment)
        seen_assignments.add(key)
    for title_id, events in current_title_dataset.events.items():
        for event in events:
            holder = event.values.get("holder", "")
            if holder not in wanted:
                continue
            key = (title_id, event.date, holder)
            if key in seen_assignments:
                continue
            assignments[holder].append({
                "title_id": title_id,
                "date": event.date,
                "holder": holder,
                "path": event.path,
                "line": event.line,
            })
            seen_assignments.add(key)

    historical_wanted = {
        row["primary_object"]
        for row in root_rows
        if row.get("classification")
        == "shared_asil_mod_baseline_undefined_holder"
    }
    historical_cache = upstream.historical_asil_candidates(
        asil_repo, historical_wanted
    )
    yusseter_revision = upstream.git_revision(repo_root)
    current_asil_revision = upstream.git_revision(asil_repo)

    rows: list[dict[str, str]] = []
    for root in sorted(root_rows, key=lambda row: row["primary_object"]):
        character_id = root["primary_object"]
        current_blocks = current.get(character_id, [])
        premerge_blocks = premerge.get(character_id, [])
        merged_blocks = merged_source.get(character_id, [])
        source_blocks = current_source.get(character_id, [])
        vanilla_blocks = vanilla_raw.get(character_id, [])
        historical = historical_cache.get(
            character_id, upstream.empty_historical_candidate()
        )
        holder_assignments = assignments.get(character_id, [])
        assignment_dates = [
            value["date"]
            for value in holder_assignments
            if isinstance(value.get("date"), runtime.Date)
        ]
        root_bookmark_dates = bookmark_dates(root)
        if root.get("classification") == "featured_character_dead_before_bookmark":
            reference_dates = root_bookmark_dates
            reference_basis = "bookmark_dates"
        else:
            reference_dates = assignment_dates or root_bookmark_dates
            reference_basis = (
                "holder_assignment_dates"
                if assignment_dates else "bookmark_dates"
            )
        recovery, confidence, reason, recommendation = classify_recovery(
            root,
            current_blocks,
            premerge_blocks,
            merged_blocks,
            source_blocks,
            vanilla_blocks,
            historical,
            reference_dates,
        )
        current_life = upstream.block_life(current_blocks, character_id)
        source_life = upstream.block_life(source_blocks, character_id)
        vanilla_life = upstream.block_life(vanilla_blocks, character_id)
        rows.append({
            "root_cause_id": root["root_cause_id"],
            "character_id": character_id,
            "root_classification": root["classification"],
            "root_provenance": root["provenance"],
            "yusseter_revision": yusseter_revision,
            "baseline_revision": args.baseline_revision,
            "merged_source_revision": args.merged_source_revision,
            "current_asil_revision": current_asil_revision,
            "raw_finding_count": root["raw_finding_count"],
            "impacted_titles": root["impacted_titles"],
            "bookmark_dates": root["bookmark_dates"],
            "holder_assignment_count": str(len(holder_assignments)),
            "holder_assignment_dates": local_mixed.date_values(
                assignment_dates
            ),
            "reference_date_basis": reference_basis,
            "reference_dates": local_mixed.date_values(reference_dates),
            "current_definition_count": str(len(current_blocks)),
            "current_locations": upstream.block_locations(current_blocks),
            "current_birth": str(current_life.birth or "") if current_life else "",
            "current_death": str(current_life.death or "") if current_life else "",
            "current_life_reference_status": local_mixed.assignment_life_status(
                current_life, reference_dates
            ),
            "current_block_sha256": upstream.block_hash(current_blocks),
            "premerge_definition_count": str(len(premerge_blocks)),
            "premerge_locations": upstream.block_locations(premerge_blocks),
            "premerge_matches_current": "yes" if local_mixed.same_block(current_blocks, premerge_blocks) else "no",
            "merged_source_definition_count": str(len(merged_blocks)),
            "merged_source_locations": upstream.block_locations(merged_blocks),
            "merged_source_matches_current": "yes" if local_mixed.same_block(current_blocks, merged_blocks) else "no",
            "current_asil_definition_count": str(len(source_blocks)),
            "current_asil_locations": upstream.block_locations(source_blocks),
            "current_asil_birth": str(source_life.birth or "") if source_life else "",
            "current_asil_death": str(source_life.death or "") if source_life else "",
            "current_asil_matches_current": "yes" if local_mixed.same_block(current_blocks, source_blocks) else "no",
            "vanilla_raw_definition_count": str(len(vanilla_blocks)),
            "vanilla_raw_locations": upstream.block_locations(vanilla_blocks),
            "vanilla_raw_birth": str(vanilla_life.birth or "") if vanilla_life else "",
            "vanilla_raw_death": str(vanilla_life.death or "") if vanilla_life else "",
            "vanilla_life_reference_status": local_mixed.assignment_life_status(
                vanilla_life, reference_dates
            ),
            **historical,
            "historical_life_reference_status": (
                local_mixed.assignment_life_status(
                    local_mixed.historical_life(historical, character_id),
                    reference_dates,
                )
            ),
            "recovery_classification": recovery,
            "confidence": confidence,
            "reason": reason,
            "recommendation": recommendation,
        })

    output_csv = output_dir / "shared_asil_mod_character_root_audit.csv"
    local_mixed.write_csv(output_csv, rows)
    recovery_counts = Counter(row["recovery_classification"] for row in rows)
    root_counts = Counter(row["root_classification"] for row in rows)
    summary = [
        "# Shared Asil Mod Character Root Audit",
        "",
        f"- roots: `{len(rows)}`",
        f"- represented raw blocker rows: `{sum(int(row['raw_finding_count']) for row in rows)}`",
        f"- raw vanilla candidates: `{sum(int(row['vanilla_raw_definition_count']) > 0 for row in rows)}`",
        f"- historical asıl-mod blocks found: `{sum(row['historical_asil_found'] == 'yes' for row in rows)}`",
        "",
        "## Root Classes",
        "",
        *[
            f"- {classification}: `{count}`"
            for classification, count in root_counts.most_common()
        ],
        "",
        "## Recovery Classes",
        "",
        *[
            f"- {classification}: `{count}`"
            for classification, count in recovery_counts.most_common()
        ],
        "",
        "## Safety",
        "",
        "- Shared source errors are not accepted as correct merely because both repos contain them.",
        "- This audit does not modify BookmarksGit source files.",
        "- Recovery candidates remain blockers until identity and every reference are validated.",
        "- Character birth or death dates are never changed automatically.",
    ]
    (output_dir / "shared_asil_mod_character_root_audit_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print(f"roots={len(rows)}")
    print(f"historical_query_ids={len(historical_wanted)}")
    print(f"root_classes={dict(sorted(root_counts.items()))}")
    print(f"recovery={dict(sorted(recovery_counts.items()))}")
    print(f"output={output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
