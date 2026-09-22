from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path


TITLE_RE = re.compile(r"^\s*([hekdcb]_[A-Za-z0-9_'\-]+)\s*=\s*\{")
CAPITAL_RE = re.compile(r"^\s*capital\s*=\s*(c_[A-Za-z0-9_'\-]+)\b")
NO_COUNTERPART = "*there_is_no*"
AUDIT_TITLE_PREFIXES = ("h_", "e_", "k_", "d_")


@dataclass(frozen=True)
class TitleBlock:
    title_id: str
    source_file: str
    start_line: int
    end_line: int
    parent_id: str
    root_title: str
    path: str
    direct_capital: str
    direct_capital_line: int
    effective_capital: str
    effective_capital_line: int
    effective_capital_source: str


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    mod_root = project_root / "BookmarksGit"
    works_root = project_root / "development"
    parser = argparse.ArgumentParser(
        description="Audit landed title capital values against their source capital mapped back to current titles."
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
        "--mask-scope-manual-like",
        type=Path,
        default=works_root
        / "analysis/generated/title_relation_manual_validation/mask_east_scope/title_relation_mask_east_scope_manual_like.csv",
    )
    parser.add_argument(
        "--mod-landed-titles-dir",
        type=Path,
        default=project_root.parent
        / "Leviathonlx MoreBookmarks-Plus"
        / "BookmarksGit"
        / "common"
        / "landed_titles",
    )
    parser.add_argument(
        "--vanilla-landed-titles-dir",
        type=Path,
        default=Path(r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game\common\landed_titles"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=works_root / "analysis/generated/landed_title_capital_source_audit",
    )
    return parser.parse_args()


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def parse_landed_title_file(path: Path) -> dict[str, TitleBlock]:
    lines = read_text(path).splitlines()
    blocks: dict[str, TitleBlock] = {}
    stack: list[dict[str, object]] = []
    depth = 0

    for index, line in enumerate(lines):
        clean = strip_comment(line)
        title_match = TITLE_RE.match(clean)
        if title_match:
            title_id = title_match.group(1)
            path_ids = [str(item["title_id"]) for item in stack] + [title_id]
            stack.append(
                {
                    "title_id": title_id,
                    "start_line": index + 1,
                    "depth": depth + 1,
                    "parent_id": path_ids[-2] if len(path_ids) > 1 else "",
                    "root_title": path_ids[0],
                    "path": " > ".join(path_ids),
                    "direct_capital": "",
                    "direct_capital_line": 0,
                }
            )

        capital_match = CAPITAL_RE.match(clean)
        if capital_match and stack:
            stack[-1]["direct_capital"] = capital_match.group(1)
            stack[-1]["direct_capital_line"] = index + 1

        depth += clean.count("{") - clean.count("}")
        while stack and depth < int(stack[-1]["depth"]):
            item = stack.pop()
            title_id = str(item["title_id"])
            if title_id not in blocks:
                blocks[title_id] = TitleBlock(
                    title_id=title_id,
                    source_file=str(path),
                    start_line=int(item["start_line"]),
                    end_line=index + 1,
                    parent_id=str(item["parent_id"]),
                    root_title=str(item["root_title"]),
                    path=str(item["path"]),
                    direct_capital=str(item["direct_capital"]),
                    direct_capital_line=int(item["direct_capital_line"]),
                    effective_capital="",
                    effective_capital_line=0,
                    effective_capital_source="",
                )

    return blocks


def with_effective_capitals(blocks: dict[str, TitleBlock]) -> dict[str, TitleBlock]:
    county_blocks = sorted(
        (block for block in blocks.values() if block.title_id.startswith("c_")),
        key=lambda block: block.start_line,
    )
    result: dict[str, TitleBlock] = {}

    for title_id, block in blocks.items():
        effective_capital = block.direct_capital
        effective_capital_line = block.direct_capital_line
        effective_capital_source = "direct" if block.direct_capital else ""

        if not effective_capital and title_id.startswith("c_"):
            effective_capital = title_id
            effective_capital_line = block.start_line
            effective_capital_source = "self_county"

        if not effective_capital and title_id.startswith(AUDIT_TITLE_PREFIXES):
            path_prefix = block.path + " > "
            first_county = next((county for county in county_blocks if county.path.startswith(path_prefix)), None)
            if first_county:
                effective_capital = first_county.title_id
                effective_capital_line = first_county.start_line
                effective_capital_source = "first_descendant_county"

        result[title_id] = replace(
            block,
            effective_capital=effective_capital,
            effective_capital_line=effective_capital_line,
            effective_capital_source=effective_capital_source,
        )

    return result


def parse_landed_titles_path(path: Path) -> dict[str, TitleBlock]:
    if path.is_file():
        return with_effective_capitals(parse_landed_title_file(path))

    merged: dict[str, TitleBlock] = {}
    for file_path in sorted(path.glob("*.txt")):
        for title_id, block in parse_landed_title_file(file_path).items():
            merged.setdefault(title_id, block)
    return with_effective_capitals(merged)


def split_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for raw in value.split("&"):
        token = raw.replace("(second)", "").strip()
        if not token or token == NO_COUNTERPART:
            continue
        tokens.append(token)
    return tokens


def read_manual_mapping(path: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    current_to_mod: dict[str, list[str]] = {}
    mod_to_current: dict[str, list[str]] = defaultdict(list)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        for row in reader:
            source_title_id = (row.get("source_title_id") or "").strip()
            if not source_title_id:
                continue
            mod_tokens = split_tokens((row.get("mod_title_id") or "").strip())
            current_to_mod[source_title_id] = mod_tokens
            for token in mod_tokens:
                if source_title_id not in mod_to_current[token]:
                    mod_to_current[token].append(source_title_id)

    return current_to_mod, dict(mod_to_current)


def read_mask_scope_origin(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    result: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        for row in reader:
            source_title_id = (row.get("source_title_id") or "").strip()
            if not source_title_id:
                continue
            result[source_title_id] = {
                "mask_scope_change": (row.get("mask_scope_change") or "").strip(),
                "mask_scope_reasons": (row.get("mask_scope_reasons") or "").strip(),
                "title_source_origin": (row.get("title_source_origin") or "").strip(),
            }
    return result


def choose_source_candidates(
    title_id: str,
    mod_tokens: list[str],
    origin: str,
    mod_blocks: dict[str, TitleBlock],
    vanilla_blocks: dict[str, TitleBlock],
) -> list[tuple[str, str, TitleBlock]]:
    mod_candidates = [("mod", token, mod_blocks[token]) for token in mod_tokens if token in mod_blocks]
    vanilla_candidates = [("vanilla", title_id, vanilla_blocks[title_id])] if title_id in vanilla_blocks else []

    if origin == "vanilla" and vanilla_candidates:
        return vanilla_candidates
    if origin == "mod" and mod_candidates:
        return mod_candidates
    if origin == "both":
        return mod_candidates + vanilla_candidates

    return mod_candidates + vanilla_candidates


def expected_current_capitals_for_source_capital(
    source_kind: str,
    source_capital: str,
    current_blocks: dict[str, TitleBlock],
    mod_to_current: dict[str, list[str]],
) -> list[str]:
    if source_kind == "mod":
        return mod_to_current.get(source_capital, [])
    if source_capital in current_blocks:
        return [source_capital]
    return []


def audit(args: argparse.Namespace) -> tuple[list[dict[str, str]], Counter[str]]:
    current_blocks = parse_landed_titles_path(args.current_landed_titles)
    mod_blocks = parse_landed_titles_path(args.mod_landed_titles_dir)
    vanilla_blocks = parse_landed_titles_path(args.vanilla_landed_titles_dir)
    current_to_mod, mod_to_current = read_manual_mapping(args.manual_csv)
    origins = read_mask_scope_origin(args.mask_scope_manual_like)

    rows: list[dict[str, str]] = []
    status_counts: Counter[str] = Counter()

    for title_id in sorted(current_to_mod):
        if not title_id.startswith(AUDIT_TITLE_PREFIXES):
            continue
        current_block = current_blocks.get(title_id)
        if not current_block:
            continue

        if not current_block.effective_capital:
            row = base_row(title_id, current_block, origins.get(title_id, {}), current_to_mod.get(title_id, []))
            row.update({"status": "missing_effective_capital"})
            rows.append(row)
            status_counts[row["status"]] += 1
            continue

        origin_info = origins.get(title_id, {})
        origin = origin_info.get("title_source_origin", "")
        mod_tokens = current_to_mod.get(title_id, [])
        candidates = choose_source_candidates(title_id, mod_tokens, origin, mod_blocks, vanilla_blocks)

        if not candidates:
            row = base_row(title_id, current_block, origin_info, mod_tokens)
            row.update({"status": "missing_source_title"})
            rows.append(row)
            status_counts[row["status"]] += 1
            continue

        for source_kind, source_title_id, source_block in candidates:
            row = base_row(title_id, current_block, origin_info, mod_tokens)
            row.update(
                {
                    "selected_source_kind": source_kind,
                    "selected_source_title_id": source_title_id,
                    "source_title_path": source_block.path,
                    "source_title_file": source_block.source_file,
                    "source_title_line": str(source_block.start_line),
                    "source_capital": source_block.effective_capital,
                    "source_capital_line": str(source_block.effective_capital_line),
                    "source_capital_source": source_block.effective_capital_source,
                    "source_direct_capital": source_block.direct_capital,
                    "source_direct_capital_line": str(source_block.direct_capital_line),
                }
            )

            if not source_block.effective_capital:
                row["status"] = "missing_effective_capital"
            else:
                expected = expected_current_capitals_for_source_capital(
                    source_kind, source_block.effective_capital, current_blocks, mod_to_current
                )
                row["expected_current_capital_candidates"] = " | ".join(expected)
                row["expected_current_capital_count"] = str(len(expected))
                if not expected:
                    row["status"] = "missing_expected_current_capital_mapping"
                elif current_block.effective_capital in expected:
                    row["status"] = "ok"
                elif len(expected) == 1:
                    row["status"] = "mismatch"
                    row["expected_current_capital"] = expected[0]
                else:
                    row["status"] = "ambiguous_expected_current_capital"

            rows.append(row)
            status_counts[row["status"]] += 1

    return rows, status_counts


def summarize_by_title(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["current_title_id"]].append(row)

    summaries: list[dict[str, str]] = []
    for title_id, title_rows in sorted(grouped.items()):
        statuses = [row["status"] for row in title_rows]
        ok_rows = [row for row in title_rows if row["status"] == "ok"]
        mismatch_rows = [row for row in title_rows if row["status"] == "mismatch"]
        ambiguous_rows = [row for row in title_rows if row["status"] == "ambiguous_expected_current_capital"]
        missing_mapping_rows = [row for row in title_rows if row["status"] == "missing_expected_current_capital_mapping"]
        missing_effective_rows = [row for row in title_rows if row["status"] == "missing_effective_capital"]
        source_capitals = sorted({row["source_capital"] for row in title_rows if row.get("source_capital")})
        mismatch_expected = sorted(
            {
                row["expected_current_capital"]
                for row in mismatch_rows
                if row.get("expected_current_capital")
            }
        )
        ambiguous_expected = sorted(
            {
                token.strip()
                for row in ambiguous_rows
                for token in row.get("expected_current_capital_candidates", "").split("|")
                if token.strip()
            }
        )
        source_conflict_expected = []
        source_capital_signatures = set()
        for row in title_rows:
            if not row.get("source_capital"):
                continue
            candidates = [
                token.strip()
                for token in row.get("expected_current_capital_candidates", "").split("|")
                if token.strip()
            ]
            if candidates:
                signature = "/".join(sorted(candidates))
                source_conflict_expected.append(f"{row['selected_source_kind']}:{signature}")
            else:
                signature = f"{row['selected_source_kind']}:{row['source_capital']}?"
                source_conflict_expected.append(signature)
            source_capital_signatures.add(signature)
        source_conflict_rows = title_rows if len(source_capital_signatures) > 1 else []

        if source_conflict_rows:
            aggregate_status = "source_conflict"
        elif ok_rows:
            aggregate_status = "ok_via_some_source"
        elif mismatch_rows:
            aggregate_status = "mismatch_no_source_ok"
        elif ambiguous_rows:
            aggregate_status = "ambiguous_no_source_ok"
        elif missing_mapping_rows:
            aggregate_status = "missing_mapping_no_source_ok"
        elif missing_effective_rows:
            aggregate_status = "missing_effective_capital"
        else:
            aggregate_status = "needs_review"

        first = title_rows[0]
        summaries.append(
            {
                "aggregate_status": aggregate_status,
                "current_title_id": title_id,
                "current_title_path": first["current_title_path"],
                "current_title_line": first["current_title_line"],
                "current_capital": first["current_capital"],
                "current_capital_line": first["current_capital_line"],
                "current_capital_source": first["current_capital_source"],
                "current_direct_capital": first["current_direct_capital"],
                "title_source_origin_hint": first["title_source_origin_hint"],
                "mask_scope_change": first["mask_scope_change"],
                "candidate_count": str(len(title_rows)),
                "candidate_statuses": " | ".join(statuses),
                "ok_source_candidates": " | ".join(
                    f"{row['selected_source_kind']}:{row['selected_source_title_id']}" for row in ok_rows
                ),
                "mismatch_source_candidates": " | ".join(
                    f"{row['selected_source_kind']}:{row['selected_source_title_id']}->{row['expected_current_capital']}"
                    for row in mismatch_rows
                ),
                "mismatch_expected_current_capitals": " | ".join(mismatch_expected),
                "ambiguous_expected_current_capitals": " | ".join(ambiguous_expected),
                "source_conflict_capitals": " | ".join(source_capitals),
                "source_conflict_expected_capitals": " | ".join(sorted(set(source_conflict_expected))),
                "suggested_current_capital": mismatch_expected[0] if aggregate_status == "mismatch_no_source_ok" and len(mismatch_expected) == 1 else "",
                "suggestion_status": (
                    "single_expected_capital_candidate"
                    if aggregate_status == "mismatch_no_source_ok" and len(mismatch_expected) == 1
                    else ("multiple_expected_capital_candidates" if aggregate_status == "mismatch_no_source_ok" else "")
                ),
                "missing_mapping_source_capitals": " | ".join(
                    f"{row['selected_source_kind']}:{row['source_capital']}" for row in missing_mapping_rows
                ),
            }
        )

    return summaries


def base_row(
    title_id: str,
    current_block: TitleBlock,
    origin_info: dict[str, str],
    mod_tokens: list[str],
) -> dict[str, str]:
    return {
        "status": "",
        "current_title_id": title_id,
        "current_title_path": current_block.path,
        "current_title_line": str(current_block.start_line),
        "current_capital": current_block.effective_capital,
        "current_capital_line": str(current_block.effective_capital_line),
        "current_capital_source": current_block.effective_capital_source,
        "current_direct_capital": current_block.direct_capital,
        "current_direct_capital_line": str(current_block.direct_capital_line),
        "manual_mod_title_tokens": " | ".join(mod_tokens),
        "title_source_origin_hint": origin_info.get("title_source_origin", ""),
        "mask_scope_change": origin_info.get("mask_scope_change", ""),
        "mask_scope_reasons": origin_info.get("mask_scope_reasons", ""),
        "selected_source_kind": "",
        "selected_source_title_id": "",
        "source_title_path": "",
        "source_title_file": "",
        "source_title_line": "",
        "source_capital": "",
        "source_capital_line": "",
        "source_capital_source": "",
        "source_direct_capital": "",
        "source_direct_capital_line": "",
        "expected_current_capital": "",
        "expected_current_capital_candidates": "",
        "expected_current_capital_count": "",
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "status",
        "current_title_id",
        "current_title_path",
        "current_title_line",
        "current_capital",
        "current_capital_line",
        "current_capital_source",
        "current_direct_capital",
        "current_direct_capital_line",
        "manual_mod_title_tokens",
        "title_source_origin_hint",
        "mask_scope_change",
        "mask_scope_reasons",
        "selected_source_kind",
        "selected_source_title_id",
        "source_title_path",
        "source_title_file",
        "source_title_line",
        "source_capital",
        "source_capital_line",
        "source_capital_source",
        "source_direct_capital",
        "source_direct_capital_line",
        "expected_current_capital",
        "expected_current_capital_candidates",
        "expected_current_capital_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_title_summary_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "aggregate_status",
        "current_title_id",
        "current_title_path",
        "current_title_line",
        "current_capital",
        "current_capital_line",
        "current_capital_source",
        "current_direct_capital",
        "title_source_origin_hint",
        "mask_scope_change",
        "candidate_count",
        "candidate_statuses",
        "ok_source_candidates",
        "mismatch_source_candidates",
        "mismatch_expected_current_capitals",
        "ambiguous_expected_current_capitals",
        "source_conflict_capitals",
        "source_conflict_expected_capitals",
        "suggested_current_capital",
        "suggestion_status",
        "missing_mapping_source_capitals",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_manual_simple_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["title_id", "current_capital", "expected_capital", "status"]
    simple_rows: list[dict[str, str]] = []

    for row in rows:
        aggregate_status = row["aggregate_status"]
        if aggregate_status == "mismatch_no_source_ok":
            if row["suggestion_status"] == "single_expected_capital_candidate":
                status = "wrong"
                expected_capital = row["suggested_current_capital"]
            else:
                status = "ambiguous"
                expected_capital = row["mismatch_expected_current_capitals"]
        elif aggregate_status == "ambiguous_no_source_ok":
            status = "ambiguous"
            expected_capital = row["ambiguous_expected_current_capitals"]
        elif aggregate_status == "missing_mapping_no_source_ok":
            status = "uncertain"
            expected_capital = ""
        elif aggregate_status == "source_conflict":
            status = "source_conflict"
            expected_capital = row["source_conflict_expected_capitals"] or row["source_conflict_capitals"]
        elif aggregate_status == "missing_effective_capital":
            status = "missing_effective_capital"
            expected_capital = ""
        else:
            continue

        simple_rows.append(
            {
                "title_id": row["current_title_id"],
                "current_capital": row["current_capital"],
                "expected_capital": expected_capital,
                "status": status,
            }
        )

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(simple_rows)


def write_summary(
    path: Path,
    rows: list[dict[str, str]],
    title_summaries: list[dict[str, str]],
    status_counts: Counter[str],
) -> None:
    aggregate_counts = Counter(row["aggregate_status"] for row in title_summaries)
    high_signal = [row for row in title_summaries if row["aggregate_status"] == "mismatch_no_source_ok"]
    source_conflicts = [row for row in title_summaries if row["aggregate_status"] == "source_conflict"]
    lines = [
        "# Landed Title Capital Source Audit",
        "",
        f"- audited source-candidate rows: `{len(rows)}`",
        f"- audited current titles: `{len(title_summaries)}`",
        "",
        "## Source Candidate Status Counts",
        "",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Current Title Aggregate Counts", ""])
    for status, count in sorted(aggregate_counts.items()):
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(
        [
            "",
            "## High Signal",
            "",
            f"- titles with no validating source and effective-capital mismatch: `{len(high_signal)}`",
            f"- titles with conflicting source effective capitals: `{len(source_conflicts)}`",
            "- main report: `landed_title_capital_source_audit.csv`",
            "- title summary: `landed_title_capital_source_title_summary.csv`",
            "- manual simple report: `landed_title_capital_manual_simple.csv`",
            "- high-signal title mismatch report: `landed_title_capital_source_title_mismatches.csv`",
            "- source-conflict title report: `landed_title_capital_source_title_source_conflicts.csv`",
            "- source-candidate mismatch report: `landed_title_capital_source_candidate_mismatches.csv`",
            "",
            "## Method",
            "",
            "- audit target scope is `h_`, `e_`, `k_`, and `d_` titles",
            "- current effective capital is direct `capital = c_*`; if absent, first descendant county is used",
            "- source title is selected from the manual title relation and source-origin hint",
            "- source effective capital is read with the same direct-or-first-descendant rule",
            "- source effective capital is mapped back to current title id using `curated_title_relations.csv`",
            "- if multiple selected sources have different effective capitals, the title is flagged as `source_conflict` even if one source matches current",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    rows, status_counts = audit(args)
    title_summaries = summarize_by_title(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "landed_title_capital_source_audit.csv", rows)
    write_csv(
        args.output_dir / "landed_title_capital_source_candidate_mismatches.csv",
        [row for row in rows if row["status"] == "mismatch"],
    )
    write_csv(
        args.output_dir / "landed_title_capital_source_needs_review.csv",
        [row for row in rows if row["status"] not in {"ok", "source_has_no_direct_capital"}],
    )
    write_title_summary_csv(args.output_dir / "landed_title_capital_source_title_summary.csv", title_summaries)
    write_title_summary_csv(
        args.output_dir / "landed_title_capital_source_title_mismatches.csv",
        [row for row in title_summaries if row["aggregate_status"] == "mismatch_no_source_ok"],
    )
    write_title_summary_csv(
        args.output_dir / "landed_title_capital_source_title_source_conflicts.csv",
        [row for row in title_summaries if row["aggregate_status"] == "source_conflict"],
    )
    write_title_summary_csv(
        args.output_dir / "landed_title_capital_source_single_fix_candidates.csv",
        [row for row in title_summaries if row["suggestion_status"] == "single_expected_capital_candidate"],
    )
    write_manual_simple_csv(args.output_dir / "landed_title_capital_manual_simple.csv", title_summaries)
    write_summary(args.output_dir / "landed_title_capital_source_audit_summary.md", rows, title_summaries, status_counts)

    print(f"audited_rows={len(rows)}")
    print(f"audited_titles={len(title_summaries)}")
    print("status_counts=" + ", ".join(f"{key}:{value}" for key, value in sorted(status_counts.items())))
    print(f"summary={args.output_dir / 'landed_title_capital_source_audit_summary.md'}")


if __name__ == "__main__":
    main()
