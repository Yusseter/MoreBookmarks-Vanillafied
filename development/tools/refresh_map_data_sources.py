from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops


REVISION = 1
BLACK = (0, 0, 0)

TARGET_FILES = {
    "provinces_modlu": "provinces_modlu.png",
    "provinces_orijinal": "provinces_orijinal.png",
    "provinces_modlu_dogu": "provinces_modlu_dogu.png",
    "provinces_modlu_kalan": "provinces_modlu_kalan.png",
    "provinces_orijinal_dogu": "provinces_orijinal_dogu.png",
    "provinces_orijinal_kalan": "provinces_orijinal_kalan.png",
    "provinces_birlesim": "provinces_birlesim.png",
}

MASK_FILES = {
    "provinces_modlu_dogu": "provinces_modlu_dogu_mask.png",
    "provinces_modlu_kalan": "provinces_modlu_kalan_mask.png",
    "provinces_orijinal_dogu": "provinces_orijinal_dogu_mask.png",
    "provinces_orijinal_kalan": "provinces_orijinal_kalan_mask.png",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh development map source PNGs from the workspace's upstream and "
            "vanilla maps without changing the live BookmarksGit map."
        )
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Multi-root .code-workspace file. Defaults to the project workspace.",
    )
    parser.add_argument(
        "--upstream-map",
        type=Path,
        help="Explicit upstream provinces.png path.",
    )
    parser.add_argument(
        "--vanilla-map",
        type=Path,
        help="Explicit vanilla provinces.png path.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Generated preview/report directory.",
    )
    parser.add_argument(
        "--bootstrap-masks",
        action="store_true",
        help="Create missing black/white masks from the current subset PNGs.",
    )
    parser.add_argument(
        "--force-bootstrap-masks",
        action="store_true",
        help="Replace existing masks from the current subset PNGs.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update only development/map_data_sources PNGs after validation.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Return exit code 1 when source PNGs differ; no effect with --apply.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_workspace_roots(workspace: Path) -> dict[str, Path]:
    data = json.loads(workspace.read_text(encoding="utf-8-sig"))
    roots: dict[str, Path] = {}
    for entry in data.get("folders", []):
        name = entry.get("name")
        raw_path = entry.get("path")
        if not name or not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = workspace.parent / path
        roots[str(name)] = path.resolve()
    return roots


def require_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} not found: {resolved}")
    return resolved


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def load_rgb(path: Path, expected_size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        if source.size != expected_size:
            raise ValueError(
                f"Image size mismatch for {path}: {source.size} != {expected_size}"
            )
        return source.convert("RGB")


def load_mask(path: Path, expected_size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        if source.size != expected_size:
            raise ValueError(
                f"Mask size mismatch for {path}: {source.size} != {expected_size}"
            )
        mask = source.convert("L")

    histogram = mask.histogram()
    non_binary = sum(histogram[1:255])
    if non_binary:
        mask.close()
        raise ValueError(f"Mask contains {non_binary} non-binary pixels: {path}")
    return mask


def atomic_save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    image.save(temporary, format="PNG")
    os.replace(temporary, path)


def occupancy_mask(image: Image.Image) -> Image.Image:
    red, green, blue = image.split()
    red_green = ImageChops.lighter(red, green)
    occupied = ImageChops.lighter(red_green, blue)
    mask = occupied.point(lambda value: 255 if value else 0)
    red.close()
    green.close()
    blue.close()
    red_green.close()
    occupied.close()
    return mask


def bootstrap_masks(
    source_dir: Path,
    mask_dir: Path,
    force: bool,
) -> list[dict[str, Any]]:
    mask_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    for target_name, mask_name in MASK_FILES.items():
        source_path = require_file(
            source_dir / TARGET_FILES[target_name],
            f"bootstrap source for {target_name}",
        )
        mask_path = mask_dir / mask_name
        if mask_path.exists() and not force:
            rows.append(
                {
                    "target": target_name,
                    "mask": str(mask_path),
                    "action": "kept_existing",
                }
            )
            continue

        size = image_size(source_path)
        source = load_rgb(source_path, size)
        mask = occupancy_mask(source)
        atomic_save_png(mask, mask_path)
        source.close()
        mask.close()
        rows.append(
            {
                "target": target_name,
                "mask": str(mask_path),
                "action": "created" if not force else "replaced",
            }
        )

    return rows


def read_overrides(path: Path) -> dict[str, list[dict[str, Any]]]:
    required_columns = {
        "target",
        "x",
        "y",
        "expected_r",
        "expected_g",
        "expected_b",
        "replacement_r",
        "replacement_g",
        "replacement_b",
        "reason",
    }
    by_target: dict[str, list[dict[str, Any]]] = {
        name: [] for name in TARGET_FILES
    }
    seen: set[tuple[str, int, int]] = set()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required_columns.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"Override CSV is missing columns {sorted(missing)}: {path}"
            )

        for line_number, row in enumerate(reader, start=2):
            target = str(row["target"]).strip()
            if target not in TARGET_FILES:
                raise ValueError(
                    f"Unknown override target at {path}:{line_number}: {target}"
                )

            x = int(row["x"])
            y = int(row["y"])
            expected = tuple(
                int(row[column])
                for column in ("expected_r", "expected_g", "expected_b")
            )
            replacement = tuple(
                int(row[column])
                for column in (
                    "replacement_r",
                    "replacement_g",
                    "replacement_b",
                )
            )
            if x < 0 or y < 0:
                raise ValueError(f"Negative override coordinate at {path}:{line_number}")
            if any(value < 0 or value > 255 for value in expected + replacement):
                raise ValueError(f"Invalid RGB value at {path}:{line_number}")

            key = (target, x, y)
            if key in seen:
                raise ValueError(f"Duplicate override coordinate at {path}:{line_number}")
            seen.add(key)
            by_target[target].append(
                {
                    "line": line_number,
                    "x": x,
                    "y": y,
                    "expected": expected,
                    "replacement": replacement,
                    "reason": str(row["reason"]).strip(),
                }
            )

    return by_target


def apply_overrides(
    image: Image.Image,
    target_name: str,
    overrides: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    width, height = image.size
    pixels = image.load()

    for row in overrides[target_name]:
        x = int(row["x"])
        y = int(row["y"])
        if x >= width or y >= height:
            raise ValueError(
                f"Override coordinate outside {target_name}: ({x}, {y})"
            )

        current = tuple(pixels[x, y])
        expected = tuple(row["expected"])
        replacement = tuple(row["replacement"])
        if current not in (expected, replacement):
            raise ValueError(
                f"Source drift at {target_name} ({x}, {y}): "
                f"found {current}, expected {expected} or {replacement}"
            )

        pixels[x, y] = replacement
        applied.append(
            {
                "target": target_name,
                "x": x,
                "y": y,
                "source_rgb": list(current),
                "replacement_rgb": list(replacement),
                "reason": row["reason"],
            }
        )

    return applied


def masked_copy(source: Image.Image, mask_path: Path) -> Image.Image:
    mask = load_mask(mask_path, source.size)
    result = Image.new("RGB", source.size, BLACK)
    result.paste(source, (0, 0), mask)
    mask.close()
    return result


def write_candidate(
    candidate_dir: Path,
    target_name: str,
    image: Image.Image,
) -> Path:
    path = candidate_dir / TARGET_FILES[target_name]
    atomic_save_png(image, path)
    return path


def build_candidates(
    upstream_map: Path,
    vanilla_map: Path,
    source_dir: Path,
    mask_dir: Path,
    candidate_dir: Path,
    overrides: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Path], list[dict[str, Any]], dict[str, Any]]:
    expected_size = image_size(upstream_map)
    if image_size(vanilla_map) != expected_size:
        raise ValueError("Upstream and vanilla province maps have different sizes")

    masks: dict[str, Path] = {}
    mask_metadata: dict[str, Any] = {}
    for target_name, filename in MASK_FILES.items():
        path = require_file(mask_dir / filename, f"mask for {target_name}")
        mask = load_mask(path, expected_size)
        histogram = mask.histogram()
        mask_metadata[target_name] = {
            "path": str(path),
            "selected_pixels": histogram[255],
            "sha256": sha256_file(path),
        }
        mask.close()
        masks[target_name] = path

    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidates: dict[str, Path] = {}
    applied_overrides: list[dict[str, Any]] = []

    mod_map = load_rgb(upstream_map, expected_size)
    applied_overrides.extend(
        apply_overrides(mod_map, "provinces_modlu", overrides)
    )
    candidates["provinces_modlu"] = write_candidate(
        candidate_dir, "provinces_modlu", mod_map
    )
    for target_name in ("provinces_modlu_dogu", "provinces_modlu_kalan"):
        subset = masked_copy(mod_map, masks[target_name])
        applied_overrides.extend(apply_overrides(subset, target_name, overrides))
        candidates[target_name] = write_candidate(
            candidate_dir, target_name, subset
        )
        subset.close()
    mod_map.close()

    vanilla = load_rgb(vanilla_map, expected_size)
    applied_overrides.extend(
        apply_overrides(vanilla, "provinces_orijinal", overrides)
    )
    candidates["provinces_orijinal"] = write_candidate(
        candidate_dir, "provinces_orijinal", vanilla
    )
    for target_name in (
        "provinces_orijinal_dogu",
        "provinces_orijinal_kalan",
    ):
        subset = masked_copy(vanilla, masks[target_name])
        applied_overrides.extend(apply_overrides(subset, target_name, overrides))
        candidates[target_name] = write_candidate(
            candidate_dir, target_name, subset
        )
        subset.close()
    vanilla.close()

    west = load_rgb(candidates["provinces_modlu_kalan"], expected_size)
    east = load_rgb(candidates["provinces_orijinal_dogu"], expected_size)
    east_mask = load_mask(masks["provinces_orijinal_dogu"], expected_size)
    west.paste(east, (0, 0), east_mask)
    applied_overrides.extend(
        apply_overrides(west, "provinces_birlesim", overrides)
    )
    candidates["provinces_birlesim"] = write_candidate(
        candidate_dir, "provinces_birlesim", west
    )
    west.close()
    east.close()
    east_mask.close()

    west_mask = load_mask(masks["provinces_modlu_kalan"], expected_size)
    east_mask = load_mask(masks["provinces_orijinal_dogu"], expected_size)
    overlap = ImageChops.multiply(west_mask, east_mask)
    union = ImageChops.lighter(west_mask, east_mask)
    overlap_count = overlap.histogram()[255]
    union_count = union.histogram()[255]
    west_mask.close()
    east_mask.close()
    overlap.close()
    union.close()

    composition = {
        "width": expected_size[0],
        "height": expected_size[1],
        "final_mask_overlap_pixels": overlap_count,
        "final_mask_union_pixels": union_count,
        "final_mask_unselected_pixels": (
            expected_size[0] * expected_size[1] - union_count
        ),
        "masks": mask_metadata,
    }
    return candidates, applied_overrides, composition


def compare_images(
    current_path: Path,
    candidate_path: Path,
    diff_mask_path: Path,
) -> dict[str, Any]:
    candidate_size = image_size(candidate_path)
    if not current_path.exists():
        mask = Image.new("L", candidate_size, 255)
        atomic_save_png(mask, diff_mask_path)
        mask.close()
        return {
            "status": "missing",
            "changed_pixels": candidate_size[0] * candidate_size[1],
            "changed_bbox": [0, 0, candidate_size[0], candidate_size[1]],
            "current_sha256": None,
            "candidate_sha256": sha256_file(candidate_path),
        }

    if image_size(current_path) != candidate_size:
        raise ValueError(
            f"Current image size mismatch for {current_path}: "
            f"{image_size(current_path)} != {candidate_size}"
        )

    current = load_rgb(current_path, candidate_size)
    candidate = load_rgb(candidate_path, candidate_size)
    difference = ImageChops.difference(current, candidate)
    red, green, blue = difference.split()
    red_green = ImageChops.lighter(red, green)
    changed_values = ImageChops.lighter(red_green, blue)
    changed_mask = changed_values.point(lambda value: 255 if value else 0)
    histogram = changed_mask.histogram()
    changed_pixels = histogram[255]
    bbox = changed_mask.getbbox()
    atomic_save_png(changed_mask, diff_mask_path)

    current.close()
    candidate.close()
    difference.close()
    red.close()
    green.close()
    blue.close()
    red_green.close()
    changed_values.close()
    changed_mask.close()

    return {
        "status": "current" if changed_pixels == 0 else "changed",
        "changed_pixels": changed_pixels,
        "changed_bbox": list(bbox) if bbox else None,
        "current_sha256": sha256_file(current_path),
        "candidate_sha256": sha256_file(candidate_path),
    }


def apply_candidates(
    source_dir: Path,
    output_dir: Path,
    candidates: dict[str, Path],
    comparisons: dict[str, dict[str, Any]],
) -> list[str]:
    resolved_source_dir = source_dir.resolve()
    changed_names = [
        name
        for name, result in comparisons.items()
        if int(result["changed_pixels"]) > 0
    ]
    if not changed_names:
        return []

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = output_dir / "backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    for target_name in changed_names:
        target = (source_dir / TARGET_FILES[target_name]).resolve()
        if target.parent != resolved_source_dir:
            raise ValueError(f"Refusing to write outside source directory: {target}")

        if target.exists():
            shutil.copy2(target, backup_dir / target.name)

        temporary = target.with_name(f".{target.name}.refresh.tmp")
        shutil.copyfile(candidates[target_name], temporary)
        os.replace(temporary, target)

    return changed_names


def write_reports(
    output_dir: Path,
    manifest: dict[str, Any],
) -> None:
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Map Data Source Refresh",
        "",
        f"- mode: {manifest['mode']}",
        f"- upstream map: {manifest['sources']['upstream']['path']}",
        f"- vanilla map: {manifest['sources']['vanilla']['path']}",
        f"- size: {manifest['composition']['width']}x{manifest['composition']['height']}",
        f"- applied targets: {len(manifest['applied_targets'])}",
        "",
        "## Pixel Differences",
        "",
        "| Target | Status | Changed pixels | Bounding box |",
        "| --- | --- | ---: | --- |",
    ]
    for target_name in TARGET_FILES:
        result = manifest["comparisons"][target_name]
        bbox = result["changed_bbox"] or ""
        lines.append(
            f"| {target_name} | {result['status']} | "
            f"{result['changed_pixels']} | {bbox} |"
        )

    lines.extend(
        [
            "",
            "## Composition",
            "",
            (
                "- Final east/west mask overlap pixels: "
                f"{manifest['composition']['final_mask_overlap_pixels']}"
            ),
            (
                "- Final east/west mask union pixels: "
                f"{manifest['composition']['final_mask_union_pixels']}"
            ),
            (
                "- Final unselected pixels: "
                f"{manifest['composition']['final_mask_unselected_pixels']}"
            ),
            f"- Validated pixel overrides: {len(manifest['validated_overrides'])}",
            "",
            "The live BookmarksGit/map_data/provinces.png file was not written.",
            "",
        ]
    )
    (output_dir / "summary.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[2]
    workspace = (
        args.workspace.resolve()
        if args.workspace
        else project_root / "Yusseter-MBP-Development.code-workspace"
    )
    roots = read_workspace_roots(require_file(workspace, "workspace file"))

    upstream_map = (
        args.upstream_map.resolve()
        if args.upstream_map
        else roots["Upstream MBP"] / "BookmarksGit/map_data/provinces.png"
    )
    vanilla_map = (
        args.vanilla_map.resolve()
        if args.vanilla_map
        else roots["CK3 Vanilla"] / "map_data/provinces.png"
    )
    upstream_map = require_file(upstream_map, "upstream provinces map")
    vanilla_map = require_file(vanilla_map, "vanilla provinces map")

    source_dir = project_root / "development/map_data_sources"
    pipeline_map_dir = project_root / "development/pipeline_inputs/map"
    mask_dir = pipeline_map_dir / "masks"
    override_path = require_file(
        pipeline_map_dir / "source_pixel_overrides.csv",
        "source pixel overrides",
    )
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else project_root
        / "development/analysis/generated/map_data_source_refresh"
    )
    candidate_dir = output_dir / "candidates"
    diff_mask_dir = output_dir / "diff_masks"
    diff_mask_dir.mkdir(parents=True, exist_ok=True)

    bootstrap_rows: list[dict[str, Any]] = []
    if args.bootstrap_masks or args.force_bootstrap_masks:
        bootstrap_rows = bootstrap_masks(
            source_dir,
            mask_dir,
            force=args.force_bootstrap_masks,
        )

    missing_masks = [
        mask_dir / filename
        for filename in MASK_FILES.values()
        if not (mask_dir / filename).is_file()
    ]
    if missing_masks:
        joined = "\n".join(f"- {path}" for path in missing_masks)
        raise FileNotFoundError(
            "Map masks are missing. Run once with --bootstrap-masks:\n" + joined
        )

    overrides = read_overrides(override_path)
    candidates, validated_overrides, composition = build_candidates(
        upstream_map,
        vanilla_map,
        source_dir,
        mask_dir,
        candidate_dir,
        overrides,
    )

    comparisons: dict[str, dict[str, Any]] = {}
    for target_name in TARGET_FILES:
        comparisons[target_name] = compare_images(
            source_dir / TARGET_FILES[target_name],
            candidates[target_name],
            diff_mask_dir / TARGET_FILES[target_name],
        )

    applied_targets: list[str] = []
    if args.apply:
        applied_targets = apply_candidates(
            source_dir,
            output_dir,
            candidates,
            comparisons,
        )

    manifest = {
        "revision": REVISION,
        "mode": "apply" if args.apply else "dry_run",
        "project_root": str(project_root),
        "workspace": str(workspace),
        "sources": {
            "upstream": {
                "path": str(upstream_map),
                "sha256": sha256_file(upstream_map),
            },
            "vanilla": {
                "path": str(vanilla_map),
                "sha256": sha256_file(vanilla_map),
            },
        },
        "source_directory": str(source_dir),
        "override_csv": {
            "path": str(override_path),
            "sha256": sha256_file(override_path),
        },
        "bootstrap_masks": bootstrap_rows,
        "composition": composition,
        "validated_overrides": validated_overrides,
        "comparisons": comparisons,
        "applied_targets": applied_targets,
        "live_map_written": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_reports(output_dir, manifest)

    changed = [
        name
        for name, result in comparisons.items()
        if int(result["changed_pixels"]) > 0
    ]
    print(f"Map source refresh: {len(changed)} target(s) differ.")
    print(f"Applied: {len(applied_targets)} target(s).")
    print(f"Summary: {output_dir / 'summary.md'}")
    print("Live BookmarksGit map written: no")

    if args.check and changed and not args.apply:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
