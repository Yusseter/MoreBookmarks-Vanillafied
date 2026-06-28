from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


TRANSFER_KEYS = [
    "definite_form",
    "ruler_uses_title_name",
    "can_be_named_after_dynasty",
    "disable_regnal_numbers",
    "landless",
    "personal_relation_vassal",
    "personal_relation_entry",
    "can_create",
    "can_create_on_partition",
    "can_destroy",
    "ai_primary_priority",
    "cultural_names",
]

TITLE_RE = re.compile(r"^\s*([hekdcb]_[A-Za-z0-9_]+)\s*=\s*\{")
KEY_RE_TEMPLATE = r"^\s*({})\s*="
TITLE_REF_RE = re.compile(r"\btitle:([hekdcb]_[A-Za-z0-9_]+)\b")


@dataclass
class TitleBlock:
    title_id: str
    start_line: int
    end_line: int
    start_depth: int


@dataclass
class PropertyBlock:
    key: str
    start_line: int
    end_line: int
    raw: str
    normalized: str


def strip_comment(line: str) -> str:
    in_quote = False
    escaped = False
    out: list[str] = []
    for ch in line:
        if ch == "\\" and in_quote:
            escaped = not escaped
            out.append(ch)
            continue
        if ch == '"' and not escaped:
            in_quote = not in_quote
        escaped = False
        if ch == "#" and not in_quote:
            break
        out.append(ch)
    return "".join(out)


def brace_delta(line: str) -> int:
    clean = strip_comment(line)
    return clean.count("{") - clean.count("}")


def normalize_block(text: str) -> str:
    parts: list[str] = []
    for line in text.splitlines():
        clean = strip_comment(line).strip()
        if clean:
            parts.append(re.sub(r"\s+", " ", clean))
    return "\n".join(parts)


def one_line_preview(text: str, max_len: int = 300) -> str:
    preview = " ".join(line.strip() for line in text.splitlines() if line.strip())
    preview = re.sub(r"\s+", " ", preview)
    if len(preview) > max_len:
        return preview[: max_len - 3] + "..."
    return preview


def parse_title_blocks(lines: list[str]) -> dict[str, TitleBlock]:
    blocks: dict[str, TitleBlock] = {}
    stack: list[tuple[str, int, int]] = []
    depth = 0

    for idx, line in enumerate(lines):
        match = TITLE_RE.match(strip_comment(line))
        if match:
            title_id = match.group(1)
            stack.append((title_id, idx, depth))

        delta = brace_delta(line)
        old_depth = depth
        depth += delta

        if delta < 0:
            while stack and depth <= stack[-1][2]:
                title_id, start_idx, start_depth = stack.pop()
                blocks[title_id] = TitleBlock(
                    title_id=title_id,
                    start_line=start_idx + 1,
                    end_line=idx + 1,
                    start_depth=start_depth,
                )

        if depth < 0:
            raise ValueError(f"Brace depth became negative at line {idx + 1}; old depth {old_depth}")

    if stack:
        open_titles = ", ".join(title for title, _, _ in stack[-10:])
        raise ValueError(f"Unclosed title blocks remain: {open_titles}")
    return blocks


def extract_properties(lines: list[str], block: TitleBlock, keys: list[str]) -> dict[str, PropertyBlock]:
    key_pattern = re.compile(KEY_RE_TEMPLATE.format("|".join(re.escape(k) for k in keys)))
    wanted_depth = block.start_depth + 1
    props: dict[str, PropertyBlock] = {}
    depth = block.start_depth + 1
    idx = block.start_line
    end_idx = block.end_line - 1

    while idx < end_idx:
        line = lines[idx]
        clean = strip_comment(line)
        match = key_pattern.match(clean)
        if depth == wanted_depth and match:
            key = match.group(1)
            prop_start = idx
            prop_end = idx
            delta = brace_delta(line)

            if "{" in clean:
                prop_depth = depth + delta
                prop_end = idx
                while prop_depth > wanted_depth and prop_end + 1 < end_idx:
                    prop_end += 1
                    prop_depth += brace_delta(lines[prop_end])
            raw = "".join(lines[prop_start : prop_end + 1])
            props.setdefault(
                key,
                PropertyBlock(
                    key=key,
                    start_line=prop_start + 1,
                    end_line=prop_end + 1,
                    raw=raw,
                    normalized=normalize_block(raw),
                ),
            )
            for consumed in range(prop_start, prop_end + 1):
                if consumed == idx:
                    continue
            depth += sum(brace_delta(lines[i]) for i in range(idx, prop_end + 1))
            idx = prop_end + 1
            continue

        depth += brace_delta(line)
        idx += 1

    return props


def load_relations(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            row = {str(k).strip(): (v or "").strip() for k, v in raw_row.items()}
            if row.get("source_title_id") and row.get("mod_title_id"):
                rows.append(row)
    return rows


def resolve_title_refs(raw: str, relation_map: dict[str, str], target_titles: set[str]) -> tuple[list[str], list[str], list[str]]:
    refs = sorted(set(TITLE_REF_RE.findall(raw)))
    mapped: list[str] = []
    unmapped: list[str] = []
    for ref in refs:
        if ref in relation_map:
            mapped.append(f"title:{ref}=title:{relation_map[ref]}")
        elif ref in target_titles:
            mapped.append(f"title:{ref}=title:{ref}")
        else:
            unmapped.append(f"title:{ref}")
    return [f"title:{ref}" for ref in refs], mapped, unmapped


def review_comment_for(key: str, source_present: bool, has_title_ref: bool) -> str:
    if not source_present:
        return ""
    if key == "cultural_names":
        return "# Yusseter: REVIEW_ASIL_MOD_CULTURAL_NAMES"
    if has_title_ref:
        return "# Yusseter: REVIEW_ASIL_MOD_TITLE_REF"
    return ""


def recommendation_for(status: str, unmapped_refs: list[str], review_comment: str) -> str:
    if status in {"asil_mod_title_missing", "target_title_missing", "asil_mod_key_missing"}:
        return "no_insert_asil_mod_or_target_missing"
    if unmapped_refs:
        return "manual_review_unmapped_title_ref"
    if status == "same":
        return "no_action_same"
    if status == "target_key_missing":
        return "insert_missing_with_review_comment" if review_comment else "insert_missing"
    if status == "different":
        return "report_difference_no_overwrite"
    return "manual_review"


def build_report(args: argparse.Namespace) -> tuple[list[dict[str, str]], Counter]:
    source_landed = args.source_root / "common" / "landed_titles" / "00_landed_titles.txt"
    target_landed = args.target_root / "common" / "landed_titles" / "00_landed_titles.txt"
    relation_csv = args.target_root / "title_relation_master_manuel_new.csv"

    source_lines = source_landed.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    target_lines = target_landed.read_text(encoding="utf-8-sig").splitlines(keepends=True)

    source_titles = parse_title_blocks(source_lines)
    target_titles = parse_title_blocks(target_lines)
    relations = load_relations(relation_csv)
    # For this transfer, the effective current-state direction is:
    # CSV mod_title_id = asil mod title, CSV source_title_id = Yusseter target title.
    relation_map = {row["mod_title_id"]: row["source_title_id"] for row in relations}

    source_props_cache: dict[str, dict[str, PropertyBlock]] = {}
    target_props_cache: dict[str, dict[str, PropertyBlock]] = {}
    rows: list[dict[str, str]] = []
    counts: Counter = Counter()

    for relation in relations:
        source_id = relation["mod_title_id"]
        target_id = relation["source_title_id"]
        source_block = source_titles.get(source_id)
        target_block = target_titles.get(target_id)

        if source_block and source_id not in source_props_cache:
            source_props_cache[source_id] = extract_properties(source_lines, source_block, TRANSFER_KEYS)
        if target_block and target_id not in target_props_cache:
            target_props_cache[target_id] = extract_properties(target_lines, target_block, TRANSFER_KEYS)

        for key in TRANSFER_KEYS:
            source_prop = source_props_cache.get(source_id, {}).get(key)
            target_prop = target_props_cache.get(target_id, {}).get(key)

            if not source_block:
                status = "asil_mod_title_missing"
            elif not target_block:
                status = "target_title_missing"
            elif not source_prop:
                status = "asil_mod_key_missing"
            elif not target_prop:
                status = "target_key_missing"
            elif source_prop.normalized == target_prop.normalized:
                status = "same"
            else:
                status = "different"

            refs: list[str] = []
            mapped_refs: list[str] = []
            unmapped_refs: list[str] = []
            if source_prop:
                refs, mapped_refs, unmapped_refs = resolve_title_refs(
                    source_prop.raw,
                    relation_map,
                    set(target_titles),
                )
            review_comment = review_comment_for(key, bool(source_prop), bool(refs))
            recommendation = recommendation_for(status, unmapped_refs, review_comment)

            counts[status] += 1
            counts[f"key:{key}:{status}"] += 1
            rows.append(
                {
                    "csv_source_title_id": relation["source_title_id"],
                    "csv_mod_title_id": relation["mod_title_id"],
                    "asil_mod_title_id": source_id,
                    "target_title_id": target_id,
                    "is_same_title_id": relation.get("is_same_title_id", ""),
                    "mask_scope_change": relation.get("mask_scope_change", ""),
                    "key": key,
                    "status": status,
                    "recommendation": recommendation,
                    "asil_mod_line": str(source_prop.start_line if source_prop else source_block.start_line if source_block else ""),
                    "target_line": str(target_prop.start_line if target_prop else target_block.start_line if target_block else ""),
                    "asil_mod_present": "yes" if source_prop else "no",
                    "target_present": "yes" if target_prop else "no",
                    "has_title_ref": "yes" if refs else "no",
                    "title_refs": ";".join(refs),
                    "mapped_title_refs": ";".join(mapped_refs),
                    "unmapped_title_refs": ";".join(unmapped_refs),
                    "review_comment": review_comment,
                    "asil_mod_preview": one_line_preview(source_prop.raw) if source_prop else "",
                    "target_preview": one_line_preview(target_prop.raw) if target_prop else "",
                }
            )

    return rows, counts


def write_outputs(rows: list[dict[str, str]], counts: Counter, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "landed_title_asil_mod_metadata_transfer_dry_run.csv"
    summary_path = output_dir / "landed_title_asil_mod_metadata_transfer_summary.md"

    fieldnames = [
        "csv_source_title_id",
        "csv_mod_title_id",
        "asil_mod_title_id",
        "target_title_id",
        "is_same_title_id",
        "mask_scope_change",
        "key",
        "status",
        "recommendation",
        "asil_mod_line",
        "target_line",
        "asil_mod_present",
        "target_present",
        "has_title_ref",
        "title_refs",
        "mapped_title_refs",
        "unmapped_title_refs",
        "review_comment",
        "asil_mod_preview",
        "target_preview",
    ]

    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    status_lines = [f"- `{status}`: {count}" for status, count in sorted(counts.items()) if not status.startswith("key:")]
    key_lines: list[str] = []
    for key in TRANSFER_KEYS:
        parts = []
        for status in sorted({row["status"] for row in rows}):
            count = counts.get(f"key:{key}:{status}", 0)
            if count:
                parts.append(f"{status}={count}")
        key_lines.append(f"- `{key}`: " + ", ".join(parts))

    summary_path.write_text(
        "\n".join(
            [
                "# Landed Title Asil Mod Metadata Transfer Dry Run",
                "",
                f"- total_rows: {total}",
                f"- transfer_keys: {', '.join(TRANSFER_KEYS)}",
                f"- report: `{report_path.name}`",
                "",
                "## Status Counts",
                *status_lines,
                "",
                "## Key Counts",
                *key_lines,
                "",
                "## Notes",
                "- This is dry-run only; landed title source files are not modified.",
                "- Existing target values are reported as `different`; they are not overwritten.",
                "- `cultural_names` rows use `# Yusseter: REVIEW_ASIL_MOD_CULTURAL_NAMES` in the review_comment column.",
                "- Asil mod blocks containing `title:*` references use `# Yusseter: REVIEW_ASIL_MOD_TITLE_REF` in the review_comment column.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    target_root = script_path.parents[2]
    crusader_kings_root = target_root.parent.parent
    source_root = crusader_kings_root / "Leviathonlx MoreBookmarks-Plus" / "BookmarksGit"
    output_dir = target_root / "works" / "analysis" / "generated" / "landed_title_asil_mod_metadata_transfer"

    parser = argparse.ArgumentParser(
        description="Build a dry-run report for transferring selected landed title metadata from asil mod equivalents.",
    )
    parser.add_argument("--target-root", type=Path, default=target_root)
    parser.add_argument("--source-root", type=Path, default=source_root)
    parser.add_argument("--output-dir", type=Path, default=output_dir)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows, counts = build_report(args)
    write_outputs(rows, counts, args.output_dir)
    print(f"rows={len(rows)}")
    for status, count in sorted(counts.items()):
        if not status.startswith("key:"):
            print(f"{status}={count}")
    print(f"output_dir={args.output_dir}")


if __name__ == "__main__":
    main()
