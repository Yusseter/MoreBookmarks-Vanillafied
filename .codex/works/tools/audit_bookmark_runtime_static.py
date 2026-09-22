from __future__ import annotations

import argparse
import csv
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import audit_landed_title_source_identity as landed


DEFAULT_ASIL_MOD_REPO = (
    Path(__file__).resolve().parents[3].parent / "Leviathonlx MoreBookmarks-Plus"
)
DEFAULT_VANILLA_GAME_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
)
DEFAULT_BASELINE = "09588cbb5212a31bc4a373b6990b2c4da1203a35"
DEFAULT_MERGED_SOURCE = "74a26a897"
OUTPUT_PATH = (
    ".codex/works/analysis/generated/repo_integration_closure/"
    "bookmark_runtime_static"
)

TITLE_HEADER_RE = re.compile(r"^\s*([hekdcb]_[A-Za-z0-9_'\-]+)\s*=\s*\{")
TITLE_ID_RE = re.compile(r"^[hekdcb]_[A-Za-z0-9_'\-]+$")
GENERIC_HEADER_RE = re.compile(r"^\s*([A-Za-z0-9_.:\-]+)\s*=\s*\{")
ENTRY_RE = re.compile(r"^\s*([A-Za-z0-9_.@?:'\"\-]+)\s*=")
DATE_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?$")
STATE_ASSIGNMENT_RE = re.compile(
    r"\b(holder|liege|government)\s*=\s*\"?([A-Za-z0-9_.:\-]+)\"?"
)
DIRECT_HOLDER_RE = re.compile(
    r"^\s*holder\s*=\s*\"?([A-Za-z0-9_.:\-]+)\"?\b"
)
BOOKMARK_FIELD_RE = re.compile(
    r"^\s*(history_id|title|government)\s*=\s*\"?([A-Za-z0-9_.:\-]+)\"?"
)

REPORTED_CASES = (
    "c_azas",
    "c_koh_ker",
    "c_SUM_riak_nan_berbedur",
    "c_suzhou_2",
)


@dataclass(frozen=True, order=True)
class Date:
    year: int
    month: int = 1
    day: int = 1

    def __str__(self) -> str:
        return f"{self.year}.{self.month}.{self.day}"


@dataclass(frozen=True)
class Block:
    key: str
    path: str
    start_line: int
    lines: tuple[str, ...]
    layer: str


@dataclass(frozen=True)
class DirectEntry:
    key: str
    relative_start: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Event:
    date: Date
    values: dict[str, str]
    path: str
    line: int


@dataclass(frozen=True)
class State:
    holder: str = ""
    liege: str = ""
    government: str = ""
    holder_path: str = ""
    holder_line: int = 0
    liege_path: str = ""
    liege_line: int = 0
    government_path: str = ""
    government_line: int = 0


@dataclass(frozen=True)
class CharacterLife:
    character_id: str
    birth: Date | None
    death: Date | None
    path: str
    line: int


@dataclass
class TitleDataset:
    label: str
    events: dict[str, list[Event]]
    blocks: dict[str, list[Block]]

    def state_at(self, title_id: str, date: Date) -> State:
        values = {
            "holder": "",
            "liege": "",
            "government": "",
            "holder_path": "",
            "holder_line": 0,
            "liege_path": "",
            "liege_line": 0,
            "government_path": "",
            "government_line": 0,
        }
        for event in self.events.get(title_id, []):
            if event.date > date:
                break
            for key, value in event.values.items():
                values[key] = "" if value == "0" else value.removeprefix("title:")
                values[f"{key}_path"] = event.path
                values[f"{key}_line"] = event.line
        return State(**values)

    def holder_ids(self) -> set[str]:
        return {
            value
            for events in self.events.values()
            for event in events
            for key, value in event.values.items()
            if key == "holder" and value != "0"
        }


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit static title/character state at every active bookmark date"
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument("--asil-mod-repo", type=Path, default=DEFAULT_ASIL_MOD_REPO)
    parser.add_argument(
        "--vanilla-game-root", type=Path, default=DEFAULT_VANILLA_GAME_ROOT
    )
    parser.add_argument("--baseline-revision", default=DEFAULT_BASELINE)
    parser.add_argument(
        "--merged-source-revision", default=DEFAULT_MERGED_SOURCE
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def strip_comment(line: str) -> str:
    quoted = False
    escaped = False
    result: list[str] = []
    for char in line:
        if char == "\\" and quoted:
            escaped = not escaped
            result.append(char)
            continue
        if char == '"' and not escaped:
            quoted = not quoted
        escaped = False
        if char == "#" and not quoted:
            break
        result.append(char)
    return "".join(result)


def brace_delta(line: str) -> int:
    clean = strip_comment(line)
    return clean.count("{") - clean.count("}")


def parse_date(value: str) -> Date | None:
    match = DATE_RE.fullmatch(value.strip())
    if not match:
        return None
    return Date(
        int(match.group(1)),
        int(match.group(2) or 1),
        int(match.group(3) or 1),
    )


def read_layer_texts(root: Path, relative_dir: str, layer: str) -> dict[str, str]:
    directory = root / relative_dir
    if not directory.is_dir():
        return {}
    return {
        f"{layer}:{path.relative_to(root).as_posix()}": path.read_text(
            encoding="utf-8-sig", errors="replace"
        )
        for path in sorted(directory.rglob("*.txt"))
    }


def read_git_texts(
    repo_root: Path, revision: str, relative_dir: str, layer: str
) -> dict[str, str]:
    prefix = f"BookmarksGit/{relative_dir}"
    listed = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", revision, "--", prefix],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.splitlines()
    texts: dict[str, str] = {}
    for path in listed:
        if not path.lower().endswith(".txt"):
            continue
        raw = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
        texts[f"{layer}:{path.removeprefix('BookmarksGit/')}"] = raw.decode(
            "utf-8-sig", errors="replace"
        )
    return texts


def effective_vanilla_texts(
    mod_texts: dict[str, str], vanilla_texts: dict[str, str]
) -> dict[str, str]:
    overridden = {
        path.split(":", 1)[-1].lower()
        for path in mod_texts
    }
    return {
        path: text
        for path, text in vanilla_texts.items()
        if path.split(":", 1)[-1].lower() not in overridden
    }


def parse_blocks(
    texts: dict[str, str],
    header_re: re.Pattern[str],
    wanted: set[str] | None = None,
) -> dict[str, list[Block]]:
    result: dict[str, list[Block]] = defaultdict(list)
    for path, text in sorted(texts.items()):
        lines = text.splitlines()
        depth = 0
        index = 0
        while index < len(lines):
            clean = strip_comment(lines[index])
            match = header_re.match(clean) if depth == 0 else None
            if not match:
                depth += brace_delta(lines[index])
                index += 1
                continue
            key = match.group(1)
            start = index
            local_depth = brace_delta(lines[index])
            while local_depth > 0 and index + 1 < len(lines):
                index += 1
                local_depth += brace_delta(lines[index])
            if local_depth != 0:
                raise RuntimeError(f"unterminated block {key} at {path}:{start + 1}")
            if wanted is None or key in wanted:
                result[key].append(
                    Block(
                        key=key,
                        path=path,
                        start_line=start + 1,
                        lines=tuple(lines[start : index + 1]),
                        layer=path.split(":", 1)[0],
                    )
                )
            index += 1
    return dict(result)


def direct_entries(block: Block) -> list[DirectEntry]:
    lines = block.lines
    entries: list[DirectEntry] = []
    depth = 1
    index = 1
    closing_index = len(lines) - 1
    while index < closing_index:
        clean = strip_comment(lines[index])
        match = ENTRY_RE.match(clean) if depth == 1 else None
        if not match:
            depth += brace_delta(lines[index])
            index += 1
            continue
        start = index
        local_depth = depth + brace_delta(lines[index])
        while local_depth > 1 and index + 1 < closing_index:
            index += 1
            local_depth += brace_delta(lines[index])
        if local_depth != 1:
            raise RuntimeError(
                f"unterminated direct entry {match.group(1)} at "
                f"{block.path}:{block.start_line + start}"
            )
        entries.append(
            DirectEntry(match.group(1), start, tuple(lines[start : index + 1]))
        )
        depth = local_depth
        index += 1
    return entries


def direct_body(lines: tuple[str, ...]) -> str:
    text = "\n".join(strip_comment(line) for line in lines)
    opening = text.find("{")
    if opening < 0:
        return text
    depth = 1
    output: list[str] = []
    for char in text[opening + 1 :]:
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                break
            continue
        if depth == 1:
            output.append(char)
    return "".join(output)


def parse_title_events(blocks: dict[str, list[Block]]) -> dict[str, list[Event]]:
    events: dict[str, list[Event]] = defaultdict(list)
    beginning = Date(-100000, 1, 1)
    for title_id, title_blocks in blocks.items():
        for block in title_blocks:
            for entry in direct_entries(block):
                date = parse_date(entry.key)
                if date is None and entry.key not in {"holder", "liege", "government"}:
                    continue
                body = direct_body(entry.lines)
                values = {
                    key: value
                    for key, value in STATE_ASSIGNMENT_RE.findall(body)
                }
                if date is None:
                    line = strip_comment(entry.lines[0])
                    match = re.search(
                        rf"\b{re.escape(entry.key)}\s*=\s*\"?([A-Za-z0-9_.:\-]+)",
                        line,
                    )
                    if match:
                        values[entry.key] = match.group(1)
                    date = beginning
                if values:
                    events[title_id].append(
                        Event(
                            date,
                            values,
                            block.path,
                            block.start_line + entry.relative_start,
                        )
                    )
        events[title_id].sort(key=lambda item: (item.date, item.path, item.line))
    return dict(events)


def build_title_dataset(
    label: str, mod_texts: dict[str, str], vanilla_texts: dict[str, str]
) -> TitleDataset:
    mod_blocks = parse_blocks(mod_texts, TITLE_HEADER_RE)
    vanilla_blocks = parse_blocks(
        effective_vanilla_texts(mod_texts, vanilla_texts), TITLE_HEADER_RE
    )
    effective = {
        title_id: mod_blocks.get(title_id, vanilla_blocks.get(title_id, []))
        for title_id in set(mod_blocks) | set(vanilla_blocks)
    }
    return TitleDataset(label, parse_title_events(effective), effective)


def extract_character_life(blocks: list[Block], character_id: str) -> CharacterLife:
    births: list[Date] = []
    deaths: list[Date] = []
    for block in blocks:
        for entry in direct_entries(block):
            date = parse_date(entry.key)
            if date is not None:
                body = direct_body(entry.lines)
                if re.search(r"\bbirth\s*=", body):
                    births.append(date)
                if re.search(r"\bdeath\s*=", body):
                    deaths.append(date)
                continue
            line = strip_comment(entry.lines[0])
            if entry.key in {"birth", "death"}:
                match = re.search(r"=\s*\"?([0-9.]+)", line)
                parsed = parse_date(match.group(1)) if match else None
                if parsed and entry.key == "birth":
                    births.append(parsed)
                if parsed and entry.key == "death":
                    deaths.append(parsed)
    first = blocks[0]
    return CharacterLife(
        character_id,
        min(births) if births else None,
        min(deaths) if deaths else None,
        first.path,
        first.start_line,
    )


def build_character_lives(
    wanted: set[str], mod_texts: dict[str, str], vanilla_texts: dict[str, str]
) -> dict[str, CharacterLife]:
    wanted = set(wanted)
    wanted.discard("0")
    mod_blocks = parse_blocks(mod_texts, GENERIC_HEADER_RE, wanted)
    missing = wanted - set(mod_blocks)
    vanilla_blocks = parse_blocks(
        effective_vanilla_texts(mod_texts, vanilla_texts),
        GENERIC_HEADER_RE,
        missing,
    )
    effective = {
        character_id: mod_blocks.get(character_id, vanilla_blocks.get(character_id, []))
        for character_id in wanted
        if character_id in mod_blocks or character_id in vanilla_blocks
    }
    return {
        character_id: extract_character_life(blocks, character_id)
        for character_id, blocks in effective.items()
    }


def character_status(
    character_id: str, date: Date, lives: dict[str, CharacterLife]
) -> str:
    if not character_id:
        return "empty"
    life = lives.get(character_id)
    if life is None:
        return "undefined"
    if life.birth and life.birth > date:
        return "born_after_bookmark"
    if life.death and life.death <= date:
        return "dead_before_bookmark"
    if life.birth is None or life.death is None:
        return "alive_life_boundary_partial"
    return "alive"


def parse_bookmarks(texts: dict[str, str]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    blocks = parse_blocks(texts, GENERIC_HEADER_RE)
    dates: list[dict[str, str]] = []
    characters: list[dict[str, str]] = []
    for bookmark_id, candidates in sorted(blocks.items()):
        block = candidates[-1]
        start_date = None
        for line in block.lines[1:-1]:
            match = re.match(r"^\s*start_date\s*=\s*([0-9.]+)", strip_comment(line))
            if match:
                start_date = parse_date(match.group(1))
                break
        if start_date is None:
            continue
        dates.append(
            {
                "bookmark_id": bookmark_id,
                "start_date": str(start_date),
                "path": block.path,
                "line": str(block.start_line),
            }
        )
        depth = 1
        frames: list[dict[str, object]] = []
        for offset, raw in enumerate(block.lines[1:-1], start=1):
            clean = strip_comment(raw)
            if re.match(r"^\s*character\s*=\s*\{", clean):
                frames.append(
                    {
                        "depth": depth + brace_delta(clean),
                        "line": block.start_line + offset,
                        "fields": {},
                    }
                )
            for frame in frames:
                if depth != int(frame["depth"]):
                    continue
                field_match = BOOKMARK_FIELD_RE.match(clean)
                if field_match:
                    fields = frame["fields"]
                    assert isinstance(fields, dict)
                    fields[field_match.group(1)] = field_match.group(2)
            depth += brace_delta(clean)
            closing = [frame for frame in frames if depth < int(frame["depth"])]
            for frame in closing:
                fields = frame["fields"]
                assert isinstance(fields, dict)
                if fields.get("history_id"):
                    characters.append(
                        {
                            "bookmark_id": bookmark_id,
                            "start_date": str(start_date),
                            "history_id": str(fields.get("history_id", "")),
                            "title": str(fields.get("title", "")),
                            "declared_government": str(fields.get("government", "")),
                            "path": block.path,
                            "line": str(frame["line"]),
                        }
                    )
                frames.remove(frame)
    return dates, characters


def read_title_mapping(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle, skipinitialspace=True):
            current_tokens = [
                token.replace("(second)", "").strip()
                for token in re.split(
                    r"[&;]", (raw.get("source_title_id") or "")
                )
            ]
            source_tokens = [
                token.replace("(second)", "").strip()
                for token in re.split(r"[&;]", (raw.get("mod_title_id") or ""))
            ]
            current_tokens = [
                token for token in current_tokens if TITLE_ID_RE.fullmatch(token)
            ]
            source_tokens = [
                token for token in source_tokens if TITLE_ID_RE.fullmatch(token)
            ]
            if len(current_tokens) == len(source_tokens):
                pairs = zip(current_tokens, source_tokens, strict=True)
            elif len(source_tokens) == 1:
                pairs = ((current, source_tokens[0]) for current in current_tokens)
            else:
                continue
            for current, source in pairs:
                mapping[current] = source
    return mapping


def normalize_current_history_path(path: str) -> str:
    relative = path.split(":", 1)[-1].lstrip("/")
    return f"BookmarksGit/{relative}"


def holder_assignments(dataset: TitleDataset) -> list[dict[str, object]]:
    beginning = Date(-100000, 1, 1)
    rows: list[dict[str, object]] = []
    for title_id, blocks in dataset.blocks.items():
        for block in blocks:
            for entry in direct_entries(block):
                date = parse_date(entry.key)
                if date is None and entry.key != "holder":
                    continue
                effective_date = date or beginning
                for offset, raw in enumerate(entry.lines):
                    match = DIRECT_HOLDER_RE.match(strip_comment(raw))
                    if not match or match.group(1) == "0":
                        continue
                    rows.append({
                        "title_id": title_id,
                        "date": effective_date,
                        "holder": match.group(1),
                        "path": block.path,
                        "line": block.start_line + entry.relative_start + offset,
                    })
    return rows


def holder_assignment_index(
    dataset: TitleDataset,
) -> dict[tuple[str, Date], list[str]]:
    result: dict[tuple[str, Date], list[str]] = defaultdict(list)
    for row in holder_assignments(dataset):
        key = (str(row["title_id"]), row["date"])
        holder = str(row["holder"])
        if holder not in result[key]:
            result[key].append(holder)
    return dict(result)


def classify_undefined_holder_provenance(
    holder: str,
    premerge_same_assignment: bool,
    source_same_assignment: bool,
    premerge_defined: bool,
    source_defined: bool,
) -> tuple[str, str, str]:
    if source_same_assignment:
        if source_defined:
            return (
                "upstream_integration_character_not_merged",
                "upstream_integration",
                "restore_merged_source_character_or_reconcile_character_file_override",
            )
        if premerge_defined:
            return (
                "upstream_integration_source_character_removed",
                "upstream_integration",
                "restore_premerge_character_or_replace_all_references_after_identity_review",
            )
        if premerge_same_assignment:
            return (
                "shared_asil_mod_baseline_undefined_holder",
                "shared_asil_mod_baseline",
                "repair_shared_source_holder_reference",
            )
        return (
            "upstream_integration_source_undefined_holder",
            "upstream_integration",
            "repair_imported_source_holder_reference",
        )
    if premerge_same_assignment:
        if premerge_defined:
            return (
                "upstream_integration_local_character_removed",
                "upstream_integration",
                "restore_premerge_character_or_replace_preserved_local_reference",
            )
        return (
            "preexisting_yusseter_undefined_holder",
            "preexisting_yusseter",
            "repair_preexisting_holder_reference",
        )
    if source_defined:
        return (
            "integration_character_definition_shadowed",
            "upstream_integration",
            "restore_source_character_or_reconcile_character_file_override",
        )
    if premerge_defined:
        return (
            "yusseter_current_reference_to_removed_character",
            "yusseter_current_only",
            "review_current_reference_and_premerge_character_identity",
        )
    return (
        "yusseter_current_only_undefined_holder",
        "yusseter_current_only",
        "define_character_or_replace_current_holder_reference",
    )


def build_title_holder_reference_provenance(
    current: TitleDataset,
    premerge: TitleDataset,
    merged_source: TitleDataset,
    current_lives: dict[str, CharacterLife],
    premerge_lives: dict[str, CharacterLife],
    source_lives: dict[str, CharacterLife],
    current_to_source_title: dict[str, str],
) -> list[dict[str, str]]:
    premerge_index = holder_assignment_index(premerge)
    source_index = holder_assignment_index(merged_source)
    rows: list[dict[str, str]] = []
    for assignment in holder_assignments(current):
        holder = str(assignment["holder"])
        if holder in current_lives:
            continue
        title_id = str(assignment["title_id"])
        date = assignment["date"]
        assert isinstance(date, Date)
        source_title_id = current_to_source_title.get(title_id, title_id)
        premerge_holders = premerge_index.get((title_id, date), [])
        source_holders = source_index.get((source_title_id, date), [])
        premerge_same = holder in premerge_holders
        source_same = holder in source_holders
        premerge_defined = holder in premerge_lives
        source_defined = holder in source_lives
        classification, provenance, recommendation = (
            classify_undefined_holder_provenance(
                holder,
                premerge_same,
                source_same,
                premerge_defined,
                source_defined,
            )
        )
        premerge_candidates = [
            value for value in premerge_holders
            if value != holder and value in premerge_lives
        ]
        source_candidates = [
            value for value in source_holders
            if value != holder and value in source_lives
        ]
        rows.append({
            "title_id": title_id,
            "source_title_id": source_title_id,
            "assignment_date": "direct" if date.year == -100000 else str(date),
            "path": normalize_current_history_path(str(assignment["path"])),
            "line": str(assignment["line"]),
            "holder": holder,
            "classification": classification,
            "provenance": provenance,
            "current_character_defined": "no",
            "premerge_character_defined": "yes" if premerge_defined else "no",
            "merged_source_character_defined": "yes" if source_defined else "no",
            "premerge_same_assignment": "yes" if premerge_same else "no",
            "merged_source_same_assignment": "yes" if source_same else "no",
            "premerge_same_date_holders": " | ".join(premerge_holders),
            "merged_source_same_date_holders": " | ".join(source_holders),
            "candidate_defined_premerge_holders": " | ".join(premerge_candidates),
            "candidate_defined_source_holders": " | ".join(source_candidates),
            "reason": (
                f"current holder is undefined; premerge character="
                f"{'defined' if premerge_defined else 'undefined'}; merged source "
                f"character={'defined' if source_defined else 'undefined'}; "
                f"same assignment premerge={'yes' if premerge_same else 'no'}; "
                f"same assignment source={'yes' if source_same else 'no'}"
            ),
            "recommendation": recommendation,
        })
    rows.sort(key=lambda row: (row["path"], int(row["line"]), row["holder"]))
    return rows


def has_bookmark_history_id(texts: dict[str, str], history_id: str) -> bool:
    pattern = re.compile(
        rf"^\s*history_id\s*=\s*\"?{re.escape(history_id)}\"?\s*$",
        re.MULTILINE,
    )
    return any(pattern.search(text) for text in texts.values())


def compact_findings(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    keys = ("domain", "category", "issue", "title_id", "holder", "provenance")
    for row in rows:
        grouped[tuple(row.get(key, "") for key in keys)].append(row)
    compact: list[dict[str, str]] = []
    for group in grouped.values():
        first = dict(group[0])
        first["bookmark_date"] = " | ".join(
            sorted({row["bookmark_date"] for row in group}, key=lambda value: parse_date(value) or Date(0))
        )
        first["occurrence_count"] = str(len(group))
        compact.append(first)
    compact.sort(
        key=lambda row: (
            row["severity"], row["issue"], row["title_id"], row["holder"]
        )
    )
    return compact


def read_government_ids(mod_root: Path, vanilla_root: Path) -> set[str]:
    texts = read_layer_texts(vanilla_root, "common/governments", "vanilla")
    texts.update(read_layer_texts(mod_root, "common/governments", "mod"))
    return set(parse_blocks(texts, GENERIC_HEADER_RE))


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


def signature(
    dataset: TitleDataset,
    title_id: str,
    date: Date,
    lives: dict[str, CharacterLife],
) -> str:
    if title_id not in dataset.events:
        return "absent"
    state = dataset.state_at(title_id, date)
    status = character_status(state.holder, date, lives)
    return "|".join((state.holder, status, state.liege, state.government))


def classify_provenance(
    current_sig: str, premerge_sig: str, source_sig: str
) -> str:
    if source_sig != "absent" and source_sig == current_sig:
        if premerge_sig == current_sig:
            return "shared_asil_mod_baseline"
        return "upstream_integration"
    if premerge_sig == current_sig:
        return "preexisting_yusseter"
    if premerge_sig == "absent":
        return "yusseter_current_addition"
    return "yusseter_current_only"


def state_row(
    title_id: str,
    date: Date,
    dataset: TitleDataset,
    lives: dict[str, CharacterLife],
    parent: str = "",
) -> dict[str, str]:
    state = dataset.state_at(title_id, date)
    life = lives.get(state.holder)
    return {
        "title_id": title_id,
        "bookmark_date": str(date),
        "de_jure_parent": parent,
        "holder": state.holder,
        "holder_status": character_status(state.holder, date, lives),
        "holder_birth": str(life.birth) if life and life.birth else "",
        "holder_death": str(life.death) if life and life.death else "",
        "liege": state.liege,
        "government": state.government,
        "holder_path": state.holder_path,
        "holder_line": str(state.holder_line or ""),
        "liege_path": state.liege_path,
        "liege_line": str(state.liege_line or ""),
        "government_path": state.government_path,
        "government_line": str(state.government_line or ""),
    }


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    current_mod = repo_root / "BookmarksGit"
    source_project = args.asil_mod_repo.resolve()
    source_mod = source_project / "BookmarksGit"
    vanilla_root = args.vanilla_game_root.resolve()
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    vanilla_title_texts = read_layer_texts(
        vanilla_root, "history/titles", "vanilla"
    )
    current_title_texts = read_layer_texts(
        current_mod, "history/titles", "current"
    )
    source_title_texts = read_layer_texts(
        source_mod, "history/titles", "asil_mod"
    )
    premerge_title_texts = read_git_texts(
        repo_root, args.baseline_revision, "history/titles", "premerge"
    )
    merged_source_title_texts = read_git_texts(
        repo_root,
        args.merged_source_revision,
        "history/titles",
        "merged_asil_mod",
    )

    current = build_title_dataset("current", current_title_texts, vanilla_title_texts)
    premerge = build_title_dataset("premerge", premerge_title_texts, vanilla_title_texts)
    source = build_title_dataset("asil_mod", source_title_texts, vanilla_title_texts)
    merged_source = build_title_dataset(
        "merged_asil_mod", merged_source_title_texts, vanilla_title_texts
    )

    bookmark_texts = read_layer_texts(
        current_mod, "common/bookmarks/bookmarks", "current"
    )
    source_bookmark_texts = read_layer_texts(
        source_mod, "common/bookmarks/bookmarks", "asil_mod"
    )
    premerge_bookmark_texts = read_git_texts(
        repo_root,
        args.baseline_revision,
        "common/bookmarks/bookmarks",
        "premerge",
    )
    bookmark_dates, bookmark_characters = parse_bookmarks(bookmark_texts)
    dates = sorted(
        {
            parsed
            for row in bookmark_dates
            if (parsed := parse_date(row["start_date"])) is not None
        }
    )

    vanilla_character_texts = read_layer_texts(
        vanilla_root, "history/characters", "vanilla"
    )
    current_character_texts = read_layer_texts(
        current_mod, "history/characters", "current"
    )
    source_character_texts = read_layer_texts(
        source_mod, "history/characters", "asil_mod"
    )
    premerge_character_texts = read_git_texts(
        repo_root, args.baseline_revision, "history/characters", "premerge"
    )
    merged_source_character_texts = read_git_texts(
        repo_root,
        args.merged_source_revision,
        "history/characters",
        "merged_asil_mod",
    )

    bookmark_history_ids = {row["history_id"] for row in bookmark_characters}
    all_reference_ids = (
        current.holder_ids()
        | premerge.holder_ids()
        | source.holder_ids()
        | merged_source.holder_ids()
        | bookmark_history_ids
    )
    current_lives = build_character_lives(
        all_reference_ids,
        current_character_texts,
        vanilla_character_texts,
    )
    premerge_lives = build_character_lives(
        all_reference_ids,
        premerge_character_texts,
        vanilla_character_texts,
    )
    source_lives = build_character_lives(
        all_reference_ids,
        source_character_texts,
        vanilla_character_texts,
    )
    merged_source_lives = build_character_lives(
        all_reference_ids,
        merged_source_character_texts,
        vanilla_character_texts,
    )

    landed_blocks = landed.parse_landed_titles_path(
        current_mod / "common/landed_titles/00_landed_titles.txt"
    )
    county_ids = sorted(title_id for title_id in landed_blocks if title_id.startswith("c_"))
    title_mapping = read_title_mapping(
        repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv"
    )
    holder_reference_rows = build_title_holder_reference_provenance(
        current,
        premerge,
        merged_source,
        current_lives,
        premerge_lives,
        merged_source_lives,
        title_mapping,
    )
    holder_reference_provenance = {
        (row["title_id"], row["holder"]): row["provenance"]
        for row in holder_reference_rows
    }
    government_ids = read_government_ids(current_mod, vanilla_root)

    state_rows: list[dict[str, str]] = []
    findings: list[dict[str, str]] = []
    independent_rows: list[dict[str, str]] = []

    for date in dates:
        held_higher: dict[str, list[str]] = defaultdict(list)
        for title_id in landed_blocks:
            if not title_id.startswith(("h_", "e_", "k_", "d_")):
                continue
            state = current.state_at(title_id, date)
            if state.holder:
                held_higher[state.holder].append(title_id)

        for title_id in county_ids:
            block = landed_blocks[title_id]
            row = state_row(title_id, date, current, current_lives, block.parent_id)
            state_rows.append(row)
            state = current.state_at(title_id, date)
            holder_status = row["holder_status"]
            issue = ""
            severity = ""
            confidence = ""
            reason = ""

            if state.holder and holder_status in {
                "undefined", "born_after_bookmark", "dead_before_bookmark"
            }:
                issue = f"effective_holder_{holder_status}"
                if holder_status == "dead_before_bookmark":
                    severity = "review"
                    confidence = "medium"
                    reason = (
                        "latest explicit holder died before the bookmark; runtime succession "
                        "may resolve the title and must be checked"
                    )
                else:
                    severity = "blocker"
                    confidence = "high"
                    reason = "effective bookmark holder is not a valid living history character"
            elif state.liege and state.liege not in landed_blocks:
                issue = "effective_liege_undefined"
                severity = "blocker"
                confidence = "high"
                reason = "effective de facto liege is absent from current landed titles"
            elif state.government and state.government not in government_ids:
                issue = "effective_government_undefined"
                severity = "blocker"
                confidence = "high"
                reason = "effective title government is absent from current government definitions"

            if issue:
                source_id = title_mapping.get(title_id, title_id)
                current_sig = signature(current, title_id, date, current_lives)
                premerge_sig = signature(premerge, title_id, date, premerge_lives)
                source_sig = signature(source, source_id, date, source_lives)
                provenance = classify_provenance(
                    current_sig, premerge_sig, source_sig
                )
                provenance_basis = "effective_state_signature"
                if issue == "effective_holder_undefined":
                    reference_provenance = holder_reference_provenance.get(
                        (title_id, state.holder)
                    )
                    if reference_provenance:
                        provenance = reference_provenance
                        provenance_basis = "title_holder_reference"
                findings.append(
                    {
                        "domain": "runtime",
                        "category": "bookmark_static_state",
                        "issue": issue,
                        "severity": severity,
                        "confidence": confidence,
                        "title_id": title_id,
                        "bookmark_date": str(date),
                        "holder": state.holder,
                        "holder_status": holder_status,
                        "liege": state.liege,
                        "government": state.government,
                        "path": state.holder_path or state.liege_path or state.government_path,
                        "line": str(state.holder_line or state.liege_line or state.government_line or ""),
                        "reason": reason,
                        "recommendation": "compare_history_chain_and_restore_valid_bookmark_state",
                        "source_title_id": source_id,
                        "current_signature": current_sig,
                        "premerge_signature": premerge_sig,
                        "asil_mod_signature": source_sig,
                        "provenance": provenance,
                        "provenance_basis": provenance_basis,
                    }
                )

            if (
                state.holder
                and holder_status.startswith("alive")
                and not state.liege
                and not held_higher.get(state.holder)
            ):
                source_id = title_mapping.get(title_id, title_id)
                pre_state = premerge.state_at(title_id, date)
                source_state = source.state_at(source_id, date)
                current_sig = signature(current, title_id, date, current_lives)
                premerge_sig = signature(premerge, title_id, date, premerge_lives)
                source_sig = signature(source, source_id, date, source_lives)
                premerge_liege_sig = (
                    pre_state.liege if title_id in premerge.events else "absent"
                )
                source_liege_sig = (
                    source_state.liege if source_id in source.events else "absent"
                )
                differs = bool(pre_state.liege or source_state.liege)
                independent_rows.append(
                    {
                        **row,
                        "higher_titles_same_holder": "",
                        "premerge_liege": pre_state.liege,
                        "asil_mod_title_id": source_id,
                        "asil_mod_liege": source_state.liege,
                        "classification": (
                            "reference_has_liege_review" if differs else "standalone_or_shared_review"
                        ),
                    }
                )
                if differs:
                    findings.append(
                        {
                            "domain": "runtime",
                            "category": "realm_hierarchy",
                            "issue": "independent_county_differs_from_reference",
                            "severity": "review",
                            "confidence": "medium",
                            "title_id": title_id,
                            "bookmark_date": str(date),
                            "holder": state.holder,
                            "holder_status": holder_status,
                            "liege": "",
                            "government": state.government,
                            "path": state.holder_path,
                            "line": str(state.holder_line or ""),
                            "reason": "county is isolated while premerge or asıl-mod counterpart has a liege",
                            "recommendation": "manual_realm_hierarchy_review",
                            "source_title_id": source_id,
                            "current_signature": current_sig,
                            "premerge_signature": premerge_sig,
                            "asil_mod_signature": source_sig,
                            "provenance": classify_provenance(
                                state.liege, premerge_liege_sig, source_liege_sig
                            ),
                            "provenance_basis": "effective_liege_state",
                        }
                    )

    bookmark_character_rows: list[dict[str, str]] = []
    for row in bookmark_characters:
        date = parse_date(row["start_date"])
        assert date is not None
        character_id = row["history_id"]
        status = character_status(character_id, date, current_lives)
        title_id = row["title"]
        title_state = current.state_at(title_id, date) if title_id else State()
        title_match = "" if not title_id else str(title_state.holder == character_id).lower()
        result = {
            **row,
            "character_status": status,
            "effective_title_holder": title_state.holder,
            "history_id_holds_declared_title": title_match,
        }
        bookmark_character_rows.append(result)
        if status in {"undefined", "born_after_bookmark", "dead_before_bookmark"}:
            pre_status = character_status(character_id, date, premerge_lives)
            source_status = character_status(character_id, date, source_lives)
            pre_ref = has_bookmark_history_id(premerge_bookmark_texts, character_id)
            source_ref = has_bookmark_history_id(source_bookmark_texts, character_id)
            if source_ref and source_status == status:
                provenance = (
                    "shared_asil_mod_baseline"
                    if pre_ref and pre_status == status
                    else "upstream_integration"
                )
            elif pre_ref and pre_status == status:
                provenance = "preexisting_yusseter"
            else:
                provenance = "yusseter_current_only"
            findings.append(
                {
                    "domain": "runtime",
                    "category": "bookmark_featured_character",
                    "issue": f"featured_character_{status}",
                    "severity": "blocker",
                    "confidence": "high",
                    "title_id": title_id,
                    "bookmark_date": str(date),
                    "holder": character_id,
                    "holder_status": status,
                    "liege": "",
                    "government": row["declared_government"],
                    "path": row["path"],
                    "line": row["line"],
                    "reason": "bookmark portrait references a character invalid at its start date",
                    "recommendation": "repair_bookmark_character_or_history_life_dates",
                    "source_title_id": title_mapping.get(title_id, title_id),
                    "current_signature": "",
                    "premerge_signature": "",
                    "asil_mod_signature": "",
                    "provenance": provenance,
                }
            )
        elif title_id and title_state.holder != character_id:
            source_id = title_mapping.get(title_id, title_id)
            current_sig = signature(current, title_id, date, current_lives)
            premerge_sig = signature(premerge, title_id, date, premerge_lives)
            source_sig = signature(source, source_id, date, source_lives)
            findings.append(
                {
                    "domain": "runtime",
                    "category": "bookmark_featured_character",
                    "issue": "featured_character_not_explicit_title_holder",
                    "severity": "review",
                    "confidence": "medium",
                    "title_id": title_id,
                    "bookmark_date": str(date),
                    "holder": character_id,
                    "holder_status": status,
                    "liege": title_state.liege,
                    "government": row["declared_government"],
                    "path": row["path"],
                    "line": row["line"],
                    "reason": (
                        "featured character is valid but is not the latest explicit holder; "
                        "runtime inheritance or startup effects may resolve this"
                    ),
                    "recommendation": "verify_featured_character_in_game_at_bookmark_start",
                    "source_title_id": source_id,
                    "current_signature": current_sig,
                    "premerge_signature": premerge_sig,
                    "asil_mod_signature": source_sig,
                    "provenance": classify_provenance(
                        current_sig, premerge_sig, source_sig
                    ),
                }
            )

    reported_rows: list[dict[str, str]] = []
    focus_date = Date(1178, 10, 1)
    independent_lookup = {
        (row["title_id"], row["bookmark_date"]): row for row in independent_rows
    }
    for title_id in REPORTED_CASES:
        source_id = title_mapping.get(title_id, title_id)
        current_row = state_row(
            title_id,
            focus_date,
            current,
            current_lives,
            landed_blocks.get(title_id).parent_id if title_id in landed_blocks else "",
        )
        pre_row = state_row(title_id, focus_date, premerge, premerge_lives)
        source_row = state_row(source_id, focus_date, source, source_lives)
        current_state = current.state_at(title_id, focus_date)
        if current_row["holder_status"] in {
            "undefined", "born_after_bookmark", "dead_before_bookmark"
        }:
            conclusion = "confirmed_invalid_effective_holder"
        elif (title_id, str(focus_date)) in independent_lookup:
            conclusion = "confirmed_isolated_county_manual_intent_review"
        elif title_id == "c_suzhou_2" and not current_state.government:
            conclusion = "no_explicit_admin_government_static_runtime_inference_only"
        else:
            conclusion = "static_state_valid_or_prior_observation_stale"
        reported_rows.append(
            {
                **current_row,
                "reported_case_conclusion": conclusion,
                "premerge_holder": pre_row["holder"],
                "premerge_holder_status": pre_row["holder_status"],
                "premerge_liege": pre_row["liege"],
                "premerge_government": pre_row["government"],
                "asil_mod_title_id": source_id,
                "asil_mod_holder": source_row["holder"],
                "asil_mod_holder_status": source_row["holder_status"],
                "asil_mod_liege": source_row["liege"],
                "asil_mod_government": source_row["government"],
            }
        )

    write_csv(output_dir / "bookmark_dates.csv", bookmark_dates)
    write_csv(output_dir / "bookmark_featured_character_state.csv", bookmark_character_rows)
    write_csv(output_dir / "county_effective_state_by_bookmark.csv", state_rows)
    write_csv(output_dir / "independent_county_inventory.csv", independent_rows)
    compact_rows = compact_findings(findings)
    write_csv(output_dir / "bookmark_runtime_static_findings.csv", findings)
    write_csv(output_dir / "bookmark_runtime_static_findings_compact.csv", compact_rows)
    write_csv(output_dir / "reported_cases_1178.csv", reported_rows)
    write_csv(
        output_dir / "title_holder_reference_provenance.csv",
        holder_reference_rows,
    )

    issue_counts = Counter(row["issue"] for row in findings)
    provenance_counts = Counter(row["provenance"] for row in findings)
    conclusion_counts = Counter(row["reported_case_conclusion"] for row in reported_rows)
    summary = [
        "# Bookmark Runtime Static Audit",
        "",
        f"- unique bookmark dates: `{len(dates)}`",
        f"- bookmark definitions: `{len(bookmark_dates)}`",
        f"- featured character rows: `{len(bookmark_character_rows)}`",
        f"- landed counties: `{len(county_ids)}`",
        f"- county/date states: `{len(state_rows)}`",
        f"- independent county inventory: `{len(independent_rows)}`",
        f"- findings: `{len(findings)}`",
        f"- compact findings: `{len(compact_rows)}`",
        f"- blockers: `{sum(row['severity'] == 'blocker' for row in findings)}`",
        f"- reviews: `{sum(row['severity'] == 'review' for row in findings)}`",
        f"- undefined holder provenance rows: `{len(holder_reference_rows)}`",
        "",
        "## Finding Counts",
        "",
    ]
    summary.extend(f"- `{key}`: `{value}`" for key, value in sorted(issue_counts.items()))
    summary.extend(["", "## Provenance Counts", ""])
    summary.extend(
        f"- `{key}`: `{value}`" for key, value in sorted(provenance_counts.items())
    )
    holder_reference_counts = Counter(
        row["classification"] for row in holder_reference_rows
    )
    summary.extend(["", "## Undefined Holder Provenance", ""])
    summary.extend(
        f"- `{key}`: `{value}`"
        for key, value in sorted(holder_reference_counts.items())
    )
    summary.extend(["", "## Reported 1178 Cases", ""])
    summary.extend(
        f"- `{key}`: `{value}`" for key, value in sorted(conclusion_counts.items())
    )
    summary.extend(
        [
            "",
            "## Limits",
            "",
            "- This proves static holder, liege, government, and character-life state only.",
            "- Succession, startup effects, government fallback, and UI display still require runtime smoke tests.",
            "- An independent county is inventory/review evidence, not automatically an error.",
        ]
    )
    (output_dir / "bookmark_runtime_static_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )

    print(f"bookmark_dates={len(dates)}")
    print(f"county_states={len(state_rows)}")
    print(f"findings={len(findings)}")
    print(f"summary={output_dir / 'bookmark_runtime_static_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
