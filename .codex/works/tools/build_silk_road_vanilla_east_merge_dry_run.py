from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import audit_repo_semantic_compatibility as semantic


CURRENT_PATH = Path("BookmarksGit/common/connection_arrows/silk_road_arrows.txt")
DEFINITION_PATH = Path("BookmarksGit/map_data/definition.csv")
MOD_TRACKING_PATH = Path(
    ".codex/works/analysis/generated/province_definition/final_modlu_tracking_preserve_old_ids.csv"
)
VANILLA_TRACKING_PATH = Path(
    ".codex/works/analysis/generated/province_definition/final_orijinal_tracking_preserve_old_ids.csv"
)
OUTPUT_PATH = Path(
    ".codex/works/analysis/generated/repo_integration_closure/"
    "silk_road_vanilla_east_merge"
)
DEFAULT_ASIL_MOD_ROOT = (
    Path(__file__).resolve().parents[3].parent / "Leviathonlx MoreBookmarks-Plus"
)
DEFAULT_VANILLA_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
)

HEADER_RE = re.compile(r"^\s*([A-Za-z0-9_\-]+)\s*=\s*\{")
PROVINCES_RE = re.compile(r"^\s*provinces\s*=\s*\{")
NUMBER_RE = re.compile(r"\b\d+\b")


@dataclass(frozen=True)
class ArrowBlock:
    name: str
    start: int
    end: int
    lines: tuple[str, ...]
    province_ids: tuple[int, ...]


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a dry-run Silk Road merge using vanilla for the east"
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument("--asil-mod-root", type=Path, default=DEFAULT_ASIL_MOD_ROOT)
    parser.add_argument("--vanilla-root", type=Path, default=DEFAULT_VANILLA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def code_part(line: str) -> str:
    return line.split("#", 1)[0]


def brace_delta(line: str) -> int:
    code = code_part(line)
    return code.count("{") - code.count("}")


def extract_province_ids(lines: tuple[str, ...] | list[str]) -> tuple[int, ...]:
    result: list[int] = []
    in_provinces = False
    provinces_depth = 0
    for line in lines:
        code = code_part(line)
        if not in_provinces:
            match = PROVINCES_RE.match(code)
            if not match:
                continue
            in_provinces = True
            provinces_depth = brace_delta(code)
            result.extend(int(value) for value in NUMBER_RE.findall(code[match.end():]))
            if provinces_depth <= 0:
                in_provinces = False
            continue
        result.extend(int(value) for value in NUMBER_RE.findall(code))
        provinces_depth += brace_delta(code)
        if provinces_depth <= 0:
            in_provinces = False
    return tuple(result)


def parse_arrow_blocks(text: str) -> list[ArrowBlock]:
    lines = semantic.normalize_text(text).splitlines(keepends=True)
    blocks: list[ArrowBlock] = []
    active_name = ""
    active_start = -1
    active_depth = 0
    for index, line in enumerate(lines):
        if active_start < 0:
            match = HEADER_RE.match(code_part(line))
            if not match or match.group(1) == "provinces":
                continue
            active_name = match.group(1)
            active_start = index
            active_depth = brace_delta(line)
            if active_depth <= 0:
                raise RuntimeError(f"Invalid arrow header at line {index + 1}")
            continue
        active_depth += brace_delta(line)
        if active_depth < 0:
            raise RuntimeError(
                f"Brace depth below zero in {active_name} at line {index + 1}"
            )
        if active_depth == 0:
            block_lines = tuple(lines[active_start:index + 1])
            blocks.append(
                ArrowBlock(
                    active_name,
                    active_start,
                    index + 1,
                    block_lines,
                    extract_province_ids(block_lines),
                )
            )
            active_name = ""
            active_start = -1
    if active_start >= 0:
        raise RuntimeError(f"Unclosed arrow block: {active_name}")
    duplicates = sorted(
        name for name, count in Counter(block.name for block in blocks).items()
        if count > 1
    )
    if duplicates:
        raise RuntimeError(f"Duplicate arrow blocks: {', '.join(duplicates)}")
    return blocks


def rewrite_province_ids(
    lines: tuple[str, ...], mapping: dict[int, int]
) -> tuple[str, ...]:
    result: list[str] = []
    in_provinces = False
    provinces_depth = 0
    for line in lines:
        if "#" in line:
            code, comment = line.split("#", 1)
            suffix = "#" + comment
        else:
            code, suffix = line, ""
        if not in_provinces:
            if not PROVINCES_RE.match(code):
                result.append(line)
                continue
            in_provinces = True
            provinces_depth = brace_delta(code)
        else:
            provinces_depth += brace_delta(code)
        code = NUMBER_RE.sub(
            lambda match: str(mapping.get(int(match.group(0)), int(match.group(0)))),
            code,
        )
        result.append(code + suffix)
        if provinces_depth <= 0:
            in_provinces = False
    return tuple(result)


def load_tracking(path: Path) -> dict[int, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = {
            int(row["old_id"]): {
                key: (value or "").strip() for key, value in row.items()
            }
            for row in csv.DictReader(handle)
            if (row.get("old_id") or "").isdigit()
        }
    if not rows:
        raise RuntimeError(f"No tracking rows loaded from {path}")
    return rows


def tracking_matches_source(
    province_id: int,
    tracking: dict[int, dict[str, str]],
    source_definition: dict[int, dict[str, object]],
) -> bool:
    row = tracking.get(province_id)
    source = source_definition.get(province_id)
    if not row or not source:
        return False
    old_rgb = row.get("old_rgb", "").replace(" ", "")
    source_rgb = str(source["rgb_text"]).replace(" ", "")
    return old_rgb == source_rgb and row.get("old_name", "") == str(source["name"])


def mapped_id(
    province_id: int,
    tracking: dict[int, dict[str, str]],
    source_definition: dict[int, dict[str, object]],
) -> int:
    if not tracking_matches_source(province_id, tracking, source_definition):
        return province_id
    value = tracking[province_id].get("final_new_id", "")
    return int(value) if value.isdigit() else province_id


def classify_block(
    current: ArrowBlock,
    vanilla: ArrowBlock | None,
    mod_tracking: dict[int, dict[str, str]],
    vanilla_tracking: dict[int, dict[str, str]],
    asil_definition: dict[int, dict[str, object]],
    vanilla_definition: dict[int, dict[str, object]],
) -> tuple[str, str, int, int]:
    current_mod_count = sum(
        tracking_matches_source(item, mod_tracking, asil_definition)
        for item in current.province_ids
    )
    vanilla_east_count = (
        sum(
            tracking_matches_source(item, vanilla_tracking, vanilla_definition)
            for item in vanilla.province_ids
        )
        if vanilla
        else 0
    )
    if vanilla is None:
        if current_mod_count == len(current.province_ids):
            return (
                "keep_asil_mod_kalan",
                "asıl modda kalan rota; vanilla karşılığı yok",
                current_mod_count,
                vanilla_east_count,
            )
        if current_mod_count == 0:
            return (
                "drop_asil_mod_east_only",
                "yalnız kaldırılmış asıl mod doğu haritasına ait",
                current_mod_count,
                vanilla_east_count,
            )
        return (
            "manual_mixed",
            "vanilla karşılığı olmayan karışık sınır rotası",
            current_mod_count,
            vanilla_east_count,
        )
    if current_mod_count == 0 and vanilla_east_count == len(vanilla.province_ids):
        return (
            "replace_with_mapped_vanilla",
            "doğu rotası mapped vanilla kaynağından alınır",
            current_mod_count,
            vanilla_east_count,
        )
    if (
        current_mod_count == len(current.province_ids)
        and vanilla_east_count == 0
    ):
        return (
            "keep_asil_mod_kalan",
            "iki kaynakta da doğu dışı rota; mevcut sürüm korunur",
            current_mod_count,
            vanilla_east_count,
        )
    return (
        "manual_mixed",
        "doğu ve doğu dışı segmentler aynı blokta karışık",
        current_mod_count,
        vanilla_east_count,
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_candidate(path: Path, text: str, newline: str, with_bom: bool) -> None:
    encoded = text.replace("\n", newline).encode("utf-8")
    if with_bom:
        encoded = b"\xef\xbb\xbf" + encoded
    path.write_bytes(encoded)


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    asil_mod_root = args.asil_mod_root.resolve()
    vanilla_root = args.vanilla_root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else (repo_root / OUTPUT_PATH).resolve()
    )

    current_path = repo_root / CURRENT_PATH
    vanilla_path = vanilla_root / "common/connection_arrows/silk_road_arrows.txt"
    current_definition_path = repo_root / DEFINITION_PATH
    asil_definition_path = asil_mod_root / "BookmarksGit/map_data/definition.csv"
    vanilla_definition_path = vanilla_root / "map_data/definition.csv"
    mod_tracking_path = repo_root / MOD_TRACKING_PATH
    vanilla_tracking_path = repo_root / VANILLA_TRACKING_PATH

    required = (
        current_path,
        vanilla_path,
        current_definition_path,
        asil_definition_path,
        vanilla_definition_path,
        mod_tracking_path,
        vanilla_tracking_path,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required files:\n" + "\n".join(missing))

    current_bytes = current_path.read_bytes()
    with_bom = current_bytes.startswith(b"\xef\xbb\xbf")
    newline = "\r\n" if b"\r\n" in current_bytes else "\n"
    current_text = current_bytes.decode("utf-8-sig")
    vanilla_text = vanilla_path.read_text(encoding="utf-8-sig")

    current_blocks = parse_arrow_blocks(current_text)
    vanilla_blocks = parse_arrow_blocks(vanilla_text)
    current_by_name = {block.name: block for block in current_blocks}
    vanilla_by_name = {block.name: block for block in vanilla_blocks}

    current_definition = semantic.parse_definition(
        current_definition_path.read_text(encoding="utf-8-sig")
    )
    asil_definition = semantic.parse_definition(
        asil_definition_path.read_text(encoding="utf-8-sig")
    )
    vanilla_definition = semantic.parse_definition(
        vanilla_definition_path.read_text(encoding="utf-8-sig")
    )
    mod_tracking = load_tracking(mod_tracking_path)
    vanilla_tracking = load_tracking(vanilla_tracking_path)
    mod_mapping = {
        province_id: mapped_id(province_id, mod_tracking, asil_definition)
        for province_id in mod_tracking
    }
    vanilla_mapping = {
        province_id: mapped_id(
            province_id, vanilla_tracking, vanilla_definition
        )
        for province_id in vanilla_tracking
    }

    block_rows: list[dict[str, str]] = []
    reference_rows: list[dict[str, str]] = []
    replacements: dict[str, tuple[str, ...]] = {}

    for current in current_blocks:
        vanilla = vanilla_by_name.get(current.name)
        action, reason, current_mod_count, vanilla_east_count = classify_block(
            current,
            vanilla,
            mod_tracking,
            vanilla_tracking,
            asil_definition,
            vanilla_definition,
        )
        if action == "keep_asil_mod_kalan":
            replacement = rewrite_province_ids(current.lines, mod_mapping)
            candidate_source = "current_asil_mod"
        elif action == "replace_with_mapped_vanilla":
            if vanilla is None:
                raise RuntimeError(f"Missing vanilla block for {current.name}")
            replacement = rewrite_province_ids(vanilla.lines, vanilla_mapping)
            candidate_source = "mapped_vanilla"
        elif action == "drop_asil_mod_east_only":
            replacement = ()
            candidate_source = "removed"
        else:
            replacement = current.lines
            candidate_source = "current_unchanged_pending_manual_review"
        replacements[current.name] = replacement

        candidate_ids = extract_province_ids(replacement)
        block_rows.append(
            {
                "arrow": current.name,
                "current_line": str(current.start + 1),
                "vanilla_line": str(vanilla.start + 1) if vanilla else "",
                "current_reference_count": str(len(current.province_ids)),
                "current_modlu_kalan_count": str(current_mod_count),
                "current_removed_east_count": str(
                    len(current.province_ids) - current_mod_count
                ),
                "vanilla_reference_count": str(
                    len(vanilla.province_ids) if vanilla else 0
                ),
                "vanilla_east_count": str(vanilla_east_count),
                "vanilla_outside_east_count": str(
                    len(vanilla.province_ids) - vanilla_east_count
                    if vanilla
                    else 0
                ),
                "action": action,
                "automatic": "no" if action == "manual_mixed" else "yes",
                "candidate_source": candidate_source,
                "reason": reason,
                "current_ids": " ".join(map(str, current.province_ids)),
                "vanilla_ids": (
                    " ".join(map(str, vanilla.province_ids)) if vanilla else ""
                ),
                "candidate_ids": " ".join(map(str, candidate_ids)),
            }
        )

        for sequence, province_id in enumerate(current.province_ids, start=1):
            emitted = action in {"keep_asil_mod_kalan", "manual_mixed"}
            target = (
                mapped_id(province_id, mod_tracking, asil_definition)
                if action == "keep_asil_mod_kalan"
                else province_id
            )
            reference_rows.append(
                {
                    "arrow": current.name,
                    "block_action": action,
                    "source": "current_asil_mod",
                    "source_sequence": str(sequence),
                    "source_province_id": str(province_id),
                    "source_name": str(
                        asil_definition.get(province_id, {}).get("name", "")
                    ),
                    "source_classification": (
                        "modlu_kalan"
                        if tracking_matches_source(
                            province_id, mod_tracking, asil_definition
                        )
                        else "removed_asil_mod_east"
                    ),
                    "target_province_id": str(target) if emitted else "",
                    "target_name": (
                        str(current_definition.get(target, {}).get("name", ""))
                        if emitted else ""
                    ),
                    "id_changed": (
                        "yes" if emitted and target != province_id else "no"
                    ),
                    "emitted_in_candidate": "yes" if emitted else "no",
                }
            )

        if vanilla is None:
            continue
        for sequence, province_id in enumerate(vanilla.province_ids, start=1):
            emitted = action == "replace_with_mapped_vanilla"
            target = mapped_id(
                province_id, vanilla_tracking, vanilla_definition
            )
            reference_rows.append(
                {
                    "arrow": current.name,
                    "block_action": action,
                    "source": "vanilla",
                    "source_sequence": str(sequence),
                    "source_province_id": str(province_id),
                    "source_name": str(
                        vanilla_definition.get(province_id, {}).get("name", "")
                    ),
                    "source_classification": (
                        "orijinal_dogu"
                        if tracking_matches_source(
                            province_id,
                            vanilla_tracking,
                            vanilla_definition,
                        )
                        else "vanilla_outside_east"
                    ),
                    "target_province_id": str(target) if emitted else "",
                    "target_name": (
                        str(current_definition.get(target, {}).get("name", ""))
                        if emitted else ""
                    ),
                    "id_changed": (
                        "yes" if emitted and target != province_id else "no"
                    ),
                    "emitted_in_candidate": "yes" if emitted else "no",
                }
            )

    normalized_current = semantic.normalize_text(current_text)
    candidate_lines = normalized_current.splitlines(keepends=True)
    for block in reversed(current_blocks):
        candidate_lines[block.start:block.end] = replacements[block.name]
    candidate_text = "".join(candidate_lines)
    candidate_blocks = parse_arrow_blocks(candidate_text)
    candidate_by_name = {block.name: block for block in candidate_blocks}

    validation_issues: list[str] = []
    for row in block_rows:
        name = row["arrow"]
        action = row["action"]
        candidate = candidate_by_name.get(name)
        if action == "drop_asil_mod_east_only":
            if candidate is not None:
                validation_issues.append(f"{name}: dropped block still present")
            continue
        if candidate is None:
            validation_issues.append(f"{name}: candidate block missing")
            continue
        expected = extract_province_ids(replacements[name])
        if candidate.province_ids != expected:
            validation_issues.append(f"{name}: candidate sequence mismatch")
        if (
            action == "manual_mixed"
            and candidate.lines != current_by_name[name].lines
        ):
            validation_issues.append(f"{name}: manual block changed")
        for province_id in candidate.province_ids:
            if province_id not in current_definition:
                validation_issues.append(
                    f"{name}: target province {province_id} missing in current definition"
                )
    if validation_issues:
        raise RuntimeError(
            "Candidate validation failed:\n" + "\n".join(validation_issues)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    block_report = output_dir / "silk_road_block_merge_plan.csv"
    reference_report = output_dir / "silk_road_reference_merge_plan.csv"
    candidate_path = output_dir / "silk_road_arrows_vanilla_east_candidate.txt"
    patch_path = output_dir / "silk_road_vanilla_east_candidate.patch"
    summary_path = output_dir / "silk_road_vanilla_east_merge_summary.md"

    semantic.write_csv(block_report, block_rows)
    semantic.write_csv(reference_report, reference_rows)
    write_candidate(candidate_path, candidate_text, newline, with_bom)
    patch_text = "".join(
        difflib.unified_diff(
            normalized_current.splitlines(keepends=True),
            candidate_text.splitlines(keepends=True),
            fromfile=f"a/{CURRENT_PATH.as_posix()}",
            tofile=f"b/{CURRENT_PATH.as_posix()}",
        )
    )
    patch_path.write_text(patch_text, encoding="utf-8")

    actions = Counter(row["action"] for row in block_rows)
    current_ref_count = sum(len(block.province_ids) for block in current_blocks)
    vanilla_ref_count = sum(len(block.province_ids) for block in vanilla_blocks)
    current_mod_count = sum(
        tracking_matches_source(item, mod_tracking, asil_definition)
        for block in current_blocks
        for item in block.province_ids
    )
    vanilla_east_count = sum(
        tracking_matches_source(item, vanilla_tracking, vanilla_definition)
        for block in vanilla_blocks
        for item in block.province_ids
    )
    emitted_rows = [
        row for row in reference_rows
        if row["emitted_in_candidate"] == "yes"
    ]
    changed_targets = sum(row["id_changed"] == "yes" for row in emitted_rows)
    manual_names = [
        row["arrow"] for row in block_rows if row["action"] == "manual_mixed"
    ]
    summary = "\n".join(
        [
            "# Silk Road vanilla-east dry-run summary",
            "",
            "## Scope",
            "",
            f"- Live file: {CURRENT_PATH.as_posix()}",
            f"- Vanilla source: {vanilla_path}",
            f"- Asıl mod semantic source: {asil_definition_path}",
            "- Live file changed: no",
            "",
            "## Classification",
            "",
            f"- Current blocks: {len(current_blocks)}",
            f"- Vanilla blocks: {len(vanilla_blocks)}",
            f"- Common blocks: {len(set(current_by_name) & set(vanilla_by_name))}",
            f"- keep_asil_mod_kalan: {actions['keep_asil_mod_kalan']}",
            f"- replace_with_mapped_vanilla: {actions['replace_with_mapped_vanilla']}",
            f"- drop_asil_mod_east_only: {actions['drop_asil_mod_east_only']}",
            f"- manual_mixed: {actions['manual_mixed']}",
            "",
            "## Reference provenance",
            "",
            f"- Current references: {current_ref_count}",
            f"- Current modlu_kalan references: {current_mod_count}",
            f"- Current removed east references: {current_ref_count - current_mod_count}",
            f"- Vanilla references: {vanilla_ref_count}",
            f"- Vanilla east references: {vanilla_east_count}",
            f"- Vanilla outside-east references: {vanilla_ref_count - vanilla_east_count}",
            f"- Candidate emitted references: {len(emitted_rows)}",
            f"- Candidate emitted ID rewrites: {changed_targets}",
            "",
            "## Validation",
            "",
            "- Candidate parse: pass",
            "- Candidate target IDs in current definition.csv: pass",
            "- Automatic replace/drop decisions: pass",
            "- Mixed boundary blocks unchanged: pass",
            f"- Live file SHA-256: {sha256_bytes(current_bytes)}",
            "",
            "## Manual mixed blocks",
            "",
            *[f"- {name}" for name in manual_names],
            "",
            "No live CK3 file was edited by this dry-run.",
            "",
        ]
    )
    summary_path.write_text(summary, encoding="utf-8")

    print(f"output_dir={output_dir}")
    print(f"live_sha256={sha256_bytes(current_bytes)}")
    print(f"candidate_sha256={sha256_bytes(candidate_path.read_bytes())}")
    print(
        "actions="
        + ",".join(f"{key}:{actions[key]}" for key in sorted(actions))
    )
    print(f"candidate_blocks={len(candidate_blocks)}")
    print(f"candidate_references={len(emitted_rows)}")
    print(f"candidate_id_rewrites={changed_targets}")
    print("validation=pass")
    print("live_file_changed=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
