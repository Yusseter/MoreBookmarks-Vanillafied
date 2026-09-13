import argparse
import csv
import re
import subprocess
from pathlib import Path

import audit_upstream_merge_state as audit
from apply_mpe_landed_title_relocations import read_text_lines, write_text_lines


LANDED_RELATIVE_PATH = "BookmarksGit/common/landed_titles/00_landed_titles.txt"
DEFAULT_SOURCE_REVISION = "99493c7e88615d3f4001e1f85d5d47de7830a060"
CAPITAL_FIXES = {
    "d_laamp_lembongs_band": ("c_mataram", "c_JAV_mataram"),
    "d_laamp_stormbringers": ("c_thanh_long", "c_thang_long"),
}
COLOR_FIXES = {
    "d_daksina_kosala": ("105 150 41", "105 120 41"),
}
CHILD_ORDERS = {
    "k_dornogovi": [
        "d_gobi_dadaels",
        "d_em_wuguguo",
        "d_gobi_shatuoguo",
        "d_teriqan_china",
        "d_SW_heicheziguo",
    ],
    "k_guishi": ["d_guiyi", "d_yijinai", "d_aksay"],
    "k_xia": ["d_ganzhou", "d_zhenfan", "d_liangzhou", "d_qilin"],
}


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]
    parser = argparse.ArgumentParser(
        description="Apply the verified safe landed-title resolutions for the active upstream merge."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--source-revision", default=DEFAULT_SOURCE_REVISION)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def snapshot(lines: list[str], newline: str, trailing: bool) -> audit.Snapshot:
    text = newline.join(lines)
    if trailing:
        text += newline
    return audit.build_snapshot("working", text)


def unique_block(state: audit.Snapshot, title_id: str) -> audit.landed.TitleBlock:
    if state.duplicate_counts.get(title_id):
        raise RuntimeError(f"duplicate title blocks prevent safe edit: {title_id}")
    block = state.titles.get(title_id)
    if not block:
        raise RuntimeError(f"missing title block: {title_id}")
    return block


def git_file(repo_root: Path, revision: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{revision}:{LANDED_RELATIVE_PATH}"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"cannot read source revision {revision}: {message}")
    return result.stdout.decode("utf-8-sig", errors="strict")


def replace_capital(
    lines: list[str],
    newline: str,
    trailing: bool,
    title_id: str,
    old_id: str,
    new_id: str,
) -> str:
    state = snapshot(lines, newline, trailing)
    unique_block(state, title_id)
    properties = state.properties.get(title_id, {}).get("capital", [])
    if len(properties) != 1:
        raise RuntimeError(f"expected one direct capital in {title_id}, found {len(properties)}")
    item = properties[0]
    index = item.start_line - 1
    if re.search(rf"\b{re.escape(new_id)}\b", lines[index]):
        return "already_applied"
    if not re.search(rf"\b{re.escape(old_id)}\b", lines[index]):
        raise RuntimeError(f"unexpected capital value in {title_id}: {lines[index].strip()}")
    lines[index] = re.sub(rf"\b{re.escape(old_id)}\b", new_id, lines[index], count=1)
    return f"replaced {old_id} -> {new_id}"


def color_pattern(value: str) -> str:
    return r"\{\s*" + r"\s+".join(re.escape(part) for part in value.split()) + r"\s*\}"


def replace_color(
    lines: list[str],
    newline: str,
    trailing: bool,
    title_id: str,
    old_value: str,
    new_value: str,
) -> str:
    state = snapshot(lines, newline, trailing)
    unique_block(state, title_id)
    properties = state.properties.get(title_id, {}).get("color", [])
    if len(properties) != 1:
        raise RuntimeError(f"expected one direct color in {title_id}, found {len(properties)}")
    item = properties[0]
    index = item.start_line - 1
    if re.search(color_pattern(new_value), lines[index]):
        return "already_applied"
    old_pattern = color_pattern(old_value)
    if not re.search(old_pattern, lines[index]):
        raise RuntimeError(f"unexpected color value in {title_id}: {lines[index].strip()}")
    lines[index] = re.sub(old_pattern, f"{{ {new_value} }}", lines[index], count=1)
    return f"replaced {old_value} -> {new_value}"


def remove_title_chunk(
    lines: list[str],
    state: audit.Snapshot,
    title_id: str,
) -> list[str]:
    block = unique_block(state, title_id)
    parent_id = state.contexts[title_id].parent_id
    parent = unique_block(state, parent_id)
    start = block.start_line - 1
    end = block.end_line
    parent_closing = parent.end_line - 1
    while end < parent_closing and not lines[end].strip():
        end += 1
    chunk = lines[start:end]
    del lines[start:end]
    return chunk


def add_pandya_wrapper(
    lines: list[str],
    newline: str,
    trailing: bool,
    source_text: str,
) -> str:
    state = snapshot(lines, newline, trailing)
    if "k_pandya" in state.titles:
        if state.contexts.get("d_pandya_nadu", audit.TitleContext()).parent_id == "k_pandya":
            return "already_applied"
        raise RuntimeError("k_pandya exists but d_pandya_nadu is not its child")
    if state.contexts.get("d_pandya_nadu", audit.TitleContext()).parent_id != "k_tamilakam":
        raise RuntimeError("d_pandya_nadu is not under the expected current parent k_tamilakam")

    source = audit.build_snapshot("source", source_text)
    source_kingdom = unique_block(source, "k_pandya")
    source_duchy = unique_block(source, "d_pandya_nadu")
    if source.contexts["d_pandya_nadu"].parent_id != "k_pandya":
        raise RuntimeError("source d_pandya_nadu is not under source k_pandya")

    current_duchy = remove_title_chunk(lines, state, "d_pandya_nadu")
    state = snapshot(lines, newline, trailing)
    tamilakam = unique_block(state, "k_tamilakam")

    source_lines = source.lines
    prefix = source_lines[source_kingdom.start_line - 1 : source_duchy.start_line - 1]
    closing = source_lines[source_kingdom.end_line - 1].rstrip("\r\n")
    wrapper = [line.rstrip("\r\n") for line in prefix]
    wrapper.extend(current_duchy)
    if wrapper and wrapper[-1].strip():
        wrapper.append("")
    wrapper.append(closing)
    wrapper.append("")
    lines[tamilakam.start_line - 1 : tamilakam.start_line - 1] = wrapper
    return "added k_pandya and moved d_pandya_nadu from k_tamilakam"


def reorder_children(
    lines: list[str],
    newline: str,
    trailing: bool,
    parent_id: str,
    desired_order: list[str],
) -> str:
    state = snapshot(lines, newline, trailing)
    parent = unique_block(state, parent_id)
    current_order = list(state.contexts[parent_id].child_ids)
    if current_order == desired_order:
        return "already_applied"
    if set(current_order) != set(desired_order) or len(current_order) != len(desired_order):
        raise RuntimeError(
            f"child set mismatch for {parent_id}: current={current_order}, expected={desired_order}"
        )

    children = [unique_block(state, child_id) for child_id in current_order]
    chunks: dict[str, list[str]] = {}
    for index, child in enumerate(children):
        start = child.start_line - 1
        end = (
            children[index + 1].start_line - 1
            if index + 1 < len(children)
            else parent.end_line - 1
        )
        chunks[child.title_id] = lines[start:end]

    region_start = children[0].start_line - 1
    region_end = parent.end_line - 1
    replacement: list[str] = []
    for child_id in desired_order:
        replacement.extend(chunks[child_id])
    lines[region_start:region_end] = replacement
    return f"reordered {' | '.join(current_order)} -> {' | '.join(desired_order)}"


def validate(
    lines: list[str],
    newline: str,
    trailing: bool,
    duplicates_before: dict[str, int],
) -> None:
    state = snapshot(lines, newline, trailing)
    if audit.CONFLICT_MARKER_RE.search(newline.join(lines)):
        raise RuntimeError("conflict marker found after edit")
    if sum(audit.landed.brace_delta(line) for line in lines) != 0:
        raise RuntimeError("brace depth is not zero after edit")
    if dict(state.duplicate_counts) != duplicates_before:
        raise RuntimeError(
            f"duplicate title inventory changed: before={duplicates_before}, after={dict(state.duplicate_counts)}"
        )
    if state.contexts["k_pandya"].parent_id != "e_chola":
        raise RuntimeError("k_pandya does not resolve under e_chola")
    if state.contexts["d_pandya_nadu"].parent_id != "k_pandya":
        raise RuntimeError("d_pandya_nadu does not resolve under k_pandya")
    for parent_id, desired_order in CHILD_ORDERS.items():
        if state.contexts[parent_id].child_ids != desired_order:
            raise RuntimeError(f"final child order mismatch for {parent_id}")
    for title_id, (_old_id, new_id) in CAPITAL_FIXES.items():
        raw, _line = audit.property_raw(state, title_id, "capital")
        if not re.search(rf"\b{re.escape(new_id)}\b", raw):
            raise RuntimeError(f"final capital mismatch for {title_id}: {raw.strip()}")

    for title_id, (_old_value, new_value) in COLOR_FIXES.items():
        raw, _line = audit.property_raw(state, title_id, "color")
        if not re.search(color_pattern(new_value), raw):
            raise RuntimeError(f"final color mismatch for {title_id}: {raw.strip()}")

def write_report(output_dir: Path, rows: list[dict[str, str]], applied: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "landed_title_safe_resolution_apply.csv"
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["action", "target", "result"])
        writer.writeheader()
        writer.writerows(rows)
    summary_path = output_dir / "landed_title_safe_resolution_apply_summary.md"
    summary_path.write_text(
        "\n".join(
            [
                "# Landed Title Safe Resolution Apply",
                "",
                f"- mode: `{'apply' if applied else 'dry-run'}`",
                f"- actions: `{len(rows)}`",
                "- validation: `passed`",
                "- Git index modified: `no`",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    landed_path = repo_root / LANDED_RELATIVE_PATH
    lines, newline, bom, trailing = read_text_lines(landed_path)
    initial = snapshot(lines, newline, trailing)
    duplicates_before = dict(initial.duplicate_counts)
    source_text = git_file(repo_root, args.source_revision)

    rows: list[dict[str, str]] = []
    for title_id, (old_id, new_id) in CAPITAL_FIXES.items():
        result = replace_capital(lines, newline, trailing, title_id, old_id, new_id)
        rows.append({"action": "replace_capital", "target": title_id, "result": result})
    for title_id, (old_value, new_value) in COLOR_FIXES.items():
        result = replace_color(lines, newline, trailing, title_id, old_value, new_value)
        rows.append({"action": "replace_color", "target": title_id, "result": result})


    result = add_pandya_wrapper(lines, newline, trailing, source_text)
    rows.append({"action": "add_and_move", "target": "k_pandya/d_pandya_nadu", "result": result})

    for parent_id, desired_order in CHILD_ORDERS.items():
        result = reorder_children(lines, newline, trailing, parent_id, desired_order)
        rows.append({"action": "reorder_children", "target": parent_id, "result": result})

    validate(lines, newline, trailing, duplicates_before)
    if args.apply:
        write_text_lines(landed_path, lines, newline, bom, trailing)
    output_dir = repo_root / ".codex/works/analysis/generated/upstream_merge_audit"
    write_report(output_dir, rows, args.apply)
    print(f"mode={'apply' if args.apply else 'dry-run'}")
    for row in rows:
        print(f"{row['action']}|{row['target']}|{row['result']}")
    print("validation=passed")


if __name__ == "__main__":
    main()
