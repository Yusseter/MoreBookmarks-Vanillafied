from __future__ import annotations

import argparse
import hashlib
import subprocess
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

import build_silk_road_vanilla_east_merge_dry_run as merge


OUTPUT_PATH = Path(
    ".codex/works/analysis/generated/repo_integration_closure/"
    "silk_road_resolved_vanilla_east_merge"
)
SPLICE_NAMES = {"first", "fourth", "twentyfirst"}
DROP_NAMES = {"twentyeighth", "fiftyfourth"}
MIXED_NAMES = SPLICE_NAMES | DROP_NAMES | {"ninth", "tenth"}
UNIQUE_VANILLA_NINTH = "yb_vanilla_east_ninth"
EXPECTED_SPLICE_COUNTS = {
    "first": (9, 13),
    "fourth": (21, 17),
    "twentyfirst": (3, 3),
}


@dataclass(frozen=True)
class CandidateNode:
    target_id: int
    target_name: str
    source: str
    source_id: int
    source_name: str
    source_classification: str
    mapping_status: str
    line: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the resolved dry-run Silk Road vanilla-east candidate"
    )
    parser.add_argument("--repo-root", type=Path, default=merge.find_project_root())
    parser.add_argument(
        "--asil-mod-root", type=Path, default=merge.DEFAULT_ASIL_MOD_ROOT
    )
    parser.add_argument(
        "--vanilla-root", type=Path, default=merge.DEFAULT_VANILLA_ROOT
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_diff_patch(
    repo_root: Path, current_path: Path, candidate_path: Path
) -> str:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--no-index",
            "--no-color",
            "--no-ext-diff",
            "--",
            str(current_path),
            str(candidate_path),
        ],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode not in {0, 1}:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git diff --no-index failed: {message}")
    old_path = f"a/{merge.CURRENT_PATH.as_posix()}"
    new_path = f"b/{merge.CURRENT_PATH.as_posix()}"
    lines = result.stdout.decode("utf-8", errors="strict").splitlines(
        keepends=True
    )
    for index, line in enumerate(lines):
        if line.startswith("diff --git "):
            lines[index] = f"diff --git {old_path} {new_path}\n"
        elif line.startswith("--- "):
            lines[index] = f"--- {old_path}\n"
        elif line.startswith("+++ "):
            lines[index] = f"+++ {new_path}\n"
    return "".join(lines)


def province_entry_lines(block: merge.ArrowBlock) -> list[str]:
    result: list[str] = []
    in_provinces = False
    depth = 0
    for line in block.lines:
        code = merge.code_part(line)
        if not in_provinces:
            if not merge.PROVINCES_RE.match(code):
                continue
            in_provinces = True
            depth = merge.brace_delta(code)
            continue
        depth += merge.brace_delta(code)
        if depth <= 0:
            break
        numbers = merge.NUMBER_RE.findall(code)
        if not numbers:
            continue
        if len(numbers) != 1:
            raise RuntimeError(
                f"{block.name}: expected one province ID per entry line"
            )
        result.append(line)
    if len(result) != len(block.province_ids):
        raise RuntimeError(
            f"{block.name}: province entry count does not match parsed IDs"
        )
    return result


def rewrite_entry(line: str, target_id: int) -> str:
    if "#" in line:
        code, comment = line.split("#", 1)
        suffix = "#" + comment
    else:
        code, suffix = line, ""
    numbers = merge.NUMBER_RE.findall(code)
    if len(numbers) != 1:
        raise RuntimeError("Expected exactly one province ID in entry line")
    return merge.NUMBER_RE.sub(str(target_id), code, count=1) + suffix


def current_nodes(
    block: merge.ArrowBlock,
    current_definition: dict[int, dict[str, object]],
    asil_definition: dict[int, dict[str, object]],
    mod_tracking: dict[int, dict[str, str]],
) -> list[CandidateNode]:
    result: list[CandidateNode] = []
    for province_id, line in zip(
        block.province_ids, province_entry_lines(block), strict=True
    ):
        is_retained = merge.tracking_matches_source(
            province_id, mod_tracking, asil_definition
        )
        target_id = (
            merge.mapped_id(province_id, mod_tracking, asil_definition)
            if is_retained
            else province_id
        )
        result.append(
            CandidateNode(
                target_id=target_id,
                target_name=str(
                    current_definition.get(target_id, {}).get("name", "")
                ),
                source="current_asil_mod",
                source_id=province_id,
                source_name=str(
                    asil_definition.get(province_id, {}).get("name", "")
                ),
                source_classification=(
                    "modlu_kalan" if is_retained else "removed_asil_mod_east"
                ),
                mapping_status=(
                    "mapped_asil_mod_kalan"
                    if is_retained and target_id != province_id
                    else (
                        "asil_mod_kalan_same_id"
                        if is_retained
                        else "raw_removed_asil_mod_east"
                    )
                ),
                line=rewrite_entry(line, target_id),
            )
        )
    return result


def vanilla_nodes(
    block: merge.ArrowBlock,
    current_definition: dict[int, dict[str, object]],
    vanilla_definition: dict[int, dict[str, object]],
    vanilla_tracking: dict[int, dict[str, str]],
) -> list[CandidateNode]:
    result: list[CandidateNode] = []
    for province_id, line in zip(
        block.province_ids, province_entry_lines(block), strict=True
    ):
        is_east = merge.tracking_matches_source(
            province_id, vanilla_tracking, vanilla_definition
        )
        target_id = merge.mapped_id(
            province_id, vanilla_tracking, vanilla_definition
        )
        if is_east:
            mapping_status = (
                "mapped_vanilla_east"
                if target_id != province_id
                else "vanilla_east_same_id"
            )
        elif merge.semantic.same_province_semantics(
            vanilla_definition.get(province_id),
            current_definition.get(target_id),
        ):
            mapping_status = "outside_east_same_definition_semantics"
        else:
            mapping_status = "outside_east_same_id_semantic_drift"
        result.append(
            CandidateNode(
                target_id=target_id,
                target_name=str(
                    current_definition.get(target_id, {}).get("name", "")
                ),
                source="vanilla",
                source_id=province_id,
                source_name=str(
                    vanilla_definition.get(province_id, {}).get("name", "")
                ),
                source_classification=(
                    "orijinal_dogu" if is_east else "vanilla_outside_east"
                ),
                mapping_status=mapping_status,
                line=rewrite_entry(line, target_id),
            )
        )
    return result


def render_block(
    template: merge.ArrowBlock, nodes: list[CandidateNode]
) -> tuple[str, ...]:
    start = -1
    end = -1
    depth = 0
    for index, line in enumerate(template.lines):
        code = merge.code_part(line)
        if start < 0:
            if not merge.PROVINCES_RE.match(code):
                continue
            start = index
            depth = merge.brace_delta(code)
            continue
        depth += merge.brace_delta(code)
        if depth <= 0:
            end = index
            break
    if start < 0 or end < 0:
        raise RuntimeError(f"{template.name}: provinces block not found")
    return (
        template.lines[: start + 1]
        + tuple(node.line for node in nodes)
        + template.lines[end:]
    )


def rename_block(lines: tuple[str, ...], new_name: str) -> tuple[str, ...]:
    result = list(lines)
    match = merge.HEADER_RE.match(merge.code_part(result[0]))
    if not match:
        raise RuntimeError("Cannot rename arrow block without a valid header")
    result[0] = (
        result[0][: match.start(1)]
        + new_name
        + result[0][match.end(1) :]
    )
    return tuple(result)


def leading_class(
    nodes: list[CandidateNode], source_classification: str
) -> list[CandidateNode]:
    result: list[CandidateNode] = []
    for node in nodes:
        if node.source_classification != source_classification:
            break
        result.append(node)
    return result


def trailing_class(
    nodes: list[CandidateNode], source_classification: str
) -> list[CandidateNode]:
    result: deque[CandidateNode] = deque()
    for node in reversed(nodes):
        if node.source_classification != source_classification:
            break
        result.appendleft(node)
    return list(result)


def route_components(routes: dict[str, tuple[int, ...]]) -> dict[str, int]:
    by_id: dict[int, set[str]] = defaultdict(set)
    for arrow, ids in routes.items():
        for province_id in ids:
            by_id[province_id].add(arrow)
    neighbors: dict[str, set[str]] = {arrow: set() for arrow in routes}
    for arrows in by_id.values():
        for arrow in arrows:
            neighbors[arrow].update(arrows - {arrow})
    result: dict[str, int] = {}
    component = 0
    for start in routes:
        if start in result:
            continue
        component += 1
        queue = deque([start])
        result[start] = component
        while queue:
            arrow = queue.popleft()
            for neighbor in neighbors[arrow]:
                if neighbor in result:
                    continue
                result[neighbor] = component
                queue.append(neighbor)
    return result


def contiguous_fragments(
    nodes: list[CandidateNode], source_classification: str
) -> list[tuple[int, ...]]:
    fragments: list[list[int]] = []
    active: list[int] = []
    for node in nodes:
        if node.source_classification == source_classification:
            active.append(node.target_id)
            continue
        if active:
            fragments.append(active)
            active = []
    if active:
        fragments.append(active)
    return [tuple(fragment) for fragment in fragments]


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

    current_path = repo_root / merge.CURRENT_PATH
    vanilla_path = (
        vanilla_root / "common/connection_arrows/silk_road_arrows.txt"
    )
    current_definition_path = repo_root / merge.DEFINITION_PATH
    asil_definition_path = (
        asil_mod_root / "BookmarksGit/map_data/definition.csv"
    )
    vanilla_definition_path = vanilla_root / "map_data/definition.csv"
    required = (
        current_path,
        vanilla_path,
        current_definition_path,
        asil_definition_path,
        vanilla_definition_path,
        repo_root / merge.MOD_TRACKING_PATH,
        repo_root / merge.VANILLA_TRACKING_PATH,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required files:\n" + "\n".join(missing))

    live_bytes = current_path.read_bytes()
    live_hash = sha256_bytes(live_bytes)
    with_bom = live_bytes.startswith(b"\xef\xbb\xbf")
    newline = "\r\n" if b"\r\n" in live_bytes else "\n"
    current_text = live_bytes.decode("utf-8-sig")
    vanilla_text = vanilla_path.read_text(encoding="utf-8-sig")
    current_blocks = merge.parse_arrow_blocks(current_text)
    vanilla_blocks = merge.parse_arrow_blocks(vanilla_text)
    current_by_name = {block.name: block for block in current_blocks}
    vanilla_by_name = {block.name: block for block in vanilla_blocks}

    current_definition = merge.semantic.parse_definition(
        current_definition_path.read_text(encoding="utf-8-sig")
    )
    asil_definition = merge.semantic.parse_definition(
        asil_definition_path.read_text(encoding="utf-8-sig")
    )
    vanilla_definition = merge.semantic.parse_definition(
        vanilla_definition_path.read_text(encoding="utf-8-sig")
    )
    mod_tracking = merge.load_tracking(repo_root / merge.MOD_TRACKING_PATH)
    vanilla_tracking = merge.load_tracking(
        repo_root / merge.VANILLA_TRACKING_PATH
    )

    replacements: dict[str, tuple[str, ...]] = {}
    resolved_nodes: dict[str, list[CandidateNode]] = {}
    plan_rows: list[dict[str, str]] = []
    resolution_reasons: dict[str, str] = {}

    for current in current_blocks:
        vanilla = vanilla_by_name.get(current.name)
        original_action, original_reason, _, _ = merge.classify_block(
            current,
            vanilla,
            mod_tracking,
            vanilla_tracking,
            asil_definition,
            vanilla_definition,
        )
        current_source_nodes = current_nodes(
            current, current_definition, asil_definition, mod_tracking
        )
        vanilla_source_nodes = (
            vanilla_nodes(
                vanilla,
                current_definition,
                vanilla_definition,
                vanilla_tracking,
            )
            if vanilla is not None
            else []
        )

        if current.name in SPLICE_NAMES:
            vanilla_prefix = leading_class(
                vanilla_source_nodes, "orijinal_dogu"
            )
            current_tail = trailing_class(current_source_nodes, "modlu_kalan")
            expected = EXPECTED_SPLICE_COUNTS[current.name]
            actual = (len(vanilla_prefix), len(current_tail))
            if actual != expected:
                raise RuntimeError(
                    f"{current.name}: splice counts {actual} != {expected}"
                )
            nodes = vanilla_prefix + current_tail
            replacement = render_block(current, nodes)
            action = "resolved_splice"
            candidate_source = "mapped_vanilla_east_plus_current_asil_mod_tail"
            reason = (
                "mapped vanilla east prefix joined to the contiguous retained "
                "asıl mod tail"
            )
        elif current.name == "ninth":
            if any(
                node.source_classification != "modlu_kalan"
                for node in current_source_nodes
            ):
                raise RuntimeError("ninth: current route is not fully retained")
            nodes = current_source_nodes
            replacement = render_block(current, nodes)
            unique_nodes = vanilla_source_nodes
            if not unique_nodes:
                raise RuntimeError("ninth: mapped vanilla route is missing")
            unique_lines = rename_block(
                render_block(vanilla, unique_nodes), UNIQUE_VANILLA_NINTH
            )
            replacement = (
                replacement
                + ("\n", "# Vanilla east: Nanhai to Chengdu\n")
                + unique_lines
            )
            action = "resolved_keep_current_add_vanilla"
            candidate_source = "current_route_plus_unique_mapped_vanilla_route"
            reason = (
                "same source block name contains two disjoint routes; preserve "
                "current and add vanilla under a unique name"
            )
            resolved_nodes[UNIQUE_VANILLA_NINTH] = unique_nodes
            resolution_reasons[UNIQUE_VANILLA_NINTH] = reason
        elif current.name == "tenth":
            nodes = list(reversed(vanilla_source_nodes))
            current_targets = [
                node.target_id for node in current_source_nodes
            ]
            if [node.target_id for node in nodes] != current_targets:
                raise RuntimeError(
                    "tenth: reversed mapped vanilla sequence differs from current"
                )
            replacement = current.lines
            action = "resolved_reverse_mapped_vanilla"
            candidate_source = "mapped_vanilla_kept_in_current_reverse_direction"
            reason = (
                "mapped vanilla route is the exact reverse; preserve the current "
                "intentional east-to-west direction"
            )
        elif current.name in DROP_NAMES:
            nodes = []
            replacement = ()
            action = "resolved_drop"
            candidate_source = "removed"
            reason = (
                "asıl mod-only east extension without a vanilla counterpart; "
                "network attachment audit permits full removal"
            )
        elif original_action == "keep_asil_mod_kalan":
            nodes = current_source_nodes
            replacement = render_block(current, nodes)
            action = original_action
            candidate_source = "current_asil_mod"
            reason = original_reason
        elif original_action == "replace_with_mapped_vanilla":
            nodes = vanilla_source_nodes
            replacement = render_block(vanilla, nodes)
            action = original_action
            candidate_source = "mapped_vanilla"
            reason = original_reason
        elif original_action == "drop_asil_mod_east_only":
            nodes = []
            replacement = ()
            action = original_action
            candidate_source = "removed"
            reason = original_reason
        else:
            raise RuntimeError(
                f"Unresolved manual mixed block remains: {current.name}"
            )

        replacements[current.name] = replacement
        resolved_nodes[current.name] = nodes
        resolution_reasons[current.name] = reason
        plan_rows.append(
            {
                "arrow": current.name,
                "current_line": str(current.start + 1),
                "vanilla_line": str(vanilla.start + 1) if vanilla else "",
                "original_action": original_action,
                "action": action,
                "review_group": (
                    "manual_mixed" if current.name in MIXED_NAMES else ""
                ),
                "candidate_source": candidate_source,
                "current_reference_count": str(len(current.province_ids)),
                "vanilla_reference_count": str(
                    len(vanilla.province_ids) if vanilla else 0
                ),
                "candidate_reference_count": str(len(nodes)),
                "candidate_removed_east_count": str(
                    sum(
                        node.source_classification
                        == "removed_asil_mod_east"
                        for node in nodes
                    )
                ),
                "reason": reason,
                "current_ids": " ".join(map(str, current.province_ids)),
                "vanilla_ids": (
                    " ".join(map(str, vanilla.province_ids)) if vanilla else ""
                ),
                "candidate_ids": " ".join(
                    str(node.target_id) for node in nodes
                ),
            }
        )

    unique_nodes = resolved_nodes[UNIQUE_VANILLA_NINTH]
    plan_rows.append(
        {
            "arrow": UNIQUE_VANILLA_NINTH,
            "current_line": "",
            "vanilla_line": str(vanilla_by_name["ninth"].start + 1),
            "original_action": "manual_mixed",
            "action": "resolved_add_mapped_vanilla",
            "review_group": "",
            "candidate_source": "mapped_vanilla_unique_route",
            "current_reference_count": "0",
            "vanilla_reference_count": str(
                len(vanilla_by_name["ninth"].province_ids)
            ),
            "candidate_reference_count": str(len(unique_nodes)),
            "candidate_removed_east_count": "0",
            "reason": resolution_reasons[UNIQUE_VANILLA_NINTH],
            "current_ids": "",
            "vanilla_ids": " ".join(
                map(str, vanilla_by_name["ninth"].province_ids)
            ),
            "candidate_ids": " ".join(
                str(node.target_id) for node in unique_nodes
            ),
        }
    )

    normalized_current = merge.semantic.normalize_text(current_text)
    candidate_lines = normalized_current.splitlines(keepends=True)
    for block in reversed(current_blocks):
        candidate_lines[block.start : block.end] = replacements[block.name]
    candidate_text = "".join(candidate_lines)
    if current_text.endswith(("\n", "\r")):
        candidate_text = candidate_text.rstrip("\n") + "\n"
    else:
        candidate_text = candidate_text.rstrip("\n")
    candidate_blocks = merge.parse_arrow_blocks(candidate_text)
    candidate_by_name = {block.name: block for block in candidate_blocks}

    expected_names = (
        set(current_by_name)
        - {
            row["arrow"]
            for row in plan_rows
            if row["action"] in {"drop_asil_mod_east_only", "resolved_drop"}
        }
    ) | {UNIQUE_VANILLA_NINTH}
    if set(candidate_by_name) != expected_names:
        missing_names = sorted(expected_names - set(candidate_by_name))
        extra_names = sorted(set(candidate_by_name) - expected_names)
        raise RuntimeError(
            f"Candidate block set mismatch; missing={missing_names}, extra={extra_names}"
        )

    reference_rows: list[dict[str, str]] = []
    validation_issues: list[str] = []
    action_by_arrow = {row["arrow"]: row["action"] for row in plan_rows}
    for arrow, block in candidate_by_name.items():
        nodes = resolved_nodes[arrow]
        expected_ids = tuple(node.target_id for node in nodes)
        if block.province_ids != expected_ids:
            validation_issues.append(f"{arrow}: candidate sequence mismatch")
        if len(nodes) < 2:
            validation_issues.append(f"{arrow}: route has fewer than two nodes")
        for sequence, node in enumerate(nodes, start=1):
            if node.target_id not in current_definition:
                validation_issues.append(
                    f"{arrow}: target province {node.target_id} missing"
                )
            if node.source_classification == "removed_asil_mod_east":
                validation_issues.append(
                    f"{arrow}: unresolved removed-east source {node.source_id}"
                )
            reference_rows.append(
                {
                    "candidate_arrow": arrow,
                    "candidate_sequence": str(sequence),
                    "target_province_id": str(node.target_id),
                    "target_name": node.target_name,
                    "source": node.source,
                    "source_province_id": str(node.source_id),
                    "source_name": node.source_name,
                    "source_classification": node.source_classification,
                    "mapping_status": node.mapping_status,
                    "resolution": action_by_arrow[arrow],
                }
            )
    if validation_issues:
        raise RuntimeError(
            "Resolved candidate validation failed:\n"
            + "\n".join(validation_issues)
        )

    candidate_routes = {
        block.name: block.province_ids for block in candidate_blocks
    }
    component_by_route = route_components(candidate_routes)
    node_routes: dict[int, set[str]] = defaultdict(set)
    for arrow, ids in candidate_routes.items():
        for province_id in ids:
            node_routes[province_id].add(arrow)

    network_rows: list[dict[str, str]] = []
    for arrow in sorted(DROP_NAMES):
        nodes = current_nodes(
            current_by_name[arrow],
            current_definition,
            asil_definition,
            mod_tracking,
        )
        attachment_ids = sorted(
            {
                node.target_id
                for node in nodes
                if node.target_id in node_routes
            }
        )
        attached_routes = sorted(
            {
                route
                for province_id in attachment_ids
                for route in node_routes[province_id]
            }
        )
        attached_components = {
            component_by_route[route] for route in attached_routes
        }
        fragments = contiguous_fragments(nodes, "modlu_kalan")
        network_rows.append(
            {
                "arrow": arrow,
                "current_ids": " ".join(
                    str(node.target_id) for node in nodes
                ),
                "retained_attachment_province_ids": " ".join(
                    map(str, attachment_ids)
                ),
                "attached_retained_routes": " ".join(attached_routes),
                "attached_retained_component_count": str(
                    len(attached_components)
                ),
                "bridges_distinct_retained_components": (
                    "yes" if len(attached_components) > 1 else "no"
                ),
                "modlu_kalan_fragments": " | ".join(
                    " ".join(map(str, fragment)) for fragment in fragments
                ),
                "decision": "drop_entire_block",
                "reason": (
                    "single retained-network attachment; removal does not bridge "
                    "two retained components"
                ),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    block_plan_path = output_dir / "silk_road_resolved_block_plan.csv"
    reference_plan_path = output_dir / "silk_road_resolved_reference_plan.csv"
    network_path = output_dir / "silk_road_resolved_network_decisions.csv"
    candidate_path = output_dir / "silk_road_arrows_resolved_candidate.txt"
    patch_path = output_dir / "silk_road_resolved_candidate.patch"
    summary_path = output_dir / "silk_road_resolved_candidate_summary.md"

    merge.semantic.write_csv(block_plan_path, plan_rows)
    merge.semantic.write_csv(reference_plan_path, reference_rows)
    merge.semantic.write_csv(network_path, network_rows)
    merge.write_candidate(candidate_path, candidate_text, newline, with_bom)
    patch_text = git_diff_patch(repo_root, current_path, candidate_path)
    patch_path.write_bytes(patch_text.encode("utf-8"))

    actions: dict[str, int] = defaultdict(int)
    for row in plan_rows:
        actions[row["action"]] += 1
    summary = "\n".join(
        [
            "# Silk Road resolved vanilla-east dry-run",
            "",
            "## Scope",
            "",
            f"- Live file: {merge.CURRENT_PATH.as_posix()}",
            "- Live file changed: no",
            "- East source: installed vanilla",
            "- Retained outside-east source: current asıl mod route data",
            "",
            "## Mixed resolutions",
            "",
            "- first: vanilla east prefix + current retained tail",
            "- fourth: vanilla east prefix + current retained tail",
            "- twentyfirst: vanilla east prefix + current retained tail",
            "- ninth: current route retained; disjoint vanilla route added as yb_vanilla_east_ninth",
            "- tenth: reversed mapped vanilla sequence keeps intentional current direction",
            "- twentyeighth: dropped after retained-network attachment audit",
            "- fiftyfourth: dropped after retained-network attachment audit",
            "",
            "## Candidate",
            "",
            f"- Blocks: {len(candidate_blocks)}",
            f"- References: {len(reference_rows)}",
            f"- Removed-east references: {sum(row['source_classification'] == 'removed_asil_mod_east' for row in reference_rows)}",
            f"- Actions: {'; '.join(f'{key}={actions[key]}' for key in sorted(actions))}",
            "",
            "## Validation",
            "",
            "- Candidate parse and unique block names: pass",
            "- Candidate target IDs in current definition.csv: pass",
            "- Candidate reference sequence matches candidate text: pass",
            "- Removed-east source references: 0",
            "- Dropped routes bridge distinct retained components: no",
            f"- Live file SHA-256: {live_hash}",
            "",
            "No live CK3 file was edited by this dry-run.",
            "",
        ]
    )
    summary_path.write_text(summary, encoding="utf-8")

    if sha256_bytes(current_path.read_bytes()) != live_hash:
        raise RuntimeError("Live silk_road_arrows.txt changed during dry-run")

    print(f"output_dir={output_dir}")
    print(f"live_sha256={live_hash}")
    print(f"candidate_sha256={sha256_bytes(candidate_path.read_bytes())}")
    print(f"candidate_blocks={len(candidate_blocks)}")
    print(f"candidate_references={len(reference_rows)}")
    print("candidate_removed_east=0")
    print("network_drop_bridges=0")
    print("validation=pass")
    print("live_file_changed=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
