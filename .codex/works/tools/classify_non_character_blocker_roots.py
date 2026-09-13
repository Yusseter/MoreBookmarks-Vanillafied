from __future__ import annotations

import argparse
import csv
import re
import subprocess
from collections import Counter
from pathlib import Path


OUTPUT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "non_character_blocker_roots"
)
ROOT_REPORT = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "repo_integration_blocker_root_causes.csv"
)
LOCALIZATION_REQUIREMENTS = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "localization_requirements.csv"
)
LOCALIZATION_VISIBILITY = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "localization_visibility/missing_title_localization_visibility.csv"
)
LOCALIZATION_FINDINGS = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "localization_findings.csv"
)
BINARY_MAP_FINDINGS = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "map_definition_pixel_audit/binary_map_findings.csv"
)
PROVINCE_FINDINGS = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "province_history_bookmark_semantics/"
    "province_history_semantic_findings_compact.csv"
)
MPE_FINDINGS = (
    ".codex/works/analysis/generated/mpe_import_add_1/closure_audit/"
    "mpe_add_1_current_closure_findings.csv"
)
MPE_SCOPE = (
    ".codex/works/analysis/generated/mpe_import_add_1/closure_audit/"
    "mpe_add_1_current_scope.csv"
)
SILK_ROAD_MARKET_FIX_DESIGN = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "silk_road_market_closure/silk_road_market_fix_design.csv"
)
DEFAULT_ASIL_MOD_REPO = (
    Path(__file__).resolve().parents[3].parent / "Leviathonlx MoreBookmarks-Plus"
)
DEFAULT_BASELINE = "09588cbb5212a31bc4a373b6990b2c4da1203a35"
DEFAULT_MERGED_SOURCE = "ed1520220"
CHARACTER_SUBSYSTEMS = {"character_title_history", "bookmark_runtime"}
HEADER_RE = re.compile(r"^\s*([A-Za-z0-9_.'-]+)\s*=\s*\{")
ENGLISH_HEADER_RE = re.compile(r"^\s*l_english:\s*$")


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify all non-character blocker roots without applying fixes."
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument(
        "--asil-mod-repo", type=Path, default=DEFAULT_ASIL_MOD_REPO
    )
    parser.add_argument("--baseline-revision", default=DEFAULT_BASELINE)
    parser.add_argument("--merged-source-revision", default=DEFAULT_MERGED_SOURCE)
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


def first_by(
    rows: list[dict[str, str]], field: str
) -> dict[str, dict[str, str]]:
    return {
        row.get(field, ""): row
        for row in rows
        if row.get(field)
    }


def joined(values: list[str] | set[str]) -> str:
    return " | ".join(sorted({value for value in values if value}))


def find_localization_line(path: Path, key: str) -> int:
    if not path.is_file() or not key:
        return 0
    pattern = re.compile(rf"^\s*{re.escape(key)}:(?:\d+)?\s")
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig", errors="replace").splitlines(),
        start=1,
    ):
        if pattern.match(line):
            return line_number
    return 0


def find_definition(
    root: Path, relative_dir: str, key: str
) -> tuple[str, int]:
    target = root / relative_dir
    if not target.is_dir() or not key:
        return "", 0
    for path in sorted(target.rglob("*.txt")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig", errors="replace").splitlines(),
            start=1,
        ):
            match = HEADER_RE.match(line.split("#", 1)[0])
            if match and match.group(1) == key:
                return path.relative_to(root).as_posix(), line_number
    return "", 0


def classify_localization(
    root: dict[str, str],
    repo_root: Path,
    requirements: dict[str, dict[str, str]],
    visibility: dict[str, dict[str, str]],
    localization_findings: dict[str, dict[str, str]],
) -> dict[str, str]:
    key = root["primary_object"]
    classification = root["classification"]
    requirement = requirements.get(key, {})
    visible = visibility.get(key, {})
    source_path = requirement.get("source_path", "")
    source_key = requirement.get("source_key", "")
    source_line = find_localization_line(
        repo_root / source_path, source_key
    ) if source_path else 0

    if classification == "missing_effective_mapped_source_available":
        return {
            "evidence_status": "mapped_source_value_verified",
            "candidate_value": requirement.get("source_value", ""),
            "candidate_source_key": source_key,
            "candidate_source_path": source_path,
            "candidate_source_line": str(source_line or ""),
            "recovery_classification": "copy_mapped_source_localization_candidate",
            "confidence": "high",
            "reason": (
                f"the effective key is missing, while mapped source key {source_key} "
                "has an existing English value in the current mod localization"
            ),
            "recommendation": (
                "add the missing mapped key with the verified source value, then rerun "
                "localization and Tiger audits"
            ),
            "evidence_sources": joined({LOCALIZATION_REQUIREMENTS, source_path}),
        }

    if classification == "missing_english_header":
        finding = localization_findings.get(key, {})
        file_path = repo_root / finding.get("path", "")
        lines = (
            file_path.read_text(
                encoding="utf-8-sig", errors="replace"
            ).splitlines()
            if file_path.is_file() else []
        )
        header_lines = [
            index for index, line in enumerate(lines, start=1)
            if ENGLISH_HEADER_RE.match(line)
        ]
        fence_lines = [
            index for index, line in enumerate(lines, start=1)
            if line.strip().startswith("```")
        ]
        first_header = header_lines[0] if header_lines else 0
        preamble_lines = sum(
            bool(line.strip()) for line in lines[: max(first_header - 1, 0)]
        )
        return {
            "evidence_status": "corrupted_localization_preamble_verified",
            "candidate_value": "l_english:",
            "candidate_source_key": "",
            "candidate_source_path": finding.get("path", ""),
            "candidate_source_line": str(first_header or ""),
            "recovery_classification": (
                "repair_corrupted_localization_file_preamble_and_markdown_fence"
            ),
            "confidence": "high",
            "reason": (
                f"the file has {preamble_lines} non-empty preamble lines before its "
                f"l_english header and Markdown fence lines at {fence_lines}; CK3 "
                "localization cannot treat this as a valid English YAML file"
            ),
            "recommendation": (
                "remove the prose preamble and Markdown fences so l_english: is the "
                "first logical line, while preserving all localization entries"
            ),
            "evidence_sources": joined({LOCALIZATION_FINDINGS, finding.get("path", "")}),
        }

    if classification == "player_visible_de_jure_title_missing_localization":
        recovery = "author_yusseter_de_jure_title_localization"
        confidence = "high"
    elif classification == "player_visible_religious_head_title_missing_localization":
        recovery = "author_missing_religious_head_title_localization"
        confidence = "high"
    elif classification == "player_visible_landless_title_missing_localization":
        recovery = "author_missing_landless_title_localization"
        confidence = "high"
    elif classification == "potentially_creatable_titular_title_missing_localization":
        recovery = "author_or_disable_titular_title_localization"
        confidence = "medium"
    else:
        recovery = "manual_missing_localization_review"
        confidence = "medium"
    return {
        "evidence_status": "missing_in_all_effective_and_source_layers",
        "candidate_value": "",
        "candidate_source_key": "",
        "candidate_source_path": "",
        "candidate_source_line": "",
        "recovery_classification": recovery,
        "confidence": confidence,
        "reason": visible.get("reason", root.get("reason", "")),
        "recommendation": visible.get(
            "recommendation", root.get("recommendation", "")
        ),
        "evidence_sources": joined({LOCALIZATION_VISIBILITY, LOCALIZATION_REQUIREMENTS}),
    }


def classify_binary_map(
    root: dict[str, str],
    binary_rows: dict[str, dict[str, str]],
    mpe_rows: dict[str, dict[str, str]],
    mpe_scope: list[dict[str, str]],
) -> dict[str, str]:
    province_id = root["primary_object"]
    binary = binary_rows.get(province_id, {})
    mpe = mpe_rows.get(province_id, {})
    scope = next(
        (
            row for row in mpe_scope
            if province_id in {
                row.get("current_province_id", ""),
                row.get("target_ids", ""),
                row.get("existing_ids", ""),
            }
        ),
        {},
    )
    mpe_class = mpe.get("classification", "")
    if mpe_class == "superseded_province_runtime_residue":
        target = mpe.get("candidate_value", "") or scope.get("current_province_id", "")
        return {
            "evidence_status": "superseded_runtime_residue_verified",
            "candidate_value": f"remove {province_id} runtime residue; retain {target}",
            "candidate_source_key": scope.get("barony", ""),
            "candidate_source_path": mpe.get("path", ""),
            "candidate_source_line": mpe.get("line", ""),
            "recovery_classification": "remove_superseded_province_runtime_residue_candidate",
            "confidence": "high",
            "reason": (
                f"province {province_id} has no pixels or live landed owner; its barony "
                f"is active at {target}, which already has current locator data"
            ),
            "recommendation": (
                f"remove stale {province_id} locator and terrain/property entries; do "
                f"not duplicate them onto already-active province {target}"
            ),
            "evidence_sources": joined({BINARY_MAP_FINDINGS, MPE_FINDINGS, MPE_SCOPE}),
        }
    if mpe_class == "scope_excluded_province_runtime_residue":
        return {
            "evidence_status": "scope_excluded_runtime_residue_verified",
            "candidate_value": f"remove {province_id} history and locator residue",
            "candidate_source_key": scope.get("barony", ""),
            "candidate_source_path": mpe.get("path", ""),
            "candidate_source_line": mpe.get("line", ""),
            "recovery_classification": "remove_scope_excluded_province_runtime_residue_candidate",
            "confidence": "high",
            "reason": (
                f"province {province_id} belongs to intentionally excluded title "
                f"{scope.get('barony', '')}, has no map pixels, and still has history "
                "plus locator runtime content"
            ),
            "recommendation": (
                f"remove {province_id} history and six locator blocks; review the "
                "technical default.map placeholder reservation separately"
            ),
            "evidence_sources": joined({BINARY_MAP_FINDINGS, MPE_FINDINGS, MPE_SCOPE}),
        }
    return {
        "evidence_status": "missing_pixel_reference_requires_manual_resolution",
        "candidate_value": binary.get("details", ""),
        "candidate_source_key": "",
        "candidate_source_path": "",
        "candidate_source_line": "",
        "recovery_classification": "manual_binary_map_identity_review",
        "confidence": "medium",
        "reason": root.get("reason", ""),
        "recommendation": root.get("recommendation", ""),
        "evidence_sources": BINARY_MAP_FINDINGS,
    }


def classify_province_history(
    root: dict[str, str],
    repo_root: Path,
    province_rows: dict[str, dict[str, str]],
) -> dict[str, str]:
    province_id = root["primary_object"]
    finding = province_rows.get(province_id, {})
    value = finding.get("current_value", "")
    culture_path, culture_line = find_definition(
        repo_root, "BookmarksGit/common/culture/cultures", value
    )
    faith_path, faith_line = find_definition(
        repo_root, "BookmarksGit/common/religion/religions", value
    )
    if (
        root["classification"] == "undefined_religion"
        and culture_path
        and not faith_path
    ):
        return {
            "evidence_status": "religion_value_is_defined_culture_not_faith",
            "candidate_value": f"culture = {value}",
            "candidate_source_key": value,
            "candidate_source_path": culture_path,
            "candidate_source_line": str(culture_line),
            "recovery_classification": "source_field_type_typo_religion_to_culture_candidate",
            "confidence": "high",
            "reason": (
                f"{value} is defined as a culture at {culture_path}:{culture_line}, is "
                "not a faith, and neighboring dated province history uses it in the "
                "culture field; current Yusseter matches the same source typo"
            ),
            "recommendation": (
                f"change the dated assignment from religion = {value} to culture = "
                f"{value}, preserve the existing faith, then rerun province semantics "
                "and Tiger"
            ),
            "evidence_sources": joined({PROVINCE_FINDINGS, culture_path}),
        }
    return {
        "evidence_status": "undefined_history_value_verified",
        "candidate_value": "",
        "candidate_source_key": value,
        "candidate_source_path": faith_path,
        "candidate_source_line": str(faith_line or ""),
        "recovery_classification": "manual_province_history_value_review",
        "confidence": "medium",
        "reason": finding.get("reason", root.get("reason", "")),
        "recommendation": finding.get(
            "recommendation", root.get("recommendation", "")
        ),
        "evidence_sources": PROVINCE_FINDINGS,
    }


def classify_silk_road_market(
    root: dict[str, str],
    designs: dict[tuple[str, str], dict[str, str]],
) -> dict[str, str]:
    key = (root.get("classification", ""), root.get("primary_object", ""))
    design = designs.get(key, {})
    if not design:
        return {
            "evidence_status": "market_fix_design_missing",
            "candidate_value": "",
            "candidate_source_key": "",
            "candidate_source_path": "",
            "candidate_source_line": "",
            "recovery_classification": "manual_silk_road_market_blocker_review",
            "confidence": "medium",
            "reason": root.get("reason", ""),
            "recommendation": root.get("recommendation", ""),
            "evidence_sources": SILK_ROAD_MARKET_FIX_DESIGN,
        }
    recovery_by_action = {
        "replace_situation_center": "update_silk_road_market_center_candidate",
        "insert_guarded_market_history": (
            "restore_silk_road_market_history_placement_candidate"
        ),
        "repair_localization_end_quote": (
            "repair_silk_road_market_localization_quote_candidate"
        ),
    }
    return {
        "evidence_status": design.get("design_status", "reviewed_fix_design"),
        "candidate_value": design.get("proposed_value", ""),
        "candidate_source_key": design.get("action_id", ""),
        "candidate_source_path": design.get("source_path", ""),
        "candidate_source_line": design.get("source_line", ""),
        "recovery_classification": recovery_by_action.get(
            design.get("action_type", ""),
            "manual_silk_road_market_blocker_review",
        ),
        "confidence": design.get("confidence", "medium"),
        "reason": design.get("reason", root.get("reason", "")),
        "recommendation": design.get(
            "validation_after_apply", root.get("recommendation", "")
        ),
        "evidence_sources": SILK_ROAD_MARKET_FIX_DESIGN,
    }


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    roots = [
        row for row in read_csv(repo_root / ROOT_REPORT)
        if row.get("severity") == "blocker"
        and row.get("subsystem") not in CHARACTER_SUBSYSTEMS
    ]
    requirements = first_by(read_csv(repo_root / LOCALIZATION_REQUIREMENTS), "key")
    visibility = first_by(read_csv(repo_root / LOCALIZATION_VISIBILITY), "title_id")
    localization_findings = first_by(
        read_csv(repo_root / LOCALIZATION_FINDINGS), "object"
    )
    binary_rows = first_by(read_csv(repo_root / BINARY_MAP_FINDINGS), "province_id")
    province_rows = first_by(read_csv(repo_root / PROVINCE_FINDINGS), "province_id")
    mpe_rows = first_by(read_csv(repo_root / MPE_FINDINGS), "object")
    mpe_scope = read_csv(repo_root / MPE_SCOPE)
    market_designs = {
        (row.get("root_classification", ""), row.get("root_object", "")): row
        for row in read_csv(repo_root / SILK_ROAD_MARKET_FIX_DESIGN)
        if row.get("root_classification") and row.get("root_object")
    }

    yusseter_revision = git_revision(repo_root)
    current_asil_revision = git_revision(args.asil_mod_repo.resolve())
    rows: list[dict[str, str]] = []
    for root in sorted(
        roots,
        key=lambda row: (
            row.get("subsystem", ""),
            row.get("classification", ""),
            row.get("primary_object", ""),
        ),
    ):
        if root["subsystem"] == "localization":
            result = classify_localization(
                root,
                repo_root,
                requirements,
                visibility,
                localization_findings,
            )
        elif root["subsystem"] == "binary_map":
            result = classify_binary_map(root, binary_rows, mpe_rows, mpe_scope)
        elif root["subsystem"] == "province_history":
            result = classify_province_history(root, repo_root, province_rows)
        elif root["subsystem"] == "silk_road_market":
            result = classify_silk_road_market(root, market_designs)
        else:
            result = {
                "evidence_status": "unclassified_non_character_blocker",
                "candidate_value": "",
                "candidate_source_key": "",
                "candidate_source_path": "",
                "candidate_source_line": "",
                "recovery_classification": "manual_non_character_blocker_review",
                "confidence": "low",
                "reason": root.get("reason", ""),
                "recommendation": root.get("recommendation", ""),
                "evidence_sources": root.get("source_reports", ""),
            }
        rows.append({
            "root_cause_id": root["root_cause_id"],
            "subsystem": root["subsystem"],
            "primary_object": root["primary_object"],
            "root_classification": root["classification"],
            "root_provenance": root["provenance"],
            "yusseter_revision": yusseter_revision,
            "baseline_revision": args.baseline_revision,
            "merged_source_revision": args.merged_source_revision,
            "current_asil_revision": current_asil_revision,
            "raw_finding_count": root["raw_finding_count"],
            "root_paths": root.get("paths", ""),
            "root_locations": root.get("locations", ""),
            **result,
        })

    output_csv = output_dir / "non_character_blocker_root_audit.csv"
    write_csv(output_csv, rows)
    recovery_counts = Counter(row["recovery_classification"] for row in rows)
    subsystem_counts = Counter(row["subsystem"] for row in rows)
    confidence_counts = Counter(row["confidence"] for row in rows)
    summary = [
        "# Non-Character Blocker Root Audit",
        "",
        f"- roots: `{len(rows)}`",
        f"- represented raw blocker rows: `{sum(int(row['raw_finding_count']) for row in rows)}`",
        "",
        "## Subsystems",
        "",
        *[
            f"- {subsystem}: `{count}`"
            for subsystem, count in subsystem_counts.most_common()
        ],
        "",
        "## Recovery Classes",
        "",
        *[
            f"- {classification}: `{count}`"
            for classification, count in recovery_counts.most_common()
        ],
        "",
        "## Confidence",
        "",
        *[
            f"- {confidence}: `{count}`"
            for confidence, count in confidence_counts.most_common()
        ],
        "",
        "## Safety",
        "",
        "- This audit does not modify BookmarksGit source files.",
        "- Every recovery candidate remains a blocker until separately applied and validated.",
        "- Technical default.map placeholder reservations are not removed automatically.",
    ]
    (output_dir / "non_character_blocker_root_audit_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print(f"roots={len(rows)}")
    print(f"subsystems={dict(sorted(subsystem_counts.items()))}")
    print(f"recovery={dict(sorted(recovery_counts.items()))}")
    print(f"output={output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
