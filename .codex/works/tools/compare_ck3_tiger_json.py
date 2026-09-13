#!/usr/bin/env python3
"""Compare two CK3-Tiger JSON logs while isolating known unstable reports."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path
from typing import Any


WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
COLLISION_RE = re.compile(
    r"localization keys '(.+) and (.+)' have same MURMUR3A hash '([^']+)'"
)
UNSTABLE_KEYS = {"scopes", "strict-scopes"}
VOLATILE_LOCATION_FIELDS = {"column", "length", "line"}
SEMANTIC_VOLATILE_LOCATION_FIELDS = VOLATILE_LOCATION_FIELDS | {"linenr"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--left-label", default="left")
    parser.add_argument("--right-label", default="right")
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"Tiger JSON must contain a list: {path}")
    return data


def normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, str) and WINDOWS_PATH_RE.match(value):
        return value.casefold()
    return value


def normalize_report(
    row: dict[str, Any], *, ignore_line_numbers: bool = False
) -> dict[str, Any]:
    normalized = normalize_value(row)
    locations = normalized.get("locations")
    volatile_fields = (
        SEMANTIC_VOLATILE_LOCATION_FIELDS
        if ignore_line_numbers
        else VOLATILE_LOCATION_FIELDS
    )
    if isinstance(locations, list):
        normalized_locations: list[Any] = []
        for location in locations:
            if not isinstance(location, dict):
                normalized_locations.append(location)
                continue

            normalized_location = {
                key: value
                for key, value in location.items()
                if key not in volatile_fields
            }
            relative_path = normalized_location.get("path")
            if isinstance(relative_path, str) and relative_path:
                normalized_location["path"] = relative_path.replace("/", "\\").casefold()
                # Tiger emits a checkout-specific absolute path alongside the
                # stable relative path. Keeping both creates false worktree deltas.
                normalized_location.pop("fullpath", None)
            normalized_locations.append(normalized_location)
        normalized["locations"] = normalized_locations
    return normalized


def stable_signature(
    row: dict[str, Any], *, ignore_line_numbers: bool = False
) -> str | None:
    key = row.get("key")
    if key in UNSTABLE_KEYS:
        return None

    if key == "localization-key-collision":
        match = COLLISION_RE.search(str(row.get("message", "")))
        if match:
            payload = {
                "confidence": row.get("confidence"),
                "hash": match.group(3),
                "key": key,
                "localization_keys": sorted((match.group(1), match.group(2))),
                "severity": row.get("severity"),
            }
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    return json.dumps(
        normalize_report(row, ignore_line_numbers=ignore_line_numbers),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def summarize(
    rows: list[dict[str, Any]], *, ignore_line_numbers: bool = False
) -> tuple[collections.Counter[str], dict[str, int]]:
    stable: collections.Counter[str] = collections.Counter()
    unstable: collections.Counter[str] = collections.Counter()
    for row in rows:
        signature = stable_signature(row, ignore_line_numbers=ignore_line_numbers)
        if signature is None:
            unstable[str(row.get("key", "unknown"))] += 1
        else:
            stable[signature] += 1
    return stable, dict(sorted(unstable.items()))


def counter_hash(counter: collections.Counter[str]) -> str:
    canonical = "\n".join(
        f"{count}\t{signature}" for signature, count in sorted(counter.items())
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()


def sample_diff(counter: collections.Counter[str], limit: int = 20) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for signature, count in counter.items():
        payload = json.loads(signature)
        rows.append({"count": count, "report": payload})
        if len(rows) == limit:
            break
    return rows


def main() -> int:
    args = parse_args()
    left_rows = read_rows(args.left)
    right_rows = read_rows(args.right)
    left_stable, left_unstable = summarize(left_rows)
    right_stable, right_unstable = summarize(right_rows)
    left_semantic, _ = summarize(left_rows, ignore_line_numbers=True)
    right_semantic, _ = summarize(right_rows, ignore_line_numbers=True)

    left_only = left_stable - right_stable
    right_only = right_stable - left_stable
    semantic_left_only = left_semantic - right_semantic
    semantic_right_only = right_semantic - left_semantic
    result = {
        "left": {
            "label": args.left_label,
            "path": str(args.left.resolve()),
            "raw_report_count": len(left_rows),
            "stable_report_count": sum(left_stable.values()),
            "stable_sha256": counter_hash(left_stable),
            "semantic_sha256": counter_hash(left_semantic),
            "unstable_report_counts": left_unstable,
        },
        "right": {
            "label": args.right_label,
            "path": str(args.right.resolve()),
            "raw_report_count": len(right_rows),
            "stable_report_count": sum(right_stable.values()),
            "stable_sha256": counter_hash(right_stable),
            "semantic_sha256": counter_hash(right_semantic),
            "unstable_report_counts": right_unstable,
        },
        "stable_multiset_equal": left_stable == right_stable,
        "stable_only_left_count": sum(left_only.values()),
        "stable_only_right_count": sum(right_only.values()),
        "stable_only_left_sample": sample_diff(left_only),
        "stable_only_right_sample": sample_diff(right_only),
        "semantic_multiset_equal": left_semantic == right_semantic,
        "semantic_only_left_count": sum(semantic_left_only.values()),
        "semantic_only_right_count": sum(semantic_right_only.values()),
        "semantic_only_left_sample": sample_diff(semantic_left_only),
        "semantic_only_right_sample": sample_diff(semantic_right_only),
        "notes": [
            "Checkout-specific absolute paths are omitted when a relative path is available.",
            "Windows relative and fallback absolute paths are compared case-insensitively.",
            "Localization collision key order and source location are normalized.",
            "Volatile source excerpts, columns, and token lengths are normalized while file and line numbers remain evidence.",
            "Semantic comparison additionally ignores line numbers so edits that only shift unchanged reports do not look like regressions.",
            "scopes and strict-scopes counts are reported separately because Tiger inference is nondeterministic.",
        ],
    }

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = args.output_dir / "tiger_json_equivalence.json"
        md_path = args.output_dir / "tiger_json_equivalence_summary.md"
        json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        md_path.write_text(
            "\n".join(
                [
                    "# CK3-Tiger JSON Equivalence",
                    "",
                    f"- Stable multiset equal: `{str(result['stable_multiset_equal']).lower()}`",
                    f"- {args.left_label} raw/stable: `{len(left_rows)}` / `{sum(left_stable.values())}`",
                    f"- {args.right_label} raw/stable: `{len(right_rows)}` / `{sum(right_stable.values())}`",
                    f"- Stable only left/right: `{sum(left_only.values())}` / `{sum(right_only.values())}`",
                    f"- Semantic multiset equal: `{str(result['semantic_multiset_equal']).lower()}`",
                    f"- Semantic only left/right: `{sum(semantic_left_only.values())}` / `{sum(semantic_right_only.values())}`",
                    f"- {args.left_label} unstable: `{json.dumps(left_unstable, sort_keys=True)}`",
                    f"- {args.right_label} unstable: `{json.dumps(right_unstable, sort_keys=True)}`",
                    "",
                    "Known normalization: checkout-independent Windows paths, localization collision ordering, volatile source excerpts/columns/lengths, a line-insensitive semantic comparison, and separate scope-inference counts.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(f"json={json_path}")
        print(f"summary={md_path}")

    print(f"stable_multiset_equal={str(result['stable_multiset_equal']).lower()}")
    print(f"stable_only_left={sum(left_only.values())}")
    print(f"stable_only_right={sum(right_only.values())}")
    print(f"semantic_multiset_equal={str(result['semantic_multiset_equal']).lower()}")
    print(f"semantic_only_left={sum(semantic_left_only.values())}")
    print(f"semantic_only_right={sum(semantic_right_only.values())}")
    return 0 if result["semantic_multiset_equal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
