#!/usr/bin/env python3
"""Classify pending-upstream CK3-Tiger deltas into actionable root causes."""

from __future__ import annotations

import argparse
import collections
import csv
import re
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delta-csv", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--base-revision", required=True)
    parser.add_argument("--latest-revision", required=True)
    parser.add_argument("--vanilla-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0]) if rows else ["root_id"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def split_values(value: str, separator: str) -> list[str]:
    return [item.strip() for item in value.split(separator) if item.strip()]


def classify(row: dict[str, str]) -> str:
    key = row["key"]
    message = row["message"]
    previews = row["line_previews"]
    paths = row["mod_paths"]
    locations = row["locations"]
    if (
        "history/titles/00_asia_south.txt" in paths
        and key in {"parse-error", "structure", "validation"}
        and any(
            68657 <= int(match.group(1)) <= 68726
            for match in re.finditer(r"00_ASIA_SOUTH\.txt:(\d+)", locations)
        )
    ):
        return "malformed_yi_luomeng_title_history_block"
    if key == "missing-item" and "clan_governmen not defined" in message:
        return "clan_government_field_truncation"
    if key == "missing-item" and re.search(
        r"character YiTribesXie\d+ not defined", message
    ):
        return "missing_yi_tribes_xie_character_chain"
    if key == "history" and re.match(
        r"(?:d_luodian|d_yushi|e_xi_xia|k_sichuan) has no holder", message
    ):
        return "liege_assignment_before_holder_regressions"
    if key == "missing-item" and "character tangut_liang_1 not defined" in message:
        return "removed_tangut_liang_bookmark_character"
    if key == "duplicate-character" and "BalhaeMo" in previews:
        return "balhae_mo_identity_collision"
    if key == "duplicate-character" and "korean_baek_daeheung_" in previews:
        return "korean_baek_daeheung_identity_collision"
    if "BalhaeMon not defined" in message:
        return "balhae_mo_identity_collision"
    if key == "exact-duplicate-item" and "dynasty is redefined" in message:
        return "balhae_mo_identity_collision"
    if "BalhaeAl not defined" in message or "BalhaeAl {" in previews:
        return "balhae_al_dynasty_parse_failure"
    if key == "history" and message.startswith("BalhaeGo"):
        return "balhae_go_identity_replacement_regression"
    if key == "missing-localization" and "localization for name" in message:
        return "new_character_name_localization_gap"
    if key == "missing-file" and "colored_emblems/baijia" in message:
        return "missing_baijia_coa_assets"
    if key == "missing-file" and "colored_emblems/ce_chuhan" in message:
        return "missing_chuhan_coa_assets"
    if key == "missing-file" and "colored_emblems/tamga" in message:
        return "missing_tamga_template_assets"
    if key == "missing-item" and "culture goguryo not defined" in message:
        return "undefined_goguryo_culture"
    if key == "missing-item" and "character korean_gim_silla_73 not defined" in message:
        return "missing_korean_gim_silla_character"
    if key == "missing-item" and re.search(r"dynasty (1000027600|1000060001) not defined", message):
        return "removed_dynasty_definitions_break_existing_characters"
    if key == "missing-item" and "trait poet not defined" in message:
        return "undefined_poet_trait"
    if key == "history" and (
        "history/titles/00_asia_south.txt" in paths
        or "history/characters/00_asia_indosphere.txt" in paths
    ):
        return "indosphere_history_lifetime_regressions"
    if key == "duplicate-item" and "korean_min_hwangryeo" in previews:
        return "duplicate_korean_min_coa_definition"
    if key == "missing-localization" and "dynn_Heo_8A31" in message:
        return "missing_dynasty_localization_template_key"
    if key == "unknown-field" and "adynasty_house" in message:
        return "adynasty_house_field_typo"
    if key == "exact-duplicate-item" and "coat of arms" in message:
        return "duplicate_balhae_ha_coa_definitions"
    return "unclassified_pending_upstream_delta"


ROOT_METADATA = {
    "malformed_yi_luomeng_title_history_block": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "1ffe7d046 içindeki 900.1.1 satırında açılış süslü parantezi eksik; "
            "ardındaki 22 tarih bloğu bu yüzden title seviyesinde ayrıştırılıyor."
        ),
        "candidate": "900.1.1 = satırını 900.1.1 = { olarak düzelt.",
        "manual_reason": "Tek karakterlik kaynak düzeltmesi merge sonrası Tiger ile doğrulanmalı.",
    },
    "clan_government_field_truncation": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "1ffe7d046 içindeki government = clan_governmen değeri komşu history "
            "bloklarında kullanılan clan_government anahtarının son harfini kaybetmiş."
        ),
        "candidate": "clan_governmen değerini clan_government olarak düzelt.",
        "manual_reason": "Exact yazım düzeltmesi merge sonrası Tiger ile doğrulanmalı.",
    },
    "missing_yi_tribes_xie_character_chain": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "1ffe7d046 c_pingyi_china için YiTribesXie1..22 holder zincirini ekliyor, "
            "fakat bu kimliklerin hiçbir character-history tanımı committe, son snapshotta "
            "veya daha eski Git geçmişinde bulunmuyor."
        ),
        "candidate": (
            "Kaynakla doğrulanmış benzersiz YiTribesXie character zinciri sağlanana kadar "
            "22 yeni holder atamasını alma; title'ın merge öncesi history durumunu koru."
        ),
        "manual_reason": "Ad yorumlarından yeni karakter biyografisi uydurmak güvenli değildir.",
    },
    "liege_assignment_before_holder_regressions": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "Yeni county/duchy history satırları d_luodian ve d_yushi için 760'tan, "
            "e_xi_xia için 1038'den, k_sichuan için 1285'ten önce liege bağı kuruyor; "
            "bu üst title'ların o tarihlerde etkin holder'ı yok."
        ),
        "candidate": (
            "Liege geçişlerini ilgili üst title'ın ilk etkin holder tarihine taşı: "
            "d_luodian=760.1.1, d_yushi=760.1.1, e_xi_xia=1038.1.1, k_sichuan=1285.1.1."
        ),
        "manual_reason": "Tarih kaydırmaları merge sonrası etkin history zinciriyle tekrar sınanmalı.",
    },
    "removed_tangut_liang_bookmark_character": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "6ab157f00 tangut_liang_1 karakter bloğunu siliyor; 1066 bookmark history_id, "
            "c_nf_xia_liang holder satırı ve portrait tanımı aynı kimliği kullanmaya devam ediyor."
        ),
        "candidate": (
            "6ab157f00^ snapshotındaki tangut_liang_1 karakter bloğunu koru; bağımlı üç "
            "tüketici birlikte yeni kimliğe taşınmadıkça yalnız karakteri silme."
        ),
        "manual_reason": "Restorasyon sonrası bookmark, landless history ve Tiger birlikte doğrulanmalı.",
    },
    "balhae_mo_identity_collision": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "İlk BalhaeMo zinciri BalhaeMon adlı tanımsız dynasty'yi kullanıyor; "
            "sonraki zincir aynı BalhaeMo1..22 kimliklerini ve BalhaeMo dynasty anahtarını "
            "ikinci kez tanımlıyor. Canlı name-list kaynağında iki ayrı Mo değeri var."
        ),
        "candidate": (
            "İlk zinciri BalhaeMo/dynn_Mo_6155 olarak koru; ikinci zinciri mevcut "
            "Balhae*2 adlandırma örüntüsüne göre BalhaeMo2 ve BalhaeMo2_1..22 yapıp "
            "dynn_Mo_5192 ile bağla. İlk zincirdeki tanımsız BalhaeMon değerlerini "
            "BalhaeMo yap ve bütün ikinci-zincir father referanslarını yeni namespace'e taşı."
        ),
        "manual_reason": "Üç parçalı bundle merge sonrası duplicate/undefined Tiger kontrolüyle doğrulanmalı.",
    },
    "balhae_al_dynasty_parse_failure": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "BalhaeAl dynasty bloğu 'BalhaeAl {' biçiminde; eksik '=' yüzünden blok "
            "yüklenmiyor ve bütün BalhaeAl karakterleri tanımsız dynasty'ye bağlanıyor."
        ),
        "candidate": "BalhaeAl { satırını BalhaeAl = { olarak düzelt.",
        "manual_reason": "Basit sözdizimi adayı olsa da merge sonrası Tiger ile doğrulanmalı.",
    },
    "balhae_go_identity_replacement_regression": {
        "status": "review_before_merge",
        "confidence": "high",
        "evidence": (
            "Title-history atamaları merge tabanında geçerliydi; 140d6d5cd aynı BalhaeGo "
            "kimliklerini daha eski yaşam tarihli yeni karakterlerle değiştirdi ve yedi "
            "holder atamasını yaşam aralığı dışına çıkardı."
        ),
        "candidate": (
            "Merge tabanındaki title-holder karakter kimliklerini koru veya yeni karakter "
            "zincirini benzersiz ID'lere taşı; holder satırlarını yalnız tarihe bakarak kör "
            "biçimde başka karakterlere bağlama."
        ),
        "manual_reason": "Tarih uyumu tek başına tarihsel kimlik eşitliğini kanıtlamaz.",
    },
    "new_character_name_localization_gap": {
        "status": "review_before_merge",
        "confidence": "high",
        "evidence": "Yeni literal character name anahtarlarının exact English localization'ı yok.",
        "candidate": "Eksik exact ad anahtarlarını English localization'a ekle veya mevcut doğru anahtara geçir.",
        "manual_reason": "Yazım ve romanizasyon tercihi kullanıcı incelemesi gerektirir.",
    },
    "missing_baijia_coa_assets": {
        "status": "review_before_merge",
        "confidence": "high",
        "evidence": "Yeni CoA bloklarının başvurduğu baijia DDS dosyaları kaynak katmanlarında bulunamadı.",
        "candidate": "Eksik DDS assetlerini ekle veya CoA texture referanslarını var olan doğru assetlere geçir.",
        "manual_reason": "Doğru görsel eşleşme yalnız dosya adına bakılarak seçilemez.",
    },
    "adynasty_house_field_typo": {
        "status": "review_before_merge",
        "confidence": "high",
        "evidence": "adynasty_house CK3 character-history alanı değil; komşu bloklar dynasty_house kullanıyor.",
        "candidate": "adynasty_house alanını dynasty_house olarak düzelt.",
        "manual_reason": "Tek satırlık güçlü aday; merge sonrası Tiger kontrolü yine zorunlu.",
    },
    "duplicate_balhae_ha_coa_definitions": {
        "status": "quality_review",
        "confidence": "high",
        "evidence": "BalhaeHa ve BalhaeHa2 CoA anahtarlarının birebir aynı ikinci tanımları var.",
        "candidate": "Her anahtar için yalnız bir canonical CoA bloğu bırak.",
        "manual_reason": "Şu an aynı içerik olsa da ileride load-order sapması yaratabilir.",
    },
    "korean_baek_daeheung_identity_collision": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "Merge tabanında canonical korean_baek_daeheung_2 ve _3 blokları zaten var; "
            "son commit bunları yineleyen ve _4.._6 ile uzatan ikinci bir dal ekliyor."
        ),
        "candidate": "Yeni eklenen _2.._6 uzatma dalını ayrı namespace kararı verilene kadar merge etme.",
        "manual_reason": "Bu güvenli exclusion yeni soy içeriğini erteler; kullanıcı kararı gerekir.",
    },
    "undefined_goguryo_culture": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "On bir yeni karakter culture = goguryo kullanıyor; aynı kültür dosyasında etkin "
            "ve tarihsel olarak amaçlanan anahtar goguryeo olarak tanımlı."
        ),
        "candidate": "On bir culture = goguryo değerini culture = goguryeo olarak düzelt.",
        "manual_reason": "Exact typo adayı; merge sonrası undefined-culture Tiger kontrolü zorunlu.",
    },
    "missing_korean_gim_silla_character": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "İki spouse effect'i tanımsız korean_gim_silla_73 kimliğine gidiyor; mevcut 1900372 "
            "bloğu açıkça Gyeongsun Wang ve title history aynı kimliği Kral Gyeongsun olarak kullanıyor."
        ),
        "candidate": "İki korean_gim_silla_73 spouse hedefini 1900372 ile değiştir.",
        "manual_reason": "Exact kimlik remap'i; iki event tarihi yaşam aralığında ve merge sonrası doğrulanmalı.",
    },
    "removed_dynasty_definitions_break_existing_characters": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "1000027600 ve 1000060001 kaldırıldı, fakat iki 00_Z_UNLANDED referansı kaldı; "
            "güncel canonical Khúc dynasty anahtarı viet_d001 ve üç anahtar aynı Khúc localization zincirine bağlı."
        ),
        "candidate": "İki eski numeric dynasty referansını viet_d001 kimliğine taşı.",
        "manual_reason": "Exact kimlik göçü; merge sonrası undefined-dynasty Tiger kontrolü zorunlu.",
    },
    "undefined_poet_trait": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": (
            "Yeni PhamHist4 karakteri trait = poet kullanıyor; mod ve vanilla katmanlarında bu trait yok, "
            "karakterin martial_4, brave ve strategist traitleri ise geçerli."
        ),
        "candidate": "Geçersiz trait = poet satırını merge etme; şair flavor'ı ayrı tasarım işi olarak bırak.",
        "manual_reason": "Güvenli exclusion; merge sonrası undefined-trait Tiger kontrolü zorunlu.",
    },
    "indosphere_history_lifetime_regressions": {
        "status": "block_merge",
        "confidence": "high",
        "evidence": "Yeni Indosphere/Asia South zinciri holder, liege ve spouse atamalarını karakter yaşamı veya liege holder durumu ile uyumsuz tarihlere yerleştiriyor.",
        "candidate": "Her atamayı karakter birth/death ve etkin liege zinciriyle karşılaştırıp tarih veya kimliği kaynak kanıtına göre düzelt.",
        "manual_reason": "Tiger tarih uyumsuzluğunu kanıtlar; doğru kişi veya doğru tarih tarihsel inceleme gerektirir.",
    },
    "missing_chuhan_coa_assets": {
        "status": "review_before_merge",
        "confidence": "high",
        "evidence": "Yeni ce_chuhan/ce_chuhannam/ce_chuhannom CoA texture referanslarının DDS dosyaları snapshot, taban ve vanilla katmanlarında bulunmuyor.",
        "candidate": "Eksik texture paketini ekle veya her CoA'yı mevcut doğru texture'a geçir.",
        "manual_reason": "Doğru hanedan görseli dosya adından güvenle türetilemez.",
    },
    "missing_tamga_template_assets": {
        "status": "review_before_merge",
        "confidence": "high",
        "evidence": "colored_emblem_lists içine eklenen tamga1..23 girdilerinin DDS assetleri kaynak katmanlarında yok.",
        "candidate": "Tamga asset paketini eklemeden template-list girdilerini merge etme.",
        "manual_reason": "Liste girdileri asset paketiyle birlikte ele alınmalıdır.",
    },
    "duplicate_korean_min_coa_definition": {
        "status": "quality_review",
        "confidence": "high",
        "evidence": "korean_min_hwangryeo CoA anahtarı iki farklı blokla yeniden tanımlanıyor.",
        "candidate": "Doğru tek canonical CoA bloğunu seç.",
        "manual_reason": "Bloklar birebir aynı olmadığı için görsel tercih gerekir.",
    },
    "missing_dynasty_localization_template_key": {
        "status": "review_before_merge",
        "confidence": "high",
        "evidence": "Template list dynn_Heo_8A31 anahtarını base-name olarak kullanıyor; English localization yok.",
        "candidate": "Anahtarın gerçekten düzeltilmiş Heo dynasty kimliği olup olmadığını doğrulayıp localization veya doğru mevcut key ile tamamla.",
        "manual_reason": "Satır yorumu bunun alternatif/düzeltme anahtarı olduğunu söylüyor.",
    },
    "unclassified_pending_upstream_delta": {
        "status": "block_merge",
        "confidence": "unknown",
        "evidence": "Yeni Tiger delta satırı bilinen sınıflandırma kurallarına girmedi.",
        "candidate": "Yeni kökü sınıflandırmadan merge etme.",
        "manual_reason": "Sınıflandırıcı kapsamı güncellenmeli.",
    },
}


LOCATION_RE = re.compile(r"^(BookmarksGit/.+):(\d+)$")
NAME_RE = re.compile(r"missing english localization for name (.+)$")
ASSET_RE = re.compile(r"file (gfx/.+\.dds) does not exist")


def git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def blame_commit(repo_root: Path, revision: str, location: str) -> str:
    match = LOCATION_RE.match(location)
    if not match:
        return ""
    path, line = match.groups()
    result = git(
        repo_root,
        "blame",
        "--porcelain",
        "-L",
        f"{line},{line}",
        revision,
        "--",
        path,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        return ""
    commit = result.stdout.splitlines()[0].split()[0]
    return commit if re.fullmatch(r"[0-9a-f]{40}", commit) else ""


def blame_commits(
    repo_root: Path, revision: str, locations: set[str]
) -> dict[str, str]:
    by_path: dict[str, set[int]] = collections.defaultdict(set)
    for location in locations:
        match = LOCATION_RE.match(location)
        if match:
            by_path[match.group(1)].add(int(match.group(2)))

    found: dict[str, str] = {}
    header_re = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)(?: \d+)?$")
    for path, wanted in sorted(by_path.items()):
        ordered = sorted(wanted)
        clusters: list[list[int]] = []
        for line in ordered:
            if not clusters or line - clusters[-1][-1] > 64:
                clusters.append([line])
            else:
                clusters[-1].append(line)
        for cluster in clusters:
            result = git(
                repo_root,
                "blame",
                "--line-porcelain",
                "-L",
                f"{cluster[0]},{cluster[-1]}",
                revision,
                "--",
                path,
                check=False,
            )
            if result.returncode != 0:
                continue
            for raw_line in result.stdout.splitlines():
                match = header_re.match(raw_line)
                if not match:
                    continue
                commit, final_line = match.group(1), int(match.group(2))
                if final_line in wanted:
                    found[f"{path}:{final_line}"] = commit
    return found


def pending_commits(repo_root: Path, base_revision: str, latest_revision: str) -> set[str]:
    result = git(repo_root, "rev-list", f"{base_revision}..{latest_revision}")
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def deletion_commits(
    repo_root: Path,
    base_revision: str,
    latest_revision: str,
    path: str,
    needles: set[str],
) -> set[str]:
    commits: set[str] = set()
    for needle in sorted(needles):
        result = git(
            repo_root,
            "log",
            "-1",
            "--format=%H",
            "-S",
            needle,
            f"{base_revision}..{latest_revision}",
            "--",
            path,
            check=False,
        )
        commit = result.stdout.strip()
        if re.fullmatch(r"[0-9a-f]{40}", commit):
            commits.add(commit)
    return commits


def balhae_go_character_locations(
    repo_root: Path, revision: str, root_rows: list[dict[str, str]]
) -> set[str]:
    ids = {
        match.group(1)
        for row in root_rows
        if (match := re.match(r"^(BalhaeGo\d+) is not alive", row["message"]))
    }
    if not ids:
        return set()
    path = "BookmarksGit/history/characters/00_ASIA_NORTHEAST.txt"
    result = git(repo_root, "show", f"{revision}:{path}", check=False)
    if result.returncode != 0:
        return set()
    return {
        f"{path}:{line_number}"
        for line_number, line in enumerate(result.stdout.splitlines(), start=1)
        if any(line.startswith(f"{character_id} = {{") for character_id in ids)
    }


def tracked_paths(repo_root: Path, revision: str) -> set[str]:
    result = git(repo_root, "ls-tree", "-r", "--name-only", revision)
    return {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}


def collect_vanilla_localization_keys(vanilla_root: Path, wanted: set[str]) -> set[str]:
    found: set[str] = set()
    if not wanted:
        return found
    key_re = re.compile(
        r"^\s*(" + "|".join(re.escape(key) for key in sorted(wanted, key=len, reverse=True))
        + r")\s*:\s*\d*\s+"
    )
    localization_root = vanilla_root / "localization"
    if not localization_root.is_dir():
        return found
    for path in localization_root.rglob("*_l_english.yml"):
        try:
            for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                match = key_re.match(line)
                if match:
                    found.add(match.group(1))
        except OSError:
            continue
        if found == wanted:
            break
    return found


def git_localization_keys(
    repo_root: Path, revision: str, wanted: set[str]
) -> set[str]:
    found: set[str] = set()
    ordered = sorted(wanted)
    for offset in range(0, len(ordered), 40):
        chunk = ordered[offset : offset + 40]
        pattern = (
            r"^[[:space:]]*("
            + "|".join(re.escape(key) for key in chunk)
            + r")[[:space:]]*:[[:space:]]*[0-9]*[[:space:]]+"
        )
        result = git(
            repo_root,
            "grep",
            "-h",
            "-E",
            pattern,
            revision,
            "--",
            "BookmarksGit",
            check=False,
        )
        if result.returncode != 0:
            continue
        for key in chunk:
            if re.search(
                rf"(?m)^\s*{re.escape(key)}\s*:\s*\d*\s+", result.stdout
            ):
                found.add(key)
    return found


def main() -> int:
    args = parse_args()
    rows = read_csv(args.delta_csv)
    introduced = [row for row in rows if row["direction"] == "introduced"]
    resolved = [row for row in rows if row["direction"] == "resolved"]
    grouped: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    assignment_rows: list[dict[str, str]] = []
    for row in introduced:
        root_id = classify(row)
        grouped[root_id].append(row)
        assignment_rows.append({"classified_root_id": root_id, **row})

    pending_commit_set = pending_commits(
        args.repo_root, args.base_revision, args.latest_revision
    )
    base_paths = tracked_paths(args.repo_root, args.base_revision)
    latest_paths = tracked_paths(args.repo_root, args.latest_revision)
    missing_names = {
        match.group(1)
        for row in introduced
        if (match := NAME_RE.search(row["message"]))
    }
    base_name_hits = git_localization_keys(args.repo_root, args.base_revision, missing_names)
    latest_name_hits = git_localization_keys(args.repo_root, args.latest_revision, missing_names)
    vanilla_name_hits = collect_vanilla_localization_keys(args.vanilla_root, missing_names)

    all_locations = {
        location
        for root_rows in grouped.values()
        for row in root_rows
        for location in split_values(row["locations"], "|")
    }
    location_commits = blame_commits(
        args.repo_root, args.latest_revision, all_locations
    )

    output_rows: list[dict[str, str]] = []
    for root_id, root_rows in sorted(grouped.items()):
        metadata = ROOT_METADATA[root_id]
        locations = {
            location
            for row in root_rows
            for location in split_values(row["locations"], "|")
        }
        if root_id == "balhae_go_identity_replacement_regression":
            locations.update(
                balhae_go_character_locations(
                    args.repo_root, args.latest_revision, root_rows
                )
            )
        commits = {
            commit[:10]
            for location in locations
            if (
                commit := location_commits.get(location, "")
                or blame_commit(args.repo_root, args.latest_revision, location)
            )
            and commit in pending_commit_set
        }
        if root_id == "removed_dynasty_definitions_break_existing_characters":
            commits.update(
                commit[:10]
                for commit in deletion_commits(
                    args.repo_root,
                    args.base_revision,
                    args.latest_revision,
                    "BookmarksGit/common/dynasties/00_dynasties.txt",
                    {"1000027600 =", "1000060001 ="},
                )
                if commit in pending_commit_set
            )
        counts = sum(int(row["count"]) for row in root_rows)
        blocker_count = sum(
            int(row["count"])
            for row in root_rows
            if row["recommendation"].startswith("block_merge")
        )
        evidence = metadata["evidence"]
        if root_id in {
            "missing_baijia_coa_assets",
            "missing_chuhan_coa_assets",
            "missing_tamga_template_assets",
        }:
            root_assets = {
                match.group(1)
                for row in root_rows
                if (match := ASSET_RE.search(row["message"]))
            }
            details = []
            for asset in sorted(root_assets):
                tracked = f"bookmarksgit/{asset}".lower()
                details.append(
                    f"{Path(asset).name}:base={'yes' if tracked in base_paths else 'no'},"
                    f"latest={'yes' if tracked in latest_paths else 'no'},"
                    f"vanilla={'yes' if (args.vanilla_root / asset).is_file() else 'no'}"
                )
            evidence += " " + "; ".join(details)
        elif root_id == "new_character_name_localization_gap":
            evidence += (
                " Exact keys: "
                + ", ".join(sorted(missing_names))
                + f". base_hits={len(base_name_hits)}, latest_hits={len(latest_name_hits)}, "
                + f"vanilla_hits={len(vanilla_name_hits)}."
            )
        output_rows.append(
            {
                "root_id": root_id,
                "status": metadata["status"],
                "confidence": metadata["confidence"],
                "introduced_report_count": str(counts),
                "block_merge_report_count": str(blocker_count),
                "tiger_row_count": str(len(root_rows)),
                "affected_paths": ";".join(
                    sorted(
                        {
                            path
                            for row in root_rows
                            for path in split_values(row["mod_paths"], ";")
                        }
                    )
                ),
                "introducing_or_touched_commits_by_blame": ";".join(sorted(commits)),
                "evidence": evidence,
                "candidate_fix": metadata["candidate"],
                "manual_review_reason": metadata["manual_reason"],
                "auto_apply": "no",
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    roots_path = args.output_dir / "upstream_tiger_root_causes.csv"
    write_csv(roots_path, output_rows)
    write_csv(
        args.output_dir / "upstream_tiger_root_assignments.csv",
        assignment_rows,
    )
    introduced_total = sum(int(row["count"]) for row in introduced)
    resolved_total = sum(int(row["count"]) for row in resolved)
    blocking_total = sum(int(row["block_merge_report_count"]) for row in output_rows)
    fallback_total = sum(
        int(row["introduced_report_count"])
        for row in output_rows
        if row["root_id"] == "unclassified_pending_upstream_delta"
    )
    covered_total = sum(int(row["introduced_report_count"]) for row in output_rows)
    if covered_total != introduced_total:
        raise RuntimeError(
            f"Root coverage mismatch: roots={covered_total}, introduced={introduced_total}"
        )

    summary = [
        "# Bekleyen Asıl Mod Tiger Kök Nedenleri",
        "",
        f"- Taban revision: `{args.base_revision}`",
        f"- Son revision: `{args.latest_revision}`",
        f"- Yeni kararlı Tiger raporu: `{introduced_total}`",
        f"- Çözülen kararlı Tiger raporu: `{resolved_total}`",
        f"- Bağımsız yeni kök: `{len(output_rows)}`",
        f"- Merge engelleyici rapor: `{blocking_total}`",
        f"- Sınıflandırılmamış rapor: `{fallback_total}`",
        f"- Merge kararı: `{'do_not_merge_yet' if blocking_total or fallback_total else 'ready_for_merge_review'}`",
        "",
        "## Kökler",
        "",
    ]
    for row in sorted(
        output_rows,
        key=lambda item: (
            item["status"] != "block_merge",
            -int(item["introduced_report_count"]),
            item["root_id"],
        ),
    ):
        summary.extend(
            [
                f"### `{row['root_id']}`",
                "",
                f"- Durum: `{row['status']}`; confidence: `{row['confidence']}`",
                f"- Tiger raporu: `{row['introduced_report_count']}`; merge engeli: `{row['block_merge_report_count']}`",
                f"- Commit kanıtı: `{row['introducing_or_touched_commits_by_blame'] or 'unresolved'}`",
                f"- Kanıt: {row['evidence']}",
                f"- Aday işlem: {row['candidate_fix']}",
                f"- Manuel inceleme nedeni: {row['manual_review_reason']}",
                "",
            ]
        )
    resolved_by_key = collections.Counter()
    for row in resolved:
        resolved_by_key[row["key"]] += int(row["count"])
    summary.extend(["## Çözülen Raporlar", ""])
    summary.extend(
        f"- `{key}`: `{count}`" for key, count in resolved_by_key.most_common()
    )
    blocking_roots = sum(
        row["status"] == "block_merge" for row in output_rows
    )
    summary.extend(
        [
            "## Sonuç",
            "",
            (
                f"Bekleyen asıl mod commitleri henüz merge edilmemelidir. "
                f"Önce `{blocking_roots}` merge-engelleyici kök için çözüm tasarlanmalı, "
                "ardından aynı Tiger binary/config ile Unicode-güvenli temiz Git checkout yeniden taranmalıdır."
            ),
            "Bu rapor hiçbir canlı mod dosyasını değiştirmez ve hiçbir satırı otomatik uygulanabilir saymaz.",
            "",
        ]
    )
    summary_path = args.output_dir / "upstream_premerge_decision_summary.md"
    summary_path.write_text("\n".join(summary), encoding="utf-8")
    print(f"introduced={introduced_total}")
    print(f"resolved={resolved_total}")
    print(f"roots={len(output_rows)}")
    print(f"blocking={blocking_total}")
    print(f"fallback={fallback_total}")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
