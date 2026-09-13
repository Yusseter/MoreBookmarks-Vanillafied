from pathlib import Path
import csv
import re

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ROOT = PROJECT_ROOT / "BookmarksGit"
OUT = (
    PROJECT_ROOT
    / ".codex/works/analysis/generated/mpe_import_add_1/consistency_fix"
)
IDS = {12922, 13359, 13360, 13361, 13362}
LOCATOR_IDS = {13359, 13360, 13361, 13362}
LOCATOR_FILES = [
    "activities.txt",
    "building_locators.txt",
    "combat_locators.txt",
    "player_stack_locators.txt",
    "siege_locators.txt",
    "special_building_locators.txt",
]


def read_lines(path):
    data = path.read_bytes()
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig" if bom else "utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    trailing = text.endswith(("\n", "\r"))
    return text.splitlines(), newline, bom, trailing


def write_lines(path, lines, newline, bom, trailing=True):
    text = newline.join(lines)
    if trailing:
        text += newline
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def strip_comment(line):
    return line.split("#", 1)[0]


def remove_province_history_blocks(path, ids, report):
    lines, newline, bom, trailing = read_lines(path)
    out = []
    i = 0
    while i < len(lines):
        m = re.match(r"^\s*(\d+)\s*=\s*\{", strip_comment(lines[i]))
        if not m or int(m.group(1)) not in ids:
            out.append(lines[i])
            i += 1
            continue
        province_id = int(m.group(1))
        start = i
        depth = 0
        block = []
        while i < len(lines):
            block.append(lines[i])
            code = strip_comment(lines[i])
            depth += code.count("{") - code.count("}")
            i += 1
            if depth == 0:
                break
        # Trim one blank line before removed block if it was only a separator.
        if out and out[-1].strip() == "":
            out.pop()
        report.append({
            "file": str(path.relative_to(ROOT)),
            "id": province_id,
            "action": "removed_province_history_block",
            "old_line_start": start + 1,
            "old_line_count": len(block),
        })
    write_lines(path, out, newline, bom, trailing)


def remove_terrain_lines(path, ids, report):
    lines, newline, bom, trailing = read_lines(path)
    out = []
    for idx, line in enumerate(lines, 1):
        m = re.match(r"^\s*(\d+)\s*=", strip_comment(line))
        if m and int(m.group(1)) in ids:
            report.append({
                "file": str(path.relative_to(ROOT)),
                "id": int(m.group(1)),
                "action": "removed_province_terrain_line",
                "old_line_start": idx,
                "old_line_count": 1,
            })
            continue
        out.append(line)
    write_lines(path, out, newline, bom, trailing)


def locator_block_id(block):
    for line in block:
        m = re.search(r"\bid\s*=\s*(\d+)\b", strip_comment(line))
        if m:
            return int(m.group(1))
    return None


def remove_locator_blocks(path, ids, report):
    lines, newline, bom, trailing = read_lines(path)
    out = []
    i = 0
    while i < len(lines):
        if not re.match(r"^\s*\{\s*(?:#.*)?$", lines[i]):
            out.append(lines[i])
            i += 1
            continue
        start = i
        depth = 0
        block = []
        while i < len(lines):
            block.append(lines[i])
            code = strip_comment(lines[i])
            depth += code.count("{") - code.count("}")
            i += 1
            if depth == 0:
                break
        bid = locator_block_id(block)
        if bid in ids:
            report.append({
                "file": str(path.relative_to(ROOT)),
                "id": bid,
                "action": "removed_map_object_locator_block",
                "old_line_start": start + 1,
                "old_line_count": len(block),
            })
        else:
            out.extend(block)
    write_lines(path, out, newline, bom, trailing)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    remove_terrain_lines(ROOT / r"common\province_terrain\00_province_terrain.txt", IDS, report)
    remove_province_history_blocks(ROOT / r"history\provinces\00_yb_MPE_PROVINCES.txt", IDS, report)
    for file_name in LOCATOR_FILES:
        remove_locator_blocks(ROOT / "gfx" / "map" / "map_object_data" / file_name, LOCATOR_IDS, report)
    report_path = OUT / "mpe_alias_placeholder_residual_cleanup_report.csv"
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "id", "action", "old_line_start", "old_line_count"])
        writer.writeheader()
        writer.writerows(report)
    print(f"removed rows/blocks: {len(report)}")
    print(report_path)


if __name__ == "__main__":
    main()
