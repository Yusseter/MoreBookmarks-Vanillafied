from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from audit_landed_title_source_identity import (
    parse_landed_titles_path,
    read_mask_province_ids,
)


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    mod_root = project_root / "BookmarksGit"
    works_root = project_root / "development"
    parser = argparse.ArgumentParser(
        description="Build an east audit scope by expanding mask-hit baronies to their current k_ title closure."
    )
    parser.add_argument(
        "--landed-titles",
        type=Path,
        default=mod_root / "common/landed_titles/00_landed_titles.txt",
    )
    parser.add_argument(
        "--definition",
        type=Path,
        default=mod_root / "map_data/definition.csv",
    )
    parser.add_argument(
        "--east-mask",
        type=Path,
        default=(
            works_root
            / "pipeline_inputs/map/scopes/east_title_scope_2026-04-19.png"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=works_root / "analysis/generated/east_kingdom_closure_scope",
    )
    parser.add_argument(
        "--closure-tier",
        choices=["k", "e"],
        default="k",
        help="Ancestor tier to expand under. k keeps kingdom closure; e expands empire/hegemony closure.",
    )
    return parser.parse_args()


def tier(title_id: str) -> str:
    return title_id.split("_", 1)[0]


def path_parts(path: str) -> list[str]:
    return [part.strip() for part in path.split(">")]


def first_closure_ancestor(path: str, closure_tier: str) -> str:
    prefix = f"{closure_tier}_"
    for part in path_parts(path):
        if part.startswith(prefix):
            return part
    return ""


def is_under_ancestor(path: str, ancestor_id: str) -> bool:
    parts = path_parts(path)
    return ancestor_id in parts


def build_scope(args: argparse.Namespace) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int | str]]:
    blocks = parse_landed_titles_path(args.landed_titles)
    mask_province_ids, mask_rgb_count, unmatched_rgb_count = read_mask_province_ids(args.east_mask, args.definition)

    seed_rows: list[dict[str, str]] = []
    ancestor_to_seed_provinces: dict[str, set[int]] = defaultdict(set)
    ancestor_to_seed_baronies: dict[str, set[str]] = defaultdict(set)
    no_ancestor_seed_count = 0

    for block in blocks.values():
        if not block.title_id.startswith("b_"):
            continue
        hit_ids = sorted(set(block.direct_province_ids) & mask_province_ids)
        if not hit_ids:
            continue
        ancestor_id = first_closure_ancestor(block.path, args.closure_tier)
        if not ancestor_id:
            no_ancestor_seed_count += 1
        else:
            ancestor_to_seed_provinces[ancestor_id].update(hit_ids)
            ancestor_to_seed_baronies[ancestor_id].add(block.title_id)
        seed_rows.append(
            {
                "barony_id": block.title_id,
                "barony_path": block.path,
                "barony_line": str(block.start_line),
                "closure_ancestor_id": ancestor_id,
                "mask_province_ids": " ".join(str(value) for value in hit_ids),
            }
        )

    closure_rows: list[dict[str, str]] = []
    for block in sorted(blocks.values(), key=lambda item: item.start_line):
        ancestor_ids = [
            ancestor_id for ancestor_id in ancestor_to_seed_provinces if is_under_ancestor(block.path, ancestor_id)
        ]
        if not ancestor_ids:
            continue
        ancestor_id = ancestor_ids[0]
        direct_hit_ids = sorted(set(block.direct_province_ids) & mask_province_ids)
        descendant_hit_ids = sorted(set(block.descendant_province_ids) & mask_province_ids)
        closure_rows.append(
            {
                "title_id": block.title_id,
                "tier": tier(block.title_id),
                "parent_id": block.parent_id,
                "closure_tier": args.closure_tier,
                "closure_ancestor_id": ancestor_id,
                "path": block.path,
                "line": str(block.start_line),
                "closure_reason": f"{args.closure_tier}_closure_from_mask_barony",
                "direct_mask_province_ids": " ".join(str(value) for value in direct_hit_ids),
                "descendant_mask_province_count": str(len(descendant_hit_ids)),
                "seed_barony_count_for_ancestor": str(len(ancestor_to_seed_baronies[ancestor_id])),
                "seed_province_count_for_ancestor": str(len(ancestor_to_seed_provinces[ancestor_id])),
            }
        )

    metadata: dict[str, int | str] = {
        "mask_rgb_count": mask_rgb_count,
        "mask_province_count": len(mask_province_ids),
        "mask_unmatched_rgb_count": unmatched_rgb_count,
        "seed_barony_count": len(seed_rows),
        "closure_tier": args.closure_tier,
        "closure_ancestor_count": len(ancestor_to_seed_provinces),
        "closure_title_count": len(closure_rows),
        "no_ancestor_seed_count": no_ancestor_seed_count,
        "closure_ancestors": " ".join(sorted(ancestor_to_seed_provinces)),
    }
    return closure_rows, seed_rows, metadata


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(output_dir: Path, closure_rows: list[dict[str, str]], seed_rows: list[dict[str, str]], metadata: dict[str, int | str]) -> None:
    closure_fields = [
        "title_id",
        "tier",
        "parent_id",
        "closure_tier",
        "closure_ancestor_id",
        "path",
        "line",
        "closure_reason",
        "direct_mask_province_ids",
        "descendant_mask_province_count",
        "seed_barony_count_for_ancestor",
        "seed_province_count_for_ancestor",
    ]
    seed_fields = ["barony_id", "barony_path", "barony_line", "closure_ancestor_id", "mask_province_ids"]
    write_csv(output_dir / "east_kingdom_closure_titles.csv", closure_rows, closure_fields)
    write_csv(output_dir / "east_kingdom_closure_seed_baronies.csv", seed_rows, seed_fields)

    tier_counts = Counter(row["tier"] for row in closure_rows)
    lines = [
        "# East Kingdom Closure Scope",
        "",
        f"- mask non-black RGB: `{metadata['mask_rgb_count']}`",
        f"- mask province IDs: `{metadata['mask_province_count']}`",
        f"- mask unmatched RGB: `{metadata['mask_unmatched_rgb_count']}`",
        f"- closure tier: `{metadata['closure_tier']}`",
        f"- seed baronies: `{metadata['seed_barony_count']}`",
        f"- closure ancestors: `{metadata['closure_ancestor_count']}`",
        f"- closure titles: `{metadata['closure_title_count']}`",
        f"- seed baronies without closure ancestor: `{metadata['no_ancestor_seed_count']}`",
        "",
        "## Closure Title Tier Counts",
        "",
    ]
    for key, value in sorted(tier_counts.items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- closure titles: `east_kingdom_closure_titles.csv`",
            "- seed baronies: `east_kingdom_closure_seed_baronies.csv`",
            "",
            "## Closure Ancestors",
            "",
            f"`{metadata['closure_ancestors']}`",
        ]
    )
    (output_dir / "east_kingdom_closure_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    closure_rows, seed_rows, metadata = build_scope(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_outputs(args.output_dir, closure_rows, seed_rows, metadata)
    print(f"closure_titles={metadata['closure_title_count']}")
    print(f"closure_ancestors={metadata['closure_ancestor_count']}")
    print(f"seed_baronies={metadata['seed_barony_count']}")
    print(f"summary={args.output_dir / 'east_kingdom_closure_summary.md'}")


if __name__ == "__main__":
    main()
