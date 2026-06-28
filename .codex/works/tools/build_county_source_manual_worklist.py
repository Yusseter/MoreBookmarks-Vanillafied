from __future__ import annotations

import argparse
import csv
from pathlib import Path


OUTPUT_COLUMNS = [
    "county_id",
    "current_source",
    "expected_source",
    "status",
    "yusseter_note",
    "yusseter_remove_note",
]

NOTE_MARKER = " #"
USER_NOTE_COLUMN = "yusseter_note"
DONE_VALUE = "done"
REMOVE_NOTE_COLUMN = "yusseter_remove_note"
NO_PROBLEM_VALUE = "no_problem"


ACTION_PRIORITY = {
    "replace_with_vanilla_block": 0,
    "replace_with_mod_block": 1,
    "manual_review": 2,
}

STATUS_PRIORITY = {
    "mismatch": 0,
    "mixed": 1,
    "unknown": 2,
    "review": 3,
    "skip": 4,
}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_dir = repo_root / "works/analysis/generated/landed_titles_source_audit"
    parser = argparse.ArgumentParser(description="Build a compact county source manual-review worklist CSV.")
    parser.add_argument("--audit-csv", type=Path, default=default_dir / "county_source_audit.csv")
    parser.add_argument("--fix-plan-csv", type=Path, default=default_dir / "county_source_fix_plan.csv")
    parser.add_argument("--output-csv", type=Path, default=default_dir / "county_source_manual_worklist.csv")
    parser.add_argument(
        "--preserved-notes-csv",
        type=Path,
        default=default_dir / "county_source_manual_worklist_preserved_notes.csv",
    )
    parser.add_argument(
        "--accepted-candidates-csv",
        type=Path,
        default=default_dir / "county_source_simple_resolution_candidates.csv",
    )
    return parser.parse_args()


def read_csv_by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row[key]: row for row in csv.DictReader(handle)}


def read_accepted_counties(path: Path) -> set[str]:
    if not path.exists():
        return set()

    accepted: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            decision = row.get("decision", "")
            county_id = row.get("county_id", "")
            if county_id and decision.startswith("accept_"):
                accepted.add(county_id)
    return accepted


def split_status_note(value: str) -> tuple[str, str]:
    if NOTE_MARKER not in value:
        return value.strip(), ""
    status, note = value.split(NOTE_MARKER, 1)
    return status.strip(), f"{NOTE_MARKER}{note.rstrip()}"


def read_row_value(row: dict[str, str], key: str) -> str:
    direct = row.get(key)
    if direct is not None:
        return direct
    for existing_key, value in row.items():
        if (existing_key or "").strip() == key:
            return value or ""
    return ""


def read_existing_annotations(path: Path, preserved_notes_path: Path) -> dict[str, dict[str, str]]:
    annotations: dict[str, dict[str, str]] = {}

    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                county_id = read_row_value(row, "county_id").strip()
                _, note = split_status_note(read_row_value(row, "status"))
                user_note = read_row_value(row, USER_NOTE_COLUMN).strip()
                remove_note = read_row_value(row, REMOVE_NOTE_COLUMN).strip()
                if county_id and (note or user_note or remove_note):
                    annotations[county_id] = {
                        "note": note,
                        USER_NOTE_COLUMN: user_note,
                        REMOVE_NOTE_COLUMN: remove_note,
                    }

    if preserved_notes_path.exists():
        with preserved_notes_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                county_id = read_row_value(row, "county_id").strip()
                note = read_row_value(row, "note").strip()
                user_note = read_row_value(row, USER_NOTE_COLUMN).strip()
                remove_note = read_row_value(row, REMOVE_NOTE_COLUMN).strip()
                if county_id and note:
                    if not note.startswith("#"):
                        note = f"# {note}"
                    note = f" {note}"
                if county_id and (note or user_note or remove_note):
                    annotations[county_id] = {
                        "note": note,
                        USER_NOTE_COLUMN: user_note,
                        REMOVE_NOTE_COLUMN: remove_note,
                    }

    return annotations


def write_preserved_notes(path: Path, annotations: dict[str, dict[str, str]], active_counties: set[str]) -> int:
    preserved_rows = []
    for county_id, annotation in sorted(annotations.items()):
        if county_id in active_counties:
            continue
        user_note = str(annotation.get(USER_NOTE_COLUMN, "")).strip()
        remove_note = str(annotation.get(REMOVE_NOTE_COLUMN, "")).strip()
        if user_note == DONE_VALUE:
            preserved_reason = "manually_marked_done"
        elif remove_note == NO_PROBLEM_VALUE:
            preserved_reason = "manually_marked_no_problem"
        else:
            preserved_reason = "county_not_in_current_worklist"
        preserved_rows.append(
            {
                "county_id": county_id,
                "note": str(annotation.get("note", "")).strip(),
                USER_NOTE_COLUMN: user_note,
                REMOVE_NOTE_COLUMN: remove_note,
                "preserved_reason": preserved_reason,
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["county_id", "note", USER_NOTE_COLUMN, REMOVE_NOTE_COLUMN, "preserved_reason"],
        )
        writer.writeheader()
        writer.writerows(preserved_rows)

    return len(preserved_rows)


def simple_status(audit_status: str) -> str:
    if audit_status.startswith("mismatch:"):
        return "mismatch"
    if audit_status.startswith("review:"):
        return "review"
    if audit_status == "manual_review:mixed":
        return "mixed"
    if audit_status == "manual_review:unknown":
        return "unknown"
    if audit_status.startswith("skip:"):
        return "skip"
    return audit_status


def split_province_sources(value: str) -> set[str]:
    return {token.strip() for token in value.split("|") if token.strip()}


def auto_remove_reason(
    audit_row: dict[str, str],
    plan_row: dict[str, str],
    audit_by_county: dict[str, dict[str, str]],
) -> str:
    county_id = plan_row.get("county_id", "")
    expected_source = plan_row.get("expected_source", "")
    current_block_source = plan_row.get("current_block_source", "")
    province_sources = split_province_sources(audit_row.get("province_sources", ""))
    vanilla_best_match = audit_row.get("vanilla_best_match", "")

    if expected_source == "mixed" and current_block_source in {"vanilla_exact", "mod_exact"}:
        return "mixed_current_exact_source"
    if expected_source == "unknown" and province_sources == {"both_masks"}:
        return "unknown_all_provinces_both_masks"
    if (
        expected_source == "mixed"
        and province_sources
        and "mod_kalan" not in province_sources
        and province_sources <= {"vanilla_east", "both_masks"}
        and "05_goryeo.txt:" in vanilla_best_match
    ):
        return "goryeo_vanilla_with_both_masks_only"
    if (
        county_id.endswith("_mbp")
        and expected_source == "mod"
        and current_block_source in {"", "no_source_candidate"}
        and audit_row.get("audit_status", "") == "review:expected_mod_source_not_exact"
    ):
        base_county_id = county_id[:-4]
        base_audit = audit_by_county.get(base_county_id, {})
        if base_audit.get("expected_source", "") == "vanilla":
            return "intentional_mbp_rename_for_vanilla_conflict"
    return ""



def sort_key(row: dict[str, str]) -> tuple[int, str, int, str]:
    action = row["_action"]
    status = row["status"]
    return (
        ACTION_PRIORITY.get(action, 99),
        STATUS_PRIORITY.get(status, 99),
        row["expected_source"],
        row["county_id"],
    )


def main() -> None:
    args = parse_args()
    audit_by_county = read_csv_by_key(args.audit_csv, "county_id")
    existing_annotations = read_existing_annotations(args.output_csv, args.preserved_notes_csv)
    accepted_counties = read_accepted_counties(args.accepted_candidates_csv)
    done_skipped = 0
    no_problem_skipped = 0
    auto_skipped = 0

    rows: list[dict[str, str]] = []
    with args.fix_plan_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        for plan_row in csv.DictReader(handle):
            action = plan_row["action"]
            if action == "no_action":
                continue

            county_id = plan_row["county_id"]
            if county_id in accepted_counties:
                continue
            user_note = str(existing_annotations.get(county_id, {}).get(USER_NOTE_COLUMN, "")).strip()
            if user_note == DONE_VALUE:
                done_skipped += 1
                continue
            remove_note = str(existing_annotations.get(county_id, {}).get(REMOVE_NOTE_COLUMN, "")).strip()
            if remove_note == NO_PROBLEM_VALUE:
                no_problem_skipped += 1
                continue

            audit_row = audit_by_county[county_id]
            status = simple_status(audit_row["audit_status"])
            if status in {"ok", "skip"}:
                continue
            auto_reason = auto_remove_reason(audit_row, plan_row, audit_by_county)
            if auto_reason:
                auto_skipped += 1
                continue
            rows.append(
                {
                    "county_id": county_id,
                    "current_source": plan_row["current_block_source"],
                    "expected_source": plan_row["expected_source"],
                    "status": status,
                    USER_NOTE_COLUMN: user_note,
                    REMOVE_NOTE_COLUMN: remove_note,
                    "_action": action,
                }
            )

    rows.sort(key=sort_key)
    active_counties = {row["county_id"] for row in rows}
    preserved_note_count = write_preserved_notes(args.preserved_notes_csv, existing_annotations, active_counties)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            output_row = {column: row.get(column, "") for column in OUTPUT_COLUMNS}
            note = str(existing_annotations.get(row["county_id"], {}).get("note", ""))
            if note:
                output_row["status"] = f"{output_row['status']}{note}"
            writer.writerow(output_row)

    print(f"wrote: {args.output_csv}")
    print(f"rows: {len(rows)}")
    print(f"preserved notes: {preserved_note_count}")
    print(f"accepted skipped: {len(accepted_counties)}")
    print(f"done skipped: {done_skipped}")
    print(f"no_problem skipped: {no_problem_skipped}")
    print(f"auto skipped: {auto_skipped}")


if __name__ == "__main__":
    main()
