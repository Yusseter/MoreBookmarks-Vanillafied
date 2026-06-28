from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from PIL import Image


NEAR_COMPACT_NAME = "locator_position_near_same_province_compact_landed_barony_only.csv"
BORDERLINE_FILE = "building_locators.txt"
BORDERLINE_NEAREST_DIFF_MAX = 1
BORDERLINE_RADIUS = 2
BORDERLINE_MAX_RADIUS_SAME_RATIO = 0.70


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


def parse_landed_title_barony_provinces(path: Path) -> set[int]:
    stack: list[str] = []
    province_ids: set[int] = set()

    import re

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


def parse_rgb(text: str) -> tuple[int, int, int] | None:
    parts = text.split(",")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def nearest_diff_distance(
    pixels: Any,
    width: int,
    height: int,
    x: int,
    y: int,
    province_rgb: tuple[int, int, int],
    max_radius: int,
) -> int | None:
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


def radius_same_ratio(
    pixels: Any,
    width: int,
    height: int,
    x: int,
    y: int,
    province_rgb: tuple[int, int, int],
    radius: int,
) -> float:
    same = 0
    total = 0
    for yy in range(max(0, y - radius), min(height - 1, y + radius) + 1):
        for xx in range(max(0, x - radius), min(width - 1, x + radius) + 1):
            total += 1
            if pixels[xx, yy] == province_rgb:
                same += 1
    return same / total if total else 0.0


def build_near_compact_with_borderline() -> dict[str, int]:
    root = repo_root()
    audit_dir = root / "works" / "analysis" / "generated" / "map_object_locator_audit"
    full_audit = read_csv(audit_dir / "locator_position_audit.csv")
    barony_province_ids = parse_landed_title_barony_provinces(root / "common" / "landed_titles" / "00_landed_titles.txt")

    image = Image.open(root / "map_data" / "provinces.png").convert("RGB")
    width, height = image.size
    pixels = image.load()

    rows: list[dict[str, Any]] = []

    for row in full_audit:
        province_id = int(row["province_id"])
        if province_id not in barony_province_ids:
            continue
        if row["status"] == "near_same_province":
            rows.append(
                {
                    "file": "# Yusseter: OK; building_locators.txt"
                    if row["file"] == BORDERLINE_FILE
                    else row["file"],
                    "province_id": row["province_id"],
                    "province_name": row["province_name"],
                    "province_rgb": row["province_rgb"],
                    "status": "near_same_province",
                    "borderline_reason": f"nearest_same_province_distance={row['nearest_same_province_distance']}",
                }
            )

    near_count = len(rows)
    borderline_count = 0

    for row in full_audit:
        if row["file"] != BORDERLINE_FILE or row["status"] != "inside_exact":
            continue
        province_id = int(row["province_id"])
        if province_id not in barony_province_ids:
            continue
        province_rgb = parse_rgb(row["province_rgb"])
        if province_rgb is None:
            continue
        pixel_x = int(row["pixel_x"])
        pixel_y = int(row["pixel_y"])
        nearest_diff = nearest_diff_distance(
            pixels,
            width,
            height,
            pixel_x,
            pixel_y,
            province_rgb,
            BORDERLINE_NEAREST_DIFF_MAX,
        )
        if nearest_diff is None:
            continue
        same_ratio = radius_same_ratio(
            pixels,
            width,
            height,
            pixel_x,
            pixel_y,
            province_rgb,
            BORDERLINE_RADIUS,
        )
        if same_ratio >= BORDERLINE_MAX_RADIUS_SAME_RATIO:
            continue

        borderline_count += 1
        rows.append(
            {
                "file": row["file"],
                "province_id": row["province_id"],
                "province_name": row["province_name"],
                "province_rgb": row["province_rgb"],
                "status": "inside_exact_but_borderline",
                "borderline_reason": (
                    f"nearest_diff_distance={nearest_diff};"
                    f"radius{BORDERLINE_RADIUS}_same_ratio={same_ratio:.3f};"
                    f"pixel={pixel_x},{pixel_y}"
                ),
            }
        )

    rows.sort(key=lambda item: (item["file"], int(item["province_id"]), item["status"]))
    write_csv(
        audit_dir / NEAR_COMPACT_NAME,
        rows,
        ["file", "province_id", "province_name", "province_rgb", "status", "borderline_reason"],
    )

    summary_path = audit_dir / "locator_position_near_same_with_borderline_summary.md"
    summary_path.write_text(
        "\n".join(
            [
                "# Near-Same + Borderline Building Locator Compact Report",
                "",
                f"- output: `{NEAR_COMPACT_NAME}`",
                f"- near_same_province rows kept: `{near_count}`",
                f"- building inside_exact_but_borderline rows added: `{borderline_count}`",
                f"- total output rows: `{len(rows)}`",
                f"- borderline file: `{BORDERLINE_FILE}`",
                f"- borderline rule: `nearest_diff_distance <= {BORDERLINE_NEAREST_DIFF_MAX}` and `radius{BORDERLINE_RADIUS}_same_ratio < {BORDERLINE_MAX_RADIUS_SAME_RATIO:.2f}`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "near_same_rows": near_count,
        "borderline_rows": borderline_count,
        "total_rows": len(rows),
    }


if __name__ == "__main__":
    result = build_near_compact_with_borderline()
    print("Locator near-same compact report rebuilt")
    print(result)
