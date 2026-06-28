from __future__ import annotations

import argparse
import codecs
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT_DEFAULT = Path(r"F:\Storage\Codding\git\Crusader Kings III\Yusseter MoreBookmarksPlus\BookmarksGit")
MANUAL_REL = Path("title_relation_master_manuel_new.csv")
OUTPUT_REL = Path("works/analysis/generated/east_title_rewrite")

TITLE_RE = re.compile(r"^(\s*)([hekdcb]_[A-Za-z0-9_'\-]+)(\s*=\s*\{.*)$")
TITLE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_'\-])([hekdcb]_[A-Za-z0-9_'\-]+)(?![A-Za-z0-9_'\-])")
NO_COUNTERPART = "*there_is_no*"
BLOCKER_STATUSES = {
    "ambiguous_direct_mapping",
    "block_collision_same_run_target_duplicate",
    "block_collision_would_duplicate",
    "mapping_parse_mismatch",
}
AUDIT_ONLY_PREFIXES = (
    "common/landed_titles/",
)


@dataclass(frozen=True)
class TextFile:
    path: Path
    rel_path: str
    text: str
    has_bom: bool
    newline: str


@dataclass(frozen=True)
class MappingEntry:
    row_number: int
    source_title_id: str
    mod_title_id_raw: str
    mod_title_id_base: str
    is_same_title_id: str
    is_second: bool
    is_amp_group: bool
    mapping_kind: str
    rewrite_action: str


@dataclass
class TitleBlock:
    title_id: str
    path: Path
    rel_path: str
    start_index: int
    end_index: int
    start_line: int
    end_line: int
    depth: int
    scope: str
    parent_id: str


@dataclass
class RewriteContext:
    direct_map: dict[str, str]
    direct_entries_by_mod: dict[str, list[MappingEntry]]
    second_entries_by_mod: dict[str, list[MappingEntry]]
    source_entries_by_source: dict[str, list[MappingEntry]]
    same_entries_by_mod: dict[str, list[MappingEntry]]
    source_ids: set[str]
    mod_ids: set[str]
    issues: list[dict[str, str]] = field(default_factory=list)
    info: list[dict[str, str]] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rewrite imported east title ids using title_relation_master_manuel_new.csv.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT_DEFAULT)
    parser.add_argument("--manual-csv", type=Path, default=REPO_ROOT_DEFAULT / MANUAL_REL)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT_DEFAULT / OUTPUT_REL)
    parser.add_argument("--write", action="store_true", help="Write changed live files and existing test_files counterparts.")
    parser.add_argument(
        "--allow-annotated-collisions",
        action="store_true",
        help="Apply duplicate-prone block rename/clone operations with EAST_TITLE_REWRITE_COLLISION comments for manual cleanup.",
    )
    parser.add_argument(
        "--annotate-second-references",
        action="store_true",
        help="Insert EAST_TITLE_REWRITE_SECOND_REFERENCE comments above report-only (second) references.",
    )
    parser.add_argument("--no-reports", action="store_true", help="Do not write generated reports.")
    return parser.parse_args()


def normalize_header(row: dict[str, str]) -> dict[str, str]:
    return {str(key).strip(): (value or "").strip() for key, value in row.items() if key is not None}


def strip_second(value: str) -> str:
    return re.sub(r"\s*\(second\)\s*$", "", value).strip()


def split_amp(value: str) -> list[str]:
    return [item.strip() for item in value.split("&") if item.strip()]


def read_manual(path: Path) -> tuple[list[MappingEntry], list[dict[str, str]]]:
    entries: list[MappingEntry] = []
    issues: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for index, raw_row in enumerate(csv.DictReader(handle, skipinitialspace=True), start=2):
            row = normalize_header(raw_row)
            source_title_id = row.get("source_title_id", "")
            mod_raw = row.get("mod_title_id", "")
            same_raw = row.get("is_same_title_id", "")
            mod_tokens = split_amp(mod_raw)
            same_tokens = split_amp(same_raw) or [same_raw]
            is_amp_group = len(mod_tokens) > 1

            if len(same_tokens) not in {1, len(mod_tokens)}:
                issues.append(issue_row(
                    "mapping_parse_mismatch",
                    source_title_id=source_title_id,
                    mod_title_id=mod_raw,
                    message=f"is_same_title_id token count ({len(same_tokens)}) does not match mod_title_id token count ({len(mod_tokens)}).",
                ))

            for token_index, mod_token in enumerate(mod_tokens):
                is_same = same_tokens[token_index] if len(same_tokens) == len(mod_tokens) else same_tokens[0]
                is_second = bool(re.search(r"\s*\(second\)\s*$", mod_token))
                mod_base = strip_second(mod_token)
                if not source_title_id or not mod_base or mod_base == NO_COUNTERPART:
                    action = "no_counterpart_skip"
                    mapping_kind = "no_counterpart"
                elif is_same == "yes":
                    action = "same_id_noop"
                    mapping_kind = "same_id"
                elif is_second:
                    action = "second_block_clone"
                    mapping_kind = "second"
                else:
                    action = "direct_rewrite"
                    mapping_kind = "direct"

                entries.append(MappingEntry(
                    row_number=index,
                    source_title_id=source_title_id,
                    mod_title_id_raw=mod_token,
                    mod_title_id_base=mod_base,
                    is_same_title_id=is_same,
                    is_second=is_second,
                    is_amp_group=is_amp_group,
                    mapping_kind=mapping_kind,
                    rewrite_action=action,
                ))
    return entries, issues


def issue_row(status: str, *, file: str = "", line: str | int = "", source_title_id: str = "", mod_title_id: str = "", message: str = "") -> dict[str, str]:
    return {
        "status": status,
        "file": file,
        "line": str(line),
        "source_title_id": source_title_id,
        "mod_title_id": mod_title_id,
        "message": message,
    }


def info_row(status: str, *, file: str = "", line: str | int = "", source_title_id: str = "", mod_title_id: str = "", message: str = "") -> dict[str, str]:
    return issue_row(status, file=file, line=line, source_title_id=source_title_id, mod_title_id=mod_title_id, message=message)


def build_context(entries: list[MappingEntry], initial_issues: list[dict[str, str]]) -> RewriteContext:
    direct_entries_by_mod: dict[str, list[MappingEntry]] = defaultdict(list)
    second_entries_by_mod: dict[str, list[MappingEntry]] = defaultdict(list)
    source_entries_by_source: dict[str, list[MappingEntry]] = defaultdict(list)
    same_entries_by_mod: dict[str, list[MappingEntry]] = defaultdict(list)
    source_ids: set[str] = set()
    mod_ids: set[str] = set()
    info: list[dict[str, str]] = []
    issues = list(initial_issues)

    for entry in entries:
        if entry.source_title_id:
            source_ids.add(entry.source_title_id)
            source_entries_by_source[entry.source_title_id].append(entry)
        if entry.mod_title_id_base:
            mod_ids.add(entry.mod_title_id_base)
        if entry.rewrite_action == "direct_rewrite":
            direct_entries_by_mod[entry.mod_title_id_base].append(entry)
        elif entry.rewrite_action == "second_block_clone":
            second_entries_by_mod[entry.mod_title_id_base].append(entry)
            info.append(info_row(
                "second_block_clone_mapping",
                source_title_id=entry.source_title_id,
                mod_title_id=entry.mod_title_id_base,
                message="(second) mapping will clone title blocks when no collision exists; non-block references are report-only.",
            ))
        elif entry.rewrite_action == "same_id_noop":
            same_entries_by_mod[entry.mod_title_id_base].append(entry)
            info.append(info_row(
                "same_id_noop",
                source_title_id=entry.source_title_id,
                mod_title_id=entry.mod_title_id_base,
                message="source_title_id and mod_title_id are marked as the same; no rewrite is needed.",
            ))

    for source, group in group_by_source(entries).items():
        if any(item.is_amp_group for item in group):
            info.append(info_row(
                "multi_mod_title_id_mapping",
                source_title_id=source,
                mod_title_id=" & ".join(item.mod_title_id_base for item in group),
                message="Manual row maps multiple mod title ids to one source title id.",
            ))

    direct_map: dict[str, str] = {}
    for mod_title_id, group in direct_entries_by_mod.items():
        targets = sorted({entry.source_title_id for entry in group})
        if len(targets) > 1:
            issues.append(issue_row(
                "ambiguous_direct_mapping",
                source_title_id="|".join(targets),
                mod_title_id=mod_title_id,
                message="One mod_title_id has multiple direct source_title_id targets; token rewrite would be ambiguous.",
            ))
            continue
        direct_map[mod_title_id] = targets[0]

    for mod_title_id, target in direct_map.items():
        if mod_title_id in source_ids and mod_title_id != target:
            info.append(info_row(
                "rewrite_chain_collision_risk",
                source_title_id=target,
                mod_title_id=mod_title_id,
                message="This mod_title_id is also a source_title_id elsewhere; atomic rewrite prevents cascading replacement.",
            ))

    return RewriteContext(
        direct_map=direct_map,
        direct_entries_by_mod=direct_entries_by_mod,
        second_entries_by_mod=second_entries_by_mod,
        source_entries_by_source=source_entries_by_source,
        same_entries_by_mod=same_entries_by_mod,
        source_ids=source_ids,
        mod_ids=mod_ids,
        issues=issues,
        info=info,
    )


def group_by_source(entries: list[MappingEntry]) -> dict[str, list[MappingEntry]]:
    result: dict[str, list[MappingEntry]] = defaultdict(list)
    for entry in entries:
        result[entry.source_title_id].append(entry)
    return result


def dominant_newline(text: str) -> str:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf >= lf and crlf > 0 else "\n"


def read_text_file(repo_root: Path, path: Path) -> TextFile:
    data = path.read_bytes()
    has_bom = data.startswith(codecs.BOM_UTF8)
    text = data.decode("utf-8-sig")
    return TextFile(path=path, rel_path=path.relative_to(repo_root).as_posix(), text=text, has_bom=has_bom, newline=dominant_newline(text))


def encode_text(file: TextFile, text: str) -> bytes:
    data = text.encode("utf-8")
    if file.has_bom:
        return codecs.BOM_UTF8 + data
    return data


def split_lines_keepends(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def split_comment(line: str) -> tuple[str, str]:
    if "#" not in line:
        return line, ""
    active, comment = line.split("#", 1)
    return active, "#" + comment


def brace_delta(line: str) -> int:
    clean = strip_comment(line)
    return clean.count("{") - clean.count("}")


def get_file_scope(rel_path: str) -> str:
    if rel_path.startswith("common/landed_titles/"):
        return "common_landed_titles"
    if rel_path.startswith("history/titles/"):
        return "history_titles"
    return ""


def parse_title_blocks(file: TextFile) -> list[TitleBlock]:
    scope = get_file_scope(file.rel_path)
    if not scope:
        return []
    lines = split_lines_keepends(file.text)
    blocks: list[TitleBlock] = []
    stack: list[dict[str, object]] = []
    depth = 0

    for index, line in enumerate(lines):
        clean = strip_comment(line)
        match = TITLE_RE.match(clean)
        if match:
            title_id = match.group(2)
            parent_id = str(stack[-1]["title_id"]) if stack else ""
            stack.append({
                "title_id": title_id,
                "start_index": index,
                "start_line": index + 1,
                "depth": depth + 1,
                "parent_id": parent_id,
            })

        depth += clean.count("{") - clean.count("}")
        while stack and depth < int(stack[-1]["depth"]):
            item = stack.pop()
            blocks.append(TitleBlock(
                title_id=str(item["title_id"]),
                path=file.path,
                rel_path=file.rel_path,
                start_index=int(item["start_index"]),
                end_index=index,
                start_line=int(item["start_line"]),
                end_line=index + 1,
                depth=int(item["depth"]),
                scope=scope,
                parent_id=str(item["parent_id"]),
            ))

        if depth < 0:
            depth = 0
            stack.clear()

    return blocks


def collect_target_files(repo_root: Path) -> list[Path]:
    roots = [
        repo_root / "common",
        repo_root / "history",
        repo_root / "events",
        repo_root / "decisions",
        repo_root / "map_data" / "geographical_regions",
    ]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.txt")):
            rel_path = path.relative_to(repo_root).as_posix()
            if "\\localization\\" in str(path).lower():
                continue
            if rel_path.startswith(AUDIT_ONLY_PREFIXES):
                continue
            files.append(path)
    return files


def collect_landed_title_audit_files(repo_root: Path) -> list[Path]:
    root = repo_root / "common" / "landed_titles"
    if not root.exists():
        return []
    return sorted(root.rglob("*.txt"))


def rewrite_tokens(active: str, direct_map: dict[str, str]) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        token = match.group(1)
        replacement = direct_map.get(token)
        if replacement and replacement != token:
            count += 1
            return replacement
        return token

    return TITLE_TOKEN_RE.sub(replace, active), count


def rewrite_line(line: str, direct_map: dict[str, str], header_title: str | None = None, header_override: str | None = None) -> tuple[str, int]:
    active, comment = split_comment(line)
    if header_title:
        match = TITLE_RE.match(active)
        if match:
            replacement_title = header_override or header_title
            rewritten_suffix, suffix_count = rewrite_tokens(match.group(3), direct_map)
            return match.group(1) + replacement_title + rewritten_suffix + comment, suffix_count + (1 if header_override and header_override != header_title else 0)

    rewritten, count = rewrite_tokens(active, direct_map)
    return rewritten + comment, count


def previous_line_is_annotation(lines: list[str], index: int, comment: str) -> bool:
    if index <= 0:
        return False
    return lines[index - 1].strip() == comment


def add_line_annotation(annotations: dict[tuple[Path, int], list[str]], file: TextFile, index: int, comment: str) -> bool:
    key = (file.path, index)
    if comment in annotations[key]:
        return False
    if previous_line_is_annotation(split_lines_keepends(file.text), index, comment):
        return False
    annotations[key].append(comment)
    return True


def collision_comment(kind: str, old_title: str, target: str, reason: str) -> str:
    return f"# EAST_TITLE_REWRITE_COLLISION: {kind} {old_title} -> {target}; {reason}; manual merge needed."


def target_collision_comment(target: str, old_title: str, reason: str) -> str:
    return f"# EAST_TITLE_REWRITE_COLLISION_TARGET: {target} receives {old_title}; {reason}; manual merge needed."


def second_reference_comment(token: str, target: str) -> str:
    return f"# EAST_TITLE_REWRITE_SECOND_REFERENCE: {token} has second mapping to {target}; manual review needed."


def sorted_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: (row.get("status", ""), row.get("file", ""), int(row["line"]) if str(row.get("line", "")).isdigit() else 0, row.get("source_title_id", ""), row.get("mod_title_id", "")))


def process_files(
    repo_root: Path,
    files: list[TextFile],
    blocks_by_path: dict[Path, list[TitleBlock]],
    ctx: RewriteContext,
    *,
    allow_annotated_collisions: bool = False,
    annotate_second_references: bool = False,
) -> tuple[dict[Path, str], dict[str, int]]:
    file_by_path = {file.path: file for file in files}
    scope_counts: dict[str, Counter[str]] = defaultdict(Counter)
    blocks_by_scope_title: dict[tuple[str, str], list[TitleBlock]] = defaultdict(list)
    for blocks in blocks_by_path.values():
        for block in blocks:
            scope_counts[block.scope][block.title_id] += 1
            blocks_by_scope_title[(block.scope, block.title_id)].append(block)

    header_overrides: dict[tuple[Path, int], str] = {}
    clone_blocks: dict[tuple[Path, int], list[list[str]]] = defaultdict(list)
    line_annotations: dict[tuple[Path, int], list[str]] = defaultdict(list)
    stats = Counter()
    planned_targets: dict[tuple[str, str], list[tuple[str, TitleBlock]]] = defaultdict(list)

    for blocks in blocks_by_path.values():
        for block in blocks:
            if block.title_id in ctx.direct_map:
                target = ctx.direct_map[block.title_id]
                if target != block.title_id:
                    planned_targets[(block.scope, target)].append(("direct", block))

            for entry in ctx.second_entries_by_mod.get(block.title_id, []):
                planned_targets[(block.scope, entry.source_title_id)].append(("second", block))

    same_run_duplicate_targets = {
        key
        for key, operations in planned_targets.items()
        if len(operations) > 1
    }

    def same_run_duplicate_message(scope: str, target: str) -> str:
        operations = planned_targets[(scope, target)]
        candidates = "|".join(f"{kind}:{block.title_id}@{block.rel_path}:{block.start_line}" for kind, block in operations)
        return f"Multiple block operations in {scope} would create {target}; operation skipped. Candidates: {candidates}"

    def mark_existing_targets(scope: str, target: str, old_title: str, reason: str) -> None:
        for target_block in blocks_by_scope_title.get((scope, target), []):
            target_file = file_by_path.get(target_block.path)
            if not target_file:
                continue
            comment = target_collision_comment(target, old_title, reason)
            if add_line_annotation(line_annotations, target_file, target_block.start_index, comment):
                stats["annotated_collision_targets_marked"] += 1

    for file in files:
        blocks = blocks_by_path.get(file.path, [])
        if not blocks:
            continue
        for block in blocks:
            if block.title_id in ctx.direct_map:
                target = ctx.direct_map[block.title_id]
                if target != block.title_id:
                    existing_collision = scope_counts[block.scope][target] > 0
                    same_run_collision = (block.scope, target) in same_run_duplicate_targets
                    if existing_collision or same_run_collision:
                        reason = (
                            f"target already exists in {block.scope}"
                            if existing_collision
                            else f"same-run duplicate target in {block.scope}"
                        )
                        skipped_message = (
                            f"Direct block rename would duplicate an existing {target} block in {block.scope}; header rename skipped."
                            if existing_collision
                            else same_run_duplicate_message(block.scope, target)
                        )
                        if allow_annotated_collisions:
                            ctx.issues.append(issue_row(
                                "annotated_collision_rewrite_planned",
                                file=block.rel_path,
                                line=block.start_line,
                                source_title_id=target,
                                mod_title_id=block.title_id,
                                message=f"Direct block rename will be written with an EAST_TITLE_REWRITE_COLLISION comment; {reason}.",
                            ))
                            header_overrides[(block.path, block.start_index)] = target
                            source_file = file_by_path[block.path]
                            comment = collision_comment("direct", block.title_id, target, reason)
                            if add_line_annotation(line_annotations, source_file, block.start_index, comment):
                                stats["annotated_collision_comments"] += 1
                            if existing_collision:
                                mark_existing_targets(block.scope, target, block.title_id, reason)
                            stats["block_header_renames"] += 1
                            stats["annotated_collision_rewrites"] += 1
                        else:
                            ctx.issues.append(issue_row(
                                "block_collision_would_duplicate" if existing_collision else "block_collision_same_run_target_duplicate",
                                file=block.rel_path,
                                line=block.start_line,
                                source_title_id=target,
                                mod_title_id=block.title_id,
                                message=skipped_message,
                            ))
                    else:
                        header_overrides[(block.path, block.start_index)] = target
                        scope_counts[block.scope][block.title_id] -= 1
                        scope_counts[block.scope][target] += 1
                        stats["block_header_renames"] += 1

            for entry in ctx.second_entries_by_mod.get(block.title_id, []):
                target = entry.source_title_id
                existing_collision = scope_counts[block.scope][target] > 0
                same_run_collision = (block.scope, target) in same_run_duplicate_targets
                if existing_collision or same_run_collision:
                    reason = (
                        f"target already exists in {block.scope}"
                        if existing_collision
                        else f"same-run duplicate target in {block.scope}"
                    )
                    skipped_message = (
                        f"(second) block clone would duplicate an existing {target} block in {block.scope}; clone skipped."
                        if existing_collision
                        else same_run_duplicate_message(block.scope, target)
                    )
                    if allow_annotated_collisions:
                        ctx.issues.append(issue_row(
                            "annotated_collision_clone_planned",
                            file=block.rel_path,
                            line=block.start_line,
                            source_title_id=target,
                            mod_title_id=block.title_id,
                            message=f"(second) block clone will be written with an EAST_TITLE_REWRITE_COLLISION comment; {reason}.",
                        ))
                        original_lines = split_lines_keepends(file.text)[block.start_index : block.end_index + 1]
                        cloned_lines = [collision_comment("second_clone", block.title_id, target, reason) + file.newline]
                        for offset, original_line in enumerate(original_lines):
                            if offset == 0:
                                cloned_line, _ = rewrite_line(original_line, ctx.direct_map, header_title=block.title_id, header_override=target)
                            else:
                                cloned_line, _ = rewrite_line(original_line, ctx.direct_map)
                            cloned_lines.append(cloned_line)

                        clone_blocks[(block.path, block.end_index)].append(cloned_lines)
                        if existing_collision:
                            mark_existing_targets(block.scope, target, block.title_id, reason)
                        stats["second_block_clones"] += 1
                        stats["annotated_collision_clones"] += 1
                    else:
                        ctx.issues.append(issue_row(
                            "block_collision_would_duplicate" if existing_collision else "block_collision_same_run_target_duplicate",
                            file=block.rel_path,
                            line=block.start_line,
                            source_title_id=target,
                            mod_title_id=block.title_id,
                            message=skipped_message,
                        ))
                    continue

                original_lines = split_lines_keepends(file.text)[block.start_index : block.end_index + 1]
                cloned_lines = []
                for offset, original_line in enumerate(original_lines):
                    if offset == 0:
                        cloned_line, _ = rewrite_line(original_line, ctx.direct_map, header_title=block.title_id, header_override=target)
                    else:
                        cloned_line, _ = rewrite_line(original_line, ctx.direct_map)
                    cloned_lines.append(cloned_line)

                clone_blocks[(block.path, block.end_index)].append(cloned_lines)
                scope_counts[block.scope][target] += 1
                stats["second_block_clones"] += 1

    changed: dict[Path, str] = {}
    for file in files:
        lines = split_lines_keepends(file.text)
        blocks = blocks_by_path.get(file.path, [])
        report_second_references(
            file,
            ctx,
            blocks,
            line_annotations=line_annotations,
            stats=stats,
            annotate_second_references=annotate_second_references,
        )
        header_by_index = {block.start_index: block for block in blocks}
        new_lines: list[str] = []
        token_replacements = 0

        for index, line in enumerate(lines):
            for annotation in line_annotations.get((file.path, index), []):
                new_lines.append(annotation + file.newline)

            block = header_by_index.get(index)
            if block:
                new_line, count = rewrite_line(
                    line,
                    ctx.direct_map,
                    header_title=block.title_id,
                    header_override=header_overrides.get((file.path, index)),
                )
            else:
                new_line, count = rewrite_line(line, ctx.direct_map)
            token_replacements += count
            new_lines.append(new_line)

            for cloned_lines in clone_blocks.get((file.path, index), []):
                new_lines.extend(cloned_lines)

        new_text = "".join(new_lines)
        if new_text != file.text:
            changed[file.path] = new_text
            stats["changed_files"] += 1
            stats["token_or_header_replacements"] += token_replacements

    return changed, dict(stats)


def report_second_references(
    file: TextFile,
    ctx: RewriteContext,
    blocks: list[TitleBlock],
    *,
    line_annotations: dict[tuple[Path, int], list[str]],
    stats: Counter[str],
    annotate_second_references: bool,
) -> None:
    if not ctx.second_entries_by_mod:
        return
    block_header_indices = {block.start_index for block in blocks if block.title_id in ctx.second_entries_by_mod}
    second_tokens = set(ctx.second_entries_by_mod)
    if not second_tokens:
        return

    for index, line in enumerate(split_lines_keepends(file.text)):
        if index in block_header_indices:
            continue
        active = split_comment(line)[0]
        for match in TITLE_TOKEN_RE.finditer(active):
            token = match.group(1)
            if token not in second_tokens:
                continue
            for entry in ctx.second_entries_by_mod[token]:
                status = "annotated_second_reference_planned" if annotate_second_references else "second_reference_report_only"
                message = (
                    "(second) mapping found outside a title block header; an EAST_TITLE_REWRITE_SECOND_REFERENCE comment will be inserted for manual review."
                    if annotate_second_references
                    else "(second) mapping found outside a title block header; reference was not cloned or rewritten automatically."
                )
                ctx.issues.append(issue_row(
                    status,
                    file=file.rel_path,
                    line=index + 1,
                    source_title_id=entry.source_title_id,
                    mod_title_id=token,
                    message=message,
                ))
                if annotate_second_references:
                    comment = second_reference_comment(token, entry.source_title_id)
                    if add_line_annotation(line_annotations, file, index, comment):
                        stats["annotated_second_references"] += 1


def build_plan_rows(entries: list[MappingEntry]) -> list[dict[str, str]]:
    return [
        {
            "source_title_id": entry.source_title_id,
            "mod_title_id_base": entry.mod_title_id_base,
            "mapping_kind": entry.mapping_kind,
            "is_same_title_id": entry.is_same_title_id,
            "is_second": "yes" if entry.is_second else "no",
            "is_amp_group": "yes" if entry.is_amp_group else "no",
            "rewrite_action": entry.rewrite_action,
        }
        for entry in entries
    ]


def build_full_title_audit(blocks: list[TitleBlock], ctx: RewriteContext, collision_keys: set[tuple[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for block in sorted(blocks, key=lambda item: (item.rel_path, item.start_line)):
        source_entries = ctx.source_entries_by_source.get(block.title_id, [])
        direct_entries = ctx.direct_entries_by_mod.get(block.title_id, [])
        second_entries = ctx.second_entries_by_mod.get(block.title_id, [])
        same_entries = ctx.same_entries_by_mod.get(block.title_id, [])
        roles = []
        if source_entries:
            roles.append("source_title_id")
        if direct_entries or second_entries or same_entries:
            roles.append("mod_title_id")
        if not roles:
            roles.append("unmapped")

        mapped_sources = [entry.source_title_id for entry in direct_entries + second_entries + same_entries]
        mapped_mods = [entry.mod_title_id_base for entry in source_entries]
        rewrite_status = "unmapped"
        if same_entries:
            rewrite_status = "same_id_noop"
        if direct_entries:
            rewrite_status = "direct_rewrite_candidate"
        if second_entries:
            rewrite_status = "second_block_clone_candidate" if rewrite_status == "unmapped" else rewrite_status + "|second_block_clone_candidate"
        if source_entries and rewrite_status == "unmapped":
            rewrite_status = "source_target"

        collision_status = ""
        if (block.rel_path, block.title_id) in collision_keys:
            collision_status = "block_collision_would_duplicate"

        chain_risk_status = ""
        if block.title_id in ctx.source_ids and block.title_id in ctx.mod_ids:
            chain_risk_status = "rewrite_chain_collision_risk"

        rows.append({
            "title_id": block.title_id,
            "tier": block.title_id.split("_", 1)[0],
            "defined_file": block.rel_path,
            "line_no": str(block.start_line),
            "relation_role": "|".join(roles),
            "mapped_source_title_id": "|".join(sorted(set(mapped_sources))),
            "mapped_mod_title_id": "|".join(sorted(set(mapped_mods))),
            "rewrite_status": rewrite_status,
            "collision_status": collision_status,
            "chain_risk_status": chain_risk_status,
            "notes": "",
        })
    return rows


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_reports(output_dir: Path, plan_rows: list[dict[str, str]], issues: list[dict[str, str]], info: list[dict[str, str]], audit_rows: list[dict[str, str]], summary: dict[str, str]) -> None:
    write_csv(output_dir / "east_title_rewrite_plan.csv", plan_rows, [
        "source_title_id",
        "mod_title_id_base",
        "mapping_kind",
        "is_same_title_id",
        "is_second",
        "is_amp_group",
        "rewrite_action",
    ])
    write_csv(output_dir / "east_title_rewrite_issues.csv", sorted_rows(issues), [
        "status",
        "file",
        "line",
        "source_title_id",
        "mod_title_id",
        "message",
    ])
    write_csv(output_dir / "east_title_rewrite_info.csv", sorted_rows(info), [
        "status",
        "file",
        "line",
        "source_title_id",
        "mod_title_id",
        "message",
    ])
    write_csv(output_dir / "east_title_full_mod_title_audit.csv", audit_rows, [
        "title_id",
        "tier",
        "defined_file",
        "line_no",
        "relation_role",
        "mapped_source_title_id",
        "mapped_mod_title_id",
        "rewrite_status",
        "collision_status",
        "chain_risk_status",
        "notes",
    ])
    summary_lines = ["# East Title Rewrite Summary", ""]
    for key, value in summary.items():
        summary_lines.append(f"- {key}: {value}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "east_title_rewrite_summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root
    entries, parse_issues = read_manual(args.manual_csv)
    ctx = build_context(entries, parse_issues)

    target_paths = collect_target_files(repo_root)
    files = [read_text_file(repo_root, path) for path in target_paths]
    blocks_by_path = {file.path: parse_title_blocks(file) for file in files}
    all_blocks = [block for blocks in blocks_by_path.values() for block in blocks]
    landed_audit_paths = collect_landed_title_audit_files(repo_root)
    landed_audit_files = [read_text_file(repo_root, path) for path in landed_audit_paths]
    landed_blocks_by_path = {file.path: parse_title_blocks(file) for file in landed_audit_files}
    common_landed_blocks = [block for blocks in landed_blocks_by_path.values() for block in blocks]

    changed, rewrite_stats = process_files(
        repo_root,
        files,
        blocks_by_path,
        ctx,
        allow_annotated_collisions=args.allow_annotated_collisions,
        annotate_second_references=args.annotate_second_references,
    )
    collision_keys = {
        (row["file"], row["mod_title_id"])
        for row in ctx.issues
        if row["status"] in {"block_collision_would_duplicate", "annotated_collision_rewrite_planned", "annotated_collision_clone_planned"}
    }
    audit_rows = build_full_title_audit(common_landed_blocks, ctx, collision_keys)

    blocker_statuses = set(BLOCKER_STATUSES)
    if args.allow_annotated_collisions:
        blocker_statuses.discard("block_collision_same_run_target_duplicate")
        blocker_statuses.discard("block_collision_would_duplicate")
    blockers = [row for row in ctx.issues if row["status"] in blocker_statuses]
    write_performed = False
    write_skipped_reason = ""
    if args.write and blockers:
        write_skipped_reason = "blockers_present"
    elif args.write:
        for path, text in changed.items():
            original = read_text_file(repo_root, path)
            path.write_bytes(encode_text(original, text))
            test_path = repo_root / "test_files" / path.relative_to(repo_root)
            if test_path.exists():
                test_path.parent.mkdir(parents=True, exist_ok=True)
                test_path.write_bytes(encode_text(original, text))
        write_performed = True

    summary = {
        "manual_rows_expanded": str(len(entries)),
        "direct_rewrite_tokens": str(len(ctx.direct_map)),
        "second_mapping_tokens": str(sum(len(value) for value in ctx.second_entries_by_mod.values())),
        "same_id_noop": str(sum(len(value) for value in ctx.same_entries_by_mod.values())),
        "target_files_scanned": str(len(files)),
        "landed_title_audit_files": str(len(landed_audit_files)),
        "changed_files_planned": str(len(changed)),
        "block_header_renames": str(rewrite_stats.get("block_header_renames", 0)),
        "second_block_clones": str(rewrite_stats.get("second_block_clones", 0)),
        "token_or_header_replacements": str(rewrite_stats.get("token_or_header_replacements", 0)),
        "allow_annotated_collisions": "yes" if args.allow_annotated_collisions else "no",
        "annotate_second_references": "yes" if args.annotate_second_references else "no",
        "annotated_collision_rewrites": str(rewrite_stats.get("annotated_collision_rewrites", 0)),
        "annotated_collision_clones": str(rewrite_stats.get("annotated_collision_clones", 0)),
        "annotated_collision_comments": str(rewrite_stats.get("annotated_collision_comments", 0)),
        "annotated_collision_targets_marked": str(rewrite_stats.get("annotated_collision_targets_marked", 0)),
        "annotated_second_references": str(rewrite_stats.get("annotated_second_references", 0)),
        "issues": str(len(ctx.issues)),
        "info": str(len(ctx.info)),
        "blockers": str(len(blockers)),
        "write_requested": "yes" if args.write else "no",
        "write_performed": "yes" if write_performed else "no",
        "write_skipped_reason": write_skipped_reason,
    }

    if not args.no_reports:
        write_reports(args.output_dir, build_plan_rows(entries), ctx.issues, ctx.info, audit_rows, summary)

    print("east title rewrite")
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
