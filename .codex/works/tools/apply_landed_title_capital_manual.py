from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path


TITLE_RE = re.compile(r"^(\s*)([hekdcb]_[A-Za-z0-9_'\-]+)\s*=\s*\{")
CAPITAL_RE = re.compile(r"^(\s*)capital\s*=\s*(c_[A-Za-z0-9_'\-]+)(.*)$")


@dataclass
class TitleBlock:
    title_id: str
    start_line: int
    end_line: int
    depth: int
    path: str
    indent: str
    direct_capital: str
    direct_capital_line: int
    effective_capital: str = ""
    effective_capital_line: int = 0
    effective_capital_source: str = ""


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Apply manually selected landed title capitals to current landed_titles."
    )
    parser.add_argument("--manual-csv", type=Path, default=repo_root / "landed_title_capital_manual_new.csv")
    parser.add_argument("--landed-titles", type=Path, default=repo_root / "common/landed_titles/00_landed_titles.txt")
    parser.add_argument(
        "--report",
        type=Path,
        default=repo_root
        / "works/analysis/generated/landed_title_capital_manual_apply/landed_title_capital_manual_apply_report.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=repo_root
        / "works/analysis/generated/landed_title_capital_manual_apply/landed_title_capital_manual_apply_summary.md",
    )
    return parser.parse_args()


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def parse_blocks(lines: list[str]) -> dict[str, TitleBlock]:
    blocks: dict[str, TitleBlock] = {}
    stack: list[dict[str, object]] = []
    depth = 0

    for index, line in enumerate(lines):
        clean = strip_comment(line)
        title_match = TITLE_RE.match(clean)
        if title_match:
            title_id = title_match.group(2)
            path_ids = [str(item["title_id"]) for item in stack] + [title_id]
            stack.append(
                {
                    "title_id": title_id,
                    "start_line": index + 1,
                    "depth": depth + 1,
                    "path": " > ".join(path_ids),
                    "indent": title_match.group(1),
                    "direct_capital": "",
                    "direct_capital_line": 0,
                }
            )

        capital_match = CAPITAL_RE.match(clean)
        if capital_match and stack:
            stack[-1]["direct_capital"] = capital_match.group(2)
            stack[-1]["direct_capital_line"] = index + 1

        depth += clean.count("{") - clean.count("}")
        while stack and depth < int(stack[-1]["depth"]):
            item = stack.pop()
            title_id = str(item["title_id"])
            blocks.setdefault(
                title_id,
                TitleBlock(
                    title_id=title_id,
                    start_line=int(item["start_line"]),
                    end_line=index + 1,
                    depth=int(item["depth"]),
                    path=str(item["path"]),
                    indent=str(item["indent"]),
                    direct_capital=str(item["direct_capital"]),
                    direct_capital_line=int(item["direct_capital_line"]),
                ),
            )

    return with_effective_capitals(blocks)


def with_effective_capitals(blocks: dict[str, TitleBlock]) -> dict[str, TitleBlock]:
    county_blocks = sorted(
        (block for block in blocks.values() if block.title_id.startswith("c_")),
        key=lambda block: block.start_line,
    )

    for block in blocks.values():
        if block.direct_capital:
            block.effective_capital = block.direct_capital
            block.effective_capital_line = block.direct_capital_line
            block.effective_capital_source = "direct"
            continue

        if block.title_id.startswith("c_"):
            block.effective_capital = block.title_id
            block.effective_capital_line = block.start_line
            block.effective_capital_source = "self_county"
            continue

        path_prefix = block.path + " > "
        first_county = next((county for county in county_blocks if county.path.startswith(path_prefix)), None)
        if first_county:
            block.effective_capital = first_county.title_id
            block.effective_capital_line = first_county.start_line
            block.effective_capital_source = "first_descendant_county"

    return blocks


def read_manual_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, skipinitialspace=True)
        ]


def replace_capital_line(line: str, selected_capital: str) -> str:
    match = CAPITAL_RE.match(line)
    if not match:
        raise ValueError(f"not a capital line: {line}")
    return f"{match.group(1)}capital = {selected_capital}{match.group(3)}"


def apply_rows(lines: list[str], manual_rows: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]]]:
    blocks = parse_blocks(lines)
    report_rows: list[dict[str, str]] = []
    insertions: list[tuple[int, str]] = []

    for row in manual_rows:
        title_id = row.get("title_id", "")
        selected_capital = row.get("yusseter_selected_capital", "")
        block = blocks.get(title_id)
        report_row = {
            "title_id": title_id,
            "current_capital_before": row.get("current_capital", ""),
            "selected_capital": selected_capital,
            "actual_direct_capital_before": block.direct_capital if block else "",
            "actual_effective_capital_before": block.effective_capital if block else "",
            "actual_effective_capital_source_before": block.effective_capital_source if block else "",
            "action": "",
            "line": str(block.direct_capital_line or block.start_line) if block else "",
            "note": "",
        }

        if not title_id:
            report_row["action"] = "skipped"
            report_row["note"] = "blank title_id"
        elif not selected_capital:
            report_row["action"] = "skipped"
            report_row["note"] = "blank selected capital"
        elif not block:
            report_row["action"] = "missing_title"
            report_row["note"] = "title not found in current landed_titles"
        elif block.direct_capital:
            if block.direct_capital == selected_capital:
                report_row["action"] = "kept"
            else:
                line_index = block.direct_capital_line - 1
                lines[line_index] = replace_capital_line(lines[line_index], selected_capital)
                report_row["action"] = "updated"
        elif block.effective_capital == selected_capital:
            report_row["action"] = "kept_effective"
            report_row["note"] = "no direct capital; descendant effective capital already matches"
        else:
            insert_line_index = block.start_line
            capital_line = f"{block.indent}\tcapital = {selected_capital}"
            insertions.append((insert_line_index, capital_line))
            report_row["action"] = "inserted"
            report_row["line"] = str(insert_line_index + 1)

        report_rows.append(report_row)

    for insert_line_index, capital_line in sorted(insertions, reverse=True):
        lines.insert(insert_line_index, capital_line)

    return lines, report_rows


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "title_id",
        "current_capital_before",
        "selected_capital",
        "actual_direct_capital_before",
        "actual_effective_capital_before",
        "actual_effective_capital_source_before",
        "action",
        "line",
        "note",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict[str, str]]) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["action"]] = counts.get(row["action"], 0) + 1

    lines = [
        "# Landed Title Capital Manual Apply",
        "",
        f"- rows: `{len(rows)}`",
        "",
        "## Action Counts",
        "",
    ]
    for action, count in sorted(counts.items()):
        lines.append(f"- `{action}`: `{count}`")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- report: `landed_title_capital_manual_apply_report.csv`",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    lines = args.landed_titles.read_text(encoding="utf-8-sig").splitlines()
    manual_rows = read_manual_rows(args.manual_csv)
    new_lines, report_rows = apply_rows(lines, manual_rows)
    args.landed_titles.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    write_report(args.report, report_rows)
    write_summary(args.summary, report_rows)

    counts: dict[str, int] = {}
    for row in report_rows:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    print("action_counts=" + ", ".join(f"{key}:{value}" for key, value in sorted(counts.items())))
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
