from pathlib import Path
import csv
import re


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TARGET = PROJECT_ROOT / "BookmarksGit"
LANDED = TARGET / r"common\landed_titles\00_landed_titles.txt"
OUT = PROJECT_ROOT / r".codex\works\analysis\generated\mpe_import_add_1\consistency_fix"


def read_lines(path):
    data = path.read_bytes()
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig" if bom else "utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.splitlines(), newline, bom, text.endswith(("\n", "\r"))


def write_lines(path, lines, newline, bom, trailing):
    text = newline.join(lines)
    if trailing:
        text += newline
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def find_line(lines, pattern, start=0):
    rx = re.compile(pattern)
    for i in range(start, len(lines)):
        if rx.search(lines[i]):
            return i
    raise RuntimeError(f"anchor not found: {pattern}")


C_KUBAN = [
    "\t\t\tc_kuban = { # Yusseter: MPE Add 1 consistency repaired",
    "\t\t\t\tcolor = { 231 185 93 }",
    "\t\t\t\tb_kuban = { # Yusseter: MPE_21394",
    "\t\t\t\t\tprovince = 13158",
    "\t\t\t\t\tcolor = { 100 72 15 }",
    "\t\t\t\t}",
    "\t\t\t\tb_soleny = {",
    "\t\t\t\t\tprovince = 5336",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t\tb_lukuka = { # Yusseter: MPE_21395",
    "\t\t\t\t\tprovince = 13160",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t\tb_papagia = {",
    "\t\t\t\t\tprovince = 5289",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t}",
    "",
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lines, newline, bom, trailing = read_lines(LANDED)
    report = []

    start = find_line(lines, r"^\s*d_klimata\s*=")
    end = find_line(lines, r"^\s*#From CE\b", start + 1)
    report.append({"label": "remove_residual_d_klimata", "old_line_count": end - start, "new_line_count": 0})
    del lines[start:end]

    start = find_line(lines, r"^\s*c_kuban\s*=")
    end = find_line(lines, r"^\s*c_khumar\s*=", start + 1)
    report.append({"label": "repair_c_kuban", "old_line_count": end - start, "new_line_count": len(C_KUBAN)})
    lines[start:end] = C_KUBAN

    write_lines(LANDED, lines, newline, bom, trailing)
    with (OUT / "mpe_landed_titles_residual_repair_report.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["label", "old_line_count", "new_line_count"])
        writer.writeheader()
        writer.writerows(report)
    print("MPE landed_titles residual repair applied")


if __name__ == "__main__":
    main()
