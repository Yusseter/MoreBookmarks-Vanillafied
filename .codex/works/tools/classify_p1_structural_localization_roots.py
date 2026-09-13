from __future__ import annotations

import argparse
import csv
import difflib
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import audit_bookmark_runtime_static as runtime
import audit_landed_title_source_identity as landed


DEFAULT_ASIL_MOD_REPO = (
    Path(__file__).resolve().parents[3].parent / "Leviathonlx MoreBookmarks-Plus"
)
DEFAULT_VANILLA_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
)
DEFAULT_BASELINE = "09588cbb5212a31bc4a373b6990b2c4da1203a35"
INPUT_ROOT = Path(
    ".codex/works/analysis/generated/repo_integration_closure"
)
OUTPUT_ROOT = INPUT_ROOT / "p1_structural_localization_roots"

NUMERIC_HEADER_RE = re.compile(r"^\s*(\d+)\s*=\s*\{")
LOC_KEY_RE = re.compile(r"^\s*([^\s:#][^:]*?):(?:\d+)?\s+(.+?)\s*$")
MISSING_FILE_RE = re.compile(r"^file\s+(.+?)\s+does not exist$")
ENTRY_FIELD_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_.:@?'-]*)\s*=\s*"
    r"(?:\"([^\"]*)\"|([^\s{}]+))"
)
COA_USAGE_RE = re.compile(
    r"\b(dynasty_house|dynasty|coat_of_arms|set_coa)\s*=\s*"
    r"(?:title:)?(?:\"([^\"]+)\"|([A-Za-z0-9_.:\-]+))"
)
COA_ALIAS_RE = re.compile(
    r"^\s*([A-Za-z0-9_.:\-]+)\s*=\s*([A-Za-z0-9_.:\-]+)\s*$"
)
COA_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:\-]+")


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Classify P1 duplicate history, missing assets, and localization "
            "review roots without changing live mod content."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument(
        "--asil-mod-repo", type=Path, default=DEFAULT_ASIL_MOD_REPO
    )
    parser.add_argument(
        "--vanilla-game-root", type=Path, default=DEFAULT_VANILLA_ROOT
    )
    parser.add_argument("--baseline-revision", default=DEFAULT_BASELINE)
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


def git_file_text(repo: Path, revision: str, relative: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=repo,
        capture_output=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8-sig", errors="replace")


def git_tree_paths(
    repo: Path, revision: str, prefixes: list[str]
) -> set[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", revision, "--", *prefixes],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines()}


def canonical_lines(lines: tuple[str, ...] | list[str]) -> str:
    clean: list[str] = []
    for line in lines:
        visible = runtime.strip_comment(line).strip()
        if not visible:
            continue
        clean.append(re.sub(r"\s+", " ", visible))
    return "\n".join(clean)


def canonical_block_body(lines: tuple[str, ...] | list[str]) -> str:
    text = "\n".join(runtime.strip_comment(line) for line in lines)
    opening = text.find("{")
    closing = text.rfind("}")
    if opening < 0 or closing <= opening:
        return re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+", " ", text[opening + 1 : closing]).strip()


def forward_title_relations(path: Path) -> dict[str, list[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for raw_row in read_csv(path):
        row = {
            (key or "").strip(): (value or "").strip()
            for key, value in raw_row.items()
        }
        current = (row.get("source_title_id") or "").strip()
        source_values = (row.get("mod_title_id") or "").strip()
        if not current or not source_values:
            continue
        for token in re.split(r"\s*[;&]\s*", source_values):
            if token:
                result[current].add(token)
    return {key: sorted(values) for key, values in result.items()}


def block_entry_map(block: runtime.Block) -> dict[str, list[str]]:
    entries: dict[str, list[str]] = defaultdict(list)
    for entry in runtime.direct_entries(block):
        entries[entry.key].append(canonical_lines(entry.lines))
    return dict(entries)


def entry_field_map(lines: tuple[str, ...]) -> dict[str, set[str]]:
    body = runtime.direct_body(lines)
    fields: dict[str, set[str]] = defaultdict(set)
    for match in ENTRY_FIELD_RE.finditer(body):
        value = match.group(2) if match.group(2) is not None else match.group(3)
        fields[match.group(1)].add(value)
    return dict(fields)


def compare_duplicate_blocks(blocks: list[runtime.Block]) -> dict[str, str]:
    fingerprints = [canonical_lines(block.lines) for block in blocks]
    entry_maps = [block_entry_map(block) for block in blocks]
    repeated_keys: set[str] = set()
    all_keys = sorted({key for values in entry_maps for key in values})
    conflicting_keys: list[str] = []
    conflicting_fields: list[str] = []
    conflicting_field_values: list[str] = []
    identical_repeated_keys: list[str] = []
    complementary_repeated_keys: list[str] = []
    for key in all_keys:
        present_entries = [
            (block, entry)
            for block in blocks
            for entry in runtime.direct_entries(block)
            if entry.key == key
        ]
        present = [values[key] for values in entry_maps if key in values]
        if len(present) < 2 or len(present_entries) < 2:
            continue
        repeated_keys.add(key)
        canonical_values = {" || ".join(value) for value in present}
        if len(canonical_values) == 1:
            identical_repeated_keys.append(key)
            continue
        per_entry_fields = [
            entry_field_map(entry.lines) for _, entry in present_entries
        ]
        shared_fields = {
            field
            for field in {field for fields in per_entry_fields for field in fields}
            if sum(field in fields for fields in per_entry_fields) > 1
        }
        field_conflicts = []
        for field in sorted(shared_fields):
            field_values = {
                value
                for fields in per_entry_fields
                for value in fields.get(field, set())
            }
            if len(field_values) > 1:
                field_conflicts.append(field)
                locations: list[str] = []
                for (block, entry), fields in zip(
                    present_entries, per_entry_fields, strict=True
                ):
                    values = sorted(fields.get(field, set()))
                    if not values:
                        continue
                    path = block.path.split(":", 1)[-1]
                    line = block.start_line + entry.relative_start
                    locations.append(f"{path}:{line}={','.join(values)}")
                conflicting_field_values.append(
                    f"{key}:{field}[{' | '.join(locations)}]"
                )
        if field_conflicts:
            conflicting_keys.append(key)
            conflicting_fields.extend(f"{key}:{field}" for field in field_conflicts)
        else:
            complementary_repeated_keys.append(key)

    if len(set(fingerprints)) == 1:
        comparison = "exact_duplicate"
        recommendation = "remove_redundant_duplicate_after_load_order_review"
    elif conflicting_fields:
        comparison = "overlapping_conflicting_fields"
        recommendation = "manually_consolidate_complete_timeline"
    elif complementary_repeated_keys:
        comparison = "additive_complementary_same_key"
        recommendation = "consolidate_complementary_entries_preserving_all_fields"
    elif repeated_keys:
        comparison = "additive_with_repeated_identical_entries"
        recommendation = "consolidate_blocks_preserving_unique_entries"
    else:
        comparison = "disjoint_additive_blocks"
        recommendation = "consolidate_or_document_engine_merge_dependency"
    return {
        "comparison": comparison,
        "repeated_keys": ";".join(sorted(repeated_keys)),
        "conflicting_keys": ";".join(conflicting_keys),
        "conflicting_fields": ";".join(conflicting_fields),
        "conflicting_field_values": ";".join(conflicting_field_values),
        "identical_repeated_keys": ";".join(identical_repeated_keys),
        "complementary_repeated_keys": ";".join(complementary_repeated_keys),
        "recommendation": recommendation,
    }


def duplicate_provenance(
    current_blocks: list[runtime.Block],
    baseline_blocks: list[runtime.Block],
    asil_blocks: list[runtime.Block],
) -> str:
    current_signature = sorted(canonical_lines(block.lines) for block in current_blocks)
    baseline_signature = sorted(canonical_lines(block.lines) for block in baseline_blocks)
    asil_signature = sorted(canonical_lines(block.lines) for block in asil_blocks)
    if len(baseline_blocks) > 1 and current_signature == baseline_signature:
        return "preexisting_yusseter_unchanged"
    if len(current_blocks) > len(baseline_blocks) and asil_signature == current_signature:
        return "upstream_integration_introduced"
    if len(current_blocks) > len(baseline_blocks):
        return "post_baseline_yusseter_introduced"
    if len(asil_blocks) > 1 and current_signature == asil_signature:
        return "shared_current_asil_mod"
    if len(baseline_blocks) > 1:
        return "preexisting_yusseter_modified"
    return "current_state_requires_history_provenance_review"


def history_duplicate_rows(
    repo_root: Path,
    asil_repo: Path,
    vanilla_root: Path,
    baseline: str,
    findings: list[dict[str, str]],
) -> list[dict[str, str]]:
    title_relations = forward_title_relations(
        repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv"
    )
    specs = (
        (
            "title_history",
            "duplicate_title_block_same_layer",
            "BookmarksGit/history/titles",
            "history/titles",
            runtime.TITLE_HEADER_RE,
        ),
        (
            "province_history",
            "duplicate_province_block",
            "BookmarksGit/history/provinces",
            "history/provinces",
            NUMERIC_HEADER_RE,
        ),
    )
    output: list[dict[str, str]] = []
    for domain, classification, current_dir, snapshot_dir, pattern in specs:
        wanted = {
            row["object"]
            for row in findings
            if row.get("severity") == "review"
            and row.get("domain") == domain
            and row.get("classification") == classification
        }
        if not wanted:
            continue
        current = runtime.parse_blocks(
            runtime.read_layer_texts(repo_root, current_dir, "current"),
            pattern,
            wanted,
        )
        baseline_data = runtime.parse_blocks(
            runtime.read_git_texts(repo_root, baseline, snapshot_dir, "baseline"),
            pattern,
            wanted,
        )
        asil_wanted = set(wanted)
        if domain == "title_history":
            for current_title in wanted:
                asil_wanted.update(
                    source_title
                    for source_title in title_relations.get(current_title, [])
                    if source_title[:2] == current_title[:2]
                )
        asil = runtime.parse_blocks(
            runtime.read_layer_texts(asil_repo, current_dir, "asil_mod"),
            pattern,
            asil_wanted,
        )
        vanilla = runtime.parse_blocks(
            runtime.read_layer_texts(vanilla_root, snapshot_dir, "vanilla"),
            pattern,
            wanted,
        )
        source_rows = {
            row["object"]: row
            for row in findings
            if row.get("severity") == "review"
            and row.get("domain") == domain
            and row.get("classification") == classification
        }
        for object_id in sorted(wanted):
            source = source_rows[object_id]
            layer_name = ""
            if domain == "title_history":
                layer_name = (
                    "development"
                    if "development" in source.get("reason", "")
                    else "regional"
                )

            def same_layer(block: runtime.Block) -> bool:
                if domain != "title_history":
                    return True
                is_development = block.path.lower().endswith(
                    "z00_adevelopment.txt"
                )
                return is_development == (layer_name == "development")

            blocks = [
                block for block in current.get(object_id, []) if same_layer(block)
            ]
            baseline_blocks = [
                block
                for block in baseline_data.get(object_id, [])
                if same_layer(block)
            ]
            asil_blocks = [
                block for block in asil.get(object_id, []) if same_layer(block)
            ]
            mapped_source_objects = (
                [
                    source_title
                    for source_title in title_relations.get(object_id, [])
                    if source_title[:2] == object_id[:2]
                    and source_title != object_id
                ]
                if domain == "title_history"
                else []
            )
            mapped_asil_blocks = [
                block
                for source_title in mapped_source_objects
                for block in asil.get(source_title, [])
                if same_layer(block)
            ]
            vanilla_blocks = [
                block for block in vanilla.get(object_id, []) if same_layer(block)
            ]
            comparison = compare_duplicate_blocks(blocks)
            current_signature = sorted(
                canonical_lines(block.lines) for block in blocks
            )
            baseline_signature = sorted(
                canonical_lines(block.lines) for block in baseline_blocks
            )
            asil_signature = sorted(
                canonical_lines(block.lines) for block in asil_blocks
            )
            current_body_signature = sorted(
                canonical_block_body(block.lines) for block in blocks
            )
            mapped_asil_body_signature = sorted(
                canonical_block_body(block.lines) for block in mapped_asil_blocks
            )
            mapped_asil_signature_match = bool(
                mapped_asil_blocks
                and current_body_signature == mapped_asil_body_signature
            )
            vanilla_signature = sorted(
                canonical_lines(block.lines) for block in vanilla_blocks
            )
            exact_asil_signature_match = current_signature == asil_signature
            semantic_source_provenance = duplicate_provenance(
                blocks,
                baseline_blocks,
                asil_blocks,
            )
            if exact_asil_signature_match:
                semantic_source_provenance = "shared_exact_asil_mod_source"
            elif mapped_asil_signature_match:
                semantic_source_provenance = "shared_mapped_asil_mod_source"
            recommended_action = comparison["recommendation"]
            if (
                mapped_asil_signature_match
                and comparison["comparison"] == "overlapping_conflicting_fields"
            ):
                recommended_action = (
                    "defer_or_fix_mapped_asil_source_conflict_first"
                )
            output.append({
                "domain": domain,
                "object": object_id,
                "history_layer": layer_name,
                "current_block_count": str(len(blocks)),
                "current_locations": " | ".join(
                    f"{block.path.split(':', 1)[-1]}:{block.start_line}"
                    for block in blocks
                ),
                "comparison": comparison["comparison"],
                "repeated_direct_keys": comparison["repeated_keys"],
                "conflicting_direct_keys": comparison["conflicting_keys"],
                "conflicting_fields": comparison["conflicting_fields"],
                "conflicting_field_values": comparison[
                    "conflicting_field_values"
                ],
                "identical_repeated_direct_keys": comparison[
                    "identical_repeated_keys"
                ],
                "complementary_repeated_direct_keys": comparison[
                    "complementary_repeated_keys"
                ],
                "baseline_block_count": str(len(baseline_blocks)),
                "asil_mod_block_count": str(len(asil_blocks)),
                "vanilla_block_count": str(len(vanilla_blocks)),
                "provenance": duplicate_provenance(
                    blocks,
                    baseline_blocks,
                    asil_blocks,
                ),
                "semantic_source_provenance": semantic_source_provenance,
                "current_matches_baseline_signature": (
                    "yes" if current_signature == baseline_signature else "no"
                ),
                "current_matches_asil_signature": (
                    "yes" if exact_asil_signature_match else "no"
                ),
                "mapped_asil_source_objects": ";".join(mapped_source_objects),
                "mapped_asil_source_block_count": str(len(mapped_asil_blocks)),
                "mapped_asil_source_locations": " | ".join(
                    f"{block.key}@{block.path.split(':', 1)[-1]}:{block.start_line}"
                    for block in mapped_asil_blocks
                ),
                "current_matches_mapped_asil_body_signature": (
                    "yes" if mapped_asil_signature_match else "no"
                ),
                "current_matches_vanilla_signature": (
                    "yes" if current_signature == vanilla_signature else "no"
                ),
                "current_block_origins": block_origin_evidence(
                    blocks,
                    baseline_blocks,
                    asil_blocks,
                ),
                "recommended_priority": (
                    "P1"
                    if comparison["comparison"]
                    in {"exact_duplicate", "overlapping_conflicting_fields"}
                    else "P2"
                ),
                "recommended_action": recommended_action,
                "closure_path": source.get("path", ""),
                "closure_line": source.get("line", ""),
                "source_classification": classification,
            })
    return output


def first_meaningful_line(lines: list[str]) -> str:
    for line in lines:
        clean = line.lstrip("\ufeff").strip()
        if clean and not clean.startswith("#"):
            return clean
    return ""


def scan_localization_texts(
    root: Path,
    display_root: Path,
    wanted: set[str] | None = None,
) -> dict[str, list[dict[str, str]]]:
    keys: dict[str, list[dict[str, str]]] = defaultdict(list)
    if not root.is_dir():
        return {}
    for path in sorted(root.rglob("*.yml")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        lines = text.splitlines()
        header = first_meaningful_line(lines)
        if not (
            path.name.lower().endswith("_l_english.yml")
            or header == "l_english:"
        ):
            continue
        try:
            relative = path.relative_to(display_root).as_posix()
        except ValueError:
            relative = path.as_posix()
        for line_number, raw in enumerate(lines, start=1):
            visible = runtime.strip_comment(raw).rstrip()
            match = LOC_KEY_RE.match(visible)
            if not match:
                continue
            key, value = match.groups()
            if wanted is not None and key not in wanted:
                continue
            keys[key].append({
                "path": relative,
                "line": str(line_number),
                "value": value.strip(),
            })
    return dict(keys)


def scan_git_localization_paths(
    repo_root: Path,
    revision: str,
    relative_paths: set[str],
    wanted: set[str],
) -> dict[str, list[dict[str, str]]]:
    keys: dict[str, list[dict[str, str]]] = defaultdict(list)
    for relative in sorted(relative_paths):
        text = git_file_text(repo_root, revision, relative)
        if not text:
            continue
        lines = text.splitlines()
        header = first_meaningful_line(lines)
        if not (
            Path(relative).name.lower().endswith("_l_english.yml")
            or header == "l_english:"
        ):
            continue
        for line_number, raw in enumerate(lines, start=1):
            visible = runtime.strip_comment(raw).rstrip()
            match = LOC_KEY_RE.match(visible)
            if not match:
                continue
            key, value = match.groups()
            if key not in wanted:
                continue
            keys[key].append({
                "path": relative,
                "line": str(line_number),
                "value": value.strip(),
            })
    return dict(keys)


def localization_rank(path: str) -> int:
    normalized = "/" + path.replace("\\", "/").lower().strip("/") + "/"
    if "/localization/replace/" in normalized:
        return 2
    if "/localization/english/replace/" in normalized:
        return 1
    return 0


def values(entries: list[dict[str, str]]) -> set[str]:
    return {entry["value"] for entry in entries}


def localization_duplicate_rows(
    repo_root: Path,
    asil_repo: Path,
    vanilla_root: Path,
    baseline: str,
    findings: list[dict[str, str]],
) -> list[dict[str, str]]:
    closure_rows = [
        row for row in findings
        if row.get("domain") == "localization"
        and row.get("classification") == "conflicting_duplicate_key"
    ]
    wanted = {row["object"] for row in closure_rows}
    current = scan_localization_texts(
        repo_root / "BookmarksGit/localization", repo_root, wanted
    )
    current_paths = {
        entry["path"]
        for key in wanted
        for entry in current.get(key, [])
    }
    baseline_data = scan_git_localization_paths(
        repo_root, baseline, current_paths, wanted
    )
    asil = scan_localization_texts(
        asil_repo / "BookmarksGit/localization", asil_repo, wanted
    )
    vanilla = scan_localization_texts(
        vanilla_root / "localization", vanilla_root, wanted
    )
    output: list[dict[str, str]] = []
    source_rows = {row["object"]: row for row in closure_rows}
    for key in sorted(wanted):
        entries = current.get(key, [])
        clean_values = values(entries)
        paths = sorted({entry["path"] for entry in entries})
        ranks = sorted({localization_rank(path) for path in paths})
        if len(clean_values) <= 1:
            conflict_type = "parser_false_positive_comment_only"
            priority = "P3"
            recommendation = "remove_false_positive_after_comment_aware_parser_refresh"
        elif len(paths) == 1:
            conflict_type = "same_file_conflicting_values"
            priority = "P1"
            recommendation = "keep_one_intended_value_in_file"
        elif len(ranks) > 1:
            conflict_type = "cross_precedence_override_candidate"
            priority = "P2"
            recommendation = "verify_replace_precedence_and_document_final_value"
        else:
            conflict_type = "same_precedence_cross_file_conflict"
            priority = "P1"
            recommendation = "resolve_file_load_order_and_keep_one_final_value"

        baseline_values = values(baseline_data.get(key, []))
        asil_values = values(asil.get(key, []))
        vanilla_values = values(vanilla.get(key, []))
        if baseline_values == clean_values and len(clean_values) > 1:
            provenance = "preexisting_yusseter_unchanged"
        elif clean_values and clean_values == asil_values and clean_values != baseline_values:
            provenance = "upstream_integration_introduced_or_expanded"
        elif len(baseline_values) > 1:
            provenance = "preexisting_yusseter_modified"
        elif len(clean_values) > 1:
            provenance = "post_baseline_conflict_or_newly_visible"
        else:
            provenance = "audit_parser_false_positive"
        asil_matches = sorted(clean_values & asil_values)
        vanilla_matches = sorted(clean_values & vanilla_values)
        source = source_rows[key]
        output.append({
            "key": key,
            "conflict_type": conflict_type,
            "current_occurrence_count": str(len(entries)),
            "current_distinct_clean_value_count": str(len(clean_values)),
            "current_values": " | ".join(sorted(clean_values)),
            "current_locations": " | ".join(
                f"{entry['path']}:{entry['line']}={entry['value']}"
                for entry in entries
            ),
            "localization_precedence_ranks": ";".join(map(str, ranks)),
            "baseline_values": " | ".join(sorted(baseline_values)),
            "asil_mod_matching_values": " | ".join(asil_matches),
            "vanilla_matching_values": " | ".join(vanilla_matches),
            "provenance": provenance,
            "recommended_priority": priority,
            "recommended_action": recommendation,
            "closure_path": source.get("path", ""),
            "closure_line": source.get("line", ""),
        })
    return output


def list_files(root: Path, relative_roots: list[str]) -> set[str]:
    output: set[str] = set()
    for relative in relative_roots:
        directory = root / relative
        if not directory.is_dir():
            continue
        output.update(
            path.relative_to(root).as_posix()
            for path in directory.rglob("*")
            if path.is_file()
        )
    return output


def contains_reference(text: str, target: str) -> bool:
    return bool(text) and Path(target).name.lower() in text.lower()


def semantic_asset_cores(path: str) -> set[str]:
    stem = Path(path).stem
    parts = stem.split("_")
    if parts and parts[0].lower() in {"e", "k", "d", "c", "b"}:
        parts = parts[1:]
    cores = {"_".join(parts).lower()}
    if parts and parts[0].isupper() and len(parts[0]) > 1:
        cores.add("_".join(parts[1:]).lower())
    return {core for core in cores if core}


def nearest_asset_candidates(
    target: str, available: set[str]
) -> list[tuple[str, float, str]]:
    target_path = Path(target)
    parent = target_path.parent.as_posix().lower()
    names = [
        path
        for path in available
        if Path(path).parent.as_posix().lower() == parent
    ]
    target_cores = semantic_asset_cores(target)
    scored: list[tuple[str, float, str]] = []
    for path in names:
        candidate_cores = semantic_asset_cores(path)
        score = max(
            difflib.SequenceMatcher(None, left, right).ratio()
            for left in target_cores
            for right in candidate_cores
        )
        relation = "fuzzy_name_only"
        if target_cores & candidate_cores:
            relation = "same_semantic_core"
            score = 1.0
        elif any(
            left in right or right in left
            for left in target_cores
            for right in candidate_cores
        ):
            relation = "split_or_extended_semantic_core"
        elif score >= 0.90:
            relation = "probable_spelling_variant"
        scored.append((path, score, relation))
    return sorted(scored, key=lambda item: (-item[1], item[0]))[:4]


def missing_asset_rows(
    repo_root: Path,
    asil_repo: Path,
    vanilla_root: Path,
    baseline: str,
    findings: list[dict[str, str]],
) -> list[dict[str, str]]:
    source_rows = [
        row for row in findings
        if row.get("domain") == "ck3_tiger"
        and row.get("classification") == "missing_asset_reference"
    ]
    roots = ["BookmarksGit/fonts", "BookmarksGit/gfx/coat_of_arms/colored_emblems"]
    current_files = list_files(repo_root, roots)
    asil_files = list_files(asil_repo, roots)
    vanilla_files = list_files(
        vanilla_root, ["fonts", "gfx/coat_of_arms/colored_emblems"]
    )
    baseline_files = git_tree_paths(repo_root, baseline, roots)
    current_lower = {path.lower(): path for path in current_files}
    asil_lower = {path.lower(): path for path in asil_files}
    vanilla_lower = {path.lower(): path for path in vanilla_files}
    baseline_lower = {path.lower(): path for path in baseline_files}
    landed_titles = set(landed.parse_landed_titles_path(
        repo_root / "BookmarksGit/common/landed_titles"
    ))
    coat_texts = runtime.read_layer_texts(
        repo_root,
        "BookmarksGit/common/coat_of_arms/coat_of_arms",
        "current",
    )
    coat_blocks = runtime.parse_blocks(coat_texts, runtime.GENERIC_HEADER_RE)
    flat_coat_blocks = [
        block for blocks in coat_blocks.values() for block in blocks
    ]
    texture_owners: dict[str, set[str]] = defaultdict(set)
    for block in flat_coat_blocks:
        for line in block.lines:
            match = re.search(r'\btexture\s*=\s*"([^"]+)"', line)
            if match:
                texture_owners[match.group(1).lower()].add(block.key)

    def coat_owner(relative: str, line: int) -> str:
        normalized = relative.replace("\\", "/").lower()
        for block in flat_coat_blocks:
            block_path = block.path.split(":", 1)[-1].replace("\\", "/").lower()
            end_line = block.start_line + len(block.lines) - 1
            if block_path == normalized and block.start_line <= line <= end_line:
                return block.key
        return ""

    output: list[dict[str, str]] = []
    for source in source_rows:
        match = MISSING_FILE_RE.match(source.get("object", ""))
        if not match:
            continue
        target = match.group(1).replace("\\", "/")
        current_target = f"BookmarksGit/{target}".lower()
        source_path = source.get("path", "").replace("\\", "/")
        source_line = int(source.get("line") or 0)
        owner = coat_owner(source_path, source_line)
        current_source = repo_root / source_path
        current_source_text = (
            current_source.read_text(encoding="utf-8-sig", errors="replace")
            if current_source.is_file()
            else ""
        )
        baseline_source_text = git_file_text(repo_root, baseline, source_path)
        asil_source = asil_repo / source_path
        asil_source_text = (
            asil_source.read_text(encoding="utf-8-sig", errors="replace")
            if asil_source.is_file()
            else ""
        )
        vanilla_key = target.lower()
        exact_current = current_lower.get(current_target, "")
        exact_baseline = baseline_lower.get(current_target, "")
        exact_asil = asil_lower.get(current_target, "")
        exact_vanilla = vanilla_lower.get(vanilla_key, "")
        candidate_rows = nearest_asset_candidates(
            f"BookmarksGit/{target}", current_files
        )
        candidates = [row[0] for row in candidate_rows]
        strong_candidates = [
            row
            for row in candidate_rows
            if row[2] in {"same_semantic_core", "probable_spelling_variant"}
        ]
        candidate_owners = sorted({
            owner_id
            for candidate in strong_candidates
            for owner_id in texture_owners.get(Path(candidate[0]).name.lower(), set())
        })
        if exact_current:
            status = "stale_tiger_asset_finding"
            priority = "P3"
            recommendation = "refresh_tiger_report"
        elif exact_asil or exact_vanilla:
            status = "recoverable_exact_source_asset"
            priority = "P1"
            recommendation = "recover_exact_asset_after_license_and_source_review"
        elif strong_candidates:
            status = "probable_name_or_variant_mismatch"
            priority = "P1"
            recommendation = "review_candidate_asset_or_correct_reference"
        else:
            status = "missing_asset_in_all_checked_layers"
            priority = "P1"
            recommendation = "restore_asset_or_replace_reference"

        if contains_reference(baseline_source_text, target):
            provenance = "preexisting_yusseter_reference"
        elif contains_reference(asil_source_text, target):
            provenance = "shared_or_upstream_reference"
        elif contains_reference(current_source_text, target):
            provenance = "post_baseline_yusseter_reference"
        else:
            provenance = "reference_context_requires_review"
        output.append({
            "source_finding_object": source.get("object", ""),
            "target_asset": target,
            "reference_path": source_path,
            "reference_line": source.get("line", ""),
            "owner_definition": owner,
            "owner_is_active_landed_title": (
                "yes" if owner and owner in landed_titles else "no"
            ),
            "asset_status": status,
            "exact_current": exact_current,
            "exact_baseline": exact_baseline,
            "exact_asil_mod": exact_asil,
            "exact_vanilla": exact_vanilla,
            "current_name_candidates": " | ".join(candidates),
            "current_candidate_evidence": " | ".join(
                f"{path}:{score:.3f}:{relation}"
                for path, score, relation in candidate_rows
            ),
            "strong_candidate_owner_definitions": ";".join(candidate_owners),
            "reference_in_baseline": (
                "yes" if contains_reference(baseline_source_text, target) else "no"
            ),
            "reference_in_asil_mod": (
                "yes" if contains_reference(asil_source_text, target) else "no"
            ),
            "provenance": provenance,
            "recommended_priority": priority,
            "recommended_action": recommendation,
        })
    return output


def mapped_localization_rows(repo_root: Path) -> list[dict[str, str]]:
    requirements = read_csv(repo_root / INPUT_ROOT / "localization_requirements.csv")
    output: list[dict[str, str]] = []
    for row in requirements:
        if row.get("status") != "missing_effective_mapped_source_available":
            continue
        key = row.get("key", "")
        source_key = row.get("source_key", "")
        target_base = key[:-4] if key.endswith("_adj") else key
        source_base = source_key[:-4] if source_key.endswith("_adj") else source_key
        target_tier = target_base.split("_", 1)[0]
        source_tier = source_base.split("_", 1)[0]
        same_tier = target_tier == source_tier
        requirement = row.get("requirement", "")
        if requirement == "title_base":
            priority = "P1"
            confidence = "high" if same_tier else "medium"
            recommendation = "copy_verified_mapped_base_value_to_target_key"
        elif same_tier:
            priority = "P2"
            confidence = "medium"
            recommendation = "batch_candidate_after_adjective_context_review"
        else:
            priority = "P1"
            confidence = "low"
            recommendation = "manual_cross_tier_adjective_review"
        output.append({
            "target_key": key,
            "requirement": requirement,
            "source_key": source_key,
            "source_value": row.get("source_value", ""),
            "source_path": row.get("source_path", ""),
            "source_origin": row.get("source_origin", ""),
            "target_tier": target_tier,
            "source_tier": source_tier,
            "same_tier": "yes" if same_tier else "no",
            "confidence": confidence,
            "recommended_priority": priority,
            "recommended_action": recommendation,
            "cross_audit_note": "do_not_double_count_tiger_mapped_localization",
        })
    return output


def inverse_title_relations(path: Path) -> dict[str, list[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for raw_row in read_csv(path):
        row = {
            (key or "").strip(): (value or "").strip()
            for key, value in raw_row.items()
        }
        current = (row.get("source_title_id") or "").strip()
        source_values = (row.get("mod_title_id") or "").strip()
        if not current or not source_values:
            continue
        for token in re.split(r"\s*[;&]\s*", source_values):
            if token:
                result[token].add(current)
    return {key: sorted(values) for key, values in result.items()}


def effective_common_texts(
    mod_content_root: Path,
    vanilla_root: Path,
    relative_dir: str,
) -> dict[str, str]:
    mod_texts = runtime.read_layer_texts(
        mod_content_root, relative_dir, "current"
    )
    vanilla_texts = runtime.read_layer_texts(
        vanilla_root, relative_dir, "vanilla"
    )
    overridden = {
        path.split(":", 1)[1].lower()
        for path in mod_texts
    }
    effective = {
        path: text
        for path, text in vanilla_texts.items()
        if path.split(":", 1)[1].lower() not in overridden
    }
    effective.update(mod_texts)
    return effective


def collect_coa_usage(
    repo_root: Path,
    wanted: set[str],
) -> dict[str, list[str]]:
    references: dict[str, list[str]] = defaultdict(list)
    content_root = repo_root / "BookmarksGit"
    coa_definition_root = (
        content_root / "common/coat_of_arms/coat_of_arms"
    ).resolve()
    for path in sorted(content_root.rglob("*.txt")):
        resolved = path.resolve()
        inside_coa_definitions = (
            resolved == coa_definition_root
            or coa_definition_root in resolved.parents
        )
        lines = path.read_text(
            encoding="utf-8-sig", errors="replace"
        ).splitlines()
        depth = 0
        for line_number, raw in enumerate(lines, start=1):
            clean = runtime.strip_comment(raw)
            if inside_coa_definitions and depth == 0:
                alias = COA_ALIAS_RE.fullmatch(clean)
                if alias and alias.group(2) in wanted:
                    references[alias.group(2)].append(
                        f"coa_alias:{path.relative_to(repo_root).as_posix()}:"
                        f"{line_number}"
                    )
            if not inside_coa_definitions:
                assigned_values: set[str] = set()
                for match in COA_USAGE_RE.finditer(clean):
                    value = match.group(2) or match.group(3) or ""
                    assigned_values.add(value)
                    if value in wanted:
                        references[value].append(
                            f"{match.group(1)}:"
                            f"{path.relative_to(repo_root).as_posix()}:"
                            f"{line_number}"
                        )
                for value in set(COA_TOKEN_RE.findall(clean)) & wanted:
                    if value in assigned_values:
                        continue
                    references[value].append(
                        f"token:{path.relative_to(repo_root).as_posix()}:"
                        f"{line_number}"
                    )
            depth += runtime.brace_delta(raw)
    return dict(references)


def block_origin_evidence(
    current_blocks: list[runtime.Block],
    baseline_blocks: list[runtime.Block],
    asil_blocks: list[runtime.Block],
) -> str:
    baseline_remaining = Counter(
        canonical_lines(block.lines) for block in baseline_blocks
    )
    asil_remaining = Counter(
        canonical_lines(block.lines) for block in asil_blocks
    )
    output: list[str] = []
    for block in current_blocks:
        signature = canonical_lines(block.lines)
        baseline_match = baseline_remaining[signature] > 0
        asil_match = asil_remaining[signature] > 0
        if baseline_match:
            baseline_remaining[signature] -= 1
        if asil_match:
            asil_remaining[signature] -= 1
        if baseline_match and asil_match:
            origin = "baseline_and_asil"
        elif baseline_match:
            origin = "baseline_only"
        elif asil_match:
            origin = "asil_only"
        else:
            origin = "neither_snapshot"
        output.append(
            f"{block.path.split(':', 1)[-1]}:{block.start_line}={origin}"
        )
    return " | ".join(output)


def ancillary_structural_rows(
    repo_root: Path,
    asil_repo: Path,
    vanilla_root: Path,
    baseline: str,
    findings: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    output: list[dict[str, str]] = []
    landed_titles = set(landed.parse_landed_titles_path(
        repo_root / "BookmarksGit/common/landed_titles"
    ))
    mod_content_root = repo_root / "BookmarksGit"
    dynasty_blocks = runtime.parse_blocks(
        effective_common_texts(
            mod_content_root, vanilla_root, "common/dynasties"
        ),
        runtime.GENERIC_HEADER_RE,
    )
    house_blocks = runtime.parse_blocks(
        effective_common_texts(
            mod_content_root, vanilla_root, "common/dynasty_houses"
        ),
        runtime.GENERIC_HEADER_RE,
    )
    current_coa = runtime.parse_blocks(
        runtime.read_layer_texts(
            repo_root,
            "BookmarksGit/common/coat_of_arms/coat_of_arms",
            "current",
        ),
        runtime.GENERIC_HEADER_RE,
    )
    duplicated_coa_ids = {
        object_id
        for object_id, blocks in current_coa.items()
        if len(blocks) > 1
    }
    coa_usage = collect_coa_usage(repo_root, duplicated_coa_ids)
    inverse = inverse_title_relations(
        repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv"
    )

    def locations(blocks: list[runtime.Block]) -> str:
        return " | ".join(
            f"{block.path.split(':', 1)[-1]}:{block.start_line}"
            for block in blocks[:5]
        )

    def coa_identity(object_id: str, blocks: list[runtime.Block]) -> dict[str, str]:
        block_paths = {
            block.path.split(":", 1)[-1].replace("\\", "/")
            for block in blocks
        }
        if object_id == "template" and all(
            path.endswith("/93_NB_random_templates.txt")
            for path in block_paths
        ):
            return {
                "identity_namespace": "random_template_container",
                "identity_status": "valid_repeated_container_entries",
                "identity_locations": locations(blocks),
                "reference_count": "0",
                "reference_evidence": "",
                "identity_confidence": "high",
                "relation_candidates": "",
                "relation_candidate_tiers": "",
            }
        namespaces: list[str] = []
        identity_locations: list[str] = []
        if object_id in landed_titles:
            namespaces.append("landed_title")
        if object_id in dynasty_blocks:
            namespaces.append("dynasty")
            identity_locations.append(locations(dynasty_blocks[object_id]))
        if object_id in house_blocks:
            namespaces.append("dynasty_house")
            identity_locations.append(locations(house_blocks[object_id]))
        references = coa_usage.get(object_id, [])
        relation_candidates = inverse.get(object_id, [])
        if relation_candidates and not namespaces:
            namespaces.append("mapped_retired_title_key")
        if references:
            namespaces.append("explicit_reference")
        if relation_candidates and not any(
            namespace in {"landed_title", "dynasty", "dynasty_house"}
            for namespace in namespaces
        ):
            identity_status = (
                "mapped_retired_title_key_still_referenced"
                if references
                else "mapped_retired_title_coa_only"
            )
        elif namespaces:
            identity_status = "active_identity_or_reference"
        else:
            identity_status = "unreferenced_identity_candidate"
        return {
            "identity_namespace": ";".join(namespaces) or "unresolved_coa_key",
            "identity_status": identity_status,
            "identity_locations": " | ".join(identity_locations),
            "reference_count": str(len(references)),
            "reference_evidence": " | ".join(references[:5]),
            "identity_confidence": (
                "high"
                if any(
                    namespace in {"landed_title", "dynasty", "dynasty_house"}
                    for namespace in namespaces
                )
                else ("medium" if relation_candidates or references else "low")
            ),
            "relation_candidates": ";".join(relation_candidates),
            "relation_candidate_tiers": ";".join(
                candidate.split("_", 1)[0]
                for candidate in relation_candidates
            ),
        }

    def append_duplicate_family(
        family: str,
        current_dir: str,
        snapshot_dir: str,
        wanted: set[str] | None = None,
    ) -> None:
        current = runtime.parse_blocks(
            runtime.read_layer_texts(repo_root, current_dir, "current"),
            runtime.GENERIC_HEADER_RE,
            wanted,
        )
        baseline_data = runtime.parse_blocks(
            runtime.read_git_texts(repo_root, baseline, snapshot_dir, "baseline"),
            runtime.GENERIC_HEADER_RE,
            wanted,
        )
        asil = runtime.parse_blocks(
            runtime.read_layer_texts(asil_repo, current_dir, "asil_mod"),
            runtime.GENERIC_HEADER_RE,
            wanted,
        )
        for object_id, blocks in sorted(current.items()):
            if len(blocks) < 2:
                continue
            comparison = compare_duplicate_blocks(blocks)
            row = {
                "structural_family": family,
                "object": object_id,
                "status": comparison["comparison"],
                "current_locations": " | ".join(
                    f"{block.path.split(':', 1)[-1]}:{block.start_line}"
                    for block in blocks
                ),
                "conflicting_fields": comparison["conflicting_fields"],
                "conflicting_field_values": comparison[
                    "conflicting_field_values"
                ],
                "current_block_count": str(len(blocks)),
                "baseline_block_count": str(len(baseline_data.get(object_id, []))),
                "asil_mod_block_count": str(len(asil.get(object_id, []))),
                "provenance": duplicate_provenance(
                    blocks,
                    baseline_data.get(object_id, []),
                    asil.get(object_id, []),
                ),
                "current_block_origins": block_origin_evidence(
                    blocks,
                    baseline_data.get(object_id, []),
                    asil.get(object_id, []),
                ),
                "last_definition_location": (
                    f"{blocks[-1].path.split(':', 1)[-1]}:"
                    f"{blocks[-1].start_line}"
                ),
                "active_landed_title": (
                    "yes" if object_id in landed_titles else "not_applicable"
                ),
                "recommended_priority": (
                    "P1"
                    if comparison["comparison"] == "overlapping_conflicting_fields"
                    else "P2"
                ),
                "recommended_action": comparison["recommendation"],
            }
            if family == "coat_of_arms_duplicate_definition":
                identity = coa_identity(object_id, blocks)
                row.update(identity)
                if (
                    identity["identity_namespace"]
                    == "random_template_container"
                ):
                    row["status"] = "valid_repeated_container_entries"
                    row["recommended_priority"] = "P3"
                    row["recommended_action"] = "none"
                elif identity["identity_status"] == "unreferenced_identity_candidate":
                    row["recommended_priority"] = "P2"
                    row["recommended_action"] = (
                        "manual_stale_or_implicit_coa_identity_review"
                    )
                elif identity["identity_status"] == (
                    "mapped_retired_title_key_still_referenced"
                ):
                    row["recommended_priority"] = "P1"
                    row["recommended_action"] = (
                        "review_live_reference_and_coa_identity_together"
                    )
                elif identity["identity_status"] == "mapped_retired_title_coa_only":
                    row["recommended_priority"] = "P2"
                    row["recommended_action"] = (
                        "review_stale_coa_against_mapped_current_title"
                    )
            output.append(row)

    append_duplicate_family(
        "coat_of_arms_duplicate_definition",
        "BookmarksGit/common/coat_of_arms/coat_of_arms",
        "common/coat_of_arms/coat_of_arms",
    )
    append_duplicate_family(
        "geographical_region_duplicate_definition",
        "BookmarksGit/map_data/geographical_regions",
        "map_data/geographical_regions",
        {"tgp_han_region"},
    )

    brace_path = repo_root / "BookmarksGit/history/provinces/00_MB_PROVINCES.txt"
    brace_lines = brace_path.read_text(
        encoding="utf-8-sig", errors="replace"
    ).splitlines()
    depth = 0
    minimum_depth = 0
    for line in brace_lines:
        depth += runtime.brace_delta(line)
        minimum_depth = min(minimum_depth, depth)
    output.append({
        "structural_family": "tiger_brace_placement_review",
        "object": "BookmarksGit/history/provinces/00_MB_PROVINCES.txt:66717",
        "status": (
            "balanced_but_misindented_inner_closing_brace"
            if depth == 0 and minimum_depth >= 0
            else "actual_brace_imbalance"
        ),
        "current_locations": "BookmarksGit/history/provinces/00_MB_PROVINCES.txt:66717",
        "conflicting_fields": "",
        "current_block_count": "",
        "baseline_block_count": "",
        "asil_mod_block_count": "",
        "provenance": "current_state_line_signature_insufficient",
        "active_landed_title": "not_applicable",
        "recommended_priority": "P2" if depth == 0 and minimum_depth >= 0 else "P0",
        "recommended_action": (
            "normalize_indentation_only_if_touched"
            if depth == 0 and minimum_depth >= 0
            else "repair_brace_structure"
        ),
    })

    encoding_path = (
        repo_root
        / "BookmarksGit/map_data/geographical_regions/tgp_chinesenaming_regions.txt"
    )
    raw = encoding_path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    output.append({
        "structural_family": "tiger_encoding_quality_review",
        "object": encoding_path.relative_to(repo_root).as_posix(),
        "status": "utf8_bom_present" if has_bom else "utf8_bom_missing",
        "current_locations": encoding_path.relative_to(repo_root).as_posix(),
        "conflicting_fields": "",
        "current_block_count": "",
        "baseline_block_count": "",
        "asil_mod_block_count": "",
        "provenance": "current_state_encoding",
        "active_landed_title": "not_applicable",
        "recommended_priority": "P3" if has_bom else "P2",
        "recommended_action": "none" if has_bom else "normalize_utf8_bom_when_safe",
    })

    region_rows: list[dict[str, str]] = []
    for row in findings:
        if not (
            row.get("domain") == "map_regions"
            and row.get("classification") == "undefined_title_reference"
        ):
            continue
        object_id = row.get("object", "")
        candidates = inverse.get(object_id, [])
        region_rows.append({
            "undefined_title": object_id,
            "path": row.get("path", ""),
            "line": row.get("line", ""),
            "relation_candidates": ";".join(candidates),
            "candidate_count": str(len(candidates)),
            "status": (
                "single_manual_relation_candidate"
                if len(candidates) == 1
                else "ambiguous_or_missing_relation"
            ),
            "recommended_priority": "P1",
            "recommended_action": (
                "review_then_remap_region_title_reference"
                if len(candidates) == 1
                else "manual_region_identity_resolution"
            ),
        })
    return output, region_rows


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    asil_repo = args.asil_mod_repo.resolve()
    vanilla_root = args.vanilla_game_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_ROOT)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    findings = read_csv(repo_root / INPUT_ROOT / "repo_integration_closure_findings.csv")
    structural = history_duplicate_rows(
        repo_root,
        asil_repo,
        vanilla_root,
        args.baseline_revision,
        findings,
    )
    assets = missing_asset_rows(
        repo_root,
        asil_repo,
        vanilla_root,
        args.baseline_revision,
        findings,
    )
    localization = localization_duplicate_rows(
        repo_root,
        asil_repo,
        vanilla_root,
        args.baseline_revision,
        findings,
    )
    mapped = mapped_localization_rows(repo_root)
    ancillary, region_references = ancillary_structural_rows(
        repo_root,
        asil_repo,
        vanilla_root,
        args.baseline_revision,
        findings,
    )

    metadata = {
        "yusseter_revision": git_revision(repo_root),
        "current_asil_revision": git_revision(asil_repo),
        "baseline_revision": args.baseline_revision,
    }
    for dataset in (
        structural,
        assets,
        localization,
        mapped,
        ancillary,
        region_references,
    ):
        for row in dataset:
            row.update(metadata)

    write_csv(output_dir / "history_duplicate_block_audit.csv", structural)
    write_csv(output_dir / "missing_asset_reference_audit.csv", assets)
    write_csv(output_dir / "localization_duplicate_key_audit.csv", localization)
    write_csv(output_dir / "mapped_localization_candidate_audit.csv", mapped)
    write_csv(output_dir / "ancillary_structural_audit.csv", ancillary)
    write_csv(output_dir / "map_region_title_reference_audit.csv", region_references)

    structural_counts = Counter(row["comparison"] for row in structural)
    structural_source_counts = Counter(
        row["semantic_source_provenance"] for row in structural
    )
    localization_counts = Counter(row["conflict_type"] for row in localization)
    asset_counts = Counter(row["asset_status"] for row in assets)
    mapped_counts = Counter(
        f"{row['requirement']}:{row['same_tier']}" for row in mapped
    )
    ancillary_counts = Counter(row["status"] for row in ancillary)
    coa_rows = [
        row
        for row in ancillary
        if row.get("structural_family") == "coat_of_arms_duplicate_definition"
    ]
    coa_identity_counts = Counter(row["identity_status"] for row in coa_rows)
    coa_provenance_counts = Counter(row["provenance"] for row in coa_rows)
    current_revision = metadata["yusseter_revision"]
    asil_revision = metadata["current_asil_revision"]
    summary = [
        "# P1 Structural And Localization Root Audit",
        "",
        f"- Yusseter revision: `{current_revision}`",
        f"- Baseline revision: `{args.baseline_revision}`",
        f"- Current asıl mod revision: `{asil_revision}`",
        "- Live BookmarksGit source files changed: `no`",
        "",
        "## History Duplicate Blocks",
        "",
        f"- Rows: `{len(structural)}`",
    ]
    summary.extend(
        f"- {key}: `{value}`" for key, value in sorted(structural_counts.items())
    )
    summary.extend(
        f"- semantic source {key}: `{value}`"
        for key, value in sorted(structural_source_counts.items())
    )
    summary.extend([
        "",
        "## Missing Assets",
        "",
        f"- Rows: `{len(assets)}`",
    ])
    summary.extend(
        f"- {key}: `{value}`" for key, value in sorted(asset_counts.items())
    )
    summary.extend([
        "",
        "## Localization Duplicate Keys",
        "",
        f"- Closure input rows: `{len(localization)}`",
    ])
    summary.extend(
        f"- {key}: `{value}`" for key, value in sorted(localization_counts.items())
    )
    summary.extend([
        "",
        "## Mapped Localization Candidates",
        "",
        f"- Rows: `{len(mapped)}`",
    ])
    summary.extend(
        f"- {key}: `{value}`" for key, value in sorted(mapped_counts.items())
    )
    summary.extend([
        "",
        "## Ancillary Structure And Region References",
        "",
        f"- Structural rows: `{len(ancillary)}`",
        f"- Undefined map-region title rows: `{len(region_references)}`",
    ])
    summary.extend(
        f"- {key}: `{value}`" for key, value in sorted(ancillary_counts.items())
    )
    summary.extend([
        "",
        "## Coat Of Arms Identity And Provenance",
        "",
        f"- Duplicate-definition keys: {len(coa_rows)}",
    ])
    summary.extend(
        f"- identity {key}: {value}"
        for key, value in sorted(coa_identity_counts.items())
    )
    summary.extend(
        f"- provenance {key}: {value}"
        for key, value in sorted(coa_provenance_counts.items())
    )
    summary.extend([
        "",
        "## Safety",
        "",
        "- This tool only classifies existing audit findings.",
        "- No candidate is automatically applicable.",
        "- Duplicate history blocks require full timeline review before consolidation.",
        "- Localization replace precedence is evidence, not permission to discard values.",
        "",
    ])
    (output_dir / "p1_structural_localization_summary.md").write_text(
        "\n".join(summary), encoding="utf-8"
    )

    print(f"history_duplicate_rows={len(structural)}")
    print(f"missing_asset_rows={len(assets)}")
    print(f"localization_duplicate_rows={len(localization)}")
    print(f"mapped_localization_rows={len(mapped)}")
    print(f"ancillary_structural_rows={len(ancillary)}")
    print(f"map_region_title_rows={len(region_references)}")
    print(f"output_dir={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
