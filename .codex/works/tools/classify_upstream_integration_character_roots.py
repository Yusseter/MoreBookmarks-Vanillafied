from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import audit_bookmark_runtime_static as runtime


OUTPUT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "upstream_integration_character_roots"
)
ROOT_REPORT = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "repo_integration_blocker_root_causes.csv"
)
HOLDER_REPORT = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "bookmark_runtime_static/title_holder_reference_provenance.csv"
)
ASIL_TIGER_REPORT = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "ck3_tiger_asil_mod.json"
)
RECOVERY_TARGET_PATH = (
    "BookmarksGit/history/characters/00_YB_UPSTREAM_CHARACTER_RECOVERY.txt"
)
DEPENDENCY_FIELD_FAMILIES = {
    "father": "character",
    "mother": "character",
    "employer": "character",
    "add_spouse": "character",
    "add_matrilineal_spouse": "character",
    "add_same_sex_spouse": "character",
    "remove_spouse": "character",
    "dynasty": "dynasty",
    "dynasty_house": "dynasty_house",
    "set_house": "dynasty_house",
    "culture": "culture",
    "set_culture": "culture",
    "faith": "faith",
    "religion": "faith",
    "set_character_faith_no_effect": "faith",
    "trait": "trait",
    "dna": "dna",
    "give_nickname": "nickname",
}
DEPENDENCY_FAMILY_PATHS = {
    "dynasty": "common/dynasties",
    "dynasty_house": "common/dynasty_houses",
    "culture": "common/culture/cultures",
    "faith": "common/religion/religion_types",
    "trait": "common/traits",
    "dna": "common/dna_data",
    "nickname": "common/nicknames",
}
DEPENDENCY_ASSIGNMENT_RE = re.compile(
    r'^\s*(' + "|".join(
        re.escape(field) for field in sorted(DEPENDENCY_FIELD_FAMILIES)
    ) + r')\s*=\s*"?([A-Za-z0-9_.:\-]+)"?'
)


def parse_args() -> argparse.Namespace:
    repo_root = runtime.find_project_root()
    parser = argparse.ArgumentParser(
        description="Classify upstream-integration character blocker roots."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
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


def read_asil_tiger_undefined_characters(path: Path) -> set[str]:
    if not path.is_file() or path.stat().st_size == 0:
        return set()
    reports = json.loads(path.read_text(encoding="utf-8-sig"))
    pattern = re.compile(
        r"^character ([A-Za-z0-9_.:\-]+) not defined in history/characters/$"
    )
    result: set[str] = set()
    for report in reports:
        if report.get("key") != "missing-item":
            continue
        match = pattern.fullmatch(report.get("message") or "")
        if match:
            result.add(match.group(1))
    return result


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def block_hash(blocks: list[runtime.Block]) -> str:
    if not blocks:
        return ""
    text = "\n\n".join("\n".join(block.lines) for block in blocks)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def block_locations(blocks: list[runtime.Block]) -> str:
    return " | ".join(
        f"{block.path}:{block.start_line}" for block in blocks
    )


def block_life(
    blocks: list[runtime.Block], character_id: str
) -> runtime.CharacterLife | None:
    return runtime.extract_character_life(blocks, character_id) if blocks else None


def clean_block_path(block: runtime.Block) -> str:
    return block.path.split(":", 1)[-1]


def object_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def reference_dates(
    root: dict[str, str], holder_evidence: list[dict[str, str]]
) -> list[runtime.Date]:
    values = {
        row.get("assignment_date", "").strip()
        for row in holder_evidence
        if row.get("assignment_date", "").strip()
    }
    values.update(
        value.strip()
        for value in re.split(r"\s*[|;]\s*", root.get("bookmark_dates", ""))
        if value.strip()
    )
    return sorted(
        parsed
        for value in values
        if (parsed := runtime.parse_date(value)) is not None
    )


def validate_candidate_life(
    life: runtime.CharacterLife | None, dates: list[runtime.Date]
) -> str:
    if not dates:
        return "no_reference_dates"
    if life is None or life.birth is None:
        return "missing_birth_requires_review"
    if any(date < life.birth for date in dates):
        return "reference_date_before_birth"
    if life.death is not None and any(date >= life.death for date in dates):
        return "reference_date_at_or_after_death"
    return "all_reference_dates_within_life"


def build_new_file_patch(
    target_path: str,
    blocks: dict[str, tuple[runtime.Block, str]],
) -> str:
    content: list[str] = ["# Yusseter: UPSTREAM_CHARACTER_RECOVERY", ""]
    for character_id in sorted(blocks, key=object_sort_key):
        block, recovery_class = blocks[character_id]
        marker = (
            "RESTORED_PREMERGE_FEATURED_CHARACTER"
            if recovery_class == "restore_premerge_featured_character_candidate"
            else "RESTORED_PREMERGE_CHARACTER"
        )
        content.append(f"# Yusseter: {marker}")
        content.extend(block.lines)
        content.append("")
    while content and content[-1] == "":
        content.pop()
    if not content:
        return ""
    patch = [
        "--- /dev/null",
        f"+++ b/{target_path}",
        f"@@ -0,0 +1,{len(content)} @@",
        *(f"+{line}" for line in content),
    ]
    return "\n".join(patch) + "\n"


def block_dependencies(
    block: runtime.Block,
) -> list[tuple[str, str, str]]:
    dependencies: set[tuple[str, str, str]] = set()
    for line in block.lines:
        match = DEPENDENCY_ASSIGNMENT_RE.match(runtime.strip_comment(line))
        if not match:
            continue
        field, value = match.groups()
        if value in {"0", "none", "yes", "no"}:
            continue
        dependencies.add((field, DEPENDENCY_FIELD_FAMILIES[field], value))
    return sorted(dependencies)


def effective_definition_keys(
    mod_root: Path,
    vanilla_root: Path,
    relative_dir: str,
    wanted: set[str],
) -> set[str]:
    if not wanted:
        return set()
    mod_texts = runtime.read_layer_texts(
        mod_root, relative_dir, "current_dependency"
    )
    vanilla_texts = runtime.read_layer_texts(
        vanilla_root, relative_dir, "vanilla_dependency"
    )
    texts = {
        **mod_texts,
        **runtime.effective_vanilla_texts(mod_texts, vanilla_texts),
    }
    found: set[str] = set()
    for text in texts.values():
        for line in text.splitlines():
            match = runtime.GENERIC_HEADER_RE.match(runtime.strip_comment(line))
            if match and match.group(1) in wanted:
                found.add(match.group(1))
    return found


def effective_blocks(
    wanted: set[str],
    mod_texts: dict[str, str],
    vanilla_texts: dict[str, str],
) -> dict[str, list[runtime.Block]]:
    mod_blocks = runtime.parse_blocks(
        mod_texts, runtime.GENERIC_HEADER_RE, wanted
    )
    missing = wanted - set(mod_blocks)
    vanilla_blocks = runtime.parse_blocks(
        runtime.effective_vanilla_texts(mod_texts, vanilla_texts),
        runtime.GENERIC_HEADER_RE,
        missing,
    )
    return {
        character_id: mod_blocks.get(
            character_id, vanilla_blocks.get(character_id, [])
        )
        for character_id in wanted
        if character_id in mod_blocks or character_id in vanilla_blocks
    }


def split_compound_values(value: str) -> set[str]:
    return {
        item.strip()
        for item in re.split(r"\s*[|;]\s*", value or "")
        if item.strip()
    }


def effective_title_dataset(
    label: str,
    wanted: set[str],
    mod_texts: dict[str, str],
    vanilla_texts: dict[str, str],
) -> runtime.TitleDataset:
    mod_blocks = runtime.parse_blocks(
        mod_texts, runtime.TITLE_HEADER_RE, wanted
    )
    missing = wanted - set(mod_blocks)
    vanilla_blocks = runtime.parse_blocks(
        runtime.effective_vanilla_texts(mod_texts, vanilla_texts),
        runtime.TITLE_HEADER_RE,
        missing,
    )
    blocks = {
        title_id: mod_blocks.get(
            title_id, vanilla_blocks.get(title_id, [])
        )
        for title_id in wanted
        if title_id in mod_blocks or title_id in vanilla_blocks
    }
    return runtime.TitleDataset(
        label, runtime.parse_title_events(blocks), blocks
    )


def source_invalid_holder_assignments(
    dataset: runtime.TitleDataset,
    character_id: str,
    title_ids: set[str],
    dates: list[runtime.Date],
    life: runtime.CharacterLife | None,
) -> list[str]:
    evidence: list[str] = []
    for title_id in sorted(title_ids):
        for date in sorted(set(dates)):
            if dataset.state_at(title_id, date).holder != character_id:
                continue
            if life is None or life.birth is None:
                status = "character_undefined"
            elif date < life.birth:
                status = "assignment_before_birth"
            elif life.death is not None and date >= life.death:
                status = "assignment_at_or_after_death"
            else:
                continue
            evidence.append(f"{title_id}@{date}:{status}")
    return evidence


def git_lines(repo: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout.splitlines()


def empty_historical_candidate() -> dict[str, str]:
    return {
        "historical_asil_found": "no",
        "historical_asil_revision": "",
        "historical_asil_trigger_commit": "",
        "historical_asil_trigger_date": "",
        "historical_asil_trigger_subject": "",
        "historical_asil_path": "",
        "historical_asil_line": "",
        "historical_asil_birth": "",
        "historical_asil_death": "",
        "historical_asil_block_sha256": "",
    }


def find_blocks_at_revision(
    repo: Path, revision: str, character_ids: set[str]
) -> dict[str, tuple[str, runtime.Block]]:
    if not character_ids:
        return {}
    alternatives = "|".join(
        re.escape(character_id) for character_id in sorted(character_ids)
    )
    pattern = (
        rf"^[[:space:]]*({alternatives})"
        rf"[[:space:]]*=[[:space:]]*\{{"
    )
    matches = git_lines(
        repo,
        "grep",
        "-n",
        "-E",
        pattern,
        revision,
        "--",
        "BookmarksGit/history/characters",
    )
    if not matches:
        return {}
    locations: dict[str, set[str]] = defaultdict(set)
    prefix = f"{revision}:"
    for raw in matches:
        value = raw[len(prefix) :] if raw.startswith(prefix) else raw
        parts = value.split(":", 2)
        if len(parts) < 3 or not parts[1].isdigit():
            continue
        header = runtime.GENERIC_HEADER_RE.match(parts[2])
        if header and header.group(1) in character_ids:
            locations[parts[0]].add(header.group(1))
    if not locations:
        return {}
    found: dict[str, tuple[str, runtime.Block]] = {}
    for path, path_ids in sorted(locations.items()):
        raw = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.decode("utf-8-sig", errors="replace")
        parsed = runtime.parse_blocks(
            {f"asil_history:{path}": raw},
            runtime.GENERIC_HEADER_RE,
            path_ids,
        )
        for character_id, blocks in parsed.items():
            if blocks and character_id not in found:
                found[character_id] = (path, blocks[0])
    return found


def historical_asil_candidates(
    repo: Path, character_ids: set[str]
) -> dict[str, dict[str, str]]:
    results = {
        character_id: empty_historical_candidate()
        for character_id in character_ids
    }
    if not character_ids:
        return results

    alternatives = "|".join(
        re.escape(character_id) for character_id in sorted(character_ids)
    )
    git_pattern = rf"^[ \t]*({alternatives})[ \t]*=[ \t]*\{{"
    diff_header = re.compile(
        rf"^[+-][ \t]*({alternatives})[ \t]*=[ \t]*\{{"
    )
    log_lines = git_lines(
        repo,
        "log",
        "--all",
        f"-G{git_pattern}",
        "--format=@@META@@%H%x09%P%x09%cs%x09%s",
        "--patch",
        "--unified=0",
        "--no-ext-diff",
        "--",
        "BookmarksGit/history/characters",
    )

    commits: list[tuple[str, list[str], str, str, set[str]]] = []
    active: tuple[str, list[str], str, str, set[str]] | None = None
    for line in log_lines:
        if line.startswith("@@META@@"):
            if active is not None:
                commits.append(active)
            parts = line[len("@@META@@") :].split("\t", 3)
            active = (
                parts[0],
                parts[1].split(),
                parts[2],
                parts[3],
                set(),
            )
            continue
        if active is None or line.startswith("+++") or line.startswith("---"):
            continue
        match = diff_header.match(line)
        if match:
            active[4].add(match.group(1))
    if active is not None:
        commits.append(active)

    unresolved = set(character_ids)
    revision_cache: dict[tuple[str, tuple[str, ...]], dict[str, tuple[str, runtime.Block]]] = {}
    for commit, parents, date, subject, touched in commits:
        candidates = unresolved & touched
        if not candidates:
            continue
        for revision in [commit, *parents]:
            if not revision or not candidates:
                continue
            cache_key = (revision, tuple(sorted(candidates)))
            found = revision_cache.setdefault(
                cache_key,
                find_blocks_at_revision(repo, revision, candidates),
            )
            for character_id, (path, block) in found.items():
                life = runtime.extract_character_life([block], character_id)
                results[character_id] = {
                    "historical_asil_found": "yes",
                    "historical_asil_revision": revision,
                    "historical_asil_trigger_commit": commit,
                    "historical_asil_trigger_date": date,
                    "historical_asil_trigger_subject": subject,
                    "historical_asil_path": path,
                    "historical_asil_line": str(block.start_line),
                    "historical_asil_birth": str(life.birth or ""),
                    "historical_asil_death": str(life.death or ""),
                    "historical_asil_block_sha256": block_hash([block]),
                }
                unresolved.discard(character_id)
                candidates.discard(character_id)
    return results


def git_revision(repo: Path) -> str:
    lines = git_lines(repo, "rev-parse", "HEAD")
    return lines[0] if lines else ""


def classify_recovery(
    root_class: str,
    current_blocks: list[runtime.Block],
    premerge_blocks: list[runtime.Block],
    merged_source_blocks: list[runtime.Block],
    current_source_blocks: list[runtime.Block],
    vanilla_blocks: list[runtime.Block],
    historical: dict[str, str],
) -> tuple[str, str, str, str]:
    if root_class == "upstream_integration_source_character_removed":
        if premerge_blocks and not current_blocks:
            return (
                "restore_premerge_character_block_candidate",
                "high",
                "character block existed pre-merge while preserved title assignments survived the merge",
                "review_identity_then_restore_premerge_block_in_yusseter_character_file",
            )
    if root_class == "featured_character_undefined":
        if premerge_blocks and not current_blocks:
            return (
                "restore_premerge_featured_character_candidate",
                "high",
                "featured bookmark character existed pre-merge but is undefined now",
                "review_identity_then_restore_premerge_block_and_revalidate_bookmark",
            )
    if root_class == "upstream_integration_source_undefined_holder":
        if historical["historical_asil_found"] == "yes":
            return (
                "restore_historical_asil_character_candidate",
                "medium",
                "imported asıl-mod holder is undefined now but a historical asıl-mod character block exists",
                "review_source_history_identity_then_restore_block_or_replace_holder_chain",
            )
        if vanilla_blocks:
            return (
                "shadowed_vanilla_character_candidate",
                "medium",
                "holder is absent from effective current data but exists in raw vanilla character history",
                "review_file_override_then_restore_or_repoint_holder",
            )
        return (
            "source_holder_chain_without_character_candidate",
            "low",
            "imported holder has no current, pre-merge, merged-source, current-source, vanilla, or historical source block",
            "manually_reconstruct_or_replace_source_holder_chain",
        )
    if root_class == "effective_holder_born_after_bookmark":
        return (
            "character_identity_or_life_date_collision_review",
            "high",
            "defined character life begins after one or more dates where the imported title chain assigns that ID",
            "compare_premerge_duplicate_identity_and_source_chain_then_remap_or_split_character",
        )
    return (
        "manual_upstream_character_review",
        "medium",
        "upstream integration character issue needs identity-level review",
        "review_character_and_title_history_together",
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

    asil_tiger_undefined = read_asil_tiger_undefined_characters(
        repo_root / ASIL_TIGER_REPORT
    )
    root_rows = []
    for row in read_csv(repo_root / ROOT_REPORT):
        if row.get("subsystem") not in {
            "character_title_history", "bookmark_runtime"
        }:
            continue
        source_tiger_match = (
            row.get("classification") == "yusseter_current_only_undefined_holder"
            and row.get("primary_object") in asil_tiger_undefined
        )
        if row.get("provenance") == "upstream_integration" or source_tiger_match:
            root_rows.append(row)
    wanted = {row["primary_object"] for row in root_rows}
    holder_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(repo_root / HOLDER_REPORT):
        if row.get("holder") in wanted:
            holder_rows[row["holder"]].append(row)

    vanilla_texts = runtime.read_layer_texts(
        vanilla_root, "history/characters", "vanilla"
    )
    current_texts = runtime.read_layer_texts(
        mod_root, "history/characters", "current"
    )
    current_source_texts = runtime.read_layer_texts(
        asil_mod_root, "history/characters", "asil_current"
    )
    premerge_texts = runtime.read_git_texts(
        repo_root, args.baseline_revision, "history/characters", "premerge"
    )
    merged_source_texts = runtime.read_git_texts(
        repo_root,
        args.merged_source_revision,
        "history/characters",
        "merged_asil_mod",
    )

    current = effective_blocks(wanted, current_texts, vanilla_texts)
    premerge = effective_blocks(wanted, premerge_texts, vanilla_texts)
    merged_source = effective_blocks(wanted, merged_source_texts, vanilla_texts)
    current_source = effective_blocks(wanted, current_source_texts, vanilla_texts)
    vanilla_raw = runtime.parse_blocks(
        vanilla_texts, runtime.GENERIC_HEADER_RE, wanted
    )
    source_title_ids = {
        title_id
        for root in root_rows
        for title_id in split_compound_values(root.get("impacted_titles", ""))
    }
    vanilla_title_texts = runtime.read_layer_texts(
        vanilla_root, "history/titles", "vanilla_title"
    )
    current_source_title_texts = runtime.read_layer_texts(
        asil_mod_root, "history/titles", "asil_current_title"
    )
    current_source_title_dataset = effective_title_dataset(
        "asil_current_title",
        source_title_ids,
        current_source_title_texts,
        vanilla_title_texts,
    )

    historical_wanted = {
        root["primary_object"]
        for root in root_rows
        if (
            root["classification"]
            == "upstream_integration_source_undefined_holder"
            or root["primary_object"] in asil_tiger_undefined
        )
        and not premerge.get(root["primary_object"], [])
        and not merged_source.get(root["primary_object"], [])
        and not current_source.get(root["primary_object"], [])
    }
    historical_cache = historical_asil_candidates(asil_repo, historical_wanted)
    historical_ids_by_revision: dict[str, set[str]] = defaultdict(set)
    for character_id, candidate in historical_cache.items():
        revision = candidate.get("historical_asil_revision", "")
        if candidate.get("historical_asil_found") == "yes" and revision:
            historical_ids_by_revision[revision].add(character_id)
    historical_source_blocks: dict[str, tuple[str, runtime.Block]] = {}
    for revision, character_ids in sorted(historical_ids_by_revision.items()):
        historical_source_blocks.update(
            find_blocks_at_revision(asil_repo, revision, character_ids)
        )
    yusseter_revision = git_revision(repo_root)
    current_asil_revision = git_revision(asil_repo)

    rows: list[dict[str, str]] = []
    preview_blocks: dict[str, tuple[runtime.Block, str]] = {}
    for root in sorted(root_rows, key=lambda row: row["primary_object"]):
        character_id = root["primary_object"]
        source_tiger_match = character_id in asil_tiger_undefined
        analysis_root_class = root["classification"]
        if (
            analysis_root_class == "yusseter_current_only_undefined_holder"
            and source_tiger_match
        ):
            analysis_root_class = "upstream_integration_source_undefined_holder"
        current_blocks = current.get(character_id, [])
        premerge_blocks = premerge.get(character_id, [])
        merged_blocks = merged_source.get(character_id, [])
        source_blocks = current_source.get(character_id, [])
        vanilla_blocks = vanilla_raw.get(character_id, [])
        historical = empty_historical_candidate()
        if (
            analysis_root_class
            == "upstream_integration_source_undefined_holder"
            and not premerge_blocks
            and not merged_blocks
            and not source_blocks
        ):
            historical = historical_cache.get(
                character_id, empty_historical_candidate()
            )
        recovery, confidence, reason, recommendation = classify_recovery(
            analysis_root_class,
            current_blocks,
            premerge_blocks,
            merged_blocks,
            source_blocks,
            vanilla_blocks,
            historical,
        )
        life_values = {
            "current": block_life(current_blocks, character_id),
            "premerge": block_life(premerge_blocks, character_id),
            "merged_source": block_life(merged_blocks, character_id),
            "current_source": block_life(source_blocks, character_id),
            "vanilla_raw": block_life(vanilla_blocks, character_id),
        }
        holder_evidence = holder_rows.get(character_id, [])
        dates = reference_dates(root, holder_evidence)
        source_invalid_assignments = source_invalid_holder_assignments(
            current_source_title_dataset,
            character_id,
            split_compound_values(root.get("impacted_titles", "")),
            dates,
            life_values["current_source"],
        )
        premerge_same_assignment = any(
            row.get("premerge_same_assignment") == "yes"
            for row in holder_evidence
        )
        merged_source_same_assignment = any(
            row.get("merged_source_same_assignment") == "yes"
            for row in holder_evidence
        )
        if source_invalid_assignments:
            source_origin_classification = (
                "asil_mod_source_native_broken_holder_chain"
            )
            source_origin_evidence = (
                "the asıl-mod source has the same invalid title/date/holder state: "
                + " | ".join(source_invalid_assignments)
            )
        elif (
            analysis_root_class in {
                "upstream_integration_source_character_removed",
                "upstream_integration_source_undefined_holder",
            }
            and (merged_source_same_assignment or source_tiger_match)
            and not merged_blocks
            and not source_blocks
        ):
            source_origin_classification = (
                "asil_mod_source_native_broken_holder_chain"
            )
            source_origin_evidence = (
                "the asıl-mod source reports the same undefined holder chain, while "
                "both merged and current asıl-mod character definitions are absent"
            )
        elif root["classification"] == "featured_character_undefined":
            source_origin_classification = (
                "yusseter_bookmark_depends_on_removed_source_character"
            )
            source_origin_evidence = (
                "the featured-bookmark reference is Yusseter-side, while its pre-merge "
                "character block disappeared with the source character replacement"
            )
        elif root["classification"] == "effective_holder_born_after_bookmark":
            source_origin_classification = "cross_layer_character_identity_collision"
            source_origin_evidence = (
                "the current source character identity replaced an older Yusseter "
                "identity still used by preserved title assignments"
            )
        else:
            source_origin_classification = "upstream_integration_requires_review"
            source_origin_evidence = "source ownership is not yet conclusive"

        source_block: runtime.Block | None = None
        source_kind = ""
        source_revision = ""
        source_definition_count = 0
        if recovery in {
            "restore_premerge_character_block_candidate",
            "restore_premerge_featured_character_candidate",
        }:
            source_kind = "premerge_yusseter"
            source_revision = args.baseline_revision
            source_definition_count = len(premerge_blocks)
            if len(premerge_blocks) == 1:
                source_block = premerge_blocks[0]
        elif recovery == "restore_historical_asil_character_candidate":
            source_kind = "historical_asil_mod"
            source_revision = historical.get("historical_asil_revision", "")
            historical_source = historical_source_blocks.get(character_id)
            source_definition_count = 1 if historical_source else 0
            if historical_source:
                source_block = historical_source[1]

        candidate_life = (
            block_life([source_block], character_id) if source_block else None
        )
        life_status = validate_candidate_life(candidate_life, dates)
        if (
            source_origin_classification
            == "asil_mod_source_native_broken_holder_chain"
        ):
            candidate_status = "deferred_asil_mod_source_native_regression"
        elif recovery in {
            "restore_premerge_character_block_candidate",
            "restore_premerge_featured_character_candidate",
        }:
            if current_blocks:
                candidate_status = "blocked_current_definition_exists"
            elif source_definition_count != 1 or source_block is None:
                candidate_status = "blocked_premerge_source_not_unique"
            elif life_status != "all_reference_dates_within_life":
                candidate_status = "blocked_reference_date_life_mismatch"
            else:
                candidate_status = "preview_ready_high_confidence"
                preview_blocks[character_id] = (source_block, recovery)
        elif recovery == "restore_historical_asil_character_candidate":
            candidate_status = "manual_historical_source_identity_review"
        elif recovery == "character_identity_or_life_date_collision_review":
            candidate_status = "manual_identity_or_life_date_collision_review"
        elif recovery == "source_holder_chain_without_character_candidate":
            candidate_status = "manual_source_holder_without_donor"
        else:
            candidate_status = "manual_character_review"

        rows.append({
            "root_cause_id": root["root_cause_id"],
            "character_id": character_id,
            "root_classification": root["classification"],
            "yusseter_revision": yusseter_revision,
            "baseline_revision": args.baseline_revision,
            "merged_source_revision": args.merged_source_revision,
            "current_asil_revision": current_asil_revision,
            "raw_finding_count": root["raw_finding_count"],
            "impacted_titles": root["impacted_titles"],
            "bookmark_dates": root["bookmark_dates"],
            "current_definition_count": str(len(current_blocks)),
            "current_locations": block_locations(current_blocks),
            "current_birth": str(life_values["current"].birth or "") if life_values["current"] else "",
            "current_death": str(life_values["current"].death or "") if life_values["current"] else "",
            "current_block_sha256": block_hash(current_blocks),
            "premerge_definition_count": str(len(premerge_blocks)),
            "premerge_locations": block_locations(premerge_blocks),
            "premerge_birth": str(life_values["premerge"].birth or "") if life_values["premerge"] else "",
            "premerge_death": str(life_values["premerge"].death or "") if life_values["premerge"] else "",
            "premerge_block_sha256": block_hash(premerge_blocks),
            "merged_source_definition_count": str(len(merged_blocks)),
            "merged_source_locations": block_locations(merged_blocks),
            "current_asil_definition_count": str(len(source_blocks)),
            "current_asil_locations": block_locations(source_blocks),
            "vanilla_raw_definition_count": str(len(vanilla_blocks)),
            "vanilla_raw_locations": block_locations(vanilla_blocks),
            "holder_assignment_rows": str(len(holder_evidence)),
            "premerge_same_assignment": "yes" if premerge_same_assignment else "no",
            "merged_source_same_assignment": "yes" if merged_source_same_assignment else "no",
            **historical,
            "recovery_classification": recovery,
            "confidence": confidence,
            "reason": reason,
            "recommendation": recommendation,
            "source_origin_classification": source_origin_classification,
            "source_origin_evidence": source_origin_evidence,
            "asil_source_invalid_assignment_evidence": " | ".join(
                source_invalid_assignments
            ),
            "asil_tiger_undefined_character": "yes" if source_tiger_match else "no",
            "dry_run_candidate_status": candidate_status,
            "dry_run_target_path": RECOVERY_TARGET_PATH,
            "dry_run_source_kind": source_kind,
            "dry_run_source_revision": source_revision,
            "dry_run_source_path": clean_block_path(source_block) if source_block else "",
            "dry_run_source_line": str(source_block.start_line) if source_block else "",
            "dry_run_source_definition_count": str(source_definition_count),
            "dry_run_source_block_sha256": block_hash([source_block]) if source_block else "",
            "dry_run_reference_dates": " | ".join(str(date) for date in dates),
            "dry_run_candidate_birth": str(candidate_life.birth or "") if candidate_life else "",
            "dry_run_candidate_death": str(candidate_life.death or "") if candidate_life else "",
            "dry_run_life_validation": life_status,
            "dry_run_patch_included": "yes" if character_id in preview_blocks else "no",
            "dry_run_dependency_review": "pending",
            "auto_apply": "no",
        })

    dependencies_by_character = {
        character_id: block_dependencies(block)
        for character_id, (block, _) in preview_blocks.items()
    }
    wanted_by_family: dict[str, set[str]] = defaultdict(set)
    for dependencies in dependencies_by_character.values():
        for _, family, value in dependencies:
            wanted_by_family[family].add(value)

    existing_characters = set(effective_blocks(
        wanted_by_family.get("character", set()),
        current_texts,
        vanilla_texts,
    ))
    found_by_family: dict[str, set[str]] = {
        "character": existing_characters | set(preview_blocks),
    }
    for family, relative_dir in DEPENDENCY_FAMILY_PATHS.items():
        found_by_family[family] = effective_definition_keys(
            mod_root,
            vanilla_root,
            relative_dir,
            wanted_by_family.get(family, set()),
        )

    row_by_character = {row["character_id"]: row for row in rows}
    dependency_rows: list[dict[str, str]] = []
    validated_preview_blocks: dict[str, tuple[runtime.Block, str]] = {}
    for character_id in sorted(preview_blocks, key=object_sort_key):
        missing: list[str] = []
        for field, family, value in dependencies_by_character[character_id]:
            if value in found_by_family.get(family, set()):
                resolved_by = (
                    "same_recovery_preview"
                    if family == "character" and value in preview_blocks
                    else "effective_current_or_vanilla"
                )
                status = "resolved"
            else:
                resolved_by = ""
                status = "missing"
                missing.append(f"{family}:{value}")
            dependency_rows.append({
                "character_id": character_id,
                "field": field,
                "dependency_family": family,
                "dependency_value": value,
                "status": status,
                "resolved_by": resolved_by,
            })
        row = row_by_character[character_id]
        if missing:
            row["dry_run_candidate_status"] = (
                "blocked_missing_static_dependencies"
            )
            row["dry_run_dependency_review"] = "missing"
            row["dry_run_missing_dependencies"] = " | ".join(sorted(missing))
            row["dry_run_patch_included"] = "no"
        else:
            row["dry_run_dependency_review"] = (
                "all_direct_static_dependencies_resolved"
            )
            row["dry_run_missing_dependencies"] = ""
            row["dry_run_patch_included"] = "yes"
            validated_preview_blocks[character_id] = preview_blocks[character_id]
    preview_blocks = validated_preview_blocks
    for row in rows:
        row.setdefault("dry_run_missing_dependencies", "")

    output_csv = output_dir / "upstream_integration_character_root_audit.csv"
    write_csv(output_csv, rows)
    dry_run_csv = output_dir / "upstream_integration_character_recovery_dry_run.csv"
    write_csv(dry_run_csv, rows)
    dependency_csv = (
        output_dir / "upstream_integration_character_recovery_dependencies.csv"
    )
    write_csv(dependency_csv, dependency_rows)
    preview_patch = output_dir / "upstream_integration_character_recovery_preview.patch"
    preview_patch.write_text(
        build_new_file_patch(RECOVERY_TARGET_PATH, preview_blocks),
        encoding="utf-8",
    )
    recovery_counts = Counter(row["recovery_classification"] for row in rows)
    candidate_status_counts = Counter(
        row["dry_run_candidate_status"] for row in rows
    )
    dependency_status_counts = Counter(
        row["status"] for row in dependency_rows
    )
    summary = [
        "# Upstream Integration Character Root Audit",
        "",
        f"- roots: `{len(rows)}`",
        f"- represented raw blocker rows: `{sum(int(row['raw_finding_count']) for row in rows)}`",
        f"- historical asıl-mod blocks found: `{sum(row['historical_asil_found'] == 'yes' for row in rows)}`",
        "",
        "## Recovery Classes",
        "",
        *[
            f"- {classification}: `{count}`"
            for classification, count in recovery_counts.most_common()
        ],
        "",
        "## Dry-Run Recovery",
        "",
        f"- candidate rows: `{len(rows)}`",
        f"- preview target: `{RECOVERY_TARGET_PATH}`",
        f"- preview blocks: `{len(preview_blocks)}`",
        f"- direct dependency rows: `{len(dependency_rows)}`",
        *[
            f"- {status}: `{count}`"
            for status, count in candidate_status_counts.most_common()
        ],
        *[
            f"- dependency {status}: `{count}`"
            for status, count in dependency_status_counts.most_common()
        ],
        "- auto-apply: `no`",
        "- Historical asıl-mod donors remain outside the preview until identity review.",
        "",
        "## Safety",
        "",
        "- This audit does not modify BookmarksGit source files.",
        "- Recovery candidates remain review-only until character identity and all references are validated.",
    ]
    (output_dir / "upstream_integration_character_root_audit_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print(f"roots={len(rows)}")
    print(f"recovery={dict(sorted(recovery_counts.items()))}")
    print(f"dry_run={dict(sorted(candidate_status_counts.items()))}")
    print(f"dependencies={dict(sorted(dependency_status_counts.items()))}")
    print(f"preview_blocks={len(preview_blocks)}")
    print(f"output={output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
