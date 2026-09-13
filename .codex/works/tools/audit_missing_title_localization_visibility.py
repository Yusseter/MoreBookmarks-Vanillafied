from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import audit_upstream_merge_state as merge_state


TITLE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])([hekdcb]_[A-Za-z0-9_'\-]+)(?![A-Za-z0-9_])")
TITLE_DECL_RE = re.compile(r"^\s*([hekdcb]_[A-Za-z0-9_'\-]+)\s*=\s*\{")
RUNTIME_ROOTS = ("common", "events", "history", "map_data", "gui", "gfx")
TEXT_SUFFIXES = {".txt", ".gui", ".asset", ".gfx", ".info", ".csv"}
MAP_MODE_PREFIXES = ("d_map_", "d_sea_minorities_map_", "d_siro_")
NULL_SENTINELS = {"e_mgr_null", "e_null_empire_japan"}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Classify missing landed-title localization by runtime visibility."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--localization-requirements",
        type=Path,
        default=repo_root
        / ".codex/works/analysis/generated/repo_integration_closure"
        / "localization_requirements.csv",
    )
    parser.add_argument(
        "--closure-findings",
        type=Path,
        default=repo_root
        / ".codex/works/analysis/generated/repo_integration_closure"
        / "repo_integration_closure_findings.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root
        / ".codex/works/analysis/generated/repo_integration_closure"
        / "localization_visibility",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def joined(values: set[str] | list[str]) -> str:
    return " | ".join(sorted({value for value in values if value}))


def load_targets(
    requirements_path: Path, findings_path: Path
) -> dict[str, dict[str, str]]:
    provenance: dict[str, str] = {}
    if findings_path.is_file():
        with findings_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if (
                    row.get("domain") == "localization"
                    and row.get("subdomain") == "title_base"
                ):
                    provenance[row.get("object", "")] = row.get("provenance", "")
    targets: dict[str, dict[str, str]] = {}
    with requirements_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (
                row.get("requirement") == "title_base"
                and row.get("status") == "missing_everywhere"
            ):
                key = row.get("key", "")
                targets[key] = {
                    "severity": "blocker",
                    "provenance": provenance.get(key, ""),
                }
    targets.pop("", None)
    return targets


def nearest_major_section(lines: list[str], line_number: int) -> str:
    for raw in reversed(lines[: line_number - 1]):
        stripped = raw.strip()
        if "MAP MODES" in stripped:
            return "MAP MODES"
        match = re.match(r"^#{8,}\s*([^#]+?)\s*#{8,}$", stripped)
        if match:
            return match.group(1).strip()
    return ""


def property_matches(raw_values: list[str], pattern: str) -> bool:
    return any(re.search(pattern, strip_comment(raw), re.I | re.S) for raw in raw_values)


def collect_landed_evidence(
    landed_dir: Path, targets: set[str]
) -> dict[str, dict[str, object]]:
    evidence: dict[str, dict[str, object]] = {
        key: {
            "definition_files": set(),
            "definition_locations": [],
            "definition_count": 0,
            "sections": set(),
            "parent_ids": set(),
            "child_ids": set(),
            "property_keys": set(),
            "property_raw": defaultdict(list),
        }
        for key in targets
    }
    for path in sorted(landed_dir.rglob("*.txt")):
        text = read_text(path)
        lines = text.splitlines()
        snapshot = merge_state.build_snapshot(str(path), text)
        relative = path.as_posix()
        for line_number, line in enumerate(lines, start=1):
            match = TITLE_DECL_RE.match(strip_comment(line))
            if not match or match.group(1) not in targets:
                continue
            key = match.group(1)
            item = evidence[key]
            item["definition_files"].add(relative)
            item["definition_locations"].append(f"{relative}:{line_number}")
            item["definition_count"] += 1
            item["sections"].add(nearest_major_section(lines, line_number))
        for key in targets.intersection(snapshot.titles):
            item = evidence[key]
            context = snapshot.contexts.get(key)
            if context:
                if context.parent_id:
                    item["parent_ids"].add(context.parent_id)
                item["child_ids"].update(context.child_ids)
            properties = snapshot.properties.get(key, {})
            item["property_keys"].update(properties)
            for property_key, occurrences in properties.items():
                item["property_raw"][property_key].extend(
                    occurrence.raw for occurrence in occurrences
                )
    return evidence


def collect_runtime_references(
    mod_root: Path, targets: set[str]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    history_blocks: dict[str, list[str]] = defaultdict(list)
    consumers: dict[str, list[str]] = defaultdict(list)
    if not targets:
        return history_blocks, consumers
    token_pattern = re.compile(
        r"(?<![A-Za-z0-9_])(" + "|".join(
            re.escape(key) for key in sorted(targets, key=len, reverse=True)
        ) + r")(?![A-Za-z0-9_])"
    )
    for root_name in RUNTIME_ROOTS:
        root = mod_root / root_name
        if not root.is_dir():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if root_name == "common" and "landed_titles" in {
                part.lower() for part in path.parts
            }:
                continue
            if "localization" in {part.lower() for part in path.parts}:
                continue
            relative = path.relative_to(mod_root.parent).as_posix()
            for line_number, raw_line in enumerate(read_text(path).splitlines(), start=1):
                clean = strip_comment(raw_line)
                if not clean.strip():
                    continue
                declaration = TITLE_DECL_RE.match(clean)
                declared_key = declaration.group(1) if declaration else ""
                for match in token_pattern.finditer(clean):
                    key = match.group(1)
                    location = f"{relative}:{line_number}"
                    if (
                        root_name == "history"
                        and "titles" in {part.lower() for part in path.parts}
                        and declared_key == key
                    ):
                        history_blocks[key].append(location)
                    else:
                        snippet = " ".join(clean.strip().split())[:180]
                        consumers[key].append(f"{location} :: {snippet}")
    return history_blocks, consumers


def classify(
    key: str,
    item: dict[str, object],
    history_blocks: list[str],
    consumers: list[str],
) -> tuple[str, str, str, str, str]:
    properties: dict[str, list[str]] = item["property_raw"]
    sections: set[str] = item["sections"]
    parents: set[str] = item["parent_ids"]
    children: set[str] = item["child_ids"]
    can_create = properties.get("can_create", [])
    can_create_never = property_matches(can_create, r"\balways\s*=\s*no\b")
    landless = property_matches(properties.get("landless", []), r"\blandless\s*=\s*yes\b")

    is_map_mode = (
        key.startswith(MAP_MODE_PREFIXES)
        and "MAP MODES" in sections
        and not parents
        and not children
        and not history_blocks
    )
    if is_map_mode:
        return (
            "internal_map_mode_color_title",
            "info",
            "high",
            "title is an unlanded MAP MODES color carrier with no title-history or hierarchy role",
            "exclude_from_player_visible_localization_blockers_keep_raw_tiger_notice",
        )
    if (
        key in NULL_SENTINELS
        and can_create_never
        and not children
        and not history_blocks
    ):
        return (
            "internal_null_sentinel_title_review",
            "review",
            "high",
            "title is a non-creatable null/sentinel container with no title-history assignment",
            "verify_no_runtime_holder_then_accept_missing_or_add_technical_localization",
        )
    if (
        "OBSOLETE TITLES" in sections
        and not parents
        and not children
        and not history_blocks
        and not consumers
    ):
        return (
            "obsolete_unreferenced_title_localization_review",
            "review",
            "high",
            "title is explicitly grouped as obsolete and has no active history, hierarchy, or consumer evidence",
            "verify_obsolete_title_should_remain_defined_then_accept_missing_or_remove_title",
        )
    color_template_only = bool(consumers) and all(
        re.search(
            rf"\bset_color_from_title\s*=\s*title:{re.escape(key)}\b",
            consumer,
        )
        for consumer in consumers
    )
    if (
        color_template_only
        and not parents
        and not children
        and not history_blocks
    ):
        return (
            "internal_color_template_title_review",
            "review",
            "high",
            "title is referenced only as a set_color_from_title template and has no holder or hierarchy evidence",
            "verify_color_template_only_then_accept_missing_or_add_technical_localization",
        )
    if history_blocks:
        return (
            "player_visible_historical_title_missing_localization",
            "blocker",
            "high",
            "title has an explicit title-history block and can surface to the player",
            "author_localization",
        )
    if "RELIGIOUS HEADS" in sections:
        return (
            "player_visible_religious_head_title_missing_localization",
            "blocker",
            "high",
            "title is configured in the RELIGIOUS HEADS section and can surface through faith-head gameplay",
            "author_localization",
        )
    if parents or children:
        return (
            "player_visible_de_jure_title_missing_localization",
            "blocker",
            "high",
            "title participates in the landed-title hierarchy and can surface to the player",
            "author_localization",
        )
    if landless:
        return (
            "player_visible_landless_title_missing_localization",
            "blocker",
            "high",
            "landless title can surface through its holder or associated gameplay system",
            "author_localization",
        )
    if consumers:
        return (
            "script_referenced_title_missing_localization",
            "blocker",
            "medium",
            "title has active non-localization consumers and may surface at runtime",
            "review_consumers_and_author_localization",
        )
    if not can_create_never:
        return (
            "potentially_creatable_titular_title_missing_localization",
            "blocker",
            "medium",
            "standalone title is not proven non-creatable and may surface at runtime",
            "author_localization_or_prove_internal_only",
        )
    return (
        "inactive_noncreatable_title_localization_review",
        "review",
        "medium",
        "non-creatable standalone title has no history, hierarchy, or active consumer evidence",
        "verify_intent_then_accept_missing_or_add_localization",
    )


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    mod_root = repo_root / "BookmarksGit"
    targets = load_targets(
        args.localization_requirements.resolve(), args.closure_findings.resolve()
    )
    evidence = collect_landed_evidence(
        mod_root / "common/landed_titles", set(targets)
    )
    history_blocks, consumers = collect_runtime_references(mod_root, set(targets))

    rows: list[dict[str, str]] = []
    for key in sorted(targets):
        item = evidence[key]
        properties: dict[str, list[str]] = item["property_raw"]
        classification, severity, confidence, reason, recommendation = classify(
            key, item, history_blocks.get(key, []), consumers.get(key, [])
        )
        can_create = properties.get("can_create", [])
        rows.append({
            "title_id": key,
            "original_severity": targets[key].get("severity", ""),
            "original_provenance": targets[key].get("provenance", ""),
            "definition_count": str(item["definition_count"]),
            "duplicate_definition": yes_no(int(item["definition_count"]) > 1),
            "definition_files": joined(item["definition_files"]),
            "definition_locations": joined(item["definition_locations"]),
            "major_sections": joined(item["sections"]),
            "parent_ids": joined(item["parent_ids"]),
            "child_count": str(len(item["child_ids"])),
            "child_ids": joined(item["child_ids"]),
            "property_keys": joined(item["property_keys"]),
            "can_create_present": yes_no(bool(can_create)),
            "can_create_never": yes_no(property_matches(can_create, r"\balways\s*=\s*no\b")),
            "landless": yes_no(property_matches(properties.get("landless", []), r"\blandless\s*=\s*yes\b")),
            "noble_family": yes_no(property_matches(properties.get("noble_family", []), r"\bnoble_family\s*=\s*yes\b")),
            "title_history_block_count": str(len(history_blocks.get(key, []))),
            "title_history_locations": joined(history_blocks.get(key, [])),
            "active_consumer_count": str(len(consumers.get(key, []))),
            "active_consumer_files": joined({value.split(":", 1)[0] for value in consumers.get(key, [])}),
            "active_consumer_examples": " | ".join(consumers.get(key, [])[:5]),
            "visibility_classification": classification,
            "classified_severity": severity,
            "confidence": confidence,
            "reason": reason,
            "recommendation": recommendation,
        })

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_csv = output_dir / "missing_title_localization_visibility.csv"
    write_csv(output_csv, rows)
    classes = Counter(row["visibility_classification"] for row in rows)
    severities = Counter(row["classified_severity"] for row in rows)
    duplicate_rows = [row for row in rows if row["duplicate_definition"] == "yes"]
    summary = [
        "# Missing Title Localization Visibility Audit",
        "",
        f"- input missing-everywhere title keys: `{len(rows)}`",
        f"- classified blockers: `{severities['blocker']}`",
        f"- classified reviews: `{severities['review']}`",
        f"- classified info: `{severities['info']}`",
        f"- duplicate landed-title definitions in scope: `{len(duplicate_rows)}`",
        "",
        "## Classes",
        "",
    ]
    summary.extend(f"- {name}: `{count}`" for name, count in classes.most_common())
    summary.extend([
        "",
        "## Safety",
        "",
        "- This audit does not modify live BookmarksGit source files.",
        "- Raw Tiger missing-localization evidence is retained even when closure severity is downgraded.",
        "- Only structurally proven MAP MODES color carriers are classified as info.",
    ])
    (output_dir / "missing_title_localization_visibility_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print(f"rows={len(rows)}")
    print(f"severity={dict(sorted(severities.items()))}")
    print(f"classes={dict(sorted(classes.items()))}")
    print(f"output={output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
