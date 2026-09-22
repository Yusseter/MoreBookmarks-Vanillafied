#!/usr/bin/env python3
"""Build revision-locked, audit-only candidates for pending upstream blockers."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import audit_bookmark_runtime_static as runtime


BLOCKING_ROOTS = {
    "balhae_al_dynasty_parse_failure",
    "balhae_mo_identity_collision",
    "indosphere_history_lifetime_regressions",
    "korean_baek_daeheung_identity_collision",
    "missing_korean_gim_silla_character",
    "removed_dynasty_definitions_break_existing_characters",
    "undefined_goguryo_culture",
    "undefined_poet_trait",
}

CANDIDATE_FIELDS = [
    "root_id",
    "candidate_id",
    "target_path",
    "upstream_lines",
    "candidate_class",
    "source_state",
    "candidate_state",
    "proof",
    "confidence",
    "requires_user_decision",
    "auto_apply",
    "post_merge_validation",
]


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    root = find_project_root()
    tiger_dir = root / "development/analysis/generated/tiger_upstream_delta"
    parser = argparse.ArgumentParser(
        description="Build audit-only fix candidates for pending upstream Tiger blockers"
    )
    parser.add_argument("--repo-root", type=Path, default=root)
    parser.add_argument("--base-revision", required=True)
    parser.add_argument("--upstream-revision", required=True)
    parser.add_argument(
        "--vanilla-game-root",
        type=Path,
        default=Path(
            r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
        ),
    )
    parser.add_argument(
        "--tiger-delta-csv", type=Path, default=tiger_dir / "upstream_tiger_delta.csv"
    )
    parser.add_argument(
        "--tiger-roots-csv",
        type=Path,
        default=tiger_dir / "upstream_tiger_root_causes.csv",
    )
    parser.add_argument(
        "--tiger-manifest",
        type=Path,
        default=tiger_dir / "upstream_tiger_delta_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root
        / "development/analysis/generated/pending_upstream_blocker_fix_candidates",
    )
    return parser.parse_args()


def run_git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def resolve_revision(repo_root: Path, revision: str) -> str:
    return run_git(repo_root, "rev-parse", revision).stdout.decode().strip()


def git_text(repo_root: Path, revision: str, path: str) -> str:
    return run_git(repo_root, "show", f"{revision}:{path}").stdout.decode(
        "utf-8-sig", errors="replace"
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str] | None = None) -> None:
    if fields is None:
        fields = list(rows[0]) if rows else ["status"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def line_numbers(text: str, pattern: str) -> list[int]:
    regex = re.compile(pattern)
    return [
        index
        for index, line in enumerate(text.splitlines(), start=1)
        if regex.search(runtime.strip_comment(line))
    ]


def block_text(block: runtime.Block) -> str:
    return "\n".join(block.lines)


def block_end(block: runtime.Block) -> int:
    return block.start_line + len(block.lines) - 1


def parse_generic(text: str, path: str, layer: str = "upstream") -> dict[str, list[runtime.Block]]:
    relative = path.removeprefix("BookmarksGit/")
    return runtime.parse_blocks(
        {f"{layer}:{relative}": text}, runtime.GENERIC_HEADER_RE
    )


def only_block(blocks: dict[str, list[runtime.Block]], key: str) -> runtime.Block:
    values = blocks.get(key, [])
    if len(values) != 1:
        raise RuntimeError(f"expected one block for {key}, found {len(values)}")
    return values[0]


def add_candidate(rows: list[dict[str, str]], **values: str) -> None:
    row = {field: "" for field in CANDIDATE_FIELDS}
    row.update(values)
    row["auto_apply"] = "no"
    rows.append(row)


def validate_inputs(args: argparse.Namespace) -> tuple[str, str, list[dict[str, str]], list[dict[str, str]]]:
    repo_root = args.repo_root.resolve()
    base = resolve_revision(repo_root, args.base_revision)
    upstream = resolve_revision(repo_root, args.upstream_revision)
    manifest = json.loads(args.tiger_manifest.read_text(encoding="utf-8-sig"))
    if manifest["base_revision"] != base or manifest["latest_revision"] != upstream:
        raise RuntimeError("Tiger manifest revisions do not match requested revisions")

    root_rows = read_csv(args.tiger_roots_csv)
    blocking = {row["root_id"] for row in root_rows if row["status"] == "block_merge"}
    if blocking != BLOCKING_ROOTS:
        raise RuntimeError(
            f"blocking root set changed: missing={sorted(BLOCKING_ROOTS - blocking)} "
            f"extra={sorted(blocking - BLOCKING_ROOTS)}"
        )
    if any(row.get("auto_apply") != "no" for row in root_rows):
        raise RuntimeError("upstream root report contains an automatic apply row")
    return base, upstream, root_rows, read_csv(args.tiger_delta_csv)


def build_exact_candidates(
    repo_root: Path, base: str, upstream: str, vanilla_root: Path
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    dynasty_path = "BookmarksGit/common/dynasties/00_dynasties.txt"
    northeast_path = "BookmarksGit/history/characters/00_ASIA_NORTHEAST.txt"
    indosphere_path = "BookmarksGit/history/characters/00_ASIA_INDOSPHERE.txt"
    unlanded_path = "BookmarksGit/history/characters/00_Z_UNLANDED.txt"

    dynasty_text = git_text(repo_root, upstream, dynasty_path)
    dynasty_blocks = parse_generic(dynasty_text, dynasty_path)
    base_dynasty_blocks = parse_generic(git_text(repo_root, base, dynasty_path), dynasty_path, "base")
    northeast_text = git_text(repo_root, upstream, northeast_path)
    northeast_blocks = parse_generic(northeast_text, northeast_path)
    base_northeast_blocks = parse_generic(
        git_text(repo_root, base, northeast_path), northeast_path, "base"
    )

    al_lines = line_numbers(dynasty_text, r"^BalhaeAl\s+\{$")
    if len(al_lines) != 1:
        raise RuntimeError(f"expected one malformed BalhaeAl header, found {al_lines}")
    add_candidate(
        rows,
        root_id="balhae_al_dynasty_parse_failure",
        candidate_id="balhae_al_add_equals",
        target_path=dynasty_path,
        upstream_lines=str(al_lines[0]),
        candidate_class="exact_source_edit",
        source_state="BalhaeAl {",
        candidate_state="BalhaeAl = {",
        proof="The missing equals prevents the dynasty block from loading; 23 BalhaeAl characters depend on it.",
        confidence="high",
        requires_user_decision="no",
        post_merge_validation="Tiger has no BalhaeAl undefined-dynasty report.",
    )

    mo_dynasties = dynasty_blocks.get("BalhaeMo", [])
    if len(mo_dynasties) != 2:
        raise RuntimeError(f"expected two BalhaeMo dynasty blocks, found {len(mo_dynasties)}")
    if any('name = "dynn_Mo_6155"' not in block_text(item) for item in mo_dynasties):
        raise RuntimeError("BalhaeMo duplicate blocks no longer share dynn_Mo_6155")
    balhae_mon_lines = line_numbers(northeast_text, r"^\s*dynasty\s*=\s*BalhaeMon\s*$")
    if len(balhae_mon_lines) != 22:
        raise RuntimeError(f"expected 22 BalhaeMon references, found {len(balhae_mon_lines)}")
    mo_pairs: list[tuple[runtime.Block, runtime.Block]] = []
    for index in range(1, 23):
        values = northeast_blocks.get(f"BalhaeMo{index}", [])
        if len(values) != 2:
            raise RuntimeError(f"expected duplicate BalhaeMo{index} blocks, found {len(values)}")
        mo_pairs.append((values[0], values[1]))
        if "dynasty = BalhaeMon" not in block_text(values[0]):
            raise RuntimeError(f"first BalhaeMo{index} chain changed dynasty")
        if "dynasty = BalhaeMo" not in block_text(values[1]):
            raise RuntimeError(f"second BalhaeMo{index} chain changed dynasty")

    name_list_text = git_text(
        repo_root, upstream, "BookmarksGit/common/culture/name_lists/z_MB_tungusic.txt"
    )
    dynasty_loc_text = git_text(
        repo_root,
        upstream,
        "BookmarksGit/localization/replace/english/dynasties/z_MB_dynasty_names_l_english.yml",
    )
    if "dynn_Mo_5192" not in name_list_text or "dynn_Mo_5192:" not in dynasty_loc_text:
        raise RuntimeError("the second Mo name key is no longer available")

    add_candidate(
        rows,
        root_id="balhae_mo_identity_collision",
        candidate_id="balhae_mo_first_chain_dynasty",
        target_path=northeast_path,
        upstream_lines=";".join(map(str, balhae_mon_lines)),
        candidate_class="exact_source_edit_bundle",
        source_state="22 first-chain characters use undefined dynasty BalhaeMon",
        candidate_state="Change the 22 first-chain dynasty values to BalhaeMo",
        proof="The first character chain follows BalhaeI_2 and precedes BalhaeGwak, matching the first BalhaeMo/dynn_Mo_6155 dynasty entry.",
        confidence="high",
        requires_user_decision="no",
        post_merge_validation="First Balhae Mo chain has one defined dynasty and no duplicate character IDs.",
    )
    add_candidate(
        rows,
        root_id="balhae_mo_identity_collision",
        candidate_id="balhae_mo_second_dynasty_identity",
        target_path=dynasty_path,
        upstream_lines=f"{mo_dynasties[1].start_line}-{block_end(mo_dynasties[1])}",
        candidate_class="exact_source_edit_bundle",
        source_state="Second BalhaeMo block duplicates BalhaeMo/dynn_Mo_6155",
        candidate_state="Rename the second block to BalhaeMo2 and use dynn_Mo_5192",
        proof="The name list/localization contain two distinct Mo keys; the second block is ordered between BalhaeDal and BalhaeAl and the project uses *2 keys for duplicate romanizations.",
        confidence="high",
        requires_user_decision="no",
        post_merge_validation="BalhaeMo and BalhaeMo2 are each defined once with distinct name keys.",
    )
    second_start = mo_pairs[0][1].start_line
    second_end = block_end(mo_pairs[-1][1])
    add_candidate(
        rows,
        root_id="balhae_mo_identity_collision",
        candidate_id="balhae_mo_second_character_namespace",
        target_path=northeast_path,
        upstream_lines=f"{second_start}-{second_end}",
        candidate_class="exact_source_edit_bundle",
        source_state="Second chain reuses BalhaeMo1..22 and dynasty BalhaeMo",
        candidate_state="Rename it to BalhaeMo2_1..22, including father links, and use dynasty BalhaeMo2",
        proof="Existing BalhaeSin2_*, BalhaeYeo2_*, BalhaeMun2_* and BalhaeGo2_* chains establish this namespace pattern; no external title/bookmark consumer uses these duplicated IDs.",
        confidence="high",
        requires_user_decision="no",
        post_merge_validation="Tiger has no duplicate BalhaeMo characters or undefined Balhae dynasty.",
    )

    for key in ("korean_baek_daeheung_2", "korean_baek_daeheung_3"):
        if len(base_northeast_blocks.get(key, [])) != 1 or len(northeast_blocks.get(key, [])) != 2:
            raise RuntimeError(f"unexpected Baek collision shape for {key}")
    for key in ("korean_baek_daeheung_4", "korean_baek_daeheung_5", "korean_baek_daeheung_6"):
        if key in base_northeast_blocks or len(northeast_blocks.get(key, [])) != 1:
            raise RuntimeError(f"unexpected new Baek extension shape for {key}")
    baek_start = northeast_blocks["korean_baek_daeheung_2"][0].start_line
    baek_end = block_end(northeast_blocks["korean_baek_daeheung_6"][0])
    add_candidate(
        rows,
        root_id="korean_baek_daeheung_identity_collision",
        candidate_id="exclude_new_baek_extension_branch",
        target_path=northeast_path,
        upstream_lines=f"{baek_start}-{baek_end}",
        candidate_class="safe_merge_exclusion",
        source_state="Latest commit adds a second _2.._3 branch plus _4.._6 while base already has canonical _2 and _3 blocks",
        candidate_state="Do not merge the new _2.._6 extension until it receives a separately reviewed namespace",
        proof="Base already contains the later korean_baek_daeheung_2/_3 chain; retaining the new branch would duplicate _2/_3 and its _4.._6 father links depend on the conflicting branch.",
        confidence="high",
        requires_user_decision="yes",
        post_merge_validation="No duplicate korean_baek_daeheung character IDs; baseline _2/_3 remain unchanged.",
    )

    silla_lines = line_numbers(
        northeast_text, r"^\s*add_spouse\s*=\s*korean_gim_silla_73\b"
    )
    gyeongsun = only_block(northeast_blocks, "1900372")
    if len(silla_lines) != 2 or "Gyeongsun Wang" not in block_text(gyeongsun):
        raise RuntimeError("Gyeongsun replacement evidence changed")
    if "910.1.1" not in block_text(gyeongsun) or "978.5.13" not in block_text(gyeongsun):
        raise RuntimeError("Gyeongsun life range changed")
    add_candidate(
        rows,
        root_id="missing_korean_gim_silla_character",
        candidate_id="replace_missing_silla_spouse_id",
        target_path=northeast_path,
        upstream_lines=";".join(map(str, silla_lines)),
        candidate_class="exact_identity_remap",
        source_state="Two spouse effects target undefined korean_gim_silla_73",
        candidate_state="Replace both targets with existing King Gyeongsun character 1900372",
        proof="1900372 is explicitly documented as Gyeongsun Wang, is used by Silla title history, and is alive for both 919 and 940 spouse events.",
        confidence="high",
        requires_user_decision="no",
        post_merge_validation="Tiger has no undefined korean_gim_silla_73 reference and spouse dates remain life-valid.",
    )

    unlanded_text = git_text(repo_root, upstream, unlanded_path)
    viet_d001 = only_block(dynasty_blocks, "viet_d001")
    if 'name = "dynn_Khuc"' not in block_text(viet_d001):
        raise RuntimeError("viet_d001 no longer represents dynn_Khuc")
    dynasty_loc = dynasty_loc_text
    if not re.search(r"^\s*dynn_Khuc:\d*\s+\"Khúc\"", dynasty_loc, re.MULTILINE):
        raise RuntimeError("dynn_Khuc localization changed")
    if not re.search(r"^\s*dynn_Khuc1:\d*\s+\"Khúc\"", dynasty_loc, re.MULTILINE):
        raise RuntimeError("dynn_Khuc1 localization changed")
    for old_id in ("1000027600", "1000060001"):
        if len(base_dynasty_blocks.get(old_id, [])) != 1 or old_id in dynasty_blocks:
            raise RuntimeError(f"unexpected dynasty migration state for {old_id}")
        reference_lines = line_numbers(
            unlanded_text, rf"^\s*dynasty\s*=\s*{re.escape(old_id)}\s*$"
        )
        if len(reference_lines) != 1:
            raise RuntimeError(f"expected one stale reference to {old_id}")
        add_candidate(
            rows,
            root_id="removed_dynasty_definitions_break_existing_characters",
            candidate_id=f"remap_{old_id}_to_viet_d001",
            target_path=unlanded_path,
            upstream_lines=str(reference_lines[0]),
            candidate_class="exact_identity_migration",
            source_state=f"Dummy character still uses removed dynasty {old_id}",
            candidate_state="Change dynasty reference to viet_d001",
            proof=(
                "The pending source removes the numeric Khúc dynasty while retaining canonical "
                "viet_d001/dynn_Khuc; dynn_Khuc and dynn_Khuc1 both localize to Khúc and neither "
                "numeric key has a distinct CoA dependency."
            ),
            confidence="high",
            requires_user_decision="no",
            post_merge_validation=f"Tiger has no undefined dynasty {old_id} report.",
        )

    culture_path = "BookmarksGit/common/culture/cultures/z_MB_00_japonic_koreanic.txt"
    culture_text = git_text(repo_root, upstream, culture_path)
    culture_blocks = parse_generic(culture_text, culture_path)
    if "goguryeo" not in culture_blocks or "goguryo" in culture_blocks:
        raise RuntimeError("goguryeo/goguryo culture definition evidence changed")
    goguryo_lines = line_numbers(northeast_text, r"^\s*culture\s*=\s*goguryo\s*$")
    if len(goguryo_lines) != 11:
        raise RuntimeError(f"expected 11 goguryo typo rows, found {len(goguryo_lines)}")
    add_candidate(
        rows,
        root_id="undefined_goguryo_culture",
        candidate_id="replace_goguryo_with_goguryeo",
        target_path=northeast_path,
        upstream_lines=";".join(map(str, goguryo_lines)),
        candidate_class="exact_source_edit",
        source_state="11 new characters use undefined culture goguryo",
        candidate_state="Replace all 11 values with defined culture goguryeo",
        proof="The same file and province history consistently use goguryeo, and the effective culture definition is keyed goguryeo; no goguryo culture exists.",
        confidence="high",
        requires_user_decision="no",
        post_merge_validation="Tiger has no undefined goguryo culture report.",
    )

    indosphere_text = git_text(repo_root, upstream, indosphere_path)
    poet_lines = line_numbers(indosphere_text, r"^\s*trait\s*=\s*poet\s*$")
    if len(poet_lines) != 1:
        raise RuntimeError(f"expected one invalid poet trait row, found {poet_lines}")
    mod_trait_texts = runtime.read_git_texts(
        repo_root, upstream, "common/traits", "upstream"
    )
    vanilla_trait_texts = runtime.read_layer_texts(
        vanilla_root, "common/traits", "vanilla"
    )
    mod_trait_blocks = runtime.parse_blocks(
        mod_trait_texts, runtime.GENERIC_HEADER_RE, {"poet"}
    )
    vanilla_trait_blocks = runtime.parse_blocks(
        vanilla_trait_texts, runtime.GENERIC_HEADER_RE, {"poet"}
    )
    if "poet" in mod_trait_blocks or "poet" in vanilla_trait_blocks:
        raise RuntimeError("poet trait is now defined; removal candidate must be reviewed")
    add_candidate(
        rows,
        root_id="undefined_poet_trait",
        candidate_id="omit_invalid_poet_trait",
        target_path=indosphere_path,
        upstream_lines=str(poet_lines[0]),
        candidate_class="safe_merge_exclusion",
        source_state="PhamHist4 uses trait = poet, but neither mod nor vanilla defines that trait",
        candidate_state="Do not merge the invalid trait line; keep the character's martial_4, brave and strategist traits",
        proof="The invalid key has no trait definition in the pending source or installed vanilla. Poet flavor, if desired, is a separate nickname/trait authoring decision.",
        confidence="high",
        requires_user_decision="no",
        post_merge_validation="Tiger has no undefined poet trait report.",
    )
    return rows


def parse_location(value: str) -> tuple[str, int]:
    first = value.split(";", 1)[0].strip().replace("\\", "/")
    match = re.fullmatch(r"(.+):(\d+)", first)
    if not match:
        raise RuntimeError(f"cannot parse Tiger location: {value}")
    return match.group(1), int(match.group(2))


def containing_block(
    blocks: dict[str, list[runtime.Block]], line: int
) -> runtime.Block | None:
    matches = [
        block
        for values in blocks.values()
        for block in values
        if block.start_line <= line <= block_end(block)
    ]
    if len(matches) > 1:
        raise RuntimeError(f"multiple top-level blocks contain line {line}")
    return matches[0] if matches else None


def find_text_key(texts: dict[str, str], relative_path: str) -> str:
    wanted = relative_path.removeprefix("BookmarksGit/").lower()
    matches = [key for key in texts if key.split(":", 1)[-1].lower() == wanted]
    if len(matches) != 1:
        raise RuntimeError(f"cannot resolve snapshot text for {relative_path}: {matches}")
    return matches[0]


def extract_history_subject(message: str) -> tuple[str, str, runtime.Date]:
    direct = re.match(r"(\S+) is not alive on ([0-9.]+)", message)
    if direct:
        date = runtime.parse_date(direct.group(2))
        if date is None:
            raise RuntimeError(f"invalid history date in {message}")
        return "character", direct.group(1), date
    title_holder = re.match(r"holder of (\S+) is not alive at ([0-9.]+)", message)
    if title_holder:
        date = runtime.parse_date(title_holder.group(2))
        if date is None:
            raise RuntimeError(f"invalid history date in {message}")
        return "title_holder", title_holder.group(1), date
    no_holder = re.match(r"(\S+) has no holder at ([0-9.]+)", message)
    if no_holder:
        date = runtime.parse_date(no_holder.group(2))
        if date is None:
            raise RuntimeError(f"invalid history date in {message}")
        return "title_without_holder", no_holder.group(1), date
    raise RuntimeError(f"unsupported history message: {message}")


def build_history_candidates(
    repo_root: Path, upstream: str, delta_rows: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rows = [
        row
        for row in delta_rows
        if row.get("direction") == "introduced"
        and row.get("key") == "history"
        and (
            "asia_indosphere" in row.get("mod_paths", "").lower()
            or "asia_south" in row.get("mod_paths", "").lower()
        )
    ]
    if len(rows) != 20:
        raise RuntimeError(f"expected 20 Indosphere history rows, found {len(rows)}")
    severity_counts = Counter(row["severity"] for row in rows)
    if severity_counts != Counter({"warning": 17, "error": 3}):
        raise RuntimeError(f"Indosphere severity distribution changed: {severity_counts}")

    character_texts = runtime.read_git_texts(
        repo_root, upstream, "history/characters", "upstream"
    )
    title_texts = runtime.read_git_texts(
        repo_root, upstream, "history/titles", "upstream"
    )
    character_blocks = runtime.parse_blocks(
        character_texts, runtime.GENERIC_HEADER_RE
    )
    title_blocks = runtime.parse_blocks(title_texts, runtime.TITLE_HEADER_RE)
    title_dataset = runtime.TitleDataset(
        "upstream", runtime.parse_title_events(title_blocks), title_blocks
    )

    parsed: list[tuple[dict[str, str], str, int, str, str, runtime.Date]] = []
    wanted_characters: set[str] = set()
    for row in rows:
        path, line = parse_location(row["locations"])
        subject_type, subject, date = extract_history_subject(row["message"])
        if subject_type == "character":
            wanted_characters.add(subject)
        elif subject_type == "title_holder":
            holder = title_dataset.state_at(subject, date).holder
            if holder:
                wanted_characters.add(holder)
        parsed.append((row, path, line, subject_type, subject, date))

    lives = runtime.build_character_lives(wanted_characters, character_texts, {})
    direct_subjects = {
        subject
        for _row, _path, _line, subject_type, subject, _date in parsed
        if subject_type == "character"
    }
    reported_assignments: set[tuple[str, runtime.Date, str]] = set()
    for _row, path, line, subject_type, subject, date in parsed:
        if subject_type != "character" or "history/titles/" not in path.lower():
            continue
        text_key = find_text_key(title_texts, path)
        path_blocks = {
            key: [block for block in values if block.path == text_key]
            for key, values in title_blocks.items()
        }
        container = containing_block(path_blocks, line)
        if container is not None:
            reported_assignments.add((container.key, date, subject))

    assignments: dict[
        tuple[str, runtime.Date, str, str], tuple[str, runtime.Date, str, str, int]
    ] = {}
    for assignment in runtime.holder_assignments(title_dataset):
        date = assignment["date"]
        if not isinstance(date, runtime.Date):
            continue
        key = (
            str(assignment["title_id"]),
            date,
            str(assignment["holder"]),
            str(assignment["path"]),
        )
        assignments[key] = (
            str(assignment["title_id"]),
            date,
            str(assignment["holder"]),
            str(assignment["path"]),
            int(assignment["line"]),
        )
    for title_id, events in title_dataset.events.items():
        for event in events:
            holder = event.values.get("holder", "")
            if not holder or holder == "0":
                continue
            key = (title_id, event.date, holder, event.path)
            assignments.setdefault(
                key, (title_id, event.date, holder, event.path, event.line)
            )

    for title_id, date, holder, source_path, line in assignments.values():
        relative_path = source_path.split(":", 1)[-1].replace("\\", "/")
        if relative_path.lower() != "history/titles/00_asia_south.txt":
            continue
        if holder not in direct_subjects:
            continue
        if (title_id, date, holder) in reported_assignments:
            continue
        if runtime.character_status(holder, date, lives) not in {
            "born_after_bookmark",
            "dead_before_bookmark",
        }:
            continue
        path = f"BookmarksGit/{relative_path}"
        text_key = find_text_key(title_texts, path)
        source_preview = title_texts[text_key].splitlines()[line - 1].strip()
        message = f"{holder} is not alive on {date}"
        related_row = {
            "severity": "related_inherited",
            "message": message,
            "line_previews": source_preview,
        }
        parsed.append((related_row, path, line, "character", holder, date))
        reported_assignments.add((title_id, date, holder))

    candidate_rows: list[dict[str, str]] = []
    detail_rows: list[dict[str, str]] = []
    for row, path, line, subject_type, subject, date in parsed:
        relative = path.removeprefix("BookmarksGit/")
        if relative.lower().startswith("history/characters/"):
            text_key = find_text_key(character_texts, path)
            path_blocks = {
                key: [block for block in values if block.path == text_key]
                for key, values in character_blocks.items()
            }
        elif relative.lower().startswith("history/titles/"):
            text_key = find_text_key(title_texts, path)
            path_blocks = {
                key: [block for block in values if block.path == text_key]
                for key, values in title_blocks.items()
            }
        else:
            raise RuntimeError(f"unexpected Indosphere history path: {path}")
        container = containing_block(path_blocks, line)
        if container is None:
            raise RuntimeError(f"cannot find top-level container for {path}:{line}")

        effective_character = ""
        if subject_type == "character":
            effective_character = subject
        elif subject_type == "title_holder":
            effective_character = title_dataset.state_at(subject, date).holder
        life = lives.get(effective_character)
        if subject_type == "title_without_holder":
            life_status = "no_effective_holder"
        elif effective_character:
            life_status = runtime.character_status(effective_character, date, lives)
        else:
            life_status = "effective_holder_missing"

        candidate_class = "manual_source_history_review"
        candidate_date = ""
        timeline_evidence = "No safe date or identity can be inferred from the local timeline."
        if (
            container.key == "VietVuong8"
            and effective_character == "1418010"
            and "add_spouse" in row.get("line_previews", "")
        ):
            block_end = container.start_line + len(container.lines) - 1
            candidate_class = "safe_duplicate_character_exclusion"
            recommended = (
                f"Exclude the duplicate VietVuong8 character block at lines "
                f"{container.start_line}-{block_end}; keep the established 1418006 identity."
            )
            timeline_evidence = (
                "upstream_comment_prefers_existing_1418006; "
                "1418006_add_spouse_1418010=931.1.1; "
                "children_reference_mother_1418006=yes"
            )
            confidence = "high"
        elif row["severity"] == "error":
            recommended = (
                "Do not merge this exact liege entry until the referenced liege title "
                "has a valid living holder at the event date; otherwise exclude the entry."
            )
            confidence = "manual"
        elif "add_spouse" in row.get("line_previews", ""):
            recommended = (
                "Review the historical spouse date/identity and exclude or retime the "
                "event; do not infer a replacement from name similarity."
            )
            confidence = "manual"
        elif (
            subject_type == "character"
            and relative.lower().startswith("history/titles/")
            and life_status == "born_after_bookmark"
            and life is not None
            and life.birth is not None
        ):
            holder_events = [
                event
                for event in title_dataset.events.get(container.key, [])
                if event.values.get("holder", "") not in {"", "0"}
            ]
            valid_same_holder = [
                event
                for event in holder_events
                if event.date > date
                and event.values.get("holder") == effective_character
                and runtime.character_status(
                    effective_character, event.date, lives
                ) not in {"born_after_bookmark", "dead_before_bookmark"}
            ]
            if valid_same_holder:
                valid_event = min(valid_same_holder, key=lambda item: item.date)
                candidate_class = "safe_duplicate_assignment_exclusion"
                candidate_date = str(valid_event.date)
                recommended = (
                    f"Exclude the invalid early assignment at {date}; the same character "
                    f"already has a valid holder assignment at {valid_event.date}."
                )
                timeline_evidence = (
                    f"same_holder_valid_event={valid_event.date}; birth={life.birth}"
                )
                confidence = "high"
            else:
                valid_following_dates: list[runtime.Date] = []
                for event in holder_events:
                    following_holder = event.values.get("holder", "")
                    if event.date <= date or following_holder == effective_character:
                        continue
                    if following_holder in lives and runtime.character_status(
                        following_holder, event.date, lives
                    ) in {"born_after_bookmark", "dead_before_bookmark"}:
                        continue
                    valid_following_dates.append(event.date)
                next_holder_date = (
                    min(valid_following_dates) if valid_following_dates else None
                )
                if next_holder_date is None or life.birth < next_holder_date:
                    candidate_class = "chronology_retime_candidate"
                    candidate_date = str(life.birth)
                    recommended = (
                        f"Candidate: retime the holder assignment from {date} to the "
                        f"character birth date {life.birth}; keep the previous holder until then."
                    )
                    timeline_evidence = (
                        f"birth={life.birth}; "
                        f"next_valid_holder_event={next_holder_date or 'none'}"
                    )
                    confidence = "medium"
                else:
                    recommended = (
                        "Review the historical holder identity/date; the character birth "
                        "does not fit before the next valid holder event."
                    )
                    timeline_evidence = (
                        f"birth={life.birth}; next_valid_holder_event={next_holder_date}"
                    )
                    confidence = "manual"
        else:
            recommended = (
                "Review the historical holder identity/date and exclude or retime this "
                "entry until the character is alive."
            )
            confidence = "manual"

        life_text = (
            f"birth={life.birth if life and life.birth else ''};"
            f"death={life.death if life and life.death else ''};status={life_status}"
        )
        candidate_id = f"indosphere_history_{line}"
        evidence_source = (
            "related full-history scan"
            if row["severity"] == "related_inherited"
            else "Tiger introduced delta"
        )
        proof = (
            f"container={container.key}; event_date={date}; referenced={subject}; "
            f"effective_character={effective_character}; {life_text}; "
            f"source={evidence_source}; timeline={timeline_evidence}; issue={row['message']}"
        )
        add_candidate(
            candidate_rows,
            root_id="indosphere_history_lifetime_regressions",
            candidate_id=candidate_id,
            target_path=path,
            upstream_lines=str(line),
            candidate_class=candidate_class,
            source_state=row.get("line_previews", ""),
            candidate_state=recommended,
            proof=proof,
            confidence=confidence,
            requires_user_decision="yes",
            post_merge_validation="Re-run Tiger history checks and the bookmark/runtime static audit.",
        )
        detail_rows.append(
            {
                "candidate_id": candidate_id,
                "severity": row["severity"],
                "path": path,
                "line": str(line),
                "container_id": container.key,
                "event_date": str(date),
                "issue": row["message"],
                "referenced_object": subject,
                "effective_character": effective_character,
                "character_birth": str(life.birth) if life and life.birth else "",
                "character_death": str(life.death) if life and life.death else "",
                "life_status": life_status,
                "candidate_class": candidate_class,
                "candidate_date": candidate_date,
                "timeline_evidence": timeline_evidence,
                "source_preview": row.get("line_previews", ""),
                "recommended_merge_action": recommended,
                "fix_confidence": confidence,
                "requires_user_decision": "yes",
                "auto_apply": "no",
            }
        )
    candidate_rows.sort(key=lambda item: (item["target_path"].lower(), int(item["upstream_lines"])))
    detail_rows.sort(key=lambda item: (item["path"].lower(), int(item["line"])))
    return candidate_rows, detail_rows


def build_root_resolution_rows(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    counts = Counter(row["root_id"] for row in candidates)
    status = {
        "balhae_al_dynasty_parse_failure": ("exact_candidate_ready", "no"),
        "balhae_mo_identity_collision": ("exact_bundle_candidate_ready", "no"),
        "indosphere_history_lifetime_regressions": ("manual_source_timeline_required", "yes"),
        "korean_baek_daeheung_identity_collision": ("safe_exclusion_candidate_requires_review", "yes"),
        "missing_korean_gim_silla_character": ("exact_identity_remap_ready", "no"),
        "removed_dynasty_definitions_break_existing_characters": ("exact_identity_migration_ready", "no"),
        "undefined_goguryo_culture": ("exact_typo_fix_ready", "no"),
        "undefined_poet_trait": ("safe_invalid_line_exclusion_ready", "no"),
    }
    rows: list[dict[str, str]] = []
    for root_id in sorted(BLOCKING_ROOTS):
        if counts[root_id] == 0:
            raise RuntimeError(f"blocking root has no candidate rows: {root_id}")
        resolution_status, user_decision = status[root_id]
        rows.append(
            {
                "root_id": root_id,
                "candidate_row_count": str(counts[root_id]),
                "resolution_status": resolution_status,
                "requires_user_decision": user_decision,
                "current_merge_gate": "block_merge",
                "auto_apply": "no",
            }
        )
    return rows


def write_summary(
    path: Path,
    base: str,
    upstream: str,
    candidates: list[dict[str, str]],
    root_rows: list[dict[str, str]],
    history_rows: list[dict[str, str]],
) -> None:
    class_counts = Counter(row["candidate_class"] for row in candidates)
    history_counts = Counter(row["severity"] for row in history_rows)
    user_roots = sum(row["requires_user_decision"] == "yes" for row in root_rows)
    lines = [
        "# Bekleyen Asıl Mod Blocker Düzeltme Adayları",
        "",
        "## Revisionlar",
        "",
        f"- Taban: `{base}`",
        f"- Güncel asıl mod: `{upstream}`",
        "",
        "## Sonuç",
        "",
        "- Merge durumu: `do_not_merge_yet`",
        f"- Blocker kök kapsamı: `{len(root_rows)} / {len(BLOCKING_ROOTS)}`",
        f"- Aday satırı: `{len(candidates)}`",
        f"- Kullanıcı kararı gerektiren kök: `{user_roots}`",
        "- Otomatik uygulama: `hayır`",
        "",
        "## Aday Sınıfları",
        "",
    ]
    lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(class_counts.items()))
    lines.extend(
        [
            "",
            "## Indosphere History",
            "",
            f"- Error: `{history_counts.get('error', 0)}`",
            f"- Warning: `{history_counts.get('warning', 0)}`",
            f"- Aynı kökte bulunan inherited satır: `{history_counts.get('related_inherited', 0)}`",
            f"- Toplam manuel history satırı: `{len(history_rows)}`",
            f"- Teknik chronology retime adayı: `{class_counts.get('chronology_retime_candidate', 0)}`",
            f"- Güvenli erken-kopya dışlama adayı: `{class_counts.get('safe_duplicate_assignment_exclusion', 0)}`",
            f"- Güvenli duplicate-character dışlama adayı: `{class_counts.get('safe_duplicate_character_exclusion', 0)}`",
            f"- Kaynak/timeline kararı gereken satır: `{class_counts.get('manual_source_history_review', 0)}`",
            "- Retime tarihleri yalnız doğum ve sonraki geçerli holder zincirinden türetilmiş adaylardır; tarihsel doğruluk veya otomatik uygulama anlamına gelmez.",
            "",
            "## Güvenlik",
            "",
            "- Rapor yalnız `development/analysis/generated` altında üretilir.",
            "- Canlı `BookmarksGit` dosyaları değiştirilmez.",
            "- Her adayda `auto_apply=no` zorunludur.",
            "- Revision veya sekiz blocker kökünden biri değişirse araç bilinçli olarak durur.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.repo_root = args.repo_root.resolve()
    args.output_dir = args.output_dir.resolve()
    base, upstream, _root_rows, delta_rows = validate_inputs(args)

    candidates = build_exact_candidates(
        args.repo_root, base, upstream, args.vanilla_game_root.resolve()
    )
    history_candidates, history_detail = build_history_candidates(
        args.repo_root, upstream, delta_rows
    )
    candidates.extend(history_candidates)
    candidates.sort(key=lambda item: (item["root_id"], item["candidate_id"]))
    if any(row["auto_apply"] != "no" for row in candidates):
        raise RuntimeError("candidate report contains an automatic apply row")

    root_resolution = build_root_resolution_rows(candidates)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = args.output_dir / "pending_upstream_blocker_fix_candidates.csv"
    history_path = args.output_dir / "indosphere_history_manual_review.csv"
    root_path = args.output_dir / "pending_upstream_blocker_root_resolution.csv"
    summary_path = args.output_dir / "pending_upstream_blocker_fix_candidates_summary.md"
    manifest_path = args.output_dir / "input_sha256_manifest.csv"
    write_csv(candidate_path, candidates, CANDIDATE_FIELDS)
    write_csv(history_path, history_detail)
    write_csv(root_path, root_resolution)
    write_summary(summary_path, base, upstream, candidates, root_resolution, history_detail)

    manifest_rows = [
        {"input": "base_revision", "identity": base, "sha256": ""},
        {"input": "upstream_revision", "identity": upstream, "sha256": ""},
    ]
    for label, input_path in (
        ("script", Path(__file__).resolve()),
        ("tiger_delta_csv", args.tiger_delta_csv.resolve()),
        ("tiger_roots_csv", args.tiger_roots_csv.resolve()),
        ("tiger_manifest", args.tiger_manifest.resolve()),
    ):
        manifest_rows.append(
            {"input": label, "identity": str(input_path), "sha256": sha256(input_path)}
        )
    write_csv(manifest_path, manifest_rows, ["input", "identity", "sha256"])

    print(f"base_revision={base}")
    print(f"upstream_revision={upstream}")
    print(f"blocking_roots={len(root_resolution)}")
    print(f"candidate_rows={len(candidates)}")
    print(f"indosphere_history_rows={len(history_detail)}")
    print("auto_apply=no")
    print("merge_status=do_not_merge_yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
