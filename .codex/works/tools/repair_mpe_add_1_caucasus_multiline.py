from pathlib import Path
import csv
import re


TARGET = Path(r"F:\Storage\Codding\git\Crusader Kings III\Yusseter MoreBookmarksPlus\BookmarksGit")
LANDED = TARGET / r"common\landed_titles\00_landed_titles.txt"
OUT = TARGET / r"works\analysis\generated\mpe_import_add_1\consistency_fix"


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


def b(indent, title, province, color, comment=""):
    head = f"{indent}{title} = {{"
    if comment:
        head += f" # {comment}"
    return [
        head,
        f"{indent}\tprovince = {province}",
        f"{indent}\tcolor = {{ {color} }}",
        f"{indent}}}",
    ]


def county(indent, title, color, baronies, comment="", extra=None):
    lines = [f"{indent}{title} = {{{(' # ' + comment) if comment else ''}", f"{indent}\tcolor = {{ {color} }}"]
    if extra:
        lines.extend(extra)
    for item in baronies:
        lines.extend(b(indent + "\t", *item))
    lines.append(f"{indent}}}")
    return lines


def duchy(indent, title, color, counties, capital="", comment=""):
    lines = [f"{indent}{title} = {{{(' # ' + comment) if comment else ''}", f"{indent}\tcolor = {{ {color} }}"]
    if capital:
        lines.append(f"{indent}\tcapital = {capital}")
    for block in counties:
        lines.append("")
        lines.extend(block)
    lines.append(f"{indent}}}")
    return lines


def replace_range(lines, start_pattern, end_pattern, replacement, label, report):
    start = find_line(lines, start_pattern)
    end = find_line(lines, end_pattern, start + 1)
    report.append({"label": label, "old_line_count": end - start, "new_line_count": len(replacement)})
    lines[start:end] = replacement
    return lines


def build_caucasus_block():
    I3 = "\t\t\t"
    d_alania = duchy("\t\t", "d_alania", "85 50 22", [
        county(I3, "c_maghas", "85 50 22", [
            ("b_maghas", 5299, "85 50 22", ""),
            ("b_arkhyz", 13271, "85 50 22", "Yusseter: MPE_21397"),
            ("b_psebai", 13272, "85 50 22", "Yusseter: MPE_21398"),
            ("b_tkhach", 13273, "85 50 22", "Yusseter: MPE_21399"),
        ]),
        county(I3, "c_alania", "85 50 22", [
            ("b_baksan", 606, "54 25 8", "Yusseter: MPE_606"),
            ("b_burgusan", 13284, "54 25 8", "Yusseter: MPE_21410"),
            ("b_chegem", 13285, "54 25 8", "Yusseter: MPE_21411"),
            ("b_malkar", 13286, "54 25 8", "Yusseter: MPE_21412"),
        ]),
        county(I3, "c_besinada", "34 5 0", [
            ("b_besinada", 5303, "54 25 8", "Yusseter: MPE_5303"),
            ("b_etzeri", 13288, "54 25 8", "Yusseter: MPE_21414"),
        ]),
        county(I3, "c_majar", "54 25 8", [
            ("b_majar", 13287, "54 25 8", "Yusseter: MPE_21413"),
            ("b_petigoria", 5344, "54 25 8", "Yusseter: MPE_5344"),
        ]),
        county(I3, "c_aorsia", "75 70 22", [
            ("b_aorsi", 13277, "85 50 22", "Yusseter: MPE_21403"),
            ("b_upper_aorsi", 13278, "85 50 22", "Yusseter: MPE_21404"),
        ]),
        county(I3, "c_maikop", "85 55 27", [
            ("b_maikop", 13279, "85 50 22", "Yusseter: MPE_21405"),
            ("b_yegerukhaj", 5301, "85 50 22", "Yusseter: MPE_5301"),
            ("b_betzini", 13280, "85 50 22", "Yusseter: MPE_21406"),
        ]),
        county(I3, "c_skhimar", "54 25 8", [
            ("b_skhimar", 13274, "85 50 22", "Yusseter: MPE_21400"),
            ("b_senti", 13275, "85 50 22", "Yusseter: MPE_21401"),
            ("b_teberda", 13276, "85 50 22", "Yusseter: MPE_21402"),
            ("b_shoana", 5300, "85 50 22", "Yusseter: MPE_5300"),
        ]),
        county(I3, "c_tapanta", "85 55 22", [
            ("b_tapanta", 13281, "85 50 22", "Yusseter: MPE_21407"),
            ("b_abazin", 13282, "85 50 22", "Yusseter: MPE_21408"),
            ("b_psyzh", 13283, "85 50 22", "Yusseter: MPE_21409"),
        ]),
    ], capital="c_maghas", comment="Yusseter: MPE Add 1 consistency repaired")

    d_ossetia = duchy("\t\t", "d_ossetia", "74 25 8", [
        county(I3, "c_ossetia", "74 25 8", [
            ("b_zaur", 603, "54 25 8", ""),
            ("b_nazran", 13289, "54 25 8", "Yusseter: MPE_21415"),
            ("b_beslan", 13290, "54 25 8", "Yusseter: MPE_21416"),
            ("b_angusht", 13291, "54 25 8", "Yusseter: MPE_21417"),
            ("b_targim", 13295, "54 25 8", "Yusseter: moved from c_dvaletia/MPE_21422"),
        ], extra=["\t\t\t\tcultural_names = { name_list_alan = cn_iryston }"]),
        county(I3, "c_iron", "85 50 22", [
            ("b_gaeliat", 13292, "54 25 8", "Yusseter: MPE_21418"),
            ("b_dargavs", 13293, "54 25 8", "Yusseter: MPE_21419"),
            ("b_alagir", 13294, "54 25 8", "Yusseter: MPE_21420"),
        ]),
        county(I3, "c_digoria", "59 29 8", [
            ("b_digora", 5302, "54 25 8", ""),
            ("b_tatartopa", 13299, "54 25 8", "Yusseter: MPE_21427"),
        ]),
        county(I3, "c_cabardinia", "54 25 8", [
            ("b_cabarda", 13296, "54 25 8", "Yusseter: MPE_21424"),
            ("b_cherek", 13297, "54 25 8", "Yusseter: MPE_21425"),
            ("b_nalchik", 13298, "54 25 8", "Yusseter: MPE_21426"),
        ]),
    ], comment="Yusseter: MPE Add 1 consistency repaired")
    d_ossetia.insert(2, "\t\t\tcultural_names = { name_list_alan = cn_iryston }")

    d_sarir = duchy("\t\t", "d_sarir", "128 40 20", [
        county(I3, "c_gumik", "148 35 9", [
            ("b_gumik", 5342, "148 35 9", ""),
            ("b_kumukh", 675, "128 40 20", ""),
            ("b_shuraozen", 13326, "128 40 20", "Yusseter: MPE_21454"),
        ]),
    ], capital="c_philan", comment="Yusseter: MPE Add 1 consistency repaired")

    d_simsir = duchy("\t\t", "d_simsir", "151 41 30", [
        county(I3, "c_simsir", "151 41 30", [
            ("b_gumse", 5306, "148 35 9", ""),
            ("b_oyskhara", 13329, "148 35 9", "Yusseter: MPE_21458"),
            ("b_endirey", 13330, "148 35 9", "Yusseter: MPE_21459"),
            ("b_simsir", 13331, "148 35 9", "Yusseter: MPE_21460"),
        ]),
        county(I3, "c_durdzukia", "148 35 9", [
            ("b_durdzukia", 13332, "148 35 9", "Yusseter: MPE_21461"),
            ("b_sunzha", 13333, "148 35 9", "Yusseter: MPE_21462"),
            ("b_marta", 13334, "148 35 9", "Yusseter: MPE_21463"),
        ]),
        county(I3, "c_malkhia", "143 37 9", [
            ("b_iskark", 13335, "148 35 9", "Yusseter: MPE_21464"),
            ("b_argun", 13336, "148 35 9", "Yusseter: MPE_21465"),
        ]),
    ], capital="c_simsir", comment="Yusseter: MPE Add 1 consistency repaired")

    return d_alania + [""] + d_ossetia + [""] + d_sarir + [""] + d_simsir + ["\t}", ""]


def build_derbent_block():
    I3 = "\t\t\t"
    return duchy("\t\t", "d_derbent", "89 75 80", [
        county(I3, "c_derbent", "203 76 76", [
            ("b_derbent", 674, "203 76 76", ""),
            ("b_kaitag", 13337, "128 40 20", "Yusseter: MPE_21467"),
            ("b_utamysh", 13338, "128 40 20", "Yusseter: MPE_21468"),
            ("b_gamri", 13339, "128 40 20", "Yusseter: MPE_21469"),
        ]),
        county(I3, "c_balanjar", "148 60 25", [
            ("b_varachan", 13340, "128 40 20", "Yusseter: MPE_21470"),
            ("b_tarki", 13341, "128 40 20", "Yusseter: MPE_21471"),
            ("b_balanjar", 5304, "128 40 20", ""),
        ]),
        county(I3, "c_avaria", "148 70 25", [
            ("b_kubachi", 13342, "128 40 20", "Yusseter: MPE_21473"),
            ("b_philan", 13327, "128 40 20", "Yusseter: moved from c_lazia/MPE_21456"),
            ("b_kuli", 13328, "128 40 20", "Yusseter: moved from c_lazia/MPE_21457"),
        ]),
        county(I3, "c_darginia", "138 48 20", [
            ("b_zirichgeran", 13343, "128 40 20", "Yusseter: MPE_21475"),
            ("b_tabarsaran", 13345, "128 40 20", "Yusseter: MPE_21476"),
            ("b_urkarakh", 13346, "128 40 20", "Yusseter: MPE_21477"),
        ]),
        county(I3, "c_lezgin", "128 40 20", [
            ("b_lezgin", 13347, "128 40 20", "Yusseter: MPE_21478"),
            ("b_richa", 13348, "128 40 20", "Yusseter: MPE_21479"),
            ("b_chiraggala", 13349, "128 40 20", "Yusseter: MPE_21481"),
        ]),
        county(I3, "c_maskut", "108 40 20", [
            ("b_kuba", 13350, "128 40 20", "Yusseter: MPE_21482"),
            ("b_shabran", 5341, "128 40 20", ""),
            ("b_hayzan", 13351, "128 40 20", "Yusseter: MPE_21483"),
            ("b_chol", 13352, "128 40 20", "Yusseter: MPE_21484"),
            ("b_maskut", 13353, "128 40 20", "Yusseter: MPE_21485"),
        ]),
    ], capital="c_derbent", comment="Yusseter: MPE Add 1 consistency repaired")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lines, newline, bom, trailing = read_lines(LANDED)
    report = []
    lines = replace_range(lines, r"^\s*d_alania\s*=", r"^\s*k_shirvan\s*=", build_caucasus_block(), "k_caucasus_multiline", report)
    lines = replace_range(lines, r"^\s*d_derbent\s*=", r"^\s*d_shirvan\s*=", build_derbent_block() + [""], "d_derbent_multiline", report)
    write_lines(LANDED, lines, newline, bom, trailing)
    with (OUT / "mpe_landed_titles_caucasus_multiline_repair_report.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["label", "old_line_count", "new_line_count"])
        writer.writeheader()
        writer.writerows(report)
    print("MPE Caucasus multiline landed_titles repair applied")


if __name__ == "__main__":
    main()
