from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image


TITLE_RE = re.compile(r"^(\s*)([hekdcb]_[A-Za-z0-9_'\-]+)\s*=\s*\{")
CAPITAL_RE = re.compile(r"^\s*capital\s*=\s*(c_[A-Za-z0-9_'\-]+)\b")
PROVINCE_RE = re.compile(r"^\s*province\s*=\s*(\d+)\b")
NO_COUNTERPART = "*there_is_no*"


@dataclass
class TitleBlock:
    title_id: str
    source_file: str
    start_line: int
    end_line: int
    parent_id: str
    root_title: str
    path: str
    direct_capital: str = ""
    direct_capital_line: int = 0
    effective_capital: str = ""
    effective_capital_line: int = 0
    effective_capital_source: str = ""
    direct_body_lines: list[str] = field(default_factory=list)
    direct_province_ids: list[int] = field(default_factory=list)
    descendant_province_ids: list[int] = field(default_factory=list)


@dataclass
class SourceCandidate:
    source_kind: str
    source_title_id: str
    block: TitleBlock
    body_ratio: float
    body_match: str
    capital_match: str
    expected_capitals: list[str]
    score: int
    score_reasons: list[str]


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    mod_root = project_root / "BookmarksGit"
    works_root = project_root / "development"
    parser = argparse.ArgumentParser(
        description="Infer landed title source identity using block metadata, capital, and province provenance."
    )
    parser.add_argument("--current-landed-titles", type=Path, default=mod_root / "common/landed_titles/00_landed_titles.txt")
    parser.add_argument("--definition", type=Path, default=mod_root / "map_data/definition.csv")
    parser.add_argument(
        "--relation-csv",
        "--manual-csv",
        dest="manual_csv",
        type=Path,
        default=works_root
        / "pipeline_inputs/title_relations/curated_title_relations.csv",
    )
    parser.add_argument(
        "--east-mask",
        type=Path,
        default=works_root
        / "pipeline_inputs/map/scopes/east_title_scope_2026-04-19.png",
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
        "--mod-tracking",
        type=Path,
        default=works_root
        / "analysis/generated/province_definition/final_modlu_tracking_preserve_old_ids.csv",
    )
    parser.add_argument(
        "--orijinal-tracking",
        type=Path,
        default=works_root
        / "analysis/generated/province_definition/final_orijinal_tracking_preserve_old_ids.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=works_root / "analysis/generated/landed_title_source_identity",
    )
    parser.add_argument(
        "--scope-title-csv",
        type=Path,
        default=works_root
        / "analysis/generated/east_kingdom_closure_scope/east_kingdom_closure_titles.csv",
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
            title_id = title_match.group(2)
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
                    "direct_body_lines": [],
                    "direct_province_ids": [],
                }
            )
        elif stack:
            stripped = clean.strip()
            if stripped and stripped not in {"{", "}"}:
                stack[-1]["direct_body_lines"].append(clean)

        capital_match = CAPITAL_RE.match(clean)
        if capital_match and stack:
            stack[-1]["direct_capital"] = capital_match.group(1)
            stack[-1]["direct_capital_line"] = index + 1

        province_match = PROVINCE_RE.match(clean)
        if province_match and stack:
            stack[-1]["direct_province_ids"].append(int(province_match.group(1)))

        depth += clean.count("{") - clean.count("}")
        while stack and depth < int(stack[-1]["depth"]):
            item = stack.pop()
            title_id = str(item["title_id"])
            blocks.setdefault(
                title_id,
                TitleBlock(
                    title_id=title_id,
                    source_file=str(path),
                    start_line=int(item["start_line"]),
                    end_line=index + 1,
                    parent_id=str(item["parent_id"]),
                    root_title=str(item["root_title"]),
                    path=str(item["path"]),
                    direct_capital=str(item["direct_capital"]),
                    direct_capital_line=int(item["direct_capital_line"]),
                    direct_body_lines=list(item["direct_body_lines"]),
                    direct_province_ids=list(item["direct_province_ids"]),
                ),
            )

    return finalize_blocks(blocks)


def parse_landed_titles_path(path: Path) -> dict[str, TitleBlock]:
    if path.is_file():
        return parse_landed_title_file(path)

    merged: dict[str, TitleBlock] = {}
    for file_path in sorted(path.glob("*.txt")):
        for title_id, block in parse_landed_title_file(file_path).items():
            merged.setdefault(title_id, block)
    return finalize_blocks(merged)


def finalize_blocks(blocks: dict[str, TitleBlock]) -> dict[str, TitleBlock]:
    county_blocks = sorted(
        (block for block in blocks.values() if block.title_id.startswith("c_")),
        key=lambda block: block.start_line,
    )

    descendant_map: dict[str, list[int]] = defaultdict(list)
    for block in blocks.values():
        if not block.title_id.startswith("b_") or not block.direct_province_ids:
            continue
        for title_id in block.path.split(" > "):
            descendant_map[title_id].extend(block.direct_province_ids)

    for block in blocks.values():
        block.descendant_province_ids = descendant_map.get(block.title_id, [])
        if block.direct_capital:
            block.effective_capital = block.direct_capital
            block.effective_capital_line = block.direct_capital_line
            block.effective_capital_source = "direct"
        elif block.title_id.startswith("c_"):
            block.effective_capital = block.title_id
            block.effective_capital_line = block.start_line
            block.effective_capital_source = "self_county"
        else:
            path_prefix = block.path + " > "
            first_county = next((county for county in county_blocks if county.path.startswith(path_prefix)), None)
            if first_county:
                block.effective_capital = first_county.title_id
                block.effective_capital_line = first_county.start_line
                block.effective_capital_source = "first_descendant_county"

    return blocks


def split_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for raw in value.split("&"):
        token = raw.replace("(second)", "").strip()
        if not token or token == NO_COUNTERPART:
            continue
        tokens.append(token)
    return tokens


def read_manual_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, skipinitialspace=True)
            if (row.get("source_title_id") or "").strip()
        ]


def read_scope_title_ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        title_ids = []
        for row in csv.DictReader(handle, skipinitialspace=True):
            title_id = (row.get("title_id") or "").strip()
            if title_id:
                title_ids.append(title_id)
        return title_ids


def read_mod_reverse_mapping(path: Path) -> dict[str, list[str]]:
    return build_mod_reverse_mapping(read_manual_rows(path))


def build_mod_reverse_mapping(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        current_id = row["source_title_id"]
        for token in split_tokens(row.get("mod_title_id", "")):
            if current_id not in reverse[token]:
                reverse[token].append(current_id)
    return dict(reverse)


def read_definition_rgb_map(path: Path) -> dict[tuple[int, int, int], int]:
    rgb_to_id: dict[tuple[int, int, int], int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        for row in reader:
            if len(row) < 4:
                continue
            try:
                province_id = int(row[0])
                rgb = (int(row[1]), int(row[2]), int(row[3]))
            except ValueError:
                continue
            rgb_to_id[rgb] = province_id
    return rgb_to_id


def read_mask_province_ids(mask_path: Path, definition_path: Path) -> tuple[set[int], int, int]:
    rgb_to_id = read_definition_rgb_map(definition_path)
    image = Image.open(mask_path).convert("RGB")
    colors = set(image.getdata())
    non_black = {rgb for rgb in colors if rgb != (0, 0, 0)}
    province_ids = {rgb_to_id[rgb] for rgb in non_black if rgb in rgb_to_id}
    unmatched_count = len([rgb for rgb in non_black if rgb not in rgb_to_id])
    return province_ids, len(non_black), unmatched_count


def read_tracking_sources(mod_path: Path, orijinal_path: Path) -> dict[int, str]:
    id_sources: dict[int, set[str]] = defaultdict(set)
    for path, source in [(mod_path, "modlu_kalan"), (orijinal_path, "orijinal_dogu")]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                value = row.get("final_new_id") or ""
                if not value:
                    continue
                try:
                    province_id = int(value)
                except ValueError:
                    continue
                id_sources[province_id].add(source)

    result: dict[int, str] = {}
    for province_id, sources in id_sources.items():
        if sources == {"modlu_kalan"}:
            result[province_id] = "modlu_kalan"
        elif sources == {"orijinal_dogu"}:
            result[province_id] = "orijinal_dogu"
        else:
            result[province_id] = "shared_tracking"
    return result


def normalize_body(lines: list[str]) -> str:
    normalized: list[str] = []
    for line in lines:
        clean = strip_comment(line).strip()
        if not clean or CAPITAL_RE.match(clean):
            continue
        clean = re.sub(r"\s+", " ", clean)
        normalized.append(clean)
    return "\n".join(normalized)


def body_ratio(current_block: TitleBlock, source_block: TitleBlock) -> float:
    current_body = normalize_body(current_block.direct_body_lines)
    source_body = normalize_body(source_block.direct_body_lines)
    if not current_body and not source_body:
        return 1.0
    if not current_body or not source_body:
        return 0.0
    return SequenceMatcher(None, current_body, source_body).ratio()


def body_match_label(ratio: float) -> str:
    if ratio >= 0.995:
        return "exact"
    if ratio >= 0.85:
        return "high"
    if ratio >= 0.65:
        return "partial"
    return "low"


def expected_current_capitals(
    source_kind: str,
    source_capital: str,
    current_blocks: dict[str, TitleBlock],
    mod_to_current: dict[str, list[str]],
) -> list[str]:
    if not source_capital:
        return []
    if source_kind == "modlu_kalan":
        return mod_to_current.get(source_capital, [])
    if source_capital in current_blocks:
        return [source_capital]
    return []


def build_candidate(
    source_kind: str,
    source_title_id: str,
    source_block: TitleBlock,
    current_block: TitleBlock,
    current_blocks: dict[str, TitleBlock],
    mod_to_current: dict[str, list[str]],
    province_majority: str,
) -> SourceCandidate:
    ratio = body_ratio(current_block, source_block)
    match_label = body_match_label(ratio)
    expected = expected_current_capitals(source_kind, source_block.effective_capital, current_blocks, mod_to_current)
    capital_match = "yes" if current_block.effective_capital and current_block.effective_capital in expected else "no"
    score = 0
    reasons: list[str] = []

    if match_label == "exact":
        score += 4
        reasons.append("body_exact")
    elif match_label == "high":
        score += 2
        reasons.append("body_high")
    elif match_label == "partial":
        score += 1
        reasons.append("body_partial")

    if capital_match == "yes":
        score += 3
        reasons.append("capital_match")

    if province_majority == source_kind:
        score += 2
        reasons.append("province_majority")

    return SourceCandidate(
        source_kind=source_kind,
        source_title_id=source_title_id,
        block=source_block,
        body_ratio=ratio,
        body_match=match_label,
        capital_match=capital_match,
        expected_capitals=expected,
        score=score,
        score_reasons=reasons,
    )


def choose_best(candidates: list[SourceCandidate], source_kind: str) -> SourceCandidate | None:
    subset = [candidate for candidate in candidates if candidate.source_kind == source_kind]
    if not subset:
        return None
    return sorted(subset, key=lambda item: (item.score, item.body_ratio), reverse=True)[0]


def decide_source(
    mod_best: SourceCandidate | None,
    vanilla_best: SourceCandidate | None,
    province_majority: str,
) -> tuple[str, str, str]:
    mod_score = mod_best.score if mod_best else -1
    vanilla_score = vanilla_best.score if vanilla_best else -1
    reasons: list[str] = []
    if mod_best:
        reasons.append("mod:" + "+".join(mod_best.score_reasons or ["candidate"]))
    if vanilla_best:
        reasons.append("vanilla:" + "+".join(vanilla_best.score_reasons or ["candidate"]))
    if province_majority:
        reasons.append(f"province_majority:{province_majority}")

    if mod_best and not vanilla_best:
        confidence = "high" if mod_score >= 5 else ("medium" if mod_score >= 2 else "low")
        return "modlu_kalan", confidence, "; ".join(reasons)
    if vanilla_best and not mod_best:
        confidence = "high" if vanilla_score >= 5 else ("medium" if vanilla_score >= 2 else "low")
        return "orijinal_dogu", confidence, "; ".join(reasons)
    if not mod_best and not vanilla_best:
        return "manual_review", "none", "no_source_candidate"

    diff = mod_score - vanilla_score
    if diff >= 3:
        confidence = "high" if mod_score >= 6 else "medium"
        return "modlu_kalan", confidence, "; ".join(reasons)
    if diff <= -3:
        confidence = "high" if vanilla_score >= 6 else "medium"
        return "orijinal_dogu", confidence, "; ".join(reasons)

    if province_majority == "modlu_kalan" and mod_score > vanilla_score:
        return "modlu_kalan", "medium", "; ".join(reasons + ["close_score_confirmed_by_province_majority"])
    if province_majority == "orijinal_dogu" and vanilla_score > mod_score:
        return "orijinal_dogu", "medium", "; ".join(reasons + ["close_score_confirmed_by_province_majority"])
    if province_majority in {"modlu_kalan", "orijinal_dogu"} and mod_score == vanilla_score:
        return province_majority, "low", "; ".join(reasons + ["tie_broken_by_province_majority"])

    return "manual_review", "low", "; ".join(reasons + ["close_or_conflicting_signals"])


def source_counts_for_block(
    block: TitleBlock,
    mask_province_ids: set[int],
    province_sources: dict[int, str],
) -> tuple[Counter[str], str, list[int]]:
    ids = [province_id for province_id in block.descendant_province_ids if province_id in mask_province_ids]
    counts: Counter[str] = Counter()
    for province_id in ids:
        counts[province_sources.get(province_id, "unknown")] += 1

    mod_count = counts["modlu_kalan"]
    orijinal_count = counts["orijinal_dogu"]
    if mod_count > orijinal_count:
        majority = "modlu_kalan"
    elif orijinal_count > mod_count:
        majority = "orijinal_dogu"
    elif mod_count or orijinal_count:
        majority = "tied"
    else:
        majority = ""
    return counts, majority, ids


def audit(args: argparse.Namespace) -> tuple[list[dict[str, str]], dict[str, int]]:
    current_blocks = parse_landed_titles_path(args.current_landed_titles)
    mod_blocks = parse_landed_titles_path(args.mod_landed_titles_dir)
    vanilla_blocks = parse_landed_titles_path(args.vanilla_landed_titles_dir)
    manual_rows = read_manual_rows(args.manual_csv)
    existing_manual_ids = {row["source_title_id"] for row in manual_rows}
    for title_id in read_scope_title_ids(args.scope_title_csv):
        if title_id.startswith("b_") or title_id in existing_manual_ids:
            continue
        manual_rows.append(
            {
                "source_title_id": title_id,
                "mod_title_id": title_id if title_id in mod_blocks else "",
                "is_same_title_id": "",
                "mask_scope_change": "east_kingdom_closure_added",
            }
        )
        existing_manual_ids.add(title_id)
    mod_to_current = build_mod_reverse_mapping(manual_rows)
    mask_province_ids, mask_rgb_count, unmatched_rgb_count = read_mask_province_ids(args.east_mask, args.definition)
    province_sources = read_tracking_sources(args.mod_tracking, args.orijinal_tracking)

    output_rows: list[dict[str, str]] = []
    for manual_row in manual_rows:
        title_id = manual_row["source_title_id"]
        if title_id.startswith("b_"):
            continue
        current_block = current_blocks.get(title_id)
        if not current_block:
            output_rows.append(
                {
                    "title_id": title_id,
                    "source_decision": "manual_review",
                    "confidence": "none",
                    "decision_reason": "missing_current_title",
                }
            )
            continue

        province_counts, province_majority, mask_descendant_ids = source_counts_for_block(
            current_block, mask_province_ids, province_sources
        )

        candidates: list[SourceCandidate] = []
        for token in split_tokens(manual_row.get("mod_title_id", "")):
            source_block = mod_blocks.get(token)
            if source_block:
                candidates.append(
                    build_candidate(
                        "modlu_kalan",
                        token,
                        source_block,
                        current_block,
                        current_blocks,
                        mod_to_current,
                        province_majority,
                    )
                )

        vanilla_block = vanilla_blocks.get(title_id)
        if vanilla_block:
            candidates.append(
                build_candidate(
                    "orijinal_dogu",
                    title_id,
                    vanilla_block,
                    current_block,
                    current_blocks,
                    mod_to_current,
                    province_majority,
                )
            )

        mod_best = choose_best(candidates, "modlu_kalan")
        vanilla_best = choose_best(candidates, "orijinal_dogu")
        decision, confidence, reason = decide_source(mod_best, vanilla_best, province_majority)

        output_rows.append(
            {
                "title_id": title_id,
                "tier": title_id.split("_", 1)[0],
                "current_parent": current_block.parent_id,
                "current_path": current_block.path,
                "current_line": str(current_block.start_line),
                "manual_mod_title_tokens": " | ".join(split_tokens(manual_row.get("mod_title_id", ""))),
                "mod_best_title": mod_best.source_title_id if mod_best else "",
                "mod_best_parent": mod_best.block.parent_id if mod_best else "",
                "mod_body_match": mod_best.body_match if mod_best else "",
                "mod_body_ratio": f"{mod_best.body_ratio:.6f}" if mod_best else "",
                "mod_capital": mod_best.block.effective_capital if mod_best else "",
                "mod_capital_expected_current": " | ".join(mod_best.expected_capitals) if mod_best else "",
                "mod_capital_match": mod_best.capital_match if mod_best else "",
                "mod_score": str(mod_best.score) if mod_best else "",
                "vanilla_title": vanilla_best.source_title_id if vanilla_best else "",
                "vanilla_parent": vanilla_best.block.parent_id if vanilla_best else "",
                "vanilla_body_match": vanilla_best.body_match if vanilla_best else "",
                "vanilla_body_ratio": f"{vanilla_best.body_ratio:.6f}" if vanilla_best else "",
                "vanilla_capital": vanilla_best.block.effective_capital if vanilla_best else "",
                "vanilla_capital_expected_current": " | ".join(vanilla_best.expected_capitals) if vanilla_best else "",
                "vanilla_capital_match": vanilla_best.capital_match if vanilla_best else "",
                "vanilla_score": str(vanilla_best.score) if vanilla_best else "",
                "mask_descendant_province_count": str(len(mask_descendant_ids)),
                "province_modlu_count": str(province_counts["modlu_kalan"]),
                "province_orijinal_count": str(province_counts["orijinal_dogu"]),
                "province_shared_tracking_count": str(province_counts["shared_tracking"]),
                "province_unknown_count": str(province_counts["unknown"]),
                "province_majority": province_majority,
                "source_decision": decision,
                "confidence": confidence,
                "decision_reason": reason,
            }
        )

    metadata = {
        "mask_rgb_count": mask_rgb_count,
        "mask_unmatched_rgb_count": unmatched_rgb_count,
        "mask_province_count": len(mask_province_ids),
    }
    return output_rows, metadata


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(output_dir: Path, rows: list[dict[str, str]], metadata: dict[str, int]) -> None:
    fieldnames = [
        "title_id",
        "tier",
        "current_parent",
        "current_path",
        "current_line",
        "manual_mod_title_tokens",
        "mod_best_title",
        "mod_best_parent",
        "mod_body_match",
        "mod_body_ratio",
        "mod_capital",
        "mod_capital_expected_current",
        "mod_capital_match",
        "mod_score",
        "vanilla_title",
        "vanilla_parent",
        "vanilla_body_match",
        "vanilla_body_ratio",
        "vanilla_capital",
        "vanilla_capital_expected_current",
        "vanilla_capital_match",
        "vanilla_score",
        "mask_descendant_province_count",
        "province_modlu_count",
        "province_orijinal_count",
        "province_shared_tracking_count",
        "province_unknown_count",
        "province_majority",
        "source_decision",
        "confidence",
        "decision_reason",
    ]
    write_csv(output_dir / "landed_title_source_identity_audit.csv", rows, fieldnames)
    write_csv(
        output_dir / "landed_title_source_identity_manual_simple.csv",
        [
            {
                "title_id": row["title_id"],
                "source_decision": row["source_decision"],
                "confidence": row["confidence"],
                "reason": row["decision_reason"],
            }
            for row in rows
        ],
        ["title_id", "source_decision", "confidence", "reason"],
    )
    write_csv(
        output_dir / "landed_title_source_identity_review.csv",
        [row for row in rows if row["source_decision"] == "manual_review" or row["confidence"] in {"none", "low"}],
        fieldnames,
    )

    decision_counts = Counter(row["source_decision"] for row in rows)
    confidence_counts = Counter(row["confidence"] for row in rows)
    lines = [
        "# Landed Title Source Identity Audit",
        "",
        f"- rows: `{len(rows)}`",
        f"- mask non-black RGB: `{metadata['mask_rgb_count']}`",
        f"- mask province IDs: `{metadata['mask_province_count']}`",
        f"- mask unmatched RGB: `{metadata['mask_unmatched_rgb_count']}`",
        "",
        "## Source Decision Counts",
        "",
    ]
    for key, value in sorted(decision_counts.items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Confidence Counts", ""])
    for key, value in sorted(confidence_counts.items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- detailed audit: `landed_title_source_identity_audit.csv`",
            "- simple manual view: `landed_title_source_identity_manual_simple.csv`",
            "- review subset: `landed_title_source_identity_review.csv`",
        ]
    )
    (output_dir / "landed_title_source_identity_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    rows, metadata = audit(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_outputs(args.output_dir, rows, metadata)
    print(f"rows={len(rows)}")
    print("source_decisions=" + ", ".join(f"{key}:{value}" for key, value in sorted(Counter(row["source_decision"] for row in rows).items())))
    print("confidence=" + ", ".join(f"{key}:{value}" for key, value in sorted(Counter(row["confidence"] for row in rows).items())))
    print(f"summary={args.output_dir / 'landed_title_source_identity_summary.md'}")


if __name__ == "__main__":
    main()
