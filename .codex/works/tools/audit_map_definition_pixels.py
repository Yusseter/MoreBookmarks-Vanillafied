from __future__ import annotations

import argparse
import csv
import re
import subprocess
import tarfile
from array import array
from collections import Counter, defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

import audit_map_object_locator_positions as locator_audit


OUTPUT_PATH = Path(
    ".codex/works/analysis/generated/repo_integration_closure/"
    "map_definition_pixel_audit"
)
DEFAULT_BASE_REVISION = "09588cbb5212a31bc4a373b6990b2c4da1203a35"
TOP_LEVEL_ID_RE = re.compile(r"(?m)^\s*(\d+)\s*=\s*\{")
PROVINCE_ASSIGNMENT_RE = re.compile(r"\bprovince\s*=\s*(\d+)\b")
LOCATOR_ID_RE = re.compile(r"(?m)^\s*id\s*=\s*(\d+)\b")
DEFAULT_MAP_ENTRY_RE = re.compile(
    r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(LIST|RANGE)\s*\{([^}]*)\}"
)
PROVINCES_BLOCK_RE = re.compile(r"\bprovinces\s*=\s*\{([^}]*)\}", re.DOTALL)
INTEGER_RE = re.compile(r"\b\d+\b")


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def find_asil_mod_repo(project_root: Path) -> Path | None:
    candidate = project_root.parent / "Leviathonlx MoreBookmarks-Plus"
    return candidate if (candidate / "BookmarksGit").is_dir() else None


def parse_args() -> argparse.Namespace:
    project_root = find_project_root()
    parser = argparse.ArgumentParser(
        description="Audit global definition.csv and provinces.png identity/topology"
    )
    parser.add_argument("--repo-root", type=Path, default=project_root)
    parser.add_argument("--asil-mod-repo", type=Path, default=find_asil_mod_repo(project_root))
    parser.add_argument("--baseline-revision", default=DEFAULT_BASE_REVISION)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--tiny-pixel-threshold", type=int, default=8)
    parser.add_argument("--skip-topology", action="store_true")
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def image_color_counts(path: Path) -> Counter[tuple[int, int, int]]:
    with Image.open(path) as source:
        return Counter(source.convert("RGB").getdata())


def parse_definition_text(text: str) -> dict[int, dict[str, Any]]:
    definition: dict[int, dict[str, Any]] = {}
    for row in csv.reader(text.splitlines(), delimiter=";"):
        if len(row) < 5:
            continue
        try:
            province_id = int(row[0])
            rgb = (int(row[1]), int(row[2]), int(row[3]))
        except ValueError:
            continue
        definition[province_id] = {
            "id": province_id,
            "rgb": rgb,
            "rgb_text": locator_audit.rgb_to_text(rgb),
            "name": row[4],
        }
    return definition


def revision_definition(repo_root: Path, revision: str) -> dict[int, dict[str, Any]]:
    if not revision:
        return {}
    try:
        text = subprocess.check_output(
            ["git", "show", f"{revision}:BookmarksGit/map_data/definition.csv"],
            cwd=repo_root,
            text=True,
            encoding="utf-8-sig",
            errors="replace",
        )
    except subprocess.CalledProcessError:
        return {}
    return parse_definition_text(text)


def revision_image_color_counts(
    repo_root: Path,
    revision: str,
) -> Counter[tuple[int, int, int]]:
    if not revision:
        return Counter()
    try:
        data = subprocess.check_output(
            ["git", "show", f"{revision}:BookmarksGit/map_data/provinces.png"],
            cwd=repo_root,
        )
    except subprocess.CalledProcessError:
        return Counter()
    with Image.open(BytesIO(data)) as source:
        return Counter(source.convert("RGB").getdata())


def add_reference(
    references: dict[int, set[str]],
    province_id: int,
    label: str,
) -> None:
    references[province_id].add(label)


def strip_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def add_text_references(
    references: dict[int, set[str]],
    relative_path: str,
    text: str,
) -> None:
    normalized = relative_path.replace("\\", "/")
    text = strip_comments(text)

    if normalized.startswith("BookmarksGit/common/landed_titles/"):
        for match in PROVINCE_ASSIGNMENT_RE.finditer(text):
            add_reference(references, int(match.group(1)), "landed_titles")
        return

    if normalized.startswith("BookmarksGit/history/provinces/"):
        for match in TOP_LEVEL_ID_RE.finditer(text):
            add_reference(references, int(match.group(1)), "province_history")
        return

    if normalized.startswith("BookmarksGit/gfx/map/map_object_data/"):
        for match in LOCATOR_ID_RE.finditer(text):
            add_reference(references, int(match.group(1)), "map_object_locator")
        return

    if normalized == "BookmarksGit/map_data/default.map":
        for key, entry_type, block in DEFAULT_MAP_ENTRY_RE.findall(text):
            values = [int(value) for value in INTEGER_RE.findall(block)]
            province_ids = values
            if entry_type == "RANGE" and len(values) >= 2:
                province_ids = list(
                    range(min(values[0], values[1]), max(values[0], values[1]) + 1)
                )
            for province_id in province_ids:
                add_reference(references, province_id, f"default_map:{key}")
        return

    if normalized == "BookmarksGit/map_data/adjacencies.csv":
        for row in csv.reader(text.splitlines(), delimiter=";"):
            for value in row[:2]:
                value = value.strip()
                if value.isdigit():
                    add_reference(references, int(value), "adjacency_endpoint")
        return

    if normalized.startswith("BookmarksGit/common/province_terrain/"):
        for match in re.finditer(r"(?m)^\s*(\d+)\s*=", text):
            add_reference(references, int(match.group(1)), "province_terrain")
        return

    if normalized.startswith("BookmarksGit/map_data/geographical_regions/"):
        for block in PROVINCES_BLOCK_RE.findall(text):
            for value in INTEGER_RE.findall(block):
                add_reference(references, int(value), "geographical_region")


REFERENCE_PATHS = [
    "BookmarksGit/common/landed_titles",
    "BookmarksGit/history/provinces",
    "BookmarksGit/gfx/map/map_object_data",
    "BookmarksGit/map_data/default.map",
    "BookmarksGit/map_data/adjacencies.csv",
    "BookmarksGit/common/province_terrain",
    "BookmarksGit/map_data/geographical_regions",
]


def collect_reference_index(mod_root: Path) -> dict[int, set[str]]:
    project_root = mod_root.parent
    references: dict[int, set[str]] = defaultdict(set)

    for path in (mod_root / "common/landed_titles").glob("*.txt"):
        add_text_references(
            references,
            path.relative_to(project_root).as_posix(),
            path.read_text(encoding="utf-8-sig", errors="replace"),
        )

    for path in (mod_root / "history/provinces").rglob("*.txt"):
        add_text_references(
            references,
            path.relative_to(project_root).as_posix(),
            path.read_text(encoding="utf-8-sig", errors="replace"),
        )

    for path in (mod_root / "gfx/map/map_object_data").glob("*.txt"):
        add_text_references(
            references,
            path.relative_to(project_root).as_posix(),
            path.read_text(encoding="utf-8-sig", errors="replace"),
        )

    default_map = mod_root / "map_data/default.map"
    if default_map.exists():
        add_text_references(
            references,
            default_map.relative_to(project_root).as_posix(),
            default_map.read_text(encoding="utf-8-sig", errors="replace"),
        )

    adjacencies = mod_root / "map_data/adjacencies.csv"
    if adjacencies.exists():
        add_text_references(
            references,
            adjacencies.relative_to(project_root).as_posix(),
            adjacencies.read_text(encoding="utf-8-sig", errors="replace"),
        )

    for path in (mod_root / "common/province_terrain").rglob("*.txt"):
        add_text_references(
            references,
            path.relative_to(project_root).as_posix(),
            path.read_text(encoding="utf-8-sig", errors="replace"),
        )

    for path in (mod_root / "map_data/geographical_regions").rglob("*.txt"):
        add_text_references(
            references,
            path.relative_to(project_root).as_posix(),
            path.read_text(encoding="utf-8-sig", errors="replace"),
        )

    return references


def revision_reference_index(
    repo_root: Path,
    revision: str,
) -> dict[int, set[str]]:
    references: dict[int, set[str]] = defaultdict(set)
    if not revision:
        return references
    try:
        archive = subprocess.check_output(
            ["git", "archive", "--format=tar", revision, *REFERENCE_PATHS],
            cwd=repo_root,
        )
    except subprocess.CalledProcessError:
        return references
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as handle:
        for member in handle.getmembers():
            if not member.isfile():
                continue
            extracted = handle.extractfile(member)
            if extracted is None:
                continue
            text = extracted.read().decode("utf-8-sig", errors="replace")
            add_text_references(references, member.name, text)
    return references


def read_relation_master(repo_root: Path) -> dict[int, dict[str, str]]:
    path = repo_root / (
        ".codex/works/pipeline_inputs/province_relations/"
        "province_relation_baseline.csv"
    )
    if not path.exists():
        return {}
    rows: dict[int, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            value = row.get("source_province_id", "").strip()
            if value.isdigit():
                rows[int(value)] = row
    return rows


def infer_palette_bounds(
    image: Image.Image,
    color_counts: Counter[tuple[int, int, int]],
    definition: dict[int, dict[str, Any]],
    defined_rgbs: set[tuple[int, int, int]],
) -> tuple[int, int, int, int] | None:
    placeholder_rgbs = {
        tuple(meta["rgb"])
        for meta in definition.values()
        if str(meta["name"]).startswith("zz_placeholder_")
        and color_counts.get(tuple(meta["rgb"]), 0) == 1
    }
    orphan_singletons = {
        rgb for rgb, count in color_counts.items()
        if rgb not in defined_rgbs and count == 1
    }
    candidate_rgbs = placeholder_rgbs | orphan_singletons
    if len(candidate_rgbs) < 100:
        return None

    points: list[tuple[int, int]] = []
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            if pixels[x, y] in candidate_rgbs:
                points.append((x, y))

    if len(points) < 100:
        return None
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    if max_x != image.width - 1 or max_y != image.height - 1:
        return None
    if image.width - min_x > 128 or image.height - min_y > 128:
        return None
    return min_x, min_y, max_x, max_y


def palette_color_counts(
    image: Image.Image,
    bounds: tuple[int, int, int, int] | None,
) -> Counter[tuple[int, int, int]]:
    if bounds is None:
        return Counter()
    min_x, min_y, max_x, max_y = bounds
    return Counter(image.crop((min_x, min_y, max_x + 1, max_y + 1)).getdata())


def analyze_components(
    image: Image.Image,
    palette_bounds: tuple[int, int, int, int] | None,
) -> tuple[Counter[int], dict[int, int]]:
    rgba = image.convert("RGBA")
    raw_bytes = rgba.tobytes()
    pixels = memoryview(raw_bytes).cast("I")
    width = image.width
    height = image.height

    parent = array("I")
    rank = array("B")
    total_pixels = array("I")
    outside_pixels = array("I")
    colors = array("I")

    def find(node: int) -> int:
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != node:
            next_node = parent[node]
            parent[node] = root
            node = next_node
        return root

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if rank[left_root] < rank[right_root]:
            left_root, right_root = right_root, left_root
        parent[right_root] = left_root
        total_pixels[left_root] += total_pixels[right_root]
        outside_pixels[left_root] += outside_pixels[right_root]
        if rank[left_root] == rank[right_root]:
            rank[left_root] += 1

    previous_runs: list[tuple[int, int, int, int]] = []
    for y in range(height):
        row_offset = y * width
        current_runs: list[tuple[int, int, int, int]] = []
        start = 0
        color = int(pixels[row_offset])
        for x in range(1, width + 1):
            next_color = int(pixels[row_offset + x]) if x < width else -1
            if next_color == color:
                continue

            end = x - 1
            run_length = end - start + 1
            palette_overlap = 0
            if palette_bounds is not None:
                min_x, min_y, max_x, max_y = palette_bounds
                if min_y <= y <= max_y:
                    overlap_start = max(start, min_x)
                    overlap_end = min(end, max_x)
                    if overlap_start <= overlap_end:
                        palette_overlap = overlap_end - overlap_start + 1

            segment_id = len(parent)
            parent.append(segment_id)
            rank.append(0)
            total_pixels.append(run_length)
            outside_pixels.append(run_length - palette_overlap)
            colors.append(color)
            current_runs.append((start, end, color, segment_id))
            start = x
            color = next_color

        previous_index = 0
        for start, end, color, segment_id in current_runs:
            while (
                previous_index < len(previous_runs)
                and previous_runs[previous_index][1] < start
            ):
                previous_index += 1
            candidate_index = previous_index
            while (
                candidate_index < len(previous_runs)
                and previous_runs[candidate_index][0] <= end
            ):
                _, _, previous_color, previous_segment = previous_runs[candidate_index]
                if previous_color == color:
                    union(segment_id, previous_segment)
                candidate_index += 1
        previous_runs = current_runs

    component_counts: Counter[int] = Counter()
    largest_components: dict[int, int] = defaultdict(int)
    for segment_id in range(len(parent)):
        if parent[segment_id] != segment_id or outside_pixels[segment_id] == 0:
            continue
        color = int(colors[segment_id])
        component_counts[color] += 1
        largest_components[color] = max(
            largest_components[color], int(outside_pixels[segment_id])
        )
    return component_counts, dict(largest_components)


def encode_rgb(rgb: tuple[int, int, int]) -> int:
    return 0xFF000000 | rgb[0] | (rgb[1] << 8) | (rgb[2] << 16)


def render_orphan_overlay(
    image: Image.Image,
    orphan_rgbs: set[tuple[int, int, int]],
    output_path: Path,
) -> None:
    source = image.convert("RGB")
    scale = 0.5
    background = source.resize(
        (round(source.width * scale), round(source.height * scale)),
        Image.Resampling.BILINEAR,
    )
    mask = Image.new("L", source.size, 0)
    mask.putdata([255 if rgb in orphan_rgbs else 0 for rgb in source.getdata()])
    mask = mask.resize(background.size, Image.Resampling.NEAREST)
    red = Image.new("RGB", background.size, (255, 30, 30))
    Image.composite(red, background, mask).save(output_path, optimize=True)


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    mod_root = repo_root / "BookmarksGit"
    output_dir = args.output_dir or (repo_root / OUTPUT_PATH)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    definition, rgb_to_ids = locator_audit.read_definition(
        mod_root / "map_data/definition.csv"
    )
    image = Image.open(mod_root / "map_data/provinces.png").convert("RGB")
    color_counts = Counter(image.getdata())
    defined_rgbs = set(rgb_to_ids)
    palette_bounds = infer_palette_bounds(image, color_counts, definition, defined_rgbs)
    palette_counts = palette_color_counts(image, palette_bounds)
    references = collect_reference_index(mod_root)
    baseline_references = revision_reference_index(repo_root, args.baseline_revision)
    relation_master = read_relation_master(repo_root)

    asil_counts: Counter[tuple[int, int, int]] = Counter()
    asil_definition: dict[int, dict[str, Any]] = {}
    if args.asil_mod_repo is not None:
        asil_mod_root = args.asil_mod_repo.resolve() / "BookmarksGit"
        asil_map = asil_mod_root / "map_data/provinces.png"
        if asil_map.exists():
            asil_counts = image_color_counts(asil_map)
        asil_definition_path = asil_mod_root / "map_data/definition.csv"
        if asil_definition_path.exists():
            asil_definition, _ = locator_audit.read_definition(asil_definition_path)
    baseline_definition = revision_definition(repo_root, args.baseline_revision)
    baseline_counts = revision_image_color_counts(repo_root, args.baseline_revision)

    component_counts: Counter[int] = Counter()
    largest_components: dict[int, int] = {}
    if not args.skip_topology:
        component_counts, largest_components = analyze_components(image, palette_bounds)

    definition_rows: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    for province_id, meta in sorted(definition.items()):
        rgb = tuple(meta["rgb"])
        total_pixel_count = color_counts.get(rgb, 0)
        palette_pixel_count = palette_counts.get(rgb, 0)
        map_pixel_count = total_pixel_count - palette_pixel_count
        duplicate_ids = sorted(rgb_to_ids[rgb])
        ref_labels = sorted(references.get(province_id, set()))
        baseline_ref_labels = sorted(baseline_references.get(province_id, set()))
        geometry_reference_labels = [
            label for label in ref_labels
            if label in {
                "landed_titles",
                "province_history",
                "map_object_locator",
                "adjacency_endpoint",
                "geographical_region",
                "default_map:sea_zones",
                "default_map:river_provinces",
                "default_map:lakes",
                "default_map:impassable_seas",
            }
        ]
        only_impassable_registration = bool(ref_labels) and all(
            label in {"default_map:impassable_mountains", "province_terrain"}
            for label in ref_labels
        )
        relation = relation_master.get(province_id, {})
        relation_target_text = relation.get("target_province_id", "").strip()
        relation_target_id = (
            int(relation_target_text) if relation_target_text.isdigit() else None
        )
        relation_target_meta = (
            definition.get(relation_target_id) if relation_target_id is not None else None
        )
        relation_target_rgb = (
            tuple(relation_target_meta["rgb"]) if relation_target_meta else None
        )
        relation_target_pixels = (
            color_counts.get(relation_target_rgb, 0)
            - palette_counts.get(relation_target_rgb, 0)
            if relation_target_rgb is not None else 0
        )
        baseline_meta = baseline_definition.get(province_id)
        baseline_rgb = tuple(baseline_meta["rgb"]) if baseline_meta else None
        baseline_pixel_count = (
            baseline_counts.get(baseline_rgb, 0) if baseline_rgb is not None else 0
        )
        if (
            baseline_meta
            and str(baseline_meta["name"]).startswith("zz_placeholder_")
            and baseline_pixel_count == 1
        ):
            baseline_pixel_count = 0
        asil_meta = asil_definition.get(province_id)
        asil_rgb = tuple(asil_meta["rgb"]) if asil_meta else None
        asil_pixel_count = asil_counts.get(asil_rgb, 0) if asil_rgb is not None else 0
        encoded = encode_rgb(rgb)
        component_count = component_counts.get(encoded, 0)
        largest_component = largest_components.get(encoded, 0)
        fragment_pixels = max(0, map_pixel_count - largest_component)
        is_placeholder = str(meta["name"]).startswith("zz_placeholder_")

        if len(duplicate_ids) > 1:
            status = "duplicate_definition_rgb"
            severity = "blocker"
            provenance = "current_definition"
        elif province_id == 0 and map_pixel_count == 0:
            status = "expected_zero_sentinel"
            severity = "info"
            provenance = "expected_engine_sentinel"
        elif map_pixel_count == 0 and palette_pixel_count > 0 and not ref_labels:
            status = (
                "reserved_palette_placeholder"
                if is_placeholder else "reserved_palette_entry"
            )
            severity = "info"
            provenance = "intentional_palette"
        elif (
            map_pixel_count == 0
            and is_placeholder
            and only_impassable_registration
        ):
            status = "reserved_placeholder_impassable_registration"
            severity = "info"
            provenance = "intentional_placeholder_policy"
        elif map_pixel_count == 0 and geometry_reference_labels:
            current_content_refs = {
                "landed_titles", "province_history", "map_object_locator"
            }.intersection(geometry_reference_labels)
            if current_content_refs:
                status = "current_content_reference_missing_pixels"
                severity = "blocker"
            elif is_placeholder and relation:
                if relation.get("status") == "mapped":
                    status = "source_semantic_reference_requires_remap"
                    severity = "blocker"
                else:
                    status = "source_semantic_reference_relation_review"
                    severity = "review"
            else:
                status = "semantic_reference_missing_pixels_unmapped_review"
                severity = "review"
            provenance = (
                "post_baseline_integration"
                if not baseline_ref_labels else "preexisting_yusseter"
            )
        elif map_pixel_count == 0 and ref_labels:
            status = "missing_pixels_non_geometry_reference_review"
            severity = "review"
            provenance = (
                "post_baseline_integration"
                if not baseline_ref_labels else "preexisting_yusseter"
            )
        elif map_pixel_count == 0 and baseline_pixel_count > 0:
            status = "missing_pixels_since_baseline"
            severity = "blocker"
            provenance = "post_baseline_regression"
        elif map_pixel_count == 0 and asil_pixel_count > 0:
            status = "source_only_definition_after_remap_review"
            severity = "review"
            provenance = "preexisting_yusseter_source_divergence"
        elif map_pixel_count == 0:
            status = "unused_definition_without_pixels_review"
            severity = "review"
            provenance = "shared_or_preexisting"
        elif map_pixel_count <= args.tiny_pixel_threshold:
            status = "tiny_map_geometry_review"
            severity = "review"
            provenance = (
                "preexisting_yusseter"
                if baseline_pixel_count == map_pixel_count else "current_map"
            )
        elif not args.skip_topology and component_count > 1:
            status = "multipart_map_geometry_review"
            severity = "review"
            provenance = "current_map"
        else:
            status = "present"
            severity = "info"
            provenance = "current_map"

        row = {
            "province_id": province_id,
            "province_name": meta["name"],
            "rgb": meta["rgb_text"],
            "total_pixel_count": total_pixel_count,
            "palette_pixel_count": palette_pixel_count,
            "map_pixel_count": map_pixel_count,
            "baseline_rgb": (
                locator_audit.rgb_to_text(baseline_rgb) if baseline_rgb else ""
            ),
            "baseline_pixel_count": baseline_pixel_count,
            "asil_mod_rgb": locator_audit.rgb_to_text(asil_rgb) if asil_rgb else "",
            "asil_mod_pixel_count": asil_pixel_count,
            "definition_ids_for_rgb": "|".join(map(str, duplicate_ids)),
            "active_references": "|".join(ref_labels),
            "geometry_references": "|".join(geometry_reference_labels),
            "baseline_references": "|".join(baseline_ref_labels),
            "relation_target_id": relation_target_id or "",
            "relation_target_name": relation.get("target_name", ""),
            "relation_target_map_pixels": relation_target_pixels,
            "relation_classification": relation.get("classification", ""),
            "relation_confidence": relation.get("confidence", ""),
            "relation_status": relation.get("status", ""),
            "component_count": component_count,
            "largest_component_pixels": largest_component,
            "fragment_pixels": fragment_pixels,
            "status": status,
            "severity": severity,
            "provenance": provenance,
        }
        definition_rows.append(row)
        if severity in {"blocker", "review"}:
            findings.append(
                {
                    "domain": "binary_map",
                    "subdomain": "provinces_png",
                    "severity": severity,
                    "classification": status,
                    "province_id": province_id,
                    "province_name": meta["name"],
                    "rgb": meta["rgb_text"],
                    "provenance": provenance,
                    "details": (
                        f"map_pixels={map_pixel_count}; components={component_count}; "
                        f"references={'|'.join(ref_labels)}; "
                        f"baseline_references={'|'.join(baseline_ref_labels)}; "
                        f"relation_target={relation_target_id or ''}; "
                        f"relation_status={relation.get('status', '')}"
                    ),
                }
            )

    orphan_rows: list[dict[str, object]] = []
    non_palette_orphans: set[tuple[int, int, int]] = set()
    for rgb, total_count in sorted(
        color_counts.items(), key=lambda item: (-item[1], item[0])
    ):
        if rgb in defined_rgbs:
            continue
        palette_count = palette_counts.get(rgb, 0)
        map_count = total_count - palette_count
        if map_count == 0:
            status = "reserved_palette_rgb"
            severity = "info"
            provenance = "intentional_palette"
        else:
            status = "map_rgb_missing_definition"
            severity = "blocker"
            provenance = "current_map"
            non_palette_orphans.add(rgb)
            findings.append(
                {
                    "domain": "binary_map",
                    "subdomain": "provinces_png",
                    "severity": severity,
                    "classification": status,
                    "province_id": "",
                    "province_name": "",
                    "rgb": locator_audit.rgb_to_text(rgb),
                    "provenance": provenance,
                    "details": f"map_pixels={map_count}",
                }
            )
        orphan_rows.append(
            {
                "rgb": locator_audit.rgb_to_text(rgb),
                "total_pixel_count": total_count,
                "palette_pixel_count": palette_count,
                "map_pixel_count": map_count,
                "status": status,
                "severity": severity,
                "provenance": provenance,
            }
        )

    problem_rows = [
        row for row in definition_rows if row["severity"] in {"blocker", "review"}
    ]
    topology_rows = [
        row for row in definition_rows if int(row["component_count"]) > 1
    ]
    source_remap_rows = [
        row for row in definition_rows
        if row["status"] == "source_semantic_reference_requires_remap"
    ]
    current_content_missing_rows = [
        row for row in definition_rows
        if row["status"] == "current_content_reference_missing_pixels"
    ]

    write_csv(output_dir / "definition_pixel_inventory.csv", definition_rows)
    write_csv(output_dir / "definition_pixel_problems.csv", problem_rows)
    write_csv(output_dir / "definition_topology_reviews.csv", topology_rows)
    write_csv(output_dir / "source_semantic_reference_remap_candidates.csv", source_remap_rows)
    write_csv(output_dir / "current_content_missing_pixels.csv", current_content_missing_rows)
    write_csv(output_dir / "orphan_pixel_rgbs.csv", orphan_rows)
    write_csv(output_dir / "binary_map_findings.csv", findings)
    if non_palette_orphans:
        render_orphan_overlay(
            image,
            non_palette_orphans,
            output_dir / "orphan_map_rgbs_overlay.png",
        )

    status_counts = Counter(str(row["status"]) for row in definition_rows)
    severity_counts = Counter(str(row["severity"]) for row in findings)
    orphan_status_counts = Counter(str(row["status"]) for row in orphan_rows)
    palette_text = (
        "none" if palette_bounds is None
        else ",".join(map(str, palette_bounds))
    )
    lines = [
        "# Global Definition Pixel Audit",
        "",
        f"- map size: `{image.width}x{image.height}`",
        f"- definition IDs: `{len(definition)}`",
        f"- definition RGBs: `{len(rgb_to_ids)}`",
        f"- PNG RGBs: `{len(color_counts)}`",
        f"- inferred palette bounds: `{palette_text}`",
        f"- orphan PNG RGBs: `{len(orphan_rows)}`",
        f"- non-palette orphan RGBs: `{len(non_palette_orphans)}`",
        f"- topology analyzed: `{'no' if args.skip_topology else 'yes'}`",
        f"- baseline revision: `{args.baseline_revision or 'none'}`",
        "",
        "## Definition Status",
        "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(status_counts.items())],
        "",
        "## Finding Severity",
        "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(severity_counts.items())],
        "",
        "## Orphan RGB Status",
        "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(orphan_status_counts.items())],
        "",
        "## Rules",
        "",
        "- Bottom-right palette/reserved pixels are excluded from playable map geometry.",
        "- Missing pixels with active references are blockers even when pre-existing.",
        "- Source-only unused definitions and multipart provinces require review, not blind fixes.",
        "- Four-neighbor components are measured; islands can make multipart geometry intentional.",
        "- No live map file is modified.",
    ]
    (output_dir / "map_definition_pixel_audit_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    print(f"output: {output_dir}")
    print(f"definition status: {dict(status_counts)}")
    print(f"finding severity: {dict(severity_counts)}")
    print(f"orphan status: {dict(orphan_status_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
