from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import audit_landed_title_source_identity as landed
import classify_ck3_tiger_current_only as tiger


GET_TITLE_RE = re.compile(
    r"GetTitleByKey\(\s*['\"]([ekdcbh]_[A-Za-z0-9_]+)['\"]\s*\)"
)
LOC_KEY_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+):")
TEXT_SUFFIXES = {".txt", ".gui", ".yml"}
OUTPUT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "dynamic_title_references"
)
DEFAULT_VANILLA_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit dynamic localization title references against current landed titles."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
    )
    parser.add_argument(
        "--asil-mod-root",
        type=Path,
        default=tiger.DEFAULT_ASIL_MOD_ROOT,
    )
    parser.add_argument(
        "--vanilla-root",
        type=Path,
        default=DEFAULT_VANILLA_ROOT,
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--premerge-revision",
        default=tiger.DEFAULT_PREMERGE_REVISION,
    )
    return parser.parse_args()


def dependency_context(relative: str) -> str:
    name = Path(relative).name.lower()
    if name.startswith("rice_"):
        return "external_rice_compatibility"
    return "native_mod_localization"


def consumer_token(localization_key: str) -> str:
    if ".preview." in localization_key:
        return localization_key.split(".preview.", 1)[0]
    for suffix in (".desc", ".t", ".a"):
        if localization_key.endswith(suffix):
            return localization_key[: -len(suffix)]
    return localization_key


def load_non_localization_text(repo_root: Path) -> str:
    mod_root = repo_root / "BookmarksGit"
    chunks = []
    for path in mod_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if "localization" in {part.lower() for part in path.parts}:
            continue
        chunks.append(path.read_text(encoding="utf-8-sig", errors="replace"))
    return "\n".join(chunks)


def build_hierarchy_candidates(
    current_blocks: dict[str, landed.TitleBlock],
    source_blocks: list[tuple[str, dict[str, landed.TitleBlock]]],
    seed_candidates: dict[str, set[str]],
) -> tuple[dict[str, set[str]], dict[tuple[str, str], list[str]]]:
    current_parent = {
        title_id: block.parent_id for title_id, block in current_blocks.items()
    }
    candidates: dict[str, set[str]] = defaultdict(set)
    evidence: dict[tuple[str, str], list[str]] = defaultdict(list)
    for source_id, values in seed_candidates.items():
        candidates[source_id].update(values)

    changed = True
    while changed:
        changed = False
        for origin, blocks in source_blocks:
            children: dict[str, list[str]] = defaultdict(list)
            for source_id, block in blocks.items():
                if block.parent_id:
                    children[block.parent_id].append(source_id)
            for source_parent, child_ids in children.items():
                target_tier = tiger.tier(source_parent)
                for child_id in child_ids:
                    for child_candidate in candidates.get(child_id, set()):
                        ancestor = tiger.ancestor_at_tier(
                            child_candidate,
                            target_tier,
                            current_parent,
                        )
                        if not ancestor or ancestor in candidates[source_parent]:
                            continue
                        candidates[source_parent].add(ancestor)
                        evidence[(source_parent, ancestor)].append(
                            f"{origin}_child:{child_id}->{child_candidate}"
                        )
                        changed = True
    return candidates, evidence


def scan_dynamic_references(repo_root: Path) -> list[dict[str, str]]:
    localization_root = repo_root / "BookmarksGit/localization"
    rows = []
    for path in sorted(localization_root.rglob("*_l_english.yml")):
        relative = path.relative_to(repo_root).as_posix()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig", errors="replace").splitlines(),
            start=1,
        ):
            title_matches = list(GET_TITLE_RE.finditer(line))
            if not title_matches:
                continue
            key_match = LOC_KEY_RE.match(line)
            localization_key = key_match.group(1) if key_match else ""
            for match in title_matches:
                rows.append(
                    {
                        "path": relative,
                        "line": str(line_number),
                        "localization_key": localization_key,
                        "title_id": match.group(1),
                        "dependency_context": dependency_context(relative),
                        "line_preview": line.strip()[:1000],
                    }
                )
    return rows


def resolve_reference(
    row: dict[str, str],
    current_ids: set[str],
    relation: dict[str, set[str]],
    identity_direct: dict[str, set[str]],
    identity_parent: dict[str, set[str]],
    identity_evidence: dict[tuple[str, str], list[str]],
    hierarchy_candidates: dict[str, set[str]],
    hierarchy_evidence: dict[tuple[str, str], list[str]],
    no_counterpart: set[str],
    consumer_count: int,
) -> tuple[str, str, str, str, str, str]:
    title_id = row["title_id"]
    if title_id in current_ids:
        return (
            "current_title_reference",
            title_id,
            "defined_in_current_landed_titles",
            "high",
            "no_action",
            "info",
        )

    pseudo_tiger_row = {
        "path": row["path"],
        "line": row["line"],
    }
    classification, candidate, evidence, confidence, recommendation = tiger.title_resolution(
        pseudo_tiger_row,
        title_id,
        {},
        relation,
        identity_direct,
        identity_parent,
        identity_evidence,
        no_counterpart,
    )
    if classification == "unresolved_missing_title_reference":
        propagated = hierarchy_candidates.get(title_id, set())
        if len(propagated) == 1:
            candidate = next(iter(propagated))
            classification = "hierarchy_derived_dynamic_title_candidate"
            evidence = " | ".join(
                hierarchy_evidence.get((title_id, candidate), [])[:12]
            )
            confidence = "medium_context_review"
            recommendation = "verify_dynamic_text_semantics_then_remap"
        elif len(propagated) > 1:
            candidate = " | ".join(sorted(propagated))
            classification = "split_dynamic_title_reference_review"
            evidence = " | ".join(
                item
                for value in sorted(propagated)
                for item in hierarchy_evidence.get((title_id, value), [])[:6]
            )
            confidence = "high_context_review"
            recommendation = "rewrite_text_for_current_split_hierarchy"

    external = row["dependency_context"] != "native_mod_localization"
    if classification != "unresolved_missing_title_reference":
        if external:
            classification = "external_compatibility_title_remap_candidate"
        severity = "review"
        return (
            classification,
            candidate,
            evidence,
            confidence,
            recommendation,
            severity,
        )
    if external:
        return (
            "external_dependency_title_reference_review",
            "",
            "title_may_be_created_or_defined_by_external_dependency",
            "low",
            "verify_with_external_mod_stack",
            "review",
        )
    if consumer_count == 0:
        return (
            "stale_unreferenced_localization_title_reference",
            "",
            "no_non_localization_consumer_found",
            "medium",
            "remove_or_update_stale_localization_after_manual_review",
            "review",
        )
    return (
        "unresolved_dynamic_title_reference",
        "",
        f"non_localization_consumer_occurrences={consumer_count}",
        "high",
        "derive_current_title_mapping_or_redesign_consumer",
        "blocker",
    )


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)
    asil_mod_root = args.asil_mod_root.resolve()
    vanilla_root = args.vanilla_root.resolve()

    current_blocks = landed.parse_landed_titles_path(
        repo_root / "BookmarksGit/common/landed_titles"
    )
    asil_blocks = landed.parse_landed_titles_path(
        asil_mod_root / "BookmarksGit/common/landed_titles"
    )
    vanilla_blocks = landed.parse_landed_titles_path(
        vanilla_root / "common/landed_titles"
    )
    current_ids = set(current_blocks)

    identity_rows = tiger.read_csv(repo_root / tiger.IDENTITY_PATH)
    relation_rows = tiger.read_csv(repo_root / tiger.RELATION_PATH)
    relation, no_counterpart = tiger.build_relation_maps(
        relation_rows,
        current_ids,
    )
    identity_direct, identity_parent, identity_evidence = tiger.build_identity_maps(
        identity_rows,
        current_ids,
    )
    seed_candidates: dict[str, set[str]] = defaultdict(set)
    for mapping in (relation, identity_direct, identity_parent):
        for source_id, candidates in mapping.items():
            seed_candidates[source_id].update(candidates)
    hierarchy_candidates, hierarchy_evidence = build_hierarchy_candidates(
        current_blocks,
        [
            ("asil_mod", asil_blocks),
            ("vanilla", vanilla_blocks),
        ],
        seed_candidates,
    )

    non_localization_text = load_non_localization_text(repo_root)
    line_provenance = tiger.build_line_provenance(
        repo_root,
        asil_mod_root,
        args.premerge_revision,
    )
    inventory = []
    for row in scan_dynamic_references(repo_root):
        token = consumer_token(row["localization_key"])
        consumer_count = non_localization_text.count(token) if token else 0
        (
            classification,
            candidate,
            evidence,
            confidence,
            recommendation,
            severity,
        ) = resolve_reference(
            row,
            current_ids,
            relation,
            identity_direct,
            identity_parent,
            identity_evidence,
            hierarchy_candidates,
            hierarchy_evidence,
            no_counterpart,
            consumer_count,
        )
        provenance, premerge_count, asil_count = line_provenance(
            row["path"],
            row["line_preview"],
        )
        inventory.append(
            {
                **row,
                "consumer_token": token,
                "non_localization_consumer_occurrences": str(consumer_count),
                "classification": classification,
                "severity": severity,
                "candidate_titles": candidate,
                "evidence": evidence,
                "confidence": confidence,
                "recommendation": recommendation,
                "line_provenance": provenance,
                "premerge_exact_line_occurrences": premerge_count,
                "asil_mod_exact_line_occurrences": asil_count,
            }
        )

    fields = [
        "path",
        "line",
        "localization_key",
        "title_id",
        "dependency_context",
        "consumer_token",
        "non_localization_consumer_occurrences",
        "classification",
        "severity",
        "candidate_titles",
        "evidence",
        "confidence",
        "recommendation",
        "line_provenance",
        "premerge_exact_line_occurrences",
        "asil_mod_exact_line_occurrences",
        "line_preview",
    ]
    findings = [
        row
        for row in inventory
        if row["classification"] != "current_title_reference"
    ]
    tiger.write_csv(
        output_dir / "dynamic_title_reference_inventory.csv",
        inventory,
        fields,
    )
    tiger.write_csv(
        output_dir / "dynamic_title_reference_findings.csv",
        findings,
        fields,
    )

    class_counts = Counter(row["classification"] for row in findings)
    severity_counts = Counter(row["severity"] for row in findings)
    lines = [
        "# Dynamic Localization Title Reference Audit",
        "",
        f"- scanned references: `{len(inventory)}`",
        f"- undefined current title references: `{len(findings)}`",
        f"- unique undefined title IDs: `{len({row['title_id'] for row in findings})}`",
        "- live mod files changed: `no`",
        "",
        "## Severity",
        "",
    ]
    lines.extend(
        f"- `{name}`: `{count}`"
        for name, count in sorted(severity_counts.items())
    )
    lines.extend(["", "## Classification", ""])
    lines.extend(
        f"- `{name}`: `{count}`"
        for name, count in class_counts.most_common()
    )
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `dynamic_title_reference_inventory.csv`",
            "- `dynamic_title_reference_findings.csv`",
        ]
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "dynamic_title_reference_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print(f"scanned_references={len(inventory)}")
    print(f"findings={len(findings)}")
    print(
        "classifications="
        + ", ".join(
            f"{key}:{value}" for key, value in class_counts.most_common()
        )
    )


if __name__ == "__main__":
    main()
