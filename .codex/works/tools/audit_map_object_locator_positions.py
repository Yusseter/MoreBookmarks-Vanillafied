from __future__ import annotations

import csv
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
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

MPE_ALIAS_ROWS = [
    {
        "target_id": 9837,
        "target_barony": "b_yalta",
        "mpe_barony": "b_gialta",
        "mpe_source_id": 22830,
        "donor_id": 13359,
    },
    {
        "target_id": 9836,
        "target_barony": "b_yamboli",
        "mpe_barony": "b_symbolon",
        "mpe_source_id": 22831,
        "donor_id": 13360,
    },
    {
        "target_id": 9835,
        "target_barony": "b_mangup",
        "mpe_barony": "b_phoros",
        "mpe_source_id": 22832,
        "donor_id": 13361,
    },
    {
        "target_id": 9838,
        "target_barony": "b_batacrim",
        "mpe_barony": "b_anapa",
        "mpe_source_id": 21385,
        "donor_id": 12922,
    },
    {
        "target_id": 9833,
        "target_barony": "b_sukdak",
        "mpe_barony": "b_soldaia",
        "mpe_source_id": 22833,
        "donor_id": 13362,
    },
    {
        "target_id": 9832,
        "target_barony": "b_kimmerikon",
        "mpe_barony": "b_kimmerikon",
        "mpe_source_id": 22826,
        "donor_id": 13355,
    },
]

FLOAT_RE = r"[-+]?\d+(?:\.\d+)?"
INSTANCE_RE = re.compile(
    rf"\{{\s*(?:#[^\n\r]*(?:\r?\n)\s*)*id\s*=\s*(?P<id>-?\d+)\s*"
    rf"position\s*=\s*\{{\s*(?P<x>{FLOAT_RE})\s+(?P<y>{FLOAT_RE})\s+(?P<z>{FLOAT_RE})\s*\}}",
    re.IGNORECASE | re.MULTILINE,
)


def repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        mod_root = candidate / "BookmarksGit"
        if mod_root.is_dir():
            return mod_root
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


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
            name = row[4]
            by_id[province_id] = {
                "id": province_id,
                "rgb": rgb,
                "rgb_text": rgb_to_text(rgb),
                "name": name,
            }
            rgb_to_ids[rgb].append(province_id)
    return by_id, rgb_to_ids


def rgb_to_text(rgb: tuple[int, int, int] | None) -> str:
    if rgb is None:
        return ""
    return f"{rgb[0]},{rgb[1]},{rgb[2]}"


def parse_locator_file(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows: list[dict[str, Any]] = []
    for match in INSTANCE_RE.finditer(text):
        rows.append(
            {
                "file": path.name,
                "line": text.count("\n", 0, match.start()) + 1,
                "id": int(match.group("id")),
                "x": float(match.group("x")),
                "height_y": float(match.group("y")),
                "z": float(match.group("z")),
            }
        )
    return rows


def round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def coord_for_mode(row: dict[str, Any], width: int, height: int, mode: str) -> tuple[int, int]:
    if "floor" in mode:
        x = int(math.floor(row["x"]))
        z = int(math.floor(row["z"]))
    else:
        x = round_half_up(row["x"])
        z = round_half_up(row["z"])

    if mode.endswith("direct"):
        y = z
    elif mode.endswith("height_minus_z"):
        y = height - z
    elif mode.endswith("height_minus_1_minus_z"):
        y = height - 1 - z
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return x, y


def in_bounds(x: int, y: int, width: int, height: int) -> bool:
    return 0 <= x < width and 0 <= y < height


def calibrate_transform(
    rows: list[dict[str, Any]],
    definition: dict[int, dict[str, Any]],
    rgb_to_ids: dict[tuple[int, int, int], list[int]],
    pixels: Any,
    width: int,
    height: int,
) -> tuple[str, list[dict[str, Any]]]:
    modes = [
        "round_direct",
        "floor_direct",
        "round_height_minus_z",
        "floor_height_minus_z",
        "round_height_minus_1_minus_z",
        "floor_height_minus_1_minus_z",
    ]
    calibration_rows: list[dict[str, Any]] = []
    for mode in modes:
        total = 0
        in_bounds_count = 0
        exact = 0
        missing_definition = 0
        for row in rows:
            total += 1
            province_id = row["id"]
            if province_id not in definition:
                missing_definition += 1
                continue
            x, y = coord_for_mode(row, width, height, mode)
            if not in_bounds(x, y, width, height):
                continue
            in_bounds_count += 1
            observed_rgb = pixels[x, y]
            if province_id in rgb_to_ids.get(observed_rgb, []):
                exact += 1
        exact_rate = exact / total if total else 0
        in_bounds_rate = in_bounds_count / total if total else 0
        calibration_rows.append(
            {
                "mode": mode,
                "total_locator_rows": total,
                "missing_definition": missing_definition,
                "in_bounds": in_bounds_count,
                "exact_matches": exact,
                "exact_rate": f"{exact_rate:.6f}",
                "in_bounds_rate": f"{in_bounds_rate:.6f}",
            }
        )

    best = max(
        calibration_rows,
        key=lambda item: (
            int(item["exact_matches"]),
            int(item["in_bounds"]),
            -1 if "height_minus_1" in item["mode"] else 0,
        ),
    )
    return str(best["mode"]), calibration_rows


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


def image_rgb_presence(image: Image.Image) -> set[tuple[int, int, int]]:
    present: set[tuple[int, int, int]] = set()
    for rgb in image.getdata():
        present.add(rgb)
    return present


def alias_lookup() -> dict[int, dict[str, Any]]:
    lookup: dict[int, dict[str, Any]] = {}
    for row in MPE_ALIAS_ROWS:
        target = dict(row)
        target["alias_role"] = "target"
        target["alias_pair_id"] = row["donor_id"]
        lookup[row["target_id"]] = target

        donor = dict(row)
        donor["alias_role"] = "donor"
        donor["alias_pair_id"] = row["target_id"]
        lookup[row["donor_id"]] = donor
    return lookup


def audit_rows(
    rows: list[dict[str, Any]],
    definition: dict[int, dict[str, Any]],
    rgb_to_ids: dict[tuple[int, int, int], list[int]],
    image_present: set[tuple[int, int, int]],
    pixels: Any,
    width: int,
    height: int,
    transform_mode: str,
    near_radius: int,
) -> list[dict[str, Any]]:
    audited: list[dict[str, Any]] = []
    aliases = alias_lookup()
    for row in rows:
        province_id = row["id"]
        target = definition.get(province_id)
        x, y = coord_for_mode(row, width, height, transform_mode)

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
        elif not in_bounds(x, y, width, height):
            status = "position_out_of_bounds"
        else:
            observed_rgb = pixels[x, y]
            observed_ids = rgb_to_ids.get(observed_rgb, [])
            observed_names = [definition[pid]["name"] for pid in observed_ids if pid in definition]
            if province_id in observed_ids:
                status = "inside_exact"
            else:
                nearest_distance, nearest_x, nearest_y = nearest_same_province(
                    pixels,
                    width,
                    height,
                    x,
                    y,
                    target["rgb"],
                    near_radius,
                )
                if nearest_distance is not None:
                    status = "near_same_province"
                else:
                    status = "outside_wrong_province"

        alias = aliases.get(province_id, {})
        audited.append(
            {
                "file": row["file"],
                "line": row["line"],
                "province_id": province_id,
                "province_name": target["name"] if target else "",
                "province_rgb": target["rgb_text"] if target else "",
                "locator_x": f"{row['x']:.6f}",
                "locator_y_height": f"{row['height_y']:.6f}",
                "locator_z": f"{row['z']:.6f}",
                "pixel_x": x,
                "pixel_y": y,
                "observed_rgb": rgb_to_text(observed_rgb),
                "observed_definition_ids": "|".join(str(pid) for pid in observed_ids),
                "observed_definition_names": "|".join(observed_names),
                "status": status,
                "nearest_same_province_distance": "" if nearest_distance is None else nearest_distance,
                "nearest_same_province_x": "" if nearest_x is None else nearest_x,
                "nearest_same_province_y": "" if nearest_y is None else nearest_y,
                "alias_role": alias.get("alias_role", ""),
                "alias_target_id": alias.get("target_id", ""),
                "alias_donor_id": alias.get("donor_id", ""),
                "alias_target_barony": alias.get("target_barony", ""),
                "alias_mpe_barony": alias.get("mpe_barony", ""),
                "alias_mpe_source_id": alias.get("mpe_source_id", ""),
            }
        )
    return audited


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize(audited: list[dict[str, Any]], calibration: list[dict[str, Any]], transform_mode: str) -> str:
    status_counts = Counter(row["status"] for row in audited)
    by_file_status = Counter((row["file"], row["status"]) for row in audited)
    alias_rows = [row for row in audited if row["alias_role"]]
    alias_status_counts = Counter(row["status"] for row in alias_rows)
    target_alias_rows = [row for row in alias_rows if row["alias_role"] == "target"]
    donor_alias_rows = [row for row in alias_rows if row["alias_role"] == "donor"]

    lines = [
        "# Map Object Locator Position Audit",
        "",
        f"- selected transform: `{transform_mode}`",
        f"- total locator rows: `{len(audited)}`",
        f"- alias locator rows: `{len(alias_rows)}`",
        f"- alias target locator rows: `{len(target_alias_rows)}`",
        f"- alias donor locator rows: `{len(donor_alias_rows)}`",
        "",
        "## Status Counts",
        "",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"- `{status}`: `{count}`")

    lines.extend(["", "## Calibration", ""])
    for row in calibration:
        selected = " selected" if row["mode"] == transform_mode else ""
        lines.append(
            f"- `{row['mode']}`: exact `{row['exact_matches']}` / "
            f"total `{row['total_locator_rows']}`; in-bounds `{row['in_bounds']}`{selected}"
        )

    lines.extend(["", "## By File", ""])
    for file_name in LOCATOR_FILES:
        file_total = sum(count for (file_key, _status), count in by_file_status.items() if file_key == file_name)
        parts = [
            f"{status}={by_file_status[(file_name, status)]}"
            for status in sorted(status_counts)
            if by_file_status[(file_name, status)]
        ]
        lines.append(f"- `{file_name}`: `{file_total}` rows; " + ", ".join(parts))

    lines.extend(["", "## MPE Alias Status Counts", ""])
    for status, count in sorted(alias_status_counts.items()):
        lines.append(f"- `{status}`: `{count}`")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This audit is read-only for live CK3 data files.",
            "- `near_same_province` means the locator point is outside the exact province pixel, but the province color exists within the configured search radius.",
            "- `game_object_layers.txt` and `great_wall_china.txt` are intentionally not included in this first audit pass.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    root = repo_root()
    definition_path = root / "map_data" / "definition.csv"
    provinces_path = root / "map_data" / "provinces.png"
    locator_dir = root / "gfx" / "map" / "map_object_data"
    out_dir = (
        root.parent
        / ".codex"
        / "works"
        / "analysis"
        / "generated"
        / "map_object_locator_audit"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    definition, rgb_to_ids = read_definition(definition_path)
    image = Image.open(provinces_path).convert("RGB")
    width, height = image.size
    pixels = image.load()
    image_present = image_rgb_presence(image)

    locator_rows: list[dict[str, Any]] = []
    for file_name in LOCATOR_FILES:
        locator_rows.extend(parse_locator_file(locator_dir / file_name))

    transform_mode, calibration_rows = calibrate_transform(locator_rows, definition, rgb_to_ids, pixels, width, height)
    audited = audit_rows(
        locator_rows,
        definition,
        rgb_to_ids,
        image_present,
        pixels,
        width,
        height,
        transform_mode,
        near_radius=16,
    )
    alias_rows = [row for row in audited if row["alias_role"]]
    problem_rows = [row for row in audited if row["status"] not in {"inside_exact", "near_same_province"}]

    write_csv(out_dir / "locator_position_transform_calibration.csv", calibration_rows)
    write_csv(out_dir / "locator_position_audit.csv", audited)
    write_csv(out_dir / "locator_position_problem_rows.csv", problem_rows)
    write_csv(out_dir / "mpe_alias_locator_position_audit.csv", alias_rows)
    (out_dir / "locator_position_summary.md").write_text(
        summarize(audited, calibration_rows, transform_mode),
        encoding="utf-8",
    )

    print("Map object locator position audit complete")
    print(f"repo: {root}")
    print(f"selected_transform: {transform_mode}")
    print(f"locator_rows: {len(audited)}")
    print(f"problem_rows: {len(problem_rows)}")
    print(f"alias_rows: {len(alias_rows)}")
    print(f"out_dir: {out_dir}")


if __name__ == "__main__":
    main()
