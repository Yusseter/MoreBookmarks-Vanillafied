from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image


LOCATOR_FILES = [
    "activities.txt",
    "building_locators.txt",
    "combat_locators.txt",
    "player_stack_locators.txt",
    "siege_locators.txt",
    "special_building_locators.txt",
]

BUILDING_FILE = "building_locators.txt"
SPECIAL_BUILDING_FILE = "special_building_locators.txt"
COMPACT_PROBLEM_FILE = "locator_position_problem_rows_compact_landed_barony_only.csv"
COMPACT_NEAR_FILE = "locator_position_near_same_province_compact_landed_barony_only.csv"
OUTPUT_FILE = "locator_fix_candidates_landed_problem_non_building.csv"
SUMMARY_FILE = "locator_fix_candidates_landed_problem_non_building_summary.md"
TRANSFORM_MODE = "floor_height_minus_1_minus_z"
NEAR_RADIUS = 16
LOCAL_OFFSET_SAMPLE_SIZE = 12
SAFE_INTERIOR_RADIUS = 2
SPECIAL_HIGH_SAFE_RADIUS = 3
NON_SPECIAL_NEAR_DISTANCE_MIN = 8
SPECIAL_NEAR_DISTANCE_MIN = 12

FLOAT_RE = r"[-+]?\d+(?:\.\d+)?"
INSTANCE_RE = re.compile(
    rf"\{{\s*(?:#[^\n\r]*(?:\r?\n)\s*)*id\s*=\s*(?P<id>-?\d+)\s*"
    rf"position\s*=\s*\{{\s*(?P<x>{FLOAT_RE})\s+(?P<y>{FLOAT_RE})\s+(?P<z>{FLOAT_RE})\s*\}}",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class LocatorRow:
    file: str
    line: int
    province_id: int
    x: float
    y: float
    z: float


@dataclass
class ProvinceGeometry:
    count: int = 0
    sum_x: int = 0
    sum_y: int = 0
    min_x: int = 10**9
    min_y: int = 10**9
    max_x: int = -1
    max_y: int = -1

    def add(self, x: int, y: int) -> None:
        self.count += 1
        self.sum_x += x
        self.sum_y += y
        self.min_x = min(self.min_x, x)
        self.min_y = min(self.min_y, y)
        self.max_x = max(self.max_x, x)
        self.max_y = max(self.max_y, y)

    @property
    def center(self) -> tuple[int, int]:
        if not self.count:
            return 0, 0
        return round(self.sum_x / self.count), round(self.sum_y / self.count)

    @property
    def max_radius(self) -> int:
        if not self.count:
            return 0
        return max(self.max_x - self.min_x, self.max_y - self.min_y, 32)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_definition(path: Path) -> tuple[dict[int, dict[str, Any]], dict[tuple[int, int, int], list[int]]]:
    by_id: dict[int, dict[str, Any]] = {}
    rgb_to_ids: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        for row in reader:
            if len(row) < 5:
                continue
            try:
                province_id = int(row[0])
                rgb = (int(row[1]), int(row[2]), int(row[3]))
            except ValueError:
                continue
            by_id[province_id] = {
                "id": province_id,
                "rgb": rgb,
                "rgb_text": rgb_to_text(rgb),
                "name": row[4],
            }
            rgb_to_ids[rgb].append(province_id)
    return by_id, rgb_to_ids


def parse_landed_title_barony_provinces(path: Path) -> set[int]:
    stack: list[str] = []
    province_ids: set[int] = set()
    token_re = re.compile(
        r"(?P<title>\b[ekdcbh]_[A-Za-z0-9_'\-]+\s*=\s*\{)"
        r"|(?P<province>\bprovince\s*=\s*(?P<province_id>\d+))"
        r"|(?P<open>\{)"
        r"|(?P<close>\})"
    )

    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.split("#", 1)[0]
            for match in token_re.finditer(line):
                if match.group("title"):
                    title = re.sub(r"\s*=\s*\{$", "", match.group("title")).strip()
                    stack.append(title)
                elif match.group("open"):
                    stack.append("")
                elif match.group("close"):
                    if stack:
                        stack.pop()
                elif match.group("province"):
                    if any(item.startswith("b_") for item in reversed(stack)):
                        province_ids.add(int(match.group("province_id")))
    return province_ids


def parse_locator_file(path: Path) -> list[LocatorRow]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows: list[LocatorRow] = []
    for match in INSTANCE_RE.finditer(text):
        rows.append(
            LocatorRow(
                file=path.name,
                line=text.count("\n", 0, match.start()) + 1,
                province_id=int(match.group("id")),
                x=float(match.group("x")),
                y=float(match.group("y")),
                z=float(match.group("z")),
            )
        )
    return rows


def rgb_to_text(rgb: tuple[int, int, int] | None) -> str:
    if rgb is None:
        return ""
    return f"{rgb[0]},{rgb[1]},{rgb[2]}"


def is_plain_building_scope(file_name: str) -> bool:
    if file_name == BUILDING_FILE:
        return True
    return file_name.startswith("# Yusseter:") and BUILDING_FILE in file_name


def nearest_distance_from_reason(row: dict[str, str]) -> int | None:
    text = row.get("borderline_reason", "")
    match = re.search(r"nearest_same_province_distance=(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def should_include_near_same_far(row: dict[str, str]) -> bool:
    if row.get("status") != "near_same_province":
        return False
    if is_plain_building_scope(row["file"]):
        return False
    distance = nearest_distance_from_reason(row)
    if distance is None:
        return False
    if row["file"] == SPECIAL_BUILDING_FILE:
        return distance >= SPECIAL_NEAR_DISTANCE_MIN
    return row["file"] in set(LOCATOR_FILES) and distance >= NON_SPECIAL_NEAR_DISTANCE_MIN


def pixel_for_position(x: float, z: float, height: int) -> tuple[int, int]:
    return int(math.floor(x)), height - 1 - int(math.floor(z))


def position_for_pixel(pixel_x: int, pixel_y: int, height: int) -> tuple[float, float]:
    return float(pixel_x), float(height - 1 - pixel_y)


def in_bounds(x: int, y: int, width: int, height: int) -> bool:
    return 0 <= x < width and 0 <= y < height


def nearest_same_province(
    pixels: Any,
    width: int,
    height: int,
    x: int,
    y: int,
    target_rgb: tuple[int, int, int],
    radius: int,
) -> tuple[int | None, int | None, int | None]:
    for distance in range(1, radius + 1):
        min_x = max(0, x - distance)
        max_x = min(width - 1, x + distance)
        min_y = max(0, y - distance)
        max_y = min(height - 1, y + distance)

        for nx in range(min_x, max_x + 1):
            for ny in (min_y, max_y):
                if pixels[nx, ny] == target_rgb:
                    return distance, nx, ny

        for ny in range(min_y + 1, max_y):
            for nx in (min_x, max_x):
                if pixels[nx, ny] == target_rgb:
                    return distance, nx, ny

    return None, None, None


def nearest_diff_distance(
    pixels: Any,
    width: int,
    height: int,
    x: int,
    y: int,
    province_rgb: tuple[int, int, int],
    max_radius: int,
) -> int | None:
    if not in_bounds(x, y, width, height):
        return None
    for radius in range(1, max_radius + 1):
        min_x = max(0, x - radius)
        max_x = min(width - 1, x + radius)
        min_y = max(0, y - radius)
        max_y = min(height - 1, y + radius)
        for yy in range(min_y, max_y + 1):
            for xx in range(min_x, max_x + 1):
                if max(abs(xx - x), abs(yy - y)) != radius:
                    continue
                if pixels[xx, yy] != province_rgb:
                    return radius
    return None


def audit_position(
    province_id: int,
    x_pos: float,
    z_pos: float,
    definition: dict[int, dict[str, Any]],
    rgb_to_ids: dict[tuple[int, int, int], list[int]],
    image_present: set[tuple[int, int, int]],
    pixels: Any,
    width: int,
    height: int,
) -> dict[str, Any]:
    pixel_x, pixel_y = pixel_for_position(x_pos, z_pos, height)
    target = definition.get(province_id)
    observed_rgb: tuple[int, int, int] | None = None
    observed_ids: list[int] = []
    observed_names: list[str] = []
    nearest_distance: int | None = None
    nearest_x: int | None = None
    nearest_y: int | None = None

    if target is None:
        status = "missing_definition"
    elif target["rgb"] not in image_present:
        status = "missing_pixels_in_png"
    elif not in_bounds(pixel_x, pixel_y, width, height):
        status = "position_out_of_bounds"
    else:
        observed_rgb = pixels[pixel_x, pixel_y]
        observed_ids = rgb_to_ids.get(observed_rgb, [])
        observed_names = [definition[item]["name"] for item in observed_ids if item in definition]
        if province_id in observed_ids:
            status = "inside_exact"
        else:
            nearest_distance, nearest_x, nearest_y = nearest_same_province(
                pixels,
                width,
                height,
                pixel_x,
                pixel_y,
                target["rgb"],
                NEAR_RADIUS,
            )
            status = "near_same_province" if nearest_distance is not None else "outside_wrong_province"

    return {
        "status": status,
        "pixel_x": pixel_x,
        "pixel_y": pixel_y,
        "observed_rgb": rgb_to_text(observed_rgb),
        "observed_definition_ids": "|".join(str(item) for item in observed_ids),
        "observed_definition_names": "|".join(observed_names),
        "nearest_same_province_distance": "" if nearest_distance is None else nearest_distance,
        "nearest_same_province_x": "" if nearest_x is None else nearest_x,
        "nearest_same_province_y": "" if nearest_y is None else nearest_y,
    }


def build_needed_geometry(
    image: Image.Image,
    needed_rgbs: set[tuple[int, int, int]],
) -> dict[tuple[int, int, int], ProvinceGeometry]:
    width, _height = image.size
    geometries = {rgb: ProvinceGeometry() for rgb in needed_rgbs}
    for index, rgb in enumerate(image.getdata()):
        if rgb not in geometries:
            continue
        x = index % width
        y = index // width
        geometries[rgb].add(x, y)
    return geometries


def pixel_is_safe(
    pixels: Any,
    width: int,
    height: int,
    x: int,
    y: int,
    target_rgb: tuple[int, int, int],
    safe_radius: int,
) -> bool:
    return (
        in_bounds(x, y, width, height)
        and pixels[x, y] == target_rgb
        and nearest_diff_distance(pixels, width, height, x, y, target_rgb, safe_radius) is None
    )


def find_nearest_pixel(
    pixels: Any,
    width: int,
    height: int,
    start_x: int,
    start_y: int,
    target_rgb: tuple[int, int, int],
    max_radius: int,
    safe_radius: int | None,
) -> tuple[int, int] | None:
    if safe_radius is None:
        if in_bounds(start_x, start_y, width, height) and pixels[start_x, start_y] == target_rgb:
            return start_x, start_y
    elif pixel_is_safe(pixels, width, height, start_x, start_y, target_rgb, safe_radius):
        return start_x, start_y

    for radius in range(1, max_radius + 1):
        min_x = max(0, start_x - radius)
        max_x = min(width - 1, start_x + radius)
        min_y = max(0, start_y - radius)
        max_y = min(height - 1, start_y + radius)

        for x in range(min_x, max_x + 1):
            for y in (min_y, max_y):
                if safe_radius is None:
                    if pixels[x, y] == target_rgb:
                        return x, y
                elif pixel_is_safe(pixels, width, height, x, y, target_rgb, safe_radius):
                    return x, y

        for y in range(min_y + 1, max_y):
            for x in (min_x, max_x):
                if safe_radius is None:
                    if pixels[x, y] == target_rgb:
                        return x, y
                elif pixel_is_safe(pixels, width, height, x, y, target_rgb, safe_radius):
                    return x, y

    return None


def find_safe_or_any_pixel(
    pixels: Any,
    width: int,
    height: int,
    preferred_x: int,
    preferred_y: int,
    target_rgb: tuple[int, int, int],
    geometry: ProvinceGeometry | None,
) -> tuple[int, int, str]:
    search_radius = 256
    safe = find_nearest_pixel(
        pixels, width, height, preferred_x, preferred_y, target_rgb, search_radius, SAFE_INTERIOR_RADIUS
    )
    if safe is not None:
        return safe[0], safe[1], "nearest_safe_interior_from_candidate"

    relaxed = find_nearest_pixel(pixels, width, height, preferred_x, preferred_y, target_rgb, search_radius, 1)
    if relaxed is not None:
        return relaxed[0], relaxed[1], "nearest_relaxed_interior_from_candidate"

    any_match = find_nearest_pixel(pixels, width, height, preferred_x, preferred_y, target_rgb, search_radius, None)
    if any_match is not None:
        return any_match[0], any_match[1], "nearest_any_province_pixel_from_candidate"

    if geometry and geometry.count:
        center_x, center_y = geometry.center
        center_radius = geometry.max_radius
        safe = find_nearest_pixel(
            pixels, width, height, center_x, center_y, target_rgb, center_radius, SAFE_INTERIOR_RADIUS
        )
        if safe is not None:
            return safe[0], safe[1], "province_safe_center"
        any_match = find_nearest_pixel(pixels, width, height, center_x, center_y, target_rgb, center_radius, None)
        if any_match is not None:
            return any_match[0], any_match[1], "province_any_center"

    return preferred_x, preferred_y, "no_target_pixel_found"


def median_pair(pairs: list[tuple[float, float]]) -> tuple[float, float]:
    return float(median([item[0] for item in pairs])), float(median([item[1] for item in pairs]))


def build_offset_models(
    by_file_id: dict[str, dict[int, LocatorRow]],
    definition: dict[int, dict[str, Any]],
    rgb_to_ids: dict[tuple[int, int, int], list[int]],
    image_present: set[tuple[int, int, int]],
    pixels: Any,
    width: int,
    height: int,
    landed_province_ids: set[int],
) -> tuple[dict[str, list[dict[str, float]]], dict[str, tuple[float, float]]]:
    building_rows = by_file_id[BUILDING_FILE]
    examples: dict[str, list[dict[str, float]]] = defaultdict(list)
    global_offsets: dict[str, tuple[float, float]] = {}

    for file_name in LOCATOR_FILES:
        if file_name == BUILDING_FILE:
            continue
        for province_id, target_row in by_file_id[file_name].items():
            if province_id not in landed_province_ids or province_id not in building_rows:
                continue
            building_row = building_rows[province_id]
            building_status = audit_position(
                province_id,
                building_row.x,
                building_row.z,
                definition,
                rgb_to_ids,
                image_present,
                pixels,
                width,
                height,
            )["status"]
            target_status = audit_position(
                province_id,
                target_row.x,
                target_row.z,
                definition,
                rgb_to_ids,
                image_present,
                pixels,
                width,
                height,
            )["status"]
            if building_status != "inside_exact" or target_status != "inside_exact":
                continue
            examples[file_name].append(
                {
                    "province_id": float(province_id),
                    "building_x": building_row.x,
                    "building_z": building_row.z,
                    "dx": target_row.x - building_row.x,
                    "dz": target_row.z - building_row.z,
                }
            )

    for file_name, rows in examples.items():
        global_offsets[file_name] = median_pair([(row["dx"], row["dz"]) for row in rows])

    return examples, global_offsets


def local_offset_for_file(
    file_name: str,
    building_row: LocatorRow,
    examples: dict[str, list[dict[str, float]]],
    global_offsets: dict[str, tuple[float, float]],
) -> tuple[float, float, str, int]:
    rows = examples.get(file_name, [])
    if rows:
        nearest = sorted(
            rows,
            key=lambda row: (row["building_x"] - building_row.x) ** 2 + (row["building_z"] - building_row.z) ** 2,
        )[:LOCAL_OFFSET_SAMPLE_SIZE]
        return (*median_pair([(row["dx"], row["dz"]) for row in nearest]), "building_anchor_local_median_offset", len(nearest))

    if file_name in global_offsets:
        dx, dz = global_offsets[file_name]
        return dx, dz, "building_anchor_global_median_offset", 0

    return 0.0, 0.0, "building_anchor_zero_offset_no_examples", 0


def confidence_for_candidate(
    file_name: str,
    candidate_status: str,
    candidate_source: str,
    candidate_border_ring: int | None,
) -> str:
    if candidate_status != "inside_exact":
        return "low"
    if candidate_border_ring == 1:
        return "low"

    if file_name == SPECIAL_BUILDING_FILE:
        if candidate_source.startswith("building_anchor") and candidate_border_ring is None:
            return "high"
        if candidate_source.startswith("building_anchor") and candidate_border_ring in {2, 3}:
            return "medium"
        return "low"

    if candidate_source.startswith("building_anchor"):
        return "high"
    if candidate_border_ring != 1:
        return "medium"
    return "low"


def build_candidates() -> dict[str, int]:
    root = repo_root()
    audit_dir = root / "works" / "analysis" / "generated" / "map_object_locator_audit"
    locator_dir = root / "gfx" / "map" / "map_object_data"

    compact_rows = read_csv(audit_dir / COMPACT_PROBLEM_FILE)
    near_rows = read_csv(audit_dir / COMPACT_NEAR_FILE)
    target_by_key: dict[tuple[str, int], dict[str, str]] = {}
    problem_target_count = 0
    near_same_far_target_count = 0

    for row in compact_rows:
        if is_plain_building_scope(row["file"]) or row["file"] not in set(LOCATOR_FILES):
            continue
        target = dict(row)
        target["_scope_file"] = COMPACT_PROBLEM_FILE
        target["_scope_reason"] = "problem_row"
        key = (target["file"], int(target["province_id"]))
        if key not in target_by_key:
            problem_target_count += 1
        target_by_key[key] = target

    for row in near_rows:
        if not should_include_near_same_far(row):
            continue
        key = (row["file"], int(row["province_id"]))
        if key in target_by_key:
            continue
        target = dict(row)
        target["_scope_file"] = COMPACT_NEAR_FILE
        target["_scope_reason"] = (
            f"near_same_far_distance={nearest_distance_from_reason(row)};"
            f"non_special_min={NON_SPECIAL_NEAR_DISTANCE_MIN};"
            f"special_min={SPECIAL_NEAR_DISTANCE_MIN}"
        )
        target_by_key[key] = target
        near_same_far_target_count += 1

    target_rows = list(target_by_key.values())

    definition, rgb_to_ids = read_definition(root / "map_data" / "definition.csv")
    landed_province_ids = parse_landed_title_barony_provinces(
        root / "common" / "landed_titles" / "00_landed_titles.txt"
    )

    image = Image.open(root / "map_data" / "provinces.png").convert("RGB")
    width, height = image.size
    pixels = image.load()
    image_present = set(image.getdata())

    all_locator_rows: dict[str, list[LocatorRow]] = {
        file_name: parse_locator_file(locator_dir / file_name) for file_name in LOCATOR_FILES
    }
    by_file_id: dict[str, dict[int, LocatorRow]] = {
        file_name: {row.province_id: row for row in rows} for file_name, rows in all_locator_rows.items()
    }

    target_rgbs = {
        definition[int(row["province_id"])]["rgb"]
        for row in target_rows
        if row["province_id"].isdigit() and int(row["province_id"]) in definition
    }
    geometries = build_needed_geometry(image, target_rgbs)
    examples, global_offsets = build_offset_models(
        by_file_id,
        definition,
        rgb_to_ids,
        image_present,
        pixels,
        width,
        height,
        landed_province_ids,
    )

    output_rows: list[dict[str, Any]] = []
    for target in target_rows:
        file_name = target["file"]
        province_id = int(target["province_id"])
        province = definition.get(province_id)
        target_row = by_file_id.get(file_name, {}).get(province_id)

        if target_row is None or province is None:
            output_rows.append(
                {
                    "file": file_name,
                    "province_id": province_id,
                    "province_name": target["province_name"],
                    "current_x": "",
                    "current_y": "",
                    "current_z": "",
                    "observed_rgb": "",
                    "current_status": "missing_locator_row" if target_row is None else "missing_definition",
                    "candidate_x": "",
                    "candidate_y": "",
                    "candidate_z": "",
                    "candidate_status": "not_generated",
                    "confidence": "low",
                    "candidate_source": "not_generated",
                    "reason": "target locator row or province definition was missing",
                }
            )
            continue

        current_audit = audit_position(
            province_id,
            target_row.x,
            target_row.z,
            definition,
            rgb_to_ids,
            image_present,
            pixels,
            width,
            height,
        )

        target_rgb = province["rgb"]
        geometry = geometries.get(target_rgb)
        building_row = by_file_id[BUILDING_FILE].get(province_id)
        reason_parts = [
            f"scope={target.get('_scope_file', '')}",
            f"scope_reason={target.get('_scope_reason', '')}",
            f"transform={TRANSFORM_MODE}",
        ]

        if building_row is not None:
            building_audit = audit_position(
                province_id,
                building_row.x,
                building_row.z,
                definition,
                rgb_to_ids,
                image_present,
                pixels,
                width,
                height,
            )
            reason_parts.append(f"building_anchor_status={building_audit['status']}")
        else:
            building_audit = {"status": "missing"}
            reason_parts.append("building_anchor_status=missing")

        if building_row is not None and building_audit["status"] == "inside_exact":
            dx, dz, source, example_count = local_offset_for_file(file_name, building_row, examples, global_offsets)
            raw_x = building_row.x + dx
            raw_z = building_row.z + dz
            raw_audit = audit_position(
                province_id,
                raw_x,
                raw_z,
                definition,
                rgb_to_ids,
                image_present,
                pixels,
                width,
                height,
            )
            reason_parts.extend(
                [
                    f"offset_source={source}",
                    f"offset_examples={example_count}",
                    f"offset_dx={dx:.3f}",
                    f"offset_dz={dz:.3f}",
                    f"raw_candidate_status={raw_audit['status']}",
                ]
            )
            if raw_audit["status"] == "inside_exact":
                candidate_x = raw_x
                candidate_z = raw_z
                candidate_source = source
            else:
                raw_pixel_x, raw_pixel_y = pixel_for_position(raw_x, raw_z, height)
                safe_x, safe_y, fallback_source = find_safe_or_any_pixel(
                    pixels,
                    width,
                    height,
                    raw_pixel_x,
                    raw_pixel_y,
                    target_rgb,
                    geometry,
                )
                candidate_x, candidate_z = position_for_pixel(safe_x, safe_y, height)
                candidate_source = f"{source}_{fallback_source}"
                reason_parts.append(f"fallback={fallback_source}")
        else:
            center_x, center_y = geometry.center if geometry else current_audit["pixel_x"], current_audit["pixel_y"]
            safe_x, safe_y, fallback_source = find_safe_or_any_pixel(
                pixels,
                width,
                height,
                int(center_x),
                int(center_y),
                target_rgb,
                geometry,
            )
            candidate_x, candidate_z = position_for_pixel(safe_x, safe_y, height)
            candidate_source = fallback_source
            reason_parts.append(f"fallback={fallback_source}")

        candidate_audit = audit_position(
            province_id,
            candidate_x,
            candidate_z,
            definition,
            rgb_to_ids,
            image_present,
            pixels,
            width,
            height,
        )
        candidate_pixel_x, candidate_pixel_y = pixel_for_position(candidate_x, candidate_z, height)
        border_check_radius = SPECIAL_HIGH_SAFE_RADIUS if file_name == SPECIAL_BUILDING_FILE else SAFE_INTERIOR_RADIUS
        candidate_border_ring = nearest_diff_distance(
            pixels,
            width,
            height,
            candidate_pixel_x,
            candidate_pixel_y,
            target_rgb,
            border_check_radius,
        )
        confidence = confidence_for_candidate(
            file_name,
            candidate_audit["status"],
            candidate_source,
            candidate_border_ring,
        )
        border_text = "none_within_radius" if candidate_border_ring is None else str(candidate_border_ring)
        reason_parts.append(f"candidate_border_ring={border_text}")

        output_rows.append(
            {
                "file": file_name,
                "province_id": province_id,
                "province_name": target["province_name"],
                "current_x": f"{target_row.x:.6f}",
                "current_y": f"{target_row.y:.6f}",
                "current_z": f"{target_row.z:.6f}",
                "observed_rgb": current_audit["observed_rgb"],
                "current_status": current_audit["status"],
                "candidate_x": f"{candidate_x:.6f}",
                "candidate_y": f"{target_row.y:.6f}",
                "candidate_z": f"{candidate_z:.6f}",
                "candidate_status": candidate_audit["status"],
                "confidence": confidence,
                "candidate_source": candidate_source,
                "reason": ";".join(reason_parts),
            }
        )

    output_rows.sort(key=lambda row: (row["file"], int(row["province_id"])))
    fieldnames = [
        "file",
        "province_id",
        "province_name",
        "current_x",
        "current_y",
        "current_z",
        "observed_rgb",
        "current_status",
        "candidate_x",
        "candidate_y",
        "candidate_z",
        "candidate_status",
        "confidence",
        "candidate_source",
        "reason",
    ]
    write_csv(audit_dir / OUTPUT_FILE, output_rows, fieldnames)

    by_file = defaultdict(int)
    by_confidence = defaultdict(int)
    by_candidate_status = defaultdict(int)
    for row in output_rows:
        by_file[row["file"]] += 1
        by_confidence[row["confidence"]] += 1
        by_candidate_status[row["candidate_status"]] += 1

    summary_lines = [
        "# Locator Fix Candidate Report",
        "",
        f"- output: `{OUTPUT_FILE}`",
        f"- source compact problem file: `{COMPACT_PROBLEM_FILE}`",
        f"- source compact near-same file: `{COMPACT_NEAR_FILE}`",
        f"- compact source rows: `{len(compact_rows)}`",
        f"- near-same source rows: `{len(near_rows)}`",
        f"- problem target rows after excluding plain building locators: `{problem_target_count}`",
        f"- near-same far target rows after excluding plain building locators: `{near_same_far_target_count}`",
        f"- total target rows: `{len(output_rows)}`",
        f"- non-special near-same distance min: `{NON_SPECIAL_NEAR_DISTANCE_MIN}`",
        f"- special-building near-same distance min: `{SPECIAL_NEAR_DISTANCE_MIN}`",
        f"- transform: `{TRANSFORM_MODE}`",
        f"- live map object files modified: `0`",
        "",
        "## By File",
        "",
    ]
    for file_name in sorted(by_file):
        summary_lines.append(f"- `{file_name}`: `{by_file[file_name]}`")
    summary_lines.extend(["", "## By Confidence", ""])
    for confidence in ["high", "medium", "low"]:
        summary_lines.append(f"- `{confidence}`: `{by_confidence[confidence]}`")
    summary_lines.extend(["", "## By Candidate Status", ""])
    for status in sorted(by_candidate_status):
        summary_lines.append(f"- `{status}`: `{by_candidate_status[status]}`")
    summary_lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This is a dry-run report only; no locator source file is changed.",
            "- `building_locators.txt` is excluded from the target set and used only as an anchor when its current position is `inside_exact`.",
            "- `# Yusseter: ... building_locators.txt` near-same marker rows are excluded from the target set.",
            "- `special_building_locators.txt` is included but uses stricter high-confidence border checks.",
            "",
        ]
    )
    (audit_dir / SUMMARY_FILE).write_text("\n".join(summary_lines), encoding="utf-8")

    return {
        "source_rows": len(compact_rows),
        "near_source_rows": len(near_rows),
        "problem_target_rows": problem_target_count,
        "near_same_far_target_rows": near_same_far_target_count,
        "target_rows": len(output_rows),
        "high": by_confidence["high"],
        "medium": by_confidence["medium"],
        "low": by_confidence["low"],
        "inside_exact_candidates": by_candidate_status["inside_exact"],
    }


def main() -> None:
    stats = build_candidates()
    print(
        "Built locator fix candidates: "
        f"target_rows={stats['target_rows']} "
        f"inside_exact_candidates={stats['inside_exact_candidates']} "
        f"high={stats['high']} medium={stats['medium']} low={stats['low']}"
    )


if __name__ == "__main__":
    main()
