from pathlib import Path
import csv
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TARGET = PROJECT_ROOT / "BookmarksGit"
LANDED = TARGET / r"common\landed_titles\00_landed_titles.txt"
OUT = PROJECT_ROOT / r"development\analysis\generated\mpe_import_add_1\consistency_fix"


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


def sanitize_replacement(block):
    # Keep one-line Jomini blocks parseable: comments before `province =` would
    # comment out the actual assignment. Detailed provenance remains in CSVs.
    return [re.sub(r"# Yusseter:[^#{}]*?\s+province\s*=", "province =", line) for line in block]


def replace_range(lines, start_pattern, end_pattern, replacement, report, label):
    replacement = sanitize_replacement(replacement)
    start = find_line(lines, start_pattern)
    end = find_line(lines, end_pattern, start + 1)
    old_count = end - start
    lines[start:end] = replacement
    report.append({
        "label": label,
        "start_pattern": start_pattern,
        "end_pattern": end_pattern,
        "old_line_count": old_count,
        "new_line_count": len(replacement),
        "status": "replaced",
    })
    return lines


def replace_prefix_until(lines, start_pattern, end_pattern, replacement, report, label):
    replacement = sanitize_replacement(replacement)
    start = find_line(lines, start_pattern)
    end = find_line(lines, end_pattern, start + 1)
    old_count = end - start
    lines[start:end] = replacement
    report.append({
        "label": label,
        "start_pattern": start_pattern,
        "end_pattern": end_pattern,
        "old_line_count": old_count,
        "new_line_count": len(replacement),
        "status": "replaced_prefix",
    })
    return lines


D_CHERSON = [
    "\t\td_cherson = { # Yusseter: MPE Add 1 consistency repaired",
    "\t\t\tcolor = { 105 50 158 }",
    "",
    "\t\t\tcapital = c_kerch",
    "",
    "\t\t\tc_kerch = { # Yusseter: old Levi c_cherson/c_kerch identity kept",
    "\t\t\t\tcolor = { 124 52 63 }",
    "",
    "\t\t\t\tb_chersonesus = { # Yusseter: MPE semantic remap c_cherson_to_c_kerch",
    "\t\t\t\t\tprovince = 560",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t\tb_mangup = { # Yusseter: MPE alias donor 22832",
    "\t\t\t\t\tprovince = 9835",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t\tb_yamboli = { # Yusseter: MPE alias donor 22831",
    "\t\t\t\t\tprovince = 9836",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t\tb_yalta = { # Yusseter: MPE alias donor 22830",
    "\t\t\t\t\tprovince = 9837",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t}",
    "",
    "\t\t\tc_theodosia = { # Yusseter: MPE alias b_soldaia replaced by b_sukdak",
    "\t\t\t\tcolor = { 100 52 63 }",
    "",
    "\t\t\t\tcultural_names = {",
    "\t\t\t\t\tname_list_greek = cn_theodosia",
    "\t\t\t\t\tname_list_roman = cn_theodosia",
    "\t\t\t\t}",
    "",
    "\t\t\t\tb_sukdak = { # Yusseter: MPE alias donor 22833",
    "\t\t\t\t\tprovince = 9833",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t\tb_theodosia = { # Yusseter: MPE_561",
    "\t\t\t\t\tprovince = 561",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t\tb_alouston = { # Yusseter: MPE_22834",
    "\t\t\t\t\tprovince = 13363",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t\tb_partenit = { # Yusseter: MPE_22835",
    "\t\t\t\t\tprovince = 13364",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t}",
    "\t\t}",
    "",
]

D_ARMENIAC_PREFIX = [
    "\t\td_armeniac = {",
    "\t\t\tcolor = { 150 130 180 }",
    "",
]

D_TAMUTARAKAN = [
    "\t\td_tmutarakan = { # Yusseter: MPE Add 1 consistency repaired",
    "\t\t\tcolor = { 216 201 124 }",
    "",
    "\t\t\tcapital = c_tmutarakan",
    "\t\t\tdisable_regnal_numbers = yes",
    "",
    "\t\t\tc_tmutarakan = {",
    "\t\t\t\tcolor = { 216 201 124 }",
    "\t\t\t\tb_tmutarakan = {",
    "\t\t\t\t\tprovince = 598",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t\tb_batacrim = { # Yusseter: MPE alias donor 21385",
    "\t\t\t\t\tprovince = 9838",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t\tb_khegayk = { # Yusseter: MPE_21386",
    "\t\t\t\t\tprovince = 12923",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t\tb_phanagoria = { # Yusseter: MPE_21387",
    "\t\t\t\t\tprovince = 12924",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t\tb_utash = { # Yusseter: MPE_21388",
    "\t\t\t\t\tprovince = 12925",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t\tb_samkarsh = { # Yusseter: MPE_21389",
    "\t\t\t\t\tprovince = 12945",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t}",
    "",
    "\t\t\tc_korchev = { # Yusseter: MPE source c_kerch moved here",
    "\t\t\t\tcolor = { 208 189 155 }",
    "\t\t\t\tb_kerch = {",
    "\t\t\t\t\tprovince = 562",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t\tb_bosporos = { # Yusseter: MPE_22825",
    "\t\t\t\t\tprovince = 13354",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t\tb_kimmerikon = { # Yusseter: MPE_22826",
    "\t\t\t\t\tprovince = 13355",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t\tb_sauromateion = { # Yusseter: MPE_22827",
    "\t\t\t\t\tprovince = 13356",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t\tb_arabat = { # Yusseter: MPE_22828",
    "\t\t\t\t\tprovince = 13357",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t\tb_kazeka = { # Yusseter: MPE_22829",
    "\t\t\t\t\tprovince = 13358",
    "\t\t\t\t\tcolor = { 124 52 63 }",
    "\t\t\t\t}",
    "\t\t\t}",
    "",
    "\t\t\tc_peshe = { # Yusseter: MPE_21390/21391/5335",
    "\t\t\t\tcolor = { 83 61 5 }",
    "\t\t\t\tb_peshe = { # Yusseter: MPE_21390",
    "\t\t\t\t\tprovince = 12985",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t\tb_uspa = { # Yusseter: MPE_21391",
    "\t\t\t\t\tprovince = 12987",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t\tb_kopa = { # Yusseter: MPE_5335",
    "\t\t\t\t\tprovince = 5335",
    "\t\t\t\t\tcolor = { 66 55 10 }",
    "\t\t\t\t}",
    "\t\t\t}",
    "\t\t}",
    "",
]

D_ALANIA_TO_K_CAUCASUS_CLOSE = [
    "\t\td_alania = { # Yusseter: MPE Add 1 consistency repaired",
    "\t\t\tcolor = { 85 50 22 }",
    "\t\t\tcapital = c_maghas",
    "\t\t\tc_maghas = {",
    "\t\t\t\tcolor = { 85 50 22 }",
    "\t\t\t\tb_maghas = { province = 5299 color = { 85 50 22 } }",
    "\t\t\t\tb_arkhyz = { # Yusseter: MPE_21397 province = 13271 color = { 85 50 22 } }",
    "\t\t\t\tb_psebai = { # Yusseter: MPE_21398 province = 13272 color = { 85 50 22 } }",
    "\t\t\t\tb_tkhach = { # Yusseter: MPE_21399 province = 13273 color = { 85 50 22 } }",
    "\t\t\t}",
    "\t\t\tc_alania = {",
    "\t\t\t\tcolor = { 85 50 22 }",
    "\t\t\t\tb_baksan = { # Yusseter: MPE_606 province = 606 color = { 54 25 8 } }",
    "\t\t\t\tb_burgusan = { # Yusseter: MPE_21410 province = 13284 color = { 54 25 8 } }",
    "\t\t\t\tb_chegem = { # Yusseter: MPE_21411 province = 13285 color = { 54 25 8 } }",
    "\t\t\t\tb_malkar = { # Yusseter: MPE_21412 province = 13286 color = { 54 25 8 } }",
    "\t\t\t}",
    "\t\t\tc_besinada = {",
    "\t\t\t\tcolor = { 34 5 0 }",
    "\t\t\t\tb_besinada = { # Yusseter: MPE_5303 province = 5303 color = { 54 25 8 } }",
    "\t\t\t\tb_etzeri = { # Yusseter: MPE_21414 province = 13288 color = { 54 25 8 } }",
    "\t\t\t}",
    "\t\t\tc_majar = {",
    "\t\t\t\tcolor = { 54 25 8 }",
    "\t\t\t\tb_majar = { # Yusseter: MPE_21413 province = 13287 color = { 54 25 8 } }",
    "\t\t\t\tb_petigoria = { # Yusseter: MPE_5344 province = 5344 color = { 54 25 8 } }",
    "\t\t\t}",
    "\t\t\tc_aorsia = { color = { 75 70 22 } b_aorsi = { # Yusseter: MPE_21403 province = 13277 color = { 85 50 22 } } b_upper_aorsi = { # Yusseter: MPE_21404 province = 13278 color = { 85 50 22 } } }",
    "\t\t\tc_maikop = { color = { 85 55 27 } b_maikop = { # Yusseter: MPE_21405 province = 13279 color = { 85 50 22 } } b_yegerukhaj = { # Yusseter: MPE_5301 province = 5301 color = { 85 50 22 } } b_betzini = { # Yusseter: MPE_21406 province = 13280 color = { 85 50 22 } } }",
    "\t\t\tc_skhimar = { color = { 54 25 8 } b_skhimar = { # Yusseter: MPE_21400 province = 13274 color = { 85 50 22 } } b_senti = { # Yusseter: MPE_21401 province = 13275 color = { 85 50 22 } } b_teberda = { # Yusseter: MPE_21402 province = 13276 color = { 85 50 22 } } b_shoana = { # Yusseter: MPE_5300 province = 5300 color = { 85 50 22 } } }",
    "\t\t\tc_tapanta = { color = { 85 55 22 } b_tapanta = { # Yusseter: MPE_21407 province = 13281 color = { 85 50 22 } } b_abazin = { # Yusseter: MPE_21408 province = 13282 color = { 85 50 22 } } b_psyzh = { # Yusseter: MPE_21409 province = 13283 color = { 85 50 22 } } }",
    "\t\t}",
    "\t\td_ossetia = {",
    "\t\t\tcolor = { 74 25 8 }",
    "\t\t\tcultural_names = { name_list_alan = cn_iryston }",
    "\t\t\tc_ossetia = { color = { 74 25 8 } cultural_names = { name_list_alan = cn_iryston } b_zaur = { province = 603 color = { 54 25 8 } } b_nazran = { # Yusseter: MPE_21415 province = 13289 color = { 54 25 8 } } b_beslan = { # Yusseter: MPE_21416 province = 13290 color = { 54 25 8 } } b_angusht = { # Yusseter: MPE_21417 province = 13291 color = { 54 25 8 } } b_targim = { # Yusseter: moved from c_dvaletia/MPE_21422 province = 13295 color = { 54 25 8 } } }",
    "\t\t\tc_iron = { color = { 85 50 22 } b_gaeliat = { # Yusseter: MPE_21418 province = 13292 color = { 54 25 8 } } b_dargavs = { # Yusseter: MPE_21419 province = 13293 color = { 54 25 8 } } b_alagir = { # Yusseter: MPE_21420 province = 13294 color = { 54 25 8 } } }",
    "\t\t\tc_digoria = { color = { 59 29 8 } b_digora = { province = 5302 color = { 54 25 8 } } b_tatartopa = { # Yusseter: MPE_21427 province = 13299 color = { 54 25 8 } } }",
    "\t\t\tc_cabardinia = { color = { 54 25 8 } b_cabarda = { # Yusseter: MPE_21424 province = 13296 color = { 54 25 8 } } b_cherek = { # Yusseter: MPE_21425 province = 13297 color = { 54 25 8 } } b_nalchik = { # Yusseter: MPE_21426 province = 13298 color = { 54 25 8 } } }",
    "\t\t}",
    "\t\td_sarir = {",
    "\t\t\tcolor = { 128 40 20 }",
    "\t\t\tcapital = c_philan",
    "\t\t\tc_philan = { color = { 128 40 20 } b_khunzakh = { # Yusseter: MPE_21450 province = 13322 color = { 128 40 20 } } b_sarir = { # Yusseter: MPE_21451 province = 13323 color = { 128 40 20 } } b_datuna = { # Yusseter: MPE_21452 province = 13324 color = { 128 40 20 } } b_akhvakh = { # Yusseter: MPE_21453 province = 13325 color = { 128 40 20 } } }",
    "\t\t\tc_gumik = { color = { 148 35 9 } b_gumik = { province = 5342 color = { 148 35 9 } } b_kumukh = { province = 675 color = { 128 40 20 } } b_shuraozen = { # Yusseter: MPE_21454 province = 13326 color = { 128 40 20 } } }",
    "\t\t}",
    "\t\td_simsir = {",
    "\t\t\tcolor = { 151 41 30 }",
    "\t\t\tcapital = c_simsir",
    "\t\t\tc_simsir = { color = { 151 41 30 } b_gumse = { province = 5306 color = { 148 35 9 } } b_oyskhara = { # Yusseter: MPE_21458 province = 13329 color = { 148 35 9 } } b_endirey = { # Yusseter: MPE_21459 province = 13330 color = { 148 35 9 } } b_simsir = { # Yusseter: MPE_21460 province = 13331 color = { 148 35 9 } } }",
    "\t\t\tc_durdzukia = { color = { 148 35 9 } b_durdzukia = { # Yusseter: MPE_21461 province = 13332 color = { 148 35 9 } } b_sunzha = { # Yusseter: MPE_21462 province = 13333 color = { 148 35 9 } } b_marta = { # Yusseter: MPE_21463 province = 13334 color = { 148 35 9 } } }",
    "\t\t\tc_malkhia = { color = { 143 37 9 } b_iskark = { # Yusseter: MPE_21464 province = 13335 color = { 148 35 9 } } b_argun = { # Yusseter: MPE_21465 province = 13336 color = { 148 35 9 } } }",
    "\t\t}",
    "\t}",
    "",
]

D_DERBENT = [
    "\t\td_derbent = { # Yusseter: MPE Add 1 consistency repaired",
    "\t\t\tcolor = { 89 75 80 }",
    "\t\t\tcapital = c_derbent",
    "\t\t\tc_derbent = { color = { 203 76 76 } b_derbent = { province = 674 color = { 203 76 76 } } b_kaitag = { # Yusseter: MPE_21467 province = 13337 color = { 128 40 20 } } b_utamysh = { # Yusseter: MPE_21468 province = 13338 color = { 128 40 20 } } b_gamri = { # Yusseter: MPE_21469 province = 13339 color = { 128 40 20 } } }",
    "\t\t\tc_balanjar = { color = { 148 60 25 } b_varachan = { # Yusseter: MPE_21470 province = 13340 color = { 128 40 20 } } b_tarki = { # Yusseter: MPE_21471 province = 13341 color = { 128 40 20 } } b_balanjar = { province = 5304 color = { 128 40 20 } } }",
    "\t\t\tc_avaria = { color = { 148 70 25 } b_kubachi = { # Yusseter: MPE_21473 province = 13342 color = { 128 40 20 } } b_philan = { # Yusseter: moved from c_lazia/MPE_21456 province = 13327 color = { 128 40 20 } } b_kuli = { # Yusseter: moved from c_lazia/MPE_21457 province = 13328 color = { 128 40 20 } } }",
    "\t\t\tc_darginia = { color = { 138 48 20 } b_zirichgeran = { # Yusseter: MPE_21475 province = 13343 color = { 128 40 20 } } b_tabarsaran = { # Yusseter: MPE_21476 province = 13345 color = { 128 40 20 } } b_urkarakh = { # Yusseter: MPE_21477 province = 13346 color = { 128 40 20 } } }",
    "\t\t\tc_lezgin = { color = { 128 40 20 } b_lezgin = { # Yusseter: MPE_21478 province = 13347 color = { 128 40 20 } } b_richa = { # Yusseter: MPE_21479 province = 13348 color = { 128 40 20 } } b_chiraggala = { # Yusseter: MPE_21481 province = 13349 color = { 128 40 20 } } }",
    "\t\t\tc_maskut = { color = { 108 40 20 } b_kuba = { # Yusseter: MPE_21482 province = 13350 color = { 128 40 20 } } b_shabran = { province = 5341 color = { 128 40 20 } } b_hayzan = { # Yusseter: MPE_21483 province = 13351 color = { 128 40 20 } } b_chol = { # Yusseter: MPE_21484 province = 13352 color = { 128 40 20 } } b_maskut = { # Yusseter: MPE_21485 province = 13353 color = { 128 40 20 } } }",
    "\t\t}",
    "",
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lines, newline, bom, trailing = read_lines(LANDED)
    report = []
    lines = replace_range(lines, r"^\s*d_cherson\s*=", r"^\s*d_armeniac\s*=", D_CHERSON, report, "d_cherson")
    lines = replace_prefix_until(lines, r"^\s*d_armeniac\s*=", r"^\s*capital\s*=\s*c_helenopontus\b", D_ARMENIAC_PREFIX, report, "d_armeniac_prefix")
    lines = replace_range(lines, r"^\s*d_tmutarakan\s*=", r"^\s*d_azov\s*=", D_TAMUTARAKAN, report, "d_tmutarakan")
    lines = replace_range(lines, r"^\s*d_alania\s*=", r"^\s*k_shirvan\s*=", D_ALANIA_TO_K_CAUCASUS_CLOSE, report, "k_caucasus_after_d_zichia")
    lines = replace_range(lines, r"^\s*d_derbent\s*=", r"^\s*d_shirvan\s*=", D_DERBENT, report, "d_derbent")
    write_lines(LANDED, lines, newline, bom, trailing)
    with (OUT / "mpe_landed_titles_manual_structure_repair_report.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["label", "start_pattern", "end_pattern", "old_line_count", "new_line_count", "status"])
        writer.writeheader()
        writer.writerows(report)
    print("MPE landed_titles manual structure repair applied")


if __name__ == "__main__":
    main()
