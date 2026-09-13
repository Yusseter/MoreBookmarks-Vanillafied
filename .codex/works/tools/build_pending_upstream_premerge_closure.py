from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
from collections import Counter
from pathlib import Path


DEFAULT_INVENTORY = Path(
    ".codex/works/analysis/generated/upstream_update_inventory/"
    "pending_live_mod_files.csv"
)
DEFAULT_DECISIONS = Path(
    ".codex/works/pipeline_inputs/upstream/pending_path_decisions.csv"
)
DEFAULT_TIGER_ROOTS = Path(
    ".codex/works/analysis/generated/tiger_upstream_delta/"
    "upstream_tiger_root_causes.csv"
)
DEFAULT_BLOCKER_FIX_CANDIDATES = Path(
    ".codex/works/analysis/generated/pending_upstream_blocker_fix_candidates/"
    "pending_upstream_blocker_fix_candidates.csv"
)
DEFAULT_BLOCKER_ROOT_RESOLUTION = Path(
    ".codex/works/analysis/generated/pending_upstream_blocker_fix_candidates/"
    "pending_upstream_blocker_root_resolution.csv"
)
DEFAULT_BLOCKER_FIX_SUMMARY = Path(
    ".codex/works/analysis/generated/pending_upstream_blocker_fix_candidates/"
    "pending_upstream_blocker_fix_candidates_summary.md"
)
DEFAULT_BLOCKER_FIX_INPUT_MANIFEST = Path(
    ".codex/works/analysis/generated/pending_upstream_blocker_fix_candidates/"
    "input_sha256_manifest.csv"
)
DEFAULT_LINEAGE_FINDINGS = Path(
    ".codex/works/analysis/generated/pending_upstream_character_lineage/"
    "pending_upstream_character_lineage_findings.csv"
)
DEFAULT_LINEAGE_DUPLICATES = Path(
    ".codex/works/analysis/generated/pending_upstream_character_lineage/"
    "pending_upstream_character_duplicate_identities.csv"
)
DEFAULT_LINEAGE_SUMMARY = Path(
    ".codex/works/analysis/generated/pending_upstream_character_lineage/"
    "pending_upstream_character_lineage_summary.md"
)
DEFAULT_LINEAGE_INPUT_MANIFEST = Path(
    ".codex/works/analysis/generated/pending_upstream_character_lineage/"
    "input_revision_manifest.csv"
)
DEFAULT_PROVINCE_AUDIT = Path(
    ".codex/works/analysis/generated/pending_upstream_semantic/"
    "ed1520220_to_66fba32c3/province_history/"
    "province_history_block_merge_audit.csv"
)
DEFAULT_TITLE_AUDIT = Path(
    ".codex/works/analysis/generated/pending_upstream_semantic/"
    "ed1520220_to_66fba32c3/title_history/"
    "title_history_upstream_delta_audit.csv"
)
DEFAULT_ENTRY_AUDIT = Path(
    ".codex/works/analysis/generated/pending_upstream_semantic/"
    "ed1520220_to_66fba32c3/title_history/"
    "title_history_entry_delta_audit.csv"
)
DEFAULT_MAP_SUMMARY = Path(
    ".codex/works/analysis/generated/upstream_map_locator_delta/"
    "upstream_map_locator_delta_summary.md"
)
DEFAULT_OUTPUT = Path(
    ".codex/works/analysis/generated/pending_upstream_premerge_closure"
)


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Build a revision-locked pending-upstream pre-merge closure report."
    )
    parser.add_argument("--repo-root", type=Path, default=root)
    parser.add_argument("--base", required=True)
    parser.add_argument("--ours", required=True)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--previous-upstream", required=True)
    parser.add_argument("--inventory-csv", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--decisions-csv", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--tiger-roots-csv", type=Path, default=DEFAULT_TIGER_ROOTS)
    parser.add_argument(
        "--blocker-fix-candidates-csv",
        type=Path,
        default=DEFAULT_BLOCKER_FIX_CANDIDATES,
    )
    parser.add_argument(
        "--blocker-root-resolution-csv",
        type=Path,
        default=DEFAULT_BLOCKER_ROOT_RESOLUTION,
    )
    parser.add_argument(
        "--blocker-fix-summary",
        type=Path,
        default=DEFAULT_BLOCKER_FIX_SUMMARY,
    )
    parser.add_argument(
        "--blocker-fix-input-manifest",
        type=Path,
        default=DEFAULT_BLOCKER_FIX_INPUT_MANIFEST,
    )
    parser.add_argument(
        "--lineage-findings-csv", type=Path, default=DEFAULT_LINEAGE_FINDINGS
    )
    parser.add_argument(
        "--lineage-duplicates-csv", type=Path, default=DEFAULT_LINEAGE_DUPLICATES
    )
    parser.add_argument("--lineage-summary", type=Path, default=DEFAULT_LINEAGE_SUMMARY)
    parser.add_argument(
        "--lineage-input-manifest",
        type=Path,
        default=DEFAULT_LINEAGE_INPUT_MANIFEST,
    )
    parser.add_argument("--province-audit-csv", type=Path, default=DEFAULT_PROVINCE_AUDIT)
    parser.add_argument("--title-audit-csv", type=Path, default=DEFAULT_TITLE_AUDIT)
    parser.add_argument("--entry-audit-csv", type=Path, default=DEFAULT_ENTRY_AUDIT)
    parser.add_argument("--map-summary", type=Path, default=DEFAULT_MAP_SUMMARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def rooted(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return result.stdout.decode("utf-8", errors="strict").strip()


def resolve_revision(root: Path, revision: str) -> str:
    return git(root, "rev-parse", f"{revision}^{{commit}}")


def blob_id(root: Path, revision: str, path: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"{revision}:{path}"],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        return ""
    return result.stdout.decode("ascii", errors="strict").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {str(key).strip(): (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, skipinitialspace=True)
        ]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def normalized_live_path(path: str) -> str:
    lowered = path.replace("\\", "/").lower()
    prefix = "bookmarksgit/"
    return lowered[len(prefix) :] if lowered.startswith(prefix) else lowered


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_tokens(path: Path, *tokens: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise RuntimeError(f"stale or incompatible evidence {path}: {missing}")


def markdown_count(path: Path, label: str) -> int:
    prefix = f"- {label}:"
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(prefix):
            return int(line[len(prefix) :].strip().strip("`"))
    raise RuntimeError(f"missing count '{label}' in {path}")


def decision_group(decision: str) -> str:
    if decision.startswith("block_"):
        return "block"
    if decision.startswith("hold_"):
        return "hold"
    if decision.startswith("manual_"):
        return "manual"
    if decision.startswith("review_"):
        return "review"
    if decision.startswith(("take_", "keep_", "entry_merge_")):
        return "planned_resolution"
    return "unclassified"


def main() -> None:
    args = parse_args()
    root = args.repo_root.resolve()
    base = resolve_revision(root, args.base)
    ours = resolve_revision(root, args.ours)
    upstream = resolve_revision(root, args.upstream)
    previous = resolve_revision(root, args.previous_upstream)

    head = resolve_revision(root, "HEAD")
    if ours != head:
        raise RuntimeError(f"ours revision must be current HEAD: ours={ours}, HEAD={head}")
    if git(root, "merge-base", ours, upstream) != base:
        raise RuntimeError("base revision is not the current ours/upstream merge-base")
    if git(root, "merge-base", previous, upstream) != previous:
        raise RuntimeError("previous upstream revision is not an ancestor of upstream")

    input_paths = {
        "inventory": rooted(root, args.inventory_csv),
        "manual_decisions": rooted(root, args.decisions_csv),
        "tiger_roots": rooted(root, args.tiger_roots_csv),
        "blocker_fix_candidates": rooted(root, args.blocker_fix_candidates_csv),
        "blocker_root_resolution": rooted(root, args.blocker_root_resolution_csv),
        "blocker_fix_summary": rooted(root, args.blocker_fix_summary),
        "blocker_fix_input_manifest": rooted(root, args.blocker_fix_input_manifest),
        "lineage_findings": rooted(root, args.lineage_findings_csv),
        "lineage_duplicates": rooted(root, args.lineage_duplicates_csv),
        "lineage_summary": rooted(root, args.lineage_summary),
        "lineage_input_manifest": rooted(root, args.lineage_input_manifest),
        "province_audit": rooted(root, args.province_audit_csv),
        "title_audit": rooted(root, args.title_audit_csv),
        "entry_audit": rooted(root, args.entry_audit_csv),
        "map_summary": rooted(root, args.map_summary),
    }
    input_paths.update(
        {
            "inventory_summary": input_paths["inventory"].with_name(
                "upstream_update_inventory_summary.md"
            ),
            "tiger_summary": input_paths["tiger_roots"].with_name(
                "upstream_tiger_delta_summary.md"
            ),
            "province_summary": input_paths["province_audit"].with_name(
                "province_history_block_merge_audit_summary.md"
            ),
            "title_summary": input_paths["title_audit"].with_name(
                "title_history_upstream_delta_summary.md"
            ),
            "entry_summary": input_paths["entry_audit"].with_name(
                "title_history_entry_delta_summary.md"
            ),
        }
    )
    missing_inputs = [str(path) for path in input_paths.values() if not path.is_file()]
    if missing_inputs:
        raise RuntimeError(f"missing inputs: {'; '.join(missing_inputs)}")

    require_tokens(input_paths["inventory_summary"], base, ours, previous, upstream)
    require_tokens(input_paths["tiger_summary"], base, upstream)
    require_tokens(
        input_paths["blocker_fix_summary"],
        base,
        upstream,
        "do_not_merge_yet",
        "8 / 8",
    )
    require_tokens(
        input_paths["lineage_summary"],
        base,
        upstream,
        "do_not_merge_yet",
        "Otomatik uygulama: hayır",
    )
    require_tokens(input_paths["province_summary"], "explicit_revisions", base, ours, upstream)
    require_tokens(input_paths["title_summary"], "explicit_revisions", base, ours, upstream)
    require_tokens(input_paths["entry_summary"], "explicit_revisions", base, ours, upstream)
    require_tokens(input_paths["map_summary"], base, ours, previous)

    inventory = read_csv(input_paths["inventory"])
    decisions = read_csv(input_paths["manual_decisions"])
    roots = read_csv(input_paths["tiger_roots"])
    blocker_fix_candidates = read_csv(input_paths["blocker_fix_candidates"])
    blocker_root_resolution = read_csv(input_paths["blocker_root_resolution"])
    lineage_rows = read_csv(input_paths["lineage_findings"])
    lineage_duplicates = read_csv(input_paths["lineage_duplicates"])
    lineage_manifest = read_csv(input_paths["lineage_input_manifest"])
    province_rows = read_csv(input_paths["province_audit"])
    title_rows = read_csv(input_paths["title_audit"])
    entry_rows = read_csv(input_paths["entry_audit"])

    inventory_by_path = {row["path"]: row for row in inventory}
    decisions_by_path = {row["path"]: row for row in decisions}
    if len(inventory_by_path) != len(inventory):
        raise RuntimeError("duplicate path in pending inventory")
    if len(decisions_by_path) != len(decisions):
        raise RuntimeError("duplicate path in manual decisions")
    if set(inventory_by_path) != set(decisions_by_path):
        missing = sorted(set(inventory_by_path) - set(decisions_by_path))
        extra = sorted(set(decisions_by_path) - set(inventory_by_path))
        raise RuntimeError(
            f"manual decision coverage mismatch; missing={missing}; extra={extra}"
        )

    actual_live_paths = {
        line.strip()
        for line in git(
            root, "diff", "--name-only", base, upstream, "--", "BookmarksGit"
        ).splitlines()
        if line.strip()
    }
    if set(inventory_by_path) != actual_live_paths:
        missing = sorted(actual_live_paths - set(inventory_by_path))
        extra = sorted(set(inventory_by_path) - actual_live_paths)
        raise RuntimeError(
            f"pending inventory differs from Git; missing={missing}; extra={extra}"
        )

    dirty_paths = {
        line.strip()
        for line in git(root, "diff", "--name-only", "HEAD").splitlines()
        if line.strip()
    }
    dirty_paths.update(
        line.strip()
        for line in git(root, "ls-files", "--others", "--exclude-standard").splitlines()
        if line.strip()
    )
    dirty_overlap = sorted(set(inventory_by_path) & dirty_paths)
    if dirty_overlap:
        raise RuntimeError(f"pending paths overlap the working tree: {dirty_overlap}")

    for row in decisions:
        if row["base_revision"] != base or row["upstream_revision"] != upstream:
            raise RuntimeError(f"stale decision revision for {row['path']}")
        if row.get("auto_apply", "").lower() != "no":
            raise RuntimeError(f"auto_apply must be no for {row['path']}")
        for field in ("decision", "confidence", "evidence", "next_action"):
            if not row.get(field):
                raise RuntimeError(f"missing {field} for {row['path']}")

    roots_by_id = {row["root_id"]: row for row in roots}
    if len(roots_by_id) != len(roots):
        raise RuntimeError("duplicate Tiger root ID")

    lineage_manifest_by_input = {
        row["input"]: row["value"] for row in lineage_manifest
    }
    if len(lineage_manifest_by_input) != len(lineage_manifest):
        raise RuntimeError("duplicate lineage manifest input")
    if lineage_manifest_by_input.get("base_revision") != base:
        raise RuntimeError("lineage base revision mismatch")
    if lineage_manifest_by_input.get("upstream_revision") != upstream:
        raise RuntimeError("lineage upstream revision mismatch")

    for row in lineage_rows:
        if row.get("auto_apply", "").lower() != "no":
            raise RuntimeError(
                f"lineage auto_apply must be no: {row.get('signature', '')}"
            )
    introduced_lineage = [
        row for row in lineage_rows if row["direction"] == "introduced"
    ]
    lineage_blocker_rows = [
        row for row in introduced_lineage if row["effective_severity"] == "blocker"
    ]
    lineage_review_rows = [
        row for row in introduced_lineage if row["effective_severity"] == "review"
    ]
    lineage_independent_rows: list[dict[str, str]] = []
    for row in introduced_lineage:
        overlap = row.get("existing_root_overlap", "")
        lineage_root = row.get("lineage_root_id", "")
        if overlap and overlap not in roots_by_id:
            raise RuntimeError(f"unknown lineage overlap root: {overlap}")
        if bool(overlap) == bool(lineage_root):
            raise RuntimeError(
                "introduced lineage row must have exactly one root source: "
                f"{row.get('signature', '')}"
            )
        if lineage_root:
            lineage_independent_rows.append(row)

    lineage_root_levels: dict[str, set[str]] = {}
    lineage_roots_by_path: dict[str, set[str]] = {}
    for row in lineage_independent_rows:
        root_id = row["lineage_root_id"]
        lineage_root_levels.setdefault(root_id, set()).add(row["effective_severity"])
        lineage_roots_by_path.setdefault(
            normalized_live_path(row["path"]), set()
        ).add(root_id)
    lineage_blocker_root_ids = {
        root_id
        for root_id, levels in lineage_root_levels.items()
        if "blocker" in levels
    }
    lineage_review_root_ids = set(lineage_root_levels) - lineage_blocker_root_ids

    for row in lineage_duplicates:
        overlap = row.get("existing_root_overlap", "")
        if row.get("auto_apply", "").lower() != "no":
            raise RuntimeError(
                f"lineage duplicate auto_apply must be no: {row.get('character_id', '')}"
            )
        if not overlap or overlap not in roots_by_id:
            raise RuntimeError(
                f"lineage duplicate lacks an existing Tiger root: {row.get('character_id', '')}"
            )
        if int(row["base_block_count"]) > 1 or int(row["upstream_block_count"]) <= 1:
            raise RuntimeError(
                f"invalid introduced duplicate counts: {row.get('character_id', '')}"
            )

    lineage_summary_path = input_paths["lineage_summary"]
    lineage_changed_ids = markdown_count(
        lineage_summary_path, "İçeriği değişen character kimliği"
    )
    expected_lineage_counts = {
        "Yeni lineage blocker satırı": len(lineage_blocker_rows),
        "Yeni lineage review": len(lineage_review_rows),
        "Yeni bağımsız lineage blocker satırı": sum(
            row["effective_severity"] == "blocker"
            for row in lineage_independent_rows
        ),
        "Yeni bağımsız lineage blocker kök ailesi": len(lineage_blocker_root_ids),
        "Yeni bağımsız yalnız-review lineage kök ailesi": len(lineage_review_root_ids),
        "Yeni duplicate character kimliği": len(lineage_duplicates),
    }
    for label, expected in expected_lineage_counts.items():
        if markdown_count(lineage_summary_path, label) != expected:
            raise RuntimeError(f"lineage summary count mismatch: {label}")

    blocker_root_ids = {
        row["root_id"] for row in roots if row["status"] == "block_merge"
    }
    candidate_counts = Counter(row["root_id"] for row in blocker_fix_candidates)
    resolution_by_root = {
        row["root_id"]: row for row in blocker_root_resolution
    }
    if len(resolution_by_root) != len(blocker_root_resolution):
        raise RuntimeError("duplicate blocker root resolution ID")
    if set(candidate_counts) != blocker_root_ids:
        raise RuntimeError(
            "blocker candidate coverage mismatch; "
            f"missing={sorted(blocker_root_ids - set(candidate_counts))}; "
            f"extra={sorted(set(candidate_counts) - blocker_root_ids)}"
        )
    if set(resolution_by_root) != blocker_root_ids:
        raise RuntimeError(
            "blocker resolution coverage mismatch; "
            f"missing={sorted(blocker_root_ids - set(resolution_by_root))}; "
            f"extra={sorted(set(resolution_by_root) - blocker_root_ids)}"
        )
    for row in blocker_fix_candidates:
        for field in (
            "candidate_id",
            "target_path",
            "candidate_class",
            "proof",
            "confidence",
            "requires_user_decision",
        ):
            if not row.get(field):
                raise RuntimeError(
                    f"missing blocker candidate {field}: {row.get('candidate_id', '')}"
                )
        if row.get("auto_apply", "").lower() != "no":
            raise RuntimeError(
                f"blocker candidate auto_apply must be no: {row['candidate_id']}"
            )
    for root_id, row in resolution_by_root.items():
        if int(row["candidate_row_count"]) != candidate_counts[root_id]:
            raise RuntimeError(f"blocker candidate count mismatch for {root_id}")
        if row.get("current_merge_gate") != "block_merge":
            raise RuntimeError(f"blocker merge gate changed for {root_id}")
        if row.get("auto_apply", "").lower() != "no":
            raise RuntimeError(f"blocker root auto_apply must be no: {root_id}")

    output_rows: list[dict[str, str]] = []
    assigned_roots: set[str] = set()
    assigned_lineage_roots: set[str] = set()
    for path, inventory_row in inventory_by_path.items():
        decision_row = decisions_by_path[path]
        live_path = normalized_live_path(path)
        natural_roots = {
            row["root_id"]
            for row in roots
            if live_path in {
                item.replace("\\", "/").lower()
                for item in split_list(row.get("affected_paths", ""))
            }
        }
        explicit_roots = set(split_list(decision_row.get("related_root_ids", "")))
        unknown_roots = sorted(explicit_roots - set(roots_by_id))
        if unknown_roots:
            raise RuntimeError(f"unknown roots for {path}: {unknown_roots}")
        related_roots = sorted(natural_roots | explicit_roots)
        assigned_roots.update(related_roots)
        related_lineage_roots = sorted(lineage_roots_by_path.get(live_path, set()))
        assigned_lineage_roots.update(related_lineage_roots)
        blocking_roots = [
            root_id
            for root_id in related_roots
            if roots_by_id[root_id]["status"] == "block_merge"
        ]
        review_roots = [
            root_id
            for root_id in related_roots
            if roots_by_id[root_id]["status"] != "block_merge"
        ]
        blocking_lineage_roots = [
            root_id
            for root_id in related_lineage_roots
            if root_id in lineage_blocker_root_ids
        ]
        review_lineage_roots = [
            root_id
            for root_id in related_lineage_roots
            if root_id in lineage_review_root_ids
        ]
        group = decision_group(decision_row["decision"])
        if blocking_roots and group != "block":
            raise RuntimeError(
                f"blocking Tiger roots require a block decision for {path}: "
                f"{blocking_roots}"
            )
        if blocking_lineage_roots and group != "block":
            raise RuntimeError(
                f"blocking lineage roots require a block decision for {path}: "
                f"{blocking_lineage_roots}"
            )
        output_rows.append(
            {
                **inventory_row,
                "decision": decision_row["decision"],
                "decision_group": group,
                "confidence": decision_row["confidence"],
                "related_root_ids": ";".join(related_roots),
                "blocking_root_ids": ";".join(blocking_roots),
                "review_root_ids": ";".join(review_roots),
                "lineage_root_ids": ";".join(related_lineage_roots),
                "lineage_blocking_root_ids": ";".join(blocking_lineage_roots),
                "lineage_review_root_ids": ";".join(review_lineage_roots),
                "evidence": decision_row["evidence"],
                "next_action": decision_row["next_action"],
                "base_blob": blob_id(root, base, path),
                "ours_blob": blob_id(root, ours, path),
                "upstream_blob": blob_id(root, upstream, path),
                "auto_apply": "no",
            }
        )

    unassigned_roots = sorted(set(roots_by_id) - assigned_roots)
    if unassigned_roots:
        raise RuntimeError(f"unassigned Tiger roots: {unassigned_roots}")
    unassigned_lineage_roots = sorted(
        set(lineage_root_levels) - assigned_lineage_roots
    )
    if unassigned_lineage_roots:
        raise RuntimeError(
            f"unassigned lineage roots: {unassigned_lineage_roots}"
        )

    manual_province_rows = [
        row for row in province_rows if row["decision"] == "manual_both_modified"
    ]
    province_ids = sorted(
        (row["province_id"] for row in manual_province_rows), key=int
    )
    title_counts = Counter(row["resolution"] for row in title_rows)
    entry_counts = Counter(row["resolution"] for row in entry_rows)

    latest_changed = {
        line.strip()
        for line in git(root, "diff", "--name-only", previous, upstream).splitlines()
        if line.strip()
    }
    map_locator_paths = {
        row["path"]
        for row in inventory
        if row["system"] in {"binary_map", "map_object_locators"}
    }
    changed_map_locator = sorted(latest_changed & map_locator_paths)
    if changed_map_locator:
        raise RuntimeError(
            "map/locator evidence is stale for latest upstream: "
            f"{changed_map_locator}"
        )

    output_dir = rooted(root, args.output_dir)
    write_csv(output_dir / "pending_upstream_path_decisions.csv", output_rows)
    manifest_rows = [
        {
            "input": name,
            "path": str(path.relative_to(root)).replace("\\", "/"),
            "size": str(path.stat().st_size),
            "sha256": sha256(path),
        }
        for name, path in input_paths.items()
    ]
    write_csv(output_dir / "input_sha256_manifest.csv", manifest_rows)

    groups = Counter(row["decision_group"] for row in output_rows)
    blocker_roots = [row for row in roots if row["status"] == "block_merge"]
    blocker_candidate_classes = Counter(
        row["candidate_class"] for row in blocker_fix_candidates
    )
    blocker_candidate_confidence = Counter(
        row["confidence"] for row in blocker_fix_candidates
    )
    user_decision_roots = sum(
        row["requires_user_decision"].lower() == "yes"
        for row in blocker_root_resolution
    )
    unresolved_groups = {"block", "hold", "manual", "review", "unclassified"}
    status = (
        "do_not_merge_yet"
        if any(groups[group] for group in unresolved_groups)
        or lineage_blocker_rows
        or lineage_duplicates
        else "ready_for_manual_merge"
    )
    lineage_overlap_blockers = sum(
        bool(row["existing_root_overlap"]) for row in lineage_blocker_rows
    )
    independent_lineage_blockers = len(lineage_blocker_rows) - lineage_overlap_blockers
    summary = [
        "# Bekleyen Asıl Mod Pre-Merge Closure",
        "",
        "## Revisionlar",
        "",
        f"- Taban: {base}",
        f"- Yusseter: {ours}",
        f"- Önceki asıl mod ucu: {previous}",
        f"- Güncel asıl mod ucu: {upstream}",
        "",
        "## Sonuç",
        "",
        f"- Merge kararı: {status}",
        f"- Kapsanan canlı dosya: {len(output_rows)} / {len(inventory)}",
        f"- Tiger kök kapsamı: {len(assigned_roots)} / {len(roots)}",
        f"- Merge engelleyici Tiger kökü: {len(blocker_roots)}",
        f"- Yeni bağımsız lineage blocker kökü: {len(lineage_blocker_root_ids)}",
        f"- Karar grupları: {', '.join(f'{key}={value}' for key, value in sorted(groups.items()))}",
        "- Otomatik uygulama: hayır",
        "- Bu rapor yalnız canlı BookmarksGit yollarını kapatır; Other/ ve error.log ayrı merge kapsamıdır.",
        "",
        "## Blocker Düzeltme Adayları",
        "",
        f"- Kök kapsamı: {len(candidate_counts)} / {len(blocker_roots)}",
        f"- Aday satırı: {len(blocker_fix_candidates)}",
        f"- Yüksek güvenli aday: {blocker_candidate_confidence['high']}",
        f"- Manuel tarihsel inceleme: {blocker_candidate_classes['manual_source_history_review']}",
        f"- Kullanıcı kararı gerektiren kök: {user_decision_roots}",
        "- Bütün adaylarda auto_apply=no; aday raporu merge izni değildir.",
        "",
        "## Character Lineage Kanıtı",
        "",
        f"- İçeriği değişen character kimliği: {lineage_changed_ids}",
        f"- Yeni lineage blocker satırı: {len(lineage_blocker_rows)}",
        f"- Mevcut Tiger köküyle örtüşen blocker satırı: {lineage_overlap_blockers}",
        f"- Yeni bağımsız lineage blocker satırı: {independent_lineage_blockers}",
        f"- Yeni bağımsız lineage blocker kökü: {len(lineage_blocker_root_ids)}",
        f"- Yeni lineage review satırı: {len(lineage_review_rows)}",
        f"- Yeni lineage review kökü: {len(lineage_review_root_ids)}",
        f"- Yeni duplicate character kimliği: {len(lineage_duplicates)}",
        "- Duplicate kimliklerin tamamı mevcut Tiger identity kökleriyle örtüşür; ayrıca blocker sayılmaz.",
        "- Bütün lineage satırlarında auto_apply=no; tarihsel kaynak kararı olmadan uygulanmaz.",
        "",
        "## History Kanıtı",
        "",
        f"- İki tarafın da değiştirdiği province ID'leri: {', '.join(province_ids) or 'yok'}",
        f"- Title-history güvenli bütün blok: {title_counts['safe_replace_whole_block'] + title_counts['safe_add_whole_block'] + title_counts['safe_delete_whole_block']}",
        f"- Title-history entry işlemi: {len(entry_rows)}",
        f"- Title-history manuel entry: {sum(value for key, value in entry_counts.items() if key.startswith('manual_'))}",
        "",
        "## Freshness",
        "",
        f"- Son upstream commitinde map/locator değişikliği: {len(changed_map_locator)}",
        f"- Bekleyen canlı yollarla çalışma ağacı çakışması: {len(dirty_overlap)}",
        "- Önceki map/locator üç-yönlü kanıtı güncel uç için path bazında geçerlidir.",
        "- Karar CSV'si revision kilitlidir; yeni upstream commitinde yeniden sınıflandırma gerekir.",
        "",
        "## Yeniden Çalıştırma",
        "",
        "Önce inventory, Tiger ve history auditlerini aynı revisionlarla yenile; ardından:",
        "",
        "```powershell",
        (
            "python .codex\\works\\tools\\build_pending_upstream_premerge_closure.py "
            f'--repo-root "{root}" --base {base} --ours {ours} '
            f"--upstream {upstream} --previous-upstream {previous}"
        ),
        "```",
        "",
        "Yeni upstream commitinde eski karar CSV'si revision kontrolünden bilinçli olarak geçmez.",
        "",
        "## Dosya Kararları",
        "",
    ]
    for row in output_rows:
        summary.append(
            f"- {row['path']}: {row['decision']} ({row['confidence']})"
        )
    summary.extend(
        [
            "",
            "Ayrıntılı kök, kanıt ve sonraki işlem bilgileri "
            "pending_upstream_path_decisions.csv dosyasındadır.",
        ]
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "pending_upstream_premerge_closure_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print(f"status: {status}")
    print(f"covered paths: {len(output_rows)}")
    print(f"covered Tiger roots: {len(assigned_roots)}")
    print(f"summary: {output_dir / 'pending_upstream_premerge_closure_summary.md'}")


if __name__ == "__main__":
    main()
