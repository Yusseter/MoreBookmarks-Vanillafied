from __future__ import annotations

import argparse
import csv
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import build_landed_title_asil_mod_metadata_transfer_dry_run as landed


DEFAULT_LANDED_PATH = "BookmarksGit/common/landed_titles/00_landed_titles.txt"
NO_COUNTERPART = "*there_is_no*"
MISSING = "<absent>"
ROOT = "<root>"
TITLE_TOKEN_RE = re.compile(r"\b([hekdcb]_[A-Za-z0-9_'\-]+)\b")
ASSIGNMENT_RE = re.compile(r"^\s*([A-Za-z0-9_@?.:\-]+)\s*=")
CONFLICT_MARKER_RE = re.compile(r"^(<<<<<<<|=======|>>>>>>>)", re.MULTILINE)

HIGH_RISK_KEYS = {
    "__title_exists__",
    "__parent__",
    "__child_order__",
    "capital",
    "province",
    "can_create",
    "can_create_on_partition",
    "can_destroy",
    "ai_primary_priority",
    "personal_relation_vassal",
    "personal_relation_entry",
    "cultural_names",
}
MEDIUM_RISK_KEYS = {
    "landless",
    "definite_form",
    "ruler_uses_title_name",
    "can_be_named_after_dynasty",
    "disable_regnal_numbers",
    "de_jure_drift_disabled",
    "always_follows_primary_heir",
    "destroy_if_invalid_heir",
}


@dataclass(frozen=True)
class DirectProperty:
    key: str
    start_line: int
    end_line: int
    raw: str


@dataclass
class TitleContext:
    parent_id: str = ""
    child_ids: list[str] = field(default_factory=list)


@dataclass
class Snapshot:
    label: str
    lines: list[str]
    titles: dict[str, landed.TitleBlock]
    contexts: dict[str, TitleContext]
    properties: dict[str, dict[str, list[DirectProperty]]]
    duplicate_counts: Counter[str]


@dataclass(frozen=True)
class MappingDecision:
    current_title_id: str
    upstream_title_id: str
    status: str
    source: str
    detail: str


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]
    parser = argparse.ArgumentParser(
        description=(
            "Build a read-only Git four-way audit for an active upstream merge, "
            "including a semantic landed-title decision inventory."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--base", default="")
    parser.add_argument("--ours", default="HEAD")
    parser.add_argument("--theirs", default="MERGE_HEAD")
    parser.add_argument("--landed-path", default=DEFAULT_LANDED_PATH)
    parser.add_argument(
        "--relation-csv",
        type=Path,
        default=repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / ".codex/works/analysis/generated/upstream_merge_audit",
    )
    return parser.parse_args()


def git_bytes(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
    return result.stdout


def git_text(repo_root: Path, *args: str) -> str:
    return git_bytes(repo_root, *args).decode("utf-8-sig", errors="replace")


def resolve_revision(repo_root: Path, revision: str) -> str:
    return git_text(repo_root, "rev-parse", "--verify", revision).strip()


def read_git_file(repo_root: Path, revision: str, relative_path: str) -> str:
    return git_bytes(repo_root, "show", f"{revision}:{relative_path}").decode(
        "utf-8-sig", errors="replace"
    )


def count_title_occurrences(lines: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for line in lines:
        match = landed.TITLE_RE.match(landed.strip_comment(line))
        if match:
            counts[match.group(1)] += 1
    return counts


def build_title_contexts(
    titles: dict[str, landed.TitleBlock],
) -> dict[str, TitleContext]:
    contexts = {title_id: TitleContext() for title_id in titles}
    stack: list[landed.TitleBlock] = []

    for block in sorted(titles.values(), key=lambda item: (item.start_line, -item.end_line)):
        while stack and block.start_line > stack[-1].end_line:
            stack.pop()
        while stack and block.start_depth <= stack[-1].start_depth:
            stack.pop()
        if stack:
            parent = stack[-1]
            contexts[block.title_id].parent_id = parent.title_id
            contexts[parent.title_id].child_ids.append(block.title_id)
        stack.append(block)

    return contexts


def extract_direct_properties(
    lines: list[str], block: landed.TitleBlock
) -> dict[str, list[DirectProperty]]:
    wanted_depth = block.start_depth + 1
    depth = wanted_depth
    index = block.start_line
    end_index = block.end_line - 1
    properties: dict[str, list[DirectProperty]] = defaultdict(list)

    while index < end_index:
        line = lines[index]
        clean = landed.strip_comment(line)
        assignment = ASSIGNMENT_RE.match(clean)
        is_child_title = landed.TITLE_RE.match(clean) is not None

        if depth == wanted_depth and assignment and not is_child_title:
            key = assignment.group(1)
            property_start = index
            property_end = index
            property_depth = depth + landed.brace_delta(line)
            if "{" in clean:
                while property_depth > wanted_depth and property_end + 1 < end_index:
                    property_end += 1
                    property_depth += landed.brace_delta(lines[property_end])
            raw = "".join(lines[property_start : property_end + 1])
            properties[key].append(
                DirectProperty(
                    key=key,
                    start_line=property_start + 1,
                    end_line=property_end + 1,
                    raw=raw,
                )
            )
            depth += sum(
                landed.brace_delta(lines[item])
                for item in range(property_start, property_end + 1)
            )
            index = property_end + 1
            continue

        depth += landed.brace_delta(line)
        index += 1

    return dict(properties)


def build_snapshot(label: str, text: str) -> Snapshot:
    lines = text.splitlines(keepends=True)
    titles = landed.parse_title_blocks(lines)
    contexts = build_title_contexts(titles)
    properties = {
        title_id: extract_direct_properties(lines, block)
        for title_id, block in titles.items()
    }
    duplicate_counts = Counter(
        {
            title_id: count
            for title_id, count in count_title_occurrences(lines).items()
            if count > 1
        }
    )
    return Snapshot(
        label=label,
        lines=lines,
        titles=titles,
        contexts=contexts,
        properties=properties,
        duplicate_counts=duplicate_counts,
    )


def split_upstream_tokens(raw_value: str) -> list[str]:
    tokens: list[str] = []
    for part in re.split(r"[&;]", raw_value):
        token = part.replace("(second)", "").strip()
        if token and token != NO_COUNTERPART:
            tokens.append(token)
    return tokens


def load_relation_index(path: Path) -> dict[str, list[dict[str, str]]]:
    relation_index: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw_row in csv.DictReader(handle, skipinitialspace=True):
            row = {str(key).strip(): (value or "").strip() for key, value in raw_row.items()}
            current_id = row.get("source_title_id", "")
            if current_id:
                relation_index[current_id].append(row)
    return dict(relation_index)


def resolve_mapping(
    current_title_id: str,
    relation_index: dict[str, list[dict[str, str]]],
    upstream_ids: set[str],
) -> MappingDecision:
    rows = relation_index.get(current_title_id, [])
    if len(rows) > 1:
        return MappingDecision(
            current_title_id,
            "",
            "ambiguous_relation_rows",
            "relation_csv",
            f"row_count={len(rows)}",
        )
    if rows:
        raw_value = rows[0].get("mod_title_id", "")
        tokens = split_upstream_tokens(raw_value)
        if len(tokens) == 1:
            return MappingDecision(
                current_title_id,
                tokens[0],
                "mapped",
                "relation_csv",
                raw_value,
            )
        if not tokens:
            return MappingDecision(
                current_title_id,
                "",
                "explicit_no_counterpart",
                "relation_csv",
                raw_value,
            )
        return MappingDecision(
            current_title_id,
            "",
            "ambiguous_multiple_upstream_titles",
            "relation_csv",
            raw_value,
        )
    if current_title_id in upstream_ids:
        return MappingDecision(
            current_title_id,
            current_title_id,
            "mapped",
            "implicit_same_id",
            current_title_id,
        )
    return MappingDecision(
        current_title_id,
        "",
        "no_upstream_counterpart",
        "implicit",
        "title id is absent from base and theirs",
    )


def build_unique_upstream_to_current(
    decisions: Iterable[MappingDecision],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    reverse: dict[str, list[str]] = defaultdict(list)
    for decision in decisions:
        if decision.status == "mapped" and decision.upstream_title_id:
            reverse[decision.upstream_title_id].append(decision.current_title_id)
    unique = {
        upstream_id: current_ids[0]
        for upstream_id, current_ids in reverse.items()
        if len(current_ids) == 1
    }
    return unique, dict(reverse)


def remap_title_tokens(text: str, upstream_to_current: dict[str, str]) -> str:
    return TITLE_TOKEN_RE.sub(
        lambda match: upstream_to_current.get(match.group(1), match.group(1)),
        text,
    )


def normalize_raw(
    raw: str,
    *,
    upstream_side: bool,
    upstream_to_current: dict[str, str],
) -> str:
    normalized = landed.normalize_block(raw)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if upstream_side:
        normalized = remap_title_tokens(normalized, upstream_to_current)
    return normalized or MISSING


def inline_opening_comment(snapshot: Snapshot, title_id: str) -> str:
    block = snapshot.titles.get(title_id)
    if not block:
        return MISSING
    line = snapshot.lines[block.start_line - 1].rstrip("\r\n")
    if "#" not in line:
        return MISSING
    return re.sub(r"\s+", " ", line.split("#", 1)[1].strip()) or MISSING


def property_raw(snapshot: Snapshot, title_id: str, key: str) -> tuple[str, str]:
    block = snapshot.titles.get(title_id)
    if key == "__title_exists__":
        return ("yes" if block else "no"), str(block.start_line if block else "")
    if not block:
        return MISSING, ""
    if key == "__parent__":
        parent = snapshot.contexts[title_id].parent_id or ROOT
        return parent, str(block.start_line)
    if key == "__child_order__":
        children = snapshot.contexts[title_id].child_ids
        return (" | ".join(children) if children else MISSING), str(block.start_line)
    if key == "__opening_comment__":
        return inline_opening_comment(snapshot, title_id), str(block.start_line)

    occurrences = snapshot.properties.get(title_id, {}).get(key, [])
    if not occurrences:
        return MISSING, ""
    raw = "\n<next_occurrence>\n".join(item.raw for item in occurrences)
    lines = ";".join(str(item.start_line) for item in occurrences)
    return raw, lines


def normalized_value(
    snapshot: Snapshot,
    title_id: str,
    key: str,
    *,
    upstream_side: bool,
    upstream_to_current: dict[str, str],
) -> tuple[str, str, str]:
    raw, line = property_raw(snapshot, title_id, key)
    if key == "__title_exists__":
        return raw, raw, line
    if raw == MISSING:
        return MISSING, MISSING, line
    if key == "__opening_comment__":
        return raw, raw, line
    normalized = normalize_raw(
        raw,
        upstream_side=upstream_side,
        upstream_to_current=upstream_to_current,
    )
    return normalized, raw, line


def classify_change(base: str, ours: str, theirs: str, working: str) -> str:
    upstream_changed = base != theirs
    yusseter_changed = base != ours

    if not upstream_changed and not yusseter_changed:
        return "unchanged" if working == ours else "working_changed_only"
    if upstream_changed and not yusseter_changed:
        if working == theirs:
            return "resolved_take_upstream"
        if working == ours:
            return "pending_upstream_change"
        return "custom_resolution_for_upstream_change"
    if not upstream_changed and yusseter_changed:
        if working == ours:
            return "preserved_yusseter_change"
        if working == base:
            return "yusseter_change_lost"
        return "modified_yusseter_change"
    if ours == theirs:
        return "both_changed_same" if working == ours else "both_changed_same_working_differs"
    if working == ours:
        return "conflict_kept_yusseter"
    if working == theirs:
        return "conflict_took_upstream"
    if working == base:
        return "conflict_reverted_to_base"
    return "conflict_custom_resolution"


def risk_for(key: str, raw_values: Iterable[str]) -> str:
    if key == "__opening_comment__":
        return "informational"
    if key in HIGH_RISK_KEYS:
        return "high"
    if any(TITLE_TOKEN_RE.search(raw) for raw in raw_values if raw != MISSING):
        return "high"
    if key in MEDIUM_RISK_KEYS:
        return "medium"
    return "low"


def recommendation_for(classification: str, risk: str) -> str:
    if classification == "pending_upstream_change":
        return "manual_review" if risk in {"high", "medium"} else "candidate_take_upstream"
    if classification == "resolved_take_upstream":
        return "verify_current_resolution"
    if classification in {
        "custom_resolution_for_upstream_change",
        "yusseter_change_lost",
        "modified_yusseter_change",
        "both_changed_same_working_differs",
        "conflict_kept_yusseter",
        "conflict_took_upstream",
        "conflict_reverted_to_base",
        "conflict_custom_resolution",
    }:
        return "manual_review"
    if classification == "preserved_yusseter_change":
        return "keep_yusseter"
    if classification == "both_changed_same":
        return "no_action_same_result"
    if classification == "working_changed_only":
        return "review_working_only_change"
    return "no_action"


def preview(value: str, limit: int = 320) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) <= limit else value[: limit - 3] + "..."


def title_property_keys(
    base: Snapshot,
    ours: Snapshot,
    theirs: Snapshot,
    working: Snapshot,
    upstream_id: str,
    current_id: str,
) -> list[str]:
    keys = {"__title_exists__", "__parent__", "__child_order__"}
    for snapshot, title_id in (
        (base, upstream_id),
        (ours, current_id),
        (theirs, upstream_id),
        (working, current_id),
    ):
        keys.update(snapshot.properties.get(title_id, {}))

    base_comment = inline_opening_comment(base, upstream_id)
    theirs_comment = inline_opening_comment(theirs, upstream_id)
    ours_comment = inline_opening_comment(ours, current_id)
    working_comment = inline_opening_comment(working, current_id)
    if base_comment != theirs_comment or ours_comment != working_comment:
        keys.add("__opening_comment__")

    pseudo_order = ["__title_exists__", "__parent__", "__child_order__", "__opening_comment__"]
    return [key for key in pseudo_order if key in keys] + sorted(keys - set(pseudo_order))


def build_landed_title_rows(
    base: Snapshot,
    ours: Snapshot,
    theirs: Snapshot,
    working: Snapshot,
    relation_path: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]], Counter[str], Counter[str]]:
    relation_index = load_relation_index(relation_path)
    upstream_ids = set(base.titles) | set(theirs.titles)
    current_ids = set(ours.titles) | set(working.titles) | set(relation_index)
    decisions = [
        resolve_mapping(current_id, relation_index, upstream_ids)
        for current_id in sorted(current_ids)
    ]
    upstream_to_current, reverse_all = build_unique_upstream_to_current(decisions)
    covered_upstream_ids = {
        decision.upstream_title_id
        for decision in decisions
        if decision.status == "mapped" and decision.upstream_title_id
    }

    property_rows: list[dict[str, object]] = []
    title_rows: list[dict[str, object]] = []
    class_counts: Counter[str] = Counter()
    mapping_counts: Counter[str] = Counter()

    for decision in decisions:
        current_id = decision.current_title_id
        upstream_id = decision.upstream_title_id
        title_class_counts: Counter[str] = Counter()
        title_recommendations: Counter[str] = Counter()
        duplicate_detail: list[str] = []
        for snapshot, title_id in (
            (base, upstream_id),
            (ours, current_id),
            (theirs, upstream_id),
            (working, current_id),
        ):
            count = snapshot.duplicate_counts.get(title_id, 0) if title_id else 0
            if count:
                duplicate_detail.append(f"{snapshot.label}:{title_id}:{count}")

        if duplicate_detail:
            mapping_status = "duplicate_definition_manual_review"
        elif decision.status == "mapped":
            reverse_targets = reverse_all.get(upstream_id, [])
            if len(reverse_targets) > 1:
                mapping_status = "ambiguous_reverse_mapping"
            else:
                mapping_status = "mapped"

            if mapping_status == "mapped":
                for key in title_property_keys(
                    base, ours, theirs, working, upstream_id, current_id
                ):
                    base_value, base_raw, base_line = normalized_value(
                        base,
                        upstream_id,
                        key,
                        upstream_side=True,
                        upstream_to_current=upstream_to_current,
                    )
                    ours_value, ours_raw, ours_line = normalized_value(
                        ours,
                        current_id,
                        key,
                        upstream_side=False,
                        upstream_to_current=upstream_to_current,
                    )
                    theirs_value, theirs_raw, theirs_line = normalized_value(
                        theirs,
                        upstream_id,
                        key,
                        upstream_side=True,
                        upstream_to_current=upstream_to_current,
                    )
                    working_value, working_raw, working_line = normalized_value(
                        working,
                        current_id,
                        key,
                        upstream_side=False,
                        upstream_to_current=upstream_to_current,
                    )
                    classification = classify_change(
                        base_value, ours_value, theirs_value, working_value
                    )
                    class_counts[classification] += 1
                    title_class_counts[classification] += 1
                    risk = risk_for(key, [base_raw, ours_raw, theirs_raw, working_raw])
                    recommendation = recommendation_for(classification, risk)
                    title_recommendations[recommendation] += 1

                    if classification == "unchanged":
                        continue
                    property_rows.append(
                        {
                            "current_title_id": current_id,
                            "upstream_title_id": upstream_id,
                            "mapping_source": decision.source,
                            "key": key,
                            "classification": classification,
                            "risk": risk,
                            "recommendation": recommendation,
                            "upstream_changed": "yes" if base_value != theirs_value else "no",
                            "yusseter_changed": "yes" if base_value != ours_value else "no",
                            "working_matches_ours": "yes" if working_value == ours_value else "no",
                            "working_matches_theirs": "yes" if working_value == theirs_value else "no",
                            "base_line": base_line,
                            "ours_line": ours_line,
                            "theirs_line": theirs_line,
                            "working_line": working_line,
                            "base_value": preview(base_value),
                            "ours_value": preview(ours_value),
                            "theirs_value": preview(theirs_value),
                            "working_value": preview(working_value),
                        }
                    )
        else:
            mapping_status = decision.status
        mapping_counts[mapping_status] += 1

        if mapping_status in {
            "ambiguous_relation_rows",
            "ambiguous_multiple_upstream_titles",
            "ambiguous_reverse_mapping",
            "duplicate_definition_manual_review",
        }:
            overall = "manual_mapping_review"
        elif mapping_status in {"explicit_no_counterpart", "no_upstream_counterpart"}:
            overall = "yusseter_only_no_upstream_counterpart"
        elif title_recommendations.get("manual_review"):
            overall = "manual_review"
        elif title_recommendations.get("candidate_take_upstream"):
            overall = "candidate_take_upstream"
        elif title_recommendations.get("verify_current_resolution"):
            overall = "verify_current_resolution"
        elif title_recommendations.get("keep_yusseter"):
            overall = "preserved_yusseter"
        else:
            overall = "no_action"

        title_rows.append(
            {
                "current_title_id": current_id,
                "upstream_title_id": upstream_id,
                "mapping_status": mapping_status,
                "mapping_source": decision.source,
                "mapping_detail": ";".join(
                    part for part in [decision.detail, *duplicate_detail] if part
                ),
                "base_exists": "yes" if upstream_id in base.titles else "no",
                "ours_exists": "yes" if current_id in ours.titles else "no",
                "theirs_exists": "yes" if upstream_id in theirs.titles else "no",
                "working_exists": "yes" if current_id in working.titles else "no",
                "changed_property_rows": sum(title_class_counts.values())
                - title_class_counts.get("unchanged", 0),
                "manual_review_rows": title_recommendations.get("manual_review", 0),
                "candidate_rows": title_recommendations.get("candidate_take_upstream", 0),
                "verify_rows": title_recommendations.get("verify_current_resolution", 0),
                "overall_status": overall,
            }
        )

    for upstream_id in sorted(upstream_ids - covered_upstream_ids):
        base_exists = upstream_id in base.titles
        theirs_exists = upstream_id in theirs.titles
        if base_exists == theirs_exists:
            base_signature = title_signature(base, upstream_id)
            theirs_signature = title_signature(theirs, upstream_id)
            if base_signature == theirs_signature:
                continue
            status = "upstream_changed_without_current_mapping"
        elif theirs_exists:
            status = "upstream_added_without_current_mapping"
        else:
            status = "upstream_removed_without_current_mapping"
        mapping_counts[status] += 1
        title_rows.append(
            {
                "current_title_id": "",
                "upstream_title_id": upstream_id,
                "mapping_status": status,
                "mapping_source": "unmapped_upstream_scan",
                "mapping_detail": "",
                "base_exists": "yes" if base_exists else "no",
                "ours_exists": "no",
                "theirs_exists": "yes" if theirs_exists else "no",
                "working_exists": "no",
                "changed_property_rows": "",
                "manual_review_rows": 1,
                "candidate_rows": 0,
                "verify_rows": 0,
                "overall_status": "manual_mapping_review",
            }
        )

    return property_rows, title_rows, class_counts, mapping_counts


def build_duplicate_rows(snapshots: Iterable[Snapshot]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for snapshot in snapshots:
        line_numbers: dict[str, list[int]] = defaultdict(list)
        for line_number, line in enumerate(snapshot.lines, start=1):
            match = landed.TITLE_RE.match(landed.strip_comment(line))
            if match:
                line_numbers[match.group(1)].append(line_number)
        for title_id, count in sorted(snapshot.duplicate_counts.items()):
            rows.append(
                {
                    "snapshot": snapshot.label,
                    "title_id": title_id,
                    "count": count,
                    "line_numbers": ";".join(
                        str(line_number) for line_number in line_numbers[title_id]
                    ),
                }
            )
    return rows


def title_signature(snapshot: Snapshot, title_id: str) -> str:
    if title_id not in snapshot.titles:
        return MISSING
    context = snapshot.contexts[title_id]
    parts = [context.parent_id or ROOT, "|".join(context.child_ids)]
    for key in sorted(snapshot.properties.get(title_id, {})):
        raw, _ = property_raw(snapshot, title_id, key)
        parts.append(f"{key}={normalize_raw(raw, upstream_side=False, upstream_to_current={})}")
    return "\n".join(parts)


def classify_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if "/common/landed_titles/" in normalized:
        return "landed_titles"
    if "/history/titles/" in normalized:
        return "title_history"
    if "/history/provinces/" in normalized:
        return "province_history"
    if "/localization/" in normalized or normalized.startswith("english/"):
        return "localization"
    if "/gfx/map/map_object_data/" in normalized:
        return "map_object_locators"
    if "/map_data/" in normalized:
        return "map_data"
    if "/common/" in normalized:
        return "common_script"
    if "/history/" in normalized:
        return "history"
    if "/gfx/" in normalized:
        return "gfx"
    return "other"


def parse_name_status(text: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            rows.append((status, parts[1], parts[2]))
        elif len(parts) >= 2:
            rows.append((status, parts[1], ""))
    return rows


def build_commit_ledger(
    repo_root: Path, base_sha: str, theirs_sha: str, landed_path: str
) -> list[dict[str, object]]:
    revisions = [
        item
        for item in git_text(
            repo_root, "rev-list", "--reverse", "--topo-order", f"{base_sha}..{theirs_sha}"
        ).splitlines()
        if item
    ]
    rows: list[dict[str, object]] = []
    for revision in revisions:
        meta = git_text(
            repo_root,
            "show",
            "-s",
            "--format=%H%x09%aI%x09%an%x09%P%x09%s",
            revision,
        ).rstrip("\r\n")
        commit, authored_at, author, parents, subject = (meta.split("\t", 4) + [""] * 5)[:5]
        changed = parse_name_status(
            git_text(
                repo_root,
                "diff-tree",
                "--first-parent",
                "--no-commit-id",
                "--name-status",
                "-r",
                "-M",
                revision,
            )
        )
        paths = [new_path or old_path for _, old_path, new_path in changed]
        domains = sorted({classify_path(path) for path in paths})
        rows.append(
            {
                "commit": commit,
                "authored_at": authored_at,
                "author": author,
                "subject": subject,
                "parent_count": len([item for item in parents.split() if item]),
                "changed_file_count": len(paths),
                "landed_titles_touched": "yes" if landed_path in paths else "no",
                "domains": ";".join(domains),
                "paths": ";".join(paths),
            }
        )
    return rows


def build_changed_file_rows(
    repo_root: Path, base_sha: str, theirs_sha: str, unmerged: set[str]
) -> list[dict[str, object]]:
    changed = parse_name_status(
        git_text(repo_root, "diff", "--name-status", "-M", base_sha, theirs_sha)
    )
    return [
        {
            "status": status,
            "old_path": old_path,
            "new_path": new_path,
            "effective_path": new_path or old_path,
            "domain": classify_path(new_path or old_path),
            "currently_unmerged": "yes" if (new_path or old_path) in unmerged else "no",
        }
        for status, old_path, new_path in changed
    ]


def read_unmerged_paths(repo_root: Path) -> list[str]:
    raw = git_bytes(repo_root, "diff", "--name-only", "--diff-filter=U", "-z")
    return [item.decode("utf-8", errors="replace") for item in raw.split(b"\0") if item]


def build_unmerged_rows(repo_root: Path, paths: list[str]) -> list[dict[str, object]]:
    stage_rows: dict[str, dict[str, str]] = defaultdict(dict)
    for line in git_text(repo_root, "ls-files", "-u").splitlines():
        match = re.match(r"^(\d+) ([0-9a-f]+) ([123])\t(.+)$", line)
        if match:
            mode, blob, stage, path = match.groups()
            stage_rows[path][f"stage_{stage}_blob"] = blob
            stage_rows[path][f"stage_{stage}_mode"] = mode

    rows: list[dict[str, object]] = []
    for path in paths:
        markers: int | str = "binary_or_missing"
        working_path = repo_root / path
        if working_path.is_file() and working_path.suffix.lower() not in {
            ".png",
            ".jpg",
            ".jpeg",
            ".dds",
            ".pdn",
        }:
            text = working_path.read_text(encoding="utf-8-sig", errors="replace")
            markers = len(CONFLICT_MARKER_RE.findall(text))
        rows.append(
            {
                "path": path,
                "domain": classify_path(path),
                "conflict_marker_count": markers,
                "stage_1_blob": stage_rows[path].get("stage_1_blob", ""),
                "stage_2_blob": stage_rows[path].get("stage_2_blob", ""),
                "stage_3_blob": stage_rows[path].get("stage_3_blob", ""),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_counter_csv(path: Path, counter: Counter[str], key_name: str) -> None:
    write_csv(
        path,
        [{key_name: key, "count": count} for key, count in sorted(counter.items())],
        [key_name, "count"],
    )


def write_summary(
    path: Path,
    *,
    branch: str,
    base_sha: str,
    ours_sha: str,
    theirs_sha: str,
    commit_rows: list[dict[str, object]],
    changed_rows: list[dict[str, object]],
    unmerged_rows: list[dict[str, object]],
    title_rows: list[dict[str, object]],
    property_rows: list[dict[str, object]],
    class_counts: Counter[str],
    mapping_counts: Counter[str],
    snapshots: list[Snapshot],
) -> None:
    title_status_counts = Counter(str(row["overall_status"]) for row in title_rows)
    domain_counts = Counter(str(row["domain"]) for row in changed_rows)
    duplicate_lines = []
    for snapshot in snapshots:
        duplicate_lines.append(
            f"- {snapshot.label}_duplicate_title_ids: {len(snapshot.duplicate_counts)}"
        )
        duplicate_lines.append(
            f"- {snapshot.label}_extra_title_definitions: "
            f"{sum(count - 1 for count in snapshot.duplicate_counts.values())}"
        )

    lines = [
        "# Upstream Merge Audit Summary",
        "",
        "## Git Anchors",
        f"- branch: `{branch}`",
        f"- base_candidate: `{base_sha}`",
        f"- ours: `{ours_sha}`",
        f"- theirs: `{theirs_sha}`",
        "- baseline_status: `git_merge_base_not_yet_semantically_certified`",
        f"- upstream_commits_in_range: {len(commit_rows)}",
        f"- net_changed_files: {len(changed_rows)}",
        f"- currently_unmerged_files: {len(unmerged_rows)}",
        "",
        "## Landed Title Inventory",
        f"- title_rows: {len(title_rows)}",
        f"- changed_property_rows: {len(property_rows)}",
        *duplicate_lines,
        "",
        "### Title Status",
        *[f"- `{key}`: {value}" for key, value in sorted(title_status_counts.items())],
        "",
        "### Property Classification",
        *[f"- `{key}`: {value}" for key, value in sorted(class_counts.items())],
        "",
        "### Mapping Status",
        *[f"- `{key}`: {value}" for key, value in sorted(mapping_counts.items())],
        "",
        "## Net Changed File Domains",
        *[f"- `{key}`: {value}" for key, value in sorted(domain_counts.items())],
        "",
        "## Safety",
        "- This run is audit-only; CK3 source files and the Git index are not modified.",
        "- `candidate_take_upstream` is not an automatic apply decision.",
        "- Hierarchy, child order, capitals, province ids, behavioral blocks, and title references remain manual-review items.",
        "- The next gate is review of `manual_review` and `candidate_take_upstream` rows before any source edit.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    ours_sha = resolve_revision(repo_root, args.ours)
    theirs_sha = resolve_revision(repo_root, args.theirs)
    base_sha = (
        resolve_revision(repo_root, args.base)
        if args.base
        else git_text(repo_root, "merge-base", ours_sha, theirs_sha).strip()
    )
    branch = git_text(repo_root, "branch", "--show-current").strip()

    base_snapshot = build_snapshot(
        "base", read_git_file(repo_root, base_sha, args.landed_path)
    )
    ours_snapshot = build_snapshot(
        "ours", read_git_file(repo_root, ours_sha, args.landed_path)
    )
    theirs_snapshot = build_snapshot(
        "theirs", read_git_file(repo_root, theirs_sha, args.landed_path)
    )
    working_path = repo_root / args.landed_path
    working_snapshot = build_snapshot(
        "working", working_path.read_text(encoding="utf-8-sig")
    )

    property_rows, title_rows, class_counts, mapping_counts = build_landed_title_rows(
        base_snapshot,
        ours_snapshot,
        theirs_snapshot,
        working_snapshot,
        args.relation_csv,
    )
    unmerged_paths = read_unmerged_paths(repo_root)
    unmerged_rows = build_unmerged_rows(repo_root, unmerged_paths)
    commit_rows = build_commit_ledger(
        repo_root, base_sha, theirs_sha, args.landed_path
    )
    changed_rows = build_changed_file_rows(
        repo_root, base_sha, theirs_sha, set(unmerged_paths)
    )
    candidate_rows = [
        row for row in property_rows if row["recommendation"] == "candidate_take_upstream"
    ]
    manual_review_rows = [
        row for row in property_rows if row["recommendation"] == "manual_review"
    ]
    comment_candidate_rows = [
        row for row in candidate_rows if row["key"] == "__opening_comment__"
    ]
    duplicate_rows = build_duplicate_rows(
        [base_snapshot, ours_snapshot, theirs_snapshot, working_snapshot]
    )

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    property_fieldnames = [
        "current_title_id",
        "upstream_title_id",
        "mapping_source",
        "key",
        "classification",
        "risk",
        "recommendation",
        "upstream_changed",
        "yusseter_changed",
        "working_matches_ours",
        "working_matches_theirs",
        "base_line",
        "ours_line",
        "theirs_line",
        "working_line",
        "base_value",
        "ours_value",
        "theirs_value",
        "working_value",
    ]
    write_csv(
        output_dir / "upstream_commit_ledger.csv",
        commit_rows,
        [
            "commit",
            "authored_at",
            "author",
            "subject",
            "parent_count",
            "changed_file_count",
            "landed_titles_touched",
            "domains",
            "paths",
        ],
    )
    write_csv(
        output_dir / "upstream_net_changed_files.csv",
        changed_rows,
        ["status", "old_path", "new_path", "effective_path", "domain", "currently_unmerged"],
    )
    write_csv(
        output_dir / "unmerged_files.csv",
        unmerged_rows,
        [
            "path",
            "domain",
            "conflict_marker_count",
            "stage_1_blob",
            "stage_2_blob",
            "stage_3_blob",
        ],
    )
    write_csv(
        output_dir / "landed_title_four_way_properties.csv",
        property_rows,
        property_fieldnames,
    )
    write_csv(
        output_dir / "landed_title_candidate_take_upstream.csv",
        candidate_rows,
        property_fieldnames,
    )
    write_csv(
        output_dir / "landed_title_manual_review.csv",
        manual_review_rows,
        property_fieldnames,
    )
    write_csv(
        output_dir / "landed_title_comment_candidates.csv",
        comment_candidate_rows,
        property_fieldnames,
    )
    write_csv(
        output_dir / "landed_title_duplicate_ids.csv",
        duplicate_rows,
        ["snapshot", "title_id", "count", "line_numbers"],
    )
    write_csv(
        output_dir / "landed_title_four_way_titles.csv",
        title_rows,
        [
            "current_title_id",
            "upstream_title_id",
            "mapping_status",
            "mapping_source",
            "mapping_detail",
            "base_exists",
            "ours_exists",
            "theirs_exists",
            "working_exists",
            "changed_property_rows",
            "manual_review_rows",
            "candidate_rows",
            "verify_rows",
            "overall_status",
        ],
    )
    write_counter_csv(
        output_dir / "landed_title_property_classification_counts.csv",
        class_counts,
        "classification",
    )
    write_counter_csv(
        output_dir / "landed_title_mapping_counts.csv",
        mapping_counts,
        "mapping_status",
    )
    write_summary(
        output_dir / "upstream_merge_audit_summary.md",
        branch=branch,
        base_sha=base_sha,
        ours_sha=ours_sha,
        theirs_sha=theirs_sha,
        commit_rows=commit_rows,
        changed_rows=changed_rows,
        unmerged_rows=unmerged_rows,
        title_rows=title_rows,
        property_rows=property_rows,
        class_counts=class_counts,
        mapping_counts=mapping_counts,
        snapshots=[base_snapshot, ours_snapshot, theirs_snapshot, working_snapshot],
    )

    print(f"base={base_sha}")
    print(f"ours={ours_sha}")
    print(f"theirs={theirs_sha}")
    print(f"upstream_commits={len(commit_rows)}")
    print(f"net_changed_files={len(changed_rows)}")
    print(f"unmerged_files={len(unmerged_rows)}")
    print(f"landed_title_rows={len(title_rows)}")
    print(f"landed_property_rows={len(property_rows)}")
    print(f"output_dir={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
