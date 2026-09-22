from __future__ import annotations

import argparse
import colorsys
import csv
import hashlib
import math
from array import array
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

import audit_repo_semantic_compatibility as semantic
import build_silk_road_vanilla_east_merge_dry_run as merge


MAP_PATH = Path("BookmarksGit/map_data/provinces.png")
CANDIDATE_PATH = (
    merge.OUTPUT_PATH / "silk_road_arrows_vanilla_east_candidate.txt"
)
BLOCK_PLAN_PATH = merge.OUTPUT_PATH / "silk_road_block_merge_plan.csv"
OUTPUT_PATH = Path(
    "development/analysis/generated/repo_integration_closure/"
    "silk_road_geometry_audit"
)
OVERLAY_SCALE = 0.5
NEAR_ENDPOINT_DISTANCE = 80.0
LONG_MIN_DISTANCE = 200.0
EXTREME_MIN_DISTANCE = 400.0
MIXED_ACTION = "manual_mixed"


@dataclass(frozen=True)
class PointGeometry:
    province_id: int
    rgb: tuple[int, int, int]
    pixel_count: int
    component_count: int
    largest_component_pixels: int
    center_x: int
    center_y: int
    safe_x: int
    safe_y: int
    border_distance: int
    method: str


@dataclass
class Route:
    layer: str
    arrow: str
    action: str
    source_ids: list[int]
    target_ids: list[int]
    source_classes: list[str]
    mapping_statuses: list[str]


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "BookmarksGit").is_dir():
            return candidate
    raise RuntimeError("Cannot locate project root containing BookmarksGit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build visual and geometric Silk Road dry-run audit"
    )
    parser.add_argument("--repo-root", type=Path, default=find_project_root())
    parser.add_argument(
        "--asil-mod-root", type=Path, default=merge.DEFAULT_ASIL_MOD_ROOT
    )
    parser.add_argument(
        "--vanilla-root", type=Path, default=merge.DEFAULT_VANILLA_ROOT
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--candidate-path", type=Path, default=CANDIDATE_PATH)
    parser.add_argument("--block-plan-path", type=Path, default=BLOCK_PLAN_PATH)
    parser.add_argument("--candidate-reference-path", type=Path, default=None)
    parser.add_argument("--overlay-scale", type=float, default=OVERLAY_SCALE)
    parser.add_argument(
        "--near-endpoint-distance",
        type=float,
        default=NEAR_ENDPOINT_DISTANCE,
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def resolve_repo_path(repo_root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def load_sources(
    repo_root: Path,
    asil_mod_root: Path,
    vanilla_root: Path,
) -> tuple[
    dict[int, dict[str, object]],
    dict[int, dict[str, object]],
    dict[int, dict[str, object]],
    dict[int, dict[str, str]],
    dict[int, dict[str, str]],
]:
    current_definition = semantic.parse_definition(
        (repo_root / merge.DEFINITION_PATH).read_text(encoding="utf-8-sig")
    )
    asil_definition = semantic.parse_definition(
        (
            asil_mod_root / "BookmarksGit/map_data/definition.csv"
        ).read_text(encoding="utf-8-sig")
    )
    vanilla_definition = semantic.parse_definition(
        (vanilla_root / "map_data/definition.csv").read_text(
            encoding="utf-8-sig"
        )
    )
    mod_tracking = merge.load_tracking(repo_root / merge.MOD_TRACKING_PATH)
    vanilla_tracking = merge.load_tracking(
        repo_root / merge.VANILLA_TRACKING_PATH
    )
    return (
        current_definition,
        asil_definition,
        vanilla_definition,
        mod_tracking,
        vanilla_tracking,
    )


def build_routes(
    repo_root: Path,
    vanilla_root: Path,
    candidate_path: Path,
    block_plan_path: Path,
    candidate_reference_path: Path | None,
    current_definition: dict[int, dict[str, object]],
    asil_definition: dict[int, dict[str, object]],
    vanilla_definition: dict[int, dict[str, object]],
    mod_tracking: dict[int, dict[str, str]],
    vanilla_tracking: dict[int, dict[str, str]],
) -> tuple[dict[str, list[Route]], dict[str, str]]:
    current_blocks = merge.parse_arrow_blocks(
        (repo_root / merge.CURRENT_PATH).read_text(encoding="utf-8-sig")
    )
    vanilla_blocks = merge.parse_arrow_blocks(
        (
            vanilla_root / "common/connection_arrows/silk_road_arrows.txt"
        ).read_text(encoding="utf-8-sig")
    )
    candidate_blocks = merge.parse_arrow_blocks(
        candidate_path.read_text(encoding="utf-8-sig")
    )
    block_plan_rows = read_csv(block_plan_path)
    block_actions = {row["arrow"]: row["action"] for row in block_plan_rows}
    review_groups = {
        row["arrow"]: row.get("review_group", "") for row in block_plan_rows
    }

    candidate_references: dict[str, list[dict[str, str]]] = defaultdict(list)
    if candidate_reference_path is not None:
        for row in read_csv(candidate_reference_path):
            arrow = row.get("candidate_arrow") or row.get("arrow") or ""
            if arrow:
                candidate_references[arrow].append(row)
        for rows in candidate_references.values():
            rows.sort(key=lambda row: int(row["candidate_sequence"]))

    current_routes: list[Route] = []
    for block in current_blocks:
        source_ids = list(block.province_ids)
        classes = [
            (
                "modlu_kalan"
                if merge.tracking_matches_source(
                    province_id, mod_tracking, asil_definition
                )
                else "removed_asil_mod_east"
            )
            for province_id in source_ids
        ]
        current_routes.append(
            Route(
                "current",
                block.name,
                block_actions.get(block.name, ""),
                source_ids,
                list(source_ids),
                classes,
                ["raw_current_id"] * len(source_ids),
            )
        )

    vanilla_routes: list[Route] = []
    for block in vanilla_blocks:
        source_ids = list(block.province_ids)
        target_ids: list[int] = []
        classes: list[str] = []
        statuses: list[str] = []
        for province_id in source_ids:
            is_east = merge.tracking_matches_source(
                province_id, vanilla_tracking, vanilla_definition
            )
            target_id = merge.mapped_id(
                province_id, vanilla_tracking, vanilla_definition
            )
            target_ids.append(target_id)
            if is_east:
                classes.append("orijinal_dogu")
                statuses.append(
                    "mapped_vanilla_east"
                    if target_id != province_id
                    else "vanilla_east_same_id"
                )
            else:
                classes.append("vanilla_outside_east")
                if semantic.same_province_semantics(
                    vanilla_definition.get(province_id),
                    current_definition.get(target_id),
                ):
                    statuses.append("outside_east_same_definition_semantics")
                else:
                    statuses.append("outside_east_same_id_semantic_drift")
        vanilla_routes.append(
            Route(
                "vanilla_mapped",
                block.name,
                block_actions.get(block.name, ""),
                source_ids,
                target_ids,
                classes,
                statuses,
            )
        )

    candidate_routes: list[Route] = []
    for block in candidate_blocks:
        target_ids = list(block.province_ids)
        action = block_actions.get(block.name, "")
        references = candidate_references.get(block.name, [])
        if references:
            reference_targets = [
                int(row["target_province_id"]) for row in references
            ]
            if reference_targets != target_ids:
                raise RuntimeError(
                    f"Candidate reference sequence mismatch for {block.name}"
                )
            source_ids = [
                int(row["source_province_id"]) for row in references
            ]
            source_classes = [
                row["source_classification"] for row in references
            ]
            mapping_statuses = [row["mapping_status"] for row in references]
        else:
            source_ids = list(target_ids)
            source_classes = [
                f"candidate_{action or 'unknown'}"
            ] * len(target_ids)
            mapping_statuses = ["candidate_emitted_id"] * len(target_ids)
        candidate_routes.append(
            Route(
                "candidate",
                block.name,
                action,
                source_ids,
                target_ids,
                source_classes,
                mapping_statuses,
            )
        )

    return {
        "current": current_routes,
        "vanilla_mapped": vanilla_routes,
        "candidate": candidate_routes,
    }, block_actions, review_groups


def collect_needed_rgbs(
    layers: dict[str, list[Route]],
    definition: dict[int, dict[str, object]],
) -> tuple[dict[tuple[int, int, int], array], list[int]]:
    missing_ids = sorted(
        {
            province_id
            for routes in layers.values()
            for route in routes
            for province_id in route.target_ids
            if province_id not in definition
        }
    )
    rgbs = {
        tuple(definition[province_id]["rgb"])
        for routes in layers.values()
        for route in routes
        for province_id in route.target_ids
        if province_id in definition
    }
    return {rgb: array("I") for rgb in rgbs}, missing_ids


def scan_needed_pixels(
    image: Image.Image,
    buckets: dict[tuple[int, int, int], array],
) -> None:
    for index, rgb in enumerate(image.getdata()):
        bucket = buckets.get(rgb)
        if bucket is not None:
            bucket.append(index)


def neighbors(index: int, width: int, height: int) -> tuple[int, ...]:
    x = index % width
    result: list[int] = []
    if x:
        result.append(index - 1)
    if x + 1 < width:
        result.append(index + 1)
    if index >= width:
        result.append(index - width)
    if index + width < width * height:
        result.append(index + width)
    return tuple(result)


def largest_component(
    indices: array,
    width: int,
    height: int,
) -> tuple[set[int], int]:
    unvisited = set(indices)
    largest: set[int] = set()
    component_count = 0
    while unvisited:
        component_count += 1
        start = unvisited.pop()
        component = {start}
        queue = [start]
        while queue:
            current = queue.pop()
            for adjacent in neighbors(current, width, height):
                if adjacent in unvisited:
                    unvisited.remove(adjacent)
                    component.add(adjacent)
                    queue.append(adjacent)
        if len(component) > len(largest):
            largest = component
    return largest, component_count


def safest_component_pixel(
    component: set[int],
    width: int,
    height: int,
) -> tuple[int, int, int, int, int]:
    if not component:
        return 0, 0, 0, 0, 0
    sum_x = sum(index % width for index in component)
    sum_y = sum(index // width for index in component)
    center_x = round(sum_x / len(component))
    center_y = round(sum_y / len(component))
    boundary = {
        index
        for index in component
        if (
            len(neighbors(index, width, height)) < 4
            or any(
                adjacent not in component
                for adjacent in neighbors(index, width, height)
            )
        )
    }
    if not boundary:
        chosen = min(
            component,
            key=lambda index: (
                (index % width - center_x) ** 2
                + (index // width - center_y) ** 2,
                index,
            ),
        )
        return center_x, center_y, chosen % width, chosen // width, 0

    visited = set(boundary)
    frontier = boundary
    distance = 0
    farthest = boundary
    while frontier:
        next_frontier: set[int] = set()
        for index in frontier:
            for adjacent in neighbors(index, width, height):
                if adjacent in component and adjacent not in visited:
                    visited.add(adjacent)
                    next_frontier.add(adjacent)
        if not next_frontier:
            break
        distance += 1
        farthest = next_frontier
        frontier = next_frontier
    chosen = min(
        farthest,
        key=lambda index: (
            (index % width - center_x) ** 2
            + (index // width - center_y) ** 2,
            index,
        ),
    )
    return center_x, center_y, chosen % width, chosen // width, distance


def build_geometries(
    buckets: dict[tuple[int, int, int], array],
    width: int,
    height: int,
    definition: dict[int, dict[str, object]],
) -> tuple[dict[int, PointGeometry], dict[tuple[int, int, int], set[int]]]:
    by_rgb: dict[tuple[int, int, int], PointGeometry] = {}
    all_pixel_sets: dict[tuple[int, int, int], set[int]] = {}
    for rgb, indices in buckets.items():
        if not indices:
            continue
        component, component_count = largest_component(indices, width, height)
        center_x, center_y, safe_x, safe_y, border_distance = (
            safest_component_pixel(component, width, height)
        )
        by_rgb[rgb] = PointGeometry(
            province_id=0,
            rgb=rgb,
            pixel_count=len(indices),
            component_count=component_count,
            largest_component_pixels=len(component),
            center_x=center_x,
            center_y=center_y,
            safe_x=safe_x,
            safe_y=safe_y,
            border_distance=border_distance,
            method="largest_component_farthest_boundary_pixel",
        )
        all_pixel_sets[rgb] = set(indices)

    result: dict[int, PointGeometry] = {}
    for province_id, meta in definition.items():
        rgb = tuple(meta["rgb"])
        geometry = by_rgb.get(rgb)
        if geometry is None:
            continue
        result[province_id] = PointGeometry(
            province_id=province_id,
            rgb=geometry.rgb,
            pixel_count=geometry.pixel_count,
            component_count=geometry.component_count,
            largest_component_pixels=geometry.largest_component_pixels,
            center_x=geometry.center_x,
            center_y=geometry.center_y,
            safe_x=geometry.safe_x,
            safe_y=geometry.safe_y,
            border_distance=geometry.border_distance,
            method=geometry.method,
        )
    return result, all_pixel_sets


def provinces_touch(
    first_rgb: tuple[int, int, int],
    second_rgb: tuple[int, int, int],
    pixel_sets: dict[tuple[int, int, int], set[int]],
    width: int,
    height: int,
    cache: dict[tuple[tuple[int, int, int], tuple[int, int, int]], bool],
) -> bool:
    if first_rgb == second_rgb:
        return True
    key = tuple(sorted((first_rgb, second_rgb)))
    if key in cache:
        return cache[key]
    first = pixel_sets.get(first_rgb, set())
    second = pixel_sets.get(second_rgb, set())
    if len(first) > len(second):
        first, second = second, first
    touching = any(
        adjacent in second
        for index in first
        for adjacent in neighbors(index, width, height)
    )
    cache[key] = touching
    return touching


def proper_intersection(
    first_start: tuple[int, int],
    first_end: tuple[int, int],
    second_start: tuple[int, int],
    second_end: tuple[int, int],
) -> bool:
    def cross(
        origin: tuple[int, int],
        first: tuple[int, int],
        second: tuple[int, int],
    ) -> int:
        return (
            (first[0] - origin[0]) * (second[1] - origin[1])
            - (first[1] - origin[1]) * (second[0] - origin[0])
        )

    first_side = cross(first_start, first_end, second_start)
    second_side = cross(first_start, first_end, second_end)
    third_side = cross(second_start, second_end, first_start)
    fourth_side = cross(second_start, second_end, first_end)
    return (
        (first_side > 0 > second_side or first_side < 0 < second_side)
        and (third_side > 0 > fourth_side or third_side < 0 < fourth_side)
    )


def route_points(
    route: Route,
    geometries: dict[int, PointGeometry],
) -> list[tuple[int, int] | None]:
    return [
        (
            (geometries[province_id].safe_x, geometries[province_id].safe_y)
            if province_id in geometries
            else None
        )
        for province_id in route.target_ids
    ]


def build_geometry_rows(
    layers: dict[str, list[Route]],
    geometries: dict[int, PointGeometry],
    definition: dict[int, dict[str, object]],
    pixel_sets: dict[tuple[int, int, int], set[int]],
    width: int,
    height: int,
    near_endpoint_distance: float,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, dict[str, float]],
]:
    node_rows: list[dict[str, Any]] = []
    segment_rows: list[dict[str, Any]] = []
    route_rows: list[dict[str, Any]] = []
    join_rows: list[dict[str, Any]] = []
    thresholds: dict[str, dict[str, float]] = {}
    touching_cache: dict[
        tuple[tuple[int, int, int], tuple[int, int, int]], bool
    ] = {}

    node_usage: dict[tuple[str, int], set[str]] = defaultdict(set)
    for layer, routes in layers.items():
        for route in routes:
            for province_id in route.target_ids:
                node_usage[(layer, province_id)].add(route.arrow)

    segments_by_layer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for layer, routes in layers.items():
        for route in routes:
            points = route_points(route, geometries)
            for sequence, (
                source_id,
                target_id,
                source_class,
                mapping_status,
                point,
            ) in enumerate(
                zip(
                    route.source_ids,
                    route.target_ids,
                    route.source_classes,
                    route.mapping_statuses,
                    points,
                    strict=True,
                ),
                start=1,
            ):
                geometry = geometries.get(target_id)
                meta = definition.get(target_id, {})
                node_rows.append(
                    {
                        "layer": layer,
                        "arrow": route.arrow,
                        "action": route.action,
                        "sequence": sequence,
                        "source_province_id": source_id,
                        "target_province_id": target_id,
                        "target_name": meta.get("name", ""),
                        "source_classification": source_class,
                        "mapping_status": mapping_status,
                        "safe_x": point[0] if point else "",
                        "safe_y": point[1] if point else "",
                        "center_x": geometry.center_x if geometry else "",
                        "center_y": geometry.center_y if geometry else "",
                        "pixel_count": geometry.pixel_count if geometry else 0,
                        "component_count": (
                            geometry.component_count if geometry else 0
                        ),
                        "largest_component_pixels": (
                            geometry.largest_component_pixels if geometry else 0
                        ),
                        "border_distance": (
                            geometry.border_distance if geometry else ""
                        ),
                        "point_method": geometry.method if geometry else "missing",
                        "shared_arrow_count": len(
                            node_usage[(layer, target_id)]
                        ),
                        "shared_arrows": " | ".join(
                            sorted(node_usage[(layer, target_id)])
                        ),
                    }
                )

            for index in range(len(route.target_ids) - 1):
                first_id = route.target_ids[index]
                second_id = route.target_ids[index + 1]
                first_point = points[index]
                second_point = points[index + 1]
                distance = ""
                touching = ""
                if first_point is not None and second_point is not None:
                    distance = math.dist(first_point, second_point)
                    first_rgb = tuple(definition[first_id]["rgb"])
                    second_rgb = tuple(definition[second_id]["rgb"])
                    touching = provinces_touch(
                        first_rgb,
                        second_rgb,
                        pixel_sets,
                        width,
                        height,
                        touching_cache,
                    )
                segment = {
                    "segment_id": f"{layer}:{route.arrow}:{index + 1}",
                    "layer": layer,
                    "arrow": route.arrow,
                    "action": route.action,
                    "segment_sequence": index + 1,
                    "from_province_id": first_id,
                    "from_name": definition.get(first_id, {}).get("name", ""),
                    "to_province_id": second_id,
                    "to_name": definition.get(second_id, {}).get("name", ""),
                    "from_x": first_point[0] if first_point else "",
                    "from_y": first_point[1] if first_point else "",
                    "to_x": second_point[0] if second_point else "",
                    "to_y": second_point[1] if second_point else "",
                    "distance_pixels": (
                        f"{distance:.3f}" if isinstance(distance, float) else ""
                    ),
                    "distance_map_width_ratio": (
                        f"{distance / width:.6f}"
                        if isinstance(distance, float)
                        else ""
                    ),
                    "provinces_touch": (
                        "yes" if touching is True
                        else "no" if touching is False
                        else ""
                    ),
                    "from_source_class": route.source_classes[index],
                    "to_source_class": route.source_classes[index + 1],
                    "length_flag": "",
                    "proper_crossing_count": 0,
                    "crosses_segments": "",
                }
                segment_rows.append(segment)
                segments_by_layer[layer].append(segment)

    for layer, segments in segments_by_layer.items():
        distances = [
            float(row["distance_pixels"])
            for row in segments
            if row["distance_pixels"] != ""
        ]
        layer_median = median(distances) if distances else 0.0
        long_threshold = max(LONG_MIN_DISTANCE, layer_median * 2.5)
        extreme_threshold = max(EXTREME_MIN_DISTANCE, layer_median * 4.0)
        thresholds[layer] = {
            "median": layer_median,
            "long": long_threshold,
            "extreme": extreme_threshold,
        }
        for row in segments:
            if row["distance_pixels"] == "":
                row["length_flag"] = "missing_geometry"
                continue
            distance = float(row["distance_pixels"])
            if distance >= extreme_threshold:
                row["length_flag"] = "extreme_jump"
            elif distance >= long_threshold:
                row["length_flag"] = "long_jump"
            else:
                row["length_flag"] = "normal"

        crossing_ids: dict[str, list[str]] = defaultdict(list)
        for index, first in enumerate(segments):
            if first["from_x"] == "" or first["to_x"] == "":
                continue
            first_ids = {
                int(first["from_province_id"]),
                int(first["to_province_id"]),
            }
            first_start = (int(first["from_x"]), int(first["from_y"]))
            first_end = (int(first["to_x"]), int(first["to_y"]))
            for second in segments[index + 1:]:
                if second["from_x"] == "" or second["to_x"] == "":
                    continue
                second_ids = {
                    int(second["from_province_id"]),
                    int(second["to_province_id"]),
                }
                if first_ids & second_ids:
                    continue
                second_start = (int(second["from_x"]), int(second["from_y"]))
                second_end = (int(second["to_x"]), int(second["to_y"]))
                if proper_intersection(
                    first_start,
                    first_end,
                    second_start,
                    second_end,
                ):
                    crossing_ids[first["segment_id"]].append(
                        second["segment_id"]
                    )
                    crossing_ids[second["segment_id"]].append(
                        first["segment_id"]
                    )
        for row in segments:
            crossings = sorted(crossing_ids[row["segment_id"]])
            row["proper_crossing_count"] = len(crossings)
            row["crosses_segments"] = " | ".join(crossings)

    for layer, routes in layers.items():
        for route in routes:
            points = route_points(route, geometries)
            route_segments = [
                row
                for row in segments_by_layer[layer]
                if row["arrow"] == route.arrow
            ]
            distances = [
                float(row["distance_pixels"])
                for row in route_segments
                if row["distance_pixels"] != ""
            ]
            route_rows.append(
                {
                    "layer": layer,
                    "arrow": route.arrow,
                    "action": route.action,
                    "node_count": len(route.target_ids),
                    "segment_count": len(route_segments),
                    "total_length_pixels": (
                        f"{sum(distances):.3f}" if distances else ""
                    ),
                    "max_segment_pixels": (
                        f"{max(distances):.3f}" if distances else ""
                    ),
                    "long_jump_count": sum(
                        row["length_flag"] == "long_jump"
                        for row in route_segments
                    ),
                    "extreme_jump_count": sum(
                        row["length_flag"] == "extreme_jump"
                        for row in route_segments
                    ),
                    "non_touching_segment_count": sum(
                        row["provinces_touch"] == "no"
                        for row in route_segments
                    ),
                    "proper_crossing_count": sum(
                        int(row["proper_crossing_count"])
                        for row in route_segments
                    ),
                    "missing_geometry_nodes": sum(
                        point is None for point in points
                    ),
                    "shared_node_count": sum(
                        len(node_usage[(layer, province_id)]) > 1
                        for province_id in set(route.target_ids)
                    ),
                }
            )

        for (usage_layer, province_id), arrows in sorted(node_usage.items()):
            if usage_layer != layer or len(arrows) < 2:
                continue
            geometry = geometries.get(province_id)
            join_rows.append(
                {
                    "layer": layer,
                    "join_type": "exact_shared_province",
                    "first_arrow": " | ".join(sorted(arrows)),
                    "second_arrow": "",
                    "first_province_id": province_id,
                    "second_province_id": province_id,
                    "distance_pixels": "0.000",
                    "x": geometry.safe_x if geometry else "",
                    "y": geometry.safe_y if geometry else "",
                }
            )

        endpoints: list[tuple[str, int, tuple[int, int]]] = []
        for route in routes:
            points = route_points(route, geometries)
            if not points:
                continue
            if points[0] is not None:
                endpoints.append((route.arrow, route.target_ids[0], points[0]))
            if len(points) > 1 and points[-1] is not None:
                endpoints.append((route.arrow, route.target_ids[-1], points[-1]))
        for index, first in enumerate(endpoints):
            for second in endpoints[index + 1:]:
                if first[0] == second[0] or first[1] == second[1]:
                    continue
                distance = math.dist(first[2], second[2])
                if distance <= near_endpoint_distance:
                    join_rows.append(
                        {
                            "layer": layer,
                            "join_type": "near_route_endpoints",
                            "first_arrow": first[0],
                            "second_arrow": second[0],
                            "first_province_id": first[1],
                            "second_province_id": second[1],
                            "distance_pixels": f"{distance:.3f}",
                            "x": "",
                            "y": "",
                        }
                    )

    return node_rows, segment_rows, route_rows, join_rows, thresholds


def muted_background(image: Image.Image, scale: float) -> Image.Image:
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    background = image.resize(
        (width, height),
        Image.Resampling.BILINEAR,
    ).convert("RGB")
    background = ImageEnhance.Color(background).enhance(0.18)
    background = ImageEnhance.Contrast(background).enhance(0.78)
    return ImageEnhance.Brightness(background).enhance(1.30)


def segment_color(row: dict[str, Any]) -> tuple[int, int, int]:
    layer = row["layer"]
    if layer == "current":
        classes = {row["from_source_class"], row["to_source_class"]}
        if classes == {"modlu_kalan"}:
            return 46, 190, 95
        if classes == {"removed_asil_mod_east"}:
            return 225, 58, 55
        return 255, 151, 35
    if layer == "vanilla_mapped":
        classes = {row["from_source_class"], row["to_source_class"]}
        if classes == {"orijinal_dogu"}:
            return 25, 205, 230
        if classes == {"vanilla_outside_east"}:
            return 45, 110, 235
        return 178, 75, 225
    classes = {row["from_source_class"], row["to_source_class"]}
    if "removed_asil_mod_east" in classes:
        return 225, 58, 55
    if classes == {"modlu_kalan"}:
        return 46, 190, 95
    if classes and classes <= {"orijinal_dogu", "vanilla_outside_east"}:
        return 25, 205, 230
    action = row["action"]
    if action == "keep_asil_mod_kalan":
        return 46, 190, 95
    if action == "replace_with_mapped_vanilla":
        return 25, 205, 230
    if action in {
        MIXED_ACTION,
        "resolved_splice",
        "resolved_reverse_mapped_vanilla",
        "resolved_keep_current_add_vanilla",
    }:
        return 255, 151, 35
    return 210, 210, 210


def draw_legend(
    draw: ImageDraw.ImageDraw,
    layer: str,
    width: int,
) -> None:
    font = ImageFont.load_default()
    legends = {
        "current": [
            ((46, 190, 95), "modlu_kalan"),
            ((225, 58, 55), "removed east raw ID"),
            ((255, 151, 35), "boundary transition"),
        ],
        "vanilla_mapped": [
            ((25, 205, 230), "mapped vanilla east"),
            ((45, 110, 235), "vanilla outside east"),
            ((178, 75, 225), "boundary transition"),
        ],
        "candidate": [
            ((46, 190, 95), "kept asıl mod"),
            ((25, 205, 230), "mapped vanilla"),
            ((255, 151, 35), "resolved splice boundary"),
            ((225, 58, 55), "removed east (must be zero)"),
        ],
    }
    title = {
        "current": "CURRENT RAW IDS",
        "vanilla_mapped": "MAPPED VANILLA",
        "candidate": "DRY-RUN CANDIDATE",
    }[layer]
    box_width = min(500, width - 20)
    box_height = 28 + len(legends[layer]) * 24
    draw.rounded_rectangle(
        (10, 10, 10 + box_width, 10 + box_height),
        radius=8,
        fill=(20, 24, 30),
        outline=(235, 235, 235),
        width=1,
    )
    draw.text((22, 18), title, fill=(255, 255, 255), font=font)
    y = 42
    for color, label in legends[layer]:
        draw.line((24, y + 6, 62, y + 6), fill=color, width=5)
        draw.text((72, y), label, fill=(245, 245, 245), font=font)
        y += 24


def render_layer_overlay(
    image: Image.Image,
    layer: str,
    segment_rows: list[dict[str, Any]],
    route_rows: list[dict[str, Any]],
    scale: float,
    output_path: Path,
) -> Image.Image:
    overlay = muted_background(image, scale)
    draw = ImageDraw.Draw(overlay)
    layer_segments = [row for row in segment_rows if row["layer"] == layer]
    for row in layer_segments:
        if row["from_x"] == "" or row["to_x"] == "":
            continue
        coordinates = (
            round(int(row["from_x"]) * scale),
            round(int(row["from_y"]) * scale),
            round(int(row["to_x"]) * scale),
            round(int(row["to_y"]) * scale),
        )
        if row["length_flag"] == "extreme_jump":
            draw.line(coordinates, fill=(20, 20, 20), width=8)
        elif row["length_flag"] == "long_jump":
            draw.line(coordinates, fill=(35, 35, 35), width=6)
        draw.line(coordinates, fill=segment_color(row), width=3)

    route_lookup = {
        (row["layer"], row["arrow"]): row for row in route_rows
    }
    endpoint_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in segment_rows:
        if row["layer"] == layer:
            endpoint_rows[row["arrow"]].append(row)
    for arrow, rows in endpoint_rows.items():
        rows.sort(key=lambda row: int(row["segment_sequence"]))
        if not rows or rows[0]["from_x"] == "" or rows[-1]["to_x"] == "":
            continue
        color = segment_color(rows[0])
        for x, y in (
            (int(rows[0]["from_x"]), int(rows[0]["from_y"])),
            (int(rows[-1]["to_x"]), int(rows[-1]["to_y"])),
        ):
            sx, sy = round(x * scale), round(y * scale)
            draw.ellipse(
                (sx - 4, sy - 4, sx + 4, sy + 4),
                fill=color,
                outline=(20, 20, 20),
                width=1,
            )
        route_row = route_lookup.get((layer, arrow), {})
        if (
            int(route_row.get("extreme_jump_count", 0))
            or int(route_row.get("proper_crossing_count", 0))
        ):
            sx = round(int(rows[0]["from_x"]) * scale)
            sy = round(int(rows[0]["from_y"]) * scale)
            draw.text(
                (sx + 6, sy + 4),
                arrow,
                fill=(255, 255, 255),
                stroke_width=2,
                stroke_fill=(20, 20, 20),
                font=ImageFont.load_default(),
            )
    draw_legend(draw, layer, overlay.width)
    overlay.save(output_path, optimize=True)
    return overlay


def render_triptych(
    overlays: dict[str, Image.Image],
    output_path: Path,
) -> None:
    panel_width = 2048
    panel_height = 1024
    result = Image.new("RGB", (panel_width * 3, panel_height), (20, 20, 20))
    for index, layer in enumerate(("current", "vanilla_mapped", "candidate")):
        panel = overlays[layer].copy()
        panel.thumbnail((panel_width, panel_height), Image.Resampling.LANCZOS)
        x = index * panel_width + (panel_width - panel.width) // 2
        y = (panel_height - panel.height) // 2
        result.paste(panel, (x, y))
    result.save(output_path, optimize=True)


def stable_route_color(name: str) -> tuple[int, int, int]:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    hue = int.from_bytes(digest[:2], "big") / 65535
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.70, 0.95)
    return round(red * 255), round(green * 255), round(blue * 255)


def draw_route_on_crop(
    draw: ImageDraw.ImageDraw,
    route: Route | None,
    geometries: dict[int, PointGeometry],
    left: int,
    top: int,
    scale: float,
    color: tuple[int, int, int],
    width: int,
) -> None:
    if route is None:
        return
    points = [
        (
            round((geometry.safe_x - left) * scale),
            round((geometry.safe_y - top) * scale),
        )
        for province_id in route.target_ids
        if (geometry := geometries.get(province_id)) is not None
    ]
    if len(points) >= 2:
        draw.line(points, fill=(20, 20, 20), width=width + 4, joint="curve")
        draw.line(points, fill=color, width=width, joint="curve")
    for x, y in points:
        draw.ellipse(
            (x - 3, y - 3, x + 3, y + 3),
            fill=color,
            outline=(20, 20, 20),
        )


def render_mixed_comparison(
    image: Image.Image,
    arrow: str,
    current_route: Route,
    vanilla_route: Route | None,
    candidate_route: Route | None,
    geometries: dict[int, PointGeometry],
    output_path: Path,
) -> None:
    all_points = [
        (geometry.safe_x, geometry.safe_y)
        for route in (current_route, vanilla_route, candidate_route)
        if route is not None
        for province_id in route.target_ids
        if (geometry := geometries.get(province_id)) is not None
    ]
    if not all_points:
        return
    padding = 140
    left = max(0, min(point[0] for point in all_points) - padding)
    top = max(0, min(point[1] for point in all_points) - padding)
    right = min(image.width, max(point[0] for point in all_points) + padding)
    bottom = min(image.height, max(point[1] for point in all_points) + padding)
    crop = image.crop((left, top, right, bottom)).convert("RGB")
    max_width, max_height = 2400, 1400
    scale = min(max_width / crop.width, max_height / crop.height, 1.0)
    if scale < 1.0:
        crop = crop.resize(
            (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
            Image.Resampling.BILINEAR,
        )
    crop = ImageEnhance.Color(crop).enhance(0.20)
    crop = ImageEnhance.Brightness(crop).enhance(1.25)
    draw = ImageDraw.Draw(crop)
    draw_route_on_crop(
        draw, current_route, geometries, left, top, scale, (225, 58, 55), 7
    )
    draw_route_on_crop(
        draw, vanilla_route, geometries, left, top, scale, (25, 205, 230), 5
    )
    draw_route_on_crop(
        draw, candidate_route, geometries, left, top, scale, (255, 151, 35), 3
    )
    font = ImageFont.load_default()
    draw.rounded_rectangle(
        (10, 10, min(crop.width - 10, 560), 104),
        radius=8,
        fill=(20, 24, 30),
        outline=(240, 240, 240),
    )
    draw.text((22, 18), f"MIXED BLOCK: {arrow}", fill="white", font=font)
    draw.line((22, 48, 62, 48), fill=(225, 58, 55), width=6)
    draw.text((72, 42), "current raw route", fill="white", font=font)
    draw.line((22, 72, 62, 72), fill=(25, 205, 230), width=5)
    draw.text(
        (72, 66),
        "mapped vanilla route" if vanilla_route else "no vanilla block",
        fill="white",
        font=font,
    )
    draw.line((290, 48, 330, 48), fill=(255, 151, 35), width=3)
    draw.text((340, 42), "candidate", fill="white", font=font)
    crop.save(output_path, optimize=True)


def render_mixed_contact_sheet(
    paths: list[Path],
    output_path: Path,
) -> None:
    panel_width, panel_height = 1200, 700
    columns = 2
    rows = math.ceil(len(paths) / columns)
    sheet = Image.new(
        "RGB",
        (panel_width * columns, panel_height * rows),
        (28, 30, 34),
    )
    for index, path in enumerate(paths):
        panel = Image.open(path).convert("RGB")
        panel.thumbnail(
            (panel_width - 20, panel_height - 20),
            Image.Resampling.LANCZOS,
        )
        column = index % columns
        row = index // columns
        x = column * panel_width + (panel_width - panel.width) // 2
        y = row * panel_height + (panel_height - panel.height) // 2
        sheet.paste(panel, (x, y))
    sheet.save(output_path, optimize=True)


def compressed_classes(values: list[str]) -> str:
    if not values:
        return ""
    groups: list[tuple[str, int]] = []
    for value in values:
        if groups and groups[-1][0] == value:
            groups[-1] = (value, groups[-1][1] + 1)
        else:
            groups.append((value, 1))
    return " -> ".join(
        f"{value}*{count}" if count > 1 else value
        for value, count in groups
    )


def build_mixed_review_rows(
    mixed_names: list[str],
    layers: dict[str, list[Route]],
    route_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    route_lookup = {
        (layer, route.arrow): route
        for layer, routes in layers.items()
        for route in routes
    }
    metric_lookup = {
        (row["layer"], row["arrow"]): row for row in route_rows
    }
    rows: list[dict[str, Any]] = []
    for arrow in mixed_names:
        current = route_lookup[("current", arrow)]
        vanilla = route_lookup.get(("vanilla_mapped", arrow))
        current_metrics = metric_lookup[("current", arrow)]
        vanilla_metrics = metric_lookup.get(("vanilla_mapped", arrow), {})
        common_ids = (
            sorted(set(current.target_ids) & set(vanilla.target_ids))
            if vanilla else []
        )
        exact_reverse = bool(
            vanilla and current.target_ids == list(reversed(vanilla.target_ids))
        )
        current_extreme = int(current_metrics["extreme_jump_count"])
        vanilla_extreme = int(vanilla_metrics.get("extreme_jump_count", 0))

        if exact_reverse and current_extreme == 0 and vanilla_extreme == 0:
            recommendation = "keep_current_direction_remap_east_nodes"
            reason = "same clean route in exact reverse order; current comment intentionally fixes direction"
        elif vanilla and common_ids and current_extreme and not vanilla_extreme:
            recommendation = "build_vanilla_east_current_west_splice_preview"
            reason = "mapped vanilla is clean and shares boundary nodes with current modlu_kalan tail"
        elif vanilla and not common_ids:
            recommendation = "keep_current_and_add_vanilla_under_unique_name"
            reason = "same block name represents two disjoint routes"
        elif vanilla and not current_extreme and not vanilla_extreme:
            recommendation = "manual_direction_or_network_choice"
            reason = "both alternatives are geometrically clean"
        else:
            recommendation = "manual_drop_or_split_network_review"
            reason = "no vanilla counterpart and current-only boundary route has extreme jumps"

        rows.append(
            {
                "arrow": arrow,
                "current_node_count": len(current.target_ids),
                "current_source_pattern": compressed_classes(
                    current.source_classes
                ),
                "current_long_jump_count": current_metrics["long_jump_count"],
                "current_extreme_jump_count": current_metrics[
                    "extreme_jump_count"
                ],
                "current_max_segment_pixels": current_metrics[
                    "max_segment_pixels"
                ],
                "vanilla_exists": "yes" if vanilla else "no",
                "vanilla_node_count": len(vanilla.target_ids) if vanilla else 0,
                "vanilla_source_pattern": (
                    compressed_classes(vanilla.source_classes)
                    if vanilla else ""
                ),
                "vanilla_long_jump_count": vanilla_metrics.get(
                    "long_jump_count", ""
                ),
                "vanilla_extreme_jump_count": vanilla_metrics.get(
                    "extreme_jump_count", ""
                ),
                "vanilla_max_segment_pixels": vanilla_metrics.get(
                    "max_segment_pixels", ""
                ),
                "common_target_ids_count": len(common_ids),
                "common_target_ids": " ".join(map(str, common_ids)),
                "exact_reverse_sequence": "yes" if exact_reverse else "no",
                "recommendation": recommendation,
                "reason": reason,
            }
        )
    return rows


def build_summary(
    layers: dict[str, list[Route]],
    node_rows: list[dict[str, Any]],
    segment_rows: list[dict[str, Any]],
    route_rows: list[dict[str, Any]],
    join_rows: list[dict[str, Any]],
    thresholds: dict[str, dict[str, float]],
    missing_ids: list[int],
    current_removed_count: int,
    candidate_pending_removed_count: int,
    vanilla_drift_count: int,
    live_hash: str,
) -> str:
    lines = [
        "# Silk Road geometry audit summary",
        "",
        "## Method",
        "",
        "- Province points use the largest RGB-connected component.",
        "- The plotted point is the component pixel farthest from its boundary.",
        "- Segments are straight-line proxies between ordered province points.",
        "- Actual CK3 smoothing can differ; in-game review remains final proof.",
        "",
        "## Layers",
        "",
    ]
    for layer in ("current", "vanilla_mapped", "candidate"):
        layer_segments = [
            row for row in segment_rows if row["layer"] == layer
        ]
        layer_routes = [row for row in route_rows if row["layer"] == layer]
        exact_joins = sum(
            row["layer"] == layer
            and row["join_type"] == "exact_shared_province"
            for row in join_rows
        )
        near_joins = sum(
            row["layer"] == layer
            and row["join_type"] == "near_route_endpoints"
            for row in join_rows
        )
        proper_crossings = (
            sum(int(row["proper_crossing_count"]) for row in layer_segments) // 2
        )
        layer_thresholds = thresholds.get(
            layer, {"median": 0.0, "long": 0.0, "extreme": 0.0}
        )
        lines.extend(
            [
                f"### {layer}",
                "",
                f"- Routes: {len(layers[layer])}",
                f"- Nodes: {sum(len(route.target_ids) for route in layers[layer])}",
                f"- Segments: {len(layer_segments)}",
                f"- Median segment distance: {layer_thresholds['median']:.3f}px",
                f"- Long threshold: {layer_thresholds['long']:.3f}px",
                f"- Extreme threshold: {layer_thresholds['extreme']:.3f}px",
                f"- Long jumps: {sum(row['length_flag'] == 'long_jump' for row in layer_segments)}",
                f"- Extreme jumps: {sum(row['length_flag'] == 'extreme_jump' for row in layer_segments)}",
                f"- Routes with an extreme jump: {sum(int(row['extreme_jump_count']) > 0 for row in layer_routes)}",
                f"- Proper straight-line crossings: {proper_crossings}",
                f"- Exact shared-province joins: {exact_joins}",
                f"- Near endpoint joins: {near_joins}",
                "",
            ]
        )

    lines.extend(
        [
            "## Source Risks",
            "",
            f"- Current removed-east raw references: {current_removed_count}",
            f"- Candidate pending removed-east references: {candidate_pending_removed_count}",
            f"- Vanilla outside-east same-ID semantic drift references: {vanilla_drift_count}",
            f"- Target IDs missing from current definition.csv: {len(missing_ids)}",
            f"- Missing IDs: {' | '.join(map(str, missing_ids))}",
            f"- Node rows without map pixels: {sum(row['point_method'] == 'missing' for row in node_rows)}",
            f"- Node rows with multiple RGB components: {sum(int(row['component_count']) > 1 for row in node_rows)}",
            f"- Live file SHA-256: {live_hash}",
            "- Live file changed: no",
            "",
            "## Longest Segments",
            "",
        ]
    )
    for layer in ("current", "vanilla_mapped", "candidate"):
        longest = sorted(
            (
                row
                for row in segment_rows
                if row["layer"] == layer and row["distance_pixels"] != ""
            ),
            key=lambda row: float(row["distance_pixels"]),
            reverse=True,
        )[:12]
        lines.extend([f"### {layer}", ""])
        lines.extend(
            (
                f"- {row['arrow']}[{row['segment_sequence']}]: "
                f"{row['from_province_id']} -> {row['to_province_id']} = "
                f"{float(row['distance_pixels']):.3f}px "
                f"({row['length_flag']})"
            )
            for row in longest
        )
        lines.append("")

    lines.extend(
        [
            "The generated images are geometric proxies, not engine screenshots.",
            "",
        ]
    )
    return "\n".join(lines)


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
    if not 0 < args.overlay_scale <= 1:
        raise ValueError("--overlay-scale must be greater than 0 and at most 1")

    current_path = repo_root / merge.CURRENT_PATH
    map_path = repo_root / MAP_PATH
    candidate_path = resolve_repo_path(repo_root, args.candidate_path)
    block_plan_path = resolve_repo_path(repo_root, args.block_plan_path)
    candidate_reference_path = (
        resolve_repo_path(repo_root, args.candidate_reference_path)
        if args.candidate_reference_path is not None
        else None
    )
    required = (
        current_path,
        map_path,
        candidate_path,
        block_plan_path,
        repo_root / merge.DEFINITION_PATH,
        repo_root / merge.MOD_TRACKING_PATH,
        repo_root / merge.VANILLA_TRACKING_PATH,
        asil_mod_root / "BookmarksGit/map_data/definition.csv",
        vanilla_root / "map_data/definition.csv",
        vanilla_root / "common/connection_arrows/silk_road_arrows.txt",
    )
    if candidate_reference_path is not None:
        required = (*required, candidate_reference_path)
    missing_files = [str(path) for path in required if not path.is_file()]
    if missing_files:
        raise FileNotFoundError(
            "Missing required files:\n" + "\n".join(missing_files)
        )

    live_bytes = current_path.read_bytes()
    live_hash = hashlib.sha256(live_bytes).hexdigest()
    (
        current_definition,
        asil_definition,
        vanilla_definition,
        mod_tracking,
        vanilla_tracking,
    ) = load_sources(repo_root, asil_mod_root, vanilla_root)
    layers, block_actions, review_groups = build_routes(
        repo_root,
        vanilla_root,
        candidate_path,
        block_plan_path,
        candidate_reference_path,
        current_definition,
        asil_definition,
        vanilla_definition,
        mod_tracking,
        vanilla_tracking,
    )

    image = Image.open(map_path).convert("RGB")
    width, height = image.size
    buckets, missing_ids = collect_needed_rgbs(layers, current_definition)
    print(
        f"pixel_scan_start map={width}x{height} needed_rgbs={len(buckets)}",
        flush=True,
    )
    scan_needed_pixels(image, buckets)
    geometries, pixel_sets = build_geometries(
        buckets, width, height, current_definition
    )
    del buckets
    print(
        f"pixel_scan_complete geometries={len(geometries)}",
        flush=True,
    )

    (
        node_rows,
        segment_rows,
        route_rows,
        join_rows,
        thresholds,
    ) = build_geometry_rows(
        layers,
        geometries,
        current_definition,
        pixel_sets,
        width,
        height,
        args.near_endpoint_distance,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    mixed_dir = output_dir / "mixed_blocks"
    mixed_dir.mkdir(parents=True, exist_ok=True)
    semantic.write_csv(output_dir / "silk_road_geometry_nodes.csv", node_rows)
    semantic.write_csv(
        output_dir / "silk_road_geometry_segments.csv", segment_rows
    )
    semantic.write_csv(output_dir / "silk_road_geometry_routes.csv", route_rows)
    semantic.write_csv(output_dir / "silk_road_geometry_joins.csv", join_rows)

    overlays: dict[str, Image.Image] = {}
    for layer in ("current", "vanilla_mapped", "candidate"):
        overlays[layer] = render_layer_overlay(
            image,
            layer,
            segment_rows,
            route_rows,
            args.overlay_scale,
            output_dir / f"silk_road_{layer}_overlay.png",
        )
    render_triptych(
        overlays, output_dir / "silk_road_geometry_comparison_triptych.png"
    )

    route_lookup = {
        (layer, route.arrow): route
        for layer, routes in layers.items()
        for route in routes
    }
    mixed_names = sorted(
        arrow for arrow, action in block_actions.items()
        if (
            action == MIXED_ACTION
            or review_groups.get(arrow) == MIXED_ACTION
        )
        and ("current", arrow) in route_lookup
    )
    mixed_paths: list[Path] = []
    for arrow in mixed_names:
        mixed_path = mixed_dir / f"{arrow}_current_vanilla_candidate.png"
        render_mixed_comparison(
            image,
            arrow,
            route_lookup[("current", arrow)],
            route_lookup.get(("vanilla_mapped", arrow)),
            route_lookup.get(("candidate", arrow)),
            geometries,
            mixed_path,
        )
        mixed_paths.append(mixed_path)
    render_mixed_contact_sheet(
        mixed_paths,
        output_dir / "silk_road_mixed_blocks_contact_sheet.png",
    )
    semantic.write_csv(
        output_dir / "silk_road_mixed_block_geometry_review.csv",
        build_mixed_review_rows(mixed_names, layers, route_rows),
    )

    current_removed_count = sum(
        source_class == "removed_asil_mod_east"
        for route in layers["current"]
        for source_class in route.source_classes
    )
    if candidate_reference_path is not None:
        candidate_pending_removed_count = sum(
            source_class == "removed_asil_mod_east"
            for route in layers["candidate"]
            for source_class in route.source_classes
        )
    else:
        candidate_pending_removed_count = sum(
            source_class == "removed_asil_mod_east"
            for route in layers["current"]
            if route.action == MIXED_ACTION
            for source_class in route.source_classes
        )
    vanilla_drift_count = sum(
        status == "outside_east_same_id_semantic_drift"
        for route in layers["vanilla_mapped"]
        for status in route.mapping_statuses
    )
    summary = build_summary(
        layers,
        node_rows,
        segment_rows,
        route_rows,
        join_rows,
        thresholds,
        missing_ids,
        current_removed_count,
        candidate_pending_removed_count,
        vanilla_drift_count,
        live_hash,
    )
    (output_dir / "silk_road_geometry_audit_summary.md").write_text(
        summary, encoding="utf-8"
    )

    after_hash = hashlib.sha256(current_path.read_bytes()).hexdigest()
    if after_hash != live_hash:
        raise RuntimeError("Live silk_road_arrows.txt changed during dry-run")
    print(f"output_dir={output_dir}")
    print(f"current_routes={len(layers['current'])}")
    print(f"vanilla_routes={len(layers['vanilla_mapped'])}")
    print(f"candidate_routes={len(layers['candidate'])}")
    print(f"node_rows={len(node_rows)}")
    print(f"segment_rows={len(segment_rows)}")
    print(f"join_rows={len(join_rows)}")
    print(f"mixed_images={len(mixed_names)}")
    print(f"candidate_pending_removed_east={candidate_pending_removed_count}")
    print(f"live_sha256={live_hash}")
    print("validation=pass")
    print("live_file_changed=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
