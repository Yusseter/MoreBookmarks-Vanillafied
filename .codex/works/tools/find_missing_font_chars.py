from __future__ import annotations

import argparse
import csv
import json
import re
import struct
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


BOOKMARKS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FONT_PATH = BOOKMARKS_ROOT / "fonts" / "mapfont" / "Paradox_King_Script.otf"
DEFAULT_LOC_FOLDER = BOOKMARKS_ROOT / "localization"
DEFAULT_OUTPUT_DIR = (
    BOOKMARKS_ROOT
    / "works"
    / "analysis"
    / "generated"
    / "font_missing_chars_paradox_king_script"
)

LOC_VALUE_RE = re.compile(r"^\s*[^#\s][^:]*:\d*\s*(?P<value>.*)$")
QUOTED_VALUE_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def read_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def read_i16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">h", data, offset)[0]


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def codepoint_to_char(codepoint: int) -> str | None:
    if 0 <= codepoint <= 0x10FFFF:
        try:
            return chr(codepoint)
        except ValueError:
            return None
    return None


def chars_from_fonttools(font_path: Path) -> set[str] | None:
    try:
        from fontTools.ttLib import TTFont  # type: ignore
    except ModuleNotFoundError:
        return None

    chars: set[str] = set()
    with TTFont(font_path) as font:
        for table in font["cmap"].tables:
            if not table.isUnicode():
                continue
            for codepoint in table.cmap.keys():
                char = codepoint_to_char(codepoint)
                if char is not None:
                    chars.add(char)
    return chars


def parse_cmap_format_0(data: bytes, start: int, chars: set[str]) -> None:
    for codepoint, glyph_id in enumerate(data[start + 6 : start + 262]):
        if glyph_id:
            chars.add(chr(codepoint))


def parse_cmap_format_4(data: bytes, start: int, chars: set[str]) -> None:
    length = read_u16(data, start + 2)
    end = start + length
    seg_count = read_u16(data, start + 6) // 2

    end_codes_offset = start + 14
    start_codes_offset = end_codes_offset + (2 * seg_count) + 2
    id_deltas_offset = start_codes_offset + (2 * seg_count)
    id_range_offsets_offset = id_deltas_offset + (2 * seg_count)

    for index in range(seg_count):
        end_code = read_u16(data, end_codes_offset + (2 * index))
        start_code = read_u16(data, start_codes_offset + (2 * index))
        id_delta = read_i16(data, id_deltas_offset + (2 * index))
        id_range_offset_pos = id_range_offsets_offset + (2 * index)
        id_range_offset = read_u16(data, id_range_offset_pos)

        if start_code == 0xFFFF and end_code == 0xFFFF:
            continue

        for codepoint in range(start_code, end_code + 1):
            glyph_id = 0
            if id_range_offset == 0:
                glyph_id = (codepoint + id_delta) % 65536
            else:
                glyph_pos = id_range_offset_pos + id_range_offset + (2 * (codepoint - start_code))
                if glyph_pos + 2 <= end:
                    glyph_id = read_u16(data, glyph_pos)
                    if glyph_id:
                        glyph_id = (glyph_id + id_delta) % 65536
            if glyph_id:
                chars.add(chr(codepoint))


def parse_cmap_format_6(data: bytes, start: int, chars: set[str]) -> None:
    first_code = read_u16(data, start + 6)
    entry_count = read_u16(data, start + 8)
    glyph_array_offset = start + 10
    for offset in range(entry_count):
        glyph_id = read_u16(data, glyph_array_offset + (2 * offset))
        if glyph_id:
            char = codepoint_to_char(first_code + offset)
            if char is not None:
                chars.add(char)


def parse_cmap_format_10(data: bytes, start: int, chars: set[str]) -> None:
    start_char_code = read_u32(data, start + 12)
    num_chars = read_u32(data, start + 16)
    glyph_array_offset = start + 20
    for offset in range(num_chars):
        glyph_id = read_u16(data, glyph_array_offset + (2 * offset))
        if glyph_id:
            char = codepoint_to_char(start_char_code + offset)
            if char is not None:
                chars.add(char)


def parse_cmap_format_12_or_13(data: bytes, start: int, chars: set[str]) -> None:
    num_groups = read_u32(data, start + 12)
    group_offset = start + 16
    for index in range(num_groups):
        record = group_offset + (12 * index)
        start_char_code = read_u32(data, record)
        end_char_code = read_u32(data, record + 4)
        for codepoint in range(start_char_code, end_char_code + 1):
            char = codepoint_to_char(codepoint)
            if char is not None:
                chars.add(char)


def chars_from_opentype_cmap(font_path: Path) -> set[str]:
    data = font_path.read_bytes()
    num_tables = read_u16(data, 4)
    table_record_offset = 12
    cmap_offset = None
    cmap_length = None

    for index in range(num_tables):
        record = table_record_offset + (16 * index)
        tag = data[record : record + 4]
        if tag == b"cmap":
            cmap_offset = read_u32(data, record + 8)
            cmap_length = read_u32(data, record + 12)
            break

    if cmap_offset is None or cmap_length is None:
        raise ValueError(f"No cmap table found in {font_path}")

    cmap_end = cmap_offset + cmap_length
    num_subtables = read_u16(data, cmap_offset + 2)
    chars: set[str] = set()

    for index in range(num_subtables):
        record = cmap_offset + 4 + (8 * index)
        platform_id = read_u16(data, record)
        encoding_id = read_u16(data, record + 2)
        subtable_start = cmap_offset + read_u32(data, record + 4)

        if subtable_start >= cmap_end:
            continue
        if platform_id not in {0, 3}:
            continue
        if platform_id == 3 and encoding_id not in {0, 1, 10}:
            continue

        cmap_format = read_u16(data, subtable_start)
        if cmap_format == 0:
            parse_cmap_format_0(data, subtable_start, chars)
        elif cmap_format == 4:
            parse_cmap_format_4(data, subtable_start, chars)
        elif cmap_format == 6:
            parse_cmap_format_6(data, subtable_start, chars)
        elif cmap_format == 10:
            parse_cmap_format_10(data, subtable_start, chars)
        elif cmap_format in {12, 13}:
            parse_cmap_format_12_or_13(data, subtable_start, chars)

    return chars


def get_font_chars(font_path: Path) -> tuple[set[str], str]:
    fonttools_chars = chars_from_fonttools(font_path)
    if fonttools_chars is not None:
        return fonttools_chars, "fontTools"
    return chars_from_opentype_cmap(font_path), "built-in cmap parser"


def decode_simple_localization_escapes(text: str) -> str:
    return text.replace(r"\"", '"').replace(r"\\", "\\")


def iter_visible_localization_values(text: str) -> list[str]:
    values: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or stripped.startswith("l_"):
            continue

        match = LOC_VALUE_RE.match(line)
        if not match:
            continue

        raw_value = match.group("value")
        quoted = QUOTED_VALUE_RE.search(raw_value)
        if quoted:
            values.append(decode_simple_localization_escapes(quoted.group(1)))
    return values


def should_skip_char(char: str) -> bool:
    if not char.strip():
        return True
    if char == "\ufeff":
        return True
    return unicodedata.category(char).startswith("C")


def char_label(char: str) -> str:
    if char == '"':
        return '"""'
    return char


def collect_localization_chars(loc_folder: Path) -> tuple[
    Counter[str],
    Counter[str],
    dict[str, set[Path]],
    dict[str, set[Path]],
    int,
]:
    all_counts: Counter[str] = Counter()
    visible_counts: Counter[str] = Counter()
    all_files: dict[str, set[Path]] = defaultdict(set)
    visible_files: dict[str, set[Path]] = defaultdict(set)
    file_count = 0

    for path in sorted(loc_folder.rglob("*.yml")):
        file_count += 1
        text = path.read_text(encoding="utf-8-sig")

        for char in text:
            if should_skip_char(char):
                continue
            all_counts[char] += 1
            all_files[char].add(path)

        for value in iter_visible_localization_values(text):
            for char in value:
                if should_skip_char(char):
                    continue
                visible_counts[char] += 1
                visible_files[char].add(path)

    return all_counts, visible_counts, all_files, visible_files, file_count


def relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def write_report(
    output_dir: Path,
    font_path: Path,
    loc_folder: Path,
    font_source: str,
    font_chars: set[str],
    all_counts: Counter[str],
    visible_counts: Counter[str],
    all_files: dict[str, set[Path]],
    visible_files: dict[str, set[Path]],
    file_count: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    missing_visible = sorted((char for char in visible_counts if char not in font_chars), key=ord)
    missing_all = sorted((char for char in all_counts if char not in font_chars), key=ord)

    report_path = output_dir / "missing_chars_report.txt"
    csv_path = output_dir / "missing_chars.csv"
    diagnostic_csv_path = output_dir / "missing_chars_all_yml_diagnostic.csv"
    summary_path = output_dir / "summary.json"

    with report_path.open("w", encoding="utf-8", newline="\n") as report:
        report.write("Missing localization characters for font\n")
        report.write("========================================\n\n")
        report.write(f"Font: {font_path}\n")
        report.write(f"Localization folder: {loc_folder}\n")
        report.write(f"Font reader: {font_source}\n")
        report.write(f"Localization files scanned: {file_count}\n")
        report.write(f"Font characters found: {len(font_chars)}\n")
        report.write(f"Distinct visible localization characters: {len(visible_counts)}\n")
        report.write(f"Missing visible localization characters: {len(missing_visible)}\n")
        report.write(f"Missing characters anywhere in .yml files: {len(missing_all)}\n")
        report.write(
            "Note: the main report and missing_chars.csv only list visible localization values.\n"
        )
        report.write(
            "The anywhere-in-yml count is diagnostic and includes comments, keys, and syntax.\n\n"
        )

        report.write("Missing visible localization characters\n")
        report.write("---------------------------------------\n")
        if missing_visible:
            for char in missing_visible:
                name = unicodedata.name(char, "UNKNOWN")
                sample_files = sorted(visible_files[char])[:5]
                sample = ", ".join(relpath(path, BOOKMARKS_ROOT) for path in sample_files)
                report.write(
                    f"{char_label(char)}  U+{ord(char):04X}  {name}  "
                    f"count={visible_counts[char]}  files={len(visible_files[char])}"
                )
                if sample:
                    report.write(f"  sample={sample}")
                report.write("\n")
        else:
            report.write("None\n")

        report.write("\nDiagnostic file\n")
        report.write("---------------\n")
        report.write(
            "All .yml characters, including comments/keys/syntax, are written to "
            f"{diagnostic_csv_path.name}\n"
        )

    with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "char",
                "codepoint",
                "unicode_name",
                "visible_count",
                "visible_file_count",
                "all_yml_count",
                "all_yml_file_count",
                "sample_visible_files",
            ]
        )
        for char in missing_visible:
            writer.writerow(
                [
                    char,
                    f"U+{ord(char):04X}",
                    unicodedata.name(char, "UNKNOWN"),
                    visible_counts[char],
                    len(visible_files.get(char, set())),
                    all_counts[char],
                    len(all_files.get(char, set())),
                    "; ".join(
                        relpath(path, BOOKMARKS_ROOT)
                        for path in sorted(visible_files.get(char, set()))[:10]
                    ),
                ]
            )

    with diagnostic_csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "char",
                "codepoint",
                "unicode_name",
                "in_visible_values",
                "visible_count",
                "visible_file_count",
                "all_yml_count",
                "all_yml_file_count",
                "sample_visible_files",
                "sample_all_yml_files",
            ]
        )
        for char in missing_all:
            writer.writerow(
                [
                    char,
                    f"U+{ord(char):04X}",
                    unicodedata.name(char, "UNKNOWN"),
                    char in missing_visible,
                    visible_counts[char],
                    len(visible_files.get(char, set())),
                    all_counts[char],
                    len(all_files.get(char, set())),
                    "; ".join(
                        relpath(path, BOOKMARKS_ROOT)
                        for path in sorted(visible_files.get(char, set()))[:10]
                    ),
                    "; ".join(
                        relpath(path, BOOKMARKS_ROOT)
                        for path in sorted(all_files.get(char, set()))[:10]
                    ),
                ]
            )

    summary = {
        "font": str(font_path),
        "localization_folder": str(loc_folder),
        "font_reader": font_source,
        "localization_files_scanned": file_count,
        "font_characters_found": len(font_chars),
        "distinct_visible_localization_characters": len(visible_counts),
        "missing_visible_localization_characters": len(missing_visible),
        "missing_anywhere_in_yml_files": len(missing_all),
        "report": str(report_path),
        "csv": str(csv_path),
        "diagnostic_csv": str(diagnostic_csv_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find localization characters not covered by a CK3 font."
    )
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT_PATH)
    parser.add_argument("--localization", type=Path, default=DEFAULT_LOC_FOLDER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    font_path = args.font.resolve()
    loc_folder = args.localization.resolve()
    output_dir = args.output.resolve()

    if not font_path.is_file():
        raise FileNotFoundError(f"Font file not found: {font_path}")
    if not loc_folder.is_dir():
        raise FileNotFoundError(f"Localization folder not found: {loc_folder}")

    font_chars, font_source = get_font_chars(font_path)
    all_counts, visible_counts, all_files, visible_files, file_count = collect_localization_chars(
        loc_folder
    )
    write_report(
        output_dir,
        font_path,
        loc_folder,
        font_source,
        font_chars,
        all_counts,
        visible_counts,
        all_files,
        visible_files,
        file_count,
    )

    print(f"Font reader: {font_source}")
    print(f"Localization files scanned: {file_count}")
    print(f"Output folder: {output_dir}")
    print(f"Report: {output_dir / 'missing_chars_report.txt'}")
    print(f"CSV: {output_dir / 'missing_chars.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
