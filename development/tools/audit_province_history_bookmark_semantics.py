from __future__ import annotations

import argparse
import csv
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import audit_bookmark_runtime_static as runtime
import audit_landed_title_source_identity as landed


DEFAULT_ASIL_MOD_REPO = (
    Path(__file__).resolve().parents[2].parent / "Leviathonlx MoreBookmarks-Plus"
)
DEFAULT_VANILLA_GAME_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
)
DEFAULT_BASELINE = "09588cbb5212a31bc4a373b6990b2c4da1203a35"
OUTPUT_PATH = (
    "development/analysis/generated/repo_integration_closure/"
    "province_history_bookmark_semantics"
)

NUMERIC_HEADER_RE = re.compile(r"^\s*(\d+)\s*=\s*\{")
GENERIC_HEADER_RE = re.compile(r"^\s*([A-Za-z0-9_.'\-]+)\s*=\s*\{")
STATE_ASSIGNMENT_RE = re.compile(
    r"\b(culture|religion|faith|holding)\s*=\s*\"?([A-Za-z0-9_.:\-]+)\"?"
)
FAITHS_RE = re.compile(r"^\s*faiths\s*=\s*\{")
MAPPING_RE = re.compile(r"^\s*(\d+)\s*=\s*(\d+)\s*$")


@dataclass(frozen=True)
class ProvinceEvent:
    date: runtime.Date
    values: dict[str, str]
    path: str
    line: int


@dataclass(frozen=True)
class ProvinceState:
    culture: str = ""
    religion: str = ""
    holding: str = ""
    culture_path: str = ""
    religion_path: str = ""
    holding_path: str = ""
    culture_line: int = 0
    religion_line: int = 0
    holding_line: int = 0
    culture_mapped_from: int = 0
    religion_mapped_from: int = 0
    culture_mapping_path: str = ""
    religion_mapping_path: str = ""
    culture_mapping_line: int = 0
    religion_mapping_line: int = 0

    def signature(self) -> str:
        return f"culture={self.culture};religion={self.religion};holding={self.holding}"


@dataclass
class ProvinceDataset:
    label: str
    events: dict[int, list[ProvinceEvent]]
    mapping: dict[int, int]
    mapping_locations: dict[int, tuple[str, int]]

    def direct_state_at(self, province_id: int, date: runtime.Date) -> ProvinceState:
        values: dict[str, str | int] = {
            "culture": "",
            "religion": "",
            "holding": "",
            "culture_path": "",
            "religion_path": "",
            "holding_path": "",
            "culture_line": 0,
            "religion_line": 0,
            "holding_line": 0,
            "culture_mapped_from": 0,
            "religion_mapped_from": 0,
            "culture_mapping_path": "",
            "religion_mapping_path": "",
            "culture_mapping_line": 0,
            "religion_mapping_line": 0,
        }
        for event in self.events.get(province_id, []):
            if event.date > date:
                break
            for key, value in event.values.items():
                values[key] = value
                values[f"{key}_path"] = event.path
                values[f"{key}_line"] = event.line
        return ProvinceState(**values)

    def state_at(
        self,
        province_id: int,
        date: runtime.Date,
        visited: frozenset[int] | None = None,
    ) -> ProvinceState:
        direct = self.direct_state_at(province_id, date)
        source_id = self.mapping.get(province_id)
        if source_id is None or source_id == province_id:
            return direct
        visited = visited or frozenset()
        if province_id in visited or source_id in visited:
            return direct
        source = self.state_at(source_id, date, visited | {province_id})
        values = dict(direct.__dict__)
        mapping_path, mapping_line = self.mapping_locations.get(
            province_id, ("", 0)
        )
        for field in ("culture", "religion"):
            if getattr(direct, field) or not getattr(source, field):
                continue
            values[field] = getattr(source, field)
            values[f"{field}_path"] = getattr(source, f"{field}_path")
            values[f"{field}_line"] = getattr(source, f"{field}_line")
            values[f"{field}_mapped_from"] = source_id
            values[f"{field}_mapping_path"] = mapping_path
            values[f"{field}_mapping_line"] = mapping_line
        return ProvinceState(**values)


@dataclass(frozen=True)
class SourceRef:
    kind: str
    source_province_id: int
    row_status: str


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit landed province-history semantics at every active bookmark date"
        )
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument("--asil-mod-repo", type=Path, default=DEFAULT_ASIL_MOD_REPO)
    parser.add_argument(
        "--vanilla-game-root", type=Path, default=DEFAULT_VANILLA_GAME_ROOT
    )
    parser.add_argument("--baseline-revision", default=DEFAULT_BASELINE)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def parse_state_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in STATE_ASSIGNMENT_RE.findall(text):
        values["religion" if key == "faith" else key] = value
    return values


def parse_province_events(
    blocks: dict[str, list[runtime.Block]],
) -> dict[int, list[ProvinceEvent]]:
    events: dict[int, list[ProvinceEvent]] = defaultdict(list)
    beginning = runtime.Date(-100000, 1, 1)
    for raw_id, province_blocks in blocks.items():
        province_id = int(raw_id)
        for block in province_blocks:
            for entry in runtime.direct_entries(block):
                date = runtime.parse_date(entry.key)
                if date is None and entry.key not in {
                    "culture", "religion", "faith", "holding"
                }:
                    continue
                values = parse_state_values(runtime.direct_body(entry.lines))
                if date is None:
                    date = beginning
                if values:
                    events[province_id].append(
                        ProvinceEvent(
                            date,
                            values,
                            block.path,
                            block.start_line + entry.relative_start,
                        )
                    )
        events[province_id].sort(key=lambda item: (item.date, item.path, item.line))
    return dict(events)


def build_dataset(
    label: str,
    mod_texts: dict[str, str],
    vanilla_texts: dict[str, str],
    mod_mapping_texts: dict[str, str],
    vanilla_mapping_texts: dict[str, str],
) -> ProvinceDataset:
    effective = runtime.parse_blocks(
        effective_layer_texts(mod_texts, vanilla_texts), NUMERIC_HEADER_RE
    )
    mapping, mapping_locations = parse_province_mapping(
        effective_layer_texts(mod_mapping_texts, vanilla_mapping_texts)
    )
    return ProvinceDataset(
        label, parse_province_events(effective), mapping, mapping_locations
    )


def effective_layer_texts(
    mod_texts: dict[str, str],
    vanilla_texts: dict[str, str],
) -> dict[str, str]:
    mod_relatives = {
        key.split(":", 1)[1].lower()
        for key in mod_texts
    }
    effective = {
        key: text
        for key, text in vanilla_texts.items()
        if key.split(":", 1)[1].lower() not in mod_relatives
    }
    effective.update(mod_texts)
    return effective


def parse_province_mapping(
    texts: dict[str, str],
) -> tuple[dict[int, int], dict[int, tuple[str, int]]]:
    mapping: dict[int, int] = {}
    locations: dict[int, tuple[str, int]] = {}
    for path, text in sorted(texts.items()):
        for line_number, raw in enumerate(text.splitlines(), start=1):
            match = MAPPING_RE.fullmatch(runtime.strip_comment(raw).strip())
            if not match:
                continue
            target_id, source_id = (int(value) for value in match.groups())
            mapping[target_id] = source_id
            locations[target_id] = (path, line_number)
    return mapping, locations


def read_tracking(path: Path, kind: str) -> dict[int, SourceRef]:
    rows: dict[int, SourceRef] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            target = (row.get("final_new_id") or "").strip()
            source = (row.get("old_id") or "").strip()
            if not target.isdigit() or not source.isdigit():
                continue
            rows[int(target)] = SourceRef(
                kind,
                int(source),
                (row.get("candidate_type") or row.get("primary_status") or "").strip(),
            )
    return rows


def read_source_refs(repo_root: Path) -> dict[int, list[SourceRef]]:
    generated = repo_root / "development/analysis/generated/province_definition"
    result: dict[int, list[SourceRef]] = defaultdict(list)
    inputs = (
        (generated / "final_modlu_tracking_preserve_old_ids.csv", "asil_mod"),
        (generated / "final_orijinal_tracking_preserve_old_ids.csv", "vanilla"),
    )
    for path, kind in inputs:
        for target, source_ref in read_tracking(path, kind).items():
            result[target].append(source_ref)
    return dict(result)


def county_capitals(
    blocks: dict[str, landed.TitleBlock],
) -> list[dict[str, str | int]]:
    children: dict[str, list[landed.TitleBlock]] = defaultdict(list)
    for block in blocks.values():
        if block.title_id.startswith("b_") and block.direct_province_ids:
            children[block.parent_id].append(block)
    rows: list[dict[str, str | int]] = []
    for county in sorted(
        (block for block in blocks.values() if block.title_id.startswith("c_")),
        key=lambda item: (item.source_file.lower(), item.start_line),
    ):
        candidates = sorted(
            children.get(county.title_id, []),
            key=lambda item: (item.source_file.lower(), item.start_line),
        )
        explicit = county.direct_capital if county.direct_capital.startswith("b_") else ""
        capital = blocks.get(explicit) if explicit else (candidates[0] if candidates else None)
        if capital is None or not capital.direct_province_ids:
            continue
        rows.append(
            {
                "county_id": county.title_id,
                "capital_barony": capital.title_id,
                "province_id": capital.direct_province_ids[0],
                "capital_source": "explicit" if explicit else "first_barony",
                "landed_path": capital.source_file,
                "landed_line": capital.start_line,
            }
        )
    return rows


def landed_provinces(blocks: dict[str, landed.TitleBlock]) -> dict[int, str]:
    result: dict[int, str] = {}
    for block in blocks.values():
        if not block.title_id.startswith("b_") or not block.direct_province_ids:
            continue
        result.setdefault(block.direct_province_ids[0], block.title_id)
    return result


def top_level_ids(texts: dict[str, str]) -> set[str]:
    return set(runtime.parse_blocks(texts, GENERIC_HEADER_RE))


def faith_ids(texts: dict[str, str]) -> set[str]:
    result: set[str] = set()
    for text in texts.values():
        depth = 0
        faith_depth: int | None = None
        for raw in text.splitlines():
            clean = runtime.strip_comment(raw)
            if faith_depth is None and FAITHS_RE.match(clean):
                faith_depth = depth + runtime.brace_delta(clean)
            elif faith_depth is not None and depth == faith_depth:
                match = GENERIC_HEADER_RE.match(clean)
                if match:
                    result.add(match.group(1))
            depth += runtime.brace_delta(clean)
            if faith_depth is not None and depth < faith_depth:
                faith_depth = None
    return result


def effective_common_texts(
    mod_root: Path,
    vanilla_root: Path,
    relative_dir: str,
) -> dict[str, str]:
    vanilla = runtime.read_layer_texts(vanilla_root, relative_dir, "vanilla")
    mod = runtime.read_layer_texts(mod_root, relative_dir, "current")
    return effective_layer_texts(mod, vanilla)


def source_state(
    refs: list[SourceRef],
    date: runtime.Date,
    asil_mod: ProvinceDataset,
    vanilla: ProvinceDataset,
) -> tuple[ProvinceState | None, str, str, str]:
    candidates: list[tuple[SourceRef, ProvinceState]] = []
    for ref in refs:
        dataset = asil_mod if ref.kind == "asil_mod" else vanilla
        candidates.append((ref, dataset.state_at(ref.source_province_id, date)))
    if not candidates:
        return None, "untracked", "", ""
    signatures = {state.signature() for _, state in candidates}
    source_ids = " | ".join(
        f"{ref.kind}:{ref.source_province_id}" for ref, _ in candidates
    )
    if len(signatures) > 1:
        return None, "ambiguous", source_ids, " | ".join(sorted(signatures))
    kinds = {ref.kind for ref, _ in candidates}
    kind = next(iter(kinds)) if len(kinds) == 1 else "shared_source"
    return candidates[0][1], kind, source_ids, candidates[0][1].signature()


def classify_provenance(
    current: ProvinceState,
    premerge: ProvinceState,
    source: ProvinceState | None,
    source_kind: str,
) -> str:
    current_sig = current.signature()
    premerge_sig = premerge.signature()
    if source is None:
        return "preexisting_yusseter" if current_sig == premerge_sig else "yusseter_current_only"
    source_sig = source.signature()
    if current_sig == source_sig:
        if premerge_sig == current_sig:
            return (
                "shared_vanilla_baseline"
                if source_kind == "vanilla"
                else "shared_asil_mod_baseline"
            )
        return "core_map_integration" if source_kind == "vanilla" else "upstream_integration"
    if current_sig == premerge_sig:
        return "preexisting_yusseter"
    return "yusseter_current_only"


def state_location(state: ProvinceState, field: str) -> tuple[str, str]:
    return str(getattr(state, f"{field}_path")), str(getattr(state, f"{field}_line"))


def finding(
    issue: str,
    severity: str,
    confidence: str,
    county_id: str,
    barony_id: str,
    province_id: int,
    date: runtime.Date,
    state: ProvinceState,
    field: str,
    reason: str,
    recommendation: str,
    provenance: str,
    source_kind: str,
    source_ids: str,
    source_signature: str,
) -> dict[str, str]:
    path, line = state_location(state, field)
    mapped_from = str(getattr(state, f"{field}_mapped_from", 0) or "")
    mapping_path = str(getattr(state, f"{field}_mapping_path", ""))
    mapping_line = str(getattr(state, f"{field}_mapping_line", 0) or "")
    return {
        "domain": "province_history",
        "category": "bookmark_semantics",
        "issue": issue,
        "severity": severity,
        "confidence": confidence,
        "county_id": county_id,
        "barony_id": barony_id,
        "province_id": str(province_id),
        "bookmark_date": str(date),
        "field": field,
        "current_value": str(getattr(state, field)),
        "current_signature": state.signature(),
        "path": path,
        "line": line,
        "mapped_from_province": mapped_from,
        "mapping_path": mapping_path,
        "mapping_line": mapping_line,
        "reason": reason,
        "recommendation": recommendation,
        "provenance": provenance,
        "source_kind": source_kind,
        "source_ids": source_ids,
        "source_signature": source_signature,
    }


def compact_findings(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    keys = (
        "issue", "county_id", "barony_id", "province_id", "field",
        "current_value", "current_signature", "provenance", "source_signature",
    )
    for row in rows:
        grouped[tuple(row.get(key, "") for key in keys)].append(row)
    compact: list[dict[str, str]] = []
    for group in grouped.values():
        first = dict(group[0])
        first["bookmark_date"] = " | ".join(
            sorted(
                {row["bookmark_date"] for row in group},
                key=lambda value: runtime.parse_date(value) or runtime.Date(0),
            )
        )
        first["occurrence_count"] = str(len(group))
        compact.append(first)
    compact.sort(
        key=lambda row: (
            row["severity"], row["issue"], int(row["province_id"]), row["bookmark_date"]
        )
    )
    return compact


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    mod_root = repo_root / "BookmarksGit"
    asil_mod_root = args.asil_mod_repo.resolve() / "BookmarksGit"
    vanilla_root = args.vanilla_game_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    current_history = runtime.read_layer_texts(
        mod_root, "history/provinces", "current"
    )
    premerge_history = runtime.read_git_texts(
        repo_root, args.baseline_revision, "history/provinces", "premerge"
    )
    asil_mod_history = runtime.read_layer_texts(
        asil_mod_root, "history/provinces", "asil_mod"
    )
    vanilla_history = runtime.read_layer_texts(
        vanilla_root, "history/provinces", "vanilla"
    )
    current_mapping = runtime.read_layer_texts(
        mod_root, "history/province_mapping", "current"
    )
    premerge_mapping = runtime.read_git_texts(
        repo_root, args.baseline_revision, "history/province_mapping", "premerge"
    )
    asil_mod_mapping = runtime.read_layer_texts(
        asil_mod_root, "history/province_mapping", "asil_mod"
    )
    vanilla_mapping = runtime.read_layer_texts(
        vanilla_root, "history/province_mapping", "vanilla"
    )
    current = build_dataset(
        "current", current_history, vanilla_history,
        current_mapping, vanilla_mapping,
    )
    premerge = build_dataset(
        "premerge", premerge_history, vanilla_history,
        premerge_mapping, vanilla_mapping,
    )
    asil_mod = build_dataset(
        "asil_mod", asil_mod_history, vanilla_history,
        asil_mod_mapping, vanilla_mapping,
    )
    vanilla = build_dataset(
        "vanilla", {}, vanilla_history, {}, vanilla_mapping
    )

    bookmark_texts = runtime.read_layer_texts(
        mod_root, "common/bookmarks", "current"
    )
    bookmark_rows, _ = runtime.parse_bookmarks(bookmark_texts)
    dates = sorted({runtime.parse_date(row["start_date"]) for row in bookmark_rows})
    dates = [date for date in dates if date is not None]

    landed_blocks = landed.parse_landed_titles_path(mod_root / "common/landed_titles")
    capitals = county_capitals(landed_blocks)
    all_landed = landed_provinces(landed_blocks)
    capital_by_province = {int(row["province_id"]): row for row in capitals}
    source_refs = read_source_refs(repo_root)

    culture_texts = effective_common_texts(
        mod_root, vanilla_root, "common/culture/cultures"
    )
    religion_texts = effective_common_texts(
        mod_root, vanilla_root, "common/religion/religion_types"
    )
    holding_texts = effective_common_texts(
        mod_root, vanilla_root, "common/holdings"
    )
    cultures = top_level_ids(culture_texts)
    religions = faith_ids(religion_texts)
    holdings = top_level_ids(holding_texts) | {"none", "auto"}

    findings: list[dict[str, str]] = []
    state_rows: list[dict[str, str]] = []
    source_mapping_rows: list[dict[str, str]] = []
    mapping_seen: set[int] = set()

    for province_id, barony_id in sorted(all_landed.items()):
        capital = capital_by_province.get(province_id)
        county_id = str(capital["county_id"]) if capital else ""
        refs = source_refs.get(province_id, [])
        if province_id not in mapping_seen:
            mapping_seen.add(province_id)
            source_mapping_rows.append(
                {
                    "province_id": str(province_id),
                    "barony_id": barony_id,
                    "county_id": county_id,
                    "is_county_capital": "yes" if capital else "no",
                    "source_refs": " | ".join(
                        f"{ref.kind}:{ref.source_province_id}" for ref in refs
                    ),
                    "source_ref_count": str(len(refs)),
                    "mapping_status": (
                        "untracked" if not refs
                        else ("single" if len(refs) == 1 else "shared_candidate")
                    ),
                }
            )

        for date in dates:
            state = current.state_at(province_id, date)
            pre_state = premerge.state_at(province_id, date)
            source, source_kind, source_ids, source_signature = source_state(
                refs, date, asil_mod, vanilla
            )
            provenance = classify_provenance(
                state, pre_state, source, source_kind
            )

            for field, valid_values, issue in (
                ("culture", cultures, "undefined_culture"),
                ("religion", religions, "undefined_religion"),
                ("holding", holdings, "undefined_holding"),
            ):
                value = str(getattr(state, field))
                if value and value not in valid_values:
                    findings.append(
                        finding(
                            issue, "blocker", "high", county_id, barony_id,
                            province_id, date, state, field,
                            f"effective {field} is absent from current definitions",
                            f"restore_or_remap_{field}", provenance,
                            source_kind, source_ids, source_signature,
                        )
                    )

            if not capital:
                continue

            if not state.culture:
                findings.append(
                    finding(
                        "capital_missing_culture", "blocker", "high", county_id,
                        barony_id, province_id, date, state, "culture",
                        "county capital has no effective culture at bookmark start",
                        "restore_capital_culture_history", provenance,
                        source_kind, source_ids, source_signature,
                    )
                )
            if not state.religion:
                findings.append(
                    finding(
                        "capital_missing_religion", "blocker", "high", county_id,
                        barony_id, province_id, date, state, "religion",
                        "county capital has no effective religion at bookmark start",
                        "restore_capital_religion_history", provenance,
                        source_kind, source_ids, source_signature,
                    )
                )
            if state.holding == "none":
                findings.append(
                    finding(
                        "capital_holding_none", "review", "high", county_id,
                        barony_id, province_id, date, state, "holding",
                        "county capital explicitly prevents holding generation at bookmark start",
                        "verify_unoccupied_county_intent_in_game", provenance,
                        source_kind, source_ids, source_signature,
                    )
                )
            if source_kind == "ambiguous":
                findings.append(
                    finding(
                        "ambiguous_authoritative_source_state", "review", "medium",
                        county_id, barony_id, province_id, date, state, "culture",
                        "modlu and vanilla tracking candidates have different history states",
                        "resolve_shared_tracking_source_intent", provenance,
                        source_kind, source_ids, source_signature,
                    )
                )
            elif (
                source is not None
                and state.signature() != source.signature()
                and provenance == "yusseter_current_only"
            ):
                findings.append(
                    finding(
                        "capital_current_only_source_divergence", "review", "medium",
                        county_id, barony_id, province_id, date, state, "culture",
                        "county-capital state differs from both premerge and authoritative source",
                        "review_current_only_capital_history_change", provenance,
                        source_kind, source_ids, source_signature,
                    )
                )

            source_match = (
                "untracked" if not refs
                else ("ambiguous" if source is None else (
                    "same" if state.signature() == source.signature() else "different"
                ))
            )
            state_rows.append(
                {
                    "county_id": county_id,
                    "capital_barony": barony_id,
                    "province_id": str(province_id),
                    "bookmark_date": str(date),
                    "culture": state.culture,
                    "religion": state.religion,
                    "holding": state.holding,
                    "culture_mapped_from": str(state.culture_mapped_from or ""),
                    "religion_mapped_from": str(state.religion_mapped_from or ""),
                    "culture_mapping_path": state.culture_mapping_path,
                    "religion_mapping_path": state.religion_mapping_path,
                    "current_signature": state.signature(),
                    "premerge_signature": pre_state.signature(),
                    "source_kind": source_kind,
                    "source_ids": source_ids,
                    "source_signature": source_signature,
                    "source_match": source_match,
                    "provenance": provenance,
                }
            )

    compact = compact_findings(findings)
    write_csv(output_dir / "county_capital_source_mapping.csv", source_mapping_rows)
    write_csv(output_dir / "county_capital_state_by_bookmark.csv", state_rows)
    write_csv(output_dir / "province_history_semantic_findings.csv", findings)
    write_csv(output_dir / "province_history_semantic_findings_compact.csv", compact)

    issue_counts = Counter(row["issue"] for row in findings)
    severity_counts = Counter(row["severity"] for row in compact)
    provenance_counts = Counter(row["provenance"] for row in compact)
    source_match_counts = Counter(row["source_match"] for row in state_rows)
    summary = [
        "# Province History Bookmark Semantics Audit", "",
        f"- Yusseter HEAD: `{subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo_root, check=True, stdout=subprocess.PIPE, text=True).stdout.strip()}`",
        f"- unique bookmark dates: `{len(dates)}`",
        f"- landed barony provinces checked: `{len(all_landed)}`",
        f"- county capitals checked: `{len(capitals)}`",
        f"- county-capital date states: `{len(state_rows)}`",
        f"- effective current province mappings: `{len(current.mapping)}`",
        f"- detailed findings: `{len(findings)}`",
        f"- compact findings: `{len(compact)}`",
        f"- compact blockers: `{severity_counts['blocker']}`",
        f"- compact reviews: `{severity_counts['review']}`",
        "", "## Detailed Finding Counts", "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(issue_counts.items())],
        "", "## Compact Provenance", "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(provenance_counts.items())],
        "", "## Capital Source Match", "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(source_match_counts.items())],
        "", "## Rules", "",
        "- Valid culture/religion assignments on non-capital baronies are allowed and never treated as findings.",
        "- `history/province_mapping` supplies mapped culture/religion recursively; target-explicit values take precedence and holding is never copied.",
        "- Missing holding uses CK3 auto-generation and is not an error; explicit `holding = none` on a county capital is review-only.",
        "- `modlu_kalan` tracking uses the asıl-mod old province; `orijinal_dogu` tracking uses the vanilla old province.",
        "- This is a static bookmark-date audit; runtime map initialization still needs smoke testing.",
        "- No live BookmarksGit source file is modified by this audit.", "",
    ]
    (output_dir / "province_history_bookmark_semantics_summary.md").write_text(
        "\n".join(summary), encoding="utf-8"
    )
    print(f"output: {output_dir}")
    print(f"dates: {len(dates)}; landed: {len(all_landed)}; capitals: {len(capitals)}")
    print(f"findings: {len(findings)}; compact: {len(compact)}")
    print(f"compact severity: {dict(severity_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
