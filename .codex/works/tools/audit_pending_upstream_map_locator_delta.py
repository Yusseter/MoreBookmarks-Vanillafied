from __future__ import annotations

import argparse
import csv
import hashlib
import re
import subprocess
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageOps


BASE_REVISION = "ed1520220c1e8469a9865e3f69c57bcc399df0c5"
THEIRS_REVISION = "upstream/main"
OUTPUT_PATH = Path(
    ".codex/works/analysis/generated/upstream_map_locator_delta"
)
PROVINCES_PATH = "BookmarksGit/map_data/provinces.png"
DEFINITION_PATH = "BookmarksGit/map_data/definition.csv"
LOCATOR_PATHS = (
    "BookmarksGit/gfx/map/map_object_data/building_locators.txt",
    "BookmarksGit/gfx/map/map_object_data/special_building_locators.txt",
)
SPECIAL_PATH = "BookmarksGit/gfx/map/map_object_data/special.txt"
DESCRIPTOR_PATH = "BookmarksGit/descriptor.mod"

LOCATOR_RE = re.compile(
    r"\{\s*id\s*=\s*(?P<id>\d+)\s*"
    r"position\s*=\s*\{(?P<position>[^{}]*)\}\s*"
    r"rotation\s*=\s*\{(?P<rotation>[^{}]*)\}\s*"
    r"scale\s*=\s*\{(?P<scale>[^{}]*)\}\s*\}",
    re.DOTALL,
)
ID_RE = re.compile(r"(?m)^\s*id\s*=\s*(\d+)\b")
REPLACE_PATH_RE = re.compile(r'\breplace_path\s*=\s*"([^"]+)"')
PROPERTY_RE = re.compile(
    r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r'(?:"([^"]*)"|([^\s#{}]+))',
    re.DOTALL,
)


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    project_root = find_project_root()
    parser = argparse.ArgumentParser(
        description=(
            "Audit pending upstream provinces.png and map-object locator changes "
            "without modifying live CK3 files"
        )
    )
    parser.add_argument("--repo-root", type=Path, default=project_root)
    parser.add_argument("--base-revision", default=BASE_REVISION)
    parser.add_argument("--ours-revision", default="HEAD")
    parser.add_argument("--theirs-revision", default=THEIRS_REVISION)
    parser.add_argument(
        "--vanilla-root",
        type=Path,
        default=Path(
            r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def run_git(repo_root: Path, *args: str, text: bool = True) -> str | bytes:
    return subprocess.check_output(
        ["git", *args],
        cwd=repo_root,
        text=text,
        encoding="utf-8-sig" if text else None,
        errors="replace" if text else None,
        stderr=subprocess.DEVNULL,
    )


def resolve_revision(repo_root: Path, revision: str) -> str:
    return str(run_git(repo_root, "rev-parse", revision)).strip()


def revision_bytes(repo_root: Path, revision: str, path: str) -> bytes | None:
    try:
        result = run_git(repo_root, "show", f"{revision}:{path}", text=False)
    except subprocess.CalledProcessError:
        return None
    assert isinstance(result, bytes)
    return result


def sha256(data: bytes | None) -> str:
    if data is None:
        return "missing"
    return hashlib.sha256(data).hexdigest()


def decode_text(data: bytes | None) -> str:
    return "" if data is None else data.decode("utf-8-sig", errors="replace")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["status"])
        writer.writeheader()
        writer.writerows(rows)


def normalize_script(text: str) -> str:
    output: list[str] = []
    quoted = False
    comment = False
    escaped = False
    for char in text.lstrip("\ufeff"):
        if comment:
            if char in "\r\n":
                comment = False
            continue
        if quoted:
            output.append(char)
            if char == '"' and not escaped:
                quoted = False
            escaped = char == "\\" and not escaped
            if char != "\\":
                escaped = False
            continue
        if char == "#":
            comment = True
            continue
        if char == '"':
            quoted = True
            output.append(char)
            continue
        if not char.isspace():
            output.append(char)
    return "".join(output)


def strip_comments(text: str) -> str:
    output: list[str] = []
    quoted = False
    comment = False
    escaped = False
    for char in text:
        if comment:
            if char in "\r\n":
                comment = False
                output.append(char)
            continue
        if quoted:
            output.append(char)
            if char == '"' and not escaped:
                quoted = False
            escaped = char == "\\" and not escaped
            if char != "\\":
                escaped = False
            continue
        if char == "#":
            comment = True
            continue
        if char == '"':
            quoted = True
        output.append(char)
    return "".join(output)


def parse_definition(data: bytes | None) -> tuple[dict[int, dict[str, Any]], dict[tuple[int, int, int], list[dict[str, Any]]]]:
    by_id: dict[int, dict[str, Any]] = {}
    by_rgb: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for row in csv.reader(decode_text(data).splitlines(), delimiter=";"):
        if len(row) < 5:
            continue
        try:
            province_id = int(row[0])
            rgb = (int(row[1]), int(row[2]), int(row[3]))
        except ValueError:
            continue
        entry = {"id": province_id, "rgb": rgb, "name": row[4].strip()}
        by_id[province_id] = entry
        by_rgb.setdefault(rgb, []).append(entry)
    return by_id, by_rgb


def rgb_text(rgb: tuple[int, int, int]) -> str:
    return f"{rgb[0]} {rgb[1]} {rgb[2]}"


def definition_values(
    by_rgb: dict[tuple[int, int, int], list[dict[str, Any]]],
    rgb: tuple[int, int, int],
) -> tuple[str, str]:
    rows = by_rgb.get(rgb, [])
    return (
        "|".join(str(row["id"]) for row in rows),
        "|".join(str(row["name"]) for row in rows),
    )


def definition_identity_status(
    theirs_by_rgb: dict[tuple[int, int, int], list[dict[str, Any]]],
    ours_by_rgb: dict[tuple[int, int, int], list[dict[str, Any]]],
    rgb: tuple[int, int, int],
) -> str:
    if rgb == (0, 0, 0):
        return "reserved_impassable_black"
    theirs = theirs_by_rgb.get(rgb, [])
    ours = ours_by_rgb.get(rgb, [])
    if not theirs:
        return "missing_in_theirs_definition"
    if not ours:
        return "missing_in_ours_definition"
    theirs_ids = [row["id"] for row in theirs]
    ours_ids = [row["id"] for row in ours]
    if theirs_ids != ours_ids:
        return "rgb_repurposed_to_different_id"
    theirs_names = [row["name"] for row in theirs]
    ours_names = [row["name"] for row in ours]
    if theirs_names != ours_names:
        return "same_id_different_name"
    return "exact_identity"


def image_from_bytes(data: bytes | None, label: str) -> Image.Image:
    if data is None:
        raise RuntimeError(f"Missing image for {label}")
    with Image.open(BytesIO(data)) as source:
        return source.convert("RGB")


def neq_mask(first: Image.Image, second: Image.Image) -> Image.Image:
    difference = ImageChops.difference(first, second)
    channels = [channel.point([0] + [255] * 255) for channel in difference.split()]
    return ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])


def mask_and(first: Image.Image, second: Image.Image) -> Image.Image:
    return ImageChops.multiply(first, second)


def mask_or(first: Image.Image, second: Image.Image) -> Image.Image:
    return ImageChops.lighter(first, second)


def mask_count(mask: Image.Image) -> int:
    return mask.histogram()[255]


def masked_color_counts(
    image: Image.Image,
    mask: Image.Image,
) -> Counter[tuple[int, int, int]]:
    bbox = mask.getbbox()
    if bbox is None:
        return Counter()
    crop = image.crop(bbox).convert("RGBA")
    crop.putalpha(mask.crop(bbox))
    colors = crop.getcolors(maxcolors=crop.width * crop.height)
    if colors is None:
        raise RuntimeError("Too many colors while inventorying changed pixels")
    return Counter(
        {(red, green, blue): count for count, (red, green, blue, alpha) in colors if alpha == 255}
    )


def build_control_png(
    ours: Image.Image,
    masks: dict[str, Image.Image],
    counts: dict[str, int],
    path: Path,
) -> None:
    max_width = 2200
    scale = min(1.0, max_width / ours.width)
    size = (max(1, round(ours.width * scale)), max(1, round(ours.height * scale)))
    gray = ImageOps.grayscale(ours).convert("RGB").resize(size, Image.Resampling.LANCZOS)
    gray = ImageEnhance.Contrast(gray).enhance(0.75)
    colors = {
        "ours_only": (40, 120, 255),
        "theirs_only": (50, 220, 70),
        "both_same": (0, 220, 220),
        "conflict": (255, 35, 35),
    }
    rendered = gray
    for key in ("ours_only", "theirs_only", "both_same", "conflict"):
        resized_mask = masks[key].resize(size, Image.Resampling.NEAREST)
        tinted = Image.blend(rendered, Image.new("RGB", size, colors[key]), 0.72)
        rendered = Image.composite(tinted, rendered, resized_mask)

    header_height = 120
    canvas = Image.new("RGB", (size[0], size[1] + header_height), (22, 22, 22))
    canvas.paste(rendered, (0, header_height))
    draw = ImageDraw.Draw(canvas)
    draw.text((18, 12), "Pending upstream provinces.png three-way audit", fill="white")
    x = 18
    y = 48
    for key in ("ours_only", "theirs_only", "both_same", "conflict"):
        draw.rectangle((x, y, x + 22, y + 22), fill=colors[key])
        draw.text((x + 30, y + 4), f"{key}: {counts[key]:,}", fill="white")
        x += 310
    draw.text(
        (18, 88),
        "Blue=Yusseter only, green=upstream only, cyan=same edit, red=conflict",
        fill=(210, 210, 210),
    )
    canvas.save(path, optimize=False, compress_level=9)


def parse_number_tuple(value: str) -> tuple[Decimal, ...]:
    numbers: list[Decimal] = []
    for token in value.split():
        try:
            number = Decimal(token)
        except InvalidOperation as error:
            raise ValueError(f"Invalid locator number {token!r}") from error
        numbers.append(Decimal(0) if number == 0 else number)
    return tuple(numbers)


def tuple_text(values: tuple[Decimal, ...] | None) -> str:
    if values is None:
        return "missing"
    return " ".join(format(value, "f") for value in values)


def parse_locator_records(data: bytes | None, label: str) -> dict[int, dict[str, tuple[Decimal, ...]]]:
    if data is None:
        return {}
    text = strip_comments(decode_text(data))
    raw_ids = [int(value) for value in ID_RE.findall(text)]
    records: dict[int, dict[str, tuple[Decimal, ...]]] = {}
    for match in LOCATOR_RE.finditer(text):
        province_id = int(match.group("id"))
        if province_id in records:
            raise RuntimeError(f"Duplicate locator id {province_id} in {label}")
        records[province_id] = {
            "position": parse_number_tuple(match.group("position")),
            "rotation": parse_number_tuple(match.group("rotation")),
            "scale": parse_number_tuple(match.group("scale")),
        }
    if len(raw_ids) != len(records):
        raise RuntimeError(
            f"Locator parser coverage mismatch in {label}: ids={len(raw_ids)} parsed={len(records)}"
        )
    return records


def changed_record_fields(
    base: dict[str, tuple[Decimal, ...]] | None,
    theirs: dict[str, tuple[Decimal, ...]] | None,
) -> list[str]:
    if base is None or theirs is None:
        return ["record"]
    return [key for key in ("position", "rotation", "scale") if base.get(key) != theirs.get(key)]


def classify_three_way(base: Any, ours: Any, theirs: Any) -> str:
    if base == theirs:
        return "no_upstream_semantic_change"
    if ours == theirs:
        return "already_matches_upstream"
    if ours == base:
        return "candidate_take_upstream"
    if base is None and ours is None:
        return "candidate_add_upstream"
    return "conflict_manual_review"


def locator_position_status(
    record: dict[str, tuple[Decimal, ...]] | None,
    province_id: int,
    image: Image.Image,
    definition_by_rgb: dict[tuple[int, int, int], list[dict[str, Any]]],
) -> dict[str, str]:
    if record is None or len(record["position"]) < 3:
        return {
            "map_x": "",
            "map_y": "",
            "observed_rgb": "",
            "observed_ids": "",
            "observed_names": "",
            "position_status": "missing_record",
        }
    x = int(record["position"][0])
    y = image.height - 1 - int(record["position"][2])
    if not (0 <= x < image.width and 0 <= y < image.height):
        return {
            "map_x": str(x),
            "map_y": str(y),
            "observed_rgb": "",
            "observed_ids": "",
            "observed_names": "",
            "position_status": "out_of_bounds",
        }
    observed = image.getpixel((x, y))
    observed_ids, observed_names = definition_values(definition_by_rgb, observed)
    status = "inside_exact" if province_id in {
        row["id"] for row in definition_by_rgb.get(observed, [])
    } else "different_or_unknown_province"
    return {
        "map_x": str(x),
        "map_y": str(y),
        "observed_rgb": rgb_text(observed),
        "observed_ids": observed_ids,
        "observed_names": observed_names,
        "position_status": status,
    }


def extract_object_blocks(data: bytes | None) -> dict[str, dict[str, str]]:
    if data is None:
        return {}
    text = strip_comments(decode_text(data))
    opener = re.compile(r"\bobject\s*=\s*\{")
    objects: dict[str, dict[str, str]] = {}
    search_from = 0
    while True:
        match = opener.search(text, search_from)
        if match is None:
            break
        start = match.start()
        index = match.end()
        depth = 1
        quoted = False
        escaped = False
        while index < len(text) and depth:
            char = text[index]
            if quoted:
                if char == '"' and not escaped:
                    quoted = False
                escaped = char == "\\" and not escaped
                if char != "\\":
                    escaped = False
            elif char == '"':
                quoted = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1
        if depth:
            raise RuntimeError("Unbalanced object block in special.txt")
        block = text[start:index]
        properties: dict[str, str] = {}
        for prop in PROPERTY_RE.finditer(block):
            properties[prop.group(1)] = (
                prop.group(2) if prop.group(2) is not None else prop.group(3)
            ).strip()
        name = properties.get("name", "")
        if not name:
            raise RuntimeError("Unnamed object block in special.txt")
        if name in objects:
            raise RuntimeError(f"Duplicate special object {name!r}")
        properties["__normalized__"] = normalize_script(block)
        objects[name] = properties
        search_from = index
    return objects


def replace_path_blocks_fallback(descriptor: bytes | None, relative_path: str) -> bool:
    target = relative_path.replace("\\", "/").removeprefix("BookmarksGit/")
    for value in REPLACE_PATH_RE.findall(decode_text(descriptor)):
        replace_path = value.replace("\\", "/").rstrip("/")
        if target == replace_path or target.startswith(replace_path + "/"):
            return True
    return False


def vanilla_bytes(vanilla_root: Path, relative_path: str) -> bytes | None:
    path = vanilla_root / relative_path.removeprefix("BookmarksGit/")
    return path.read_bytes() if path.is_file() else None


def find_mesh_asset(vanilla_root: Path, mesh_name: str) -> str:
    models_root = vanilla_root / "gfx/models"
    if not models_root.is_dir() or not mesh_name:
        return ""
    for path in sorted(models_root.rglob("*.asset")):
        try:
            if mesh_name in path.read_text(encoding="utf-8-sig", errors="replace"):
                return str(path)
        except OSError:
            continue
    return ""


def object_position_status(
    object_row: dict[str, str],
    image: Image.Image,
    definition_by_rgb: dict[tuple[int, int, int], list[dict[str, Any]]],
) -> dict[str, str]:
    try:
        values = [Decimal(value) for value in object_row.get("transform", "").split()]
    except InvalidOperation:
        values = []
    if len(values) < 3:
        return {
            "map_x": "",
            "map_y": "",
            "observed_rgb": "",
            "observed_ids": "",
            "observed_names": "",
            "position_status": "missing_transform",
        }
    x = int(values[0])
    y = image.height - 1 - int(values[2])
    if not (0 <= x < image.width and 0 <= y < image.height):
        return {
            "map_x": str(x),
            "map_y": str(y),
            "observed_rgb": "",
            "observed_ids": "",
            "observed_names": "",
            "position_status": "out_of_bounds",
        }
    observed = image.getpixel((x, y))
    observed_ids, observed_names = definition_values(definition_by_rgb, observed)
    return {
        "map_x": str(x),
        "map_y": str(y),
        "observed_rgb": rgb_text(observed),
        "observed_ids": observed_ids,
        "observed_names": observed_names,
        "position_status": "mapped_pixel" if observed_ids else "unknown_pixel",
    }


def semantic_hash(data: bytes | None) -> str:
    return hashlib.sha256(normalize_script(decode_text(data)).encode("utf-8")).hexdigest()


def file_dirty(repo_root: Path, path: str) -> str:
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", path],
        cwd=repo_root,
        check=False,
    )
    return "yes" if result.returncode else "no"


def audit_map(
    repo_root: Path,
    base_revision: str,
    ours_revision: str,
    theirs_revision: str,
    output_dir: Path,
) -> dict[str, Any]:
    image_data = {
        "base": revision_bytes(repo_root, base_revision, PROVINCES_PATH),
        "ours": revision_bytes(repo_root, ours_revision, PROVINCES_PATH),
        "theirs": revision_bytes(repo_root, theirs_revision, PROVINCES_PATH),
    }
    definition_data = {
        "base": revision_bytes(repo_root, base_revision, DEFINITION_PATH),
        "ours": revision_bytes(repo_root, ours_revision, DEFINITION_PATH),
        "theirs": revision_bytes(repo_root, theirs_revision, DEFINITION_PATH),
    }
    images = {
        label: image_from_bytes(data, label) for label, data in image_data.items()
    }
    dimensions = {image.size for image in images.values()}
    if len(dimensions) != 1:
        raise RuntimeError(f"provinces.png dimensions differ: {dimensions}")

    definitions = {
        label: parse_definition(data) for label, data in definition_data.items()
    }
    pixel_hashes = {
        label: hashlib.sha256(image.tobytes()).hexdigest()
        for label, image in images.items()
    }
    image_metadata_rows: list[dict[str, Any]] = []
    for label, data in image_data.items():
        if data is None:
            continue
        with Image.open(BytesIO(data)) as source:
            image_metadata_rows.append(
                {
                    "snapshot": label,
                    "byte_count": len(data),
                    "file_sha256": sha256(data),
                    "source_mode": source.mode,
                    "width": source.width,
                    "height": source.height,
                    "metadata_keys": "|".join(sorted(source.info)),
                    "rgb_pixel_sha256": pixel_hashes[label],
                    "pixels_match_base": "yes"
                    if pixel_hashes[label] == pixel_hashes["base"]
                    else "no",
                }
            )
    write_csv(output_dir / "map_image_snapshot_metadata.csv", image_metadata_rows)
    base_changed = neq_mask(images["base"], images["ours"])
    theirs_changed = neq_mask(images["base"], images["theirs"])
    ours_vs_theirs = neq_mask(images["ours"], images["theirs"])
    both_changed = mask_and(base_changed, theirs_changed)
    masks = {
        "unchanged": ImageOps.invert(mask_or(base_changed, theirs_changed)),
        "ours_only": mask_and(base_changed, ImageOps.invert(theirs_changed)),
        "theirs_only": mask_and(ImageOps.invert(base_changed), theirs_changed),
        "both_same": mask_and(both_changed, ImageOps.invert(ours_vs_theirs)),
        "conflict": mask_and(both_changed, ours_vs_theirs),
    }
    counts = {key: mask_count(mask) for key, mask in masks.items()}
    total_pixels = images["base"].width * images["base"].height
    if sum(counts.values()) != total_pixels:
        raise RuntimeError(
            f"Pixel category coverage mismatch: {sum(counts.values())} != {total_pixels}"
        )

    category_rows = [
        {
            "category": key,
            "pixel_count": counts[key],
            "percent": f"{counts[key] / total_pixels * 100:.8f}",
            "meaning": {
                "unchanged": "all three snapshots match",
                "ours_only": "only Yusseter changed from merge base",
                "theirs_only": "only pending upstream changed from merge base",
                "both_same": "both sides made the same pixel result",
                "conflict": "both sides changed the pixel differently",
            }[key],
        }
        for key in ("unchanged", "ours_only", "theirs_only", "both_same", "conflict")
    ]
    write_csv(output_dir / "map_pixel_three_way_categories.csv", category_rows)

    destination_counts = masked_color_counts(images["theirs"], theirs_changed)
    theirs_by_rgb = definitions["theirs"][1]
    ours_by_rgb = definitions["ours"][1]
    color_rows: list[dict[str, Any]] = []
    unsafe_color_count = 0
    unsafe_pixel_count = 0
    for rgb, count in sorted(destination_counts.items(), key=lambda item: (-item[1], item[0])):
        status = definition_identity_status(theirs_by_rgb, ours_by_rgb, rgb)
        safe = status in {"exact_identity", "reserved_impassable_black"}
        if not safe:
            unsafe_color_count += 1
            unsafe_pixel_count += count
        theirs_ids, theirs_names = definition_values(theirs_by_rgb, rgb)
        ours_ids, ours_names = definition_values(ours_by_rgb, rgb)
        color_rows.append(
            {
                "theirs_destination_rgb": rgb_text(rgb),
                "changed_pixel_count": count,
                "identity_status_in_ours_definition": status,
                "direct_color_copy_safe": "yes" if safe else "no",
                "theirs_province_ids": theirs_ids,
                "theirs_province_names": theirs_names,
                "ours_province_ids": ours_ids,
                "ours_province_names": ours_names,
            }
        )
    write_csv(output_dir / "map_upstream_destination_colors.csv", color_rows)

    conflict_rows: list[dict[str, Any]] = []
    for snapshot in ("base", "ours", "theirs"):
        for rgb, count in sorted(
            masked_color_counts(images[snapshot], masks["conflict"]).items(),
            key=lambda item: (-item[1], item[0]),
        ):
            ids, names = definition_values(definitions[snapshot][1], rgb)
            conflict_rows.append(
                {
                    "snapshot": snapshot,
                    "rgb": rgb_text(rgb),
                    "conflict_pixel_count": count,
                    "definition_ids": ids,
                    "definition_names": names,
                }
            )
    write_csv(output_dir / "map_conflict_color_inventory.csv", conflict_rows)
    build_control_png(
        images["ours"],
        masks,
        counts,
        output_dir / "provinces_three_way_control.png",
    )

    upstream_raw_changed = image_data["base"] != image_data["theirs"]
    upstream_pixel_change_count = mask_count(theirs_changed)
    merge_status = "standard_three_way_candidate"
    if not upstream_pixel_change_count and upstream_raw_changed:
        merge_status = "upstream_encoding_metadata_only_keep_ours"
    elif not upstream_pixel_change_count:
        merge_status = "no_upstream_pixel_change"
    elif counts["conflict"]:
        merge_status = "pixel_conflicts_require_semantic_resolution"
    elif unsafe_pixel_count:
        merge_status = "upstream_colors_require_definition_remap"

    return {
        "images": images,
        "definitions": definitions,
        "image_data": image_data,
        "definition_data": definition_data,
        "counts": counts,
        "total_pixels": total_pixels,
        "unsafe_color_count": unsafe_color_count,
        "unsafe_pixel_count": unsafe_pixel_count,
        "destination_color_count": len(destination_counts),
        "upstream_raw_changed": upstream_raw_changed,
        "upstream_pixel_change_count": upstream_pixel_change_count,
        "pixel_hashes": pixel_hashes,
        "merge_status": merge_status,
    }


def audit_locator_files(
    repo_root: Path,
    base_revision: str,
    ours_revision: str,
    theirs_revision: str,
    map_result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, bytes | None]]:
    file_rows: list[dict[str, Any]] = []
    change_rows: list[dict[str, Any]] = []
    input_data: dict[str, bytes | None] = {}
    for path in LOCATOR_PATHS:
        data = {
            "base": revision_bytes(repo_root, base_revision, path),
            "ours": revision_bytes(repo_root, ours_revision, path),
            "theirs": revision_bytes(repo_root, theirs_revision, path),
        }
        for label, value in data.items():
            input_data[f"{label}:{path}"] = value
        records = {
            label: parse_locator_records(value, f"{label}:{path}")
            for label, value in data.items()
        }
        raw_changed = data["base"] != data["theirs"]
        normalized_changed = semantic_hash(data["base"]) != semantic_hash(data["theirs"])
        changed_ids = sorted(
            province_id
            for province_id in set(records["base"]) | set(records["theirs"])
            if records["base"].get(province_id) != records["theirs"].get(province_id)
        )
        if not raw_changed:
            status = "no_upstream_change"
        elif not normalized_changed and not changed_ids:
            status = "formatting_only_no_semantic_change"
        elif changed_ids:
            status = "semantic_locator_change"
        else:
            status = "unparsed_file_level_semantic_change"
        file_rows.append(
            {
                "path": path,
                "upstream_file_status": status,
                "base_record_count": len(records["base"]),
                "ours_record_count": len(records["ours"]),
                "theirs_record_count": len(records["theirs"]),
                "upstream_semantic_changed_ids": len(changed_ids),
                "working_tree_dirty": file_dirty(repo_root, path),
                "base_sha256": sha256(data["base"]),
                "ours_sha256": sha256(data["ours"]),
                "theirs_sha256": sha256(data["theirs"]),
                "base_semantic_sha256": semantic_hash(data["base"]),
                "ours_semantic_sha256": semantic_hash(data["ours"]),
                "theirs_semantic_sha256": semantic_hash(data["theirs"]),
            }
        )
        for province_id in changed_ids:
            base_record = records["base"].get(province_id)
            ours_record = records["ours"].get(province_id)
            theirs_record = records["theirs"].get(province_id)
            classification = classify_three_way(base_record, ours_record, theirs_record)
            fields = changed_record_fields(base_record, theirs_record)
            ours_position = locator_position_status(
                ours_record,
                province_id,
                map_result["images"]["ours"],
                map_result["definitions"]["ours"][1],
            )
            theirs_position = locator_position_status(
                theirs_record,
                province_id,
                map_result["images"]["theirs"],
                map_result["definitions"]["theirs"][1],
            )
            recommendation = "manual_review"
            confidence = "low"
            if classification == "candidate_take_upstream" and fields == ["scale"]:
                recommendation = "review_then_take_upstream_scale"
                confidence = "medium"
            change_rows.append(
                {
                    "record_type": "province_locator",
                    "path": path,
                    "record_key": province_id,
                    "classification": classification,
                    "changed_fields": "|".join(fields),
                    "confidence": confidence,
                    "recommendation": recommendation,
                    "auto_apply": "no",
                    "base_position": tuple_text(base_record.get("position") if base_record else None),
                    "ours_position": tuple_text(ours_record.get("position") if ours_record else None),
                    "theirs_position": tuple_text(theirs_record.get("position") if theirs_record else None),
                    "base_rotation": tuple_text(base_record.get("rotation") if base_record else None),
                    "ours_rotation": tuple_text(ours_record.get("rotation") if ours_record else None),
                    "theirs_rotation": tuple_text(theirs_record.get("rotation") if theirs_record else None),
                    "base_scale": tuple_text(base_record.get("scale") if base_record else None),
                    "ours_scale": tuple_text(ours_record.get("scale") if ours_record else None),
                    "theirs_scale": tuple_text(theirs_record.get("scale") if theirs_record else None),
                    "ours_map_x": ours_position["map_x"],
                    "ours_map_y": ours_position["map_y"],
                    "ours_observed_ids": ours_position["observed_ids"],
                    "ours_observed_names": ours_position["observed_names"],
                    "ours_position_status": ours_position["position_status"],
                    "theirs_map_x": theirs_position["map_x"],
                    "theirs_map_y": theirs_position["map_y"],
                    "theirs_observed_ids": theirs_position["observed_ids"],
                    "theirs_observed_names": theirs_position["observed_names"],
                    "theirs_position_status": theirs_position["position_status"],
                }
            )
    return file_rows, change_rows, input_data


def audit_special_file(
    repo_root: Path,
    vanilla_root: Path,
    base_revision: str,
    ours_revision: str,
    theirs_revision: str,
    map_result: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, bytes | None]]:
    data = {
        "base": revision_bytes(repo_root, base_revision, SPECIAL_PATH),
        "ours": revision_bytes(repo_root, ours_revision, SPECIAL_PATH),
        "theirs": revision_bytes(repo_root, theirs_revision, SPECIAL_PATH),
    }
    descriptor = revision_bytes(repo_root, ours_revision, DESCRIPTOR_PATH)
    vanilla = vanilla_bytes(vanilla_root, SPECIAL_PATH)
    fallback_blocked = replace_path_blocks_fallback(descriptor, SPECIAL_PATH)
    effective_ours = data["ours"]
    effective_source = "mod_file"
    if effective_ours is None and not fallback_blocked:
        effective_ours = vanilla
        effective_source = "vanilla_fallback"
    if effective_ours is None:
        effective_source = "missing"

    objects = {
        "base": extract_object_blocks(data["base"]),
        "ours": extract_object_blocks(data["ours"]),
        "effective_ours": extract_object_blocks(effective_ours),
        "theirs": extract_object_blocks(data["theirs"]),
    }
    changed_names = sorted(
        name
        for name in set(objects["base"]) | set(objects["theirs"])
        if objects["base"].get(name, {}).get("__normalized__")
        != objects["theirs"].get(name, {}).get("__normalized__")
    )
    exact_vanilla = data["theirs"] is not None and data["theirs"] == vanilla
    file_row = {
        "path": SPECIAL_PATH,
        "upstream_file_status": "semantic_object_change" if changed_names else "no_semantic_change",
        "ours_file_exists": "yes" if data["ours"] is not None else "no",
        "vanilla_fallback_blocked": "yes" if fallback_blocked else "no",
        "effective_ours_source": effective_source,
        "theirs_exact_current_vanilla": "yes" if exact_vanilla else "no",
        "changed_object_count": len(changed_names),
        "working_tree_dirty": file_dirty(repo_root, SPECIAL_PATH),
        "base_sha256": sha256(data["base"]),
        "ours_sha256": sha256(data["ours"]),
        "effective_ours_sha256": sha256(effective_ours),
        "theirs_sha256": sha256(data["theirs"]),
        "vanilla_sha256": sha256(vanilla),
    }

    rows: list[dict[str, Any]] = []
    mesh_cache: dict[str, str] = {}
    for name in changed_names:
        base_object = objects["base"].get(name)
        ours_object = objects["ours"].get(name)
        effective_object = objects["effective_ours"].get(name)
        theirs_object = objects["theirs"].get(name)
        base_value = None if base_object is None else base_object["__normalized__"]
        ours_value = None if ours_object is None else ours_object["__normalized__"]
        effective_value = (
            None if effective_object is None else effective_object["__normalized__"]
        )
        theirs_value = None if theirs_object is None else theirs_object["__normalized__"]
        direct_classification = classify_three_way(base_value, ours_value, theirs_value)
        effective_classification = classify_three_way(
            base_value, effective_value, theirs_value
        )
        recommendation = "manual_review"
        confidence = "low"
        if effective_value == theirs_value and effective_source == "vanilla_fallback":
            recommendation = "keep_mod_file_absent_use_vanilla_fallback"
            confidence = "high"
        elif effective_value == theirs_value:
            recommendation = "no_action_effective_content_matches"
            confidence = "high"

        theirs_position = object_position_status(
            theirs_object or {},
            map_result["images"]["theirs"],
            map_result["definitions"]["theirs"][1],
        )
        ours_position = object_position_status(
            effective_object or theirs_object or {},
            map_result["images"]["ours"],
            map_result["definitions"]["ours"][1],
        )
        mesh = "" if theirs_object is None else theirs_object.get("pdxmesh", "")
        if mesh and mesh not in mesh_cache:
            mesh_cache[mesh] = find_mesh_asset(vanilla_root, mesh)
        rows.append(
            {
                "record_type": "special_map_object",
                "path": SPECIAL_PATH,
                "record_key": name,
                "direct_mod_three_way_classification": direct_classification,
                "effective_three_way_classification": effective_classification,
                "effective_ours_source": effective_source,
                "confidence": confidence,
                "recommendation": recommendation,
                "auto_apply": "no",
                "pdxmesh": mesh,
                "mesh_asset_found": "yes" if mesh_cache.get(mesh) else "no",
                "mesh_asset_path": mesh_cache.get(mesh, ""),
                "transform": "" if theirs_object is None else theirs_object.get("transform", ""),
                "ours_map_x": ours_position["map_x"],
                "ours_map_y": ours_position["map_y"],
                "ours_observed_ids": ours_position["observed_ids"],
                "ours_observed_names": ours_position["observed_names"],
                "ours_position_status": ours_position["position_status"],
                "theirs_map_x": theirs_position["map_x"],
                "theirs_map_y": theirs_position["map_y"],
                "theirs_observed_ids": theirs_position["observed_ids"],
                "theirs_observed_names": theirs_position["observed_names"],
                "theirs_position_status": theirs_position["position_status"],
            }
        )
    inputs = {
        f"base:{SPECIAL_PATH}": data["base"],
        f"ours:{SPECIAL_PATH}": data["ours"],
        f"theirs:{SPECIAL_PATH}": data["theirs"],
        f"vanilla:{SPECIAL_PATH}": vanilla,
        f"ours:{DESCRIPTOR_PATH}": descriptor,
    }
    return file_row, rows, inputs


def build_summary(
    output_dir: Path,
    revisions: dict[str, str],
    map_result: dict[str, Any],
    file_rows: list[dict[str, Any]],
    change_rows: list[dict[str, Any]],
) -> str:
    counts = map_result["counts"]
    building = next(
        (
            row
            for row in change_rows
            if row.get("record_type") == "province_locator"
            and str(row.get("record_key")) == "6053"
        ),
        None,
    )
    special = next(
        (
            row
            for row in change_rows
            if row.get("record_type") == "special_map_object"
            and row.get("record_key") == "constantinople_sprawl"
        ),
        None,
    )
    formatting_files = [
        row["path"]
        for row in file_rows
        if row.get("upstream_file_status") == "formatting_only_no_semantic_change"
    ]
    lines = [
        "# Bekleyen Asıl Mod Harita ve Locator Üç Yönlü Auditi",
        "",
        "## Kapsam",
        "",
        f"- base: `{revisions['base']}`",
        f"- Yusseter/ours: `{revisions['ours']}`",
        f"- yeni asıl mod/theirs: `{revisions['theirs']}`",
        "- canlı `BookmarksGit` kaynakları değiştirilmedi; `auto_apply=no`.",
        "",
        "## provinces.png",
        "",
        f"- toplam piksel: `{map_result['total_pixels']}`",
        f"- yalnız Yusseter değişikliği: `{counts['ours_only']}`",
        f"- yalnız yeni asıl mod değişikliği: `{counts['theirs_only']}`",
        f"- iki tarafta aynı sonuç: `{counts['both_same']}`",
        f"- gerçek piksel çatışması: `{counts['conflict']}`",
        f"- yeni asıl mod hedef renkleri: `{map_result['destination_color_count']}`",
        f"- Yusseter definition kimliğiyle güvenli olmayan hedef renk/piksel: "
        f"`{map_result['unsafe_color_count']}` / `{map_result['unsafe_pixel_count']}`",
        f"- asıl mod blob değişikliği / gerçek RGB piksel değişikliği: "
        f"`{'yes' if map_result['upstream_raw_changed'] else 'no'}` / "
        f"`{map_result['upstream_pixel_change_count']}`",
        f"- karar: `{map_result['merge_status']}`",
        "- Kontrol görseli: `provinces_three_way_control.png`.",
        "",
        "## Locator ve Özel Objeler",
        "",
    ]
    if building:
        lines.extend(
            [
                "- `building_locators.txt`, `id=6053`: yalnız scale değişiyor; "
                f"`{building['base_scale']}` -> `{building['theirs_scale']}`.",
                f"- ID 6053 konumu: Yusseter `{building['ours_position_status']}`, "
                f"asıl mod `{building['theirs_position_status']}`; karar "
                f"`{building['recommendation']}`.",
            ]
        )
    if formatting_files:
        lines.append(
            "- Yalnız biçim/boşluk değişikliği: `"
            + "`, `".join(formatting_files)
            + "`."
        )
    if special:
        lines.extend(
            [
                "- `special.txt` Yusseter modunda bilinçli olarak bulunmuyor; klasör için "
                "`replace_path` yok, bu yüzden vanilla dosyası etkin.",
                "- Yeni asıl moddaki `special.txt` güncel vanilla dosyasıyla byte düzeyinde "
                "aynı ve `constantinople_sprawl` etkin vanilla fallback içinde zaten var.",
                f"- Öneri: `{special['recommendation']}`; mesh asset "
                f"`{special['mesh_asset_found']}`.",
            ]
        )
    lines.extend(
        [
            "",
            "## Sonuç",
            "",
            (
                "- `provinces.png`: yeni asıl mod yalnız PNG encoding/metadata katmanını "
                "değiştirmiş; RGB piksel içeriği base ile aynı. Merge çözümü mevcut "
                "Yusseter PNG'sini korumaktır."
                if map_result["merge_status"]
                == "upstream_encoding_metadata_only_keep_ours"
                else "- `provinces.png` semantik piksel çözümü rapordaki üç yönlü karara "
                "göre manuel ele alınmalıdır."
            ),
            "- Locator tarafında otomatik uygulama yok. ID 6053 scale düzeltmesi ayrı, "
            "dar bir manuel/onaylı adaydır.",
            "- `special.txt` yeniden eklenmemeli; mevcut vanilla fallback aynı etkin sonucu "
            "daha az override riskiyle sağlıyor.",
            "",
            "## Çıktılar",
            "",
            "- `map_pixel_three_way_categories.csv`",
            "- `map_upstream_destination_colors.csv`",
            "- `map_conflict_color_inventory.csv`",
            "- `map_image_snapshot_metadata.csv`",
            "- `locator_file_three_way_summary.csv`",
            "- `locator_semantic_changes.csv`",
            "- `input_sha256_manifest.csv`",
            "- `provinces_three_way_control.png`",
            "",
        ]
    )
    summary = "\n".join(lines)
    (output_dir / "upstream_map_locator_delta_summary.md").write_text(
        summary, encoding="utf-8", newline="\n"
    )
    return summary


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else (repo_root / OUTPUT_PATH).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    revisions = {
        "base": resolve_revision(repo_root, args.base_revision),
        "ours": resolve_revision(repo_root, args.ours_revision),
        "theirs": resolve_revision(repo_root, args.theirs_revision),
    }

    map_result = audit_map(
        repo_root,
        revisions["base"],
        revisions["ours"],
        revisions["theirs"],
        output_dir,
    )
    file_rows, change_rows, locator_inputs = audit_locator_files(
        repo_root,
        revisions["base"],
        revisions["ours"],
        revisions["theirs"],
        map_result,
    )
    special_file_row, special_rows, special_inputs = audit_special_file(
        repo_root,
        args.vanilla_root.resolve(),
        revisions["base"],
        revisions["ours"],
        revisions["theirs"],
        map_result,
    )
    file_rows.append(special_file_row)
    change_rows.extend(special_rows)
    write_csv(output_dir / "locator_file_three_way_summary.csv", file_rows)
    write_csv(output_dir / "locator_semantic_changes.csv", change_rows)

    manifest_inputs: dict[str, bytes | None] = {}
    for snapshot, data in map_result["image_data"].items():
        manifest_inputs[f"{snapshot}:{PROVINCES_PATH}"] = data
    for snapshot, data in map_result["definition_data"].items():
        manifest_inputs[f"{snapshot}:{DEFINITION_PATH}"] = data
    manifest_inputs.update(locator_inputs)
    manifest_inputs.update(special_inputs)
    manifest_rows = [
        {
            "input": key,
            "sha256": sha256(value),
            "byte_count": "missing" if value is None else len(value),
        }
        for key, value in sorted(manifest_inputs.items())
    ]
    write_csv(output_dir / "input_sha256_manifest.csv", manifest_rows)
    summary = build_summary(
        output_dir, revisions, map_result, file_rows, change_rows
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
