from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import build_landed_title_asil_mod_metadata_transfer_dry_run as dry


NAME_LIST_ENTRY_RE = re.compile(r"^(\s*)(name_list_[A-Za-z0-9_]+)\s*=\s*([^#\s]+)")


@dataclass
class PendingChange:
    action: str
    asil_mod_title_id: str
    target_title_id: str
    key: str
    raw: str
    review_comment: str
    source_line: int
    start_index: int
    end_index: int
    merge_lines: list[str] | None = None


def detect_newline(lines: list[str]) -> str:
    for line in lines:
        if line.endswith("\r\n"):
            return "\r\n"
        if line.endswith("\n"):
            return "\n"
    return "\n"


def leading_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def target_property_indent(block: dry.TitleBlock) -> str:
    return "\t" * (block.start_depth + 1)


def reindent_block(raw: str, target_indent: str, newline: str) -> list[str]:
    raw_lines = raw.splitlines(keepends=True)
    nonempty = [line for line in raw_lines if line.strip()]
    source_indent = leading_indent(nonempty[0]) if nonempty else ""
    result: list[str] = []

    for line in raw_lines:
        line_body = line.rstrip("\r\n")
        line_newline = newline if line.endswith(("\n", "\r\n")) else newline
        if not line_body.strip():
            result.append(line_newline)
            continue
        if source_indent and line_body.startswith(source_indent):
            suffix = line_body[len(source_indent) :]
        else:
            suffix = line_body.lstrip(" \t")
        result.append(target_indent + suffix + line_newline)
    return result


def remap_title_refs(raw: str, relation_map: dict[str, str], target_titles: set[str]) -> tuple[str, list[str]]:
    unmapped: list[str] = []

    def replace(match: re.Match[str]) -> str:
        title_id = match.group(1)
        if title_id in relation_map:
            return f"title:{relation_map[title_id]}"
        if title_id in target_titles:
            return match.group(0)
        unmapped.append(match.group(0))
        return match.group(0)

    return dry.TITLE_REF_RE.sub(replace, raw), sorted(set(unmapped))


def cultural_name_entries(raw: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in raw.splitlines(keepends=True):
        match = NAME_LIST_ENTRY_RE.match(line)
        if match:
            entries.append((match.group(2), line))
    return entries


def missing_cultural_name_lines(source_raw: str, target_raw: str) -> list[str]:
    target_keys = {key for key, _ in cultural_name_entries(target_raw)}
    return [line for key, line in cultural_name_entries(source_raw) if key not in target_keys]


def find_insert_index(lines: list[str], block: dry.TitleBlock) -> int:
    direct_depth = block.start_depth + 1
    depth = direct_depth
    start_index = block.start_line
    end_index = block.end_line - 1

    for index in range(start_index, end_index):
        clean = dry.strip_comment(lines[index])
        if depth == direct_depth and dry.TITLE_RE.match(clean):
            return index
        depth += dry.brace_delta(lines[index])

    return end_index


def existing_review_comment_start(lines: list[str], target_start_index: int) -> int:
    previous_index = target_start_index - 1
    if previous_index < 0:
        return target_start_index
    if lines[previous_index].strip().startswith("# Yusseter: REVIEW_ASIL_MOD_"):
        return previous_index
    return target_start_index


def build_pending_changes(args: argparse.Namespace, target_lines: list[str]) -> tuple[list[PendingChange], list[dict[str, str]]]:
    source_landed = args.source_root / "common" / "landed_titles" / "00_landed_titles.txt"
    target_landed = args.target_root / "common" / "landed_titles" / "00_landed_titles.txt"
    relation_csv = args.target_root / "title_relation_master_manuel_new.csv"

    source_lines = source_landed.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    source_titles = dry.parse_title_blocks(source_lines)
    target_titles = dry.parse_title_blocks(target_lines)
    relations = dry.load_relations(relation_csv)
    relation_map = {row["mod_title_id"]: row["source_title_id"] for row in relations}

    source_props_cache: dict[str, dict[str, dry.PropertyBlock]] = {}
    target_props_cache: dict[str, dict[str, dry.PropertyBlock]] = {}
    target_title_set = set(target_titles)
    pending: list[PendingChange] = []
    report_rows: list[dict[str, str]] = []

    for relation in relations:
        asil_mod_title_id = relation["mod_title_id"]
        target_title_id = relation["source_title_id"]
        source_block = source_titles.get(asil_mod_title_id)
        target_block = target_titles.get(target_title_id)

        if source_block and asil_mod_title_id not in source_props_cache:
            source_props_cache[asil_mod_title_id] = dry.extract_properties(source_lines, source_block, dry.TRANSFER_KEYS)
        if target_block and target_title_id not in target_props_cache:
            target_props_cache[target_title_id] = dry.extract_properties(target_lines, target_block, dry.TRANSFER_KEYS)

        for key in dry.TRANSFER_KEYS:
            source_prop = source_props_cache.get(asil_mod_title_id, {}).get(key)
            target_prop = target_props_cache.get(target_title_id, {}).get(key)
            row = {
                "asil_mod_title_id": asil_mod_title_id,
                "target_title_id": target_title_id,
                "key": key,
                "source_line": str(source_prop.start_line if source_prop else source_block.start_line if source_block else ""),
                "target_line": str(target_prop.start_line if target_prop else target_block.start_line if target_block else ""),
                "status": "",
                "review_comment": "",
                "action_line": "",
                "unmapped_title_refs": "",
            }

            if not source_block:
                row["status"] = "skipped_asil_mod_title_missing"
            elif not target_block:
                row["status"] = "skipped_target_title_missing"
            elif not source_prop:
                row["status"] = "skipped_asil_mod_key_missing"
            else:
                refs, _, _ = dry.resolve_title_refs(source_prop.raw, relation_map, target_title_set)
                review_comment = dry.review_comment_for(key, True, bool(refs))
                remapped_raw, unmapped = remap_title_refs(source_prop.raw, relation_map, target_title_set)
                row["review_comment"] = review_comment
                row["unmapped_title_refs"] = ";".join(unmapped)
                if unmapped:
                    row["status"] = "skipped_unmapped_title_ref"
                elif target_prop and source_prop.normalized == target_prop.normalized:
                    row["status"] = "skipped_same"
                elif key == "cultural_names" and target_prop:
                    missing_lines = missing_cultural_name_lines(remapped_raw, target_prop.raw)
                    if not missing_lines:
                        row["status"] = "skipped_cultural_names_no_new_name_list_key"
                    else:
                        row["status"] = "will_merge_cultural_names"
                        row["action_line"] = str(target_prop.end_line)
                        pending.append(
                            PendingChange(
                                action="merge_cultural_names",
                                asil_mod_title_id=asil_mod_title_id,
                                target_title_id=target_title_id,
                                key=key,
                                raw=remapped_raw,
                                review_comment=review_comment,
                                source_line=source_prop.start_line,
                                start_index=target_prop.end_line - 1,
                                end_index=target_prop.end_line - 1,
                                merge_lines=missing_lines,
                            )
                        )
                elif target_prop:
                    replace_start = existing_review_comment_start(target_lines, target_prop.start_line - 1)
                    row["status"] = "will_replace"
                    row["action_line"] = str(replace_start + 1)
                    pending.append(
                        PendingChange(
                            action="replace",
                            asil_mod_title_id=asil_mod_title_id,
                            target_title_id=target_title_id,
                            key=key,
                            raw=remapped_raw,
                            review_comment=review_comment,
                            source_line=source_prop.start_line,
                            start_index=replace_start,
                            end_index=target_prop.end_line,
                        )
                    )
                else:
                    insert_index = find_insert_index(target_lines, target_block)
                    row["status"] = "will_insert"
                    row["action_line"] = str(insert_index + 1)
                    pending.append(
                        PendingChange(
                            action="insert",
                            asil_mod_title_id=asil_mod_title_id,
                            target_title_id=target_title_id,
                            key=key,
                            raw=remapped_raw,
                            review_comment=review_comment,
                            source_line=source_prop.start_line,
                            start_index=insert_index,
                            end_index=insert_index,
                        )
                    )

            report_rows.append(row)

    return pending, report_rows


def build_insert_lines(items: list[PendingChange], target_block: dry.TitleBlock, newline: str) -> list[str]:
    target_indent = target_property_indent(target_block)
    lines: list[str] = [newline]
    for item in items:
        if item.review_comment:
            lines.append(target_indent + item.review_comment + newline)
        lines.extend(reindent_block(item.raw, target_indent, newline))
        lines.append(newline)
    return lines


def build_replace_lines(item: PendingChange, target_block: dry.TitleBlock, newline: str) -> list[str]:
    target_indent = target_property_indent(target_block)
    lines: list[str] = []
    if item.review_comment:
        lines.append(target_indent + item.review_comment + newline)
    lines.extend(reindent_block(item.raw, target_indent, newline))
    return lines


def build_cultural_merge_lines(item: PendingChange, target_lines: list[str], newline: str) -> list[str]:
    if item.merge_lines is None:
        return []
    closing_line = target_lines[item.start_index]
    target_indent = leading_indent(closing_line) + "\t"
    lines: list[str] = []
    if item.review_comment:
        lines.append(target_indent + item.review_comment + newline)
    for source_line in item.merge_lines:
        source_body = source_line.rstrip("\r\n").lstrip(" \t")
        lines.append(target_indent + source_body + newline)
    return lines


def apply_changes(target_lines: list[str], changes: list[PendingChange]) -> list[str]:
    target_titles = dry.parse_title_blocks(target_lines)
    grouped_inserts: dict[tuple[str, int], list[PendingChange]] = defaultdict(list)
    replacements: list[PendingChange] = []
    cultural_merges: list[PendingChange] = []

    for item in changes:
        if item.action == "insert":
            grouped_inserts[(item.target_title_id, item.start_index)].append(item)
        elif item.action == "merge_cultural_names":
            cultural_merges.append(item)
        else:
            replacements.append(item)

    newline = detect_newline(target_lines)
    new_lines = list(target_lines)

    operations: list[tuple[int, int, list[str]]] = []
    for item in replacements:
        target_block = target_titles[item.target_title_id]
        operations.append((item.start_index, item.end_index, build_replace_lines(item, target_block, newline)))

    for item in cultural_merges:
        operations.append((item.start_index, item.end_index, build_cultural_merge_lines(item, target_lines, newline)))

    for (target_title_id, insertion_index), items in grouped_inserts.items():
        target_block = target_titles[target_title_id]
        ordered_items = sorted(items, key=lambda item: dry.TRANSFER_KEYS.index(item.key))
        insert_lines = build_insert_lines(ordered_items, target_block, newline)
        operations.append((insertion_index, insertion_index, insert_lines))

    for start_index, end_index, replacement_lines in sorted(operations, key=lambda item: item[0], reverse=True):
        new_lines[start_index:end_index] = replacement_lines

    return new_lines


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "asil_mod_title_id",
        "target_title_id",
        "key",
        "status",
        "source_line",
        "target_line",
        "action_line",
        "review_comment",
        "unmapped_title_refs",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    target_root = script_path.parents[2]
    crusader_kings_root = target_root.parent.parent
    source_root = crusader_kings_root / "Leviathonlx MoreBookmarks-Plus" / "BookmarksGit"
    output_dir = target_root / "works" / "analysis" / "generated" / "landed_title_asil_mod_metadata_transfer"

    parser = argparse.ArgumentParser(
        description="Apply selected landed title metadata from asil mod equivalents, replacing different target values.",
    )
    parser.add_argument("--target-root", type=Path, default=target_root)
    parser.add_argument("--source-root", type=Path, default=source_root)
    parser.add_argument("--output-dir", type=Path, default=output_dir)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_landed = args.target_root / "common" / "landed_titles" / "00_landed_titles.txt"
    target_lines = target_landed.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    pending, report_rows = build_pending_changes(args, target_lines)

    report_path = args.output_dir / "landed_title_asil_mod_metadata_transfer_apply_report.csv"
    write_report(report_path, report_rows)

    if not args.dry_run:
        new_lines = apply_changes(target_lines, pending)
        target_landed.write_text("".join(new_lines), encoding="utf-8-sig")

    print(f"will_apply={len(pending)}")
    print(f"will_insert={sum(1 for item in pending if item.action == 'insert')}")
    print(f"will_replace={sum(1 for item in pending if item.action == 'replace')}")
    print(f"will_merge_cultural_names={sum(1 for item in pending if item.action == 'merge_cultural_names')}")
    print(f"dry_run={'yes' if args.dry_run else 'no'}")
    print(f"report={report_path}")


if __name__ == "__main__":
    main()
