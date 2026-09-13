from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

import audit_bookmark_runtime_static as runtime
import classify_upstream_integration_character_roots as upstream


OUTPUT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "local_mixed_character_roots"
)
ROOT_REPORT = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "repo_integration_blocker_root_causes.csv"
)
TARGET_PROVENANCES = {"preexisting_yusseter", "mixed_provenance"}
TARGET_SUBSYSTEMS = {"character_title_history", "bookmark_runtime"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify local and mixed-provenance character blocker roots."
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
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def in_scope(row: dict[str, str]) -> bool:
    return (
        row.get("severity") == "blocker"
        and row.get("subsystem") in TARGET_SUBSYSTEMS
        and row.get("provenance") in TARGET_PROVENANCES
    )


def date_values(values: list[runtime.Date]) -> str:
    return " | ".join(str(value) for value in sorted(set(values)))


def assignment_life_status(
    life: runtime.CharacterLife | None,
    dates: list[runtime.Date],
) -> str:
    dated = [value for value in dates if value.year >= 0]
    if life is None:
        return "character_undefined"
    if not dated:
        return "no_dated_holder_assignment"
    before_birth = [
        value for value in dated if life.birth is not None and value < life.birth
    ]
    after_death = [
        value for value in dated if life.death is not None and value >= life.death
    ]
    if before_birth and after_death:
        return "assignments_before_birth_and_after_death"
    if before_birth:
        return "assignment_before_birth"
    if after_death:
        return "assignment_at_or_after_death"
    if life.birth is None or life.death is None:
        return "valid_at_all_assignments_partial_life_boundary"
    return "valid_at_all_assignments"


def historical_life(
    historical: dict[str, str], character_id: str
) -> runtime.CharacterLife | None:
    if historical.get("historical_asil_found") != "yes":
        return None
    birth = runtime.parse_date(historical.get("historical_asil_birth", ""))
    death = runtime.parse_date(historical.get("historical_asil_death", ""))
    return runtime.CharacterLife(
        character_id=character_id,
        birth=birth,
        death=death,
        path=historical.get("historical_asil_path", ""),
        line=int(historical.get("historical_asil_line") or 0),
    )


def same_block(
    left: list[runtime.Block], right: list[runtime.Block]
) -> bool:
    return bool(
        left
        and right
        and upstream.block_hash(left) == upstream.block_hash(right)
    )


def classify_recovery(
    root: dict[str, str],
    current_blocks: list[runtime.Block],
    premerge_blocks: list[runtime.Block],
    merged_source_blocks: list[runtime.Block],
    current_source_blocks: list[runtime.Block],
    vanilla_blocks: list[runtime.Block],
    historical: dict[str, str],
    assignment_dates: list[runtime.Date],
) -> tuple[str, str, str, str]:
    character_id = root.get("primary_object", "")
    current_life = upstream.block_life(current_blocks, character_id)
    current_status = assignment_life_status(current_life, assignment_dates)
    vanilla_status = assignment_life_status(
        upstream.block_life(vanilla_blocks, character_id), assignment_dates
    )
    historical_status = assignment_life_status(
        historical_life(historical, character_id), assignment_dates
    )

    if root.get("classification") == "effective_holder_born_after_bookmark":
        source_match = same_block(current_blocks, current_source_blocks)
        merged_match = same_block(current_blocks, merged_source_blocks)
        if current_status == "assignment_before_birth":
            return (
                "shared_source_title_character_identity_collision_review",
                "high" if source_match or merged_match else "medium",
                (
                    "the defined character is born after current holder assignments; "
                    "the same title/character mismatch predates the latest merge or is "
                    "shared with the source, so changing the birth date is unsafe"
                ),
                "identify_the_intended_historical_holder_then_remap_or_split_the_character_id",
            )

    if root.get("classification") == "undefined_holder_multiple_assignment_origins":
        if vanilla_blocks:
            historical_note = (
                "; a historical source block also exists"
                if historical.get("historical_asil_found") == "yes"
                else ""
            )
            return (
                "shadowed_vanilla_character_candidate",
                "high" if vanilla_status == "valid_at_all_assignments" else "medium",
                (
                    "the exact character ID exists in raw vanilla but is absent from "
                    "effective current history because a mod character file overrides "
                    f"the vanilla file; life-to-assignment status is {vanilla_status}"
                    f"{historical_note}"
                ),
                "review_file_override_then_restore_or_merge_the_vanilla_character_block",
            )
        if historical.get("historical_asil_found") == "yes":
            return (
                "restore_historical_asil_character_candidate",
                "high" if historical_status == "valid_at_all_assignments" else "medium",
                (
                    "the exact undefined character ID has a historical source block and "
                    f"its life-to-assignment status is {historical_status}"
                ),
                "review_identity_then_restore_the_historical_character_block_and_reaudit_all_references",
            )
        if not any(
            (
                current_blocks,
                premerge_blocks,
                merged_source_blocks,
                current_source_blocks,
                vanilla_blocks,
            )
        ):
            return (
                "missing_character_definition_or_wrong_holder_id_review",
                "low",
                (
                    "the holder is referenced by multiple title chains but no current, "
                    "pre-merge, source, vanilla, or historical character block was found"
                ),
                "manually_identify_the_person_then_define_the_character_or_replace_the_holder_id",
            )

    return (
        "manual_local_mixed_character_review",
        "medium",
        "local or mixed-provenance character root needs identity-level review",
        "review_character_life_and_all_title_assignments_together",
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
        row for row in read_csv(repo_root / ROOT_REPORT) if in_scope(row)
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
    current_source_title_texts = runtime.read_layer_texts(
        asil_mod_root, "history/titles", "asil_current_title"
    )
    source_title_ids = {
        title_id
        for root in root_rows
        for title_id in upstream.split_compound_values(
            root.get("impacted_titles", "")
        )
    }
    current_source_title_dataset = upstream.effective_title_dataset(
        "asil_current_title",
        source_title_ids,
        current_source_title_texts,
        vanilla_title_texts,
    )
    assignments: dict[str, list[dict[str, object]]] = defaultdict(list)
    seen_assignments: set[tuple[str, runtime.Date, str]] = set()
    for assignment in runtime.holder_assignments(current_title_dataset):
        holder = str(assignment["holder"])
        if holder not in wanted:
            continue
        key = (
            str(assignment["title_id"]),
            assignment["date"],
            holder,
        )
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
        character_id
        for character_id in wanted
        if not current.get(character_id, [])
        and not premerge.get(character_id, [])
        and not merged_source.get(character_id, [])
        and not current_source.get(character_id, [])
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
        recovery, confidence, reason, recommendation = classify_recovery(
            root,
            current_blocks,
            premerge_blocks,
            merged_blocks,
            source_blocks,
            vanilla_blocks,
            historical,
            assignment_dates,
        )
        current_life = upstream.block_life(current_blocks, character_id)
        premerge_life = upstream.block_life(premerge_blocks, character_id)
        source_life = upstream.block_life(source_blocks, character_id)
        vanilla_life = upstream.block_life(vanilla_blocks, character_id)
        source_invalid_assignments = upstream.source_invalid_holder_assignments(
            current_source_title_dataset,
            character_id,
            {
                str(value["title_id"])
                for value in holder_assignments
                if value.get("title_id")
            },
            assignment_dates,
            source_life,
        )
        source_origin_classification = (
            "asil_mod_source_native_broken_holder_chain"
            if source_invalid_assignments
            else "local_or_mixed_character_review"
        )
        source_origin_evidence = (
            "the asıl-mod source has the same invalid title/date/holder state: "
            + " | ".join(source_invalid_assignments)
            if source_invalid_assignments
            else "no exact invalid asıl-mod title/date/holder match was proven"
        )
        historical_status = assignment_life_status(
            historical_life(historical, character_id), assignment_dates
        )
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
            "holder_assignment_dates": date_values(assignment_dates),
            "holder_assignment_locations": " | ".join(
                sorted({
                    f"BookmarksGit/{str(value['path']).split(':', 1)[-1]}:{value['line']}"
                    for value in holder_assignments
                })
            ),
            "current_definition_count": str(len(current_blocks)),
            "current_locations": upstream.block_locations(current_blocks),
            "current_birth": str(current_life.birth or "") if current_life else "",
            "current_death": str(current_life.death or "") if current_life else "",
            "current_life_assignment_status": assignment_life_status(
                current_life, assignment_dates
            ),
            "current_block_sha256": upstream.block_hash(current_blocks),
            "premerge_definition_count": str(len(premerge_blocks)),
            "premerge_locations": upstream.block_locations(premerge_blocks),
            "premerge_birth": str(premerge_life.birth or "") if premerge_life else "",
            "premerge_death": str(premerge_life.death or "") if premerge_life else "",
            "premerge_matches_current": "yes" if same_block(current_blocks, premerge_blocks) else "no",
            "merged_source_definition_count": str(len(merged_blocks)),
            "merged_source_locations": upstream.block_locations(merged_blocks),
            "merged_source_matches_current": "yes" if same_block(current_blocks, merged_blocks) else "no",
            "current_asil_definition_count": str(len(source_blocks)),
            "current_asil_locations": upstream.block_locations(source_blocks),
            "current_asil_birth": str(source_life.birth or "") if source_life else "",
            "current_asil_death": str(source_life.death or "") if source_life else "",
            "current_asil_matches_current": "yes" if same_block(current_blocks, source_blocks) else "no",
            "vanilla_raw_definition_count": str(len(vanilla_blocks)),
            "vanilla_raw_locations": upstream.block_locations(vanilla_blocks),
            "vanilla_raw_birth": str(vanilla_life.birth or "") if vanilla_life else "",
            "vanilla_raw_death": str(vanilla_life.death or "") if vanilla_life else "",
            "vanilla_life_assignment_status": assignment_life_status(
                vanilla_life, assignment_dates
            ),
            **historical,
            "historical_life_assignment_status": historical_status,
            "recovery_classification": recovery,
            "source_origin_classification": source_origin_classification,
            "source_origin_evidence": source_origin_evidence,
            "asil_source_invalid_assignment_evidence": " | ".join(
                source_invalid_assignments
            ),
            "confidence": confidence,
            "reason": reason,
            "recommendation": recommendation,
        })

    output_csv = output_dir / "local_mixed_character_root_audit.csv"
    write_csv(output_csv, rows)
    recovery_counts = Counter(row["recovery_classification"] for row in rows)
    provenance_counts = Counter(row["root_provenance"] for row in rows)
    summary = [
        "# Local And Mixed Character Root Audit",
        "",
        f"- roots: `{len(rows)}`",
        f"- represented raw blocker rows: `{sum(int(row['raw_finding_count']) for row in rows)}`",
        f"- historical source blocks found: `{sum(row['historical_asil_found'] == 'yes' for row in rows)}`",
        "",
        "## Provenance",
        "",
        *[
            f"- {provenance}: `{count}`"
            for provenance, count in provenance_counts.most_common()
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
        "- This audit does not modify BookmarksGit source files.",
        "- Recovery candidates remain blockers until identity and every title reference are validated.",
        "- Birth dates are never changed automatically to satisfy an older holder assignment.",
    ]
    (output_dir / "local_mixed_character_root_audit_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print(f"roots={len(rows)}")
    print(f"historical_query_ids={len(historical_wanted)}")
    print(f"provenance={dict(sorted(provenance_counts.items()))}")
    print(f"recovery={dict(sorted(recovery_counts.items()))}")
    print(f"output={output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
