from __future__ import annotations

import argparse
import csv
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import build_landed_title_asil_mod_metadata_transfer_dry_run as landed


LOCALIZED_AS_RE = re.compile(r"#\s*Localized as\b")
YUSSETER_RE = re.compile(r"#\s*Yusseter:")
MAPPING_SPLIT_RE = re.compile(r"\s*[;&]\s*")
TITLE_ID_RE = re.compile(r"[hekdcb]_[A-Za-z0-9_'\-]+")


@dataclass(frozen=True)
class Declaration:
    title_id: str
    line_index: int
    line_no: int
    path: tuple[str, ...]
    body: str
    ending: str
    comment: str


@dataclass(frozen=True)
class SourceToken:
    title_id: str
    occurrence: int | None
    raw: str


def split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n") or line.endswith("\r"):
        return line[:-1], line[-1]
    return line, ""


def extract_comment(body: str) -> str:
    clean = landed.strip_comment(body)
    if len(clean) == len(body):
        return ""
    return body[len(clean) :].rstrip()


def parse_declarations(lines: list[str], label: str) -> tuple[list[Declaration], dict[str, list[Declaration]]]:
    declarations: list[Declaration] = []
    by_id: dict[str, list[Declaration]] = defaultdict(list)
    stack: list[tuple[str, int]] = []
    depth = 0

    for index, line in enumerate(lines):
        body, ending = split_line_ending(line)
        clean = landed.strip_comment(body)
        match = landed.TITLE_RE.match(clean)
        if match:
            title_id = match.group(1)
            declaration = Declaration(
                title_id=title_id,
                line_index=index,
                line_no=index + 1,
                path=tuple(item[0] for item in stack) + (title_id,),
                body=body,
                ending=ending,
                comment=extract_comment(body),
            )
            declarations.append(declaration)
            by_id[title_id].append(declaration)
            stack.append((title_id, depth))

        depth += landed.brace_delta(body)
        while stack and depth <= stack[-1][1]:
            stack.pop()

        if depth < 0:
            raise ValueError(f"{label}: brace depth became negative at line {index + 1}")

    if depth != 0 or stack:
        open_titles = ",".join(item[0] for item in stack[-10:])
        raise ValueError(f"{label}: unbalanced braces depth={depth} open_titles={open_titles}")

    return declarations, dict(by_id)


def read_text_lines(path: Path) -> tuple[list[str], bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig" if has_bom else "utf-8")
    return text.splitlines(keepends=True), has_bom


def read_git_text_lines(repo_root: Path, revision: str, relative_path: str) -> list[str]:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git show {revision}:{relative_path} failed: {error}")
    return result.stdout.decode("utf-8-sig", errors="replace").splitlines(keepends=True)


def write_text_lines(path: Path, lines: list[str], has_bom: bool) -> None:
    encoding = "utf-8-sig" if has_bom else "utf-8"
    path.write_bytes("".join(lines).encode(encoding))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {str(key).strip(): (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, skipinitialspace=True)
        ]


def parse_source_tokens(value: str) -> list[SourceToken]:
    tokens: list[SourceToken] = []
    for part in MAPPING_SPLIT_RE.split(value.strip()):
        if not part or part == "*there_is_no*":
            continue
        match = TITLE_ID_RE.search(part)
        if not match:
            continue
        occurrence = 2 if "(second)" in part.lower() else None
        tokens.append(SourceToken(match.group(0), occurrence, part))
    return tokens


def build_unique_source_to_target_map(
    relation_rows: list[dict[str, str]],
) -> dict[str, str]:
    reverse: dict[str, list[str]] = defaultdict(list)
    for row in relation_rows:
        target_id = row.get("source_title_id", "")
        tokens = parse_source_tokens(row.get("mod_title_id", ""))
        if not target_id or len(tokens) != 1:
            continue
        source_id = tokens[0].title_id
        if target_id not in reverse[source_id]:
            reverse[source_id].append(target_id)
    return {
        source_id: target_ids[0]
        for source_id, target_ids in reverse.items()
        if len(target_ids) == 1
    }


def remap_source_path(
    path: tuple[str, ...], source_to_target: dict[str, str]
) -> tuple[str, ...]:
    return tuple(source_to_target.get(title_id, title_id) for title_id in path)


def normalize_comment(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def merge_comments(target: Declaration, source_comment: str) -> tuple[str, str, str]:
    if YUSSETER_RE.search(source_comment):
        return "manual_source_contains_yusseter", "", "source comment unexpectedly contains Yusseter marker"

    current = target.comment.strip()
    yusseter_match = YUSSETER_RE.search(current)
    if yusseter_match:
        current_prefix = current[: yusseter_match.start()].rstrip()
        yusseter_suffix = current[yusseter_match.start() :].strip()
    else:
        current_prefix = current
        yusseter_suffix = ""

    source_norm = normalize_comment(source_comment)
    prefix_norm = normalize_comment(current_prefix)

    if not prefix_norm:
        status = "ready_apply"
        reason = "target has no non-Yusseter declaration comment"
    elif prefix_norm == source_norm:
        status = "already_present"
        reason = "asil mod comment already present"
    elif source_norm.startswith(prefix_norm + " "):
        status = "ready_apply"
        reason = "asil mod comment safely extends existing comment prefix"
    elif LOCALIZED_AS_RE.search(current_prefix) and source_norm.endswith(" " + prefix_norm):
        status = "ready_apply"
        reason = "asil mod comment safely enriches matching Localized-as suffix"
    else:
        return (
            "manual_conflicting_target_comment",
            "",
            "target has a different non-Yusseter declaration comment",
        )

    code = landed.strip_comment(target.body).rstrip()
    merged_comment = source_comment.strip()
    if yusseter_suffix:
        merged_comment += " " + yusseter_suffix
    proposed = code + " " + merged_comment

    if proposed == target.body:
        return "already_present", proposed, "target line already equals proposed line"
    if status == "already_present" and yusseter_suffix:
        return "already_present", proposed, reason
    return status, proposed, reason


def choose_source_declaration(
    target: Declaration,
    source_id: str,
    occurrence: int | None,
    source_by_id: dict[str, list[Declaration]],
    require_exact_path: bool,
    source_to_target: dict[str, str],
) -> tuple[Declaration | None, str, str]:
    candidates = source_by_id.get(source_id, [])
    if not candidates:
        return None, "skipped_source_title_missing", "asil mod title declaration not found"

    if occurrence is not None:
        if len(candidates) < occurrence:
            return None, "manual_source_occurrence_missing", "mapped source occurrence does not exist"
        return candidates[occurrence - 1], "", ""

    if require_exact_path:
        path_matches = [
            item
            for item in candidates
            if remap_source_path(item.path, source_to_target) == target.path
        ]
        if len(path_matches) == 1:
            return path_matches[0], "", ""
        return None, "manual_hierarchy_mismatch", "same-ID title does not have one mapped hierarchy-path match"

    if len(candidates) == 1:
        return candidates[0], "", ""

    path_matches = [item for item in candidates if item.path == target.path]
    if len(path_matches) == 1:
        return path_matches[0], "", ""
    return None, "manual_source_duplicate", "multiple asil mod declarations remain ambiguous"


def build_rows(args: argparse.Namespace, target_lines: list[str], source_lines: list[str]) -> tuple[list[dict[str, str]], dict[int, str]]:
    target_declarations, target_by_id = parse_declarations(target_lines, "target")
    _, source_by_id = parse_declarations(source_lines, "asil_mod")

    relation_rows = read_csv_rows(args.relation_csv)
    relation_rows_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in relation_rows:
        title_id = row.get("source_title_id", "")
        if title_id:
            relation_rows_by_id[title_id].append(row)
    source_to_target = build_unique_source_to_target_map(relation_rows)

    source_decisions = {
        row.get("title_id", ""): row.get("source_decision", "")
        for row in read_csv_rows(args.source_identity_csv)
        if row.get("title_id", "")
    }

    rows: list[dict[str, str]] = []
    changes: dict[int, str] = {}

    for target in target_declarations:
        relation_rows = relation_rows_by_id.get(target.title_id, [])
        decision = source_decisions.get(target.title_id, "")
        source_id = ""
        occurrence: int | None = None
        eligibility = ""
        status = ""
        reason = ""
        relation_same = ""
        relation_mod = ""
        require_exact_path = False

        if len(target_by_id[target.title_id]) > 1:
            status = "manual_target_duplicate"
            reason = "multiple target declarations share the same title ID"
        elif len(relation_rows) > 1:
            status = "manual_mapping_duplicate"
            reason = "multiple relation rows share the same target title ID"
        else:
            relation = relation_rows[0] if relation_rows else None
            if relation:
                relation_same = relation.get("is_same_title_id", "")
                relation_mod = relation.get("mod_title_id", "")

            if decision == "modlu_kalan":
                eligibility = "modlu_kalan"
                if relation:
                    tokens = parse_source_tokens(relation_mod)
                    if len(tokens) != 1:
                        status = "manual_mapping_ambiguous"
                        reason = "modlu_kalan mapping does not resolve to exactly one asil mod title"
                    else:
                        source_id = tokens[0].title_id
                        occurrence = tokens[0].occurrence
                else:
                    source_id = target.title_id
            elif relation and relation_same.lower() == "yes":
                eligibility = "explicit_same_title_id"
                source_id = target.title_id
            elif relation:
                status = "ineligible_different_id_non_modlu"
                reason = "different-ID mapping is not modlu_kalan"
            elif target.title_id in source_by_id:
                eligibility = "unmapped_same_id_exact_path"
                source_id = target.title_id
                require_exact_path = True
            else:
                status = "ineligible_no_asil_mod_counterpart"
                reason = "no mapping and no same-ID asil mod title"

        source: Declaration | None = None
        source_comment = ""
        proposed = ""

        if not status and source_id:
            source, status, reason = choose_source_declaration(
                target,
                source_id,
                occurrence,
                source_by_id,
                require_exact_path,
                source_to_target,
            )

        if not status and source:
            source_comment = source.comment.strip()
            if not LOCALIZED_AS_RE.search(source_comment):
                status = "skipped_source_no_localized_as"
                reason = "asil mod declaration has no Localized-as comment"
            else:
                status, proposed, reason = merge_comments(target, source_comment)
                if status == "ready_apply":
                    changes[target.line_index] = proposed + target.ending

        rows.append(
            {
                "target_title_id": target.title_id,
                "target_line": str(target.line_no),
                "target_path": " > ".join(target.path),
                "source_decision": decision,
                "eligibility": eligibility,
                "relation_is_same_title_id": relation_same,
                "relation_mod_title_id": relation_mod,
                "asil_mod_title_id": source_id,
                "asil_mod_line": str(source.line_no if source else ""),
                "asil_mod_path": " > ".join(source.path) if source else "",
                "target_comment": target.comment.strip(),
                "asil_mod_comment": source_comment,
                "status": status,
                "reason": reason,
                "current_line": target.body,
                "proposed_line": proposed,
            }
        )

    return rows, changes


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "target_title_id",
        "target_line",
        "target_path",
        "source_decision",
        "eligibility",
        "relation_is_same_title_id",
        "relation_mod_title_id",
        "asil_mod_title_id",
        "asil_mod_line",
        "asil_mod_path",
        "target_comment",
        "asil_mod_comment",
        "status",
        "reason",
        "current_line",
        "proposed_line",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict[str, str]], apply_mode: bool) -> Counter[str]:
    counts = Counter(row["status"] for row in rows)
    eligibility_counts = Counter(
        row["eligibility"] for row in rows if row["status"] in {"ready_apply", "already_present"}
    )
    lines = [
        "# Landed Title Localized-as Comment Transfer",
        "",
        f"- mode: {'apply' if apply_mode else 'dry-run'}",
        f"- total_title_declarations: {len(rows)}",
        f"- ready_apply: {counts.get('ready_apply', 0)}",
        f"- already_present: {counts.get('already_present', 0)}",
        "",
        "## Status Counts",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in sorted(counts.items()))
    lines.extend(["", "## Eligible Comment Sources"])
    lines.extend(f"- `{key}`: {value}" for key, value in sorted(eligibility_counts.items()))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return counts


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    project_root = script_path.parents[3]
    target_root = project_root / "BookmarksGit"
    source_root = project_root.parent / "Leviathonlx MoreBookmarks-Plus" / "BookmarksGit"
    output_dir = project_root / ".codex" / "works" / "analysis" / "generated" / "landed_title_localized_as_comment_transfer"

    parser = argparse.ArgumentParser(description="Transfer safe landed-title Localized-as declaration comments from asil mod.")
    parser.add_argument("--target-landed", type=Path, default=target_root / "common" / "landed_titles" / "00_landed_titles.txt")
    parser.add_argument("--source-landed", type=Path, default=source_root / "common" / "landed_titles" / "00_landed_titles.txt")
    parser.add_argument("--source-repo", type=Path, default=project_root)
    parser.add_argument("--source-revision", default="")
    parser.add_argument("--source-path", default="BookmarksGit/common/landed_titles/00_landed_titles.txt")
    parser.add_argument(
        "--relation-csv",
        type=Path,
        default=project_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv",
    )
    parser.add_argument(
        "--source-identity-csv",
        type=Path,
        default=project_root / ".codex" / "works" / "analysis" / "generated" / "landed_title_source_identity" / "landed_title_source_identity_manual_simple.csv",
    )
    parser.add_argument("--output-dir", type=Path, default=output_dir)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_lines, target_has_bom = read_text_lines(args.target_landed)
    if args.source_revision:
        source_lines = read_git_text_lines(
            args.source_repo,
            args.source_revision,
            args.source_path,
        )
    else:
        source_lines, _ = read_text_lines(args.source_landed)
    rows, changes = build_rows(args, target_lines, source_lines)

    suffix = "apply_report" if args.apply else "dry_run"
    report_path = args.output_dir / f"landed_title_localized_as_comment_transfer_{suffix}.csv"
    summary_path = args.output_dir / f"landed_title_localized_as_comment_transfer_{suffix}_summary.md"
    write_report(report_path, rows)
    counts = write_summary(summary_path, rows, args.apply)

    if args.apply and changes:
        new_lines = list(target_lines)
        for line_index, replacement in changes.items():
            new_lines[line_index] = replacement
        parse_declarations(new_lines, "target_after_apply")
        write_text_lines(args.target_landed, new_lines, target_has_bom)

    print(f"mode={'apply' if args.apply else 'dry-run'}")
    print(f"ready_apply={counts.get('ready_apply', 0)}")
    print(f"already_present={counts.get('already_present', 0)}")
    print(f"manual_review={sum(value for key, value in counts.items() if key.startswith('manual_'))}")
    print(f"report={report_path}")
    print(f"summary={summary_path}")


if __name__ == "__main__":
    main()
