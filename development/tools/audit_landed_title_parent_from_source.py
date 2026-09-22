from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from audit_landed_title_source_identity import (
    NO_COUNTERPART,
    parse_landed_titles_path,
    read_manual_rows,
    split_tokens,
)


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    mod_root = project_root / "BookmarksGit"
    works_root = project_root / "development"
    parser = argparse.ArgumentParser(
        description="Audit current landed title parents against inferred source identity."
    )
    parser.add_argument("--current-landed-titles", type=Path, default=mod_root / "common/landed_titles/00_landed_titles.txt")
    parser.add_argument(
        "--relation-csv",
        "--manual-csv",
        dest="manual_csv",
        type=Path,
        default=works_root
        / "pipeline_inputs/title_relations/curated_title_relations.csv",
    )
    parser.add_argument(
        "--source-identity",
        type=Path,
        default=works_root
        / "analysis/generated/landed_title_source_identity/landed_title_source_identity_audit.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=works_root / "analysis/generated/landed_title_parent_source_audit",
    )
    return parser.parse_args()


def read_source_identity(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            row["title_id"].strip(): {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, skipinitialspace=True)
            if (row.get("title_id") or "").strip()
        }


def build_mod_parent_reverse(manual_rows: list[dict[str, str]]) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = {}
    for row in manual_rows:
        current_id = row["source_title_id"]
        for token in split_tokens(row.get("mod_title_id", "")):
            reverse.setdefault(token, [])
            if current_id not in reverse[token]:
                reverse[token].append(current_id)
    return reverse


def add_source_identity_reverse(reverse: dict[str, list[str]], source_rows: dict[str, dict[str, str]]) -> None:
    for title_id, row in source_rows.items():
        mod_title = row.get("mod_best_title", "")
        if not mod_title:
            continue
        reverse.setdefault(mod_title, [])
        if title_id not in reverse[mod_title]:
            reverse[mod_title].append(title_id)


def expected_parent_candidates(
    source_decision: str,
    source_parent: str,
    current_title_ids: set[str],
    mod_parent_reverse: dict[str, list[str]],
) -> list[str]:
    if not source_parent:
        return [""]
    if source_decision == "modlu_kalan":
        return mod_parent_reverse.get(source_parent, [])
    if source_decision == "orijinal_dogu" and source_parent in current_title_ids:
        return [source_parent]
    return []


def audit(args: argparse.Namespace) -> list[dict[str, str]]:
    current_blocks = parse_landed_titles_path(args.current_landed_titles)
    manual_rows = read_manual_rows(args.manual_csv)
    source_rows = read_source_identity(args.source_identity)
    mod_parent_reverse = build_mod_parent_reverse(manual_rows)
    add_source_identity_reverse(mod_parent_reverse, source_rows)
    current_title_ids = set(current_blocks)

    rows: list[dict[str, str]] = []
    for title_id in sorted(source_rows, key=lambda key: int(source_rows[key].get("current_line") or 0)):
        if title_id.startswith("b_"):
            continue
        current_block = current_blocks.get(title_id)
        source_row = source_rows.get(title_id, {})
        source_decision = source_row.get("source_decision", "")

        row = {
            "title_id": title_id,
            "current_parent": current_block.parent_id if current_block else "",
            "current_path": current_block.path if current_block else "",
            "source_decision": source_decision,
            "source_confidence": source_row.get("confidence", ""),
            "source_title": "",
            "source_parent": "",
            "expected_parent": "",
            "expected_parent_candidates": "",
            "status": "",
            "note": "",
        }

        if not current_block:
            row["status"] = "missing_current_title"
            rows.append(row)
            continue
        if source_decision not in {"modlu_kalan", "orijinal_dogu"}:
            row["status"] = "manual_review_source"
            row["note"] = source_row.get("decision_reason", "")
            rows.append(row)
            continue

        if source_decision == "modlu_kalan":
            source_title = source_row.get("mod_best_title", "")
            source_parent = source_row.get("mod_best_parent", "")
        else:
            source_title = source_row.get("vanilla_title", "")
            source_parent = source_row.get("vanilla_parent", "")

        expected = expected_parent_candidates(source_decision, source_parent, current_title_ids, mod_parent_reverse)
        row["source_title"] = source_title
        row["source_parent"] = source_parent
        row["expected_parent_candidates"] = " | ".join(expected)

        if row["current_parent"] in expected:
            row["status"] = "ok"
            row["expected_parent"] = row["current_parent"]
        elif not expected:
            row["status"] = "missing_parent_mapping"
            row["expected_parent"] = f"{source_decision}:{source_parent}?"
        elif len(expected) == 1:
            row["status"] = "wrong"
            row["expected_parent"] = expected[0]
        else:
            row["status"] = "ambiguous_parent_mapping"

        rows.append(row)

    return rows


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(output_dir: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "title_id",
        "current_parent",
        "current_path",
        "source_decision",
        "source_confidence",
        "source_title",
        "source_parent",
        "expected_parent",
        "expected_parent_candidates",
        "status",
        "note",
    ]
    write_csv(output_dir / "landed_title_parent_source_audit.csv", rows, fieldnames)
    write_csv(
        output_dir / "landed_title_parent_manual_simple.csv",
        [
            {
                "title_id": row["title_id"],
                "current_parent": row["current_parent"],
                "expected_parent": row["expected_parent"] or row["expected_parent_candidates"],
                "status": row["status"],
            }
            for row in rows
            if row["status"] != "ok"
        ],
        ["title_id", "current_parent", "expected_parent", "status"],
    )
    write_csv(
        output_dir / "landed_title_parent_wrong.csv",
        [row for row in rows if row["status"] == "wrong"],
        fieldnames,
    )

    status_counts = Counter(row["status"] for row in rows)
    lines = [
        "# Landed Title Parent Source Audit",
        "",
        f"- rows: `{len(rows)}`",
        "",
        "## Status Counts",
        "",
    ]
    for key, value in sorted(status_counts.items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- detailed audit: `landed_title_parent_source_audit.csv`",
            "- simple manual view: `landed_title_parent_manual_simple.csv`",
            "- wrong-only report: `landed_title_parent_wrong.csv`",
        ]
    )
    (output_dir / "landed_title_parent_source_audit_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    rows = audit(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_outputs(args.output_dir, rows)
    print(f"rows={len(rows)}")
    print("status_counts=" + ", ".join(f"{key}:{value}" for key, value in sorted(Counter(row["status"] for row in rows).items())))
    print(f"summary={args.output_dir / 'landed_title_parent_source_audit_summary.md'}")


if __name__ == "__main__":
    main()
