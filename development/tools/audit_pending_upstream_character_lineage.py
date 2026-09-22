#!/usr/bin/env python3
"""Audit pending upstream character changes for lineage and life contradictions."""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import audit_bookmark_runtime_static as runtime
import build_pending_upstream_blocker_fix_candidates as common


SCALAR_RE_TEMPLATE = r"\b{field}\s*=\s*\"?([A-Za-z0-9_.:\-]+)\"?"
SPOUSE_RE = re.compile(r"\badd_spouse\s*=\s*\"?([A-Za-z0-9_.:\-]+)\"?")


@dataclass(frozen=True)
class SpouseEvent:
    date: runtime.Date
    spouse_id: str
    line: int


@dataclass(frozen=True)
class CharacterRecord:
    character_id: str
    path: str
    line: int
    birth: runtime.Date | None
    death: runtime.Date | None
    father: str
    father_line: int
    mother: str
    mother_line: int
    spouse_events: tuple[SpouseEvent, ...]
    fingerprint: str


@dataclass(frozen=True)
class Snapshot:
    records: dict[str, CharacterRecord]
    duplicate_counts: dict[str, int]
    mod_fingerprints: dict[str, tuple[str, ...]]


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    root = find_project_root()
    parser = argparse.ArgumentParser(
        description="Audit pending upstream character lineage without editing live files"
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
        "--output-dir",
        type=Path,
        default=root
        / "development/analysis/generated/pending_upstream_character_lineage",
    )
    return parser.parse_args()


def relative_source_path(path: str) -> str:
    return path.split(":", 1)[-1].replace("\\", "/")


def live_path(path: str) -> str:
    relative = relative_source_path(path)
    return f"BookmarksGit/{relative}" if not path.startswith("vanilla:") else relative


def block_fingerprint(block: runtime.Block) -> str:
    normalized = "\n".join(line.rstrip() for line in block.lines)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def scalar_value(entry: runtime.DirectEntry, field: str) -> str:
    text = runtime.strip_comment(entry.lines[0])
    match = re.search(SCALAR_RE_TEMPLATE.format(field=re.escape(field)), text)
    return match.group(1) if match else ""


def record_from_block(block: runtime.Block) -> CharacterRecord:
    birth: runtime.Date | None = None
    death: runtime.Date | None = None
    father = ""
    father_line = 0
    mother = ""
    mother_line = 0
    spouse_events: list[SpouseEvent] = []
    for entry in runtime.direct_entries(block):
        line = block.start_line + entry.relative_start
        if entry.key == "father":
            father = scalar_value(entry, "father")
            father_line = line
            continue
        if entry.key == "mother":
            mother = scalar_value(entry, "mother")
            mother_line = line
            continue
        date = runtime.parse_date(entry.key)
        if date is None:
            continue
        body = runtime.direct_body(entry.lines)
        if re.search(r"\bbirth\s*=", body):
            birth = date if birth is None else min(birth, date)
        if re.search(r"\bdeath\s*=", body):
            death = date if death is None else min(death, date)
        for spouse_id in SPOUSE_RE.findall(body):
            spouse_events.append(SpouseEvent(date, spouse_id, line))
    return CharacterRecord(
        character_id=block.key,
        path=block.path,
        line=block.start_line,
        birth=birth,
        death=death,
        father=father,
        father_line=father_line,
        mother=mother,
        mother_line=mother_line,
        spouse_events=tuple(spouse_events),
        fingerprint=block_fingerprint(block),
    )


def build_snapshot(
    mod_texts: dict[str, str], vanilla_texts: dict[str, str]
) -> Snapshot:
    effective_texts = runtime.effective_vanilla_texts(mod_texts, vanilla_texts)
    effective_texts.update(mod_texts)
    effective_blocks = runtime.parse_blocks(
        effective_texts, runtime.GENERIC_HEADER_RE
    )
    records: dict[str, CharacterRecord] = {}
    duplicate_counts: dict[str, int] = {}
    for character_id, blocks in effective_blocks.items():
        if len(blocks) != 1:
            duplicate_counts[character_id] = len(blocks)
            continue
        records[character_id] = record_from_block(blocks[0])

    mod_blocks = runtime.parse_blocks(mod_texts, runtime.GENERIC_HEADER_RE)
    mod_fingerprints = {
        character_id: tuple(sorted(block_fingerprint(block) for block in blocks))
        for character_id, blocks in mod_blocks.items()
    }
    return Snapshot(records, duplicate_counts, mod_fingerprints)


def full_years(earlier: runtime.Date, later: runtime.Date) -> int:
    years = later.year - earlier.year
    if (later.month, later.day) < (earlier.month, earlier.day):
        years -= 1
    return years


def semantic_signature(row: dict[str, str]) -> str:
    return "|".join(
        row[key]
        for key in (
            "classification",
            "character_id",
            "relation",
            "related_id",
            "event_date",
        )
    )


def make_finding(
    *,
    classification: str,
    severity: str,
    character: CharacterRecord,
    relation: str,
    related_id: str,
    event_date: runtime.Date | None,
    line: int,
    child_birth: runtime.Date | None,
    related_birth: runtime.Date | None,
    related_death: runtime.Date | None,
    age_at_event: str,
    reason: str,
    recommendation: str,
) -> dict[str, str]:
    row = {
        "classification": classification,
        "severity": severity,
        "character_id": character.character_id,
        "relation": relation,
        "related_id": related_id,
        "event_date": str(event_date) if event_date else "",
        "path": live_path(character.path),
        "line": str(line or character.line),
        "character_birth": str(child_birth) if child_birth else "",
        "related_birth": str(related_birth) if related_birth else "",
        "related_death": str(related_death) if related_death else "",
        "related_age_at_event": age_at_event,
        "reason": reason,
        "recommendation": recommendation,
        "auto_apply": "no",
    }
    row["signature"] = semantic_signature(row)
    return row


def analyze_snapshot(snapshot: Snapshot) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for character in snapshot.records.values():
        if (
            character.birth is not None
            and character.death is not None
            and character.death <= character.birth
        ):
            findings.append(
                make_finding(
                    classification="death_not_after_birth",
                    severity="blocker",
                    character=character,
                    relation="self_life",
                    related_id="",
                    event_date=character.death,
                    line=character.line,
                    child_birth=character.birth,
                    related_birth=None,
                    related_death=None,
                    age_at_event="",
                    reason="Character death is not later than birth.",
                    recommendation="Correct the character life dates from source evidence.",
                )
            )

        for role, parent_id, relation_line in (
            ("father", character.father, character.father_line),
            ("mother", character.mother, character.mother_line),
        ):
            if not parent_id or parent_id == "0":
                continue
            parent = snapshot.records.get(parent_id)
            if parent is None:
                if parent_id in snapshot.duplicate_counts:
                    classification = "parent_identity_ambiguous_duplicate"
                    reason = "Parent identity has multiple effective character blocks."
                else:
                    classification = "undefined_parent"
                    reason = "Parent character is not defined in the effective snapshot."
                findings.append(
                    make_finding(
                        classification=classification,
                        severity="blocker",
                        character=character,
                        relation=role,
                        related_id=parent_id,
                        event_date=character.birth,
                        line=relation_line,
                        child_birth=character.birth,
                        related_birth=None,
                        related_death=None,
                        age_at_event="",
                        reason=reason,
                        recommendation="Resolve the parent identity before merging this lineage.",
                    )
                )
                continue
            if character.birth is None or parent.birth is None:
                continue
            age = full_years(parent.birth, character.birth)
            father_posthumous_limit = (
                runtime.Date(
                    parent.death.year + 1, parent.death.month, parent.death.day
                )
                if role == "father" and parent.death is not None
                else None
            )
            father_dead_too_early = (
                father_posthumous_limit is not None
                and character.birth > father_posthumous_limit
            )
            mother_dead_too_early = (
                role == "mother"
                and parent.death is not None
                and parent.death < character.birth
            )
            if age <= 0:
                findings.append(
                    make_finding(
                        classification="parent_not_older_than_child",
                        severity="blocker",
                        character=character,
                        relation=role,
                        related_id=parent_id,
                        event_date=character.birth,
                        line=relation_line,
                        child_birth=character.birth,
                        related_birth=parent.birth,
                        related_death=parent.death,
                        age_at_event=str(age),
                        reason="Parent is born on or after the child.",
                        recommendation="Correct the parent identity or life dates from source evidence.",
                    )
                )
            elif age < 12:
                findings.append(
                    make_finding(
                        classification="parent_implausibly_young",
                        severity="review",
                        character=character,
                        relation=role,
                        related_id=parent_id,
                        event_date=character.birth,
                        line=relation_line,
                        child_birth=character.birth,
                        related_birth=parent.birth,
                        related_death=parent.death,
                        age_at_event=str(age),
                        reason="Parent is younger than 12 at the child's birth.",
                        recommendation="Review the generated genealogy and dates.",
                    )
                )
            elif (
                ((role == "mother" and age > 55) or (role == "father" and age > 90))
                and not father_dead_too_early
                and not mother_dead_too_early
            ):
                findings.append(
                    make_finding(
                        classification="parent_age_extreme",
                        severity="review",
                        character=character,
                        relation=role,
                        related_id=parent_id,
                        event_date=character.birth,
                        line=relation_line,
                        child_birth=character.birth,
                        related_birth=parent.birth,
                        related_death=parent.death,
                        age_at_event=str(age),
                        reason="Parent age at child birth is outside the conservative review range.",
                        recommendation="Review the generated genealogy and dates.",
                    )
                )
            if parent.death is None:
                continue
            if mother_dead_too_early:
                findings.append(
                    make_finding(
                        classification="mother_dead_before_child_birth",
                        severity="blocker",
                        character=character,
                        relation=role,
                        related_id=parent_id,
                        event_date=character.birth,
                        line=relation_line,
                        child_birth=character.birth,
                        related_birth=parent.birth,
                        related_death=parent.death,
                        age_at_event=str(age),
                        reason="Mother dies before the child's birth.",
                        recommendation="Correct the mother identity or life dates from source evidence.",
                    )
            )
            if father_dead_too_early:
                findings.append(
                    make_finding(
                        classification="father_dead_too_long_before_child_birth",
                        severity="blocker",
                        character=character,
                        relation=role,
                        related_id=parent_id,
                        event_date=character.birth,
                        line=relation_line,
                        child_birth=character.birth,
                        related_birth=parent.birth,
                        related_death=parent.death,
                        age_at_event=str(age),
                        reason="Father dies more than one year before the child's birth.",
                        recommendation="Correct the father identity or life dates from source evidence.",
                    )
                )

        for event in character.spouse_events:
            spouse = snapshot.records.get(event.spouse_id)
            if spouse is None:
                findings.append(
                    make_finding(
                        classification="undefined_spouse",
                        severity="blocker",
                        character=character,
                        relation="add_spouse",
                        related_id=event.spouse_id,
                        event_date=event.date,
                        line=event.line,
                        child_birth=character.birth,
                        related_birth=None,
                        related_death=None,
                        age_at_event="",
                        reason="Spouse character is not uniquely defined.",
                        recommendation="Resolve the spouse identity before merging the event.",
                    )
                )
                continue
            actor_status = runtime.character_status(
                character.character_id,
                event.date,
                {
                    character.character_id: runtime.CharacterLife(
                        character.character_id,
                        character.birth,
                        character.death,
                        character.path,
                        character.line,
                    )
                },
            )
            spouse_status = runtime.character_status(
                spouse.character_id,
                event.date,
                {
                    spouse.character_id: runtime.CharacterLife(
                        spouse.character_id,
                        spouse.birth,
                        spouse.death,
                        spouse.path,
                        spouse.line,
                    )
                },
            )
            if actor_status in {"born_after_bookmark", "dead_before_bookmark"}:
                findings.append(
                    make_finding(
                        classification="spouse_event_actor_not_alive",
                        severity="blocker",
                        character=character,
                        relation="add_spouse",
                        related_id=event.spouse_id,
                        event_date=event.date,
                        line=event.line,
                        child_birth=character.birth,
                        related_birth=spouse.birth,
                        related_death=spouse.death,
                        age_at_event="",
                        reason=f"Character status at spouse event is {actor_status}.",
                        recommendation="Retime or exclude the spouse event from source evidence.",
                    )
                )
            if spouse_status in {"born_after_bookmark", "dead_before_bookmark"}:
                findings.append(
                    make_finding(
                        classification="spouse_event_target_not_alive",
                        severity="blocker",
                        character=character,
                        relation="add_spouse",
                        related_id=event.spouse_id,
                        event_date=event.date,
                        line=event.line,
                        child_birth=character.birth,
                        related_birth=spouse.birth,
                        related_death=spouse.death,
                        age_at_event="",
                        reason=f"Spouse status at event is {spouse_status}.",
                        recommendation="Retime, remap, or exclude the spouse event from source evidence.",
                    )
                )
    return findings


OUTPUT_FIELDS = [
    "direction",
    "effective_severity",
    "intrinsic_severity",
    "classification",
    "character_id",
    "relation",
    "related_id",
    "event_date",
    "path",
    "line",
    "character_birth",
    "related_birth",
    "related_death",
    "related_age_at_event",
    "character_changed",
    "related_changed",
    "existing_root_overlap",
    "lineage_root_id",
    "reason",
    "recommendation",
    "signature",
    "auto_apply",
]


def scoped_rows(
    base_findings: list[dict[str, str]],
    upstream_findings: list[dict[str, str]],
    changed_ids: set[str],
    base_snapshot: Snapshot,
    upstream_snapshot: Snapshot,
) -> list[dict[str, str]]:
    base_by_signature = {row["signature"]: row for row in base_findings}
    upstream_by_signature = {row["signature"]: row for row in upstream_findings}
    rows: list[dict[str, str]] = []
    for signature in sorted(set(base_by_signature) | set(upstream_by_signature)):
        base_row = base_by_signature.get(signature)
        upstream_row = upstream_by_signature.get(signature)
        source = upstream_row or base_row
        assert source is not None
        character_changed = source["character_id"] in changed_ids
        related_changed = source["related_id"] in changed_ids
        if not character_changed and not related_changed:
            continue
        if upstream_row is not None and base_row is None:
            upstream_record = upstream_snapshot.records.get(
                upstream_row["character_id"]
            )
            exact_block_in_base = (
                upstream_record is not None
                and upstream_record.fingerprint
                in base_snapshot.mod_fingerprints.get(
                    upstream_row["character_id"], ()
                )
            )
            if (
                exact_block_in_base
                and upstream_row["classification"]
                in {"undefined_parent", "undefined_spouse"}
            ):
                direction = "related_inherited_after_duplicate_resolution"
                effective_severity = "info"
            else:
                direction = "introduced"
                effective_severity = upstream_row["severity"]
            selected = upstream_row
        elif upstream_row is None and base_row is not None:
            direction = "resolved"
            effective_severity = "info"
            selected = base_row
        else:
            direction = "related_inherited"
            effective_severity = "info"
            selected = upstream_row
            assert selected is not None
        overlap = ""
        if (
            selected["character_id"] == "VietVuong8"
            and selected["related_id"] == "1418010"
        ):
            overlap = "indosphere_history_lifetime_regressions"
        elif selected["related_id"] == "korean_gim_silla_73":
            overlap = "missing_korean_gim_silla_character"
        elif selected["character_id"].startswith("korean_baek_daeheung_"):
            overlap = "korean_baek_daeheung_identity_collision"
        lineage_root_id = ""
        normalized_path = selected["path"].replace("\\", "/")
        if direction == "introduced" and not overlap:
            if normalized_path.endswith("history/characters/00_ASIA_INDOSPHERE.txt"):
                lineage_root_id = "indosphere_character_lineage_regressions"
            elif normalized_path.endswith("history/characters/00_ASIA_NORTHEAST.txt"):
                lineage_root_id = "northeast_character_lineage_quality_review"
        rows.append(
            {
                "direction": direction,
                "effective_severity": effective_severity,
                "intrinsic_severity": selected["severity"],
                "classification": selected["classification"],
                "character_id": selected["character_id"],
                "relation": selected["relation"],
                "related_id": selected["related_id"],
                "event_date": selected["event_date"],
                "path": selected["path"],
                "line": selected["line"],
                "character_birth": selected["character_birth"],
                "related_birth": selected["related_birth"],
                "related_death": selected["related_death"],
                "related_age_at_event": selected["related_age_at_event"],
                "character_changed": "yes" if character_changed else "no",
                "related_changed": "yes" if related_changed else "no",
                "existing_root_overlap": overlap,
                "lineage_root_id": lineage_root_id,
                "reason": selected["reason"],
                "recommendation": selected["recommendation"],
                "signature": selected["signature"],
                "auto_apply": "no",
            }
        )
    return rows


def write_summary(
    path: Path,
    *,
    base: str,
    upstream: str,
    changed_paths: list[str],
    changed_ids: set[str],
    rows: list[dict[str, str]],
    introduced_duplicates: set[str],
) -> None:
    directions = Counter(row["direction"] for row in rows)
    introduced_severity = Counter(
        row["effective_severity"]
        for row in rows
        if row["direction"] == "introduced"
    )
    introduced_classes = Counter(
        row["classification"]
        for row in rows
        if row["direction"] == "introduced"
    )
    introduced_overlap = sum(
        row["direction"] == "introduced" and bool(row["existing_root_overlap"])
        for row in rows
    )
    independent_blockers = sum(
        row["direction"] == "introduced"
        and row["effective_severity"] == "blocker"
        and not row["existing_root_overlap"]
        for row in rows
    )
    independent_blocker_roots = sorted(
        {
            row["lineage_root_id"]
            for row in rows
            if row["direction"] == "introduced"
            and row["effective_severity"] == "blocker"
            and row["lineage_root_id"]
        }
    )
    independent_review_roots = sorted(
        {
            row["lineage_root_id"]
            for row in rows
            if row["direction"] == "introduced"
            and row["effective_severity"] == "review"
            and row["lineage_root_id"]
        }
        - set(independent_blocker_roots)
    )
    inherited_total = (
        directions["related_inherited"]
        + directions["related_inherited_after_duplicate_resolution"]
    )
    duplicate_overlap = sum(
        character_id.startswith("BalhaeMo")
        or character_id.startswith("korean_baek_daeheung_")
        for character_id in introduced_duplicates
    )
    status = (
        "do_not_merge_yet"
        if introduced_severity["blocker"] or introduced_duplicates
        else "no_new_lineage_blocker"
    )
    lines = [
        "# Bekleyen Asıl Mod Character Lineage Auditi",
        "",
        "## Revisionlar",
        "",
        f"- Taban: {base}",
        f"- Güncel asıl mod: {upstream}",
        "",
        "## Sonuç",
        "",
        f"- Merge durumu: {status}",
        f"- Değişen character dosyası: {len(changed_paths)}",
        f"- İçeriği değişen character kimliği: {len(changed_ids)}",
        f"- Yeni lineage blocker satırı: {introduced_severity['blocker']}",
        f"- Mevcut Tiger blocker köküyle örtüşen satır: {introduced_overlap}",
        f"- Yeni bağımsız lineage blocker satırı: {independent_blockers}",
        f"- Yeni bağımsız lineage blocker kök ailesi: {len(independent_blocker_roots)}",
        f"- Yeni bağımsız yalnız-review lineage kök ailesi: {len(independent_review_roots)}",
        f"- Yeni lineage review: {introduced_severity['review']}",
        f"- İlişkili inherited bulgu: {inherited_total}",
        f"- Çözülen eski bulgu: {directions['resolved']}",
        f"- Yeni duplicate character kimliği: {len(introduced_duplicates)}",
        f"- Mevcut Tiger identity köküyle örtüşen duplicate: {duplicate_overlap}",
        "- Otomatik uygulama: hayır",
        "",
        "## Yeni Bulgu Sınıfları",
        "",
    ]
    if introduced_classes:
        lines.extend(
            f"- {key}: {value}" for key, value in sorted(introduced_classes.items())
        )
    else:
        lines.append("- Yeni lineage bulgusu yok.")
    lines.extend(
        [
            "",
            "## Kapsam",
            "",
            "- Parent/child doğum sırası, ebeveyn ölüm sınırı, aşırı ebeveyn yaşı ve add_spouse yaşam durumu denetlendi.",
            "- Aynı semantik bulgu tabanda da varsa yeni upstream hatası sayılmadı.",
            "- Duplicate character kimlikleri sayıldı; ayrıntılı çözüm kanıtı Tiger kök raporunda tutulur.",
            "- Bu audit tarihsel doğruluk kaynağı değildir; yalnız engine ve yaşam-zinciri çelişkilerini saptar.",
            "",
            "## Değişen Dosyalar",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in changed_paths)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.repo_root = args.repo_root.resolve()
    args.output_dir = args.output_dir.resolve()
    base = common.resolve_revision(args.repo_root, args.base_revision)
    upstream = common.resolve_revision(args.repo_root, args.upstream_revision)
    ancestry = common.run_git(
        args.repo_root, "merge-base", "--is-ancestor", base, upstream, check=False
    )
    if ancestry.returncode != 0:
        raise RuntimeError("base revision is not an ancestor of upstream revision")

    changed_paths = [
        line
        for line in common.run_git(
            args.repo_root,
            "diff",
            "--name-only",
            base,
            upstream,
            "--",
            "BookmarksGit/history/characters",
        )
        .stdout.decode("utf-8", errors="strict")
        .splitlines()
        if line.lower().endswith(".txt")
    ]
    if not changed_paths:
        raise RuntimeError("no changed character history paths")

    vanilla_texts = runtime.read_layer_texts(
        args.vanilla_game_root.resolve(), "history/characters", "vanilla"
    )
    base_mod_texts = runtime.read_git_texts(
        args.repo_root, base, "history/characters", "base"
    )
    upstream_mod_texts = runtime.read_git_texts(
        args.repo_root, upstream, "history/characters", "upstream"
    )
    base_snapshot = build_snapshot(base_mod_texts, vanilla_texts)
    upstream_snapshot = build_snapshot(upstream_mod_texts, vanilla_texts)
    changed_ids = {
        character_id
        for character_id in (
            set(base_snapshot.mod_fingerprints)
            | set(upstream_snapshot.mod_fingerprints)
        )
        if base_snapshot.mod_fingerprints.get(character_id)
        != upstream_snapshot.mod_fingerprints.get(character_id)
    }
    if not changed_ids:
        raise RuntimeError("changed character paths produced no changed character IDs")

    base_findings = analyze_snapshot(base_snapshot)
    upstream_findings = analyze_snapshot(upstream_snapshot)
    rows = scoped_rows(
        base_findings,
        upstream_findings,
        changed_ids,
        base_snapshot,
        upstream_snapshot,
    )
    introduced_duplicates = {
        character_id
        for character_id, count in upstream_snapshot.duplicate_counts.items()
        if count > 1 and base_snapshot.duplicate_counts.get(character_id, 0) <= 1
        and character_id in changed_ids
    }

    if any(row["auto_apply"] != "no" for row in rows):
        raise RuntimeError("lineage audit emitted an auto-apply row")
    unclassified_blockers = [
        row
        for row in rows
        if row["direction"] == "introduced"
        and row["effective_severity"] == "blocker"
        and not row["existing_root_overlap"]
        and not row["lineage_root_id"]
    ]
    if unclassified_blockers:
        raise RuntimeError(
            f"{len(unclassified_blockers)} introduced blockers lack a root classification"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    findings_path = args.output_dir / "pending_upstream_character_lineage_findings.csv"
    duplicate_path = (
        args.output_dir / "pending_upstream_character_duplicate_identities.csv"
    )
    summary_path = args.output_dir / "pending_upstream_character_lineage_summary.md"
    manifest_path = args.output_dir / "input_revision_manifest.csv"
    common.write_csv(findings_path, rows, OUTPUT_FIELDS)
    duplicate_rows = []
    for character_id in sorted(introduced_duplicates):
        overlap = ""
        if character_id.startswith("BalhaeMo"):
            overlap = "balhae_mo_identity_collision"
        elif character_id.startswith("korean_baek_daeheung_"):
            overlap = "korean_baek_daeheung_identity_collision"
        duplicate_rows.append(
            {
                "character_id": character_id,
                "base_block_count": str(
                    base_snapshot.duplicate_counts.get(
                        character_id,
                        1 if character_id in base_snapshot.records else 0,
                    )
                ),
                "upstream_block_count": str(
                    upstream_snapshot.duplicate_counts.get(
                        character_id,
                        1 if character_id in upstream_snapshot.records else 0,
                    )
                ),
                "existing_root_overlap": overlap,
                "classification": "introduced_duplicate_character_identity",
                "auto_apply": "no",
            }
        )
    common.write_csv(
        duplicate_path,
        duplicate_rows,
        [
            "character_id",
            "base_block_count",
            "upstream_block_count",
            "existing_root_overlap",
            "classification",
            "auto_apply",
        ],
    )
    common.write_csv(
        manifest_path,
        [
            {"input": "base_revision", "value": base},
            {"input": "upstream_revision", "value": upstream},
            {
                "input": "changed_character_paths",
                "value": ";".join(changed_paths),
            },
            {
                "input": "vanilla_game_root",
                "value": str(args.vanilla_game_root.resolve()),
            },
        ],
        ["input", "value"],
    )
    write_summary(
        summary_path,
        base=base,
        upstream=upstream,
        changed_paths=changed_paths,
        changed_ids=changed_ids,
        rows=rows,
        introduced_duplicates=introduced_duplicates,
    )

    introduced = [row for row in rows if row["direction"] == "introduced"]
    introduced_severity = Counter(row["effective_severity"] for row in introduced)
    print(f"base_revision={base}")
    print(f"upstream_revision={upstream}")
    print(f"changed_paths={len(changed_paths)}")
    print(f"changed_character_ids={len(changed_ids)}")
    print(f"introduced_blockers={introduced_severity['blocker']}")
    print(f"introduced_reviews={introduced_severity['review']}")
    print(
        "related_inherited="
        f"{sum(row['direction'].startswith('related_inherited') for row in rows)}"
    )
    print(f"resolved={sum(row['direction'] == 'resolved' for row in rows)}")
    print(f"introduced_duplicate_ids={len(introduced_duplicates)}")
    print("auto_apply=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
