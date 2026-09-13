#!/usr/bin/env python3
"""Report stable CK3-Tiger changes introduced by pending upstream commits."""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
from pathlib import Path
from typing import Any


UNSTABLE_KEYS = {"scopes", "strict-scopes"}
COLLISION_RE = re.compile(
    r"localization keys '(.+) and (.+)' have same MURMUR3A hash '([^']+)'"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-json", required=True, type=Path)
    parser.add_argument("--latest-json", required=True, type=Path)
    parser.add_argument("--pending-files-csv", required=True, type=Path)
    parser.add_argument("--base-revision", required=True)
    parser.add_argument("--latest-revision", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def read_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"Tiger JSON must contain a list: {path}")
    return data


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0]) if rows else ["direction"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def normalize_path(value: str) -> str:
    path = value.replace("\\", "/").lstrip("./")
    if path.lower().startswith("bookmarksgit/"):
        path = path.split("/", 1)[1]
    return path


def report_signature(report: dict[str, Any]) -> tuple[Any, ...] | None:
    key = str(report.get("key", ""))
    if key in UNSTABLE_KEYS:
        return None
    paths = tuple(
        sorted(
            {
                normalize_path(str(location.get("path") or "")).lower()
                for location in report.get("locations") or []
                if isinstance(location, dict)
                and location.get("from") == "MOD"
                and location.get("path")
            }
        )
    )
    message = str(report.get("message", ""))
    if key == "localization-key-collision":
        match = COLLISION_RE.search(message)
        if match:
            message = f"{match.group(3)}|{'|'.join(sorted((match.group(1), match.group(2))))}"
    return (
        str(report.get("severity", "")),
        str(report.get("confidence", "")),
        key,
        message,
        paths,
    )


def build_counter(
    reports: list[dict[str, Any]],
) -> tuple[
    collections.Counter[tuple[Any, ...]],
    collections.Counter[str],
    dict[tuple[Any, ...], list[dict[str, Any]]],
]:
    stable: collections.Counter[tuple[Any, ...]] = collections.Counter()
    unstable: collections.Counter[str] = collections.Counter()
    evidence: dict[tuple[Any, ...], list[dict[str, Any]]] = collections.defaultdict(list)
    for report in reports:
        signature = report_signature(report)
        if signature is None:
            unstable[str(report.get("key", "unknown"))] += 1
        else:
            stable[signature] += 1
            evidence[signature].append(report)
    return stable, unstable, evidence


def joined(values: set[str]) -> str:
    return ";".join(sorted(value for value in values if value))


def recommendation(direction: str, severity: str, confidence: str, key: str) -> str:
    if direction == "resolved":
        return "retain_and_verify_upstream_resolution"
    if key == "duplicate-character":
        return "block_merge_until_character_identity_collision_is_resolved"
    if key == "missing-item" and confidence == "strong":
        return "block_merge_until_missing_dependency_is_resolved"
    if severity == "error" and confidence in {"strong", "reasonable"}:
        return "block_merge_until_error_is_reviewed"
    if key == "missing-file":
        return "verify_asset_or_reference_before_merge"
    return "review_before_merge"


def report_evidence(reports: list[dict[str, Any]]) -> tuple[str, str]:
    locations: set[str] = set()
    previews: set[str] = set()
    for report in reports:
        for location in report.get("locations") or []:
            if not isinstance(location, dict) or location.get("from") != "MOD":
                continue
            path = normalize_path(str(location.get("path") or ""))
            line_number = str(location.get("linenr") or "")
            locations.add(f"BookmarksGit/{path}:{line_number}")
            preview = str(location.get("line") or "").strip()
            if preview:
                previews.add(preview)
    return " | ".join(sorted(locations)), " | ".join(sorted(previews))


def occurrence_signature(report: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (
                normalize_path(str(location.get("path") or "")).lower(),
                str(location.get("line") or "").strip(),
            )
            for location in report.get("locations") or []
            if isinstance(location, dict) and location.get("from") == "MOD"
        )
    )


def delta_evidence(
    direction: str,
    signature: tuple[Any, ...],
    count: int,
    base_evidence: dict[tuple[Any, ...], list[dict[str, Any]]],
    latest_evidence: dict[tuple[Any, ...], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    source = latest_evidence if direction == "introduced" else base_evidence
    comparison = base_evidence if direction == "introduced" else latest_evidence
    remaining = collections.Counter(
        occurrence_signature(report) for report in source.get(signature, [])
    )
    remaining.subtract(
        occurrence_signature(report) for report in comparison.get(signature, [])
    )
    selected: list[dict[str, Any]] = []
    for report in source.get(signature, []):
        occurrence = occurrence_signature(report)
        if remaining[occurrence] <= 0:
            continue
        selected.append(report)
        remaining[occurrence] -= 1
        if len(selected) == count:
            break
    return selected


def main() -> int:
    args = parse_args()
    base_reports = read_json(args.base_json)
    latest_reports = read_json(args.latest_json)
    base_counter, base_unstable, base_evidence = build_counter(base_reports)
    latest_counter, latest_unstable, latest_evidence = build_counter(latest_reports)
    introduced = latest_counter - base_counter
    resolved = base_counter - latest_counter

    pending_rows = read_csv(args.pending_files_csv)
    pending_by_path = {
        normalize_path(row.get("path", "")).lower(): row for row in pending_rows
    }
    output_rows: list[dict[str, str]] = []
    for direction, delta in (("introduced", introduced), ("resolved", resolved)):
        for signature, count in sorted(
            delta.items(), key=lambda item: (-item[1], item[0])
        ):
            severity, confidence, key, message, paths = signature
            evidence_reports = delta_evidence(
                direction,
                signature,
                count,
                base_evidence,
                latest_evidence,
            )
            pending_matches = [pending_by_path[path] for path in paths if path in pending_by_path]
            commits = {
                commit.strip()
                for row in pending_matches
                for commit in row.get("touching_commits", "").split(";")
                if commit.strip()
            }
            risks = {row.get("risk", "") for row in pending_matches}
            evidence_groups = [[report] for report in evidence_reports]
            unmatched_count = count - len(evidence_reports)
            if unmatched_count:
                evidence_groups.append([])
            for evidence_group in evidence_groups:
                locations, line_previews = report_evidence(evidence_group)
                unit_count = len(evidence_group) or unmatched_count
                output_rows.append({
                    "direction": direction,
                    "count": str(unit_count),
                    "severity": severity,
                    "confidence": confidence,
                    "key": key,
                    "message": message,
                    "mod_paths": joined(set(paths)),
                    "locations": locations,
                    "line_previews": line_previews,
                    "direct_pending_file_match": "yes" if pending_matches else "no",
                    "touching_commits": joined(commits),
                    "newly_fetched_commit_touches": (
                        "yes"
                        if any(row.get("newly_fetched_commit_touches") == "yes" for row in pending_matches)
                        else "no"
                    ),
                    "inventory_risk": joined(risks),
                    "recommendation": recommendation(
                        direction, severity, confidence, key
                    ),
                    "auto_apply": "no",
                })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "upstream_tiger_delta.csv", output_rows)

    introduced_rows = [row for row in output_rows if row["direction"] == "introduced"]
    resolved_rows = [row for row in output_rows if row["direction"] == "resolved"]
    introduced_by_key = collections.Counter(
        (row["severity"], row["key"], row["confidence"])
        for row in introduced_rows
        for _ in range(int(row["count"]))
    )
    introduced_by_path: collections.Counter[str] = collections.Counter()
    for row in introduced_rows:
        for path in row["mod_paths"].split(";") if row["mod_paths"] else ["<no_mod_path>"]:
            introduced_by_path[path] += int(row["count"])

    blocking_count = sum(
        int(row["count"])
        for row in introduced_rows
        if row["recommendation"].startswith("block_merge")
    )
    summary = [
        "# Pending Upstream CK3-Tiger Delta",
        "",
        f"- Base revision: `{args.base_revision}`",
        f"- Latest revision: `{args.latest_revision}`",
        f"- Base raw/stable reports: `{len(base_reports)}` / `{sum(base_counter.values())}`",
        f"- Latest raw/stable reports: `{len(latest_reports)}` / `{sum(latest_counter.values())}`",
        f"- Introduced stable reports: `{sum(introduced.values())}`",
        f"- Resolved stable reports: `{sum(resolved.values())}`",
        f"- Introduced block-merge reports: `{blocking_count}`",
        f"- Merge readiness: `{'blocked_pending_review' if blocking_count else 'ready_for_next_merge_stage'}`",
        f"- Base unstable scope reports: `{dict(sorted(base_unstable.items()))}`",
        f"- Latest unstable scope reports: `{dict(sorted(latest_unstable.items()))}`",
        "",
        "## Introduced By Class",
        "",
    ]
    summary.extend(
        f"- `{severity}/{key}/{confidence}`: `{count}`"
        for (severity, key, confidence), count in introduced_by_key.most_common()
    )
    summary.extend(["", "## Introduced By Mod Path", ""])
    summary.extend(
        f"- `{path}`: `{count}`" for path, count in introduced_by_path.most_common()
    )
    summary.extend(
        [
            "",
            "Scope and strict-scope reports are counted separately because Tiger inference is nondeterministic.",
            "No source change is auto-applied by this audit.",
            "",
        ]
    )
    summary_path = args.output_dir / "upstream_tiger_delta_summary.md"
    summary_path.write_text("\n".join(summary), encoding="utf-8")
    manifest = {
        "base_revision": args.base_revision,
        "latest_revision": args.latest_revision,
        "base_json": str(args.base_json.resolve()),
        "latest_json": str(args.latest_json.resolve()),
        "pending_files_csv": str(args.pending_files_csv.resolve()),
        "base_raw_count": len(base_reports),
        "latest_raw_count": len(latest_reports),
        "introduced_stable_count": sum(introduced.values()),
        "resolved_stable_count": sum(resolved.values()),
        "blocking_introduced_count": blocking_count,
        "merge_readiness": (
            "blocked_pending_review" if blocking_count else "ready_for_next_merge_stage"
        ),
    }
    (args.output_dir / "upstream_tiger_delta_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"introduced={sum(introduced.values())}")
    print(f"resolved={sum(resolved.values())}")
    print(f"blocking_introduced={blocking_count}")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
