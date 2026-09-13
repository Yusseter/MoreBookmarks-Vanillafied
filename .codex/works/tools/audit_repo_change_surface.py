from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


DEFAULT_BASE = "09588cbb5"
DEFAULT_MERGED_SOURCE = "ed1520220"
DEFAULT_LATEST_SOURCE = "upstream/main"
OUTPUT_PATH = Path(
    ".codex/works/analysis/generated/repo_change_closure"
)
GENERATED_ROOT = ".codex/works/analysis/generated/"

TEXT_SUFFIXES = {
    ".txt",
    ".yml",
    ".yaml",
    ".csv",
    ".gui",
    ".asset",
    ".info",
    ".mod",
    ".conf",
    ".py",
    ".ps1",
    ".md",
    ".json",
    ".log",
    ".ini",
}


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit every changed file against repo closure evidence"
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--merged-source", default=DEFAULT_MERGED_SOURCE)
    parser.add_argument("--latest-source", default=DEFAULT_LATEST_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def run_git(repo_root: Path, *args: str, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def git_text(repo_root: Path, *args: str) -> str:
    return run_git(repo_root, *args).decode("utf-8", errors="replace")


def resolve_revision(repo_root: Path, revision: str) -> str:
    return git_text(repo_root, "rev-parse", revision).strip()


def parse_name_status(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1].replace("\\", "/")
        result[path] = status
    return result


def changed_paths(
    repo_root: Path,
    start: str,
    end: str,
) -> dict[str, str]:
    return parse_name_status(
        git_text(repo_root, "diff", "--name-status", "-M", f"{start}..{end}")
    )


def working_paths(repo_root: Path) -> dict[str, str]:
    return parse_name_status(
        git_text(repo_root, "diff", "--name-status", "-M", "HEAD")
    )


def untracked_paths(repo_root: Path) -> set[str]:
    raw = run_git(
        repo_root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    return {
        item.decode("utf-8", errors="replace").replace("\\", "/")
        for item in raw.split(b"\0")
        if item
    }


def tree_blobs(repo_root: Path, revision: str) -> dict[str, str]:
    raw = run_git(repo_root, "ls-tree", "-r", "-z", revision)
    result: dict[str, str] = {}
    for item in raw.split(b"\0"):
        if not item or b"\t" not in item:
            continue
        metadata, raw_path = item.split(b"\t", 1)
        fields = metadata.split()
        if len(fields) < 3:
            continue
        path = raw_path.decode("utf-8", errors="replace").replace("\\", "/")
        result[path] = fields[2].decode("ascii", errors="replace")
    return result


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def is_generated(path: str) -> bool:
    return path.startswith(GENERATED_ROOT)


def runtime_role(path: str) -> str:
    normalized = path.lower()
    if normalized.startswith(".codex/"):
        return "audit_tooling_or_evidence"
    if normalized.startswith("english/"):
        return "external_reference_not_packaged"
    if not normalized.startswith("bookmarksgit/"):
        return "project_support"
    relative = normalized.removeprefix("bookmarksgit/")
    if relative.startswith("wip/"):
        return "mod_wip_not_loaded"
    if relative.startswith("works/"):
        return "mod_internal_tooling_not_loaded"
    return "active_mod"


def subsystem(path: str) -> str:
    normalized = path.lower().replace("\\", "/")
    if normalized.startswith(".codex/"):
        return "audit_tooling"
    if normalized.startswith("english/"):
        return "external_localization_reference"
    if "/common/landed_titles/" in normalized:
        return "landed_titles"
    if "/history/titles/" in normalized:
        return "title_history"
    if "/history/provinces/" in normalized:
        return "province_history"
    if "/history/characters/" in normalized:
        return "character_history"
    if "/history/cultures/" in normalized:
        return "culture_history"
    if "/history/wars/" in normalized:
        return "war_history"
    if "/common/bookmarks/" in normalized or "/common/bookmark_portraits/" in normalized:
        return "bookmarks_and_portraits"
    if "/common/connection_arrows/" in normalized:
        return "connection_arrows"
    if "/common/situation/" in normalized:
        return "situations"
    if "/common/decisions/" in normalized:
        return "decisions"
    if "/common/events/" in normalized or "/events/" in normalized:
        return "events"
    if "/common/scripted_effects/" in normalized:
        return "scripted_effects"
    if "/common/scripted_triggers/" in normalized:
        return "scripted_triggers"
    if "/common/on_action/" in normalized:
        return "on_actions"
    if "/common/buildings/" in normalized:
        return "buildings"
    if "/common/great_projects/" in normalized:
        return "great_projects"
    if "/common/culture/" in normalized:
        return "cultures"
    if "/common/religion/" in normalized:
        return "religion"
    if "/common/governments/" in normalized:
        return "governments"
    if "/common/coat_of_arms/" in normalized:
        return "coat_of_arms"
    if "/common/ethnicities/" in normalized or "/common/dna_data/" in normalized:
        return "appearance_and_dna"
    if "/common/" in normalized:
        return "common_script_other"
    if "/localization/" in normalized:
        return "localization"
    if "/gfx/map/map_object_data/" in normalized:
        return "map_object_locators"
    if "/gfx/models/" in normalized:
        return "gfx_models"
    if "/gfx/interface/" in normalized:
        return "gfx_interface"
    if "/gfx/" in normalized:
        return "gfx_other"
    if "/map_data/geographical_regions/" in normalized:
        return "geographical_regions"
    if normalized.endswith("/map_data/definition.csv"):
        return "map_definition"
    if normalized.endswith("/map_data/provinces.png"):
        return "map_provinces_image"
    if "/map_data/" in normalized:
        return "map_data_other"
    if "/gui/" in normalized:
        return "gui"
    if "/history/" in normalized:
        return "history_other"
    if normalized.endswith("descriptor.mod"):
        return "mod_descriptor"
    if normalized.endswith("ck3-tiger.conf"):
        return "audit_config"
    if "/wip/" in normalized:
        return "wip"
    return "project_other"


def source_relation(
    path: str,
    head_tree: dict[str, str],
    merged_tree: dict[str, str],
    latest_tree: dict[str, str],
) -> str:
    head = head_tree.get(path)
    merged = merged_tree.get(path)
    latest = latest_tree.get(path)
    if head is None:
        return "absent_at_head"
    if latest is not None and head == latest:
        return "matches_latest_asil_mod"
    if merged is not None and head == merged:
        return "matches_last_merged_asil_mod"
    if merged is None and latest is None:
        return "yusseter_only"
    if latest is None:
        return "retained_after_asil_mod_removal"
    return "yusseter_diverged_from_asil_mod"


def aggregate_by_path(
    rows: Iterable[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        path = (row.get("path") or "").replace("\\", "/")
        if path:
            result[path].append(row)
    return result


def count_severity(rows: list[dict[str, str]], severity: str) -> int:
    return sum(row.get("severity") == severity for row in rows)


def count_provenance_severity(
    rows: list[dict[str, str]],
    severity: str,
    provenances: set[str],
) -> int:
    return sum(
        row.get("severity") == severity
        and row.get("provenance", "") in provenances
        for row in rows
    )


def tiger_counts(rows: list[dict[str, str]]) -> tuple[int, int, int, int]:
    current = [
        row for row in rows
        if row.get("provenance") == "yusseter_current_only"
    ]
    shared = [
        row for row in rows
        if row.get("provenance") == "shared_asil_mod_baseline"
    ]
    return (
        sum(row.get("severity") == "error" for row in current),
        sum(row.get("severity") == "warning" for row in current),
        sum(row.get("severity") == "error" for row in shared),
        sum(row.get("severity") == "warning" for row in shared),
    )


def evidence_coverage(
    path: str,
    role: str,
    suffix: str,
    closure_rows: list[dict[str, str]],
    semantic_rows: list[dict[str, str]],
    tiger_rows: list[dict[str, str]],
) -> tuple[str, str, str, str, str]:
    if role != "active_mod":
        return ("not_applicable",) * 5
    normalized = path.lower()
    tiger_applicable = suffix in {".txt", ".gui", ".yml", ".mod"}
    syntax = "fresh_tiger" if tiger_applicable else "not_covered"
    source = "covered" if semantic_rows else "partial_or_not_applicable"
    identity = "covered" if closure_rows else "no_path_finding_not_proof"
    binary = (
        "not_covered"
        if suffix in {".png", ".dds", ".mesh", ".pdn"}
        else "not_applicable"
    )
    runtime = "not_covered"
    if "/gfx/map/map_object_data/" in normalized:
        runtime = "stale_geometry_evidence"
    elif "/common/connection_arrows/" in normalized:
        runtime = "fresh_geometry_static_only"
    return syntax, identity, source, binary, runtime


def risk_and_next_check(
    path: str,
    role: str,
    system: str,
    relation: str,
    working_status: str,
    closure_actionable_blockers: int,
    closure_shared_blockers: int,
    tiger_current_errors: int,
    runtime_coverage: str,
) -> tuple[str, str, str]:
    if role != "active_mod":
        return "low", "inactive_or_tooling", "retain_as_evidence_only"
    if closure_actionable_blockers:
        return "critical", "static_blocker_evidence", "classify_and_verify_blockers"
    if tiger_current_errors:
        return "high", "current_only_tiger_error", "classify_tiger_errors_against_intent"
    if working_status:
        return "high", "uncommitted_active_change", "run_domain_specific_current_state_audit"
    if closure_shared_blockers:
        return "medium", "shared_asil_mod_blocker", "classify_as_source_baseline_or_adopt_fix"
    high_semantic = {
        "landed_titles",
        "title_history",
        "province_history",
        "character_history",
        "bookmarks_and_portraits",
        "connection_arrows",
        "situations",
        "decisions",
        "scripted_effects",
        "scripted_triggers",
        "on_actions",
        "buildings",
        "great_projects",
        "geographical_regions",
        "map_definition",
        "map_provinces_image",
        "map_object_locators",
        "governments",
    }
    if system in high_semantic and runtime_coverage in {
        "not_covered",
        "stale_geometry_evidence",
    }:
        return "high", "cross_file_or_runtime_gap", "run_functional_system_closure_audit"
    if relation == "yusseter_diverged_from_asil_mod":
        return "medium", "intentionality_not_proven", "compare_with_premerge_source_and_vanilla"
    return "medium", "static_only_evidence", "retain_for_system_level_review"


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    head_revision = resolve_revision(repo_root, "HEAD")
    base_revision = resolve_revision(repo_root, args.base)
    merged_revision = resolve_revision(repo_root, args.merged_source)
    latest_revision = resolve_revision(repo_root, args.latest_source)

    committed = changed_paths(repo_root, base_revision, head_revision)
    working = working_paths(repo_root)
    untracked = {
        path for path in untracked_paths(repo_root)
        if not is_generated(path)
    }
    pending_source = changed_paths(repo_root, merged_revision, latest_revision)

    base_tree = tree_blobs(repo_root, base_revision)
    head_tree = tree_blobs(repo_root, head_revision)
    merged_tree = tree_blobs(repo_root, merged_revision)
    latest_tree = tree_blobs(repo_root, latest_revision)

    closure_root = repo_root / ".codex/works/analysis/generated/repo_integration_closure"
    semantic_root = repo_root / ".codex/works/analysis/generated/repo_semantic_compatibility"
    closure_by_path = aggregate_by_path(
        read_csv(closure_root / "repo_integration_closure_findings.csv")
    )
    semantic_by_path = aggregate_by_path(
        read_csv(semantic_root / "repo_semantic_compatibility_findings.csv")
    )
    tiger_by_path = aggregate_by_path(
        read_csv(closure_root / "ck3_tiger_comparison.csv")
    )

    paths = sorted(set(committed) | set(working) | untracked | set(pending_source))
    inventory: list[dict[str, object]] = []
    for path in paths:
        absolute = repo_root / path
        role = runtime_role(path)
        system = subsystem(path)
        suffix = absolute.suffix.lower()
        closure_rows = closure_by_path.get(path, [])
        semantic_rows = semantic_by_path.get(path, [])
        tiger_rows = tiger_by_path.get(path, [])
        current_errors, current_warnings, shared_errors, shared_warnings = tiger_counts(
            tiger_rows
        )
        relation = source_relation(path, head_tree, merged_tree, latest_tree)
        syntax, identity, source, binary, runtime = evidence_coverage(
            path,
            role,
            suffix,
            closure_rows,
            semantic_rows,
            tiger_rows,
        )
        closure_blockers = count_severity(closure_rows, "blocker")
        closure_shared_blockers = count_provenance_severity(
            closure_rows,
            "blocker",
            {"shared_asil_mod_baseline"},
        )
        closure_actionable_blockers = count_provenance_severity(
            closure_rows,
            "blocker",
            {
                "yusseter_current_only",
                "yusseter_integration_bug",
                "yusseter_merge_regression_from_asil_mod",
                "current_state_unclassified",
            },
        )
        risk, attention, recommendation = risk_and_next_check(
            path,
            role,
            system,
            relation,
            working.get(path, "") or ("untracked" if path in untracked else ""),
            closure_actionable_blockers,
            closure_shared_blockers,
            current_errors,
            runtime,
        )
        inventory.append(
            {
                "path": path,
                "runtime_role": role,
                "subsystem": system,
                "suffix": suffix,
                "file_exists_working": "yes" if absolute.exists() else "no",
                "committed_change_status": committed.get(path, ""),
                "working_change_status": working.get(path, ""),
                "untracked": "yes" if path in untracked else "no",
                "pending_asil_mod_status": pending_source.get(path, ""),
                "present_base": "yes" if path in base_tree else "no",
                "present_head": "yes" if path in head_tree else "no",
                "present_last_merged_asil_mod": "yes" if path in merged_tree else "no",
                "present_latest_asil_mod": "yes" if path in latest_tree else "no",
                "source_relation": relation,
                "closure_blockers": closure_blockers,
                "closure_actionable_blockers": closure_actionable_blockers,
                "closure_shared_asil_mod_blockers": closure_shared_blockers,
                "closure_reviews": count_severity(closure_rows, "review"),
                "semantic_findings": len(semantic_rows),
                "tiger_current_only_errors": current_errors,
                "tiger_current_only_warnings": current_warnings,
                "tiger_shared_errors": shared_errors,
                "tiger_shared_warnings": shared_warnings,
                "syntax_schema_coverage": syntax,
                "identity_reference_coverage": identity,
                "source_provenance_coverage": source,
                "binary_integrity_coverage": binary,
                "visual_runtime_coverage": runtime,
                "risk": risk,
                "attention_class": attention,
                "recommendation": recommendation,
            }
        )

    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in inventory:
        groups[(str(row["runtime_role"]), str(row["subsystem"]))].append(row)

    summary_rows: list[dict[str, object]] = []
    for (role, system), rows in sorted(groups.items()):
        risk_counts = Counter(str(row["risk"]) for row in rows)
        summary_rows.append(
            {
                "runtime_role": role,
                "subsystem": system,
                "changed_file_count": len(rows),
                "committed_file_count": sum(bool(row["committed_change_status"]) for row in rows),
                "working_file_count": sum(bool(row["working_change_status"]) for row in rows),
                "untracked_file_count": sum(row["untracked"] == "yes" for row in rows),
                "pending_asil_mod_file_count": sum(bool(row["pending_asil_mod_status"]) for row in rows),
                "yusseter_diverged_file_count": sum(row["source_relation"] == "yusseter_diverged_from_asil_mod" for row in rows),
                "closure_blockers": sum(int(row["closure_blockers"]) for row in rows),
                "closure_actionable_blockers": sum(int(row["closure_actionable_blockers"]) for row in rows),
                "closure_shared_asil_mod_blockers": sum(int(row["closure_shared_asil_mod_blockers"]) for row in rows),
                "closure_reviews": sum(int(row["closure_reviews"]) for row in rows),
                "tiger_current_only_errors": sum(int(row["tiger_current_only_errors"]) for row in rows),
                "tiger_current_only_warnings": sum(int(row["tiger_current_only_warnings"]) for row in rows),
                "critical_files": risk_counts["critical"],
                "high_risk_files": risk_counts["high"],
                "medium_risk_files": risk_counts["medium"],
                "low_risk_files": risk_counts["low"],
                "static_coverage": "present" if any(row["syntax_schema_coverage"] == "fresh_tiger" for row in rows) else "partial_or_not_applicable",
                "runtime_coverage": "missing_or_partial" if any(row["visual_runtime_coverage"] in {"not_covered", "stale_geometry_evidence"} for row in rows) else "not_applicable_or_static_only",
            }
        )

    attention_rows = [
        row for row in inventory
        if row["runtime_role"] == "active_mod"
        and row["risk"] in {"critical", "high"}
    ]
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    attention_rows.sort(
        key=lambda row: (
            risk_order[str(row["risk"])],
            -int(row["closure_actionable_blockers"]),
            -int(row["tiger_current_only_errors"]),
            str(row["path"]),
        )
    )

    write_csv(output_dir / "repo_change_surface_inventory.csv", inventory)
    write_csv(output_dir / "repo_change_surface_by_subsystem.csv", summary_rows)
    write_csv(output_dir / "repo_change_surface_attention.csv", attention_rows)

    role_counts = Counter(str(row["runtime_role"]) for row in inventory)
    risk_counts = Counter(str(row["risk"]) for row in inventory)
    attention_counts = Counter(str(row["attention_class"]) for row in inventory)
    active_rows = [row for row in inventory if row["runtime_role"] == "active_mod"]
    lines = [
        "# Repo Change Surface Audit",
        "",
        "## Revisions",
        "",
        f"- base Yusseter: `{base_revision}`",
        f"- current HEAD: `{head_revision}`",
        f"- last merged asıl mod: `{merged_revision}`",
        f"- latest known asıl mod: `{latest_revision}`",
        "",
        "## Inventory",
        "",
        f"- total paths in change universe: `{len(inventory)}`",
        f"- committed paths: `{len(committed)}`",
        f"- tracked working paths: `{len(working)}`",
        f"- untracked paths: `{len(untracked)}`",
        f"- pending asıl-mod paths: `{len(pending_source)}`",
        f"- active mod paths: `{len(active_rows)}`",
        "",
        "### Runtime Roles",
        "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(role_counts.items())],
        "",
        "### Risk",
        "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(risk_counts.items())],
        "",
        "### Attention Classes",
        "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(attention_counts.items())],
        "",
        "## Evidence Totals For Active Changed Files",
        "",
        f"- closure blockers: `{sum(int(row['closure_blockers']) for row in active_rows)}`",
        f"- actionable Yusseter/integration blockers: `{sum(int(row['closure_actionable_blockers']) for row in active_rows)}`",
        f"- shared asıl-mod blockers: `{sum(int(row['closure_shared_asil_mod_blockers']) for row in active_rows)}`",
        f"- closure reviews: `{sum(int(row['closure_reviews']) for row in active_rows)}`",
        f"- Tiger current-only errors: `{sum(int(row['tiger_current_only_errors']) for row in active_rows)}`",
        f"- Tiger current-only warnings: `{sum(int(row['tiger_current_only_warnings']) for row in active_rows)}`",
        "",
        "## Interpretation",
        "",
        "- This report inventories every path changed since the selected base, every tracked working-tree change, every untracked path, and every latest-source delta.",
        "- A Tiger report is evidence, not an automatic defect classification.",
        "- No-path-finding is not treated as proof that a domain-specific semantic check ran.",
        "- Visual and bookmark-runtime coverage remain separate gates.",
        "- No live BookmarksGit source file is modified by this audit.",
    ]
    (output_dir / "repo_change_surface_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(f"output: {output_dir}")
    print(f"change universe: {len(inventory)}")
    print(f"active mod paths: {len(active_rows)}")
    print(f"risk: {dict(risk_counts)}")
    print(f"attention: {dict(attention_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
