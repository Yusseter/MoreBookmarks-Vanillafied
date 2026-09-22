from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

import audit_upstream_merge_state as merge_state
import audit_upstream_title_history_delta as history_delta
import audit_upstream_title_history_merge as history_merge


DEFAULT_PREMERGE_REVISION = "09588cbb5"
DEFAULT_MERGED_SOURCE_REVISION = "74a26a897"
DEFAULT_ASIL_MOD_REPO = (
    Path(__file__).resolve().parents[2].parent / "Leviathonlx MoreBookmarks-Plus"
)
DEFAULT_VANILLA_GAME_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
)
LANDED_TITLES_PATH = "BookmarksGit/common/landed_titles/00_landed_titles.txt"
DEFINITION_PATH = "BookmarksGit/map_data/definition.csv"
TITLE_RELATION_PATH = (
    "development/pipeline_inputs/title_relations/curated_title_relations.csv"
)
PROVINCE_RELATION_PATH = (
    "development/pipeline_inputs/province_relations/"
    "province_relation_baseline.csv"
)
OUTPUT_PATH = "development/analysis/generated/repo_semantic_compatibility"
SILK_RESOLVED_REFERENCE_PLAN = (
    "development/analysis/generated/repo_integration_closure/"
    "silk_road_resolved_vanilla_east_merge/"
    "silk_road_resolved_reference_plan.csv"
)

TEXT_SUFFIXES = {".txt", ".csv", ".yml", ".gui"}
SHARED_SCAN_ROOTS = (
    "BookmarksGit/common", "BookmarksGit/events", "BookmarksGit/history",
    "BookmarksGit/map_data", "BookmarksGit/gfx/map/map_object_data", "BookmarksGit/gui",
)
MODIFIED_PROVINCE_REFERENCE_DEDICATED_PREFIXES = (
    "BookmarksGit/common/landed_titles/",
    "BookmarksGit/gfx/map/map_object_data/",
)
TITLE_TOKEN_RE = re.compile(r"\b([hekdcb]_[A-Za-z0-9_'\-]+)\b")
TITLE_HISTORY_NAME_RE = re.compile(r'\bname\s*=\s*(?:"[^"]*"|[A-Za-z0-9_\-]+)')
HOLDER_RE = re.compile(r"^\s*holder\s*=\s*([A-Za-z0-9_.\-]+)\b")
CHARACTER_HEADER_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*=\s*\{")
BLAME_HEADER_RE = re.compile(r"^([0-9a-f]{40})\s+\d+\s+(\d+)(?:\s+\d+)?$")
PROVINCE_ASSIGNMENT_RE = re.compile(r"\b(?:province|province_id)\s*=\s*(\d+)\b|\bprovince:(\d+)\b")
LOCATOR_ID_RE = re.compile(r"\bid\s*=\s*(\d+)\b")
ARROW_HEADER_RE = re.compile(r"^\s*([A-Za-z0-9_\-]+)\s*=\s*\{")
PROVINCES_BLOCK_RE = re.compile(r"^\s*provinces\s*=\s*\{")


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only repo semantic compatibility audit")
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument("--premerge", default=DEFAULT_PREMERGE_REVISION)
    parser.add_argument("--merged-source", default=DEFAULT_MERGED_SOURCE_REVISION)
    parser.add_argument(
        "--history-source-revision",
        default=None,
        help=(
            "Optional parse-safe snapshot for title-history analysis. "
            "The merged-source revision remains authoritative for provenance."
        ),
    )
    parser.add_argument("--asil-mod-repo", type=Path, default=DEFAULT_ASIL_MOD_REPO)
    parser.add_argument(
        "--vanilla-game-root", type=Path, default=DEFAULT_VANILLA_GAME_ROOT
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--max-shared-file-size", type=int, default=5_000_000)
    return parser.parse_args()


def run_git(repo_root: Path, *args: str, check: bool = True) -> bytes:
    result = subprocess.run(["git", *args], cwd=repo_root, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def git_text(repo_root: Path, *args: str) -> str:
    return run_git(repo_root, *args).decode("utf-8-sig", errors="replace")


def revision_text(repo_root: Path, revision: str, path: str) -> str:
    return run_git(repo_root, "show", f"{revision}:{path}").decode("utf-8-sig", errors="replace")


def revision_has_path(repo_root: Path, revision: str, path: str) -> bool:
    result = subprocess.run(["git", "cat-file", "-e", f"{revision}:{path}"], cwd=repo_root, check=False,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        payload = b""
        if not path.exists() or path.read_bytes() != payload:
            path.write_bytes(payload)
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")
    if not path.exists() or path.read_bytes() != payload:
        path.write_bytes(payload)


def parse_definition(text: str) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for line in normalize_text(text).splitlines():
        parts = line.strip().split(";")
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        try:
            rgb = tuple(int(value) for value in parts[1:4])
        except ValueError:
            continue
        province_id = int(parts[0])
        result[province_id] = {"id": province_id, "rgb": rgb, "rgb_text": ",".join(map(str, rgb)), "name": parts[4]}
    return result


def split_relation_tokens(value: str) -> list[str]:
    tokens = []
    for raw in re.split(r"[&;]", value):
        token = raw.replace("(second)", "").strip()
        if token and token not in {"*there_is_no*", "none"}:
            tokens.append(token)
    return tokens


def load_title_mapping(path: Path, current_ids: set[str], source_ids: set[str]):
    candidates: dict[str, set[str]] = defaultdict(set)
    issues: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for line_number, row in enumerate(csv.DictReader(handle, skipinitialspace=True), start=2):
            current = split_relation_tokens((row.get("source_title_id") or "").strip())
            source = split_relation_tokens((row.get("mod_title_id") or "").strip())
            if not current or not source:
                continue
            if len(current) == len(source):
                pairs = zip(current, source, strict=True)
            elif len(current) == 1:
                pairs = ((current[0], item) for item in source)
            elif len(source) == 1:
                pairs = ((item, source[0]) for item in current)
            else:
                issues.append({"line": str(line_number), "current_tokens": "&".join(current),
                               "source_tokens": "&".join(source), "issue": "ambiguous_relation_cardinality"})
                continue
            for current_id, source_id in pairs:
                candidates[source_id].add(current_id)
    for title_id in current_ids & source_ids:
        if title_id not in candidates:
            candidates[title_id].add(title_id)
    unique, ambiguous = {}, {}
    for source_id, raw in candidates.items():
        valid = sorted(item for item in raw if item in current_ids)
        if len(valid) == 1:
            unique[source_id] = valid[0]
        elif len(valid) > 1:
            ambiguous[source_id] = valid
    return unique, ambiguous, issues


def direct_barony_province_maps(snapshot: merge_state.Snapshot):
    by_province: dict[int, list[str]] = defaultdict(list)
    by_barony: dict[str, int] = {}
    for title_id, properties in snapshot.properties.items():
        if not title_id.startswith("b_"):
            continue
        for prop in properties.get("province", []):
            match = re.search(r"\bprovince\s*=\s*(\d+)\b", prop.raw)
            if match:
                province_id = int(match.group(1))
                by_province[province_id].append(title_id)
                by_barony.setdefault(title_id, province_id)
    return dict(by_province), by_barony


def build_landed_province_mapping(source_snapshot, current_snapshot, source_to_current_title):
    source_baronies, _ = direct_barony_province_maps(source_snapshot)
    _, current_by_barony = direct_barony_province_maps(current_snapshot)
    mapping, evidence = {}, {}
    for source_id, baronies in source_baronies.items():
        target_ids, pairs = set(), []
        for source_barony in baronies:
            current_barony = source_to_current_title.get(source_barony, source_barony if source_barony in current_by_barony else "")
            if current_barony and current_barony in current_by_barony:
                target_ids.add(current_by_barony[current_barony])
                pairs.append(f"{source_barony}->{current_barony}")
        if len(target_ids) == 1:
            mapping[source_id] = next(iter(target_ids))
            evidence[source_id] = " | ".join(pairs)
    return mapping, evidence, source_baronies


def load_province_relation(path: Path) -> dict[int, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            int(row["source_province_id"]): {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
            if (row.get("source_province_id") or "").isdigit()
        }


def same_province_semantics(source_meta, current_meta) -> bool:
    return bool(
        source_meta and current_meta
        and source_meta["rgb"] == current_meta["rgb"]
        and source_meta["name"] == current_meta["name"]
    )


def choose_province_candidate(
    source_id, source_definition, current_definition, landed_mapping,
    landed_evidence, province_relation,
):
    if source_id in landed_mapping:
        return str(landed_mapping[source_id]), "high", "landed_barony_identity", landed_evidence.get(source_id, "")
    if same_province_semantics(source_definition.get(source_id), current_definition.get(source_id)):
        return str(source_id), "high", "same_definition_semantics", ""
    relation = province_relation.get(source_id, {})
    target = relation.get("target_province_id", "")
    if target.isdigit() and relation.get("status") == "mapped":
        return target, "high", "province_relation_mapped", relation.get("notes", "")
    if target.isdigit():
        overlap = float(relation.get("overlap_score") or 0.0)
        confidence = "medium" if overlap >= 0.80 else "low"
        return target, confidence, "province_relation_top_candidate_review", relation.get("top_candidates", "")
    return "", "low", "no_semantic_mapping", ""


def parse_arrow_rows(text: str) -> list[dict[str, str]]:
    rows = []
    arrow_name, arrow_depth = "", 0
    in_provinces, provinces_depth, sequence = False, 0, 0
    for line_number, line in enumerate(normalize_text(text).splitlines(), start=1):
        clean = strip_comment(line)
        if not in_provinces and arrow_depth == 0:
            header = ARROW_HEADER_RE.match(clean)
            if header and header.group(1) != "provinces":
                arrow_name = header.group(1)
                arrow_depth = clean.count("{") - clean.count("}")
                sequence = 0
                continue
        if arrow_name and not in_provinces and PROVINCES_BLOCK_RE.match(clean):
            in_provinces = True
            provinces_depth = clean.count("{") - clean.count("}")
            continue
        if in_provinces:
            for raw_id in re.findall(r"\b\d+\b", clean):
                sequence += 1
                rows.append({"arrow": arrow_name, "line": str(line_number),
                             "sequence": str(sequence), "source_province_id": raw_id})
            provinces_depth += clean.count("{") - clean.count("}")
            if provinces_depth <= 0:
                in_provinces = False
        if arrow_name:
            arrow_depth += clean.count("{") - clean.count("}")
            if arrow_depth <= 0 and not in_provinces:
                arrow_name, arrow_depth = "", 0
    return rows


def load_silk_resolved_reference_plan(
    repo_root: Path,
) -> dict[tuple[str, str], dict[str, str]]:
    path = repo_root / SILK_RESOLVED_REFERENCE_PLAN
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {
        (row.get("candidate_arrow", ""), row.get("candidate_sequence", "")): row
        for row in rows
    }


def build_silk_road_audit(
    repo_root, source_revision, source_definition, vanilla_definition,
    current_definition,
    landed_mapping, landed_evidence, source_baronies, province_relation,
):
    relative_path = "BookmarksGit/common/connection_arrows/silk_road_arrows.txt"
    current_text = (repo_root / relative_path).read_text(encoding="utf-8-sig")
    source_text = revision_text(repo_root, source_revision, relative_path)
    exact_source_file = normalize_text(current_text) == normalize_text(source_text)
    resolved_plan = load_silk_resolved_reference_plan(repo_root)
    rows = []
    for raw in parse_arrow_rows(current_text):
        current_id = int(raw["source_province_id"])
        plan = resolved_plan.get((raw["arrow"], raw["sequence"]))
        plan_matches = bool(
            plan and plan.get("target_province_id") == str(current_id)
        )
        route_source = (
            plan.get("source", "") if plan_matches and plan else "current_asil_mod"
        )
        if route_source == "vanilla":
            source_raw = plan.get("source_province_id", "") if plan else ""
            source_id = int(source_raw) if source_raw.isdigit() else current_id
            source_meta = vanilla_definition.get(source_id)
            current_same = current_definition.get(current_id)
            target = str(current_id)
            confidence = "high"
            candidate_source = "resolved_vanilla_east_plan"
            evidence = (
                f"{plan.get('mapping_status', '')}; {plan.get('resolution', '')}"
                if plan else ""
            )
        else:
            source_id = current_id
            source_meta = source_definition.get(source_id)
            current_same = current_definition.get(current_id)
            target, confidence, candidate_source, evidence = choose_province_candidate(
                source_id, source_definition, current_definition, landed_mapping,
                landed_evidence, province_relation,
            )
        target_id = int(target) if target.isdigit() else None
        target_meta = current_definition.get(target_id) if target_id is not None else None
        semantic_drift = not same_province_semantics(source_meta, current_same)
        if source_meta is None:
            status = "invalid_source_reference"
        elif current_same is None:
            status = "missing_current_definition"
        elif route_source == "vanilla" and plan_matches:
            status = "compatible_by_resolved_vanilla_plan"
        elif not semantic_drift:
            status = "compatible"
        elif confidence == "high" and target and target != str(source_id):
            status = "requires_remap"
        elif confidence == "high" and target == str(source_id):
            status = "compatible_by_title_identity"
        else:
            status = "manual_review"
        rows.append({
            **raw, "path": relative_path,
            "current_province_id": str(current_id),
            "source_province_id": str(source_id),
            "route_source": route_source,
            "source_name": str(source_meta["name"]) if source_meta else "",
            "source_rgb": str(source_meta["rgb_text"]) if source_meta else "",
            "current_same_id_name": str(current_same["name"]) if current_same else "",
            "current_same_id_rgb": str(current_same["rgb_text"]) if current_same else "",
            "candidate_province_id": target,
            "candidate_name": str(target_meta["name"]) if target_meta else "",
            "candidate_rgb": str(target_meta["rgb_text"]) if target_meta else "",
            "source_baronies": " | ".join(source_baronies.get(source_id, [])),
            "semantic_drift": "yes" if semantic_drift else "no",
            "status": status, "confidence": confidence,
            "candidate_source": candidate_source, "evidence": evidence,
            "exact_source_file": "yes" if exact_source_file else "no",
        })
    block_rows = []
    by_arrow: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_arrow[row["arrow"]].append(row)
    for arrow, items in by_arrow.items():
        counts = Counter(item["status"] for item in items)
        compatible = (
            counts["compatible"] + counts["compatible_by_title_identity"]
            + counts["compatible_by_resolved_vanilla_plan"]
        )
        affected = any(
            item["status"] not in {
                "compatible", "compatible_by_title_identity",
                "compatible_by_resolved_vanilla_plan",
            }
            for item in items
        )
        block_rows.append({
            "arrow": arrow, "province_references": str(len(items)),
            "compatible": str(compatible), "requires_remap": str(counts["requires_remap"]),
            "manual_review": str(counts["manual_review"]),
            "invalid_or_missing": str(counts["invalid_source_reference"] + counts["missing_current_definition"]),
            "affected": "yes" if affected else "no",
        })
    return rows, block_rows


def collect_current_character_ids(
    repo_root: Path, vanilla_game_root: Path | None = None
) -> set[str]:
    result = {"0"}
    mod_directory = repo_root / "BookmarksGit/history/characters"
    mod_paths = sorted(mod_directory.rglob("*.txt")) if mod_directory.is_dir() else []
    mod_relatives = {
        path.relative_to(mod_directory).as_posix().lower() for path in mod_paths
    }
    paths = []
    if vanilla_game_root and vanilla_game_root.is_dir():
        vanilla_directory = vanilla_game_root / "history/characters"
        paths.extend(
            path for path in sorted(vanilla_directory.rglob("*.txt"))
            if path.relative_to(vanilla_directory).as_posix().lower()
            not in mod_relatives
        )
    paths.extend(mod_paths)
    for path in paths:
        depth = 0
        for line in path.read_text(
            encoding="utf-8-sig", errors="replace"
        ).splitlines():
            clean = strip_comment(line)
            if depth == 0:
                match = CHARACTER_HEADER_RE.match(clean)
                if match:
                    result.add(match.group(1))
            depth += clean.count("{") - clean.count("}")
    return result


def history_texts_working(repo_root: Path) -> dict[str, str]:
    result = {}
    directory = repo_root / "BookmarksGit/history/titles"
    for absolute in sorted(directory.rglob("*.txt")):
        path = absolute.relative_to(repo_root).as_posix()
        result[path] = absolute.read_text(encoding="utf-8-sig", errors="replace")
    return result


def history_texts_revision(repo_root: Path, revision: str) -> dict[str, str]:
    archive = run_git(
        repo_root, "archive", "--format=tar", revision,
        "BookmarksGit/history/titles",
    )
    result = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        for member in bundle.getmembers():
            if not member.isfile() or not member.name.lower().endswith(".txt"):
                continue
            handle = bundle.extractfile(member)
            if handle is not None:
                result[member.name] = handle.read().decode(
                    "utf-8-sig", errors="replace"
                )
    return result


def identity_mapper(title_id: str) -> tuple[str, str]:
    return title_id, "identity"


def block_holder_ids(block: history_merge.HistoryBlock) -> list[str]:
    holders = []
    for line in block.lines:
        match = HOLDER_RE.match(strip_comment(line))
        if match:
            holders.append(match.group(1))
    return holders


def one_block(layers, key):
    candidates = layers.get(key, [])
    return candidates[0] if len(candidates) == 1 else None


def premerge_holder_provenance(
    repo_root: Path,
    premerge_revision: str,
    source_revision: str,
    block: history_merge.HistoryBlock,
    ancestor_cache: dict[str, bool],
) -> tuple[str, list[str], int, int]:
    holder_lines = {
        block.start_line + offset
        for offset, line in enumerate(block.lines)
        if HOLDER_RE.match(strip_comment(line))
    }
    if not holder_lines:
        return "no_holder_lines", [], 0, 0

    blame = run_git(
        repo_root,
        "blame",
        "--line-porcelain",
        premerge_revision,
        "-L",
        f"{block.start_line},{block.end_line}",
        "--",
        block.path,
    ).decode("utf-8", errors="replace")
    commits_by_line: dict[int, str] = {}
    for line in blame.splitlines():
        match = BLAME_HEADER_RE.match(line)
        if match:
            commits_by_line[int(match.group(2))] = match.group(1)

    commits = sorted(
        {
            commits_by_line[line]
            for line in holder_lines
            if line in commits_by_line
        }
    )
    if not commits or any(line not in commits_by_line for line in holder_lines):
        return "unknown", commits, 0, 0

    for commit in commits:
        if commit not in ancestor_cache:
            result = subprocess.run(
                [
                    "git",
                    "merge-base",
                    "--is-ancestor",
                    commit,
                    source_revision,
                ],
                cwd=repo_root,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            ancestor_cache[commit] = result.returncode == 0
    source_ancestors = sum(ancestor_cache[commit] for commit in commits)
    non_source_ancestors = len(commits) - source_ancestors
    status = (
        "inherited_asil_mod"
        if non_source_ancestors == 0
        else "local_or_diverged"
    )
    return status, commits, source_ancestors, non_source_ancestors


def build_title_history_overwrite_audit(
    repo_root, premerge_revision, source_revision, source_to_current_title,
    vanilla_game_root=None,
):
    current = history_merge.build_snapshot("working_current", history_texts_working(repo_root), identity_mapper, {})
    premerge = history_merge.build_snapshot("premerge", history_texts_revision(repo_root, premerge_revision), identity_mapper, {})

    def source_mapper(title_id: str) -> tuple[str, str]:
        target = source_to_current_title.get(title_id, "")
        return (target, "mapped") if target else ("", "unmapped")

    source = history_merge.build_snapshot(
        "merged_source", history_texts_revision(repo_root, source_revision),
        source_mapper, source_to_current_title,
    )
    current_layers = history_delta.layered_blocks(current)
    premerge_layers = history_delta.layered_blocks(premerge)
    source_layers = history_delta.layered_blocks(source)
    character_ids = collect_current_character_ids(repo_root, vanilla_game_root)
    ancestor_cache: dict[str, bool] = {}
    rows = []
    for key in sorted(set(current_layers) & set(source_layers)):
        current_block, source_block = one_block(current_layers, key), one_block(source_layers, key)
        premerge_block = one_block(premerge_layers, key)
        if not current_block or not source_block or not premerge_block:
            continue
        if current_block.semantic_key == premerge_block.semantic_key:
            continue
        current_holders = block_holder_ids(current_block)
        premerge_holders = block_holder_ids(premerge_block)
        source_holders = block_holder_ids(source_block)
        source_semantic_match = current_block.semantic_key == source_block.semantic_key
        source_holder_match = bool(current_holders) and current_holders == source_holders
        if not source_semantic_match and not source_holder_match:
            continue
        if current_holders == premerge_holders:
            continue
        current_undefined = [item for item in current_holders if item not in character_ids]
        premerge_undefined = [item for item in premerge_holders if item not in character_ids]
        premerge_defined = [item for item in premerge_holders if item in character_ids]
        provenance = "not_evaluated"
        provenance_commits: list[str] = []
        source_ancestor_count = 0
        non_source_ancestor_count = 0
        if len(current_undefined) > len(premerge_undefined) and premerge_defined:
            (
                provenance,
                provenance_commits,
                source_ancestor_count,
                non_source_ancestor_count,
            ) = premerge_holder_provenance(
                repo_root,
                premerge_revision,
                source_revision,
                premerge_block,
                ancestor_cache,
            )
            if provenance == "local_or_diverged":
                classification, severity = "merge_regression", "blocker"
                recommendation = "restore_or_reconcile_premerge_defined_holder_chain"
            elif provenance == "inherited_asil_mod":
                classification, severity = "source_overwrite_review", "review"
                recommendation = "accept_source_evolution_track_shared_asil_mod_baseline"
            else:
                classification, severity = "source_overwrite_review", "review"
                recommendation = "verify_premerge_holder_provenance_before_apply"
        else:
            classification, severity = "source_overwrite_review", "review"
            recommendation = "compare_effective_bookmark_state_before_apply"
        rows.append({
            "current_title_id": key[0], "history_layer": key[1],
            "classification": classification, "severity": severity,
            "source_match_type": "semantic_block" if source_semantic_match else "holder_chain",
            "current_path": current_block.path, "current_line": str(current_block.start_line),
            "premerge_path": premerge_block.path, "premerge_line": str(premerge_block.start_line),
            "source_path": source_block.path, "source_line": str(source_block.start_line),
            "current_holder_count": str(len(current_holders)),
            "source_holder_count": str(len(source_holders)),
            "current_undefined_count": str(len(current_undefined)),
            "current_undefined_holders": " | ".join(current_undefined),
            "premerge_holder_count": str(len(premerge_holders)),
            "premerge_defined_count": str(len(premerge_defined)),
            "premerge_defined_holders": " | ".join(premerge_defined),
            "premerge_undefined_count": str(len(premerge_undefined)),
            "premerge_holder_provenance": provenance,
            "premerge_holder_commits": " | ".join(provenance_commits),
            "premerge_holder_source_ancestor_count": str(source_ancestor_count),
            "premerge_holder_non_source_ancestor_count": str(non_source_ancestor_count),
            "recommendation": recommendation,
        })
    return rows


def git_tree_blobs(repo_root: Path, revision: str) -> dict[str, str]:
    output = run_git(repo_root, "ls-tree", "-r", revision, "--", "BookmarksGit")
    result = {}
    for raw_line in output.decode("utf-8", errors="replace").splitlines():
        match = re.match(r"\d+\s+blob\s+([0-9a-f]+)\t(.+)", raw_line)
        if match:
            result[match.group(2)] = match.group(1)
    return result


def premerge_relation(path, source_blobs, premerge_blobs) -> str:
    if path not in premerge_blobs:
        return "added_by_merge"
    if premerge_blobs[path] == source_blobs.get(path):
        return "longstanding_source_copy"
    return "changed_or_replaced_by_merge"


def active_title_tokens(line: str, path: str) -> set[str]:
    if path.startswith("BookmarksGit/common/coat_of_arms/"):
        return set()
    clean = strip_comment(line)
    if path.startswith("BookmarksGit/history/titles/"):
        clean = TITLE_HISTORY_NAME_RE.sub("", clean)
    return set(TITLE_TOKEN_RE.findall(clean))


def active_province_ids(line: str, path: str) -> set[int]:
    ids = set()
    clean = strip_comment(line)
    for match in PROVINCE_ASSIGNMENT_RE.finditer(clean):
        raw = match.group(1) or match.group(2)
        if raw:
            ids.add(int(raw))
    normalized_path = "/" + path.replace("\\", "/")
    if "/gfx/map/map_object_data/" in normalized_path:
        ids.update(int(raw) for raw in LOCATOR_ID_RE.findall(clean))
    return ids


def build_source_shared_file_audit(
    repo_root, asil_mod_repo, premerge_revision, source_revision,
    latest_source_revision, source_to_current_title, current_title_ids,
    source_definition, current_definition, landed_mapping, landed_evidence,
    province_relation, max_file_size,
):
    source_blobs = git_tree_blobs(repo_root, source_revision)
    premerge_blobs = git_tree_blobs(repo_root, premerge_revision)
    changed_since_merge = set(
        git_text(asil_mod_repo, "diff", "--name-only", f"{source_revision}..{latest_source_revision}",
                 "--", "BookmarksGit").splitlines()
    )
    inventory, title_rows, province_rows = [], [], []
    for scan_root in SHARED_SCAN_ROOTS:
        current_dir = repo_root / scan_root
        if not current_dir.exists():
            continue
        for current_path in sorted(current_dir.rglob("*")):
            if not current_path.is_file() or current_path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if current_path.stat().st_size > max_file_size:
                continue
            relative = current_path.relative_to(repo_root).as_posix()
            if relative not in source_blobs or relative in changed_since_merge:
                continue
            source_path = asil_mod_repo / Path(relative)
            if not source_path.exists() or source_path.stat().st_size > max_file_size:
                continue
            current_text = current_path.read_text(encoding="utf-8-sig", errors="replace")
            source_text = source_path.read_text(encoding="utf-8-sig", errors="replace")
            normalized_current = normalize_text(current_text)
            normalized_source = normalize_text(source_text)
            exact_source_file = normalized_current == normalized_source
            scan_modified_province_references = exact_source_file or not any(
                relative.startswith(prefix)
                for prefix in MODIFIED_PROVINCE_REFERENCE_DEDICATED_PREFIXES
            )
            source_lines = set(normalized_source.splitlines())
            relation = premerge_relation(relative, source_blobs, premerge_blobs)
            file_title_count, file_province_count = 0, 0
            seen_title, seen_province = set(), set()
            for line_number, line in enumerate(normalized_current.splitlines(), start=1):
                if not exact_source_file and line not in source_lines:
                    continue
                clean = strip_comment(line).strip()
                if not clean:
                    continue
                for source_title in active_title_tokens(line, relative):
                    if source_title in current_title_ids:
                        continue
                    target_title = source_to_current_title.get(source_title, source_title)
                    if target_title == source_title or target_title not in current_title_ids:
                        continue
                    key = (line_number, source_title)
                    if key in seen_title:
                        continue
                    seen_title.add(key)
                    file_title_count += 1
                    title_rows.append({
                        "path": relative, "line": str(line_number),
                        "source_title_id": source_title,
                        "candidate_current_title_id": target_title,
                        "premerge_relation": relation,
                        "exact_source_file": "yes" if exact_source_file else "no",
                        "classification": "source_semantic_title_reference",
                        "severity": "review", "line_preview": clean[:300],
                        "recommendation": "verify_reference_then_remap_if_source_semantics_intended",
                    })
                province_ids = (
                    active_province_ids(line, relative)
                    if scan_modified_province_references
                    else set()
                )
                for source_id in province_ids:
                    key = (line_number, source_id)
                    if key in seen_province:
                        continue
                    seen_province.add(key)
                    source_meta, current_meta = source_definition.get(source_id), current_definition.get(source_id)
                    if same_province_semantics(source_meta, current_meta):
                        continue
                    target, confidence, candidate_source, evidence = choose_province_candidate(
                        source_id, source_definition, current_definition, landed_mapping,
                        landed_evidence, province_relation,
                    )
                    target_meta = current_definition.get(int(target)) if target.isdigit() else None
                    file_province_count += 1
                    province_rows.append({
                        "path": relative, "line": str(line_number),
                        "source_province_id": str(source_id),
                        "source_name": str(source_meta["name"]) if source_meta else "",
                        "current_same_id_name": str(current_meta["name"]) if current_meta else "",
                        "candidate_province_id": target,
                        "candidate_name": str(target_meta["name"]) if target_meta else "",
                        "confidence": confidence, "candidate_source": candidate_source,
                        "context_validation": "not_checked", "auto_apply": "no",
                        "evidence": evidence, "premerge_relation": relation,
                        "exact_source_file": "yes" if exact_source_file else "no",
                        "classification": "source_semantic_province_reference",
                        "severity": "review",
                        "line_preview": clean[:300],
                        "recommendation": "verify_reference_then_remap_to_current_province",
                    })
            if exact_source_file or file_title_count or file_province_count:
                inventory.append({
                    "path": relative, "bytes": str(current_path.stat().st_size),
                    "exact_source_file": "yes" if exact_source_file else "no",
                    "premerge_relation": relation,
                    "title_reference_candidates": str(file_title_count),
                    "province_reference_candidates": str(file_province_count),
                })
    return inventory, title_rows, province_rows


def build_upstream_delta(asil_mod_repo, merged_source_revision, latest_source_revision):
    rows = []
    for line in git_text(asil_mod_repo, "diff", "--name-status",
                         f"{merged_source_revision}..{latest_source_revision}").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append({"change": parts[0], "path": parts[-1],
                         "classification": "new_upstream_not_in_current_merge"})
    commits = [
        line for line in git_text(
            asil_mod_repo, "log", "--format=%H%x09%s",
            f"{merged_source_revision}..{latest_source_revision}",
        ).splitlines() if line.strip()
    ]
    return rows, commits


def build_combined_findings(silk_rows, history_rows, title_rows, province_rows):
    findings = []
    for row in silk_rows:
        if row["status"] in {
            "compatible", "compatible_by_title_identity",
            "compatible_by_resolved_vanilla_plan",
        }:
            continue
        classification = (
            "yusseter_integration_bug" if row["status"] == "requires_remap"
            else "needs_manual_mapping"
        )
        findings.append({
            "domain": "connection_arrows", "classification": classification,
            "severity": "blocker" if row["status"] == "requires_remap" else "review",
            "path": row["path"], "line": row["line"],
            "object": f"{row['arrow']}:{row.get('current_province_id', row['source_province_id'])}",
            "current_value": row.get("current_province_id", row["source_province_id"]),
            "candidate_value": row["candidate_province_id"],
            "confidence": row["confidence"],
            "reason": f"{row['source_name']} -> {row['current_same_id_name']}",
            "recommendation": "remap_and_validate_arrow_continuity",
        })
    for row in history_rows:
        findings.append({
            "domain": "title_history", "classification": row["classification"],
            "severity": row["severity"], "path": row["current_path"],
            "line": row["current_line"], "object": row["current_title_id"],
            "current_value": row["current_undefined_holders"],
            "candidate_value": row["premerge_defined_holders"],
            "confidence": "high" if row["classification"] == "merge_regression" else "review",
            "reason": "current block matches source and differs from pre-merge holder chain",
            "recommendation": row["recommendation"],
        })
    for row in title_rows:
        findings.append({
            "domain": "source_shared_title_reference",
            "classification": "integration_candidate", "severity": row["severity"],
            "path": row["path"], "line": row["line"],
            "object": row["source_title_id"], "current_value": row["source_title_id"],
            "candidate_value": row["candidate_current_title_id"], "confidence": "review",
            "reason": row["premerge_relation"], "recommendation": row["recommendation"],
        })
    for row in province_rows:
        findings.append({
            "domain": "source_shared_province_reference",
            "classification": "integration_candidate", "severity": row["severity"],
            "path": row["path"], "line": row["line"],
            "object": row["source_province_id"], "current_value": row["source_province_id"],
            "candidate_value": row["candidate_province_id"], "confidence": "context_unverified",
            "reason": (
                f"{row['source_name']} -> {row['current_same_id_name']}; "
                f"identity_confidence={row['confidence']}; {row['premerge_relation']}"
            ),
            "recommendation": row["recommendation"],
        })
    return findings


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    asil_mod_repo = args.asil_mod_repo.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    current_revision = git_text(repo_root, "rev-parse", "HEAD").strip()
    premerge_revision = git_text(repo_root, "rev-parse", args.premerge).strip()
    merged_source_revision = git_text(repo_root, "rev-parse", args.merged_source).strip()
    history_source_revision = git_text(
        repo_root,
        "rev-parse",
        args.history_source_revision or args.merged_source,
    ).strip()
    latest_source_revision = git_text(asil_mod_repo, "rev-parse", "HEAD").strip()

    current_landed_text = (repo_root / LANDED_TITLES_PATH).read_text(encoding="utf-8-sig", errors="replace")
    source_landed_text = revision_text(repo_root, merged_source_revision, LANDED_TITLES_PATH)
    current_landed = merge_state.build_snapshot("current", current_landed_text)
    source_landed = merge_state.build_snapshot("source", source_landed_text)
    source_to_current_title, ambiguous_titles, relation_issues = load_title_mapping(
        repo_root / TITLE_RELATION_PATH, set(current_landed.titles), set(source_landed.titles),
    )
    landed_mapping, landed_evidence, source_baronies = build_landed_province_mapping(
        source_landed, current_landed, source_to_current_title,
    )
    province_relation = load_province_relation(repo_root / PROVINCE_RELATION_PATH)
    current_definition = parse_definition(
        (repo_root / DEFINITION_PATH).read_text(encoding="utf-8-sig", errors="replace")
    )
    source_definition = parse_definition(revision_text(repo_root, merged_source_revision, DEFINITION_PATH))
    vanilla_definition = parse_definition(
        (args.vanilla_game_root.resolve() / "map_data/definition.csv").read_text(
            encoding="utf-8-sig", errors="replace"
        )
    )

    silk_rows, silk_blocks = build_silk_road_audit(
        repo_root, merged_source_revision, source_definition, vanilla_definition,
        current_definition,
        landed_mapping, landed_evidence, source_baronies, province_relation,
    )
    history_rows = build_title_history_overwrite_audit(
        repo_root, premerge_revision, history_source_revision, source_to_current_title,
        args.vanilla_game_root.resolve(),
    )
    shared_inventory, shared_title_rows, shared_province_rows = build_source_shared_file_audit(
        repo_root, asil_mod_repo, premerge_revision, merged_source_revision,
        latest_source_revision, source_to_current_title, set(current_landed.titles),
        source_definition, current_definition, landed_mapping, landed_evidence,
        province_relation, args.max_shared_file_size,
    )
    upstream_rows, upstream_commits = build_upstream_delta(
        asil_mod_repo, merged_source_revision, latest_source_revision,
    )
    findings = build_combined_findings(
        silk_rows, history_rows, shared_title_rows, shared_province_rows,
    )

    write_csv(output_dir / "repo_semantic_compatibility_findings.csv", findings)
    write_csv(output_dir / "silk_road_province_audit.csv", silk_rows)
    write_csv(output_dir / "silk_road_arrow_summary.csv", silk_blocks)
    write_csv(output_dir / "title_history_source_overwrite_candidates.csv", history_rows)
    write_csv(output_dir / "source_shared_file_inventory.csv", shared_inventory)
    write_csv(output_dir / "source_shared_title_reference_candidates.csv", shared_title_rows)
    write_csv(output_dir / "source_shared_province_reference_candidates.csv", shared_province_rows)
    write_csv(output_dir / "title_relation_parse_issues.csv", relation_issues)
    write_csv(output_dir / "ambiguous_source_title_mappings.csv", [
        {"source_title_id": source, "current_candidates": " | ".join(targets)}
        for source, targets in sorted(ambiguous_titles.items())
    ])
    write_csv(output_dir / "upstream_since_last_merge.csv", upstream_rows)

    silk_counts = Counter(row["status"] for row in silk_rows)
    history_counts = Counter(row["classification"] for row in history_rows)
    shared_counts = Counter(row["premerge_relation"] for row in shared_inventory)
    exact_shared_count = sum(row["exact_source_file"] == "yes" for row in shared_inventory)
    shared_line_candidate_files = len(shared_inventory) - exact_shared_count
    finding_counts = Counter(row["classification"] for row in findings)
    known_c_sum = next((row for row in history_rows if row["current_title_id"] == "c_SUM_riak_nan_berbedur"), None)
    summary = [
        "# Repo Semantic Compatibility Audit", "", "## Revisions", "",
        f"- current Yusseter: `{current_revision}`",
        f"- pre-merge Yusseter: `{premerge_revision}`",
        f"- last merged asıl mod: `{merged_source_revision}`",
        f"- title-history analysis source: `{history_source_revision}`",
        f"- current asıl mod: `{latest_source_revision}`",
        f"- asıl mod commits since merge: `{len(upstream_commits)}`",
        "", "## Silk Road", "",
        f"- references: `{len(silk_rows)}`",
        f"- unique source province IDs: `{len({row['source_province_id'] for row in silk_rows})}`",
        f"- exact source file: `{silk_rows[0]['exact_source_file'] if silk_rows else 'unknown'}`",
        f"- compatible: `{silk_counts['compatible'] + silk_counts['compatible_by_title_identity'] + silk_counts['compatible_by_resolved_vanilla_plan']}`",
        f"- high-confidence remap: `{silk_counts['requires_remap']}`",
        f"- manual review: `{silk_counts['manual_review']}`",
        f"- affected arrow blocks: `{sum(row['affected'] == 'yes' for row in silk_blocks)}` / `{len(silk_blocks)}`",
        "", "## Title History", "",
        f"- source-overwrite candidates: `{len(history_rows)}`",
        f"- merge regressions: `{history_counts['merge_regression']}`",
        f"- c_SUM_riak_nan_berbedur: `{known_c_sum['classification'] if known_c_sum else 'not_detected'}`",
        "", "## Exact Source-Shared Files", "",
        f"- exact shared text files: `{exact_shared_count}`",
        f"- modified files with source-shared candidate lines: `{shared_line_candidate_files}`",
        f"- longstanding copies: `{shared_counts['longstanding_source_copy']}`",
        f"- added by merge: `{shared_counts['added_by_merge']}`",
        f"- changed/replaced by merge: `{shared_counts['changed_or_replaced_by_merge']}`",
        f"- undefined mapped-title reference candidates: `{len(shared_title_rows)}`",
        f"- province semantic-drift candidates requiring context review: `{len(shared_province_rows)}`",
        "", "## Combined Findings", "",
        *[f"- {key}: `{value}`" for key, value in sorted(finding_counts.items())],
        "", "## Rules", "",
        "- merge_regression requires pre-merge holder blame outside the merged source ancestry and increased undefined holders.",
        "- inherited_asil_mod means the pre-merge holder chain was an older source revision, not a local override.",
        "- requires_remap means landed barony identity or an accepted province relation proves a different current ID.",
        "- Resolved vanilla-east plan rows are validated against vanilla provenance instead of asıl-mod same-ID semantics.",
        "- Modified landed-title and map-object locator province references remain covered by their dedicated audits.",
        "- Defined current titles, coat-of-arms definitions/textures, and title-history display names are not missing-title references.",
        "- Province candidate confidence measures identity evidence, not whether the calling effect intends that place; no candidate is auto-applied.",
        "- manual_review proves semantic drift but does not yet prove one safe target.",
        "- Candidate rows are not automatic apply instructions.",
        "", "## New Asıl-Mod Commits Not Yet Merged", "",
        *[f"- `{line}`" for line in upstream_commits], "",
    ]
    (output_dir / "repo_semantic_compatibility_summary.md").write_text("\n".join(summary), encoding="utf-8")

    print(f"output: {output_dir}")
    print(f"silk rows: {len(silk_rows)}; counts: {dict(silk_counts)}")
    print(f"history candidates: {len(history_rows)}; counts: {dict(history_counts)}")
    print(f"exact source-shared files: {exact_shared_count}")
    print(f"modified source-line candidate files: {shared_line_candidate_files}")
    print(f"shared title candidates: {len(shared_title_rows)}")
    print(f"shared province candidates: {len(shared_province_rows)}")
    print(f"combined findings: {len(findings)}")
    print(f"upstream commits since merge: {len(upstream_commits)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
