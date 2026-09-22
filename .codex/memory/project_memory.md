# CK3 Harita Birlesim Hafizasi

## Calisma Kurali

- Kullanici `su an tartisiyoruz`, `simdi yapma`, `eyleme gecme` gibi bir cerceve cizdiyse otomatik uygulamaya gecilmemeli.
- Bu durumda once sadece anlama teyidi, kural netlestirme ve planlama yapilmali.
- Kullanici 2026-04-11 tarihinde bu planlama konusu icin tekrar yetki verdi ve eylem asamasina gecmeme izin verdi.
- Kullanici `sadece soru` dediginde yalnizca cevap verilmeli, dosya degisikligi yapilmamali.
- `common/landed_titles/00_landed_titles.txt` degisirse ayni degisiklik `test_files/common/landed_titles/00_landed_titles.txt` icine de yansitilmali; kullanici test kopyasindan dosya temin ediyor.
- Kullanici `hafiza.md`nin sismesinden cekinmiyor. Hafiza ne kadar dolu ve bilgi tasiyorsa o kadar iyi.
- Uzun analizler yalnizca gecici baglamda kalmamali; `hafiza.md` disinda ayri analiz dosyalarina da kaydedilmeli.
- Kullanici ayrica her asamada yeni bilgilerin `hafiza.md`ye aktarilmasini istiyor.
- Kullanici bu konuda tekrar tekrar hatirlatmak istemiyor; bundan sonra yeni bir karar, ara sonuc veya netlesmis teknik kural olusunca `hafiza.md` ayrica hatirlatma beklenmeden guncellenmeli.
- Ama kullanici acikca tartisma modunda `simdi yapma` dediyse, `unutma`, `not et`, `hafizaya gecir` gibi ifadeler anlik dosya duzenleme emri degil, sonraki uygun guncellemede kayda gecirilmesi gereken hatirlatma olarak ele alinmali.
- Bir seyin hafizada yazili olup olmadigi soruldugunda yalnizca sohbetteki hatiraya guvenmek yerine dosyanin mevcut durumu kontrol edilerek cevap verilmeli.
- Kisa ve operasyonel hafiza `hafiza.md`de tutulmali.
- Daha uzun ve detayli analizler `analysis/` altinda ayrica saklanmali.

## 2026-04-15 Province ve Title Mapping Pipeline Durumu

- `works/tools/build_province_relation_master.py` eklendi.
- Bu script `Pillow` kullanarak:
  - `works/map_data_sources/provinces_modlu_dogu.png`
  - `map_data/provinces.png`
  uzerinden province bazli iliski cikartiyor.
- Uretilen ana dosya:
  - `works/map_data_sources/province_relation_master.csv`
- Uretilen raporlar:
  - `works/analysis/generated/province_relation_mapping/province_relation_manual_review.csv`
  - `works/analysis/generated/province_relation_mapping/province_relation_split_merge_preview.csv`
  - `works/analysis/generated/province_relation_mapping/province_relation_coverage.csv`
  - `works/analysis/generated/province_relation_mapping/province_relation_summary.md`
- Son province relation ozetleri:
  - `master rows: 4282`
  - `exact mapped rows: 100`
  - `split/merge agirlikli manual review var`
- `works/tools/apply_province_relation_history.ps1` eklendi.
- Bu script sadece `exact + mapped + apply_to_history = yes` province relation satirlarini kullanarak backup moddan province history bloklarini:
  - `history/provinces/00_MB_PROVINCES.txt`
  - `test_files/history/provinces/00_MB_PROVINCES.txt`
  icine tasiyor.
- Province history apply raporlari:
  - `works/analysis/generated/province_relation_mapping/province_relation_history_apply_report.csv`
  - `works/analysis/generated/province_relation_mapping/province_relation_history_apply_summary.md`

## 2026-04-15 e_srivijaya Province Pilot Turu

- `works/tools/build_province_cluster_review.py` eklendi.
- Bu arac:
  - `province_relation_master.csv` satirlarini cluster bazinda filtreliyor
  - current `common/landed_titles/00_landed_titles.txt` icinden hedef province title path bilgisini ekliyor
  - backup source history blogu var mi kontrol ediyor
  - live/test target history blogu var mi kontrol ediyor
  - `promotion_hint` uretip review csv/summary cikariyor
- Ilk pilot:
  - `python works/tools/build_province_cluster_review.py --source-root e_srivijaya --target-root e_srivijaya --cluster-name e_srivijaya_pilot`
- Uretilen ciktilar:
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_srivijaya_pilot.csv`
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_srivijaya_pilot_summary.md`
- Pilot ozeti:
  - `rows: 264`
  - `ready:exact: 2`
  - `review:target_fully_captured: 1`
  - `review:high_overlap: 18`
  - `blocked:no_target_title: 73`
  - `blocked:no_source_history: 26`
- Bu turda tek manuel province terfisi yapildi:
  - `source_province_id 10399 (North Andaman) -> target_province_id 12848 (Diglipur)`
  - eski durum: `classification = split`, `status = manual_review`, `apply_to_history = no`
  - yeni durum: `classification = exact`, `status = mapped`, `apply_to_history = yes`
  - not: `manual: target_fully_captured_and_unique_target`
- Gerekce:
  - `12848` icin tek kaynak aday `10399`
  - `target_coverage = 1.000000`
  - `source_history_exists = yes`
  - hedef province current `e_srivijaya > k_malayadvipa > d_handumans > c_andamans > b_diglipur`
- Sonraki apply sonrasi:
  - `province_relation_history_apply_summary.md`
    - `exact rows requested: 101`
    - `applied rows: 184`
    - `missing source blocks: 27`
  - `10399 -> 12848` hem live hem `test_files` province history dosyasina uygulandi
- Son validator:
  - `validation errors: 0`
  - `validation warnings: 0`
  - `missing playable province titles: 0`
  - `landed_titles live/test hash match: yes`

## 2026-04-16 e_andong Province Pilot Turu

- `works/tools/build_province_cluster_review.py` sikilastirildi.
- Yeni review metrikleri:
  - `target_source_count_all`
  - `target_best_source_id`
  - `target_best_overlap_score`
  - `target_second_best_overlap_score`
  - `target_overlap_gap`
  - `target_is_best_source`
- `promotion_hint` kurallari da guclendirildi:
  - paylasilan hedef ve dusuk `target_coverage` artik `blocked:shared_target_low_coverage`
  - bir hedef icin birincil kaynak olmayan satirlar artik `blocked:not_primary_target_source`
  - boylece yalnizca overlap yuksek diye yanlis pozitif promote adayi cikmiyor
- Pilot komutu:
  - `python works/tools/build_province_cluster_review.py --source-root e_andong --target-root e_andong --cluster-name e_andong_pilot`
- Ciktilar:
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_andong_pilot.csv`
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_andong_pilot_summary.md`
- Pilot ozeti:
  - `rows: 228`
  - `review:manual: 129`
  - `blocked:not_primary_target_source: 60`
  - `blocked:no_source_history: 35`
  - `blocked:shared_target_low_coverage: 4`
- Sonuc:
  - bu ilk `e_andong` turunda guvenli promote edilebilir satir cikmadi
  - yani `province_relation_master.csv` icinde bu turda yeni manuel exact terfi yapilmadi
- Blokaj tipleri:
  - bazi hedefler birden fazla source province tarafindan paylasiliyor ve `target_coverage` dusuk kaliyor
  - bazi satirlarda source history block backup setinde yok
  - bazi satirlar hedefin ikincil/ucuncul kaynagi oldugu icin promote edilemez
- Ornek bloklanan satirlar:
  - `12864 -> 11664` `blocked:shared_target_low_coverage`
  - `14384 -> 11683` `blocked:shared_target_low_coverage`
  - `12456 -> 11758` `blocked:shared_target_low_coverage`
  - `13704 -> 11911` `blocked:shared_target_low_coverage`
- Bu turda validator/apply dongusu yeniden calistirilmadi; cunku data dosyalarina degil yalnizca review aracina degisiklik yapildi ve province master icinde yeni mapping override'u yazilmadi.

## 2026-04-16 Nested Target Title Block Review

- `works/tools/build_province_cluster_review.py` icine `--target-title-block` argumani eklendi.
- Bu filtre current `common/landed_titles/00_landed_titles.txt` icindeki adli title block'u bulup o subtree altindaki tum province id'leri cikartiyor.
- Boylece `source_root`/`target_root` seviyesinin yetmedigi nested yapilar artik review edilebiliyor.
- Eklenen yardimci fonksiyonlar:
  - `extract_named_title_block`
  - `get_province_ids_from_title_block`
- Bu degisiklikten sonra `filter_reason` icine `target_title_block` da yaziliyor.
- Review csv kolonlari ve promotion mantigi korunuyor; ama artik root degil subtree bazli cluster analizi yapilabiliyor.

## 2026-04-16 e_yongliang Subtree Turu

- Ilk root bazli deneme bosta kaldi cunku `e_yongliang` province'leri `target_root = e_yongliang` degil, current landed_titles parser acisindan `h_china` altindaki nested subtree olarak gorunuyor.
- `--target-title-block e_yongliang` ile tekrar review alindi:
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_yongliang_block_probe.csv`
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_yongliang_block_probe_summary.md`
- Ozet:
  - `rows: 130`
  - `ready:exact: 6`
  - `blocked:not_primary_target_source: 44`
  - `blocked:no_source_history: 14`
  - `blocked:shared_target_low_coverage: 11`
- Sonuc:
  - Yeni manuel exact terfi yapilmadi.
  - `ready:exact` satirlar zaten mevcutta `exact/mapped`.
  - Geri kalan adaylar paylasilan hedef, ikincil kaynak veya history eksigi nedeniyle promote edilmedi.
- Ornek blokajlar:
  - `12916 -> 12366` `blocked:not_primary_target_source`
  - `12797 -> 12206` `blocked:shared_target_low_coverage`
  - `12856 -> 12203` `blocked:shared_target_low_coverage`

## 2026-04-16 e_xi_xia Subtree Turu

- Ayni nested filtre mantigi `--target-title-block e_xi_xia` ile uygulandi:
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_xi_xia_block_probe.csv`
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_xi_xia_block_probe_summary.md`
- Ozet:
  - `rows: 5`
  - `ready:exact: 2`
  - `blocked:not_primary_target_source: 2`
  - `blocked:shared_target_low_coverage: 1`
- Sonuc:
  - Yeni manuel exact terfi yapilmadi.
  - Iki `ready:exact` satir zaten mevcutta `exact/mapped`:
    - `9537 -> 9537` `Wuluhai`
    - `9539 -> 9539` `Dengkou`
  - Diğer uc satir guvenli promote eşiğini gecmedi.

## 2026-04-15 Title Relation Master V2

- `works/tools/build_title_relation_master.ps1` yeniden duzenlendi.
- Eski global `mod canonical` mantigi birakildi; yeni schema source/canonical ayrimini ve provenance cluster bilgisini tutuyor.
- Yeni `title_relation_master.csv` kolonlari en az su alanlari iceriyor:
  - `source_title_id`
  - `source_tier`
  - `canonical_title_id`
  - `canonical_tier`
  - `canonical_namespace`
  - `cluster_key`
  - `source_root_title`
  - `source_kingdom`
  - `source_duchy`
  - `source_county`
  - `relation_type`
  - `rewrite_allowed`
  - `status`
  - `notes`
- Candidate discovery sadece province overlap'e degil, name-family ve context ipuclarina da bakacak sekilde guclendirildi.
- `b_xiagui` icin bos kalan mapping problemi bu refactor sirasinda kapatildi:
  - `b_xiagui -> b_xiagui_china`
  - `relation_type = contextual`
  - `canonical_namespace = mod`
- Son title master seed ozeti:
  - `source titles inventoried: 3776`
  - `mapped rows: 3770`
  - `manual review rows: 6`
  - `exact rows: 2246`
  - `contextual rows: 1524`
  - `mod canonical rows: 1536`
  - `vanilla canonical rows: 2234`

## 2026-04-15 Apostrof Içeren Title ID Desteği

- `common/landed_titles/00_landed_titles.txt` icinde `b_ka'abir` gibi apostrof iceren title id'ler var.
- Ilk title parser/validator regex'leri bu title'lari kapsamiyordu.
- Bu nedenle apostrof desteklenmediğinde:
  - bazi title'lar relation inventory'ye girmeyebiliyor
  - statik province-title validator sahte eksik province uretebiliyor
- 2026-04-15 tarihinde su scriptlerde regex'ler apostrof destekleyecek sekilde guncellendi:
  - `works/tools/build_title_relation_master.ps1`
  - `works/tools/build_title_relation_outputs.ps1`
  - `works/tools/validate_east_mapping_pipeline.ps1`
- Ayrica title stem normalization icinde apostrof kaldiriliyor; bu name-family matching'i iyilestiriyor.

## 2026-04-15 Title Output ve Validator Durumu

- `works/tools/build_title_relation_outputs.ps1` yeni schema ile uyumlu hale getirildi.
- Uretilen raporlar:
  - `works/analysis/generated/title_relation_mapping/title_relation_outputs_summary.md`
  - `works/analysis/generated/title_relation_mapping/title_relation_manual_review.csv`
  - `works/analysis/generated/title_relation_mapping/title_relation_reference_hits.csv`
  - `works/analysis/generated/title_relation_mapping/title_relation_rewrite_candidates.csv`
  - `works/analysis/generated/title_relation_mapping/title_relation_coverage.csv`
- Son output ozeti:
  - `safe rewrite rows: 438`
  - `reference hits: 704`
  - `rewrite candidate hits: 2`
  - `apply mode: no`
- Otomatik rewrite bu turda uygulanmadi; sadece rapor uretildi.
- `works/tools/validate_east_mapping_pipeline.ps1` eklendi.
- Bu validator su seyleri statik olarak kontrol ediyor:
  - province relation safety gate
  - province history apply safety gate
  - title inventory/master coverage
  - rewrite candidate safety gate
  - landed_titles brace dengesi
  - `common` ve `test_files` landed_titles hash senkronu
  - duplicate province assignment
  - invalid capital
  - invalid de jure tier zinciri
  - non-land province assignment
  - `definition.csv` bazli missing playable province title
- Son validator ozeti:
  - `landed_titles live/test hash match: yes`
  - `missing playable province titles: 0`
  - `validation errors: 0`
  - `validation warnings: 0`

## 2026-04-15 Manual Review Kapatma Turu

- Title relation master icindeki kalan `6` manuel satir kapatildi.
- Elle verilen canonical kararlar:
  - `d_LIAO_linhuang -> d_xarmoron_china`
  - `d_LIAO_shangjing -> d_changchun_china`
  - `d_LIAO_zhongjing -> d_tohchen_china`
  - `d_yanyun_yuyi -> d_hiyaxu_china`
  - `b_siantan -> b_riau`
  - `b_muot -> b_nakkavaram`
- Bu kararlar `manual:` notuyla yazildi; boylece `build_title_relation_master.ps1` yeniden calistiginda korunuyorlar.
- Ayrica `history/titles/00_ASIA_CHINA.txt` icinde:
  - `set_capital_county = title:c_hangzhou`
  - `set_capital_county = title:c_hangzhou_china`
  olarak duzeltildi.
- `works/tools/build_title_relation_outputs.ps1` icinde quoted string tarama false positive'i azaltildi:
  - scan asamasinda quoted string segmentleri ayiklaniyor
  - bu sayede `name = "b_Wuling"` gibi localization/name stringleri rewrite hit sayilmiyor
- Son yeniden uretim sonrasi:
  - `manual review rows: 0`
  - `rewrite candidate hits: 0`
  - `rewrite candidate rows: 0`
  - validator yine `errors = 0`, `warnings = 0`

## 2026-04-15 Landed Titles Crash Notlari

- `ck3_20260415_005155` crash analizinde en guclu suphe, `Works/tools/restore_missing_landed_title_roots.ps1` icindeki `mapping yoksa barony sil` mantigiydi.
- Bu mantik sonrasi `Province with no county data` zinciri ozellikle `e_xi_xia`, `e_tibet`, `e_yongliang` ve `h_china` cevresinde goruldu.
- 2026-04-15 tarihinde `common/landed_titles/00_landed_titles.txt` ve `test_files/common/landed_titles/00_landed_titles.txt` icinden yuksek supheli top-level root'lar geri alindi:
  - `e_xi_xia`
  - `e_tibet`
  - `e_yongliang`
- Ayni tarihte `Works/tools/restore_missing_landed_title_roots.ps1` guncellendi:
  - artik `missing_mapping_barony_removed` yok
  - onun yerine `missing_mapping_barony_blocked` raporlaniyor
  - eksik province mapping varsa script root restore'u durdurup hata veriyor
- Dogrulama sonucu:
  - iki landed_titles kopyasi yine birebir ayni hash'e sahip
  - brace dengesi iki dosyada da `final_depth=0`
  - restore script calistirildiginda `e_xi_xia` icin `51` eksik mappingte fail ediyor; artik sessizce barony silmiyor

## 2026-04-15 Landed Titles Full Rebuild Karari

- `Works/tools/rebuild_managed_landed_titles_from_sources.ps1` bu turda daha guclu hale getirildi:
  - `SourceBlockName` destegi eklendi
  - `RemoveNestedNames` destegi eklendi
  - `Rename-BlockRootName` fonksiyonu eklendi
  - `manual_barony_override` destegi eklendi
- En kritik karar: `e_xi_xia` artik mod kaynagindan degil, vanilla `02_china.txt` icindeki `k_xia` blogundan uretilecek.
- Buna paralel olarak `h_china` rebuild sirasinda nested `k_xia` blogu cikariliyor; boylece Xi Xia iki kez tanimlanmiyor.
- Ayni turda su zorunlu temizlemeler yapildi:
  - `h_india` icinden `b_kaptai` cikarildi
  - `h_china` icinden `c_maozhou` ve `b_shanglin` cikarildi
  - `e_tibet` icinden `b_jagsam` cikarildi
- `e_tibet` icin kullanilan guvenli province override'lari:
  - `b_muli -> 11454`
  - `b_maowun -> 7115`
  - `b_sumshul -> 12535`
  - `b_wunchoin -> 10322`
- Rebuild 2026-04-15 tarihinde basariyla tamamlandi.
- Son rebuild dogrulamasi:
  - `managed roots rebuilt: 16`
  - `province rows rewritten/re-evaluated: 3716`
  - `duplicate province rows after rebuild: 0`
  - `common/landed_titles/00_landed_titles.txt` ile `test_files/common/landed_titles/00_landed_titles.txt` hash olarak birebir ayni
- Bu turdaki landed_titles duzeltmesi script uzerinden iki kopyaya da yazildi; ancak oyun ici yeni launch/crash testi bu kayittan sonra kullanici tarafinda yapilacak.

## Proje Amaci

- Hedef: mevcut total conversion modunun genel harita mantigini korumak, ama Dogu Asya tarafinda vanilla CK3 projeksiyonuna geri donmek.
- Birlesim mantigi: modun vanilla ile uyumsuz olan dogu kismi vanilla'dan alinacak, geri kalan kisim moddan kalacak.
- Mevcut odak: eldeki `definition_modlu.csv`, `definition_orijinal.csv` ve `provinces_*.png` secim dosyalarini kullanarak gelecekte uretilecek `definition_birlesim.csv` icin saglam bir veri modeli ve plan cikarmak.
- Bu asamada ana hedef dogrudan tum oyun dosyalarini donusturmek degil; once final `definition` tablosunu guvenli sekilde nasil cikaracagimizi netlestirmek.

## Kaynak Dizinler

- Mod klasoru: `F:\Storage\Codding\git\Crusader Kings III\Leviathonlx MoreBookmarks-Plus\BookmarksGit`
- Vanilla oyun klasoru: `C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game`

## Kaynak Rolleri

- Mod tarafi kimlik kaynagi: `map_data/definition_modlu.csv`
- Vanilla tarafi kimlik kaynagi: `map_data/definition_orijinal.csv`
- Mod tam province haritasi: `map_data/provinces_modlu.png`
- Vanilla tam province haritasi: `map_data/provinces_orijinal.png`
- Mod dogu secimi: `map_data/provinces_modlu_dogu.png`
- Mod kalan secimi: `map_data/provinces_modlu_kalan.png`
- Vanilla dogu secimi: `map_data/provinces_orijinal_dogu.png`
- Vanilla kalan secimi: `map_data/provinces_orijinal_kalan.png`
- Nihai secim goruntusu: `map_data/provinces_birlesim.png`

## Isimlendirme Notu

- Genel `provinces.png` ifadesi bu proje icin fazla belirsiz.
- Bundan sonra mumkun oldugunca dosya adlari acikca yazilmali:
  - `provinces_modlu.png`
  - `provinces_orijinal.png`
  - `provinces_modlu_dogu.png`
  - `provinces_modlu_kalan.png`
  - `provinces_orijinal_dogu.png`
  - `provinces_orijinal_kalan.png`
  - `provinces_birlesim.png`

## Temel Teknik Bilgiler

- Mod tam province haritasi boyutu: `9216x4608`
- Vanilla tam province haritasi boyutu: `9216x4608`
- Sonuc: teknik olarak iki harita ayni canvas uzerinde calisabiliyor.

- `definition_modlu.csv` aktif satir sayisi: `14697` (`id 0` dahil)
- `definition_orijinal.csv` aktif satir sayisi: `13270` (`id 0` dahil)

- Mod icinde province ID referanslarinin ana agirligi:
  - `map_data/default.map`
  - `common/landed_titles/00_landed_titles.txt`
  - `history/provinces/00_MB_PROVINCES.txt`
  - bazi `history/titles/*.txt`
  - bazi `map_data/geographical_regions/*.txt`

- `history/provinces` yapisi modda buyuk oranda su dosyada toplu duruyor:
  - `history/provinces/00_MB_PROVINCES.txt`

## Tam Harita Seviyesinde Mod ve Vanilla Cakisma Tabani

- Mod icinde duplicate RGB yok.
- Vanilla icinde duplicate RGB olarak gorunen anlamli tek durum `0,0,0` disi degil; aktif problem gibi ele alinmamali.
- Tam harita karsilastirmasinda mod ve vanilla arasinda:
  - ortak RGB sayisi: `9602`
  - ayni RGB ve ayni ID olanlar: `9473`
  - ayni RGB ama farkli ID olanlar: `129`
  - ortak ID sayisi: `13270`
  - ayni ID ama farkli RGB olanlar: `3797`

## Kullanici Tarafindan Netlestirilen Kural

- `provinces_modlu_kalan.png` ile `provinces_orijinal_dogu.png` arasinda ayni RGB varsa ve `definition_modlu.csv` ile `definition_orijinal.csv` icinde bu RGB ayni province ID'ye gidiyorsa bu hata degildir.
- Yani "ayni RGB" tek basina hata kriteri degil.
- Hata karari icin en azindan RGB ve ID birlikte degerlendirilmeli.

## Format Notu

- Province rengi dogrulugu icin ana oncelik lossless ve pixel-exact davranistir.
- JPG/JPEG kullanilmamali.
- Lossy WebP kullanilmamali.
- `PNG` su an en guvenli calisma formati.
- `DDS` teorik olarak kullanilabilir ama pratikte sikistirma, mipmap, format varyasyonu ve arac farklari nedeniyle analiz girdisi olarak daha riskli.
- Province secimi icin calisma formati olarak `PNG` tercih edilmeli.

## Tarihsel Not: Eski Kirik Girdi

- 2026-04-11 tarihinde ilk verilen `provinces_orijinal_dogu.png` dosyasinda agir renk bozulmasi goruldu.
- O surumde `provinces_orijinal_dogu.png` non-black unique renk sayisi `61589` idi.
- Bu, vanilla tam haritadaki `12750` renkten cok daha yuksekti ve exact province RGB korunumunun bozulduguna isaret ediyordu.
- Bu bulgu artik tarihsel not olarak saklanmali.
- Daha sonra kullanici `provinces_orijinal_dogu.png` dosyasini duzeltti; guncel plan ve analizler sadece duzeltilmis set uzerinden yorumlanmali.

## Guncel PNG Seti Icin Hash Kaydi

- `provinces_modlu.png`: `05A03A6FB339CFA64E57974BCED142180D4CFA52730E64DB9B199F241B652438`
- `provinces_modlu_dogu.png`: `F3ABE180F5E10033A3D295998A0D1E0874CCE6B4BDBF2F3160AAE1B548A438DB`
- `provinces_modlu_kalan.png`: `1AB2562A9109388C734F0B2C199F6E9E6F3CF6CEFF1D4F41EBC96A70E48CD501`
- `provinces_orijinal.png`: `33A2B0D488DE5CB79488E5C8603788D52277DDAB93FB1F3B1FED0FCD75E82CD4`
- `provinces_orijinal_dogu.png`: `F354B7FBFD13B3854837FDB02A5B1958A960BA478D810AC56ED3463BBA166504`
- `provinces_orijinal_kalan.png`: `AC136EE9E2A6621CFB8D7AAEDA2DB5969B6442A7E382513486116EBCBF372714`
- `provinces_birlesim.png`: `514DCA0E95DAF9FA23304604708B90CBE50768C91D2FFADCFAAD2C13EB94102D`

## Guncel PNG Dosya Ozetleri

- `provinces_modlu.png`
  - non-black unique renk: `14155`
  - black piksel: `0`

- `provinces_modlu_dogu.png`
  - non-black unique renk: `4282`
  - black piksel: `28010551`

- `provinces_modlu_kalan.png`
  - non-black unique renk: `9891`
  - black piksel: `14456836`

- `provinces_orijinal.png`
  - non-black unique renk: `12750`
  - black piksel: `0`

- `provinces_orijinal_dogu.png`
  - non-black unique renk: `3391`
  - black piksel: `28010490`

- `provinces_orijinal_kalan.png`
  - non-black unique renk: `9365`
  - black piksel: `14459659`

- `provinces_birlesim.png`
  - non-black unique renk: `13142`
  - black piksel: `0`

## Guncel Renk Butunlugu Kontrolu

- 2026-04-11 tarihli kontrol sonucuna gore mevcut `provinces*.png` setinde anti-alias veya rastgele renk kaymasi bulgusu gorulmedi.
- Kontrol mantigi:
  - `provinces_modlu_dogu.png` icindeki tum non-black renkler `provinces_modlu.png` icinde bulundu
  - `provinces_modlu_kalan.png` icindeki tum non-black renkler `provinces_modlu.png` icinde bulundu
  - `provinces_orijinal_dogu.png` icindeki tum non-black renkler `provinces_orijinal.png` icinde bulundu
  - `provinces_orijinal_kalan.png` icindeki tum non-black renkler `provinces_orijinal.png` icinde bulundu
  - `provinces_birlesim.png` icindeki tum non-black renkler mod veya vanilla tam haritalardan en az birinde bulundu

- Sonuc sayilari:
  - `provinces_modlu_dogu.png`: bilinmeyen non-black renk `0`
  - `provinces_modlu_kalan.png`: bilinmeyen non-black renk `0`
  - `provinces_orijinal_dogu.png`: bilinmeyen non-black renk `0`
  - `provinces_orijinal_kalan.png`: bilinmeyen non-black renk `0`
  - `provinces_birlesim.png`: bilinmeyen non-black renk `0`

- Yorum:
  - Su anki PNG seti, en azindan exact RGB butunlugu acisindan temiz gorunuyor.
  - Bu kontrol renk bozulmasi olmadigini destekliyor.
  - Bu kontrol tek basina split province veya eksik piksel gibi secim mantigi sorunlarini bitirmez; sadece renklerin kaynak haritalardaki gerçek province renklerinden geldigini gosterir.

## Definition ve PNG Uyumlulugu

### Tam Mod Haritasi

- `provinces_modlu.png` icindeki tum non-black renkler `definition_modlu.csv` icinde tanimli.
- Sayilar:
  - PNG non-black unique renk: `14155`
  - definition non-black unique renk: `14696`
  - PNG'de olup definition'da olmayan renk: `0`
  - definition'da olup PNG'de kullanilmayan renk: `541`

- Yorum:
  - `definition_modlu.csv`, `provinces_modlu.png` icin kapsama acisindan uyumlu.
  - Ama definition tarafinda su an haritada kullanilmayan ek satirlar var.

### Tam Vanilla Haritasi

- `provinces_orijinal.png` icindeki tum non-black renkler `definition_orijinal.csv` icinde tanimli.
- Sayilar:
  - PNG non-black unique renk: `12750`
  - definition non-black unique renk: `13268`
  - PNG'de olup definition'da olmayan renk: `0`
  - definition'da olup PNG'de kullanilmayan renk: `518`

- Yorum:
  - `definition_orijinal.csv`, `provinces_orijinal.png` icin kapsama acisindan uyumlu.
  - Vanilla definition tarafinda da haritada kullanilmayan ek satirlar var.

### Secim PNG'leri ve Kendi Definition Kaynaklari

- `provinces_modlu_dogu.png`
  - PNG'de olup `definition_modlu.csv` icinde olmayan renk: `0`
  - `definition_modlu.csv` icinde olup bu secimde kullanilmayan renk: `10414`

- `provinces_modlu_kalan.png`
  - PNG'de olup `definition_modlu.csv` icinde olmayan renk: `0`
  - `definition_modlu.csv` icinde olup bu secimde kullanilmayan renk: `4805`

- `provinces_orijinal_dogu.png`
  - PNG'de olup `definition_orijinal.csv` icinde olmayan renk: `0`
  - `definition_orijinal.csv` icinde olup bu secimde kullanilmayan renk: `9877`

- `provinces_orijinal_kalan.png`
  - PNG'de olup `definition_orijinal.csv` icinde olmayan renk: `0`
  - `definition_orijinal.csv` icinde olup bu secimde kullanilmayan renk: `3903`

- Yorum:
  - Bu beklenen bir durum.
  - Secim PNG'leri definition'in sadece bir alt kumesini kullaniyor.

### Birlesim PNG ve Definition Birligi

- `provinces_birlesim.png` icindeki tum non-black renkler mod veya vanilla definition kaynaklarindan en az birinde tanimli.
- Sayilar:
  - `provinces_birlesim.png` non-black unique renk: `13142`
  - her iki definition'da da bulunmayan renk: `0`
  - sadece mod definition'da bulunan renk: `590`
  - sadece vanilla definition'da bulunan renk: `3094`
  - hem mod hem vanilla definition'da bulunup ayni ID'ye giden renk: `9333`
  - hem mod hem vanilla definition'da bulunup farkli ID'ye giden renk: `125`

- Yorum:
  - Final `provinces_birlesim.png` icin definition seviyesinde kapsama sorunu yok.
  - Esas sorun "eksik tanim" degil, "iki kaynakta farkli anlama gelen ortak renkler" yani collision yonetimi.

## Definition Uyumlulugu Icin Genel Sonuc

- Guncel `definition_modlu.csv` ile `provinces_modlu.png` uyumlu.
- Guncel `definition_orijinal.csv` ile `provinces_orijinal.png` uyumlu.
- Secim PNG'leri kendi kaynak definition'lariyla uyumlu.
- `provinces_birlesim.png` mod+vanilla definition birligiyle uyumlu.
- Bu da su an asagidaki seyi guclu sekilde destekliyor:
  - final `definition_birlesim.csv` uretimi teknik olarak tanim eksigi yuzunden degil
  - esas olarak collision ve ID/RGB politika kararlari yuzunden dikkat gerektiriyor

## Guncel Secim Ozetleri

- `provinces_modlu_dogu.png` secimi, `provinces_modlu.png` icindeki province renkleri acisindan:
  - tam tutulan province rengi: `4250`
  - hic alinmayan province rengi: `9873`
  - parcali kalan province rengi: `32`

- `provinces_modlu_kalan.png` secimi, `provinces_modlu.png` icindeki province renkleri acisindan:
  - tam tutulan province rengi: `9851`
  - hic alinmayan province rengi: `4264`
  - parcali kalan province rengi: `40`

- `provinces_orijinal_dogu.png` secimi, `provinces_orijinal.png` icindeki province renkleri acisindan:
  - tam tutulan province rengi: `3385`
  - hic alinmayan province rengi: `9359`
  - parcali kalan province rengi: `6`

- `provinces_orijinal_kalan.png` secimi, `provinces_orijinal.png` icindeki province renkleri acisindan:
  - tam tutulan province rengi: `9359`
  - hic alinmayan province rengi: `3385`
  - parcali kalan province rengi: `6`

## Dogu ve Kalan Arasindaki Ayni-RGB Sayilari

- Mod tarafinda `provinces_modlu_dogu.png` ile `provinces_modlu_kalan.png` arasinda ortak RGB sayisi: `18`
- Vanilla tarafinda `provinces_orijinal_dogu.png` ile `provinces_orijinal_kalan.png` arasinda ortak RGB sayisi: `6`

## Composite Kontroller

- `provinces_modlu_dogu.png + provinces_modlu_kalan.png -> provinces_modlu.png`
  - non-ambiguous mismatch piksel: `624`
  - overlap same-color piksel: `0`
  - overlap different-color piksel: `0`
  - yorum: modun dogu/kalan ayriminda kucuk miktarda eksik piksel veya bosluk birakilmis gorunuyor

- `provinces_orijinal_dogu.png + provinces_orijinal_kalan.png -> provinces_orijinal.png`
  - non-ambiguous mismatch piksel: `2821`
  - overlap same-color piksel: `0`
  - overlap different-color piksel: `0`
  - yorum: vanilla dogu/kalan ayrimi genel olarak temiz ama tam kusursuz degil; az miktarda bosluk veya eksik piksel var

- `provinces_modlu_kalan.png + provinces_orijinal_dogu.png -> provinces_birlesim.png`
  - non-ambiguous mismatch piksel: `0`
  - overlap same-color piksel: `2`
  - overlap different-color piksel: `0`
  - yorum: mevcut `provinces_birlesim.png`, `provinces_modlu_kalan.png` ile `provinces_orijinal_dogu.png` birlesiminin en guclu referansi gibi gorunuyor

## Guncel Secim Setleri Arasi Paylasilan RGB Ozetleri

- `provinces_modlu_kalan.png` vs `provinces_orijinal_dogu.png`
  - ortak RGB toplam: `140`
  - ayni RGB ve ayni ID: `21`
  - ayni RGB ama farkli ID veya eksik tanim: `119`

- `provinces_modlu_dogu.png` vs `provinces_orijinal_dogu.png`
  - ortak RGB toplam: `161`
  - ayni RGB ve ayni ID: `157`
  - ayni RGB ama farkli ID veya eksik tanim: `4`

- `provinces_modlu_kalan.png` vs `provinces_orijinal_kalan.png`
  - ortak RGB toplam: `9163`
  - ayni RGB ve ayni ID: `9163`
  - ayni RGB ama farkli ID veya eksik tanim: `0`

## Bu Ozetlerden Cikan Ana Yorum

- Mod ve vanilla kalan kisimlari buyuk oranda ortak province tabanini koruyor.
- Dogu tarafinda mod ve vanilla arasinda daha fazla yapisal ayrisma var.
- Final `definition_birlesim.csv` uretiminde esas belirleyici kaynak, tam secimlerin union mantigini gosteren `provinces_birlesim.png` olmali.
- `provinces_modlu_dogu.png` ve `provinces_orijinal_kalan.png` daha cok audit ve capraz kontrol girdisi gibi dusunulmeli.

## Yeni Definition Uretim Mantigi

- Amac `definition_modlu.csv` ve `definition_orijinal.csv` dosyalarini PNG'den sifirdan yeniden cizmek degil.
- Dogru model su:
  - `PNG` dosyalari hangi province'lerin finalde yasadigini ve hangi tarafa ait olduklarini gosterecek
  - `definition_modlu.csv` ve `definition_orijinal.csv` ise bu province'lerin `id/rgb/name` sozlugu olacak
  - bunlardan yeni bir `definition_birlesim.csv` uretilecek

- Kisa formul:
  - `PNG` = secim ve geometri
  - `definition_*.csv` = kimlik sozlugu
  - final hedef = `definition_birlesim.csv`

## Guncellenmis Ara Uretim Fikri

- Kullanici tarafindan kabul edilen yeni ara plan:
  1. `provinces_modlu_kalan.png` icindeki tum yasayan RGB'leri al
  2. bunlari `definition_modlu.csv` icinden ayikla
  3. `definition_modlu_kalan.csv` uret
  4. `provinces_orijinal_dogu.png` icindeki tum yasayan RGB'leri al
  5. bunlari `definition_orijinal.csv` icinden ayikla
  6. `definition_orijinal_dogu.csv` uret
  7. sonra bu iki ara definition dosyasini kuralli bicimde karsilastir
  8. en son `definition_birlesim.csv` uret

- Bu yaklasimda `provinces_birlesim.png`ye dogrudan dokunma veya recolor etme plani yok.
- Bu nedenle final asamada PNG degismeden cozulmesi gereken butun kimlik cakismalari raporlanmali.

## Cakisma Kurallari

- Ayni RGB + ayni ID:
  - benign overlap
  - hata degil

- Ayni RGB + farkli ID:
  - sert cakisma
  - kullaniciya bildirilmeli

- Farkli RGB + ayni ID:
  - ID cakismasi
  - kullaniciya bildirilmeli

- Kullanici notu:
  - bu durumlarin hic olmamasi umuluyor
  - ama olurlarsa mutlaka raporlanmali

## Alt-Kume Definition Dosyalariyla Kontrol Fikri

- Kullanici, `definition_(modlu/orijinal)*isim*.csv` benzeri ara CSV dosyalari olusturarak kontroller yapilmasini uygun goruyor.
- Bu ara dosyalar yalnizca uretim icin degil, audit icin de kullanilabilir.

- Olası audit basliklari:
  - PNG'de olup ilgili definition alt-kumesinde olmayan renkler
  - alt-kume definition icinde olup PNG'de bulunmayan renkler
  - ayni RGB + farkli ID durumlari
  - farkli RGB + ayni ID durumlari
  - ayni province'in iki kaynakta farkli name/comment tasimasi
  - secim sonucu olusan bosluk / split province / parcali secim bulgulari
  - birlesim sonunda yalniz bir tarafta kalan province kimlikleri
  - beklenmeyen placeholder / bos isim / x satirlari

- Kullanici `vb.` derken benzer diger mantikli denetimlerin de dahil edilmesini istiyor.

## Cakisma Siniflari

- Benign overlap:
  - ayni RGB
  - ayni ID
  - kullanici kuralina gore hata degil

- RGB collision:
  - ayni RGB
  - farkli ID
  - final tabloda ayni renk iki farkli province anlamina gelemeyecegi icin cozulmeli

- ID collision:
  - farkli RGB
  - ayni ID
  - final tabloda ayni ID iki farkli province anlamina geliyorsa cozulmeli

- Split province:
  - bir province rengi secim taraflarinda parcali kalmis
  - bu durumda province tek parcali final sahipligine nasil atanacagi netlestirilmeli

- Missing-pixel gap:
  - dogu+kalan ayriminda bazi pikseller hicbir tarafa gitmemis
  - composite mismatch bunun isaretlerinden biri

- Name/comment divergence:
  - ayni RGB ve ayni ID olsa bile `comment/name` alanlari farkli olabilir
  - bu tek basina hata sayilmiyor
  - ama final comment politikasinda karar gerektirebilir

## Gecici ID Politikasi Dusuncesi

- En guvenli ilk dusunce hala su:
  - modda kalan province'ler mod ID'lerini korusun
  - vanilla'dan ithal edilen dogu province'leri sadece guvenliyse mevcut ID'yi korusun
  - conflict varsa yeni ID bloguna tasinsin

- Bunun icin finalde ayri bir esleme tablosu lazim:
  - `old_id`
  - `new_id`
  - `source`

## Gecici RGB Politikasi Dusuncesi

- Cakismayan province mevcut RGB'sini koruyabilir.
- Ayni RGB farkli province anlami tasiyorsa finalde tekil RGB zorunlulugu nedeniyle bunlardan biri recolor edilmeli.
- Bunun icin ayri bir RGB esleme tablosu lazim:
  - `old_rgb`
  - `new_rgb`
  - `source`

## Planlanan Uretim Artefaktlari

- `definition_birlesim.csv`
- `id_mapping.csv`
- `rgb_mapping.csv`
- `conflict_report.csv`
- daha sonra gerekiyorsa:
  - `split_province_report.csv`
  - downstream province referans donusum tablolari

## Uretim Araci

- Tekrarlanabilir subset ve audit uretimi icin script eklendi:
  - `tools/build_definition_subset_audit.ps1`

- Bu script su ciktilari uretir:
  - `map_data/definition_modlu_dogu.csv`
  - `map_data/definition_modlu_kalan.csv`
  - `map_data/definition_orijinal_dogu.csv`
  - `map_data/definition_orijinal_kalan.csv`
  - `analysis/generated/definition_rgb_conflicts.csv`
  - `analysis/generated/definition_id_conflicts.csv`
  - `analysis/generated/definition_shared_same_id.csv`
  - `analysis/generated/definition_quality_flags.csv`
  - `analysis/generated/definition_merge_inventory.csv`
  - `analysis/generated/definition_id_tracking.csv`
  - `analysis/generated/definition_subset_audit.md`
  - `analysis/generated/definition_subset_validation.csv`
  - `analysis/generated/definition_modlu_dogu_rgb_inventory.csv`
  - `analysis/generated/definition_modlu_kalan_rgb_inventory.csv`
  - `analysis/generated/definition_orijinal_dogu_rgb_inventory.csv`
  - `analysis/generated/definition_orijinal_kalan_rgb_inventory.csv`

- Kullanici istegi uzerine yeni guvence:
  - subset olusturulurken PNG'den alinan tum RGB'ler ayri dosyalara tek tek yazilmali
  - boylece hangi renklerin gercekten secildigi sonradan da denetlenebilmeli

## Uretilen Alt-Kume Definition Dosyalari

- `definition_modlu_dogu.csv`
  - image renk sayisi: `4282`
  - cekilen satir sayisi: `4282`
  - definition eksigi: `0`

- `definition_modlu_kalan.csv`
  - image renk sayisi: `9891`
  - cekilen satir sayisi: `9891`
  - definition eksigi: `0`

- `definition_orijinal_dogu.csv`
  - image renk sayisi: `3391`
  - cekilen satir sayisi: `3391`
  - definition eksigi: `0`

- `definition_orijinal_kalan.csv`
  - image renk sayisi: `9365`
  - cekilen satir sayisi: `9365`
  - definition eksigi: `0`

## RGB Inventory Dosyalari

- `analysis/generated/definition_modlu_dogu_rgb_inventory.csv`
  - satir sayisi: `4282`
  - `provinces_modlu_dogu.png` icinden alinan tum non-black RGB'leri tek tek listeler

- `analysis/generated/definition_modlu_kalan_rgb_inventory.csv`
  - satir sayisi: `9891`
  - `provinces_modlu_kalan.png` icinden alinan tum non-black RGB'leri tek tek listeler

- `analysis/generated/definition_orijinal_dogu_rgb_inventory.csv`
  - satir sayisi: `3391`
  - `provinces_orijinal_dogu.png` icinden alinan tum non-black RGB'leri tek tek listeler

- `analysis/generated/definition_orijinal_kalan_rgb_inventory.csv`
  - satir sayisi: `9365`
  - `provinces_orijinal_kalan.png` icinden alinan tum non-black RGB'leri tek tek listeler

- Bu dosyalardaki her satirda en az su bilgiler tutuluyor:
  - subset_name
  - source_label
  - rgb
  - r/g/b
  - present_in_png
  - present_in_definition
  - source_id
  - source_name
  - definition_path
  - image_path

## Subset Validation Tekrari

- `analysis/generated/definition_subset_validation.csv` olusturuldu.
- Bu dosya her subset icin su kontrolu tekrar kaydediyor:
  - image non-black unique renk sayisi
  - cekilen definition satir sayisi
  - rgb inventory satir sayisi
  - missing_colors_in_definition
  - validation_pass

- Sonuc:
  - `modlu_dogu`: `validation_pass = True`
  - `modlu_kalan`: `validation_pass = True`
  - `orijinal_dogu`: `validation_pass = True`
  - `orijinal_kalan`: `validation_pass = True`

- Yorum:
  - tekrar kontrolde her subset icin:
    - PNG'deki secili non-black RGB sayisi
    - cekilen definition satir sayisi
    - yazilan RGB inventory satir sayisi
    birebir ayni cikti
  - ve tanimsiz renk bulunmadi

## Uretilen Audit Sonuclari

- `analysis/generated/definition_shared_same_id.csv`
  - satir sayisi: `21`
  - anlami: ayni RGB + ayni ID

- `analysis/generated/definition_rgb_conflicts.csv`
  - satir sayisi: `119`
  - anlami: ayni RGB + farkli ID
  - kullanici kuralina gore sert cakisma, raporlanmali

- `analysis/generated/definition_id_conflicts.csv`
  - satir sayisi: `634`
  - anlami: farkli RGB + ayni ID
  - kullanici kuralina gore ID cakismasi, raporlanmali

- `analysis/generated/definition_quality_flags.csv`
  - satir sayisi: `188`
  - anlami: bos isim, placeholder, veya name/comment divergence gibi ek kalite uyarilari

- `analysis/generated/definition_merge_inventory.csv`
  - satir sayisi: `13282`
  - kapsam: `9891` modlu_kalan + `3391` orijinal_dogu
  - her satir icin status, partner eslesmeleri ve notlar tutuluyor

- `analysis/generated/definition_id_tracking.csv`
  - satir sayisi: `13282`
  - rol: gelecekte verilecek yeni ID'lerin ana takip tablosu
  - `final_new_id` su an bilerek bos
  - conflict olmayan satirlarda bile ileride bu dosya uzerinden gitmek daha guvenli

## Yeni ID Takibi Icin Kural

- Kullaniciya gore ileride yeni ID atanan modlu ve orijinal province'ler not edilmeli.
- Bunun nedeni, daha sonra province ID iceren oyun dosyalarini duzenlerken hata yapmamak.
- Bu amacla:
  - `analysis/generated/definition_id_tracking.csv` birincil takip tablosu olacak
  - burada su alanlar tutuluyor:
    - kaynak alt-kume
    - kaynak definition
    - source_id
    - source_rgb
    - source_name
    - primary_status
    - final_new_id
    - final_id_status
    - partner conflict bilgileri
    - notlar

- Kural:
  - gelecekte bir province yeni ID alirsa bu once `definition_id_tracking.csv` icine yazilmali
  - daha sonra province referansli oyun dosyalarina gecilmeli

## Bu Asamada Cikan En Onemli Yeni Sonuc

- `definition_birlesim.csv` olusturmadan once mutlaka iki buyuk conflict sinifi ele alinmali:
  - `119` adet RGB conflict
  - `634` adet ID conflict

- Bu da su demek:
  - sorun tanim eksigi degil
  - sorun aktif kimlik cakismasi

## Placeholder Province Tartismasi

- Kullanici yeni bir oneride bulundu:
  - final `definition_birlesim.csv` icinde ID'ler ardışık olmak zorundaysa
  - arada bos kalan ID'ler `place_holder` satirlariyla doldurulabilir
  - ornek mantik:
    - `13999;123;53;87;place_holder;x`
  - daha sonra bu placeholder province'ler `provinces_birlesim.png` icinde haritanin en sag altinda gorunmeyecek teknik bir bolgeye tek tek kucuk pikseller olarak yerlestirilebilir
  - `default.map` icinde bunlar yorumla aciklanmis bir `impassable_mountains` bloguna eklenebilir

- Bu tartismada yeni netlesen nokta:
  - daha once "PNG'ye hic dokunmayalim" itirazi zayifladi
  - cunku kullaniciya gore zaten `provinces_birlesim.png` icinde ayni RGB ile cakisan province'ler yuzunden belirli duzeyde PNG duzenlemesi gerekebilir

- Kullanici itirazlari:
  - placeholder'lari sadece CSV'de tutup PNG'de hic boyamamak cokmeye neden olabilir
  - alt sagdaki teknik bolge oyunda gorunmeyecegi icin oradaki yapay province birikimi pratikte sorun olmayabilir
  - `default.map`e "gereksiz teknik province" sokmus olmayiz; bunun yerine yorumla aciklanan tek bir `impassable_mountains` blogu kullanabiliriz

- Bu tartismadan cikan guncel tutum:
  - placeholder'larin sadece CSV'de tutulmasi artik tek tercih olarak dusunulmemeli
  - placeholder'lari `provinces_birlesim.png` icinde gizli teknik bir bolgede boyama fikri ciddi ve gecerli bir secenek
  - bu teknik placeholder province'ler icin `default.map`te acik yorumlu ayri bir `impassable_mountains` blogu kullanmak makul goruluyor

- Hala acik teknik sorular:
  - CK3 placeholder province'lerin hic boyanmamasina gercekten toleransli mi
  - `1` piksel mi, yoksa biraz daha guvenli bir teknik boyut mu kullanilmali
  - placeholder bolgesinin tam koordinat ve geometri kurali ne olmali
  - bu teknik province'lerin adjacencies, rivers veya baska map sistemleriyle etkilesimi sifir kalir mi

- Ama genel yon su an icin kullanici tarafina dogru kaydi:
  - gerekirse PNG'ye teknik placeholder province'ler eklenebilir
  - bunlar gizli bir alanda tutulur
  - `default.map`te yorumla belgelenir

## Su Anki Cakisma Durumu

- Bu baslik, mevcut son generator calistirmasinin ozet durumudur.

- benign overlap:
  - `21`
  - anlami: ayni RGB + ayni ID
  - bunlar hata degil

- RGB conflict:
  - `119`
  - anlami: ayni RGB + farkli ID
  - bunlar sert cakisma olarak ele alinmali

- ID conflict:
  - `634`
  - anlami: farkli RGB + ayni ID
  - bunlar province referansli dosyalar acisindan ileride kritik risk tasiyor

- quality flags:
  - `188`
  - bos isim, placeholder, veya name/comment divergence gibi ek kalite uyarilari

- manual ID review gereken satir:
  - `1271`
  - kaynak: `definition_id_tracking.csv`
  - not: bu satir bazli sayidir; conflict ciftlerinin her iki tarafi da burada isaretlenebilir

- Validation durumu:
  - `modlu_dogu`: `True`
  - `modlu_kalan`: `True`
  - `orijinal_dogu`: `True`
  - `orijinal_kalan`: `True`

- En onemli yorum:
  - su anki ana problem tanim eksigi degil
  - aktif problem, subsetler arasi kimlik cakismalari

## Kullanici Notlari

- Kullanici `hafiza.md` icinde kendi yazdiklari ile benim ne anladigimin de tutulmasini istiyor.
- Kullanici hafizanin kisa olmasindansa dolu ve bilgili olmasini tercih ediyor.
- Kullanici once tartisma ve plan, sonra uygulama sekliyle ilerlemek istiyor.
- Kullanici, daha sonra verdigi yetkiyle mevcut konu icin eyleme gecilebilecegini acikca belirtti.

## Benim Anladigim

- Bundan sonra kararlar ve ara bulgular daha net sekilde `hafiza.md`ye yazilabilir.
- Uzun teknik analizler ayri dosyalara da yazilmali.
- `definition_birlesim.csv` olusturma sureci, `provinces_birlesim.png` ile iki `definition` sozlugunun kontrollu birlesiminden cikacak.
- Nihai oyun dosyalarina genis capli dokunmadan once `definition` seviyesindeki kimlik ve cakisma modeli netlestirilmeli.

## Son Tartisma Netlesmeleri

- `same RGB + different ID` durumu zaten aktif olarak tartisilan ana teknik problemdir; bu konuda `provinces_birlesim.png` uzerinde kontrollu recolor ihtiyaci olabilecegi kabul edildi.
- Placeholder province fikri su an ciddi ve mesru bir secenek olarak tartisiliyor, ancak bu hala kesin uygulanmis karar degil.
- Placeholder yaklasimi esas olarak `ID` ardissikligi sorununa aday bir cozumdur; `RGB` cakismalarini tek basina cozmez.
- Kullanici 2026-04-11 tarihinde acikca su duzeltmeyi yapti:
  - `634` adet `ID conflict` placeholder ile cozulecek bir konu degil
  - bu conflict'ler icin cozum, gerekli province'lere yeni `final_new_id` vermek ve eski `id/rgb/source` bilgisini tam takip etmektir
  - yani placeholder mantigi ile `ID conflict` cozumu ayni sey degildir
- Gizli teknik bolgede placeholder province boyama ve bunu `default.map` icinde yorumlu bir `impassable_mountains` bloguyla belgeleme fikri olumlu degerlendirildi, ama teknik ayrintilari hala acik.
- Kullanici ayrica sunu netlestirdi:
  - `119` adet `same RGB + different ID` vakasinda, modlu ya da orijinal taraftan hangisi secilecekse o karardan sonra diger tarafa yeni RGB verilecek
  - yani iki province de ayri yasayacaksa, paylasilan eski RGB yalnizca bir tarafta kalacak

## RGB Conflict Karar Asamasi

- Sıradaki fiili uygulama asamasi olarak `119` adet `same RGB + different ID` vakasi icin karar tablosu uretildi.
- Bu is icin script genisletildi:
  - `tools/build_definition_subset_audit.ps1`
- Yeni cikan ana dosya:
  - `analysis/generated/definition_rgb_conflict_decisions.csv`
- Yeni yardimci preview klasoru:
  - `analysis/generated/rgb_conflict_previews/`

- Bu yeni karar dosyasinin mantigi:
  - her satir bir RGB conflict vakasini temsil eder
  - modlu ve orijinal taraftaki eski `id`, `name` ve ilgili piksel kapsami birlikte yazilir
  - karar asamasinda su alanlar daha sonra doldurulabilir:
    - `keep_original_rgb_source`
    - `recolor_source`
    - `new_rgb`
    - `final_modlu_id`
    - `final_orijinal_id`
    - `decision_notes`

- Script bu dosya icin ayrica yardimci uzamsal bilgi de uretir:
  - `modlu_pixel_count`
  - `modlu_bbox`
  - `orijinal_pixel_count`
  - `orijinal_bbox`
  - `modlu_preview_path`
  - `orijinal_preview_path`
- Bu sayede, conflict karari verirken province'in secili alt-kumedeki kapladigi alan ve yaklasik konumu gorulebilir.

- Karar vermeyi hizlandirmak icin mekanik bir oneri katmani da eklendi:
  - `suggest_keep_original_rgb_source`
  - `suggest_recolor_source`
  - `suggestion_reason`
- Bu oneri katmani bir adim daha genisletildi:
  - `suggest_new_rgb`
  - `suggest_new_rgb_reason`
- Bu bir politika karari degil, yalnizca yardimci heuristiktir.
- Su anki heuristic mantigi:
  - daha az piksel kaplayan tarafi recolor etmek daha ucuz olabilir
  - bu yuzden daha kucuk `pixel_count` sahibi taraf `suggest_recolor_source` olarak isaretlenir
  - ayrica, modlu+orijinal definition renk uzayinda bos olan bir `suggest_new_rgb` otomatik onerilir

- Guncel sonuc:
  - `definition_rgb_conflict_decisions.csv` satir sayisi: `119`
  - bu, `definition_rgb_conflicts.csv` icindeki conflict sayisiyla birebir uyumlu
  - `rgb_conflict_previews/` icindeki preview dosya sayisi: `238`
  - heuristic dagilimi:
    - `suggest_recolor_source = modlu`: `105`
    - `suggest_recolor_source = orijinal`: `14`

- Bu onerilere dayanarak yeni bir taslak dosya da uretildi:
  - `analysis/generated/rgb_mapping_draft.csv`
- Bu dosya:
  - `119` satir icerir
  - her satirda hangi tarafin recolor edilmesinin onerildigi
  - etkilenen subset/id/name
  - ilgili preview yolu
  - onerilen yeni RGB
  - ve heuristic gerekcesi yazilir
- Onemli:
  - bu dosya final karar degildir
  - yalnizca review edilebilir taslak mapping katmanidir

## Olusturulan Dosyalar ve Amaclari

- `tools/build_definition_subset_audit.ps1`
  - amac: subset definition dosyalarini ve bunlara bagli audit/rapor dosyalarini tekrar uretmek
  - neden olusturuldu: `provinces_*.png` secimlerinden sistematik ve tekrar calistirilabilir sekilde `definition` alt-kumeleri, conflict raporlari ve takip tablolari cikarmak

- `map_data/definition_modlu_dogu.csv`
  - amac: `provinces_modlu_dogu.png` icindeki yasayan RGB'lerin `definition_modlu.csv` karsiliklarini tutmak
  - neden olusturuldu: mod tarafindaki dogu secimini ayri bir definition alt-kumesi olarak gorebilmek

- `map_data/definition_modlu_kalan.csv`
  - amac: `provinces_modlu_kalan.png` icindeki yasayan RGB'lerin `definition_modlu.csv` karsiliklarini tutmak
  - neden olusturuldu: final birlesimde moddan kalacak province'leri tanim seviyesinde ayiklamak

- `map_data/definition_orijinal_dogu.csv`
  - amac: `provinces_orijinal_dogu.png` icindeki yasayan RGB'lerin `definition_orijinal.csv` karsiliklarini tutmak
  - neden olusturuldu: final birlesimde vanilla/orijinal taraftan alinacak dogu province'lerini tanim seviyesinde ayiklamak

- `map_data/definition_orijinal_kalan.csv`
  - amac: `provinces_orijinal_kalan.png` icindeki yasayan RGB'lerin `definition_orijinal.csv` karsiliklarini tutmak
  - neden olusturuldu: vanilla tarafinin dogu disi referans alt-kumesini de kontrol edebilmek ve secimlerin ic tutarliligini dogrulamak

- `analysis/generated/definition_modlu_dogu_rgb_inventory.csv`
  - amac: `provinces_modlu_dogu.png` icinden secilen tum non-black RGB'leri tek tek kaydetmek
  - neden olusturuldu: PNG'den hangi renklerin gercekten alindigini kalici olarak belgelemek

- `analysis/generated/definition_modlu_kalan_rgb_inventory.csv`
  - amac: `provinces_modlu_kalan.png` icinden secilen tum non-black RGB'leri tek tek kaydetmek
  - neden olusturuldu: moddan kalan kisim icin renk envanterini kaybetmemek ve subset extraction'i tekrar kontrol edebilmek

- `analysis/generated/definition_orijinal_dogu_rgb_inventory.csv`
  - amac: `provinces_orijinal_dogu.png` icinden secilen tum non-black RGB'leri tek tek kaydetmek
  - neden olusturuldu: vanilla dogu seciminin exact RGB setini kalici kayit altina almak

- `analysis/generated/definition_orijinal_kalan_rgb_inventory.csv`
  - amac: `provinces_orijinal_kalan.png` icinden secilen tum non-black RGB'leri tek tek kaydetmek
  - neden olusturuldu: vanilla kalan seciminin exact RGB setini kaydetmek ve tutarlilik kontrolu yapmak

- `analysis/generated/definition_subset_validation.csv`
  - amac: her subset icin PNG renk sayisi, cekilen satir sayisi ve RGB inventory satir sayisini karsilastirmak
  - neden olusturuldu: subset extraction adiminin sayisal olarak tam tutup tutmadigini gostermek

- `analysis/generated/definition_rgb_conflicts.csv`
  - amac: `same RGB + different ID` conflict listesini sade formatta vermek
  - neden olusturuldu: ana RGB cakisma kumesini hizli okumak ve kontrol etmek

- `analysis/generated/definition_rgb_conflict_decisions.csv`
  - amac: `119` RGB conflict icin karar verme ve daha sonra recolor uygulama tablosu olmak
  - neden olusturuldu: hangi tarafin eski RGB'yi koruyacagi, hangi tarafin yeni RGB alacagi ve final ID'lerin nasil baglanacaginin tek dosyada islenebilmesi

- `analysis/generated/rgb_conflict_previews/`
  - amac: her RGB conflict icin modlu ve orijinal tarafin province sekil preview'lerini tutmak
  - neden olusturuldu: `definition_rgb_conflict_decisions.csv` icindeki karar asamasinda tek tek harita aramaya gerek kalmadan ilgili province sekillerini hizli inceleyebilmek

- `analysis/generated/rgb_mapping_draft.csv`
  - amac: heuristic tabanli ilk recolor mapping taslagini vermek
  - neden olusturuldu: `suggest_recolor_source` ve `suggest_new_rgb` bilgilerini uygulamaya yakin, review edilebilir bir csv katmanina donusturmek

## Selective RGB Apply Asamasi

- Draft RGB mapping'in gercekten uygulanabilir olup olmadigini test etmek icin yeni bir script uretildi:
  - `tools/apply_selective_rgb_mapping.ps1`

- Bu scriptin amaci:
  - `rgb_mapping_draft.csv` benzeri bir mapping tablosunu alip
  - `provinces_birlesim.png` uzerinde yalnizca secilen subset tarafini recolor etmek
  - orijinal dosyayi bozmadan once sonuc gorselini ve uygulama raporunu uretmek

- Bu scriptin neden olusturuldugu:
  - `same RGB + different ID` durumlarinin yalnizca CSV mantiginda degil, gercek piksel seviyesinde de cozulup cozulemedigini dogrulamak
  - recolor'un global degil, subset-mask bazli secici sekilde yapildigini kanitlamak

- Bu asamada uretilen ana dosyalar:
  - `analysis/generated/provinces_birlesim_rgb_draft.png`
  - `analysis/generated/rgb_mapping_apply_report.csv`
  - `analysis/generated/rgb_mapping_apply_summary.md`

- Bu dosyalarin rolleri:
  - `provinces_birlesim_rgb_draft.png`
    - amac: draft recolor uygulanmis test cikti haritasi
    - neden olusturuldu: orijinal `provinces_birlesim.png`ye dokunmadan teknik uygulanabilirligi gormek
  - `rgb_mapping_apply_report.csv`
    - amac: her mapping satiri icin kac pikselin hedeflendigi ve gercekten degistirildigini gostermek
    - neden olusturuldu: recolor'un subset bazli dogru uygulandigini satir satir dogrulamak
  - `rgb_mapping_apply_summary.md`
    - amac: selective recolor turunun okunabilir markdown ozeti olmak
    - neden olusturuldu: toplam degisen piksel, mismatch ve tam uygulama sayilarini hizli okumak

- Guncel sonuc:
  - toplam mapping satiri: `119`
  - fully applied satir: `119`
  - total changed pixels: `24443`
  - total base mismatch pixels: `0`

- Bu sonucun anlami:
  - heuristic draft mapping teknik olarak uygulanabildi
  - `provinces_birlesim.png` icinde secici recolor mantigi calisiyor
  - en azindan draft seviyesinde, secilen subset pikselleri hedeflenen yeni RGB'lere kaydirilabildi

## RGB Resolved Candidate Asamasi

- RGB duzeyindeki kararlarin `definition` envanterine de yansitilmasi icin yeni bir script uretildi:
  - `tools/build_rgb_resolved_candidates.ps1`

- Bu scriptin amaci:
  - `definition_merge_inventory.csv` uzerindeki satirlara `effective_rgb` mantigi islemek
  - recolor edilen province'leri ve eski RGB'yi koruyan taraflari tek bir ara tabloda gostermek
  - `benign_shared` ciftlerini final ID asamasindan once tek candidate satira indirmek

- Bu scriptin neden olusturuldugu:
  - RGB problemi cozuldukten sonra, siradaki buyuk asama olan ID atamasi icin `definition` tarafinda daha temiz ve yararli bir temel tabloya ihtiyac vardi

- Bu asamada uretilen dosyalar:
  - `analysis/generated/definition_rgb_resolved_inventory.csv`
  - `analysis/generated/definition_rgb_resolved_candidates_pre_id.csv`
  - `analysis/generated/definition_rgb_resolved_summary.md`

- Bu dosyalarin rolleri:
  - `definition_rgb_resolved_inventory.csv`
    - amac: tum merge satirlarini koruyup her satir icin `effective_rgb` degerini gostermek
    - neden olusturuldu: recolor edilen ve eski RGB'yi koruyan satirlari tek inventory katmaninda toplamak
  - `definition_rgb_resolved_candidates_pre_id.csv`
    - amac: `benign_shared` tekrarlarini merge edip final ID oncesi candidate satir listesi cikarmak
    - neden olusturuldu: ID atama asamasina daha yakin, daha temiz bir candidate tablosu elde etmek
  - `definition_rgb_resolved_summary.md`
    - amac: resolved inventory ve pre-ID candidate asamasinin ozetini vermek
    - neden olusturuldu: recolor sonrasi satir sayilarini ve merge etkisini hizli okumak

- Guncel sonuc:
  - resolved inventory row count: `13282`
  - pre-ID candidate row count: `13261`
  - recolored rows: `119`
  - keep-original-shared-rgb rows: `119`
  - benign-shared rows in inventory: `42`
  - benign-shared merged candidates: `21`

- Bu sonucun anlami:
  - RGB tarafindaki kararlar `definition` tarafina basariyla tasindi
  - `benign_shared` tekrarlar final ID asamasi icin tek candidate'a indirildi
  - bundan sonraki ana problem artik agirlikli olarak ID stratejisi

## Pre-ID Strategy Analizi

- RGB-resolved candidate seti icin mevcut ID manzarasini sayisallastirmak amaciyla yeni bir script uretildi:
  - `tools/analyze_pre_id_strategy.ps1`

- Bu scriptin amaci:
  - mevcut candidate satirlarin eski ID dagilimini cikarmak
  - duplicate ID gruplarini bulmak
  - bos ID araliklarini cikarip placeholder yukunu sayisallastirmak

- Bu scriptin neden olusturuldugu:
  - "eski ID'leri ne kadar koruyabiliriz" sorusunu sezgisel degil, sayisal veriyle tartisabilmek

- Bu asamada uretilen dosyalar:
  - `analysis/generated/current_id_candidate_inventory.csv`
  - `analysis/generated/id_duplicates_pre_id.csv`
  - `analysis/generated/id_gap_ranges_pre_id.csv`
  - `analysis/generated/id_strategy_pre_id_summary.md`

- Bu dosyalarin rolleri:
  - `current_id_candidate_inventory.csv`
    - amac: her pre-ID candidate satir icin mevcut/kanonik eski ID'yi gosterir envanter olmak
    - neden olusturuldu: duplicate ve gap analizinin ana girdisini kalici kaydetmek
  - `id_duplicates_pre_id.csv`
    - amac: ayni mevcut ID'yi paylasan candidate satirlari listelemek
    - neden olusturuldu: yeni `final_new_id` gerektiren duplicate kimlikleri topluca gormek
  - `id_gap_ranges_pre_id.csv`
    - amac: `1..max current ID` araligindaki bos ID araliklarini range bazli kaydetmek
    - neden olusturuldu: placeholder veya contiguous strateji maliyetini olcmek
  - `id_strategy_pre_id_summary.md`
    - amac: duplicate/gap analizinin markdown ozeti olmak
    - neden olusturuldu: hangi ID stratejisinin daha az maliyetli oldugunu hizli tartisabilmek

- Guncel sonuc:
  - candidate row count: `13261`
  - unique current ID count: `12627`
  - max current ID: `14696`
  - duplicate current ID groups: `634`
  - duplicate current ID rows: `1268`
  - one row per duplicate group eski ID'yi korursa yeni ID ihtiyaci: `634`
  - missing ID count from `1..14696`: `2069`
  - gap range count: `135`
  - eger tum unique eski ID'leri koruyup arayi contiguous yapmak istersek placeholder ihtiyaci: `2069`

- Bu sonucun anlami:
  - ID problemi artik sayisal olarak cok daha net
  - duplicate yuzunden en az `634` yeni ID gerekecek
  - eski unique ID'leri topluca koruma denemesi ise `2069` placeholder yukune yol acacak

## ID Policy Draft Asamasi

- ID tarafi icin iki somut draft politika uretildi:
  - `old-id-heavy / preserve_old_ids`
  - `full_renumber`

- Bu is icin yeni bir script uretildi:
  - `tools/build_id_policy_drafts.ps1`

- Bu scriptin amaci:
  - ayni pre-ID candidate setinden iki farkli final ID atama taslagi cikarmak
  - her politika icin source bazli `old_id -> final_new_id` map dosyalari uretmek
  - placeholder yukunu ve ID degisim yukunu sayisal olarak karsilastirmak

- Bu scriptin neden olusturuldugu:
  - "hangi ID stratejisi daha az aci verir" sorusunu sezgiyle degil, dogrudan draft ciktılarla tartisabilmek

- Bu asamada uretilen dosyalar:
  - `analysis/generated/id_policy_preserve_old_assignments.csv`
  - `analysis/generated/id_policy_preserve_old_placeholders.csv`
  - `analysis/generated/id_map_modlu_preserve_old.csv`
  - `analysis/generated/id_map_orijinal_preserve_old.csv`
  - `analysis/generated/id_policy_full_renumber_assignments.csv`
  - `analysis/generated/id_map_modlu_full_renumber.csv`
  - `analysis/generated/id_map_orijinal_full_renumber.csv`
  - `analysis/generated/id_policy_source_burden.csv`
  - `analysis/generated/id_policy_drafts_summary.md`

- Bu dosyalarin rolleri:
  - `id_policy_preserve_old_assignments.csv`
    - amac: old-id-heavy draft politikadaki gercek province satirlarinin final ID atamalarini vermek
    - neden olusturuldu: mumkun oldugunca eski ID koruyan draft'i somutlastirmak
  - `id_policy_preserve_old_placeholders.csv`
    - amac: old-id-heavy draft'te contiguous kalmak icin gereken placeholder satirlarini vermek
    - neden olusturuldu: placeholder yukunu soyut degil, satir seviyesinde gormek
  - `id_map_modlu_preserve_old.csv`
    - amac: modlu satirlar icin old-id-heavy draft `old_id -> final_new_id` map'i olmak
    - neden olusturuldu: daha sonra mod tarafindaki province referansli dosyalari guncellerken kullanmak
  - `id_map_orijinal_preserve_old.csv`
    - amac: orijinal satirlar icin old-id-heavy draft `old_id -> final_new_id` map'i olmak
    - neden olusturuldu: vanilla/orijinal import edilen province referanslarini daha sonra guncellerken kullanmak
  - `id_policy_full_renumber_assignments.csv`
    - amac: full renumber draft'inde tum gercek province satirlarin final ID atamalarini vermek
    - neden olusturuldu: placeholder'siz alternatif stratejiyi somutlastirmak
  - `id_map_modlu_full_renumber.csv`
    - amac: modlu satirlar icin full renumber draft `old_id -> final_new_id` map'i olmak
    - neden olusturuldu: modlu referanslari genis capli yeniden numaralandirmada takip etmek
  - `id_map_orijinal_full_renumber.csv`
    - amac: orijinal satirlar icin full renumber draft `old_id -> final_new_id` map'i olmak
    - neden olusturuldu: orijinal referanslari genis capli yeniden numaralandirmada takip etmek
  - `id_policy_source_burden.csv`
    - amac: her politika altinda source bazli ne kadar satirin eski ID'yi korudugunu veya degistirdigini gostermek
    - neden olusturuldu: degisim yukunun modlu mu, orijinal mi tarafina bindigini sayisal gormek
  - `id_policy_drafts_summary.md`
    - amac: iki draft politikanin ozet karsilastirmasini markdown olarak vermek
    - neden olusturuldu: draft sonuclarini hizli okumak ve tartismak

- Guncel sonuc:
  - `preserve_old_ids`
    - current ID'yi koruyan candidate satir: `12627`
    - yeni ID alan candidate satir: `634`
    - mevcut gap'lere yerlestirilen duplicate satir: `634`
    - max old ID ustune append ihtiyaci: `0`
    - placeholder ihtiyaci: `1435`
    - final max ID: `14696`
    - degisen `modlu_kalan` satir: `0`
    - degisen `orijinal_dogu` satir: `634`
  - `full_renumber`
    - current ID'yi tesadufen koruyan satir: `615`
    - ID'si degisen satir: `12646`
    - placeholder ihtiyaci: `0`
    - final max ID: `13261`
    - degisen `modlu_kalan` satir: `9508`
    - degisen `orijinal_dogu` satir: `3138`

- Bu sonucun anlami:
  - `preserve_old_ids` draft'i degisim yukunu neredeyse tamamen `orijinal_dogu` tarafina iter
  - `full_renumber` draft'i ise her iki tarafa da buyuk bir yeniden numaralandirma yukler
  - temel tradeoff artik cok net:
    - az ID degisikligi + cok placeholder
    - sifir placeholder + cok fazla ID degisikligi

## Definition Policy Draft Asamasi

- ID draft'lerinden gercek `definition.csv` taslaklari da uretildi.
- Bu is icin yeni bir script uretildi:
  - `tools/build_definition_csv_drafts.ps1`

- Bu scriptin amaci:
  - draft ID assignment ciktılarini CK3 `definition.csv` bicimine donusturmek
  - contiguity ve duplicate RGB gibi temel teknik kontrolleri otomatik yapmak

- Bu scriptin neden olusturuldugu:
  - tartisilan ID politikalarinin gercek `definition.csv` ciktilarina donustugunde teknik olarak gecerli olup olmadigini aninda gorebilmek

- Bu asamada uretilen dosyalar:
  - `analysis/generated/definition_policy_preserve_old_draft.csv`
  - `analysis/generated/definition_policy_full_renumber_draft.csv`
  - `analysis/generated/definition_policy_draft_validation.csv`
  - `analysis/generated/definition_policy_drafts_summary.md`

- Bu dosyalarin rolleri:
  - `definition_policy_preserve_old_draft.csv`
    - amac: old-id-heavy draft'ten uretilmis gercek `definition.csv` taslagi olmak
    - neden olusturuldu: placeholder'li stratejinin teknik gecerliligini gormek
  - `definition_policy_full_renumber_draft.csv`
    - amac: full renumber draft'ten uretilmis gercek `definition.csv` taslagi olmak
    - neden olusturuldu: placeholder'siz stratejinin teknik gecerliligini gormek
  - `definition_policy_draft_validation.csv`
    - amac: her iki draft'in row count, max id, placeholder count, duplicate RGB ve contiguous ID durumunu topluca gostermek
    - neden olusturuldu: hangi draft'in teknik olarak saglam oldugunu hizli kontrol etmek
  - `definition_policy_drafts_summary.md`
    - amac: definition draft sonuclarinin markdown ozeti olmak
    - neden olusturuldu: iki policy `definition` ciktilarini karsilastirmayi kolaylastirmak

- Guncel validation sonucu:
  - `preserve_old_ids` draft:
    - data rows: `14696`
    - placeholders: `1435`
    - duplicate RGB: `0`
    - missing IDs: `0`
    - contiguous: `True`
  - `full_renumber` draft:
    - data rows: `13261`
    - placeholders: `0`
    - duplicate RGB: `0`
    - missing IDs: `0`
    - contiguous: `True`

- Bu sonucun anlami:
  - her iki draft da teknik olarak gecerli `definition.csv` taslagi uretiyor
  - yani bu noktadan sonra tartisma "calisir mi" degil, daha cok "hangi bakim stratejisi daha az maliyetli" sorusuna donmus durumda

- `analysis/generated/definition_id_conflicts.csv`
  - amac: `different RGB + same ID` conflict listesini vermek
  - neden olusturuldu: yeni `final_new_id` gerektiren kimlik cakismalarini belirlemek

- `analysis/generated/definition_shared_same_id.csv`
  - amac: `same RGB + same ID` olan benign overlap vakalarini gostermek
  - neden olusturuldu: hata olmayan paylasimlari conflict'lerden ayirmak

- `analysis/generated/definition_quality_flags.csv`
  - amac: bos isim, placeholder benzeri isim ve name/comment divergence gibi kalite uyarilarini toplamak
  - neden olusturuldu: final merge oncesi veri temizligi gereken satirlari ayri gormek

- `analysis/generated/definition_merge_inventory.csv`
  - amac: modlu_kalan + orijinal_dogu icindeki tum satirlari ortak bir envanter tablosunda gostermek
  - neden olusturuldu: her satirin source, partner conflict durumu ve merge statulerini tek yerde toplamak

- `analysis/generated/definition_id_tracking.csv`
  - amac: gelecekte yeni final ID atanacak satirlarin birincil takip tablosu olmak
  - neden olusturuldu: eski `source_id`, `source_rgb`, `source_name`, `source_subset` ve gelecekteki `final_new_id` iliskisini kaybetmemek

- `analysis/generated/definition_subset_audit.md`
  - amac: tum subset extraction ve audit ciktisinin okunabilir markdown ozeti olmak
  - neden olusturuldu: sayisal sonuclari ve ana rapor dosyalarini tek yerde hizli okumak

## Ayri Analiz Dosyasi

- Daha uzun ve fazlandirilmis teknik notlar icin bak:
  - `analysis/definition_birlesim_plan.md`

## Repo Impact Asamasi

- Iki ID politikasinin mevcut mod reposu uzerinde ne kadar downstream dosya duzenleme yuku getirecegini sayisal gormek icin yeni bir script yazildi:
  - `tools/build_id_policy_repo_impact.ps1`

- Bu scriptin amaci:
  - mevcut repo icindeki aktif province ID referanslarini taramak
  - `preserve_old_ids` ve `full_renumber` altinda hangi referanslarin degisecegini saymak
  - karar verirken sadece `definition.csv` gecerliligine degil, gercek duzenleme maliyetine de bakmak

- Bu scriptin neden olusturuldugu:
  - iki ID politikasinin teknik olarak calistigi zaten gorulmustu
  - ama asil stratejik soru, repo genelinde hangi politikanin daha az kirilim ve daha az toplu refactor gerektirdigiydi

- Script once iki kez hata verdi ve duzeltildi:
  - `Sort-Object` coklu property yazimi parser hatasi veriyordu; hashtable-property siralamaya cevrildi
  - tek satirli dosyalarda `Get-Content` string dondurdugu icin `.Count` hatasi aliyordu; tum line okumalar `@(...)` ile diziye zorlandi

- Bu asamada uretilen dosyalar:
  - `analysis/generated/id_policy_repo_impact_by_context.csv`
  - `analysis/generated/id_policy_repo_impact_by_file.csv`
  - `analysis/generated/id_policy_repo_impact_summary.md`

- Bu dosyalarin rolleri:
  - `id_policy_repo_impact_by_context.csv`
    - amac: referans tipine gore (landed_titles, history/provinces, adjacencies, default.map vb.) iki ID politikasinin kac satiri etkileyecegini gostermek
    - neden olusturuldu: degisim yukunun hangi sistemlerde yogunlastigini gormek
  - `id_policy_repo_impact_by_file.csv`
    - amac: dosya bazinda hangi dosyalarin ne kadar etkilenecegini gostermek
    - neden olusturuldu: daha sonra gercek edit asamasinda en pahali dosyalari onceden bilmek
  - `id_policy_repo_impact_summary.md`
    - amac: repo etki sonucunun hizli okunabilir markdown ozeti olmak
    - neden olusturuldu: politikalar arasi bakim maliyet farkini tek bakista gormek

- Bu scriptin taradigi aktif referans baglamlari:
  - `history/provinces` icindeki province block header ID'leri
  - `history/province_mapping` icindeki sol ve sag numeric mapping satirlari
  - `common/landed_titles` icindeki aktif `province = <id>` satirlari
  - `common/situation` icindeki aktif `capital_province = <id>` satirlari
  - `history/titles` icindeki aktif `capital = <id>` satirlari
  - `map_data/adjacencies.csv`
  - `map_data/default.map` icindeki aktif `LIST {}` ve `RANGE {}` province ID satirlari
  - `map_data/island_region.txt`, `map_data/geographical_regions/*.txt`, `common/connection_arrows/*.txt` icindeki aktif `provinces = {}` bloklari

- Cok onemli yorum:
  - bu repo impact taramasi mevcut mod reposundaki aktif province referanslari icin yapildi
  - yani esasen mod tarafinin bugunku ID uzayina dokunma maliyetini olcer
  - vanilla/orijinalden ithal edilecek dogu province'lerinin henuz repo icine tasinmamis gelecekteki referanslari bu raporda dogal olarak yoktur

- Guncel sonuc:
  - `preserve_old_ids`
    - changed references: `0`
    - touched lines: `0`
  - `full_renumber`
    - changed references: `19499`
    - touched lines: `18206`

- Bu sonucun anlami:
  - mevcut repo mod ID uzayini kullandigi icin `preserve_old_ids` secenegi bugunku dosyalarin neredeyse tamamini oldugu gibi birakiyor
  - `full_renumber` ise mevcut mod tarafinda cok buyuk bir toplu duzenleme dalgasi gerektiriyor
  - bu nedenle repo bakim maliyeti acisindan su anki en guclu aday politika `preserve_old_ids`

- Full renumber altinda en cok etkilenen context'ler:
  - `common_landed_titles_province`: `8327` touched line
  - `history_provinces_block_header`: `7897` touched line
  - `common_connection_arrows_provinces_block`: `486` touched line
  - `history_province_mapping_right`: `360` touched line
  - `history_province_mapping_left`: `360` touched line
  - `adjacencies_through`: `202` touched line
  - `adjacencies_to`: `180` touched line
  - `adjacencies_from`: `180` touched line

- Full renumber altinda en cok etkilenen dosyalar:
  - `common/landed_titles/00_landed_titles.txt`: `8327` touched line
  - `history/provinces/00_MB_PROVINCES.txt`: `7897` touched line
  - `history/province_mapping/00_guinea.txt`: `600` touched line
  - `map_data/adjacencies.csv`: `562` touched line
  - `common/connection_arrows/silk_road_arrows.txt`: `486` touched line
  - `map_data/default.map`: `170` touched line

- Bu asamadan cikan pratik sonuc:
  - teknik gecerlilik acisindan iki draft da olur
  - ama mevcut repo uzerinde uygulanabilirlik ve emek maliyeti acisindan `preserve_old_ids` cok daha avantajli gorunuyor
  - sonraki ana asama buyuk ihtimalle `preserve_old_ids` politikasini ana yol kabul edip final tracking/master tabloyu ona gore kurmak olmali

## Final Master Tracking Asamasi

- Repo impact sonucundan sonra `preserve_old_ids` pratik ana politika adayi olarak one ciktigi icin, bu politika etrafinda tek merkezli bir final tracking/master tablo katmani kuruldu.

- Bu is icin yeni bir script yazildi:
  - `tools/build_policy_master_tracking.ps1`

- Bu scriptin amaci:
  - secilen ID policy assignment ciktisini tek bir final master tabloya donusturmek
  - `modlu` ve `orijinal` kaynaklar icin ayri source-tracking csv'leri uretmek
  - eski `id/rgb/name/source` ile final `new_id/rgb/name` baglantisini kayipsiz tutmak
  - placeholder satirlarini da ayri bir inventory olarak cikarmak

- Bu scriptin neden olusturuldugu:
  - ileride province referansli oyun dosyalari duzenlenirken tek tek farkli ara csv'lere bakmak yerine, final gercegi tek bir master tablo ve source-map katmaninda toplamak gerekiyordu
  - kullanicinin ozellikle istedigi `old id`, `old rgb`, `source` bilgisini kalici ve sorgulanabilir tutmak gerekiyordu

- Bu script gelistirilirken bir kritik eksik yakalandi:
  - ilk surum sadece `id_policy_preserve_old_assignments.csv` girisini okuyordu
  - fakat `preserve_old_ids` politikasindaki placeholder satirlari ayri dosyada tutuluyordu: `id_policy_preserve_old_placeholders.csv`
  - bu nedenle ilk ozet yanlis olarak `13261` master row ve `0` placeholder gosterdi
  - script duzeltildi ve placeholder input'u da dahil edilerek tekrar calistirildi
  - dogru toplam artik:
    - master rows: `14696`
    - placeholder rows: `1435`

- Bu asamada uretilen dosyalar:
  - `analysis/generated/final_master_preserve_old_ids.csv`
  - `analysis/generated/final_modlu_tracking_preserve_old_ids.csv`
  - `analysis/generated/final_orijinal_tracking_preserve_old_ids.csv`
  - `analysis/generated/final_placeholder_inventory_preserve_old_ids.csv`
  - `analysis/generated/final_tracking_summary_preserve_old_ids.md`

- Bu dosyalarin rolleri:
  - `final_master_preserve_old_ids.csv`
    - amac: `preserve_old_ids` politikasindaki tum final satirlari tek tabloda toplamak
    - neden olusturuldu: final province gercegini `final_new_id` bazinda tek yerden izlemek
  - `final_modlu_tracking_preserve_old_ids.csv`
    - amac: modlu kaynakli province'ler icin `old_id -> final_new_id` ve `old_rgb -> final_rgb` takibini vermek
    - neden olusturuldu: mevcut mod referansli dosyalari guncellerken mod tarafinin kaydini kaybetmemek
  - `final_orijinal_tracking_preserve_old_ids.csv`
    - amac: orijinal/dogu kaynakli province'ler icin `old_id -> final_new_id` ve `old_rgb -> final_rgb` takibini vermek
    - neden olusturuldu: vanilla dogudan ithal edilen province'lerin yeni kimligini ve varsa recolor/renumber durumunu kalici kayit altina almak
  - `final_placeholder_inventory_preserve_old_ids.csv`
    - amac: `preserve_old_ids` altinda araya giren tum placeholder satirlarini listelemek
    - neden olusturuldu: ardissiklik icin olusan teknik satirlari ileride map/default.map tasarimiyla baglayabilmek
  - `final_tracking_summary_preserve_old_ids.md`
    - amac: final master tracking katmaninin okunabilir markdown ozeti olmak
    - neden olusturuldu: sayisal dagilimi ve degisim yukunu hizli okumak

- Guncel final tracking sonucu (`preserve_old_ids`):
  - master rows: `14696`
  - real candidate rows: `13261`
  - placeholder rows: `1435`
  - modlu tracking rows: `9891`
  - orijinal tracking rows: `3391`
  - modlu rows with changed final ID: `0`
  - orijinal rows with changed final ID: `634`
  - modlu rows with changed final RGB: `105`
  - orijinal rows with changed final RGB: `14`

- Real row source split:
  - `both`: `21`
  - `modlu`: `9870`
  - `orijinal`: `3370`

- Real row primary status split:
  - `benign_shared`: `21`
  - `id_conflict`: `1033`
  - `mod_only`: `9234`
  - `orijinal_only`: `2735`
  - `rgb_conflict`: `238`

- Bu sonucun anlami:
  - artik `preserve_old_ids` politikasinda hangi eski province'in finalde nereye gittigi tek merkezli olarak takip edilebiliyor
  - mod tarafinda ID degisikligi yok, yani mevcut mod dosyalari icin buyuk avantaj korunuyor
  - orijinal/dogu tarafinda `634` satir yeni final ID alacak
  - RGB recolor yukunun buyuk kismi mod tarafina (`105`) bindigi icin `provinces_birlesim.png` final uygulama asamasinda bu mapping'ler dikkatle kullanilmali

- Bu asamadan sonraki mantikli adim:
  - `preserve_old_ids` master tabloyu baz alip gercek uygulama sirasini tanimlamak
  - yani:
    - final `provinces_birlesim.png` RGB uygulamasi
    - final `definition_birlesim.csv`
    - sonra province referansli oyun dosyalari icin kontrollu update pipeline'i

## Final Preserve-Old Staging Asamasi

- Kullanici tarafindan kabul edilen plan gerceklestirildi:
  - `preserve_old_ids` ana politika olarak uygulandi
  - RGB tarafinda mevcut draft kararlar final staging temeli olarak kilitlendi
  - placeholder province'ler sag alt teknik bolgede, en sag alttan baslayan `1 pixel` duzenli grid olarak boyandi
  - bu boyama siyah alan zorunlulugu aramadan yapildi
  - kullanicinin duzeltmesine gore sag alt anchor alani `126,186,199` (`sea_indian_ocean`) ustune boyandi

- Bu is icin yeni bir script yazildi:
  - `tools/build_final_preserve_old_staging.ps1`

- Bu scriptin amaci:
  - final RGB mapping csv'sini draft mapping'den authoritative staging mapping'e cevirmek
  - `provinces_birlesim.png` uzerinde secici RGB recolor'u uygulamak
  - placeholder grid'i son final staging PNG uzerine boyamak
  - final `definition_birlesim` staging csv'sini uretmek
  - placeholder'lar icin `default.map` teknik blok taslagi uretmek
  - overpaint ve legacy-unused raporlarini cikarmak
  - final staging validation ozeti vermek

- Bu scriptin neden olusturuldugu:
  - daha once farkli script ve ara csv'lerle parcali kurulan pipeline'i tek seferde tekrar uretilebilir staging hattina cevirmek gerekiyordu
  - canli mod dosyalarina dokunmadan, kontrol edilebilir bir final taslak seti elde etmek gerekiyordu

- Script gelistirme notlari:
  - ilk parser hatasi `Sort-Object` coklu property yazimindan geldi; PowerShell uyumlu hashtable siralamaya cevrildi
  - `Add-Type` icindeki `nameof(...)` kullanimi ortam derleyicisi tarafindan desteklenmedi; klasik string argumana cevrildi
  - consecutive-run helper'in donus tipi PowerShell list/dizi uyumsuzlugu verdi; `ToArray()` ile sabitlendi
  - `default.map` staging blok satirlarinda format operatoru ile literal `{}` kullanimi hata veriyordu; brace escaping duzeltildi
  - son olarak validation markdown icindeki ufak format kusuru ve final RGB mapping notlarindaki eski `draft only` ifadesi temizlendi

- Bu asamada uretilen dosyalar:
  - `analysis/generated/rgb_mapping_final_preserve_old.csv`
  - `analysis/generated/provinces_birlesim_rgb_only_preserve_old.png`
  - `analysis/generated/rgb_mapping_final_apply_report_preserve_old.csv`
  - `analysis/generated/rgb_mapping_final_apply_summary_preserve_old.md`
  - `analysis/generated/provinces_birlesim_final_preserve_old.png`
  - `analysis/generated/placeholder_pixel_map_preserve_old.csv`
  - `analysis/generated/placeholder_overpaint_report_preserve_old.csv`
  - `analysis/generated/legacy_unused_after_placeholder_overpaint_preserve_old.csv`
  - `analysis/generated/definition_birlesim_final_preserve_old.csv`
  - `analysis/generated/default_map_placeholder_block_preserve_old.txt`
  - `analysis/generated/final_staging_validation_preserve_old.md`

- Bu dosyalarin rolleri:
  - `rgb_mapping_final_preserve_old.csv`
    - amac: draft RGB kararlarini authoritative final staging mapping'e cevirmek
    - neden olusturuldu: recolor isleminde artik hangi RGB'nin kesin secildigini sabitlemek
  - `provinces_birlesim_rgb_only_preserve_old.png`
    - amac: sadece RGB conflict recolor'u uygulanmis, placeholder henuz boyanmamis ara PNG olmak
    - neden olusturuldu: placeholder oncesi ve sonrasi asamalari ayirmak
  - `rgb_mapping_final_apply_report_preserve_old.csv`
    - amac: final RGB mapping satirlarinin piksel bazli ne kadar uygulandigini gostermek
    - neden olusturuldu: recolor uygulamasinin tam yapildigini dogrulamak
  - `rgb_mapping_final_apply_summary_preserve_old.md`
    - amac: recolor uygulama ozetini okunabilir markdown olarak vermek
    - neden olusturuldu: mapping tarafinin sonucunu hizli okumak
  - `provinces_birlesim_final_preserve_old.png`
    - amac: RGB recolor + placeholder grid boyamasi tamamlanmis final staging province haritasi olmak
    - neden olusturuldu: canli `provinces.png` oncesinde kontrol edilecek nihai taslak gorsel
  - `placeholder_pixel_map_preserve_old.csv`
    - amac: her placeholder final ID'sinin hangi piksele boyandigini kaydetmek
    - neden olusturuldu: teknik placeholder alanini koordinat bazinda izlemek
  - `placeholder_overpaint_report_preserve_old.csv`
    - amac: placeholder boyamasi sirasinda hangi mevcut province renginin ne kadar ustune yazildigini toplu gostermek
    - neden olusturuldu: placeholder teknik alaninin hangi province'i feda ettigini net kaydetmek
  - `legacy_unused_after_placeholder_overpaint_preserve_old.csv`
    - amac: final definition'da kalip final PNG'de artik hic pikseli olmayan satirlari listelemek
    - neden olusturuldu: placeholder overpaint sonrasi bos kalan eski province var mi diye kontrol etmek
  - `definition_birlesim_final_preserve_old.csv`
    - amac: `preserve_old_ids` politikasina gore uretilmis final staging `definition.csv` olmak
    - neden olusturuldu: canli `map_data/definition.csv` oncesi authoritative taslak tanimi saglamak
  - `default_map_placeholder_block_preserve_old.txt`
    - amac: placeholder province ID'lerini tek yorumlu teknik `impassable_mountains` blogu halinde vermek
    - neden olusturuldu: canli `default.map` degisikliginden once staging blok hazirlamak
  - `final_staging_validation_preserve_old.md`
    - amac: tum staging setinin dogrulama ve sayisal kontrol ozetini vermek
    - neden olusturuldu: final taslagin teknik olarak tutarli oldugunu tek yerde gostermek

- Guncel staging sonucu:
  - final image size: `9216x4608`
  - anchor base RGB before placeholder overlay: `126,186,199`
  - placeholder grid: `38` kolon x `38` satir
  - placeholder pixel count: `1435`
  - final non-black image color count: `14696`
  - final definition color count: `14696`
  - contiguous final definition IDs: `True`
  - duplicate RGB count in final definition: `0`
  - legacy unused definition rows after placeholder overpaint: `0`

- Placeholder overpaint sonucu:
  - placeholder boyamasi yalnizca `126,186,199` uzerine oturdu
  - bu renk `final_new_id = 12763`, isim `sea_indian_ocean`
  - overwritten pixel count: `1435`
  - baska hicbir province renginin ustune placeholder boyanmadi

- Bunun anlami:
  - kullanicinin istedigi teknik alan pratikte dogrudan `sea_indian_ocean` alani oldu
  - fakat bu boyama sonrasinda bile `legacy_unused` sayisi `0` cikti
  - yani `sea_indian_ocean` rengi haritada tamamen yok olmadi; alt sagdaki teknik alan disinda baska piksellerde de yasiyor

- Placeholder koordinat ornegi:
  - ilk placeholder `12773` su piksele boyandi: `9215,4607`
  - sonra sola dogru gidildi: `9214,4607`, `9213,4607` ...
  - satir dolunca bir ust satira gecildi

- `default.map` staging blok ozet sonucu:
  - blok yorumlu teknik placeholder bolumu olarak uretildi
  - hem `RANGE` hem `LIST` satirlari kullanildi
  - bloktaki ID kumesi placeholder inventory ile birebir ayni cikti

- RGB tarafi staging sonucu:
  - final RGB mapping authoritative dosyaya kilitlendi
  - mapping notlari artik yalnizca draft degil, final staging temeli oldugunu acikca belirtiyor
  - mevcut beklenen sayilar korundu:
    - modlu changed RGB: `105`
    - orijinal changed RGB: `14`

- ID / tracking tarafi staging boyunca korunan sayilar:
  - modlu changed ID: `0`
  - orijinal changed ID: `634`

- Bu asamanin pratik sonucu:
  - artik canli dosyalara terfi edilmeden once incelenebilecek tam bir final staging set var
  - province PNG, definition, placeholder koordinatlari, overpaint raporu ve `default.map` teknik blok taslagi birbirine bagli halde duruyor
  - bir sonraki mantikli asama, bu staging seti kullanarak gercek `map_data/provinces.png`, `map_data/definition.csv` ve `map_data/default.map` gecis planini uygulamak olacak

## Canli Map_Data Terfi Asamasi

- Staging setten canli `map_data` dosyalarina kontrollu terfi yapildi.

- Bu asamada yapilan canli degisiklikler:
  - `analysis/generated/provinces_birlesim_final_preserve_old.png` -> `map_data/provinces.png`
  - `analysis/generated/definition_birlesim_final_preserve_old.csv` -> `map_data/definition.csv`
  - `map_data/default.map` icine teknik placeholder blogu eklendi

- Bu asamanin amaci:
  - staging seti artik oyunun bekledigi gercek hedef dosya adlarina terfi ettirmek
  - `default.map` icindeki `definitions = "definition.csv"` ve `provinces = "provinces.png"` referanslarini fiilen karsilamak

- Bu asamada yapilan on kontrol:
  - `map_data/default.map` aktif olarak `definition.csv` ve `provinces.png` bekliyordu
  - fakat `map_data` klasorunde bu dosyalar yoktu
  - bu nedenle staging promotion yalnizca iyilestirme degil, ayni zamanda gerekli hedef dosyalari yerine koyma islevi gordu

- `default.map` placeholder blogu eklenirken yapilan ek akil yurutme:
  - placeholder inventory icindeki tum ID'ler kor olarak eklenmedi
  - once `default.map` icinde sayilar tarandi
  - `1435` placeholder ID'sinin `118` tanesinin zaten mevcut `impassable_mountains` satirlarinda bulundugu goruldu
  - bu nedenle canli `default.map`e yalnizca eksik `1317` ID eklendi
  - boylece gereksiz duplicate `impassable_mountains` kalabaligi olusturulmadi

- Bu asamada uretilen ek yardimci dosya:
  - `analysis/generated/default_map_placeholder_block_missing_only_preserve_old.txt`

- Bu dosyanin rolu:
  - amac: canli `default.map`e eklenecek filtrelenmis teknik placeholder blogunu saklamak
  - neden olusturuldu: staging bloktaki mevcut duplicate ID'leri ayiklayip yalnizca eksik placeholder ID'leri canli dosyaya temiz sekilde eklemek

- `default.map` icindeki canli ekleme:
  - blok, mevcut `impassable_mountains` bolumunun sonunda
  - `#Old Steppe. Re use these` satirlarindan sonra
  - yeni `sea_zones` satirlarina gecilmeden once yerlestirildi
  - blok bas/son yorumlari:
    - `# TECH PLACEHOLDER PROVINCES BEGIN`
    - `# TECH PLACEHOLDER PROVINCES END`

- Canli promotion sonrasi dogrulama:
  - `map_data/provinces.png` var: `True`
  - `map_data/definition.csv` var: `True`
  - `map_data/default.map` icinde teknik placeholder blogu bulundu: `True`
  - staging vs canli hash esitligi:
    - `provinces.png`: `True`
    - `definition.csv`: `True`

- Canli dosya boyutlari:
  - `map_data/provinces.png`: `3287215`
  - `map_data/definition.csv`: `441244`
  - `map_data/default.map`: `19802`

- Bu asamanin pratik sonucu:
  - mod artik province haritasi ve definition icin gercek hedef dosya adlarina sahip
  - `default.map` placeholder ID'leri de canli dosyada tanimli
  - staging set ile canli set arasinda province PNG ve definition tarafinda icerik farki yok

- Bu asamadan sonraki mantikli adim:
  - oyun/log seviyesinde smoke test
  - sonra province ID referansli diger canli dosyalari, tracking csv'lere bakarak gerekli yerlerde guncellemek

## Definition Name Encoding Notu

- Kullanici, `map_data/definition.csv` icinde bazi isimlerin bozuk gorundugunu bildirdi:
  - ornek: `Näsijärvi` yerine `NÃ¤sijÃ¤rvi`

- Yapilan tespit:
  - temiz kaynak dosyalar:
    - `map_data/definition_modlu.csv`
    - `map_data/definition_orijinal.csv`
    icinde isimler dogru UTF-8 olarak duruyor
  - bozulmus isimler esasen ara generated csv'lerdeki onceki encoding yanlis okumalarindan geliyor
  - ama canli `map_data/definition.csv` icin cok onemli bir nufans bulundu:
    - dosya UTF-8 olarak dogru icerige sahip
    - PowerShell `Get-Content` varsayilan encoding ile okununca isimler bozuk gorunuyor
    - ayni dosya `-Encoding utf8` ile okununca isimler dogru gorunuyor

- Bu nedenle sonuc:
  - canli `map_data/definition.csv` icindeki bayt duzeyi isimler zaten dogruydu
  - bozuk gorunumun bir kismi gosterim/okuma katmanindan kaynaklaniyordu

- Yine de isim onarimi icin yeni bir script yazildi:
  - `tools/repair_definition_names_from_sources.ps1`

- Bu scriptin amaci:
  - final master tracking tablosunu kullanip her final ID icin dogru source adini belirlemek
  - temiz UTF-8 kaynaklardan isimleri tekrar yuklemek
  - hedef definition dosyalarinda yalnizca isim sutununu duzeltmek

- Bu scriptin neden olusturuldugu:
  - isim katmanini gelecekte kontrollu sekilde yeniden kurabilmek
  - bozuk generated definition kopyalarini temiz kaynaklardan tekrar isimlendirmek

- Bu asamada uretilen dosyalar:
  - `analysis/generated/definition_name_repair_report.csv`
  - `analysis/generated/definition_name_repair_summary.md`

- Bu dosyalarin rolleri:
  - `definition_name_repair_report.csv`
    - amac: hangi final ID'de hangi eski ismin hangi yeni isme cevrildigini listelemek
    - neden olusturuldu: isim duzeltmesini denetlenebilir hale getirmek
  - `definition_name_repair_summary.md`
    - amac: hangi hedef dosyada kac isim duzeltmesi yapildigini ozetlemek
    - neden olusturuldu: onarimin sonucunu hizli okumak

- Scriptin hedefledigi dosyalar:
  - `map_data/definition.csv`
  - `analysis/generated/definition_birlesim_final_preserve_old.csv`

- Guncel sonuc:
  - `map_data/definition.csv` icin changed names: `0`
    - neden: dosya UTF-8 olarak zaten dogruydu; varsayilan yanlis okuma bozuk gorunum uretiyordu
  - `analysis/generated/definition_birlesim_final_preserve_old.csv` icin changed names: `98`
    - burada generated staging kopyasinda gercek mojibake isimler vardi ve onarildi

- Dogrulama:
  - `map_data/definition.csv` dosyasi UTF-8 ile okununca:
    - `Näsijärvi`
    - `Aral Teńizi`
    - `Kilikía`
    - `Aktí tis Taurikê`
    gibi isimler dogru gorunuyor
  - ayni dosya bozuk mojibake metni (`NÃ¤sijÃ¤rvi`) artik UTF-8 raw okumada icermiyor

## Works Klasoru Temizlik Asamasi

- Kullanici repo kokunde `Works` adinda ayri bir klasor acti.
- Bu asamanin ana amaci:
  - canli kullanilan son `map_data` dosyalarini yerinde birakmak
  - bizim uretdigimiz generated/developing dosyalari ayri klasorde toplamak
  - ortami temizleyip sonraki provinces downstream asamasina daha duzenli gecmek

- Kullanici tarafindan korunmasi istenen canli hedef dosyalar:
  - `map_data/provinces.png`
  - `map_data/default.map`
  - `map_data/definition.csv`

- Bu asamada gercekten yapilan tasimalar:
  - `analysis/generated/*` -> `Works/analysis/generated/`
  - `map_data` icindeki development source PNG/CSV dosyalari -> `Works/map_data_sources/`

- `Works/analysis/generated/` klasorunun rolu:
  - amac: bugune kadar uretilen tum audit, tracking, staging, preview ve final-draft dosyalarini tek yerde toplamak
  - neden olusturuldu: canli mod dosyalari ile analysis/generated kalabaligini ayirmak

- `Works/map_data_sources/` klasorunun rolu:
  - amac: merge sirasinda kullandigimiz kaynak `definition_*.csv` ve `provinces_*.png` dosyalarini saklamak
  - neden olusturuldu: `map_data` klasorunde sadece final canli province setini birakmak

- `Works/map_data_sources/` altina tasinan dosyalar:
  - `definition_modlu.csv`
  - `definition_modlu_kalan.csv`
  - `definition_orijinal.csv`
  - `definition_orijinal_dogu.csv`
  - `definition_orijinal_kalan.csv`
  - `provinces_birlesim.png`
  - `provinces_modlu.png`
  - `provinces_modlu_dogu.png`
  - `provinces_modlu_kalan.png`
  - `provinces_orijinal.png`
  - `provinces_orijinal_dogu.png`
  - `provinces_orijinal_kalan.png`

- Temizlik sonrasi yorum kuralı:
  - onceki notlarda gecen `analysis/generated/...` yollarinin buyuk cogu artik fiziksel olarak `Works/analysis/generated/...` altinda bulunuyor
  - onceki notlarda gecen `map_data/definition_modlu*.csv`, `map_data/definition_orijinal*.csv` ve `map_data/provinces_*` source dosyalari artik `Works/map_data_sources/...` altinda bulunuyor
  - canli authoritative province seti ise halen su uc dosya:
    - `map_data/provinces.png`
    - `map_data/definition.csv`
    - `map_data/default.map`

- Temizlik sonrasi `map_data` klasorunde kalan ana dosya yapisi:
  - `provinces.png`
  - `definition.csv`
  - `default.map`
  - ve normal CK3 map altyapi dosyalari:
    - `adjacencies.csv`
    - `geographical_regions/`
    - `gude-2026-03-26.log`
    - `heightmap.heightmap`
    - `heightmap.png`
    - `indirection_heightmap.png`
    - `island_region.txt`
    - `nodes.dat`
    - `packed_heightmap.png`
    - `rivers.png`

- Bu asamanin pratik sonucu:
  - repo kokundeki generated kalabalik `Works` altina toplandi
  - `map_data` artik final canli map_data setini daha net temsil ediyor
  - bundan sonraki provinces downstream calismalarinda yanlislikla eski source/preview dosyalarini hedef alma riski azaldi

## Works Altina Tools Ve Analysis Tasinmasi

- Kullanici, kokte hala duran `tools` ve `analysis` klasorlerinin de `Works` altina alinmasini acikca istedi.

- Bu asamada yapilan tasima:
  - `analysis/definition_birlesim_plan.md` -> `Works/analysis/definition_birlesim_plan.md`
  - `tools/*.ps1` -> `Works/tools/`

- `Works/tools/` klasorunun rolu:
  - amac: merge, audit, tracking, staging, name-repair ve policy uretim scriptlerini tek yerde toplamak
  - neden olusturuldu: kokte teknik script kalabaligini azaltmak ve calisma dosyalarini `Works` altinda toplamak

- `Works/tools/` altina tasinan scriptler:
  - `analyze_pre_id_strategy.ps1`
  - `apply_selective_rgb_mapping.ps1`
  - `build_definition_csv_drafts.ps1`
  - `build_definition_subset_audit.ps1`
  - `build_final_preserve_old_staging.ps1`
  - `build_id_policy_drafts.ps1`
  - `build_id_policy_repo_impact.ps1`
  - `build_policy_master_tracking.ps1`
  - `build_rgb_resolved_candidates.ps1`
  - `repair_definition_names_from_sources.ps1`

- `Works/analysis/definition_birlesim_plan.md` dosyasinin rolu:
  - amac: birlesim mantiginin uzun teknik planini, asamalari ve karar notlarini saklamak
  - neden oraya tasindi: `analysis/generated` zaten `Works/analysis/generated` altina alinmisti; plan dosyasinin da ayni ana klasorde durmasi daha tutarli oldu

- Tasima sonrasi kok durumu:
  - eski `analysis` klasoru bosaldigi icin kaldirildi
  - eski `tools` klasoru bosaldigi icin kaldirildi
  - kokte canli mod dosyalari ve genel mod klasorleri kaldi

- Bu asamanin pratik sonucu:
  - artik tum development/analysis/script varliklari `Works` altinda toplandi
  - kokteki ana odak canli mod yapisi ve `map_data` oldu
  - bundan sonraki downstream province entegrasyon asamalarinda aranacak yardimci dosyalar:
    - `Works/tools/...`
    - `Works/analysis/...`
    - `Works/map_data_sources/...`

## Province Touchpoints Envanteri

- Kullanici yeni asamada mod icinde province ile ilgili butun dosya ve kisimlari bulmamizi istedi.
- Bu asamanin hedefi:
  - province merge sonrasi hangi dosya ailelerine dokunmamiz gerekecegini tek yerde gormek
  - canli `map_data` degisince etkilenebilecek downstream dosyalari envanterlemek

- Bu is icin yeni script olusturuldu:
  - `Works/tools/build_province_touchpoints_inventory.ps1`

- Bu scriptin rolu:
  - amac: mod icinde province ile dogrudan veya dolayli ilgili dosyalari kategorilere ayirip listelemek
  - neden olusturuldu: sonraki downstream entegrasyon asamalarinda hangi dosya ailelerinin taranacagini ve oncelik sirasini netlestirmek

- Bu scriptin uretdigi dosyalar:
  - `Works/analysis/generated/province_touchpoints_inventory.csv`
  - `Works/analysis/generated/province_touchpoints_inventory.md`
  - `Works/analysis/generated/province_touchpoints_category_counts.csv`

- Bu dosyalarin rolleri:
  - `province_touchpoints_inventory.csv`
    - amac: her file path icin kategori, oncelik, neden ve varsa ilk evidence satirini tutmak
    - neden olusturuldu: province ile ilgili tum dosya temas noktalarini makine-okunur tam liste olarak saklamak
  - `province_touchpoints_inventory.md`
    - amac: ayni envanterin insan-okunur ozetini vermek
    - neden olusturuldu: hizli kategori bazli tarama yapabilmek
  - `province_touchpoints_category_counts.csv`
    - amac: kategori bazinda kac dosya oldugunu gostermek
    - neden olusturuldu: is yukunu ve oncelikli aileleri hizli degerlendirmek

- Guncel sayilar:
  - `history_provinces`: `186`
  - `history_titles`: `257`
  - `landed_titles`: `12`
  - `map_data_core`: `5`
  - `map_data_regions`: `11`
  - `map_object_data`: `21`
  - `map_object_generated`: `18`
  - `secondary_province_touchpoint`: `77`

- Bu sayilarin anlami:
  - `history_provinces`, `landed_titles`, `history_titles`, `map_data_core`, `map_object_data` ana downstream province aileleri
  - `secondary_province_touchpoint` ise core ailelerin disinda acik province/province-scope/location/building referansi iceren event/decision/script/history dosyalarini gosteriyor

- Bu asamanin pratik sonucu:
  - artik province merge sonrasi bakilacak dosya aileleri sadece sezgisel degil, somut envanter halinde mevcut
  - sonraki asamada bu listeye bakarak once `gfx/map/map_object_data`, sonra province ID veya province-title baglantisini etkileyen ailelere sirali gidebiliriz

- Sonraki rafine etme notu:
  - ilk inventory surumunde localization concept-link false positive'leri vardi
  - ornek: `localization/replace/english/z_MB_decisions_l_english.yml` dosyasi yalnizca `[special_building|E]` gibi localization kavram linkleri yuzunden secondary kategoriye girmisti
  - script daha sonra daraltildi:
    - localization koku secondary taramadan cikarildi
    - yalnizca daha yapisal patternler birakildi:
      - `province:`
      - `province =`
      - `province_id`
      - `capital_province`
      - `title_province`
      - `any_county_province`
      - `every_county_province`
      - `outbreak_province`
      - `location = title:b_/c_`
      - `capital = b_/c_`
      - `special_building_slot =`
      - `special_building =`
      - `duchy_capital_building =`
  - bu rafine etmeden sonra localization false positive'leri inventory'den cikarildi
  - `secondary_province_touchpoint` sayisi `84`ten `77`ye dustu

- Daha sonra ikinci bir gap-check yapildi:
  - amac: sabit county/barony title atayan ama ilk daraltmada kacmis dosyalari bulmak
  - bu gap-check sonunda script bir kez daha genisletildi:
    - `title = c_*`
    - `county = c_*`
    - `barony = b_*`
    - `has_title = c_*` veya `has_title = title:c_*`
    - `x = c_*` tipi sabit title mapping satirlari da dahil edildi

- Bu ikinci turda envantere sonradan eklenen onemli gercek dosyalar:
  - `common/bookmarks/bookmarks/00_bookmarks.txt`
  - `common/religion/holy_site_types/00_holy_site_types.txt`
  - `common/religion/holy_site_types/RICE_holy_sites.txt`
  - `common/coat_of_arms/coat_of_arms/91_NB_landed_titles.txt`
  - `common/coat_of_arms/coat_of_arms/92_NB_dynasties.txt`
  - `common/coat_of_arms/dynamic_definitions/00_MB_dynamic_coas.txt`

- Ikinci tur sonrasi `secondary_province_touchpoint` guncel sayisi:
  - `68`

- Ikinci tur gap-check sonucu bilincli olarak disarida birakilan false positive dosyalar:
  - `common/coat_of_arms/coat_of_arms/93_NB_random_templates.txt`
    - `c_` ile baslayan sablon anahtarlari title degil, COA template adi
  - `common/dynasties/00_dynasties.txt`
    - `c_` ile baslayan bazi anahtarlar county title degil, dynasty key

- Bu gap-check sonucunu belgelemek icin yeni dosya olusturuldu:
  - `Works/analysis/generated/province_touchpoints_gap_check.md`

- Bu dosyanin rolu:
  - amac: inventory'nin son daraltma/genisletme sonrasi neden bu sekilde kabul edildigini belgelemek
  - neden olusturuldu: hangi dosyalar sonradan eklendi, hangileri bilincli olarak disarida birakildi net kalsin

## 2026-04-12 Core Province Entegrasyon Turu Uygulandi

Bu turda daha once planlanan `core only` downstream entegrasyon gercekten uygulandi.

Canli olarak guncellenen dosyalar:

- `history/provinces/00_MB_PROVINCES.txt`
- `common/landed_titles/00_landed_titles.txt`
- `history/titles/00_ASIA_CHINA.txt`
- `history/titles/00_ASIA_JAPAN.txt`
- `history/titles/00_ASIA_NORTH.txt`
- `history/titles/00_ASIA_SOUTH.txt`
- `history/titles/00_OTHER.txt`
- `map_data/adjacencies.csv`
- `map_data/island_region.txt`
- `gfx/map/map_object_data/building_locators.txt`
- `gfx/map/map_object_data/special_building_locators.txt`
- `gfx/map/map_object_data/player_stack_locators.txt`
- `gfx/map/map_object_data/combat_locators.txt`
- `gfx/map/map_object_data/siege_locators.txt`
- `gfx/map/map_object_data/activities.txt`

Bu turda bilerek dokunulmayan aileler:

- `map_data/geographical_regions/*.txt`
- `secondary_province_touchpoint`
- 6 crash locator disindaki `map_object_data`

### Uygulama Kurali

- `modlu_kalan` icerik mod kaynagindan tasindi
- `orijinal_dogu` icerik vanilla kaynagindan tasindi
- imported vanilla east tarafinda `old_vanilla_id -> final_new_id` rewrite uygulandi
- ana ID politikasi degismedi: `preserve_old_ids`

### Uretilen Ana Arac

- `Works/tools/implement_core_province_integration.ps1`
  - amac: core downstream province entegrasyonunu tek script ile tekrar uretilebilir hale getirmek
  - neden olusturuldu: `history/provinces`, `landed_titles`, `history/titles`, `adjacencies` ve 6 locator dosyasini ayni authoritative tracking tablolarindan tekrar kurabilmek

### Bu Turda Uretilen Yeni Raporlar

- `Works/analysis/generated/core_province_integration/core_province_integration_summary.md`
  - amac: bu turun toplu sonuc sayilarini kisa ozet halinde saklamak
  - neden olusturuldu: tek bakista coverage/missing/diff durumunu gormek

- `Works/analysis/generated/core_province_integration/history_provinces_merge_report.csv`
  - amac: her final province icin history blok kaynagi bulundu mu bulunmadi mi gostermek
  - neden olusturuldu: imported east ve kept west history coverage'ini satir bazinda denetlemek

- `Works/analysis/generated/core_province_integration/history_provinces_mod_duplicates.csv`
  - amac: mod history/provinces tarafinda ayni province id birden fazla dosyada var mi gostermek
  - neden olusturuldu: source dictionary cikarirken duplicate riskini belgelemek

- `Works/analysis/generated/core_province_integration/history_provinces_vanilla_duplicates.csv`
  - amac: vanilla history/provinces tarafinda ayni province id birden fazla dosyada var mi gostermek
  - neden olusturuldu: vanilla source coverage/duplicate durumunu kayda gecirmek

- `Works/analysis/generated/core_province_integration/landed_titles_vanilla_province_rewrite_report.csv`
  - amac: imported vanilla landed title root'larindaki `province = id` satirlarinin nasil cozuldugunu gostermek
  - neden olusturuldu: dogrudan rewrite, mod-barony fallback ve tamamen kaldirilan unmapped barony durumlarini belgelemek

- `Works/analysis/generated/core_province_integration/history_titles_merge_report.csv`
  - amac: hangi east title history root'larinin hangi mod dosyasina import edildigini gostermek
  - neden olusturuldu: macro root bazli merge'in izlenebilir olmasi

- `Works/analysis/generated/core_province_integration/stale_old_vanilla_id_report.csv`
  - amac: adjacencies merge sirasinda maplenemeyen vanilla/mod source satirlarini gostermek
  - neden olusturuldu: seam veya source coverage sorunlarini sonradan manuel incelemek

- `Works/analysis/generated/core_province_integration/invalid_final_id_report.csv`
  - amac: final definition disi province id kalip kalmadigini raporlamak
  - neden olusturuldu: rewritten `adjacencies.csv` icinde gecersiz id kalmamasini denetlemek

- `Works/analysis/generated/core_province_integration/island_region_pass_report.csv`
  - amac: `map_data/island_region.txt` icin bu turda ne yapildigini kayda gecirmek
  - neden olusturuldu: bu dosyada numeric province rewrite gerekmedigi ve mevcut mod bazinin korundugu net kalsin

- `Works/analysis/generated/core_province_integration/locator_missing_report.csv`
  - amac: 6 locator dosyasinda mod/vanilla source veya generated fallback tarafinda eksik kalan province id'leri gostermek
  - neden olusturuldu: incomplete locator riskinin hangi subsette toplandigini belgelemek

- `Works/analysis/generated/core_province_integration/locator_validation_report.csv`
  - amac: final locator dosyalarinda invalid final id veya duplicate positive id var mi gostermek
  - neden olusturuldu: statik locator saglik kontrolu yapmak

- `Works/analysis/generated/core_province_integration/locator_oracle_diff_report.csv`
  - amac: merged locator sonucu ile crash-sonrasi generated oracle arasindaki farklari dosya/id bazinda gostermek
  - neden olusturuldu: source-merge sonucu ile oyunun uretecegi locator seti arasindaki aciyi olcmek

### Core Tur Sonuc Sayilari

- `history/provinces` merged candidates: `11063`
- `history/provinces` missing history block: `2198`
  - yorum: bu eksiklerin tamami fatal kabul edilmemeli; deniz/wasteland/boş history beklenen alanlar olabilir

- `common/landed_titles` imported root sayisi: `10`
- `history/titles` imported root sayisi: `7`

- `map_data/adjacencies.csv` merged row sayisi: `375`
- `map_data/adjacencies.csv` dropped stale row sayisi: `279`

- `landed_titles` province rewrite sonucu:
  - `rewritten`: `1853`
  - `fallback_mod_barony`: `345`
  - `missing_mapping_barony_removed`: `90`
  - yorum: `h_china` ve `e_tibet` root'larinda final ID karsiligi bulunmayan bazi vanilla barony'ler tamamen kaldirildi; boylece stale yanlis province id tasinmadi

- locator sonucu:
  - `locator missing rows`: `8466`
  - `locator validation flags`: `0`
  - `locator oracle diffs`: `12841`
  - status dagilimi:
    - `missing_mod_locator`: `5748`
    - `missing_vanilla_locator`: `496`
    - `fallback_generated_for_missing_vanilla`: `2222`

### Bu Turda Alinan Ek Teknik Kararlar

- `common/landed_titles` importunda vanilla province id finale maplenemiyorsa once ayni `b_*` title icin moddaki province id fallback'i denendi
- bu da yoksa ilgili vanilla `b_*` barony block'u tamamen kaldirildi
- amac yanlis province id ile oyuna hatali title baglantisi sokmamak

- mod source dosyalarini tekrar tekrar ustune merge ederken drift olmamasi icin bazi kaynaklar script icinde `git HEAD` iceriginden okunacak sekilde tasarlandi
- bu sayede ikinci/ucuncu kosularda mevcut working copy merge sonucu tekrar kaynak sanilmayacak

- `git show` stdout encoding'i unicode mojibake uretebildigi icin HEAD okuma katmani byte-seviyesinde okunacak sekilde duzeltildi
- bu duzeltme sonrasi imported title history bloklarinda `Shōtoku` gibi isimlerdeki bozulma temizlendi

### Bu Turun Pratik Sonucu

- artik `map_data` merge'inin downstream ilk cekirdek ailesi gercekten uygulanmis durumda
- bundan sonraki crash/uyumsuzluk arastirmasi icin ana focus:
  - locator completeness
  - `geographical_regions`
  - sonra `secondary_province_touchpoint`

## 2026-04-12 Core Entegrasyon Sonrasi Dogrulama Bulgulari

Core entegrasyon turundan sonra degisen dosyalar tek tek kontrol edildi.

### Kesin Hata

- 6 locator dosyasinda script kaynakli `id` bozulmasi bulundu:
  - `gfx/map/map_object_data/building_locators.txt`
  - `gfx/map/map_object_data/special_building_locators.txt`
  - `gfx/map/map_object_data/player_stack_locators.txt`
  - `gfx/map/map_object_data/combat_locators.txt`
  - `gfx/map/map_object_data/siege_locators.txt`
  - `gfx/map/map_object_data/activities.txt`

- Ornek:
  - `gfx/map/map_object_data/activities.txt` satir civari `2289`
  - beklenen: `id=383`
  - mevcut bozuk sonuc: `$1383`

- Kok neden:
  - `Works/tools/implement_core_province_integration.ps1` icindeki `Rewrite-LocatorBlockId`
  - regex replacement `('$1' + $NewId)` kullandigi icin `id=` prefixini korumak yerine `$1NNN` turu bozuk satirlar uretti

- Bozuk satir sayilari:
  - `building_locators.txt`: `2826`
  - `special_building_locators.txt`: `2826`
  - `player_stack_locators.txt`: `3099`
  - `combat_locators.txt`: `3099`
  - `siege_locators.txt`: `2826`
  - `activities.txt`: `2826`

- Sonuc:
  - locator dosyalari su haliyle guvenilir kabul edilmemeli
  - bir sonraki uygulama adiminda once locator rewrite bug'i duzeltilmeli

### Yapisal Olarak Temiz Gorunenler

- `common/landed_titles/00_landed_titles.txt`
  - imported east root'lar tek kopya:
    - `e_viet`
    - `e_tibet`
    - `h_china`
    - `e_suvarnabhumi`
    - `e_brunei`
    - `e_kambuja`
    - `e_japan`
    - `k_chrysanthemum_throne`
    - `e_goryeo`
    - `k_yongson_throne`
  - `province = ...` satirlarinda final set disi ID bulunmadi
  - ama fidelity acisindan:
    - `1853` satir direkt rewrite
    - `345` satir mod-barony fallback
    - `90` vanilla barony tamamen kaldirildi
  - yorum:
    - invalid province id birakmadi
    - ama imported east birebir vanilla kalmadi; bazi barony baglari fallback veya drop ile cozuldu

- `history/titles`
  - imported east root'lar hedef dosyalarda tek kopya bulundu
  - duplicate east root bug'i gorulmedi
  - imported block'larda bazi mojibake comment/name kalintilari var ama bunlar buyuk olcude vanilla/source iceriginden geliyor; merge'in yarattigi yeni syntax hatasi olarak degerlendirilmedi

- `map_data/adjacencies.csv`
  - final definition disi province id bulunmadi
  - ama `279` stale/source satiri drop edildigi icin baglanti kapsaminda eksik kalmis olabilecek seam satirlari sonra gozden gecirilmeli

- `map_data/island_region.txt`
  - bu turda fiilen mantiksal degisiklik yapilmadi
  - eldeki fark esasen line ending seviyesinde

### Izlenmesi Gereken Riskler

- `history/provinces/00_MB_PROVINCES.txt`
  - merge raporuna gore `11063` candidate icin block bulundu
  - `2198` candidate icin source history block bulunmadi
  - bu durum tek basina fatal degil; bir kismi deniz/wasteland/default olabilir
  - ama imported east history coverage'in eksiksiz oldugu soylenemez

- `locator_oracle_diff_report.csv`
- locator tarafinda oracle'a gore fark halen cok yuksek (`12841`)
- bu da locator merge'in sadece syntax bug'i degil, coverage/fidelity acisindan da tekrar ele alinmasi gerektigini gosteriyor

## 2026-04-12 Locator Rewrite Bug Duzeltildi

Core entegrasyon sonrasi bulunan `$1383` tipi locator `id` bozulmasi duzeltildi.

### Kok Neden

- `Works/tools/implement_core_province_integration.ps1`
  - `Rewrite-LocatorBlockId`
  - `Rewrite-ProvinceHistoryBlockId`

- Bu helper'larda regex replacement string olarak `('$1' + $NewId)` benzeri ifade kullaniliyordu.
- `id=383` gibi bir satir bu nedenle `id=383` yerine `$1383` tipine bozulabiliyordu.

### Duzeltme

- Her iki helper da string replacement yerine explicit line rewrite mantigina cekildi
- yani prefix ve suffix regex match ile ayrilip yeni id dogrudan tekrar birlestirildi

### Duzeltme Sonrasi Sonuc

- 6 locator dosyasindaki `$NNN` bozuk satir sayisi artik `0`
  - `building_locators.txt`: `0`
  - `special_building_locators.txt`: `0`
  - `player_stack_locators.txt`: `0`
  - `combat_locators.txt`: `0`
  - `siege_locators.txt`: `0`
  - `activities.txt`: `0`

- `gfx/map/map_object_data/activities.txt` icindeki onceki ornek:
  - eski bozuk: `$1383`
  - yeni dogru: `id=383`

- `locator_validation_report.csv`
  - invalid final ID: `0`
  - duplicate positive ID: `0`

### Duzeltme Sonrasi Hala Acik Kalan Locator Riski

- syntax bug kapandi
- ama coverage/fidelity sorunu kapanmadi
- guncel sayilar:
  - `locator missing rows`: `8466`
  - `locator oracle diffs`: `17582`

- `locator_missing_report.csv` dagilimi:
  - `missing_mod_locator`: `5748`
  - `missing_vanilla_locator`: `496`
  - `fallback_generated_for_missing_vanilla`: `2222`

Yorum:

- Artık locator dosyalari parse edilebilir gorunuyor
- Ama source-merge coverage hala zayif; bu crash/log davranisini tekrar test etmek gerekiyor

## 2026-04-12 History Provinces Gap Siniflandirma

`history/provinces/00_MB_PROVINCES.txt` coverage acigi daha iyi anlasilsin diye ayri siniflandirma yapildi.

Yeni arac:

- `Works/tools/classify_history_province_gaps.ps1`
  - amac: `missing_history_block` satirlarini isim ve subset bazinda siniflandirmak
  - neden olusturuldu: `2198` eksigin ne kadarinin normal sayilabilecek deniz/wasteland/default alanlar oldugunu ayirmak

Yeni raporlar:

- `Works/analysis/generated/core_province_integration/history_provinces_missing_classification.csv`
  - amac: her eksik satir icin category ve review class yazmak
  - neden olusturuldu: manuel bakilacak province'leri daraltmak

- `Works/analysis/generated/core_province_integration/history_provinces_missing_classification.md`
  - amac: toplu siniflandirma sayilarini kisa ozetlemek
  - neden olusturuldu: tek bakista risk seviyesini gormek

### Siniflandirma Sonucu

- toplam `missing_history_block`: `2198`

- review class:
  - `likely_benign_or_low_priority`: `1200`
  - `needs_manual_review`: `998`

- category:
  - `named_land_or_special`: `998`
  - `maritime_or_water`: `746`
  - `terrain_or_impassable`: `299`
  - `blank_name`: `155`

- source subset:
  - `modlu_kalan`: `1636`
  - `orijinal_dogu`: `562`

### Bu Sonucun Yorumlanmasi

- `2198` sayisinin tamami artik ayni agirlikta gorulmemeli
- bunlarin `1200` tanesi su anlik daha dusuk oncelikli gorunuyor
  - deniz
  - river
  - lake
  - terrain/wasteland benzeri isimler
  - bos isimli satirlar

- asil aktif inceleme havuzu su anda `998` satir
  - yani adli, ozel, kara province veya normal county/barony gibi duran eksik history bloklari

### Sonraki Mantikli Teknik Oncelik

- locator coverage ve smoke test
- ardindan `history_provinces_missing_classification.csv` icindeki `998` manual-review satirini kaynak bazli temizlemek

## Test Files Paketi

- kullanicinin istegiyle `test_files/` klasoru olusturulan test paketi hedefi olarak kullaniliyor
- amac: oyunda/ayri ortamda denenecek, az once yeniden yazdigimiz veya duzenledigimiz canli dosyalari tek yerde toplamak
- kural: sadece testte kullanilacak canli veri dosyalari kopyalandi; `Works/` altindaki analiz raporlari bu paketin icine alinmadi

### Kopyalanan Dosyalar

- `test_files/common/landed_titles/00_landed_titles.txt`
- `test_files/gfx/map/map_object_data/activities.txt`
- `test_files/gfx/map/map_object_data/building_locators.txt`
- `test_files/gfx/map/map_object_data/combat_locators.txt`
- `test_files/gfx/map/map_object_data/player_stack_locators.txt`
- `test_files/gfx/map/map_object_data/siege_locators.txt`
- `test_files/gfx/map/map_object_data/special_building_locators.txt`
- `test_files/history/provinces/00_MB_PROVINCES.txt`
- `test_files/history/titles/00_ASIA_CHINA.txt`
- `test_files/history/titles/00_ASIA_JAPAN.txt`
- `test_files/history/titles/00_ASIA_NORTH.txt`
- `test_files/history/titles/00_ASIA_SOUTH.txt`
- `test_files/history/titles/00_OTHER.txt`
- `test_files/map_data/adjacencies.csv`
- `test_files/map_data/default.map`
- `test_files/map_data/definition.csv`
- `test_files/map_data/island_region.txt`
- `test_files/map_data/provinces.png`

### Manifest

- `test_files/copied_files_manifest.txt`
  - amac: test paketine hangi dosyalarin konuldugunu tek listede tutmak
  - neden olusturuldu: klasor icindeki kopyalarin kapsamını hizli dogrulamak

## default.map Vanilla East Merge

- yeni crash analizi sonrasi `default.map`in dogu tarafi icin vanilla siniflandirmalarin hic merge edilmedigi netlesti
- bu nedenle yeni script yazildi:
  - `Works/tools/merge_default_map_vanilla_east.ps1`
  - amac: vanilla `default.map` icindeki imported east province'lerin `sea_zones`, `river_provinces`, `lakes`, `impassable_mountains`, `impassable_seas` uyeliklerini final `old_vanilla_id -> final_new_id` mapping ile canli `map_data/default.map`e tasimak
  - neden olusturuldu: `Province with no county data` loglarini azaltmak ve dogu su/mountain/special province siniflarini vanilla ile uyumlu hale getirmek

### default.map Merge Kurali

- baz dosya mevcut mod `map_data/default.map`
- imported east province seti:
  - `Works/analysis/generated/final_orijinal_tracking_preserve_old_ids.csv`
- kaynak kategori dogrusu:
  - vanilla `game/map_data/default.map`
- uygulama mantigi:
  - imported east final ID'lerini mevcut mod `default.map` icindeki hedef kategorilerden temizle
  - vanilla'daki karsilik old ID uyeliklerini final yeni ID'ye cevir
  - sonucu `# VANILLA EAST DEFAULT MAP BEGIN/END` blok olarak canli `default.map`e ekle
- test paketi senkronu:
  - `test_files/map_data/default.map` guncellendi

### Uretilen Dosyalar

- `Works/analysis/generated/default_map_vanilla_east/default_map_vanilla_east_merge_summary.md`
  - amac: merge ozeti ve ornek province kontrolleri
  - neden olusturuldu: hangi kategoride kac imported east ID oldugunu ve kritik isimlerin post-merge durumunu tek dosyada gormek

- `Works/analysis/generated/default_map_vanilla_east/default_map_vanilla_east_merge_category_report.csv`
  - amac: kategori bazli eklenen/temizlenen ID sayilari
  - neden olusturuldu: merge etkisini sayisal olarak dogrulamak

- `Works/analysis/generated/default_map_vanilla_east/default_map_vanilla_east_name_sample_report.csv`
  - amac: crash logdaki ornek province isimlerinin merge sonrasi hangi kategorilere dustugunu gostermek
  - neden olusturuldu: `no county data` loglarina en hizli geri beslemeyi saglamak

### Sayisal Sonuc

- imported east tracked row: `3391`
- hedef kategoriler:
  - `sea_zones`
  - `river_provinces`
  - `lakes`
  - `impassable_mountains`
  - `impassable_seas`

- merge edilen imported east final ID sayilari:
  - `sea_zones`: `207`
  - `river_provinces`: `54`
  - `lakes`: `15`
  - `impassable_mountains`: `273`
  - `impassable_seas`: `7`

### Ornek Sonuc

- artik su province'ler `impassable_mountains` icinde:
  - `east_hokkaido_mountains`
  - `shinano_mountains` varyantlari
  - `korea_mountains` varyantlari
  - `Viet_Mountains_6`
  - `Viet_Mountains_7`
  - `Viet_Mountains_8`

- su province'ler sample kontrolde hala kategori almamis gorundu:
  - `Binglingsi`
  - `Hezhou`
  - `XYZ` varyantlarindan biri
- yorum:
  - bunlar `default.map` yerine daha cok `landed_titles/county` veya ozel province mantigi problemi olabilir

### Canli Dosya Durumu

- `map_data/default.map` simdi:
  - placeholder teknik blogunu
  - ve ayrica `# VANILLA EAST DEFAULT MAP BEGIN/END` managed blokunu
  - birlikte iceriyor

## Crash: 2026-04-12 20:02:35

- crash klasoru:
  - `C:\Users\bsgho\Documents\Paradox Interactive\Crusader Kings III\crashes\ck3_20260412_200235`
- exception ayni tipte kaldi:
  - `EXCEPTION_ACCESS_VIOLATION`
- ama pre-crash log artik onceki teste gore daha dar bir probleme isaret ediyor

### Yeni Log Yorumu

- `Province with no county data` sayisi:
  - onceki crash: `715`
  - yeni crash: `643`
- yorum:
  - `default.map` dogu merge'u bazi su/mountain/impassable vakalarini azaltmis gorunuyor
  - ama ana blocker artik daha net sekilde `landed_titles` icindeki county/barony province baglari

### Ana Bulgular

- kalan `no county data` vakalari agirlikla gercek kara province'leri:
  - East Manchuria / Balhae / Liao / Amur
  - Gobi
  - Sakhalin
  - Endonezya/Papua/Andaman benzeri imported east bolgeleri
  - `Hezhou`
  - `Binglingsi`

- kritik teknik bulgu:
  - `common/landed_titles/00_landed_titles.txt` icinde bazi imported east barony'ler gercek final province yerine placeholder veya stale province ID'ye bagli

### Kanit Ornekleri

- `b_EMan_Ningzhou`
  - landed_titles province: `11855`
  - dogru final province:
    - `definition.csv`de `EMan_Ningzhou = 11899`

- `b_FIC_EMan_Zhonganyuan`
  - landed_titles province: `14394`
  - `14394` artik placeholder araliginda
  - dogru final province:
    - `definition.csv`de `FIC_EMan_Zhonganyuan = 11897`

- `b_FIC_EMan_Qingshancun`
  - landed_titles province: `14395`
  - dogru final province:
    - `definition.csv`de `FIC_EMan_Qingshancun = 11900`

- `b_FIC_EMan_Huangyuan`
  - landed_titles province: `14396`
  - dogru final province:
    - `definition.csv`de `FIC_EMan_Huangyuan = 11901`

- `b_FIC_EMan_Sanhean`
  - landed_titles province: `14402`
  - `14402` placeholder
  - dogru final province:
    - `definition.csv`de `FIC_EMan_Sanhean = 11908`

### Sonuc

- su anki ana crash adayi `default.map` degil
- asıl sorun imported east `landed_titles` province rewritelarinin bazi bloklarda placeholder/stale ID ile kalmis olmasi
- sonraki mantikli teknik hedef:
  - `common/landed_titles/00_landed_titles.txt` icindeki imported east rootlerde tum `province = ...` satirlarini gercek final province ID'lere yeniden dogrulamak ve placeholder baglarini temizlemek

## landed_titles Province Link Repair

- yeni script:
  - `Works/tools/repair_landed_titles_province_links.ps1`
  - amac: `common/landed_titles/00_landed_titles.txt` icindeki barony `province = ...` baglarini final `definition.csv` ile yeniden dogrulamak
  - neden olusturuldu: `no county data` crash logunda gorulen stale/placeholder province baglarini temizlemek

### Repair Mantigi

- her `b_*` barony blogu icin barony anahtari `b_` olmadan alinir
- bu isim normalize edilip `map_data/definition.csv` icindeki province isimleriyle eslestirilir
- sadece su durumlarda rewrite yapilir:
  - mevcut province placeholder ise
  - veya imported east final ID kapsamina giren, acik isim uyusmazligi varsa
- unrelated bati duzeltmeleri kalici olmamasi icin kapsam daraltildi

### Teknik Not

- ilk repair calismasi placeholder/stale baglariyla birlikte bazi east-disi normalized mismatch satirlarini da duzeltti
- bunlardan imported east disindaki `4` satir geri alindi
- script daha sonra imported east + placeholder odakli hale getirildi

### Somut Duzenlenen Ornekler

- `b_EMan_Ningzhou`
  - eski: `11855`
  - yeni: `11899`

- `b_FIC_EMan_Qingshancun`
  - eski: `14395` placeholder
  - yeni: `11900`

- `b_FIC_EMan_Huangyuan`
  - eski: `14396` placeholder
  - yeni: `11901`

- `b_FIC_EMan_Sanhean`
  - eski: `14402` placeholder
  - yeni: `11908`

- `b_FIC_EMan_Zhonganyuan`
  - eski: `14394` placeholder
  - yeni: `11897`

- `b_gobi_ikh_nart`
  - eski: `14539` placeholder
  - yeni: `12552`

### Uretilen Dosyalar

- `Works/analysis/generated/landed_titles_link_repair/landed_titles_province_link_repair_report.csv`
  - amac: taranan her province assignment icin rewrite/keep/unresolved durumu
  - neden olusturuldu: hangi baronylerin duzeltildigini ve hangilerinin hala unresolved kaldigini belgelemek

- `Works/analysis/generated/landed_titles_link_repair/landed_titles_province_link_repair_summary.md`
  - amac: repair ozet sayilari
  - neden olusturuldu: tek bakista kalan unresolved havuzunu gormek

### Mevcut Durum

- repair sonrasi kritik ornekler canli dosyada duzeldi:
  - `province = 11899`
  - `province = 11900`
  - `province = 11901`
  - `province = 11908`
  - `province = 11897`
  - `province = 12552`

- hala unresolved ornekler var:
  - `b_tym_sakhalin = province 13913` placeholder
  - `b_hezhou_hailong_china = province 12454` ve isim eslesmesi otomatik cikmiyor
- yorum:
  - bu kalanlar otomatik exact/normalized isim eslesmesiyle cozulmeyen, daha manuel veya root-bazli ikinci tur adaylar

### Yeni Bug Bulgusu

- `common/landed_titles/00_landed_titles.txt` icinde yeni bir regex-replacement bozulmasi bulundu
- ornek:
  - `b_primda` altinda `province = 4144` yerine sadece `$14144` yaziyor
- bulunan satirlar:
  - `$11609`
  - `$14144`
  - `$11902`
  - `$11890`
- yorum:
  - bu kasitli degil
  - onceki geri-alma adiminda replacement string icinde `$1 + sayi` formu kullanilmasindan kaynakli ayni tur bir PowerShell regex bug'i
  - locator bug'indaki `$1383` problemine benzer bir sinif

### Bug Fix

- bozuk `4` satir dogrudan duzeltildi
  - `$11609` -> `province = 1609`
  - `$14144` -> `province = 4144`
  - `$11902` -> `province = 1902`
  - `$11890` -> `province = 1890`
- canli dosya ve `test_files/common/landed_titles/00_landed_titles.txt` senkronlandi
- yeniden taramada `^\$[0-9]+` patterni iki dosyada da `0` sonuc verdi

### Yeni Esleme Kurali

- kullanici yeni landed_titles/province link onarimlarinda yalnizca isim benzerligine guvenilmemesini istedi
- bundan sonraki dogru province bulma mantigi icin ana zincir su olacak:
  - `old source province id`
  - `old source province rgb`
  - `source` (`modlu` / `orijinal`)
  - bu bilgilerden `final_new_id`
- yorum:
  - isim/normalized isim eslesmesi yalnizca yardimci sinyal olacak
  - placeholder ya da sea province'e yanlis baglanan baronylerde once provenance zinciri kontrol edilecek
  - ozellikle imported east barony repair turlarinda `final_orijinal_tracking_preserve_old_ids.csv`, `final_modlu_tracking_preserve_old_ids.csv` ve gerekiyorsa eski `definition_*.csv` kaynaklari temel alinacak

### Landed Titles Root Sebebi

- `Barony ... has no province defined` havuzunun onemli bir bolumunde sorun tek tek barony satiri degil, `common/landed_titles/00_landed_titles.txt` icinde eski mod dogu top-level root'larinin dosyada kalmis olmasi
- vanilla east root'lari eklenmis olsa da asagidaki mod dogu root'lari ayri bloklar olarak halen duruyordu:
  - `e_qixi`
  - `e_tunguse`
  - `e_jurchen_china`
  - `e_java`
  - `e_malayadvipa`
  - `e_srivijaya`
  - `e_kalimantan`
  - `e_angkor`
  - `e_ramanya`
  - `e_panyupayana`
  - `e_maluku`
- yorum:
  - bu root'lar placeholder/sea/stale province id'lerine bagli mod dogu baronylerini tasiyordu
  - `b_fic_eman_*`, `b_tym_sakhalin`, `b_johor`, `b_laputta`, `b_wakema`, `b_pyapon`, `b_maynila` gibi crash ornekleri bunlardan cikti

### E Nusantara Bulgusu

- ilk `implement_core_province_integration.ps1` landed_titles merge turunda `e_nusantara` hic import edilmemisti
- yorum:
  - bu eksik kapsam Filipinler / Nusantara tarafindaki `has no province defined` havuzunu buyuttu

### Yeni Refresh Turu

- yeni script eklendi:
  - `Works/tools/refresh_landed_titles_imported_east_from_vanilla.ps1`
  - amac: imported vanilla east root'larini tekrar kurmak, `e_nusantara`yi eklemek ve eski mod dogu root'larini dosyadan temizlemek
  - neden olusturuldu: current landed_titles icinde vanilla east ve mod east'in birlikte kalmasindan dogan stale province linklerini toplu temizlemek

- script iki kez gelistirilerek kosuldu:
  - ilk kosuda vanilla east root refresh yapildi ama eski mod dogu root'lar kaldi
  - ikinci kosuda legacy mod east root remove list'i eklenerek gercek temizleme tamamlandi

### Landed Titles Vanilla Refresh Sonucu

- rapor klasoru:
  - `Works/analysis/generated/landed_titles_vanilla_refresh/`
- ana dosyalar:
  - `landed_titles_vanilla_refresh_report.csv`
    - amac: vanilla source old province id -> final new id rewrite satirlarini belgelemek
    - neden olusturuldu: hangi imported east barony province satirlarinin rewrite/keep/remove oldugunu gormek
  - `landed_titles_vanilla_refresh_validation.csv`
    - amac: refresh sonrasi imported east root'lardaki barony province linklerinin `land / water / placeholder / missing_definition` sinifini cikarmak
    - neden olusturuldu: placeholder ya da sea province'e kalan barony baglari var mi kesin kontrol etmek
  - `landed_titles_vanilla_refresh_summary.md`
    - amac: tek bakista sayisal ozet
    - neden olusturuldu: refresh kalitesini hizli okumak

- ikinci refresh sonrasi ozet:
  - refreshed roots: `22`
  - rewritten province rows: `625`
  - kept same-id rows: `1495`
  - removed unmapped baronies: `435`
  - validation `land`: `2120`
  - validation `water`: `0`
  - validation `placeholder`: `0`
  - validation `missing_definition`: `0`

- pratik sonuc:
  - onceki ornek bozuk baronyler (`b_fic_eman_*`, `b_tym_sakhalin`, `b_idoi`, `b_tarayka`, `b_eusutur`, `b_ketuni`, `b_johor`, `b_laputta`, `b_wakema`, `b_pyapon`, `b_maynila` vb.) canli `00_landed_titles.txt` icinden kayboldu
  - bu satirlar ya dogru vanilla east blocklariyla degisti ya da stale mod east root temizligiyle dosyadan kalkti

### Tooling Duzeltmesi

- `Works/tools/implement_core_province_integration.ps1` landed_titles root kapsami da guncellendi
- yeni eklenen / duzeltilenler:
  - `e_nusantara` landed replacement spec'e eklendi
  - remove list'e yukaridaki legacy mod east root'lari eklendi
- yorum:
  - boylece script ileride tekrar kosulursa ayni root omission / stale east root problemi daha az olasi

## 2026-04-12 21:43 crash objective log reading

- Crash folder: C:\Users\bsgho\Documents\Paradox Interactive\Crusader Kings III\crashes\ck3_20260412_214320
- More objective reading after user correction:
  - Province with no county data: 987 total, 983 unique
  - Barony ... has no province defined: 160 total, 27 unique
  - Land associated barony/county ... null holder: 1
  - Assertion failed: 1
  - geographical_region: 3520
- Comparison with previous crash ck3_20260412_211533:
  - Province with no county data: 380 -> 987
  - Barony ... has no province defined: 1026 -> 160
- Interpretation:
  - recent fixes reduced has no province defined heavily
  - but county coverage problems became the dominant log class
  - _yerevan is still the final fatal assert line, but should be treated as a downstream/final blocker candidate, not automatically as the primary root cause
- Some has no province defined examples (_crivitz, _kyburg, _eutin, _wismar, etc.) already have visible province = ... rows in common/landed_titles/00_landed_titles.txt, so at least part of that class may indicate deeper landed_titles parse/structure/consistency issues rather than simple missing province assignments

## 2026-04-12 - provinces.png / definition.csv dual-source duplicate RGB onarimi

- Kullanici `map_data/provinces.png` icinde `135,36,34` RGB'sinin duplicate oldugunu fark etti; bu satir final `definition.csv`de `9668;135;36;34;Crivitz;x;` olarak duruyordu ama ayni RGB daha once `orijinal_dogu` tarafinda `IMPASSABLE CENTRAL GOBI 3` olarak da secilmisti.
- Bu uyaridan sonra `source_origin=both` olan tum final RGB satirlari icin fiziksel piksel denetimi yapildi.
- Yeni audit araci:
  - `Works/tools/audit_dual_source_rgb_in_final_map.ps1`
- Audit raporlari:
  - `Works/analysis/generated/provinces_duplicate_rgb_audit/dual_source_rgb_presence.csv`
  - `Works/analysis/generated/provinces_duplicate_rgb_audit/dual_source_rgb_presence.md`
- Audit sonucu:
  - `21` adet `source_origin=both` satiri denetlendi.
  - Canli `provinces.png` icinde `18` RGB gercekten hem `provinces_modlu_kalan.png` hem `provinces_orijinal_dogu.png` kaynakli piksel tasiyordu.
  - Bunlarin `13` tanesi farkli province adi/kimligi tasiyordu. Bu grup gercek hata kabul edildi.
- Problemli final RGB'ler `preferred_source_subset=modlu_kalan` olmasina ragmen orijinal dogudan gelen pikselleri de yasatiyordu. Bu, tek bir final RGB altinda iki ayri province kimligini birlestiriyordu.
- Onarim yaklasimi:
  - `modlu_kalan` tarafi mevcut final ID/RGB ile korundu.
  - `orijinal_dogu` tarafindaki ayri province parcasi icin mevcut placeholder ID/RGB'lerden `13` tanesi repurpose edildi.
  - Canli `provinces.png` icinde sadece `orijinal_dogu` kaynagindan gelen ilgili pikseller yeni RGB'lere tasindi.
  - Ayni placeholder satirlari `definition.csv` icinde gercek province satirlarina cevrildi.
  - Placeholder teknik pikselleri siyaha cekildi.
- Onarim scripti:
  - `Works/tools/repair_dual_source_duplicate_provinces.ps1`
- Onarim raporlari:
  - `Works/analysis/generated/provinces_duplicate_rgb_repair/dual_source_duplicate_repair_assignments.csv`
  - `Works/analysis/generated/provinces_duplicate_rgb_repair/dual_source_duplicate_repair_summary.md`
  - yedekler:
    - `Works/analysis/generated/provinces_duplicate_rgb_repair/provinces_before_dual_source_split.png`
    - `Works/analysis/generated/provinces_duplicate_rgb_repair/definition_before_dual_source_split.csv`
- Bu assignment CSV'si kullanici tarafindan ozellikle istenen `degisen rgb/id kaydi`nin authoritative kaydidir. Icindeki alanlar:
  - `kept_final_id`
  - `kept_rgb`
  - `modlu_old_id / modlu_old_rgb / modlu_old_name`
  - `orijinal_old_id / orijinal_old_rgb / orijinal_old_name`
  - `new_final_id`
  - `new_rgb`
  - `new_name`
  - `changed_pixels`
- Repurpose edilen yeni final ID'ler:
  - `12773` `Karub`
  - `12774` `PLACEHOLDER_REGION_KOREA`
  - `12775` `IMPASSABLE CENTRAL GOBI 1`
  - `12776` `IMPASSABLE CENTRAL GOBI 3`
  - `12777` `split_orijinal_9671`
  - `12778` `PLACEHOLDER_REGION_SOUTHEAST_COAST`
  - `12779` `Marakele`
  - `12780` `Siantan Island`
  - `12781` `Goryeo_Donggye_Myeongju`
  - `12782` `Goryeo_Donggye_Deungju`
  - `12783` `Goryeo_Donggye_Uiju`
  - `12784` `Goryeo_Donggye_Hwaju`
  - `12785` `Goryeo_Bukgye_Maengju`
- En buyuk piksel tasimalari:
  - `9665 -> 12775` `IMPASSABLE CENTRAL GOBI 1`: `75122` piksel
  - `9668 -> 12776` `IMPASSABLE CENTRAL GOBI 3`: `34909` piksel
- Onarim sonrasi audit sonucu:
  - canli `provinces.png` icinde iki kaynaktan birden yasayan RGB sayisi `5`e indi
  - farkli isimli `both-source` RGB sayisi `0` oldu
  - geriye kalan `5` RGB her iki kaynakta da ayni isim/kimlik tasiyan benign satirlardir:
    - `Candranatha`
    - `EAST INDIAN OCEAN TI`
    - `sea_bay_of_bengal` (2 satir)
    - `Naga Hills`
- `definition.csv` duplicate RGB kontrolu:
  - `0`
- Bu turda canli ve test kopyalari birlikte guncellendi:
  - `map_data/provinces.png`
  - `map_data/definition.csv`
  - `test_files/map_data/provinces.png`
  - `test_files/map_data/definition.csv`
- Onemli sonraki not:
  - Bu yeni repurpose edilen `13` final ID ileride `default.map`, `landed_titles` ve gerekirse `history/provinces`/diger province-reference dosyalarina da propagate edilmelidir.
  - Ozellikle Goryeo ve Gobi tarafindaki yeni province kimlikleri artik placeholder degil, gercek province olarak yasiyor.

## 2026-04-12 - dual-source split denemesi geri alindi

- Kullanici, bu `13`'lu split onarimindan sonra canli `map_data/provinces.png` icinde province renklerinin dogru konuma gelmedigini ve gorunurde kayma/yanlis yerlesim oldugunu bildirdi.
- Bu geri bildirim kabul edildi; gorsel hata kesin kullanici raporu olarak ele alindi ve split onarimi canli setten geri alindi.
- Geri alma islemi:
  - `map_data/provinces.png` -> `Works/analysis/generated/provinces_duplicate_rgb_repair/provinces_before_dual_source_split.png` yedegine donuldu
  - `map_data/definition.csv` -> `Works/analysis/generated/provinces_duplicate_rgb_repair/definition_before_dual_source_split.csv` yedegine donuldu
  - `test_files/map_data/provinces.png` ve `test_files/map_data/definition.csv` de ayni surume senkronlandi
- Hatali ara surumler silinmedi; inceleme icin saklandi:
  - `Works/analysis/generated/provinces_duplicate_rgb_repair/provinces_bad_after_split.png`
  - `Works/analysis/generated/provinces_duplicate_rgb_repair/definition_bad_after_split.csv`
- Hash dogrulamasi yapildi:
  - canli `map_data/provinces.png` hash'i `provinces_before_dual_source_split.png` ile birebir ayni
  - canli `map_data/definition.csv` hash'i `definition_before_dual_source_split.csv` ile birebir ayni
- Bu nedenle su anki canli durumda `13`'lu split uygulanmis DEGILDIR.
- Yani su an:
  - dual-source benign/shared fiziksel problem raporu hala gecerlidir
  - fakat onu cozmek icin kullanilan son otomatik split/recolor yaklasimi kabul edilmemis ve geri alinmistir
- Daha guvenli bir sonraki yol:
  - problemi rapor seviyesinde koru
  - otomatik toplu split yerine daha kontrollu / province-bazli / kullanici-onayli uygulama dusun

## 2026-04-12 - rollback sonrasi provinces.png teshi s turu

- Rollback sonrasi kullanicinin yonlendirmesiyle `provinces.png` ustunde yeniden sadece teshis yapildi; canli `map_data` dosyalarina bu turda degisiklik uygulanmadi.
- Kullanilan yeni araclar:
  - `Works/tools/compare_live_provinces_to_source_split.ps1`
  - `Works/tools/analyze_rgb_components_in_provinces.ps1`
  - `Works/tools/build_dual_source_conflict_diagnostics.ps1`
- Once `map_data/provinces.png` canli dosyasi ile ham secim kaynagi `Works/map_data_sources/provinces_birlesim.png` karsilastirildi.
- Sonuc:
  - canli `provinces.png`, ham `provinces_birlesim.png` ile ayni degil
  - degisen piksel sayisi: `3,536,008`
  - degisim bbox'i: tum haritayi kapsiyor (`0,0 -> 9215,4607`)
- Bu ilk bakista buyuk gozukse de sonraki kontrol daha anlamli oldu:
  - canli `map_data/provinces.png` hash'i
  - `Works/analysis/generated/provinces_birlesim_final_preserve_old.png`
  ile birebir ayni cikti.
- Yani mevcut canli `provinces.png`, ham `provinces_birlesim.png` degil; eski final staging ciktiyla ayni.
- Bu nedenle ham secim PNG ile buyuk fark tek basina yeni bir hata kaniti degil; mevcut canli dosya zaten final-preserve-old uretilmis staging setle ayni.
- Rollback sonrasi `dual_source_rgb_presence` audit tekrar calistirildiginda:
  - `source_origin=both` satirlarindan canli haritada iki kaynaktan piksel tasiyan RGB sayisi `5`
  - farkli isimli canli both-source RGB sayisi `0`
- Bu da su anki canli dosyada eski `13` vakalik automated split onarimindan sonra gorulen tipte bir "both-source different-name" durumunun artik ayni sekilde yeniden uretilemedigini gosterdi.
- Bunun uzerine kullanicinin ozellikle isaret ettigi RGB'ler icin komponent analizi yapildi:
  - rapor klasoru: `Works/analysis/generated/provinces_rgb_components`
  - `135,36,34` raporu: `rgb_135_36_34_components.md/csv`
  - `9,27,160` raporu: `rgb_9_27_160_components.md/csv`
  - `177,24,32` raporu: `rgb_177_24_32_components.md/csv`
  - `93,48,36` raporu: `rgb_93_48_36_components.md/csv`
- Cok onemli bulgu:
  - `135,36,34` canli haritada `2` ayri komponentte gorunuyor:
    - buyuk komponent bbox: `6177,1325 -> 6486,1558`, `37391` piksel
    - kucuk komponent bbox: `1584,1171 -> 1616,1201`, `631` piksel
  - `9,27,160` da `2` komponent:
    - buyuk: `5976,1388 -> 6425,1723`, `78171` piksel
    - kucuk: `1348,1256 -> 1371,1277`, `357` piksel
  - `177,24,32` da `2` komponent:
    - buyuk: `7467,1461 -> 7511,1491`, `887` piksel
    - kucuk: `1259,1405 -> 1276,1418`, `185` piksel
  - `93,48,36` da `2` komponent:
    - buyuk: `7423,2424 -> 7462,2530`, `1757` piksel
    - kucuk: `1473,1546 -> 1497,1570`, `397` piksel
- Bu, kullanicinin "ayni RGB canli haritada duplicate/dagilmis durumda" suphelerini destekleyen objective kanittir.
- Ancak su noktada hala dikkat edilmesi gereken sey:
  - bu komponent bulgusu, hangi komponentin hangi province kimligine ait oldugunu tek basina ispatlamaz
  - fakat ayni RGB'nin haritada iki cok uzak bolgede yasadigini gosterdigi icin province-level kontrollu split/recolor ihtiyacini guclu sekilde destekler
- Bu nedenle artik toplu otomatik split yerine daha guvenli sonraki yol:
  - tek RGB
  - tek karar
  - koordinat/bbox kontrollu
  - her adimdan sonra görsel dogrulama

## 2026-04-13 - source PNG + subset definition tabanli overlap/conflict audit

- Kullanici yeni karar yontemini netlestirdi:
  - `provinces_modlu_kalan.png` icindeki yasayan RGB'ler alinacak
  - `provinces_orijinal_dogu.png` icindeki yasayan RGB'ler alinacak
  - ortak RGB'ler bulunacak
  - her ortak RGB icin ilgili subset definition dosyasindan province `id`si cekilecek
  - `same RGB + same ID = sorun yok`
  - `same RGB + different ID = gercek conflict`
- Bu kural artik authoritative conflict tespit yontemi olarak kabul edildi.
- Bu turda canli `map_data` dosyalarina dokunulmadi; sadece audit ve karar-sablonu uretildi.
- Yeni script:
  - `Works/tools/build_source_rgb_overlap_audit.ps1`
- Script once source PNG'leri tarayip her RGB icin:
  - `pixel_count`
  - `bbox`
  - ilgili subset definition'daki `source_id`
  - `source_name`
  topladi.
- Sonra su dosyalari urett i:
  - `Works/analysis/generated/source_rgb_overlap_audit/modlu_kalan_rgb_inventory_from_png.csv`
  - `Works/analysis/generated/source_rgb_overlap_audit/orijinal_dogu_rgb_inventory_from_png.csv`
  - `Works/analysis/generated/source_rgb_overlap_audit/source_rgb_overlap_same_id.csv`
  - `Works/analysis/generated/source_rgb_overlap_audit/source_rgb_overlap_conflicts.csv`
  - `Works/analysis/generated/source_rgb_overlap_audit/source_rgb_overlap_conflict_decisions.csv`
  - `Works/analysis/generated/source_rgb_overlap_audit/source_rgb_overlap_summary.md`
- Ilk calistirmada absurt unique RGB sayilari cikti. Bunun sebebi yeni image-analysis araclarinda `Graphics.DrawImageUnscaled` ile clone yapilmasi olabilir diye tespit edildi.
- Bu yuzden su araclarda piksel yolu guvenli `original.Clone(..., Format32bppArgb)` seklinde duzeltildi:
  - `Works/tools/build_source_rgb_overlap_audit.ps1`
  - `Works/tools/audit_dual_source_rgb_in_final_map.ps1`
  - `Works/tools/build_dual_source_conflict_diagnostics.ps1`
  - `Works/tools/compare_live_provinces_to_source_split.ps1`
  - `Works/tools/analyze_rgb_components_in_provinces.ps1`
- Duzenleme sonrasi source-overlap audit sonucu:
  - `modlu_kalan` unique non-black RGB: `9891`
  - `orijinal_dogu` unique non-black RGB: `3391`
  - ortak RGB: `140`
  - `same RGB + same ID`: `21`
  - `same RGB + different ID`: `119`
  - definition'da bulunamayan source PNG RGB: `0`
- Yani onceki `119` conflict sayisi, kullanicinin istedigi yontemle tekrar dogrulandi.
- Benign grup:
  - `21` satir `same RGB + same ID`
  - bunlarin `15` tanesinde isim farkli ama ID ayni
  - kullanicinin koydugu kurala gore bunlar conflict DEGIL
  - ornek: `135,36,34`
    - modlu: `9668 Crivitz`
    - orijinal: `9668 IMPASSABLE CENTRAL GOBI 3`
    - source PNG + source definition yontemine gore `same ID`, dolayisiyla benign kabul edilir
- Bu benign ama isim-farkli grup metadata acisindan ilginc olabilir, ancak conflict karari degistirmez.
- Gercek conflict grubu authoritative dosya:
  - `Works/analysis/generated/source_rgb_overlap_audit/source_rgb_overlap_conflicts.csv`
- Bir sonraki karar/uygulama icin kullanilacak sablon:
  - `Works/analysis/generated/source_rgb_overlap_audit/source_rgb_overlap_conflict_decisions.csv`
  - kolonlar:
    - `rgb`
    - `modlu_id`
    - `modlu_name`
    - `modlu_pixel_count`
    - `modlu_bbox`
    - `orijinal_id`
    - `orijinal_name`
    - `orijinal_pixel_count`
    - `orijinal_bbox`
    - `keep_rgb_source`
    - `recolor_source`
    - `new_rgb`
    - `decision_notes`
- Bu noktadan sonra conflict cozumunde bbox/pixel_count bilgisi sadece karar yardimcisi olacak; conflict'in varligi veya yoklugu artik source PNG + source definition ID karsilastirmasindan belirlenecek.

## 2026-04-13 - source default.map + source landed_titles semantic audit

- Kullanici `same_name` bilgisinin tek basina yetersiz oldugunu netlestirdi.
- Bundan sonra overlap/conflict semantigi icin yalnizca isim degil, su source kanitlari da kullanilacak:
  - source `default.map` sinifi
    - `sea_zones`
    - `river_provinces`
    - `lakes`
    - `impassable_mountains`
    - `impassable_seas`
    - veya `none`
  - source `common/landed_titles` tanimi
    - tanimli mi
    - tanimliysa hangi `b_*`
    - hangi `c_*`
    - gerekiyorsa ust zincir (`d_*`, `k_*`, `e_*`)
- Kullanici ayrica modun canli dosyalari degistirildigi icin mod source okunurken artik su klasor authoritative kabul edilecek bilgisini verdi:
  - `C:\Program Files (x86)\Steam\steamapps\workshop\content\1158310\2216670956\0backup`
- Buna gore semantic audit'te:
  - mod source = `0backup`
  - orijinal source = vanilla oyun dosyalari
- Yeni script:
  - `Works/tools/build_source_semantic_overlap_audit.ps1`
- Yeni cikt i dosyalari:
  - `Works/analysis/generated/source_semantic_overlap_audit/source_rgb_overlap_semantic_audit.csv`
  - `Works/analysis/generated/source_semantic_overlap_audit/source_rgb_overlap_semantic_decisions.csv`
  - `Works/analysis/generated/source_semantic_overlap_audit/source_rgb_overlap_semantic_summary.md`
  - `Works/analysis/generated/source_semantic_overlap_audit/source_rgb_overlap_semantic_class_counts.csv`
- Bu turda canli `map_data`, `default.map` veya `landed_titles` dosyalarina dokunulmadi.
- Semantic audit toplam ortak RGB seti uzerinde calisti:
  - toplam ortak RGB satiri: `140`
  - `same RGB + same ID`: `21`
  - `same RGB + different ID`: `119`
  - `same RGB + same ID + different name`: `15`
- Semantic suggestion dagilimi:
  - `Review`: `81`
  - `False`: `58`
  - `True`: `1`
- Semantic classification dagilimi:
  - `unclassified_review`: `76`
  - `barony_vs_nonbarony`: `54`
  - `same_noncounty_default_class_review`: `5`
  - `different_barony`: `2`
  - `different_default_map_class`: `2`
  - `same_barony`: `1`
- Yeni semantic kural:
  - source PNG + subset definition audit'i halen temel yapisal overlap tespitidir
  - ama artik `same RGB + same ID` satirlari otomatik olarak "guvenli/benign" sayilmayacak
  - once source `default.map` ve source `landed_titles` semantigiyle ikinci bir kontrol daha yapilacak
- Ozellikle su vakalar semantik olarak art ik problemli goruluyor:
  - `135,36,34`
    - mod source: `9668 Crivitz`
    - mod source landed title: `b_wismar`, `c_schwerin`
    - orijinal source: `9668 IMPASSABLE CENTRAL GOBI 3`
    - orijinal source default.map sinifi: `impassable_mountains`
    - semantic sonuc: `barony_vs_nonbarony`
    - onerilen eylem: `new_rgb_needed`
  - `177,24,32`
    - mod source: `9664 Stablo`
    - mod source landed title: `b_stablo`, `c_liege`
    - orijinal source: `9664 PLACEHOLDER_REGION_KOREA`
    - orijinal source default.map sinifi: `impassable_mountains`
    - semantic sonuc: `barony_vs_nonbarony`
    - onerilen eylem: `new_rgb_needed`
  - `9,27,160`
    - mod source: `9665 Laar`
    - mod source landed title: `b_laar`, `c_bentheim`
    - orijinal source: `9665 IMPASSABLE CENTRAL GOBI 1`
    - orijinal source default.map sinifi: `impassable_mountains`
    - semantic sonuc: `barony_vs_nonbarony`
    - onerilen eylem: `new_rgb_needed`
- Bu nedenle bundan sonraki karar modeli su olacak:
  - 1. source PNG + subset definition ile overlap/id yapisi bulunur
  - 1. source `default.map` + source `landed_titles` ile semantic anlam kontrol edilir
  - 1. ancak ondan sonra `keep_single_identity` mi yoksa `new_rgb_needed` mi karar verilir
- Semantic karar dosyasi bir tur daha ileri goturuldu:
  - `Works/analysis/generated/source_semantic_overlap_audit/source_rgb_overlap_semantic_decisions.csv`
  - artik `auto_keep_rgb_source`, `auto_recolor_source`, `auto_requires_new_rgb`, `auto_final_action`, `auto_decision_confidence`, `auto_decision_notes` kolonlarini da tasiyor
- Bu turda otomatik karar verilebilen satir sayisi:
  - `59`
  - manual review kalan satir:
  - `81`
- Otomatik karar kurallari:
  - `same_barony`:
    - `keep_single_identity`
    - recolor yok
  - `barony_vs_nonbarony`:
    - barony olan tarafin RGB'si korunur
    - nonbarony taraf recolor olur
  - `different_default_map_class`:
    - `navigable_water` tarafi korunur
    - `impassable` taraf recolor olur
  - `different_barony`:
    - iki taraf da barony ise buyuk piksel alani korunur
    - diger taraf recolor olur
- Otomatik karar dagilimi:
  - `56` satir:
    - `keep modlu`
    - `recolor orijinal`
  - `2` satir:
    - `keep orijinal`
    - `recolor modlu`
  - `1` satir:
    - `keep_single_identity`
- Kritik orneklerde otomatik karar:
  - `135,36,34`
    - `keep modlu`
    - `recolor orijinal`
  - `177,24,32`
    - `keep modlu`
    - `recolor orijinal`
  - `9,27,160`
    - `keep modlu`
    - `recolor orijinal`
  - `134,78,44`
    - `keep orijinal`
    - `recolor modlu`
    - neden: `sea_zones` tarafi, `impassable_seas` tarafina gore korunuyor
  - `178,192,2`
    - `keep modlu`
    - `recolor orijinal`
    - neden: `river_provinces` tarafi, `impassable_mountains` tarafina gore korunuyor
- Otomatik semantic kararlar icin yeni RGB atama dosyasi uretildi:
  - `Works/tools/build_source_semantic_rgb_assignments.ps1`
  - `Works/analysis/generated/source_semantic_overlap_audit/source_rgb_overlap_auto_rgb_assignments.csv`
  - `Works/analysis/generated/source_semantic_overlap_audit/source_rgb_overlap_auto_rgb_assignments_summary.md`
- Bu dosya:
  - sadece `auto_final_action = new_rgb_needed` olan `58` satiri kapsar
  - `keep_rgb_source`
  - `recolor_source`
  - `recolor_source_id`
  - `recolor_source_name`
  - `new_rgb`
  kolonlarini authoritative sekilde tasir
- Yeni RGB havuzu secilirken kullanilan occupied color uzayi:
  - canli `map_data/definition.csv`
  - `Works/map_data_sources/definition_modlu.csv`
  - `Works/map_data_sources/definition_orijinal.csv`
  - mevcut overlap satirlarinin kendi shared old RGB'leri
- Uretilen assignment sonucu:
  - toplam new RGB atanmis satir: `58`
  - `recolor modlu`: `2`
  - `recolor orijinal`: `56`
  - yeni RGB duplicate: `0`
  - mevcut color uzayiyla collision: `0`
- Kritik atama ornekleri:
  - `135,36,34`
    - `keep modlu`
    - `recolor orijinal`
    - `new_rgb = 1,5,32`
  - `177,24,32`
    - `keep modlu`
    - `recolor orijinal`
    - `new_rgb = 1,5,29`
  - `9,27,160`
    - `keep modlu`
    - `recolor orijinal`
    - `new_rgb = 1,5,30`
  - `134,78,44`
    - `keep orijinal`
    - `recolor modlu`
    - `new_rgb = 1,5,27`
- Bu otomatik semantic RGB atama katmaninin ustune staging uygulama turevi kuruldu:
  - `Works/tools/build_source_semantic_staging_fix.ps1`
  - amaci:
    - canli `map_data` dosyalarina dokunmadan
    - semantic overlap icin staging `provinces.png + definition.csv` uretmek
    - keep-source tarafini old/shared RGB'ye geri zorlamak
    - recolor-source tarafini `new_rgb` ile boyamak
    - `same_id` semantic conflictlerde placeholder ID ve placeholder piksel repurpose ederek yeni final kimlik yaratmak
- Bu scriptin girdileri:
  - `map_data/provinces.png`
  - `map_data/definition.csv`
  - `Works/map_data_sources/provinces_modlu_kalan.png`
  - `Works/map_data_sources/provinces_orijinal_dogu.png`
  - `Works/analysis/generated/source_semantic_overlap_audit/source_rgb_overlap_auto_rgb_assignments.csv`
  - `Works/analysis/generated/final_modlu_tracking_preserve_old_ids.csv`
  - `Works/analysis/generated/final_orijinal_tracking_preserve_old_ids.csv`
  - `Works/analysis/generated/final_placeholder_inventory_preserve_old_ids.csv`
  - `Works/analysis/generated/placeholder_pixel_map_preserve_old.csv`
- Bu scriptin urettigi staging ciktilar:
  - `Works/analysis/generated/source_semantic_staging_fix/provinces_source_semantic_staging.png`
  - `Works/analysis/generated/source_semantic_staging_fix/definition_source_semantic_staging.csv`
  - `Works/analysis/generated/source_semantic_staging_fix/source_semantic_staging_image_apply_report.csv`
  - `Works/analysis/generated/source_semantic_staging_fix/source_semantic_same_id_split_id_assignments.csv`
  - `Works/analysis/generated/source_semantic_staging_fix/source_semantic_staging_definition_changes.csv`
  - `Works/analysis/generated/source_semantic_staging_fix/source_semantic_staging_fix_summary.md`
- Staging uygulama sonucu:
  - toplam semantic assignment: `58`
  - `same_id` split: `15`
  - `different_id` recolor: `43`
  - kullanilan placeholder ID sayisi: `15`
  - kullanilan placeholder ID araligi: `12773..12787`
  - region apply rapor satiri: `116`
  - placeholder pixel repurpose satiri: `15`
  - staging definition duplicate RGB sayisi (`0,0,0` disi): `0`
  - recolor satirlarinda gercekten piksel degisen assignment: `58/58`
  - toplam recolor edilen piksel: `180178`
- `same_id` semantic split mantigi:
  - keep-source taraf mevcut merged final ID'de kalir
  - recolor-source taraf placeholder final ID'ye tasinir
  - ilgili gizli teknik placeholder pikseli de ayni `new_rgb` ile boyanir
  - boylece yeni split province hem gercek bolgesini hem de teknik kimlik pikselini kazanir
- Bu tur sadece staging uretir; canli `map_data/provinces.png` ve `map_data/definition.csv` henuz bu semantic split ile degistirilmedi
- `134,78,44 / 8688 / sea_bay_of_bengal` vakasi uzerinden yeni bir false-positive sinifi tespit edildi:
  - mod kaynaginda:
    - `8688;134;78;44;sea_bay_of_bengal`
    - `default.map` sinifi: `impassable_seas`
  - orijinal kaynaginda:
    - `8688;134;78;44;sea_bay_of_bengal`
    - `default.map` sinifi: `sea_zones`
  - ilk semantic kural bunu sadece `different_default_map_class` gorup yanlis sekilde `new_rgb_needed` demisti
  - kullanici itiraziyla bu kural daraltildi
- Yeni semantic kural:
  - `same_id + same_name + nonbarony + structured nonland/water default.map class`
  - tek basina split sebebi degildir
  - bu durum:
    - `semantic_same_province_suggest = True`
    - `semantic_classification = same_id_same_name_nonbarony_nonland`
    - `final_action = keep_single_identity`
  olarak ele alinacak
- Bu kural `Works/tools/build_source_semantic_overlap_audit.ps1` icine gomuldu; amac sadece `8688`i elle kapatmak degil, benzer water/nonland false-positive vakalarin tekrar etmesini onlemek
- Bu kuraldan sonra semantic karar zinciri yeniden uretildi:
  - `Works/tools/build_source_semantic_overlap_audit.ps1`
  - `Works/tools/build_source_semantic_rgb_assignments.ps1`
  - `Works/tools/build_source_semantic_staging_fix.ps1`
- Guncel authoritative sayilar:
  - otomatik `new_rgb` assignment: `57`
  - `recolor modlu`: `1`
  - `recolor orijinal`: `56`
  - staging assignment satiri: `57`
  - `same_id` split: `14`
  - `different_id` recolor: `43`
  - kullanilan placeholder id: `14`
  - staging definition duplicate RGB (`0,0,0` disi): `0`
- Bu yeniden uretimle:
  - `134,78,44` artik `source_rgb_overlap_auto_rgb_assignments.csv` icinde yer almiyor
  - `provinces_source_semantic_staging.png` icinde bu vaka icin ekstra `new_rgb` atanmiyor
  - staging split placeholder tuketimi `15 -> 14` dustu
- Semantic staging zincirinden sonra test paketi icin uygulama katmani kuruldu:
  - `Works/tools/apply_source_semantic_staging_to_test_files.ps1`
- Bu script:
  - staging `provinces_source_semantic_staging.png` dosyasini `test_files/map_data/provinces.png` olarak kopyalar
  - staging `definition_source_semantic_staging.csv` dosyasini `test_files/map_data/definition.csv` olarak kopyalar
  - same_id split assignment'lardan gelen nonland/default.map ihtiyaclarini `test_files/map_data/default.map` icine yorumlu blok olarak ekler
  - gerekiyorsa `test_files/common/landed_titles/00_landed_titles.txt` icinde barony `province = ...` baglarini yeni split ID'lere rewrite eder
- Bu turdaki test paketi sonucu:
  - guncellenen test dosyalari:
    - `test_files/map_data/provinces.png`
    - `test_files/map_data/definition.csv`
    - `test_files/map_data/default.map`
    - `test_files/common/landed_titles/00_landed_titles.txt`
  - same_id split `default.map` ekleme satiri: `7`
  - same_id split `landed_titles` relink satiri: `0`
  - test `default.map` icine su blok eklendi:
    - `# SOURCE SEMANTIC SAME-ID SPLITS BEGIN`
    - `impassable_mountains = LIST { 12774 12775 12776 12778 12779 12784 12786 }`
    - `# SOURCE SEMANTIC SAME-ID SPLITS END`
- Bu uygulamanin raporlari:
  - `Works/analysis/generated/source_semantic_test_package/source_semantic_test_package_summary.md`
  - `Works/analysis/generated/source_semantic_test_package/source_semantic_test_default_map_additions.csv`
  - `Works/analysis/generated/source_semantic_test_package/source_semantic_test_landed_title_relinks.csv`
- Yorum:
  - bu same_id split grubunda landed_titles tarafina yeni province ID rewrite gerektiren bir recolor-source barony bulunmadi; bu yuzden relink sayisi `0`
  - test paketi artik semantic staging map ve definition ile senkron durumdadir; sonraki dogal adim yeni test crash/log almaktir
- Sonraki crash ile birlikte somut blocker olarak su netlesti:
  - same_id semantic splitlerden gelen `impassable_mountains` yeni ID'leri test `default.map`e eklenmisti
  - ama eski split oncesi ID'ler vanilla-east impassable blokta kaldigi icin ayni `17` barony hala impassable province'e bagli gorunuyordu
  - bu yuzden `default.map` test uygulama scripti tekrar duzeltildi
- `Works/tools/apply_source_semantic_staging_to_test_files.ps1` guncellendi:
  - artik `default.map`e ayri ek blok yazmiyor
  - bunun yerine `# VANILLA EAST DEFAULT MAP BEGIN/END` blogunu parse edip yeniden yaziyor
  - same_id splitlerde:
    - eski `old_id` ilgili default.map sinifindan siliniyor
    - yeni `final_new_id` ayni sinifa ekleniyor
- Bu duzeltmeden sonra test `default.map` durumu:
  - `9664, 9665, 9666, 9668, 9671, 9672` eski impassable ID'leri bloktan temizlendi
  - yeni split ID'ler vanilla-east impassable blok icinde yasiyor:
    - `12774`
    - `12775`
    - `12776`
    - `12778`
    - `12779`
    - `12784`
    - `12786`
  - eski `# SOURCE SEMANTIC SAME-ID SPLITS` ek blogu kaldirildi; authoritative yer artik vanilla-east blok rewrite'i
- Bu adimin ozel raporu:
  - `Works/analysis/generated/source_semantic_test_package/source_semantic_test_default_map_additions.csv`
  - burada `old_id -> final_new_id` default.map rewrite satirlari authoritative olarak tutuluyor
- Bu adimdan sonra `test_files` paketindeki bir sonraki dogru adim:
  - yeniden oyun testi alip ayni `17 impassable barony` hatasinin dusup dusmedigine bakmak
- Sonraki testte oyun crash vermeden acildi; bu calisan durum referans kabul edildi
- Crash'i cozen pratik fark, `test_files/common/landed_titles/00_landed_titles.txt` icindeki legacy `_china` bloklarinin temizlenmesiyle birlikte `test_files` paketinin butun olarak stabil hale gelmesiydi
- Bunun ardindan calisan `test_files` seti canli dosyalara terfi edildi:
  - `test_files/common/landed_titles/00_landed_titles.txt` -> `common/landed_titles/00_landed_titles.txt`
  - `test_files/map_data/default.map` -> `map_data/default.map`
  - `test_files/map_data/definition.csv` -> `map_data/definition.csv`
  - `test_files/map_data/provinces.png` -> `map_data/provinces.png`
- Terfi sonrasi dogrulama:
  - `common/landed_titles/00_landed_titles.txt`, `map_data/default.map`, `map_data/definition.csv` ile `test_files` kopyalari birebir senkron
  - `map_data/provinces.png` hash'i ile `test_files/map_data/provinces.png` hash'i birebir ayni
- Bundan sonraki dogru asama:
  - crashsiz acilisin guncel `error.log`unu ayirip sadece kalan gercek hata/temizlik maddelerine odaklanmak
- Bu crashsiz acilisin sonraki ana log ailesi incelendi:
  - `C:\Users\bsgho\Documents\Paradox Interactive\Crusader Kings III\logs\error.log`
  - satir araligi `339249-340242`
  - hata ailesi: `Province '<id>' has no associated title in common/landed_titles`
- Bu aile icin kaynak-provenance raporu uretildi:
  - script: `Works/tools/build_missing_landed_title_source_cluster_report.ps1`
  - ciktilar:
    - `Works/analysis/generated/missing_landed_title_source_cluster/missing_landed_titles_source_detail.csv`
    - `Works/analysis/generated/missing_landed_title_source_cluster/missing_landed_titles_source_by_root.csv`
    - `Works/analysis/generated/missing_landed_title_source_cluster/missing_landed_titles_source_by_subtree.csv`
    - `Works/analysis/generated/missing_landed_title_source_cluster/missing_landed_titles_source_summary.md`
- Bu raporun net sonucu:
  - `994` eksik live province tamamen source old_id ve landed_titles hiyerarsisine baglandi
  - `missing_source_binding = 0`
  - `missing_final_master/source_old_id = 0`
  - yani bu ailede bilinmeyen veya eslesmeyen province kalmadi
- En buyuk root kumeleri:
  - `modlu_kalan / e_tibet` -> `285`
  - `orijinal_dogu / e_andong` -> `249`
  - `orijinal_dogu / e_srivijaya` -> `159`
  - `orijinal_dogu / e_amur` -> `129`
  - `modlu_kalan / e_qixi` -> `101`
  - `modlu_kalan / e_xi_xia` -> `61`
- Operasyonel yorum:
  - sorun artik tekil province degil; eksik `landed_titles` subtree/root coverage problemi
  - `e_andong`, `e_srivijaya`, `e_amur`, `e_qixi`, `e_xi_xia` gibi koklerin veya alt-duchy bloklarinin canli `common/landed_titles/00_landed_titles.txt` icinde eksik oldugu sayisal olarak kanitlandi
  - `e_tibet` icinde ise root mevcut olsa da bazi alt-subtree/county/barony coverage'i eksik
- Sonraki dogru adim:
  - bu rapordaki `by_subtree` kumelerine gore eksik landed_titles subtree'lerini source dosyalardan geri almak
  - oncelik sirasi: `e_tibet`, `e_andong`, `e_srivijaya`, `e_amur`, `e_qixi`, `e_xi_xia`
- Canli `common/landed_titles/00_landed_titles.txt` icine ilk buyuk coverage geri yuklemesi uygulandi:
  - script: `Works/tools/restore_missing_landed_title_roots.ps1`
  - bu turda sadece tam eksik `5` root geri alindi:
    - `e_andong`
    - `e_srivijaya`
    - `e_amur`
    - `e_qixi`
    - `e_xi_xia`
  - source provenance:
    - `e_andong`, `e_srivijaya`, `e_amur` -> vanilla `00_landed_titles.txt`
    - `e_qixi`, `e_xi_xia` -> mod `0backup\common\landed_titles\00_landed_titles.txt`
  - province ID'ler source old_id -> final_new_id olarak rewrite edildi
- Bu uygulamanin raporlari:
  - `Works/analysis/generated/missing_landed_title_restore_roots/restored_missing_landed_title_roots_rewrite_report.csv`
  - `Works/analysis/generated/missing_landed_title_restore_roots/restored_missing_landed_title_roots_summary.csv`
  - `Works/analysis/generated/missing_landed_title_restore_roots/restored_missing_landed_title_roots_summary.md`
- Root bazli rewrite sonucu:
  - `e_andong` -> rewritten `321`
  - `e_srivijaya` -> rewritten `162`
  - `e_amur` -> rewritten `130`
  - `e_qixi` -> rewritten `99`
  - `e_xi_xia` -> rewritten `61`, fallback `16`, removed `36`
- Ardindan `Works/tools/build_missing_landed_title_source_cluster_report.ps1` yeniden calistirildi ve eski `994` province listesinin canli landed_titles kapsami tekrar olculdu
- Guncel canli coverage sonucu:
  - toplam eski eksik liste: `994`
  - simdi canlida tanimli olanlar: `699`
  - hala tanimsiz kalanlar: `295`
- Kalan tanimsizlarin dagilimi:
  - `e_tibet` -> `285`
  - `e_yongliang` -> `8`
  - `e_bengal` -> `1`
  - `e_wendish_empire` -> `1`
- Bu, ilk buyuk root geri yuklemesinin dogrudan `699` province coverage kazandirdigini kanitladi
- Sonraki en dogru adim:
  - `e_tibet` icindeki eksik subtree/county/barony coverage'ini tamamlamak
  - ilk oncelikli alt kumeler:
    - `d_lhasa` `16`
    - `d_nagormo` `15`
    - `d_ngari` `14`
    - `d_qamdo` `14`
    - `d_tuyuhun` `14`
- Kullanici yeni bir is akisi tercihi verdi:
  - `landed_titles` gibi degisiklikler yapildiginda `test_files` kopyasi da ayni turda guncel tutulmali
  - sebep: kullanici dosyalari cogu zaman `test_files` icinden temin ediyor
- `Works/tools/restore_missing_landed_title_roots.ps1` buna gore genislestirildi:
  - artik ciktiyi hem
    - `common/landed_titles/00_landed_titles.txt`
    - `test_files/common/landed_titles/00_landed_titles.txt`
    dosyalarina yazar
  - restore kapsami da su rootleri icerecek sekilde buyutuldu:
    - `e_bengal`
    - `e_tibet`
    - `e_yongliang`
    - `e_wendish_empire`
- `2026-04-15` crash klasoru `C:\Users\bsgho\Documents\Paradox Interactive\Crusader Kings III\crashes\ck3_20260415_002257` icin yeni landed_titles incelemesi yapildi
- Crash deseni:
  - `logs/error.log` sonundaki baskin hata ailesi `Province with no county data`
  - kumelenen rootler:
    - `e_tibet` -> `282`
    - `e_yongliang` -> `8`
    - `e_bengal` -> `1`
    - `e_wendish_empire` -> `1`
    - `e_xi_xia` -> `1`
- Yeni net bulgu:
  - asıl sorun sadece eksik root coverage degil, onceki `landed_titles` degisikliklerinde iki buyuk yapisal brace kaymasi da varmis
  - `e_bengal` rootu `h_india` icine yanlislikla gomulmus durumdaydi
  - eski `e_yongliang` rootu da `h_china` icine yanlislikla gomulmus durumdaydi
  - bu yuzden bu rootler gercek top-level blok olarak davranmiyordu
- Yapilan duzeltmeler:
  - `common/landed_titles/00_landed_titles.txt`
  - `test_files/common/landed_titles/00_landed_titles.txt`
  icinde:
    - `h_india -> e_bengal` sinirinda eksik kapanis dogru yere tasindi
    - `h_china -> e_yongliang` sinirinda eksik kapanis dogru yere tasindi
  - ardindan `restore_missing_landed_title_roots.ps1` tekrar calistirildi ve restore edilen rootler temiz top-level olarak yeniden basildi
- Son dogrulama:
  - hedef rootlerin hepsi `depth_before=0` olacak sekilde top-level hale geldi
  - dosya genel brace dengesi `final_depth=0`
  - crash logdaki `Province with no county data` listesinden taninabilen `295` province adinin `294`u artik landed_titles icinde bagli
  - kalan tek artik isim:
    - `CirQF_Langxinguan` (`final id 12356`)
  - bu artik `h_china` tarafindan geliyor; ana Tibet/Yongliang kaynakli crash zinciri ise landed_titles yapisal olarak kapatildi
- `2026-04-15` mevcut `logs/error.log` icinde crash olmadan kalan `Province 'X' has no associated title in common/landed_titles` blogu icin yeni landed_titles onarimi yapildi
- Bu turda duzeltilen exact eksikler:
  - `e_tibet`
    - `b_karub` -> `9301`
    - `c_deqen` icindeki `b_deqen` -> `9316`
    - `c_deqen` icindeki `b_balung` -> `9317`
  - `e_bengal`
    - `c_charaideo` icine `b_patkai` -> `10488`
  - `e_yongliang`
    - minimal `k_longxi_china -> d_shanzhou -> c_hezhou_china`
    - `b_hezhou_longyou_china` -> `12916`
    - `b_binglingsi_china` -> `12965`
  - `e_xi_xia`
    - minimal `d_guiyi -> c_subei -> b_ngor` -> `9408`
    - minimal `d_aksay -> c_aksay/c_haltang`
    - `9470/9471/9472/9469` baglari geri geldi
  - `e_andong`
    - vanilla `e_andong` blogundan sadece o anki error.log'da eksik kalan subtree'ler parcali olarak geri getirildi
    - province rewrite barony bazinda `missing_landed_titles_source_detail.csv` icindeki `final_new_id` degerlerine gore yapildi
    - boylece `k_balhae`, `k_luzhen`, `k_raole`, `k_shiwei` ve onlara bagli eksik county/barony zinciri geri geldi
- Bu tur sonunda yerel landed_titles dogrulamasi:
  - error.log'daki ayni setten okunan `260` missing province id'nin `260/260`i artik landed_titles icinde bagli
  - duplicate province assignment `0`
  - dosya brace dengesi `final_depth=0`
  - `common/landed_titles/00_landed_titles.txt` ile `test_files/common/landed_titles/00_landed_titles.txt` birebir ayni tutuldu
- `2026-04-15` canonical title mapping sistemi eklendi
- Yeni source-of-truth:
  - `Works/map_data_sources/title_relation_master.csv`
- Yeni tool'lar:
  - `Works/tools/build_title_relation_master.ps1`
  - `Works/tools/build_title_relation_outputs.ps1`
- Alinan karar:
  - canonical namespace `mod title id`
  - mapping sadece `vanilla -> mod`
  - `exact/contextual` olmayanlar otomatik rewrite edilmez
  - savunulabilir karsiligi olmayanlar `manual_review` olarak kalir
- Seed sonucu:
  - source inventory `3776`
  - mapped `3764`
  - manual review `12`
  - contextual auto-map `0`
  - safe rewrite row `0`
  - scan edilen hedef dosyalarda rewrite candidate hit `0`
- Bu su anlama geliyor:
  - repo taranan alanlarda zaten agirlikli olarak canonical mod title id'lerini kullaniyor
  - mapping sistemi su an daha cok coverage/validation/manual review katmani olarak devrede
- Mevcut `manual_review` listesi:
  - `e_andong`: `k_khitan`, `d_LIAO_linhuang`, `d_LIAO_shangjing`, `d_LIAO_zhongjing`, `d_yanyun_yuyi`
  - `e_goryeo`: `b_Goryeo_Bukgye_Maengju`, `b_Goryeo_Donggye_Deungju`, `b_Goryeo_Donggye_Hwaju`, `b_Goryeo_Donggye_Uiju`, `b_Goryeo_Donggye_Myeongju`
  - `e_srivijaya`: `b_siantan`, `b_muot`
- Generated raporlar:
  - `Works/analysis/generated/title_relation_mapping/title_relation_source_inventory.csv`
  - `Works/analysis/generated/title_relation_mapping/title_relation_coverage.csv`
  - `Works/analysis/generated/title_relation_mapping/title_relation_manual_review.csv`
  - `Works/analysis/generated/title_relation_mapping/title_relation_reference_hits.csv`
  - `Works/analysis/generated/title_relation_mapping/title_relation_rewrite_candidates.csv`
  - `Works/analysis/generated/title_relation_mapping/title_relation_outputs_summary.md`
- Sonradan canonical mapping seed'inde yapisal bug bulundu ve duzeltildi
- Bug:
  - `build_title_relation_master.ps1` canonical `mod_title_id` havuzunu yanlislikla `common/landed_titles/00_landed_titles.txt` icindeki live hibrit dosyadan kuruyordu
  - bu da `c_zezhou -> c_zezhou` gibi, orijinal modda bulunmayan ama live dosyada bulunan yanlis `exact` eslesmeler uretiyordu
- Duzeltme:
  - canonical aday havuzu artik sadece orijinal mod kaynagindan geliyor:
    - `C:\Program Files (x86)\Steam\steamapps\workshop\content\1158310\2216670956\0backup\common\landed_titles\00_landed_titles.txt`
  - province set karsilastirmasi hem vanilla hem mod tarafinda `final_new_id` uzayina normalize edildi:
    - `final_orijinal_tracking_preserve_old_ids.csv`
    - `final_modlu_tracking_preserve_old_ids.csv`
- Sonuc:
  - hatali `same_title_id` false-positive'leri temizlendi
  - `c_zezhou` artik `c_zezhou` olarak maplenmiyor; `manual_review`
  - yeni seed sayilari:
    - source inventory `3776`
    - mapped `1118`
    - manual review `2658`
    - safe rewrite row `0`
- Yorum:
  - bu sayilar daha dusuk ama semantik olarak daha dogru
  - bundan sonraki ilerleme manual review veya daha akilli contextual heuristic ile olacak
- `2026-04-16` province-first review turu devam etti
- `e_goryeo` subtree probe:
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_goryeo_block_probe.csv`
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_goryeo_block_probe_summary.md`
  - sonuc:
    - `rows = 21`
    - `review:manual = 16`
    - `blocked:not_primary_target_source = 3`
    - `blocked:no_source_history = 2`
  - tum playable adaylar ya `e_japan` kokenliydi ya da guvenli source history tasimiyordu
  - bu turda `e_goryeo` icin savunulabilir manual promote yapilmadi
- Review araci komsu cluster secimi icin kullanildi:
  - `e_tibet`, `e_amur`, `e_bengal` block probe raporlari uretildi
  - en yuksek getirili cluster `e_tibet` gorundu
- `e_tibet` icinde bir manuel exact terfi yapildi:
  - `9283 Kagong -> 9283 Kagong`
  - gerekce:
    - source ve target ayni `id`
    - source ve target ayni ad
    - `target_source_count_all = 1`
    - `overlap_score = 1.0`
    - source history mevcut
  - `works/map_data_sources/province_relation_master.csv` satiri:
    - `classification = exact`
    - `status = mapped`
    - `apply_to_history = yes`
    - note: `manual: same_id_name_unique_target_overlap_1_0`
  - not:
    - mevcut live/test province history bloklari zaten orijinal mod source ile ayniydi
    - yani bu terfi semantik esitligi master tabloda resmilestirdi; history iceriginde fiili fark olusturmasi beklenmiyor
- `e_bengal` subtree probe acildi:
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_bengal_block_probe.csv`
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/e_bengal_block_probe_summary.md`
  - sonuc:
    - `rows = 151`
    - `ready:exact = 22`
    - `review:high_overlap = 3`
    - `review:manual = 33`
    - geri kalan buyuk kisim `blocked:not_primary_target_source` ve `blocked:shared_target_low_coverage`
- `e_bengal` icinde iki manuel exact terfi yapildi:
  - `9556 Ava -> 9556 Ava`
  - `9562 Minbu -> 9562 Minbu`
  - gerekce:
    - source ve target ayni `id`
    - source ve target ayni ad
    - `target_source_count_all = 1`
    - ikinci aday overlap'i marjinal kaldi
    - `overlap_score` sirasiyla `0.996656` ve `0.961702`
    - source history mevcut
  - `works/map_data_sources/province_relation_master.csv` satirlari:
    - `classification = exact`
    - `status = mapped`
    - `apply_to_history = yes`
    - note: `manual: same_id_name_unique_target_high_overlap`
- `11585 Khabaungkyo -> 9595 Swa` promote edilmedi
  - ayni guven seviyesinde degil; ad/id degisimi var ve semantik sapma riski daha yuksek
- `11585 Khabaungkyo -> 9595 Swa` icin sonraki inceleme sonucu:
  - backup `c_toungoo` icinde hem `b_khabaungkyo = 11585` hem `b_swa = 9595` var
  - current landed_titles `c_toungoo` ise sadece `9593/9594/9595` tasiyor ve `11585` artik doguda degil
  - province relation verisi gosteriyor ki:
    - source `11585 b_khabaungkyo` en guclu olarak current `9595`e oturuyor
    - source `9595 b_swa` ise current `9593`e oturuyor
  - yani burada basit rename degil, `c_toungoo` icinde barony slot yeniden dagitimi var
  - bu nedenle `11585 -> 9595` province-only exact promote edilmedi
  - not:
    - bu tip satirlar title/subtree migration asamasinda birlikte ele alinmali
- `c_toungoo` subtree probe uretildi:
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/c_toungoo_block_probe.csv`
  - `works/analysis/generated/province_relation_mapping/cluster_reviews/c_toungoo_block_probe_summary.md`
  - sonuc:
    - `rows = 9`
    - `review:high_overlap = 1`
    - `blocked:shared_target_low_coverage = 2`
    - `blocked:not_primary_target_source = 4`
    - `blocked:no_source_history = 2`
- `c_toungoo` icindeki barony shuffle yapisi:
  - source `11585 b_khabaungkyo` -> current `9595 b_swa` en guclu aday
  - source `9595 b_swa` -> current `9593 b_toungoo`
  - source `9593 b_toungoo` de current `9593 b_toungoo` uzerine yukleniyor
  - yani burada ayni county icinde province geometrisi ile aktif title slotlari birebir hizali degil
- karar:
  - `c_toungoo` icinde province-only promote yapilmadi
  - bu blok `title + province` birlikte ele alinacak subtree migration adayi olarak park edildi
- `2026-04-16` province manual review inventory araci eklendi:
  - `works/tools/build_province_manual_review_inventory.py`
- Uretilen raporlar:
  - `works/analysis/generated/province_relation_mapping/manual_review_inventory/province_manual_review_worklist.csv`
  - `works/analysis/generated/province_relation_mapping/manual_review_inventory/province_manual_review_root_summary.csv`
  - `works/analysis/generated/province_relation_mapping/manual_review_inventory/province_manual_review_summary.md`
  - `works/analysis/generated/province_relation_mapping/manual_review_inventory/province_probe_review_worklist.csv`
  - `works/analysis/generated/province_relation_mapping/manual_review_inventory/province_probe_summary.csv`
  - `works/analysis/generated/province_relation_mapping/manual_review_inventory/province_probe_summary.md`
- Bulgular:
  - master seviyesinde `manual_review` satirlarinin buyuk cogu hala `blocked:no_target_title`, yani dogrudan uygulanabilir backlog icin probe seviyesine bakmak daha dogru
  - probe bazli inventory sonucu:
    - `probe files = 11`
    - `unresolved probe rows = 1100`
    - `continue_exact_probe = 4`
    - `park = 7`
  - en verimli probe su an:
    - `e_srivijaya_pilot`
    - `rows = 264`
    - `high_overlap = 18`
    - `manual = 145`
  - sonra:
    - `e_bengal_block_probe`
    - `e_tibet_block_probe`
    - `c_toungoo_block_probe`
- Yorum:
  - bundan sonra province-only exact toplama icin en iyi hedef `e_srivijaya_pilot`
  - `c_toungoo_block_probe` ise exact backlogtan cok `subtree/title+province migration` backlogu olarak degerlendirilmeli
- Ek domain bilgisi:
  - `e_tibet` buyuk olcude moddan geliyor; sadece kucuk bir dogu parcasi vanilla ile yenilenmis
  - `e_bengal` de ayni sekilde buyuk olcude moddan geliyor; vanilla etkisi lokal
- Sonuc:
  - `e_tibet` ve `e_bengal` artik genel migration backlog'u gibi degil, `mod-canonical + kucuk vanilla cleanup` bloklari olarak ele alinacak
  - bu iki root icin full probe kovalamak yerine yalnizca vanilla kalan alt parcaya odaklanilacak
- `e_srivijaya_pilot` icin yeni manuel shortlist uretildi:
  - `works/analysis/generated/province_relation_mapping/manual_review_inventory/e_srivijaya_high_overlap_manual.csv`
  - `works/analysis/generated/province_relation_mapping/manual_review_inventory/e_srivijaya_high_overlap_manual.md`
- `e_srivijaya` sonucu:
  - `18` adet `review:high_overlap` satir var
  - bunlarin hicbiri province-only `exact` promote icin yeterince temiz degil
  - ortak ozellik:
    - neredeyse hepsi `merge`
    - overlap cok yuksek olsa da `target_coverage` dusuk
    - yani target province, source province'in basit birebir karsiligi degil; daha buyuk veya yeniden paketlenmis bir slot
- Kural:
  - `e_srivijaya` high-overlap satirlari bundan sonra `manual/contextual` backlog olarak tutulacak
  - otomatik `exact` promote ancak ayni `id/ad` veya daha sert kanit gelirse yapilacak
- `e_srivijaya` icinde yeni bir sert kanitli satir bulundu ve promote edildi:
  - `10401 Nicobar Islands -> 12849 Muot/Nancowry`
  - gerekce:
    - backup landed_titles icinde `b_nakkavaram = province 10401`
    - current landed_titles icinde ayni `b_nakkavaram = province 12849`
    - yani bu satir geometri dusuk gorunse de ayni barony yolunun yeni province id'ye tasinmis hali
    - current live history `12849` backup mod source ile farkliydi; bu nedenle promote fiili history duzeltmesi de sagliyor
  - `works/map_data_sources/province_relation_master.csv` satiri:
    - `classification = exact`
    - `status = mapped`
    - `apply_to_history = yes`
    - note: `manual: same_barony_path_id_reuse_to_current_target`
- `10401 -> 12849` uygulama sonucu:
  - `works/tools/apply_province_relation_history.ps1` calistirildi
  - live/test `history/provinces/00_MB_PROVINCES.txt` tekrar senkron kaldi
  - current `12849` history blogu artik backup mod source ile uyumlu:
    - `culture = aslian`
    - `religion = kadai`
    - `holding = tribal_holding`
  - validator temiz:
    - `validation errors = 0`
    - `validation warnings = 0`
    - `missing playable province titles = 0`
- `e_srivijaya_pilot` guncel durum:
  - `ready:exact = 3`
  - `review:manual = 54`
  - `blocked:not_primary_target_source = 88`
  - `blocked:shared_target_low_coverage = 20`
- `2026-04-16` strict `same_county_barony` exact harvest turu yapildi:
  - yeni promote edilen satirlar:
    - `8722 Karnaphuli -> 8722 Karnaphuli`
    - `9641 Singu -> 9641 Singu`
    - `9643 Takon -> 9643 Takon`
    - `9571 Yamethin -> 9571 Yamethin`
    - `828 Chatigama -> 828 Chatigama`
    - `9624 Kale -> 9624 Kale`
    - `11535 Taikkala -> 9630 Taikkala`
    - `9324 Lenggu -> 9324 Lenggu`
    - `9443 Jone -> 9443 Jone`
    - `9457 Choqu -> 9457 Choqu`
  - ortak promote gerekceleri:
    - ayni county/barony yolu veya ayni barony yolunun yeni province id'ye tasinmis olmasi
    - current target tarafinda dominant source olmalari
    - source history blogunun mevcut olmasi
  - `works/tools/apply_province_relation_history.ps1` her batch sonrasi tekrar calistirildi
  - `works/tools/validate_east_mapping_pipeline.ps1` her batch sonrasi temiz dondu
  - guncel apply sonucu:
    - `exact rows requested = 123`
    - `applied rows = 228`
    - `missing source blocks = 27`
  - guncel validator sonucu:
    - `validation errors = 0`
    - `validation warnings = 0`
    - `missing playable province titles = 0`
    - `landed_titles live/test hash match = yes`
  - live/test `history/provinces/00_MB_PROVINCES.txt` SHA256:
    - `A9AB084714B0340ED098FC3C3836955D9F79BE6B1C9AEF6BA890EBFD4B26356E`
  - probe durumlari:
    - `e_bengal_block_probe`: `ready:exact = 32`, `review:manual = 28`, `blocked:not_primary_target_source = 52`, `blocked:shared_target_low_coverage = 31`
    - `e_tibet_block_probe`: `ready:exact = 31`, `review:manual = 5`, `blocked:no_source_history = 4`
  - yorum:
    - `e_tibet` ve `e_bengal` icinde genel migration yerine `strict exact` hasadi verimli olmaya devam ediyor
    - `c_toungoo` benzeri shuffle/subtree vakalari ise hala province-only promote icin uygun degil
- Ayni tur icinde daha gevsek ama hala savunulabilir `province history` promote esikleri de uygulandi:
  - `same_county_barony_unique_target`:
    - `9317 Balung -> 9317 Balung`
    - `9328 Gyezil -> 9328 Gyezil`
    - `9445 Zhugqu -> 9445 Zhugqu`
    - `9551 Popa -> 9551 Popa`
  - `same_county_name_unique_target`:
    - `9561 Mekkhaya -> 9561 Mekkhaya`
    - `9625 Chin -> 9625 Chin`
  - `same_barony_name_unique_target`:
    - `9564 Ngape -> 9564 Ngape`
  - `same_id_name_dominant_self_target`:
    - `9557 Pinya -> 9557 Pinya`
    - `9568 Sagaing -> 9568 Sagaing`
    - `9590 Thayetmyo -> 9590 Thayetmyo`
    - `9599 Krapan -> 9599 Krapan`
    - `9622 Maukkadaw -> 9622 Maukkadaw`
    - `9628 Muttina -> 9628 Muttina`
    - `9638 Shwegyin -> 9638 Shwegyin`
    - `9639 Myinmu -> 9639 Myinmu`
  - `same_id_name_unique_target_high_coverage`:
    - `9658 Thaungdut -> 9658 Thaungdut`
  - `same_barony_path_id_reuse_to_current_target`:
    - `11061 Dagon -> 9598 Dagon`
  - guncel apply sonucu:
    - `exact rows requested = 140`
    - `applied rows = 262`
    - `missing source blocks = 27`
  - guncel validator sonucu degismedi:
    - `validation errors = 0`
    - `validation warnings = 0`
    - `missing playable province titles = 0`
    - `landed_titles live/test hash match = yes`
  - live/test `history/provinces/00_MB_PROVINCES.txt` SHA256:
    - `0FC7A544E5409B1548FE2A8885D7A3C93619D7C42F7047EB104B2747E942060B`
  - probe guncellemeleri:
    - `e_bengal_block_probe`: `ready:exact = 46`, `review:manual = 17`, `blocked:shared_target_low_coverage = 28`, `blocked:not_primary_target_source = 52`
    - `e_tibet_block_probe`: `ready:exact = 34`, `review:manual = 2`, `blocked:no_source_history = 4`
  - kalan agir zorluklar:
    - `11585 Khabaungkyo -> 9595 Swa` hala `review:high_overlap`; bu `c_toungoo` subtree shuffle vakasi olarak ayrik tutuluyor
    - kalan `e_bengal` satirlarinin buyuk cogu artik gercek `merge/shared_target` veya `not_primary_target_source` sinifinda

## 2026-04-17 title_relation_master_manuel anlami ve dogrulama

- Son `title_relation_master_manuel` turunda kritik anlam kuralı netlesti:
  - `title_relation_master_manuel.csv` icindeki `mod_title_id` alani yalnizca orijinal modda gercekten var olan title id tasir
  - authoritative kaynak:
    - `F:\Storage\Codding\git\Crusader Kings III\Leviathonlx MoreBookmarks-Plus\BookmarksGit\common\landed_titles\00_landed_titles.txt`
  - current/Yusseter repo title id'leri bu kolona fallback olarak yazilmaz

- Bu kurali bozan yanlis ara deneme kayda gecirildi:
  - onceki bozuk yeniden-yazimda, orijinal mod title id current repoda yoksa ama `source_title_id` current repoda varsa, o `source_title_id` yanlislikla `mod_title_id` olarak yazildi
  - bu semantik olarak yanlisti; cunku kolonun anlami `current title` degil, `orijinal mod counterpart` olmaliydi

- Kanit ornegi:
  - `source_title_id = b_youxi`
  - `works/map_data_sources/title_relation_master.csv` tarafinda gercek mod/canonical karsiligi `b_youxi_china`
  - Leviathon orijinal mod `00_landed_titles.txt` icinde `b_youxi_china` var
  - Leviathon orijinal modda `b_youxi` yok
  - bu nedenle `mod_title_id = b_youxi` yazimi acik hata kabul edildi

- Kullanici duzgun ve bozuk surumu ayri dosyalarda sabitledi:
  - dogru ana dosya:
    - `title_relation_master_manuel.csv`
  - bozuk ara surum:
    - `title_relation_master_manuel_bozuk.csv`

- Sonraki dogru kontrol kuralı:
  - `title_relation_master_manuel.csv` ile `works/map_data_sources/title_relation_master.csv` tutarliligi kontrol edilir
  - dolu `mod_title_id` degerlerinin tamami Leviathon orijinal mod `00_landed_titles.txt` icinde fiilen mevcut olmali
  - Yusseter/current landed_titles varligi burada yeterli kabul edilmez

- Son dogrulama sonucu:
  - `title_relation_master_manuel.csv` ile `works/map_data_sources/title_relation_master.csv` farki: `0`
  - dolu `mod_title_id` satiri: `1541`
  - Leviathon orijinal mod `00_landed_titles.txt` icinde bulunmayan `mod_title_id`: `0`
  - `title_relation_master_manuel.csv` ile `title_relation_master_manuel_bozuk.csv` farki: `412` satir

- Sonuc:
  - mevcut `title_relation_master_manuel.csv` dogru ve kullanilacak surum
  - `title_relation_master_manuel_bozuk.csv` yanlis fallback mantigiyla uretilmis bozuk surum olarak tutuluyor
  - bu turda ana dosyanin ustune tekrar yazilmadi; cunku dogru surum zaten geri gelmisti

- Sync yorumu netlestirildi:
  - mevcut `title_relation_master_manuel.csv`, kendi amaci bakimindan Leviathon orijinal mod `00_landed_titles.txt` ile sync icinde kabul edilir
  - bunun anlami:
    - dolu `mod_title_id` alanlarinin hepsi gercek Leviathon title id'leridir
  - bunun anlami DEGIL:
    - Leviathon tarafindaki tum dogu title rename/silme/merge backlog'u tamamen cozuldu
  - yani dosya semantik olarak dogru ve senkron, ama tum tarihsel merge problemi bitmis sayilmaz

- Bundan sonraki kural:
  - `title_relation_master_manuel.csv` icine current/Yusseter title id fallback'i yazilmayacak
  - `mod_title_id` sadece orijinal mod counterpart olacak
  - current projedeki bugunku karsilik gerekiyorsa ayri rapor veya ayri kolon mantigi ile tutulacak

## 2026-04-17 title_relation_master_manuel repo compare ve bozuk rebuild notlari

- Bu baslikta iki repo rolu netlestirildi:
  - degismemis/orijinal mod kaynak repo:
    - `F:\Storage\Codding\git\Crusader Kings III\Leviathonlx MoreBookmarks-Plus\BookmarksGit`
  - bizim proje repo:
    - `F:\Storage\Codding\git\Crusader Kings III\Yusseter MoreBookmarksPlus\BookmarksGit`

- Son title-relation turunda Leviathon repo tarafinda su yardimci araclar olusturuldu:
  - `works/tools/refresh_title_relation_manual.py`
  - `works/tools/compare_landed_titles_blocks.py`
  - `works/tools/rebuild_title_relation_manual_from_repo_compare.py`

- Bu araclarla ilk repo-karsilastirma raporlari uretildi:
  - `works/analysis/generated/title_relation_mapping/repo_refresh/title_manual_refresh_summary.md`
  - `works/analysis/generated/title_relation_mapping/repo_block_compare/landed_titles_block_compare_summary.md`
  - `works/analysis/generated/title_relation_mapping/repo_block_compare/shared_changed_titles.csv`
  - `works/analysis/generated/title_relation_mapping/repo_block_compare/source_only_block_titles.csv`
  - `works/analysis/generated/title_relation_mapping/repo_block_compare/mod_only_block_titles.csv`
  - `works/analysis/generated/title_relation_mapping/repo_current_rebuild/title_relation_manual_rebuild_summary.md`
  - `works/analysis/generated/title_relation_mapping/repo_current_rebuild/original_mod_to_current_title_map.csv`

- Repo block compare sonucu:
  - ortak block: `17087`
  - birebir ayni block: `16143`
  - icerik farki olan ortak block: `944`
  - sadece Yusseter/current repoda olan block: `2707`
  - sadece Leviathon/orijinal modda olan block: `1479`
- Bu karsilastirma, landed_titles merge/backlog takibi icin halen faydali kabul edilir.

- Ilk manual refresh/rewriting turunda iki kolonlu temiz CSV yeniden yazim denemesi yapildi ve su sayilar raporlandi:
  - toplam satir: `3776`
  - dolu `mod_title_id`: `1541`
  - gecersiz mod id: `0`
  - semantic remap: `0`
- Bu tur daha cok format/refresh seviyesindeydi; `mod_title_id` anlami sonradan kullanici tarafindan daha sert sekilde netlestirildi.

- Sonraki rebuild denemesinde semantik hata yapildi:
  - yanlis kural:
    - orijinal mod title id current projede yoksa ama `source_title_id` current projede varsa, `mod_title_id` o current/source title'a cevrildi
  - bu nedenle `mod_title_id` kolonu yanlislikla `current Yusseter title id` tasimaya basladi
  - bu yanlis tur sonunda raporlanan sayilar:
    - islenen dolu mod eslesmesi: `1541`
    - aynen korunan: `1129`
    - current title adina cevrilen: `407`
    - bosaltilan: `5`
- Bu deneme, bugunku anlamiyla authoritative kabul edilmez.

- Bu yanlis rebuild'in cikti durumu:
  - bozuk surum kullanici tarafinda acikca su dosyada saklandi:
    - `title_relation_master_manuel_bozuk.csv`
  - bozulmadan onceki dogru surum ise su dosyada korunuyor:
    - `title_relation_master_manuel.csv`

- Bozuk rebuild'in tipik hata kaniti:
  - `source_title_id = b_youxi`
  - current Yusseter tarafta `b_youxi` var
  - ama Leviathon orijinal mod tarafinda gercek mod counterpart `b_youxi_china`
  - Leviathon tarafinda `b_youxi` yok
  - yani `mod_title_id = b_youxi` yazmak yanlis; bu kolonun anlami current title degil, orijinal mod counterpart olmali

- Kullanici tarafindan son dogru recovery akisi:
  - `title_relation_master_manuel_bozuk.csv` yanlis surum olarak ayrildi
  - `title_relation_master_manuel.csv` dogru/pre-broken surum olarak birakildi
  - ondan sonra ana dosya tekrar bozulmadi; once sadece dogrulama yapildi

- Ana dosya icin son kesin dogrulama sayilari:
  - `title_relation_master_manuel.csv` ile `works/map_data_sources/title_relation_master.csv` farki: `0`
  - Leviathon orijinal mod `00_landed_titles.txt` icinde bulunmayan dolu `mod_title_id`: `0`
  - `title_relation_master_manuel.csv` ile `title_relation_master_manuel_bozuk.csv` farki: `412` satir
  - dolu `mod_title_id` toplamı: `1541`

- Son yorum:
  - su an kullanilacak authoritative dosya `title_relation_master_manuel.csv`
  - `title_relation_master_manuel_bozuk.csv` sadece yanlis fallback mantigini belgeleyen bozuk ara surum
  - `title_relation_master_manuel.csv` kendi amaci bakimindan Leviathon orijinal mod `00_landed_titles.txt` ile sync kabul edilir
  - ama bu sync, Leviathon tarafindaki tum dogu title rename/silme/merge backlog'unun tamamen bitmis oldugu anlamina gelmez

- Bundan sonraki title manual kuralı:
  - `mod_title_id` kolonuna current/Yusseter title id fallback'i yazilmayacak
  - bu kolonda sadece Leviathon/orijinal modda gercekten bulunan counterpart tutulacak
  - current projedeki bugunku karsilik bilgisi lazimsa ayri rapor veya ayri alan mantigi kullanilacak

## 2026-04-17 title_relation_master_manuel diff flag kolonu

- `title_relation_master_manuel.csv` icindeki 3. kolon artik `mod_title_id_differs`.
- Kural:
  - `mod_title_id` doluysa ve `source_title_id != mod_title_id` ise 3. kolon `yes`
  - ayni veya bos satirlarda 3. kolon bos kalir
- Bu turdaki `mod_title_id_differs = yes` satiri: `443`
- `works/tools/refresh_title_relation_manual.py` ve `works/tools/rebuild_title_relation_manual_from_repo_compare.py` bu kolonu koruyacak sekilde guncellendi.

## 2026-04-17 title_relation_master_manuel yes cleanup

- `title_relation_master_manuel.csv` icinde `mod_title_id` bos olan bazi satirlarda yanlislikla `source_title_id, yes,` formu olusmustu.
- Bu turda kural netlestirildi:
  - `yes/no` degeri sadece `is_same_title_id` mantiginda anlamlidir
  - `mod_title_id` bos ise satir `source_title_id, ,` biciminde kalmali
- Kullanici istegi geregi bu duzeltmede dosyanin `virgul + bosluk` duzeni korunarak sadece yanlis `mod_title_id = yes` metni silindi.
- Bu turda temizlenen satir sayisi: `2229`

## 2026-04-19 title_relation_master_manuel manuel mapping validator

- Kullanici `title_relation_master_manuel.csv` icinde barony (`b_`) disindaki butun satirlari manuel olarak doldurdugunu belirtti.
- Kullanici, onceki otomatik/heuristic mappinglerde benim yaptigim hatalari `title_relation_master_manuel_before_manuel.csv` icinde `#(Yusseter not: HATALI!)` ile isaretledi.
- Cikarilan ana ders:
  - title eslestirmede isim benzerligi tek basina kanit degildir
  - `same id/name` bile semantik esdegerlik garantisi degildir
  - asil kontrol zinciri tier, landed_titles parent chain, source/mod varligi, descendant/province baglami ve manuel karar olmalidir
- Kullanici tarafindan verilen kritik hata ornekleri:
  - `c_luzhou_2 -> c_luzhou_jin_china` yanlis; dogru baglam `c_luzhou_dongchuan_china`
  - `d_dongchuan -> d_dongchuan` tek basina eksik/yaniltici; placeholder + asil temsil icin `d_dongchuan & d_dongchuan_china` gibi dusunulmeli
  - `c_puzhou -> c_puzhou_china` yanlis
  - `c_puzhou_2 -> c_puzhou_china` yanlis; dogru baglam `c_puzhou_liang_china`
  - `c_LIAO_xianzhou -> c_xianzhou_china` yanlis; dogru baglam `c_liaoxi_china`
  - `c_aru -> c_aru` yanlis semantik eslesme; karsilik yoksa `*there_is_no*`, gerekirse en yakin aday ayri manuel kararla yazilmali
- Yeni kabul edilen manuel tablo kurallari:
  - `source_title_id` Yusseter/current `common/landed_titles/00_landed_titles.txt` icinde bulunmali
  - `mod_title_id` icindeki her gercek token Leviathon/orijinal mod `common/landed_titles/00_landed_titles.txt` icinde bulunmali
  - `source_title_id` ve `mod_title_id` tokenlari ayni tier olmalidir
  - `source_title_id == mod_title_id` ise ilgili `is_same_title_id` tokeni `yes`; degilse `no` olmalidir
  - `mod_title_id` icinde `&` varsa `is_same_title_id` de token bazinda ayni sayida `yes/no` tasimalidir
  - `*there_is_no*` gercek mod title yok anlamina gelir
  - ayni `mod_title_id` birden fazla farkli `source_title_id` icin kullaniliyorsa normalde hatadir
  - ayni `mod_title_id` tekrar kullanimi ancak tekrar eden kullanimlarda `(second)` varsa kabul edilebilir
  - `(second)` history/title rewrite asamasinda tek global replace degil, gerekirse ayri hedef history block uretme sinyalidir
  - `&` ile yazilan coklu `mod_title_id` donor gibi ele alinacak; history/script rewrite tarafinda her donor source target'a baglanacak, coa/localization icin ayni otomatik kural kullanilmayacak
- Bu kurallari statik kontrol etmek icin yeni read-only validator eklendi:
  - `works/tools/validate_title_relation_manual.py`
- Validator canli tabloyu degistirmez; sadece rapor uretir.
- Uretilen rapor klasoru:
  - `works/analysis/generated/title_relation_manual_validation/`
- Ana raporlar:
  - `title_relation_manual_validation_summary.md`
  - `title_relation_manual_validation_flags.csv`
  - `title_relation_manual_token_detail.csv`
  - `title_relation_manual_duplicate_mod_usage.csv`
  - `title_relation_manual_parent_context_report.csv`
  - `title_relation_manual_same_id_context_report.csv`
  - `title_relation_manual_source_coverage.csv`
  - `title_relation_manual_marked_bad_regression.csv`
  - `title_relation_manual_high_signal_errors.csv`
- Ilk validator sonucu:
  - manual rows: `3777`
  - master source ids: `3776`
  - errors: `121`
  - warnings: `581`
  - info blank barony rows: `1719`
  - marked bad regression status: `60 cleared`
- Error dagilimi:
  - `duplicate_mod_title_without_second`: `75`
  - `invalid_is_same_value`: `14`
  - `source_title_missing_in_yusseter_landed_titles`: `9`
  - `mod_title_missing_in_leviathon_landed_titles`: `8`
  - `is_same_token_count_mismatch`: `8`
  - `is_same_value_incorrect`: `4`
  - `blank_is_same_title_id`: `2`
  - `tier_mismatch`: `1`
- Warning dagilimi:
  - `parent_mapping_mismatch`: `578`
  - `source_title_duplicate_in_landed_titles`: `2`
  - `source_title_extra_in_manual_vs_master`: `1`
- Onemli yorum:
  - `#(Yusseter not: HATALI!)` ile isaretlenen eski hatali mappinglerden mevcut manuel tabloda aynen kalan bulunmadi (`60 cleared`)
  - kalan `121` error dogrudan incelenebilir aktif kontrol havuzudur
  - `parent_mapping_mismatch` sayisi yuksek oldugu icin bu sinif otomatik hata degil, baglam-review uyarisi olarak ele alinmalidir
  - `b_` satirlarindaki bos mappingler bu turda bilerek info seviyesinde tutuldu, cunku kullanici barony disindaki satirlari manuel doldurdugunu soyledi

## 2026-04-19 title_relation high-signal cleanup sonrasi

- Kullanici `title_relation_manual_high_signal_errors.csv` raporundaki hatalara gore `title_relation_master_manuel.csv` dosyasini manuel olarak duzeltti.
- Kullanici ayrica `common/landed_titles/00_landed_titles.txt` icinde su landed_titles duzeltmelerini yaptigini bildirdi:
  - `d_tohchen_china` -> `d_LIAO_zhongjing`
  - `d_hiyaxu_china` -> `d_yanyun_yuyi`
  - `c_yeongwon` icine `b_Goryeo_Bukgye_Maengju` eklendi
  - `c_myeongju` icine `b_Goryeo_Donggye_Myeongju` eklendi
  - `c_deungju` icine `b_Goryeo_Donggye_Deungju`, `b_Goryeo_Donggye_Uiju`, `b_Goryeo_Donggye_Hwaju` eklendi
  - `c_nakkavaram` icine `b_muot` eklendi
  - `c_riau` icine `b_siantan` eklendi
  - `k_xia_china` -> `k_xia`
- `works/tools/validate_title_relation_manual.py` tekrar calistirildi.
- Guncel validator sonucu:
  - manual rows: `3777`
  - source landed title ids: `17433`
  - mod landed title ids: `18927`
  - master source ids: `3776`
  - errors: `75`
  - warnings: `584`
  - `title_relation_manual_high_signal_errors.csv` satir sayisi: `0`
- Guncel error dagilimi:
  - `duplicate_mod_title_without_second`: `75`
- Guncel warning dagilimi:
  - `parent_mapping_mismatch`: `581`
  - `source_title_duplicate_in_landed_titles`: `2`
  - `source_title_extra_in_manual_vs_master`: `1`
- `#(Yusseter not: HATALI!)` regression raporu halen temiz:
  - `cleared: 60`
- Pratik sonuc:
  - high-signal mekanik hatalar kapandi
  - kalan aktif hata havuzu artik duplicate mod title / `(second)` isaretleme meselesi
  - parent mismatch raporu halen baglam-review uyarisi olarak duruyor, otomatik hata kabul edilmemeli
- `common/landed_titles/00_landed_titles.txt` degistigi icin proje kuralina gore `test_files/common/landed_titles/00_landed_titles.txt` canli dosyayla senkronlandi.
- Senkron sonrasi SHA256:
  - `common/landed_titles/00_landed_titles.txt`: `9648D1918282B9BFB64FD6EAA2ADFE9D6C4DF3E2D688167B2CF0040E47AF5394`
  - `test_files/common/landed_titles/00_landed_titles.txt`: `9648D1918282B9BFB64FD6EAA2ADFE9D6C4DF3E2D688167B2CF0040E47AF5394`
  - hash match: `yes`

## 2026-04-19 Mask Tabanli Dogu Title Scope Cikarimi

- Onceki title kapsam problemi netlesti: `title_relation_master.csv` dogu source seti root-list bazli oldugu icin `e_mongolia > k_gobi > d_gobi_dadaels > c_em_dadaels` gibi mask icindeki dogu title'lari kapsam disi kalabiliyordu.
- Yeni kural:
  - Dogu title kapsami elle root listesinden degil, `works/map_data_sources/provinces_birlesim_dogu 2026-04-19.png` icindeki non-black RGB'lerden cikarilacak.
  - RGB -> province id eslesmesi `map_data/definition.csv` uzerinden yapilacak.
  - Province id -> title hiyerarsisi current `common/landed_titles/00_landed_titles.txt` icindeki `province = <id>` baglarindan cikarilacak.
  - Hiyerarsi cikarilirken `b_` barony title'lari ana comparison dosyasina dahil edilmeyecek.
  - Dahil edilen title bloklarindaki `capital = c_*` county referanslari da mask scope'a eklenecek.
- Yeni arac eklendi:
  - `works/tools/build_east_title_scope_from_province_mask.py`
- Bu arac mevcut `title_relation_master_manuel.csv` dosyasini degistirmiyor; ayri rapor uretiyor.
- Uretilen cikti klasoru:
  - `works/analysis/generated/title_relation_manual_validation/mask_east_scope/`
- Ana comparison dosyasi:
  - `works/analysis/generated/title_relation_manual_validation/mask_east_scope/title_relation_master_manuel_mask_east_scope.csv`
- Diger raporlar:
  - `mask_east_scope_titles.csv`
  - `mask_east_scope_provinces.csv`
  - `mask_east_scope_unmatched_rgb.csv`
  - `mask_east_scope_unbound_provinces.csv`
  - `mask_east_scope_summary.md`
- Ilk calistirma sonucu:
  - non-black mask RGB: `4813`
  - definition ile eslesen mask province: `4813`
  - unmatched RGB: `0`
  - landed_titles baglantisi olmayan/unbound province: `1978`
  - mask tabanli non-barony title: `1222`
  - manual CSV non-barony title: `1098`
  - `added_by_mask`: `158`
  - `removed_by_mask`: `34`
  - degismeyen: `1064`
- `c_em_dadaels` yeni algoritmayla dogru sekilde `added_by_mask` olarak yakalandi.
- `c_em_dadaels` path'i:
  - `e_mongolia > k_gobi > d_gobi_dadaels > c_em_dadaels`
- Bu sonuc, onceki `eksik yok` yorumunun sadece eski `title_relation_master.csv` source setine gore gecerli oldugunu; live mask tabanli dogu kapsaminda eksikler oldugunu gosterdi.

## 2026-04-20 Mask Scope Manual-Like Cikti

- `works/tools/build_east_title_scope_from_province_mask.py` genisletildi.
- Artik detayli comparison dosyasina ek olarak manual tablo mantigina yakin dort kolonlu bir dosya uretiyor:
  - `works/analysis/generated/title_relation_manual_validation/mask_east_scope/title_relation_master_manuel_mask_scope_manual_like.csv`
- Bu dosya `title_relation_master_manuel.csv` dosyasini degistirmez.
- Kolonlar:
  - `source_title_id`
  - `mod_title_id`
  - `is_same_title_id`
  - `mask_scope_change`
- Satir mantigi:
  - mevcut manual non-barony satirlarinin sirasi korunur
  - mask kapsaminda da kalanlarda `mask_scope_change` bos kalir
  - mevcut manualde olup mask kapsaminda olmayanlarda `removed_by_mask` yazilir
  - mask kapsaminda olup manualde olmayan title'lar dosyanin en altina eklenir ve `added_by_mask` yazilir
  - `b_` barony title'lari bu dosyaya dahil edilmez
- Son calistirma sayilari degismedi:
  - mask tabanli non-barony title: `1222`
  - manual CSV non-barony title: `1098`
  - `added_by_mask`: `158`
  - `removed_by_mask`: `34`
  - degismeyen: `1064`

## 2026-04-20 Reverse Capital Scope Duzeltmesi

- Mask tabanli title scope algoritmasinda eksik kural tespit edildi:
  - mask kapsamindaki bir `c_*` county, baska bir title tarafindan `capital = c_*` olarak kullaniliyorsa, o capital owner title ve parent zinciri de dogu scope'a dahil edilmeli.
- Ornek problem:
  - `c_BOR_brunei` mask kapsaminda ve current hiyerarside `e_nusantara > k_tanjungnagara > d_BOR_barune > c_BOR_brunei` altinda.
  - Ama `e_brunei` ve `k_brunei` sadece `capital = c_BOR_brunei` uzerinden bu county'ye bagliydi.
  - Onceki algoritma reverse capital bakmadigi icin `e_brunei` ve `k_brunei` hatali olarak `removed_by_mask` gorunuyordu.
- `works/tools/build_east_title_scope_from_province_mask.py` icine reverse capital kurali eklendi:
  - `included c_* -> capital_owners_by_county[c_*] -> owner title + ancestors`
  - reason etiketi: `reverse_capital_owner_of:<county>`
- Yeniden uretilen raporlarda duzelen ornekler:
  - `e_brunei` artik `removed_by_mask` degil, reason: `reverse_capital_owner_of:c_BOR_brunei`
  - `k_brunei` artik `removed_by_mask` degil, reason: `reverse_capital_owner_of:c_BOR_brunei`
  - `e_minister_of_revenue` artik `removed_by_mask` degil, reason: `reverse_capital_owner_of:c_jingzhao`
- Reverse capital sonrasi guncel sayilar:
  - mask tabanli non-barony title: `1388`
  - manual CSV non-barony title: `1098`
  - `added_by_mask`: `309`
  - `removed_by_mask`: `19`
  - degismeyen: `1079`
  - manual-like toplam satir: `1407`

## 2026-04-20 Forward Capital Kurali Kaldirildi

- Kullanici kuralin yanlis yorumlandigini netlestirdi:
  - Istenen kural `title scope'taysa capital county de scope'tadir` degil.
  - Istenen kural yalnizca `capital county scope'taysa, bu county'yi capital kullanan title da scope'tadir`.
- Bu nedenle `works/tools/build_east_title_scope_from_province_mask.py` icindeki forward capital kurali kaldirildi.
- Kalan dogru capital kurali:
  - `included c_* -> capital_owners_by_county[c_*] -> owner title + ancestors`
  - reason etiketi: `reverse_capital_owner_of:<county>`
- Bu duzeltme sonrasi:
  - `c_delhi`, artik sadece `h_india capital = c_delhi` oldugu icin otomatik eklenmiyor.
  - `e_red_horde` ve `e_black_horde` gibi `capital = c_delhi` kaynakli fazla title'lar manual-like scope dosyasindan cikti.
  - `e_brunei` ve `k_brunei` scope'ta kalmaya devam ediyor; cunku `c_BOR_brunei` gercek `province_path` ile mask kapsaminda ve bu title'lar `capital = c_BOR_brunei` kullaniyor.
  - `e_minister_of_revenue` scope'ta kalmaya devam ediyor; cunku `c_jingzhao` gercek `province_path` ile mask kapsaminda ve bu title `capital = c_jingzhao` kullaniyor.
- Forward capital kaldirildiktan sonraki guncel sayilar:
  - mask tabanli non-barony title: `1327`
  - manual CSV non-barony title: `1098`
  - `added_by_mask`: `250`
  - `removed_by_mask`: `21`
  - degismeyen: `1077`
  - manual-like toplam satir: `1348`

## 2026-04-20 Landed Titles County Source Audit

- Kullanici `00_landed_titles.txt` uretiminde kaynak secimi hatasi olabilecegini `c_yumen` ornegiyle tespit etti.
- Ornek:
  - current `common/landed_titles/00_landed_titles.txt` icinde `c_yumen` current blok vanilla `02_china.txt` ile birebir ayni.
  - Leviathon mod kaynak `c_yumen` blogu farkli barony isimleri/kurgusu tasiyor.
  - `b_jinshan = province 9491`.
  - `definition.csv` icinde `9491` RGB: `51,144,173`, name: `Chijin`.
  - Bu RGB `provinces_birlesim_dogu 2026-04-19.png` icinde yok, `provinces_modlu_kalan.png` icinde var.
  - Yani `c_yumen` icin beklenen kaynak `mod`, ama current blok `vanilla_exact`.
- Bu sinifi toplu yakalamak icin yeni arac eklendi:
  - `works/tools/audit_landed_title_county_source_from_map.py`
- Audit mantigi:
  - current `00_landed_titles.txt` icindeki her `c_*` county blogu parse edilir.
  - county altindaki `province = <id>` degerleri `definition.csv` ile RGB'ye cevrilir.
  - RGB'ler `provinces_birlesim_dogu 2026-04-19.png` ve `provinces_modlu_kalan.png` maskeleriyle siniflandirilir.
  - county icindeki province'ler tamamen dogu maskesindeyse `expected_source = vanilla`.
  - tamamen mod kalan maskesindeyse `expected_source = mod`.
  - karisik veya belirsiz durumlar `mixed/unknown/manual_review` olur.
  - current county block, vanilla landed_titles klasorundeki county block ve Leviathon mod landed_titles klasorundeki county block ile normalize edilerek karsilastirilir.
- Uretilen rapor klasoru:
  - `works/analysis/generated/landed_titles_source_audit/`
- Uretilen dosyalar:
  - `county_source_audit.csv`
  - `county_source_high_signal_mismatches.csv`
  - `county_source_manual_review.csv`
  - `county_source_province_detail.csv`
  - `county_source_audit_summary.md`
- Ilk calistirma sonucu:
  - county rows: `3610`
  - province rows: `11551`
  - high-signal mismatch: `33`
  - manual/review rows: `287`
- Audit status dagilimi:
  - `ok`: `3287`
  - `review:expected_vanilla_source_not_exact`: `240`
  - `manual_review:mixed`: `29`
  - `mismatch:expected_mod_current_vanilla`: `24`
  - `manual_review:unknown`: `16`
  - `mismatch:expected_vanilla_current_mod`: `9`
  - `skip:no_provinces`: `3`
  - `review:expected_mod_source_not_exact`: `2`
- `c_yumen` raporda beklenen sekilde yakalandi:
  - `audit_status = mismatch:expected_mod_current_vanilla`
  - `expected_source = mod`
  - `current_block_source = vanilla_exact`
  - `province_sources = mod_kalan | mod_kalan | mod_kalan`
  - vanilla best match: `02_china.txt:2833`, similarity `1.000000`
  - mod best match: Leviathon `00_landed_titles.txt:99436`, similarity `0.625954`

## 2026-04-21 County Source Fix Plan Raporu

- `works/tools/audit_landed_title_county_source_from_map.py` genisletildi.
- Arac artik county source audit raporlarina ek olarak uygulanacak/uygulanmayacak adaylari ayiran fix plan da uretiyor.
- Yeni uretilen dosyalar:
  - `works/analysis/generated/landed_titles_source_audit/county_source_fix_plan.csv`
  - `works/analysis/generated/landed_titles_source_audit/county_source_fix_plan_summary.md`
- `county_source_fix_plan.csv` kolonlari:
  - `county_id`
  - `action`
  - `expected_source`
  - `current_block_source`
  - `source_block_path`
  - `confidence`
  - `reason`
- Action kurallari:
  - `no_action`: mevcut county block beklenen kaynak sinifiyla uyumlu.
  - `replace_with_mod_block`: province maskesine gore beklenen kaynak `mod`, current block `vanilla_exact`, Leviathon mod kaynakta ayni county icin kaynak block mevcut.
  - `replace_with_vanilla_block`: province maskesine gore beklenen kaynak `vanilla`, current block `mod_exact`; bu ters yon adaylari otomatik uygulanmadan once manuel kontrol gerektirir.
  - `manual_review`: mixed/unknown/review durumlari veya beklenen kaynak blocku bulunamayan mismatch durumlari.
- 2026-04-21 yeniden calistirma sonucu:
  - county rows: `3610`
  - province rows: `11551`
  - high-signal mismatch: `33`
  - audit `ok`: `3204`
  - audit `review:expected_vanilla_source_not_exact`: `245`
  - audit `review:expected_mod_source_not_exact`: `80`
  - audit `manual_review:mixed`: `29`
  - audit `mismatch:expected_mod_current_vanilla`: `24`
  - audit `manual_review:unknown`: `16`
  - audit `mismatch:expected_vanilla_current_mod`: `9`
  - audit `skip:no_provinces`: `3`
- Fix plan action dagilimi:
  - `no_action`: `3204`
  - `manual_review`: `383`
  - `replace_with_mod_block`: `14`
  - `replace_with_vanilla_block`: `9`
- `replace_with_mod_block` adaylari:
  - `c_liangzhou`
  - `c_fanhe`
  - `c_kuozhou`
  - `c_qilin`
  - `c_yalong`
  - `c_ganzhou`
  - `c_yumen`
  - `c_shazhou`
  - `c_guazhou`
  - `c_zhenfan`
  - `c_alxa`
  - `c_wentugaole`
  - `c_heihe`
  - `c_mazongshan`
- `replace_with_vanilla_block` adaylari:
  - `c_golag`
  - `c_zogang`
  - `c_gyaitang`
  - `c_lenggu`
  - `c_sungqu`
  - `c_zoige`
  - `c_quqen`
  - `c_lhagang`
  - `c_tewo`
- Not:
  - Bu turda `common/landed_titles/00_landed_titles.txt` veya `test_files/common/landed_titles/00_landed_titles.txt` degistirilmedi.
  - Bir sonraki guvenli uygulama adimi yalnizca `replace_with_mod_block` satirlarini, kullanici onayi sonrasinda, current county blocklari Leviathon mod kaynak blocklariyla degistirmek olmali.
  - `replace_with_vanilla_block` ters yon adaylari ozellikle Tibet/Himalaya gibi sinir/mod-canonical ihtimali olan bolgelerde manuel kontrol edilmeden uygulanmamali.

## 2026-04-21 County Source Replace With Mod Block Uygulamasi

- `works/tools/apply_county_source_fix_plan.py` eklendi.
- Bu arac:
  - `county_source_fix_plan.csv` icinden varsayilan olarak yalnizca `action = replace_with_mod_block` satirlarini alir.
  - `--apply` verilmezse sadece preview raporu uretir.
  - `--apply` verilirse hem `common/landed_titles/00_landed_titles.txt` hem `test_files/common/landed_titles/00_landed_titles.txt` icindeki ilgili county blocklarini ayni kaynak block ile degistirir.
  - source blocklari `source_block_path` kolonundaki Leviathon mod landed_titles path/line bilgisinden alir.
  - source block indentation'i target county indentation'ina uyarlar.
- Dry-run preview sonucu:
  - dosya: `works/analysis/generated/landed_titles_source_audit/county_source_replace_with_mod_block_preview.csv`
  - preview rows: `14`
  - status: `ok = 14`
  - current/test blocklari uygulama oncesi ayniydi: `current_equals_test_before = yes` for `14`
- `--apply` ile uygulanan county blocklari:
  - `c_liangzhou`
  - `c_fanhe`
  - `c_kuozhou`
  - `c_qilin`
  - `c_yalong`
  - `c_ganzhou`
  - `c_yumen`
  - `c_shazhou`
  - `c_guazhou`
  - `c_zhenfan`
  - `c_alxa`
  - `c_wentugaole`
  - `c_heihe`
  - `c_mazongshan`
- Apply raporu:
  - `works/analysis/generated/landed_titles_source_audit/county_source_replace_with_mod_block_apply_report.csv`
  - applied rows: `14`
  - apply report status: `ok = 14`
- Uygulama sonrasi live/test landed_titles hash esitlendi:
  - `common/landed_titles/00_landed_titles.txt` SHA256: `E3230CB8C5B77E98017673A53D5E342DAF4D65C97CBF8682AF34CA8064791E15`
  - `test_files/common/landed_titles/00_landed_titles.txt` SHA256: `E3230CB8C5B77E98017673A53D5E342DAF4D65C97CBF8682AF34CA8064791E15`
- County source audit tekrar calistirildi.
- Uygulama sonrasi audit ozeti:
  - county rows: `3610`
  - province rows: `11551`
  - high-signal mismatch: `19`
  - audit `ok`: `3218`
  - audit `review:expected_vanilla_source_not_exact`: `245`
  - audit `review:expected_mod_source_not_exact`: `80`
  - audit `manual_review:mixed`: `29`
  - audit `manual_review:unknown`: `16`
  - audit `mismatch:expected_mod_current_vanilla`: `10`
  - audit `mismatch:expected_vanilla_current_mod`: `9`
  - audit `skip:no_provinces`: `3`
- Fix plan action dagilimi uygulama sonrasinda:
  - `no_action`: `3218`
  - `manual_review`: `383`
  - `replace_with_vanilla_block`: `9`
  - `replace_with_mod_block`: `0`
- `c_yumen` artik temiz:
  - `audit_status = ok`
  - `expected_source = mod`
  - `current_block_source = mod_exact`
  - `province_ids = 9491 9487 9492`
  - `province_sources = mod_kalan | mod_kalan | mod_kalan`
  - `mod_exact = yes`
  - `mod_similarity = 1.000000`
- `works/tools/validate_east_mapping_pipeline.ps1` uygulama sonrasinda exit code `0` ile calisti, fakat mevcut repo durumunda validation finding kaldi:
  - `landed_titles live/test hash match = yes`
  - `validation errors = 6`
  - `validation warnings = 0`
  - `missing playable province titles = 1`
- Kalan validator hatalari uygulanan 14 county source replacement kapsaminda degil:
  - `b_muot`: non-land province ID `12781`
  - `b_siantan`: non-land province ID `12782`
  - `b_Goryeo_Donggye_Uiju`: non-land province ID `12777`
  - `b_Goryeo_Bukgye_Maengju`: non-land province ID `12780`
  - `b_Goryeo_Donggye_Hwaju`: non-land province ID `12785`
  - missing playable province title: province `12154`, expected title `b_dingzhou_anxi`
- Not:
  - Bu turda `replace_with_vanilla_block` satirlari uygulanmadi.
  - Kalan 10 `mismatch:expected_mod_current_vanilla` satiri mod kaynakta ayni county id ile block bulunamadigi icin manual review sinifinda kaldi.
  - Siradaki teknik is ya kalan validator hatalarini ayri ele almak ya da county source audit icin higher-tier `d_/k_/e_/h_` rollup raporu uretmek olmali.

## 2026-04-21 Default Map Impassable Range Split

- `map_data/default.map` ve `test_files/map_data/default.map` birlikte guncellendi.
- `TECH PLACEHOLDER PROVINCES` icindeki iki impassable range split edildi:
  - eski: `RANGE { 12774 12782 }`
  - eski: `RANGE { 12784 12793 }`
  - yeni: `RANGE { 12774 12776 }`
  - yeni: `RANGE { 12778 12779 }`
  - yeni: `LIST { 12784 }`
  - yeni: `RANGE { 12786 12793 }`
- Boylece baronylerde kullanilan su province ID'ler artik `impassable_mountains` icinde kalmiyor:
  - `12777`
  - `12780`
  - `12781`
  - `12782`
  - `12785`
- Canli dosyada daha once yapilmis olan `12773` ve `12783` impassable list cikarimi `test_files` tarafina da tasindi; iki `default.map` dosyasinin ilgili diff'i esitlendi.
- `works/tools/validate_east_mapping_pipeline.ps1` tekrar calistirildi.
- Validator sonucu:
  - `landed_titles live/test hash match = yes`
  - `validation errors = 1`
  - `validation warnings = 0`
  - `missing playable province titles = 1`
- Kapanan hatalar:
  - `b_muot`: non-land province ID `12781`
  - `b_siantan`: non-land province ID `12782`
  - `b_Goryeo_Donggye_Uiju`: non-land province ID `12777`
  - `b_Goryeo_Bukgye_Maengju`: non-land province ID `12780`
  - `b_Goryeo_Donggye_Hwaju`: non-land province ID `12785`
- Kalan tek validator hatasi:
  - province `12154`, expected landed title `b_dingzhou_anxi`

## 2026-04-21 Province 12154 Missing Title Fix

- Kalan validator hatasi `12154 -> b_dingzhou_anxi` cozuldu.
- Kaynak durum:
  - `map_data/definition.csv` ve `test_files/map_data/definition.csv` icinde province `12154` adi `b_dingzhou_anxi`.
  - `common/landed_titles/00_landed_titles.txt` ve `test_files/common/landed_titles/00_landed_titles.txt` icinde `c_dingzhou` altinda bu province daha once `b_anxi` title id'si ile duruyordu.
  - Baska bir `b_anxi` zaten `c_guazhou` altinda province `9482` icin kullaniliyor.
- Uygulanan duzeltme:
  - `c_dingzhou` altindaki `province = 12154` barony title id'si `b_anxi` -> `b_dingzhou_anxi` olarak rename edildi.
  - Degisiklik hem live landed_titles hem `test_files` landed_titles icin yapildi.
  - `localization/replace/english/z_MB_titles_l_english.yml` icine `b_dingzhou_anxi: "Ānxī"` eklendi.
  - `c_guazhou` altindaki `b_anxi = { #Guazhou }` korunarak birakildi.
- Son validator sonucu:
  - `landed_titles live/test hash match = yes`
  - `missing playable province titles = 0`
  - `validation errors = 0`
  - `validation warnings = 0`
- Son landed_titles SHA256:
  - `common/landed_titles/00_landed_titles.txt`: `A45AF6C4719A7886FBE5119409339AFA467EA9CCFC9B77B36BB19AD647F48FFA`
  - `test_files/common/landed_titles/00_landed_titles.txt`: `A45AF6C4719A7886FBE5119409339AFA467EA9CCFC9B77B36BB19AD647F48FFA`

## 2026-04-21 County Source Manual Worklist CSV

- County source audit `b_dingzhou_anxi` rename sonrasi tekrar calistirildi.
- Yeni audit ozeti:
  - county rows: `3610`
  - high signal mismatches: `19`
  - manual/review rows: `370`
- Sadece CSV ureten yeni arac eklendi:
  - `works/tools/build_county_source_manual_worklist.py`
- Uretilen dosya:
  - `works/analysis/generated/landed_titles_source_audit/county_source_manual_worklist.csv`
- CSV kolonlari:
  - `county_id`
  - `action_suggestion`
  - `audit_status`
  - `current_parent`
  - `current_line`
  - `expected_source`
  - `current_block_source`
  - `province_ids`
  - `province_names`
  - `source_file`
  - `similarity`
  - `reason`
- CSV icerigi:
  - `no_action` satirlari dahil edilmedi.
  - toplam rows: `392`
  - `replace_with_vanilla_block`: `9`
  - `manual_review`: `383`
- Audit status dagilimi:
  - `manual_review:mixed`: `29`
  - `manual_review:unknown`: `16`
  - `mismatch:expected_mod_current_vanilla`: `10`
  - `mismatch:expected_vanilla_current_mod`: `9`
  - `review:expected_mod_source_not_exact`: `80`
  - `review:expected_vanilla_source_not_exact`: `245`
  - `skip:no_provinces`: `3`
- Not:
  - `c_dingzhou` validator hatasi olarak kapandi, fakat county source worklist'te `review:expected_vanilla_source_not_exact` olarak kaldi.
  - `c_dingzhou` satiri artik `province_names = b_dingzhou_anxi | b_dingzhou_wangdu` gosteriyor.

## 2026-04-21 County Source Manual Worklist Sadelestirme

- Kullanici manuel duzenleme icin onceki CSV'nin okunabilir olmadigini belirtti.
- `works/tools/build_county_source_manual_worklist.py` sade 4 kolonlu cikti verecek sekilde guncellendi.
- Yeni `county_source_manual_worklist.csv` kolonlari:
  - `county_id`
  - `current_source`
  - `expected_source`
  - `status`
- `current_source`, fix plan icindeki `current_block_source` alanindan geliyor.
- `expected_source`, fix plan icindeki `expected_source` alanindan geliyor.
- Uzun audit durumlari kisa `status` degerlerine indirildi:
  - `mismatch:*` -> `mismatch`
  - `review:*` -> `review`
  - `manual_review:mixed` -> `mixed`
  - `manual_review:unknown` -> `unknown`
  - `skip:*` -> `skip`
- CSV tekrar uretildi:
  - toplam rows: `392`
  - `mismatch`: `19`
  - `review`: `325`
  - `mixed`: `29`
  - `unknown`: `16`
  - `skip`: `3`
- `no_action` satirlari halen CSV'ye dahil degil.

## 2026-04-21 Leviathon Cultural Names Controlled Merge

- Leviathon kaynak dosya:
  - `F:\Storage\Codding\git\Crusader Kings III\Leviathonlx MoreBookmarks-Plus\BookmarksGit\common\landed_titles\00_landed_titles.txt`
- Hedef dosyalar:
  - `common/landed_titles/00_landed_titles.txt`
  - `test_files/common/landed_titles/00_landed_titles.txt`
- Dogrudan `Namelist_script.py` calistirilmadi; onun yerine path bazli controlled merge araci eklendi:
  - `works/tools/merge_landed_titles_cultural_names_from_source.py`
- Arac yalnizca ayni title path'teki mevcut `cultural_names` bloklarinda Leviathon'da olup hedefte eksik olan su key/value satirlarini ekler:
  - `name_list_persian_turkish_anatolian`
  - `name_list_turkish`
- Karsilastirma key bazli degil, key+value bazli yapildi. Bu nedenle `b_cratea` gibi kaynakta ayni key'in iki farkli value ile tekrarlandigi bloklarda iki value da korundu:
  - `cn_krateia`
  - `cn_gerede`
- Dry-run/apply raporlari:
  - `works/analysis/generated/landed_titles_cultural_names_merge/cultural_names_missing_from_source.csv`
  - `works/analysis/generated/landed_titles_cultural_names_merge/cultural_names_apply_live.csv`
  - `works/analysis/generated/landed_titles_cultural_names_merge/cultural_names_apply_test.csv`
  - `works/analysis/generated/landed_titles_cultural_names_merge/cultural_names_postcheck_live.csv`
  - `works/analysis/generated/landed_titles_cultural_names_merge/cultural_names_postcheck_test.csv`
- Uygulanan satir sayisi:
  - live landed_titles: `528`
  - test_files landed_titles: `528`
- Eklenen key dagilimi:
  - `name_list_persian_turkish_anatolian`: `265`
  - `name_list_turkish`: `263`
- Postcheck sonucu:
  - live will_add: `0`
  - test will_add: `0`
- Son landed_titles SHA256:
  - `common/landed_titles/00_landed_titles.txt`: `6737B09C139DE6FCEA45BE1BB90ECDE367589991785A5D7D7A2B7C77F5A0290C`
  - `test_files/common/landed_titles/00_landed_titles.txt`: `6737B09C139DE6FCEA45BE1BB90ECDE367589991785A5D7D7A2B7C77F5A0290C`
- `works/tools/validate_east_mapping_pipeline.ps1` tekrar calistirildi:
  - `landed_titles live/test hash match = yes`
  - `missing playable province titles = 0`
  - `validation errors = 0`
  - `validation warnings = 0`
- County source audit ve sade manual worklist tekrar uretildi.
- Cultural names merge sonrasi fix plan dagilimi:
  - `no_action`: `3296`
  - `manual_review`: `305`
  - `replace_with_vanilla_block`: `9`
- Sade `county_source_manual_worklist.csv` son dagilim:
  - toplam rows: `314`
  - `mismatch`: `19`
  - `review`: `247`
  - `mixed`: `29`
  - `unknown`: `16`
  - `skip`: `3`

## 2026-04-22 County Source Worklist Regeneration ve Not Koruma

- Kullanici `county_source_manual_worklist.csv` icinde manuel not ekledi:
  - `c_xiningzhou,# Named to c_shanzhou_mbp`
- `works/tools/build_county_source_manual_worklist.py` guncellendi:
  - Ana CSV 4 kolonlu kalir: `county_id,current_source,expected_source,status`.
  - `status` icindeki `# ...` notlari county bazinda okunup ayni county halen worklist'te varsa geri yazilir.
  - Worklist'ten dusen notlar `works/analysis/generated/landed_titles_source_audit/county_source_manual_worklist_preserved_notes.csv` icinde korunur.
- Su an preserved notes:
  - `c_xiningzhou,# Named to c_shanzhou_mbp,county_not_in_current_worklist`
- Manuel landed_titles degisikliklerinden sonra validator su hatalari verdi ve duzeltildi:
  - `d_longyou` capital: `c_xiningzhou` -> `c_shanzhou_mbp`
  - `d_juyan` capital: `c_tongcheng` -> `c_yijinai`
  - province `10403` icin duplicate barony id cozuldu: `b_hedong` -> `b_hezhongfu_hexi`
  - province `12356` icin duplicate barony id cozuldu: `b_qingshui` -> `b_qingshui_china`
  - `localization/replace/english/z_MB_titles_l_english.yml` icine `b_hezhongfu_hexi: "Hexi"` eklendi.
- Degisiklikler hem live hem test landed_titles dosyasina uygulandi.
- `works/tools/validate_east_mapping_pipeline.ps1` son durum:
  - `landed_titles live/test hash match = yes`
  - `missing playable province titles = 0`
  - `validation errors = 0`
  - `validation warnings = 0`
- `works/tools/audit_landed_title_county_source_from_map.py` son durum:
  - county rows: `3608`
  - high signal mismatches: `0`
- `county_source_fix_plan.csv` son dagilim:
  - `no_action`: `3312`
  - `manual_review`: `296`
- Sade `county_source_manual_worklist.csv` son dagilim:
  - toplam rows: `296`
  - `review`: `247`
  - `mixed`: `29`
  - `unknown`: `16`
  - `skip`: `3`
  - `ok`: `1` (`c_suzhou`, fix-plan manual_review kaldigi icin listede)

## 2026-04-22 Safe Cosmetic County Source Fixes

- Kullanici yalnizca kesin guvenli olan basit renk/isim/bosluk islerinin otomatik yapilmasini, zor/riskli islerin manuel kalmasini istedi.
- Yeni arac eklendi:
  - `works/tools/apply_safe_county_source_cosmetic_fixes.py`
- Arac yalnizca su kosullar birlikte saglanirsa uygular:
  - fix-plan `manual_review`
  - `expected_source` sadece `vanilla` veya `mod`
  - source/current/test county province listeleri birebir ayni
  - live/test current bloklari birebir ayni
  - `color` satirlari cikarildiginda source/current/test normalized bloklari birebir ayni
  - `color` satir sayilari esit
- Dry-run iki guvenli color-only satir buldu ve uygulandi:
  - `c_deqen`
  - `c_quqen`
- Uygulama raporu:
  - `works/analysis/generated/landed_titles_source_audit/county_source_safe_color_only_apply_report.csv`
- Son classification:
  - `apply_color_only`: `0`
  - `manual`: `294`
  - `skip`: `3314`
- Validator son durum:
  - `landed_titles live/test hash match = yes`
  - `missing playable province titles = 0`
  - `validation errors = 0`
  - `validation warnings = 0`
- County source audit son durum:
  - high signal mismatches: `0`
  - `manual_review`: `294`
  - `no_action`: `3314`
- Sade worklist son dagilim:
  - toplam rows: `294`
  - `review`: `245`
  - `mixed`: `29`
  - `unknown`: `16`
  - `skip`: `3`
  - `ok`: `1`

## 2026-04-22 Mixed Worklist Better Classification

- Kullanici worklist icinde `c_barkam` gibi kafa karistiran ama aslinda basit/accepted olabilecek satirlar oldugunu belirtti.
- `works/tools/apply_safe_county_source_cosmetic_fixes.py` genisletildi:
  - `mixed` satirlar icin vanilla ve mod best-match bloklari birlikte okunuyor.
  - Current/test/source province listeleri ayniysa ve `color` disi normalized blok ayniysa daha guvenli karar veriliyor.
  - Current renkleri vanilla/mod source renklerinden satir bazli geliyorsa `accept_mixed_color_composite` olarak siniflandiriliyor.
  - Current blok hem vanilla hem mod source ile birebir ayniysa `accept_mixed_current_matches_both_sources` olarak siniflandiriliyor.
- Yeni kolay aday raporu:
  - `works/analysis/generated/landed_titles_source_audit/county_source_simple_resolution_candidates.csv`
- Son kolay/accepted aday sayisi: `11`
  - `accept_mixed_current_matches_both_sources`: `5`
  - `accept_mixed_color_composite`: `6`
- `c_barkam` sonucu:
  - `accept_mixed_color_composite`
  - Sebep: province listesi ayni, color disi icerik ayni, current renkleri vanilla/mod source renklerinden olusan guvenli kompozit.
- Bu tur landed_titles dosyalarina dokunulmadi; sadece siniflandirma raporlari ve arac guncellendi.

## 2026-04-22 Accepted Candidates Worklist Filter

- `works/tools/build_county_source_manual_worklist.py` guncellendi.
- Yeni filtre:
  - `works/analysis/generated/landed_titles_source_audit/county_source_simple_resolution_candidates.csv` icindeki `decision = accept_*` county'leri ana manual worklist'ten dusurur.
  - Accepted satirlar kaybolmaz; simple candidates raporunda kalir.
  - Manuel not koruma mekanizmasi degismedi.
- Yeniden uretim sirasi:
  - `python .\works\tools\apply_safe_county_source_cosmetic_fixes.py`
  - `python .\works\tools\build_county_source_manual_worklist.py`
- Son sonuc:
  - `county_source_manual_worklist.csv` rows: `283`
  - accepted skipped: `11`
  - `county_source_simple_resolution_candidates.csv` rows: `11`
- Worklist son dagilim:
  - `review`: `245`
  - `mixed`: `18`
  - `unknown`: `16`
  - `skip`: `3`
  - `ok`: `1`
- `c_barkam` ana worklist'ten dustu; `county_source_simple_resolution_candidates.csv` icinde `accept_mixed_color_composite` olarak duruyor.
- Bu adim landed_titles dosyalarini degistirmedi.

## 2026-04-23 Mask Scope Title Relation Output Genisletmesi

- `works/tools/build_east_title_scope_from_province_mask.py` yeniden genisletildi.
- Yeni eklenen temel kabiliyetler:
  - `--mod-landed-titles` argumani
  - `mask_scope_reasons` kolonu
  - `title_source_origin` kolonu
- `title_source_origin` su degerleri tasir:
  - `vanilla`
  - `mod`
  - `both`
  - `unknown`
- Provenance hesaplamasi current Yusseter landed_titles ile Leviathon/orijinal mod landed_titles karsilastirmasindan uretilir.
- Manual-like cikti ve worklist ciktilari da bu yeni bilgileri tasiyacak sekilde genislestirildi.
- Guncel summary:
  - non-black mask rgb: `4813`
  - matched mask province: `4798`
  - unmatched rgb: `15`
  - unbound province: `1963`
  - mask non-barony title: `1329`
  - manual non-barony title: `1098`
  - `added_by_mask`: `256`
  - `removed_by_mask`: `25`
  - unchanged: `1073`
- Ana generated dosyalar:
  - `works/analysis/generated/title_relation_manual_validation/mask_east_scope/title_relation_master_manuel_mask_east_scope.csv`
  - `works/analysis/generated/title_relation_manual_validation/mask_east_scope/title_relation_master_manuel_mask_scope_manual_like.csv`
  - `works/analysis/generated/title_relation_manual_validation/mask_east_scope/title_relation_master_manuel_mask_scope_worklist.csv`

## 2026-04-23 title_relation_master_manuel_new staging anlami

- `title_relation_master_manuel_new.csv` generated `manual_like` dosyasindan turetilmis ama artik kullanicinin curated staging dosyasidir.
- Bu dosya authoritative merge staging olarak ele alinacak; generated `manual_like` sadece referans/sablon rolundedir.
- `mask_scope_change` kolonu icindeki:
  - `was_added_by_mask`
  - `was_removed_by_mask`
  satirlari baglayici merge kurali degil, yardimci metadata/not niteligindedir.
- Bu nedenle generated diff mantigi bire bir zorunlu kabul edilmeyecek; asil karar alani `source_title_id / mod_title_id / is_same_title_id` kolonlaridir.
- `added_by_mask + is_same_title_id = yes + mod_title_id bos` shorthand'i kullanici tarafindan bilerek birakildi.
- Bu shorthand daha sonra normalize edildi:
  - `mod_title_id = source_title_id`
  - etkilenen satir: `227`
- Normalizasyon sonrasi:
  - `mod_title_id bos + is_same_title_id = yes`: `0`
  - duplicate `source_title_id`: `0`
- `title_relation_master_manuel_new.csv` su an `1350` satirlik bir east-scope/staging subsetidir; tam `title_relation_master_manuel.csv` yerine gecen tam tablo degildir.
- Ana tabloya terfi mantigi:
  - ayni `source_title_id` satirlarini replace et
  - `new` icinde olup ana tabloda olmayan `source_title_id` satirlarini ekle
  - scope disi kalan diger ana tablo satirlarini koru

## 2026-04-23 Mask Scope'ta cikmayan MBP county title notu

- `c_shanzhou_mbp` ve `c_suzhou_mbp` current landed_titles icinde bulunmalarina ragmen generated `manual_like` icinde cikmadi.
- Bunun nedeni script hatasi degil; bu title'lar:
  - mevcut `title_relation_master_manuel.csv` icinde yok
  - ve mask province scope'a da girmiyor
- Bu nedenle generated `mask_titles` setine hic dahil olmuyorlar.
- Sonuc:
  - `c_shanzhou_mbp`
  - `c_suzhou_mbp`
  gibi `modlu_kalan` kokenli ekstra current title'larin kullanici tarafindan elle `title_relation_master_manuel_new.csv` icine eklenmesi dogru ve beklenen davranistir.

## 2026-04-23 Hafiza Operasyon Notu

- Son birkaç title-relation / mask-scope turunda netlesen bazi bilgiler gecici sohbet baglaminda kaldi ve `hafiza.md`ye gec yazildi.
- Bu, kural degisikligi degil operasyon takibi eksigidir.
- Bundan sonra `sadece soru` olmayan ilk uygun turda birikmis net kararlar once `hafiza.md`ye yazilacak, sonra yeni uygulama isine gecilecek.

## 2026-04-23 title_relation_master_manuel_new ana tablo terfisi

- `title_relation_master_manuel_new.csv` ana tabloya source-id bazli merge ile terfi edildi.
- Uygulanan kural:
  - ana tabloda ayni `source_title_id` varsa `new` satiri ile replace et
  - `new` icinde olup ana tabloda olmayan `source_title_id` satirlarini sona ekle
  - `new` scope'u disindaki eski ana tablo satirlarini koru
- Merge sonucu:
  - replaced: `1082`
  - kept: `2695`
  - appended new source ids: `268`
  - final manual row count: `4045`
- Son yapisal kontrol:
  - duplicate `source_title_id`: `0`
  - header korunmus durumda:
    - `source_title_id, mod_title_id, is_same_title_id,`
- Yeni eklenen / merge ile ana tabloya giren ornek source'lar:
  - `c_shanzhou_mbp -> c_shanzhou`
  - `c_suzhou_mbp -> c_suzhou`
  - `e_liao -> e_liao`
  - `k_guishi -> k_guishi`

## 2026-04-23 title_relation validator sonrasi yeni aktif hata havuzu

- `works/tools/validate_title_relation_manual.py` merge sonrasi tekrar calistirildi.
- Guncel summary:
  - manual rows: `4045`
  - errors: `166`
  - warnings: `874`
- Error dagilimi:
  - `duplicate_mod_title_without_second`: `111`
  - `source_title_missing_in_yusseter_landed_titles`: `53`
  - `mod_title_missing_in_leviathon_landed_titles`: `1`
  - `is_same_value_incorrect`: `1`
- Warning dagilimi:
  - `parent_mapping_mismatch`: `596`
  - `source_title_extra_in_manual_vs_master`: `269`
  - `source_title_duplicate_in_landed_titles`: `5`
  - `mod_title_duplicate_in_landed_titles`: `4`
- Yeni yorum:
  - `source_title_extra_in_manual_vs_master = 269` dogal olarak `new` subsetten gelen yeni source satirlarini yansitiyor.
  - Asil aktif mekanik cleanup havuzu su iki gruptur:
    - `111` adet duplicate mod title / `(second)` isaretleme eksigi
    - `53` adet current Yusseter landed_titles icinde bulunmayan legacy `source_title_id`
- Tekil mekanik satirlar:
  - `c_langshan` satirinda `mod_title_id = c_langshan` iken `is_same_title_id = no`; validator `expected=yes` dedi.
  - `c_wuyuan_shuofang_china` tokeni Leviathon/orijinal mod landed_titles icinde bulunmuyor.
- Bu asamadan sonraki en dogru title-relation isi:
  - downstream rewrite degil
  - once validatordaki `166` error'u bilincli sekilde temizlemek

## 2026-04-24 title_relation_master_manuel_new non-barony scope ayrimi

- Kullanici current calisma dosyasinin `title_relation_master_manuel_new.csv` oldugunu netlestirdi.
- Scope duzeltmesi:
  - sadece `e_/k_/d_/c_` degil, `h_` de scope icinde
  - `b_` barony satirlari bu asamada bilerek scope disi
- Onemli ayrim:
  - onceki `53 source_title_missing_in_yusseter_landed_titles` ve benzeri legacy yorumlar `title_relation_master_manuel.csv` baglamindaydi
  - bunlar `title_relation_master_manuel_new.csv` icin aktif cleanup havuzu olarak ele alinmayacak
- `title_relation_master_manuel_new.csv` tier dagilimi:
  - `h_ = 2`
  - `e_ = 64`
  - `k_ = 75`
  - `d_ = 318`
  - `c_ = 891`
  - toplam `1350`
- Bu dosyada `mod_title_id` bos satir yok:
  - dolu `mod_title_id = 1350`
  - bos `mod_title_id = 0`
  - `*there_is_no* = 0`
- `mask_scope_change` dagilimi:
  - bos `1074`
  - `added_by_mask = 251`
  - `was_added_by_mask = 1`
  - `was_removed_by_mask = 24`
- `title_relation_master_manuel_new.csv` 4. kolon olarak `mask_scope_change` tasidigi icin validator dogrudan bu dosyaya degil, turetilmis 3 kolonlu input'a karsı kosuldu:
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/title_relation_master_manuel_new_validation_input.csv`
- Ayrik validation output klasoru:
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/`
- Bu scope icin validator sonucu:
  - `errors = 2699`
  - `warnings = 673`
- En buyuk `error` sinifi:
  - `source_title_missing_from_manual_vs_master = 2695`
  - yorum: bu beklenen subset gürültüsü; cunku `title_relation_master_manuel_new.csv` tam `3776` satirlik ana tablo degil, scoped working subset
- Bu scope icin kucuk ve gercek mekanik hata havuzu:
  - `duplicate_mod_title_without_second = 4`
  - satirlar:
    - `k_raole -> k_liao_zhongjing`
    - `k_liao_zhongjing -> k_liao_zhongjing`
    - `d_xingfeng -> d_zhaowu`
    - `d_zhaowu -> d_zhaowu`
- `source_title_extra_in_manual_vs_master = 269` bu scope'ta beklenen ve yararli sinif olarak ayri not edildi.
- Bu `269` extra row dagilimi:
  - `h_ = 1`
  - `e_ = 40`
  - `k_ = 19`
  - `d_ = 118`
  - `c_ = 91`
- Bu `269` extra row'un `mask_scope_change` dagilimi:
  - bos `2`
  - `added_by_mask = 251`
  - `was_added_by_mask = 1`
  - `was_removed_by_mask = 15`
- Kullanici icin ek inceleme dosyalari uretildi:
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/title_relation_master_manuel_new_scope_summary.md`
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/title_relation_master_manuel_new_duplicate_mod_worklist.csv`
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/title_relation_master_manuel_new_extra_rows.csv`
- Bundan sonraki dogru teknik yol:
  - yalnizca `title_relation_master_manuel_new.csv` uzerinde devam etmek
  - `h_/e_/k_/d_/c_` scope'unu korumak
  - ilk mekanik cleanup hedefi olarak 4 satirlik duplicate mod havuzunu incelemek
  - `b_` ve eski `title_relation_master_manuel.csv` legacy cleanup havuzunu simdilik scope disi tutmak
- `2026-04-24` ayni scope icinde 4 satirlik duplicate-mod mekanik havuz kapatildi.
- Karar:
  - `k_liao_zhongjing -> k_liao_zhongjing` ve `d_zhaowu -> d_zhaowu` primary/exact satir olarak kaldi
  - `k_raole -> k_liao_zhongjing` ve `d_xingfeng -> d_zhaowu` secondary donor gibi ele alinip `(second)` ile isaretlendi:
    - `k_raole -> k_liao_zhongjing (second)`
    - `d_xingfeng -> d_zhaowu (second)`
- Bu degisiklik `title_relation_master_manuel_new.csv` icinde yapildi.
- Ardindan `new scope clean` validator tekrar kosuldu:
  - `errors = 2695`
  - `warnings = 673`
  - `duplicate_mod_title_without_second = 0`
  - `allowed:secondary_uses_marked = 75`
- Sonuc:
  - bu scope icinde mekanik duplicate-mod blocker kapandi
  - sonraki gercek review havuzu:
    - `source_title_extra_in_manual_vs_master = 269`
    - `parent_mapping_mismatch = 395`
- `2026-04-24` `title_relation_master_manuel_new.csv` icindeki `269 extra` satir daha da daraltildi.
- Kritik daraltma:
  - `extra` satirlar icinde `is_same_title_id = no` olan aktif manuel havuz `23` satir
  - bunun `13` tanesi `parent_mapping_mismatch` tasiyor
  - `10` tanesi parent mismatch tasimadigi icin `provisional_keep` adayi gibi okunuyor
- Bu is icin yeni dosyalar uretildi:
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/title_relation_master_manuel_new_extra_no_worklist.csv`
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/title_relation_master_manuel_new_extra_no_parent_mismatch_yes.csv`
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/title_relation_master_manuel_new_extra_no_parent_mismatch_no.csv`
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/title_relation_master_manuel_new_extra_no_recommendations.csv`
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/title_relation_master_manuel_new_extra_no_recommendations.md`
- `23 no` satirin dagilimi:
  - `added_by_mask = 21`
  - bos `mask_scope_change = 2`
- Bos mask satirlari:
  - `c_shanzhou_mbp -> c_shanzhou`
  - `c_suzhou_mbp -> c_suzhou`
- `13 review_first` satiri cluster bazinda toplandi:
  - `d_shuofang = 5`
  - `d_xiasui = 4`
  - `d_langshan = 2`
  - `d_tiande = 2`
- Yapısal yorum:
  - bu mismatch havuzu agirlikla tekil rastgele hata degil
  - `k_xia` altindan `k_xia_china`, `k_yinshan_china` veya `d_ordos_china` tarafina kayan sistematik cluster migration gorunumu var
- Recommendation siniflandirmasi:
  - `review_first = 13`
  - `provisional_keep = 10`
- Recommendation note dagilimi:
  - `cross_duchy_shift_to_ordos_cluster = 3`
  - `systematic_k_xia_to_k_xia_china_shift = 3`
  - `systematic_k_xia_to_k_yinshan_china_shift = 1`
  - `parent_chain_review_needed = 6`
  - `mbp_current_county_variant_without_parent_mismatch = 2`
  - `non_self_map_without_parent_mismatch = 8`
- Bundan sonraki en dogru teknik sira:
  - `13 review_first` satiri cluster bazinda incelemek
  - ilk mantikli cluster: `d_shuofang`
- `2026-04-24` `13 review_first` havuzundaki ilk buyuk cluster `d_shuofang` ayri incelendi.
- Yeni not dosyasi:
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/title_relation_master_manuel_new_cluster_d_shuofang_notes.md`
- `d_shuofang` cluster sonucu:
  - toplam satir `5`
  - tek parent-rename degil; en az `3` farkli mod-parent bucket'a dagiliyor
  - dagilim:
    - `k_xia_china`: `1`
    - `d_xia`: `2`
    - `d_longxi_china`: `2`
- Satirlar:
  - `d_shuofang -> d_shuofang_china`
  - `c_lingzhou -> c_shunzhou`
  - `c_huaiyuan -> c_xingqing`
  - `c_huizhou -> c_huizhou_china`
  - `c_wulan -> c_huizhou_china (second)`
- Teknik yorum:
  - bu cluster `single exact rename` gibi ele alinmamalı
  - daha dogru okuma: `split migration problem`
  - yani `d_shuofang` altindaki county seti mod tarafinda tek bir duchy altinda korunmuyor; parcali dagiliyor
- Bundan sonraki mantikli cluster inceleme sirasi:
  - `d_xiasui`
  - sonra `d_langshan`
  - sonra `d_tiande`

## 2026-04-24 Iletisim ve ara-guncelleme kurali

- Kullanici isleme baslarken `ck3-modding kapsamiyla basliyorum` gibi skill/kapsam duyurulari istemiyor.
- Bundan sonra bu tur meta duyurular ara mesajlarda yazilmayacak.
- Ara mesajlar yalnizca gercekten is takibini etkileyen durumlarda verilecek:
  - onemli yeni bulgu
  - karar gerektiren risk
  - dosya duzenlemesi oncesi somut niyet
  - islem sonucu veya dogrulama sonucu
- Rutin "su dosyayi okuyorum", "veri modelini kuruyorum" gibi dusuk sinyalli ara mesajlar azaltilacak.
- Skill kullanimi gerekiyorsa dahili olarak uygulanacak; kullaniciya ancak sonuca veya riske etkisi varsa bildirilecek.

## 2026-04-24 Landed Title Capital Source Audit Baslangici

- Kullanici parent-chain mismatch odaginin bu is icin yanlis oncelik oldugunu netlestirdi.
- Dogru denetim modeli:
  - current/Yusseter title bulunur
  - bu title'in source'u tespit edilir:
    - `modlu_kalan` ise Leviathon/asıl mod landed_titles source'u kullanilir
    - `orijinal_dogu` ise vanilla/orijinal landed_titles source'u kullanilir
  - source title'in `capital = c_*` degeri okunur
  - source capital title'in current/Yusseter karsiligi `title_relation_master_manuel_new.csv` ters mapping'iyle bulunur
  - current title'daki mevcut `capital = c_*` ile beklenen current capital karsilastirilir
- Ornek dogrulanan hata:
  - current `d_shangqing` capital'i `c_fuzhou`
  - Leviathon/asıl mod source `d_shangqing` capital'i `c_fuzhou_qin_china`
  - `title_relation_master_manuel_new.csv` icinde `c_fuzhou_qin_china` current karsiligi `c_fuzhou_5`
  - beklenen current capital `c_fuzhou_5`
  - bu nedenle current `d_shangqing = capital c_fuzhou` hatali gorunuyor
- Yeni read-only audit araci eklendi:
  - `works/tools/audit_landed_title_capitals_from_source.py`
- Araç canli `00_landed_titles.txt` dosyasini degistirmez; sadece rapor uretir.
- Uretilen rapor klasoru:
  - `works/analysis/generated/landed_title_capital_source_audit/`
- Ana raporlar:
  - `landed_title_capital_source_audit.csv`
  - `landed_title_capital_source_title_summary.csv`
  - `landed_title_capital_source_title_mismatches.csv`
  - `landed_title_capital_source_single_fix_candidates.csv`
  - `landed_title_capital_source_candidate_mismatches.csv`
  - `landed_title_capital_source_needs_review.csv`
  - `landed_title_capital_source_audit_summary.md`
- Ilk audit sonucu:
  - source-candidate row: `629`
  - current title: `439`
  - candidate status counts:
    - `ok = 531`
    - `mismatch = 35`
    - `missing_expected_current_capital_mapping = 25`
    - `ambiguous_expected_current_capital = 3`
    - `source_has_no_direct_capital = 35`
  - current-title aggregate counts:
    - `ok_via_some_source = 409`
    - `mismatch_no_source_ok = 19`
    - `missing_mapping_no_source_ok = 9`
    - `ambiguous_no_source_ok = 2`
- Tek beklenen current capital veren potansiyel fix adayi:
  - `18`
- Birden fazla beklenen capital adayi olan satir:
  - `c_nf_xia_liang`
- Onemli not:
  - bu rapor henuz otomatik apply icin kullanilmayacak
  - ozellikle `both` source-origin ve duplicate title bulunan satirlarda manuel kontrol gerekir
  - ama `d_shangqing -> c_fuzhou_5` gibi tekil ve zinciri temiz vakalar yuksek sinyal olarak kabul edilebilir
- Kullanici daha okunabilir sade worklist istedi.
- `audit_landed_title_capitals_from_source.py` artik 4 kolonlu sade rapor da uretiyor:
  - `works/analysis/generated/landed_title_capital_source_audit/landed_title_capital_manual_simple.csv`
- Sade rapor kolonlari:
  - `title_id`
  - `current_capital`
  - `expected_capital`
  - `status`
- Sade rapor status anlamlari:
  - `wrong`: beklenen capital tekil olarak hesaplandi ve current capital farkli
  - `uncertain`: source capital biliniyor ama current karsilik `title_relation_master_manuel_new.csv` icinde yok
  - `ambiguous`: birden fazla beklenen current capital adayi var
- Ilk sade rapor sayilari:
  - `wrong = 18`
  - `uncertain = 9`
  - `ambiguous = 3`
- `d_confucius` bu sade raporda `uncertain` olarak yer aliyor:
  - current capital `c_yanzhou`
  - source capital `c_kongmeng_china`
  - `c_kongmeng_china` icin current mapping bilinmedigi icin `expected_capital` bos

## 2026-04-24 Landed Title Capital Audit Effective Capital Guncellemesi

- Kullanici iki eksik risk sinifini netlestirdi:
  - `both` source-origin vakalarinda mod ve vanilla source capitalleri farkliysa, current bir kaynagi dogrulasa bile bu risk olarak rapora girmeli
  - `h_ / e_ / k_ / d_` title'larda direct `capital = c_*` yoksa, CK3 mantiginda effective capital hiyerarsi altindaki ilk/en ust county olarak okunmali
- `c_` ve `b_` title'lar bu capital-owner audit hedefinden cikarildi; denetim hedef scope'u:
  - `h_`
  - `e_`
  - `k_`
  - `d_`
- `works/tools/audit_landed_title_capitals_from_source.py` read-only kalacak sekilde genislestirildi.
- Yeni effective capital kuralı:
  - once direct `capital = c_*`
  - yoksa title altindaki ilk descendant `c_*`
  - `c_*` bloklari sadece hesaplama yardimcisi olarak kullanilir, audit hedefi degildir
- `source_conflict` kuralı eklendi:
  - bir title icin secilen mod/vanilla source adaylari farkli effective capital sonucuna gidiyorsa rapora girer
  - conflict karsilastirmasi mumkunse source title id'leriyle degil, `title_relation_master_manuel_new.csv` uzerinden bulunan current karsiliklariyla yapilir
  - mapping yoksa ilgili source capital `?` ile belirsiz olarak rapora yazilir
- Sade rapor yine 4 kolonlu tutuldu:
  - `title_id`
  - `current_capital`
  - `expected_capital`
  - `status`
- Sade rapor status anlamlari artik:
  - `wrong`: tekil beklenen current capital var ve current farkli
  - `uncertain`: source capital biliniyor ama current karsilik mapping'de yok
  - `ambiguous`: birden fazla beklenen current capital adayi var
  - `source_conflict`: mod/vanilla source effective capital karari farkli veya mapping nedeniyle riskli
  - `missing_effective_capital`: current/source tarafinda direct veya descendant county ile effective capital bulunamadi
- Yeni ek rapor:
  - `works/analysis/generated/landed_title_capital_source_audit/landed_title_capital_source_title_source_conflicts.csv`
- Guncel audit sonucu:
  - source-candidate row: `657`
  - current title: `459`
  - source candidate status counts:
    - `ok = 572`
    - `mismatch = 43`
    - `missing_expected_current_capital_mapping = 34`
    - `ambiguous_expected_current_capital = 3`
    - `missing_effective_capital = 5`
  - current-title aggregate counts:
    - `ok_via_some_source = 378`
    - `source_conflict = 53`
    - `mismatch_no_source_ok = 15`
    - `missing_mapping_no_source_ok = 9`
    - `ambiguous_no_source_ok = 2`
    - `missing_effective_capital = 2`
- Guncel sade rapor:
  - `works/analysis/generated/landed_title_capital_source_audit/landed_title_capital_manual_simple.csv`
  - toplam satir: `81`
  - `source_conflict = 53`
  - `wrong = 15`
  - `uncertain = 9`
  - `ambiguous = 2`
  - `missing_effective_capital = 2`
- Ornekler:
  - `d_shangqing,c_fuzhou,c_fuzhou_5,wrong`
  - `d_confucius,c_yanzhou,,uncertain`
  - `d_kinai,c_yamashiro,mod:c_yamato | vanilla:c_yamashiro,source_conflict`
- Bu turda `common/landed_titles/00_landed_titles.txt` veya `test_files` kopyalari degistirilmedi; yalnizca audit scripti ve generated raporlar guncellendi.

## 2026-04-24 Landed Title Capital Manual Apply Turu

- Kullanici `landed_title_capital_manual_new.csv` dosyasini manuel doldurdu.
- Kullanici ayrica `common/landed_titles/00_landed_titles.txt` icinde bazi capital/title duzeltmeleri yaptigini bildirdi.
- `landed_title_capital_manual_new.csv` son manuel calisma kolonlari:
  - `title_id`
  - `current_capital`
  - `yusseter_selected_capital`
- Manuel secimleri current landed_titles'a uygulamak icin yeni read/update araci eklendi:
  - `works/tools/apply_landed_title_capital_manual.py`
- Bu arac:
  - `landed_title_capital_manual_new.csv` icindeki `yusseter_selected_capital` degerlerini okur
  - current `common/landed_titles/00_landed_titles.txt` icindeki ilgili `h_/e_/k_/d_` title direct/effective capital degerleriyle karsilastirir
  - direct capital varsa farkliysa satiri gunceller
  - direct capital yok ama descendant effective capital zaten secili degerse dosyaya gereksiz direct capital eklemez
  - rapor uretir
- Uygulama raporlari:
  - `works/analysis/generated/landed_title_capital_manual_apply/landed_title_capital_manual_apply_report.csv`
  - `works/analysis/generated/landed_title_capital_manual_apply/landed_title_capital_manual_apply_summary.md`
- Uygulama sonucu:
  - toplam manuel satir: `81`
  - `kept = 58`
  - `kept_effective = 3`
  - `updated = 20`
- Guncellenen direct capital satirlari:
  - `d_baosai: c_yanzhou_3 -> c_yan_an`
  - `d_jianxiong: c_jinzhou_1 -> c_pingyang`
  - `d_laamp_ding_hui: c_weizhou -> c_henan`
  - `d_laamp_frontier_guardians: c_taiyuan -> c_shangxi`
  - `d_laamp_hanshantong1337: c_yingzhou -> c_yingzhou_2`
  - `d_laamp_liangshan_band: c_qiongzhou -> c_yunzhou`
  - `d_laamp_wandering_lute: c_jizhou -> c_jizhou_3`
  - `d_laamp_youliang1337: c_yuezhou -> c_yuezhou_1`
  - `d_liangzhou: c_guazhou -> c_liangzhou`
  - `d_shangqing: c_fuzhou -> c_fuzhou_5`
  - `d_shanzhou: c_hezhou_china -> c_shanzhou_mbp`
  - `d_weisheng: c_dengzhou -> c_dengzhou_1`
  - `d_zhaowu: c_xingzhou -> c_xingqing`
  - `d_zhengyi: c_fuzhou -> c_fuzhou_5`
  - `e_min: c_fuzhou -> c_fuzhou_1`
  - `e_wei: c_yunzhou -> c_datong_2`
  - `e_wei3: c_yunzhou -> c_datong_2`
  - `e_xi_xia: c_lingzhou -> c_huaiyuan`
  - `k_tsongkha: c_shanzhou -> c_shanzhou_mbp`
  - `k_zhengyi: c_fuzhou -> c_fuzhou_5`
- `common/landed_titles/00_landed_titles.txt` degistigi icin proje kuralina gore:
  - `test_files/common/landed_titles/00_landed_titles.txt`
  canli dosyayla senkronlandi.
- Capital audit yeniden calistirildi:
  - `wrong` satiri kalmadi
  - current-title aggregate:
    - `ok_via_some_source = 396`
    - `source_conflict = 54`
    - `missing_mapping_no_source_ok = 9`
  - source-candidate status:
    - `ok = 593`
    - `mismatch = 28`
    - `missing_expected_current_capital_mapping = 34`
    - `ambiguous_expected_current_capital = 1`
    - `missing_effective_capital = 3`
- Genel validator sonucu:
  - `validation errors = 0`
  - `validation warnings = 0`
  - `missing playable province titles = 0`
  - `landed_titles live/test hash match = yes`
- Bu turda validator sirasinda capital konusundan bagimsiz bir `default.map` syntax problemi de goruldu:
  - eski satir: `impassable_mountains RANGE { 14646 14660 }`
  - duzeltme: `impassable_mountains = RANGE { 14646 14660 }`
  - ayni duzeltme `test_files/map_data/default.map` icine de yansitildi
  - bu duzeltme sonrasi validator temiz dondu

## 2026-04-24 Landed Title Source Identity ve Parent Audit Baslangici

- Kullanici `both` degerinin gercek source olamayacagini netlestirdi.
- Bundan sonraki source kimligi icin karar kategorileri:
  - `modlu_kalan`
  - `orijinal_dogu`
  - `manual_review`
- `both` yalnizca teknik sinyal olabilir; nihai source karari olarak kullanilmayacak.
- Kullanici ayrica source karari icin yalnizca province provenance yeterli degil dedi.
- Yeni source tespit modeli:
  - title'in kendi block metadata'si incelenecek
  - alt hiyerarsik title bloklari source-body karsilastirmasina dahil edilmeyecek
  - `color`, `capital`, `can_create`, `definite_form`, `can_be_named_after_dynasty` gibi title'in kendi govde ayarlari source sinyali olacak
  - capital sinyali ayri hesaplanacak
  - alt descendant barony province'lerinin provenance dagilimi yardimci sinyal olacak
  - province provenance sadece dogu maskesi icindeki province'ler uzerinden sayilacak
- Dogu maskesi:
  - `works/map_data_sources/provinces_birlesim_dogu 2026-04-19.png`
- Mask RGB -> final province id:
  - `map_data/definition.csv`
- Province provenance:
  - `works/analysis/generated/final_modlu_tracking_preserve_old_ids.csv`
  - `works/analysis/generated/final_orijinal_tracking_preserve_old_ids.csv`
- Yeni read-only source identity araci:
  - `works/tools/audit_landed_title_source_identity.py`
- Urettigi raporlar:
  - `works/analysis/generated/landed_title_source_identity/landed_title_source_identity_audit.csv`
  - `works/analysis/generated/landed_title_source_identity/landed_title_source_identity_manual_simple.csv`
  - `works/analysis/generated/landed_title_source_identity/landed_title_source_identity_review.csv`
  - `works/analysis/generated/landed_title_source_identity/landed_title_source_identity_summary.md`
- Source identity audit sonucu:
  - satir: `1350`
  - mask non-black RGB: `4813`
  - mask province id: `4797`
  - mask unmatched RGB: `16`
  - source karar dagilimi:
    - `orijinal_dogu = 1151`
    - `modlu_kalan = 146`
    - `manual_review = 53`
  - confidence dagilimi:
    - `high = 1002`
    - `medium = 286`
    - `low = 62`
- `manual_review` kalanlari agirlikli olarak:
  - mod ve vanilla block/capital ayni veya cok yakin gorundugu halde province/body sinyalleri kesin ayrim yaptirmayan title'lar
  - bazi titular/laamp veya top-level title'lar
  - bazi Liao/Gobi/Tibet gibi body/capital ve province sinyalleri ters yon gosteren vakalar
- Source identity raporundan sonra parent audit icin yeni read-only arac eklendi:
  - `works/tools/audit_landed_title_parent_from_source.py`
- Parent audit mantigi:
  - current title'in current parent'i okunur
  - source identity karari `modlu_kalan` ise mod source parent'i alinir
  - source identity karari `orijinal_dogu` ise vanilla source parent'i alinir
  - mod source parent current karsiliga `title_relation_master_manuel_new.csv` ters mapping'iyle cevrilir
  - vanilla source parent current dosyada ayni id ile aranir
  - current parent ile beklenen parent karsilastirilir
- Parent audit raporlari:
  - `works/analysis/generated/landed_title_parent_source_audit/landed_title_parent_source_audit.csv`
  - `works/analysis/generated/landed_title_parent_source_audit/landed_title_parent_manual_simple.csv`
  - `works/analysis/generated/landed_title_parent_source_audit/landed_title_parent_wrong.csv`
  - `works/analysis/generated/landed_title_parent_source_audit/landed_title_parent_source_audit_summary.md`
- Parent audit sonucu:
  - toplam satir: `1350`
  - `ok = 1267`
  - `wrong = 22`
  - `missing_parent_mapping = 8`
  - `manual_review_source = 53`
- Ilk `wrong` ornekleri:
  - `d_yanyun_yuyi`: current parent `k_khitan`, expected `k_raole`
  - `k_guishi`: current parent `e_yongliang`, expected `e_xi_xia`
  - `d_fengxiang`: current parent `k_longxi_china`, expected `k_guannei`
  - `d_ganzhou`: current parent `k_guishi`, expected `k_xia`
  - `k_lhomon`: current parent `e_himalaya`, expected `e_tibet`
  - `e_xi_xia`: current parent bos, expected `h_china`
- Bu tur read-only yapildi:
  - `common/landed_titles/00_landed_titles.txt` degistirilmedi
  - `test_files` degistirilmedi
- Sonraki dogru adim:
  - once `landed_title_parent_wrong.csv` ve `missing_parent_mapping` satirlari manuel/teknik olarak incelenecek
  - parent rewrite uygulamasina gecmeden once `manual_review_source = 53` kaynak karar havuzu ayrica ele alinacak

## 2026-04-24 East Kingdom Closure Scope Duzeltmesi

- Kullanici `county_source_audit.csv` dosyasini parent/source audit icin ana scope yapmak fazla genis olur diye uyardi.
- Yeni kabul edilen scope modeli:
  - baslangic seed'i `provinces_birlesim_dogu 2026-04-19.png` maskesindeki province'ler olacak
  - mask province id'leri `map_data/definition.csv` ile bulunacak
  - bu province'lere bagli `b_` barony'ler current `00_landed_titles.txt` icinden bulunacak
  - her seed barony'den yukari `k_` title'a cikilacak
  - bulunan `k_` title'in altindaki tum descendant title'lar audit scope'a eklenecek
  - `h_` veya `e_` altinin tamamini closure'a almak yok; closure siniri `k_`
- Bu sayede maskin birebir icinde olmayan ama dogu `k_` closure icinde kalan sinir title'lari da yakalanacak.
- Kullanici ornegi:
  - current `c_yijinai` parent'i `d_juyan`
  - Leviathon/asıl modda `c_yijinai` parent'i `d_yijinai`
  - `c_yijinai` eski `title_relation_master_manuel_new.csv` input kapsaminda olmadigi icin onceki parent audit'ten kacmisti
- Yeni scope araci eklendi:
  - `works/tools/build_east_kingdom_closure_scope.py`
- Urettigi raporlar:
  - `works/analysis/generated/east_kingdom_closure_scope/east_kingdom_closure_titles.csv`
  - `works/analysis/generated/east_kingdom_closure_scope/east_kingdom_closure_seed_baronies.csv`
  - `works/analysis/generated/east_kingdom_closure_scope/east_kingdom_closure_summary.md`
- Closure scope sonucu:
  - mask non-black RGB: `4813`
  - mask province IDs: `4797`
  - mask unmatched RGB: `16`
  - seed baronies: `2835`
  - closure kingdoms: `65`
  - closure titles: `4397`
  - seed baronies without `k_` ancestor: `0`
  - closure title tier counts:
    - `b = 3116`
    - `c = 961`
    - `d = 255`
    - `k = 65`
- `works/tools/audit_landed_title_source_identity.py` genislestirildi:
  - artik `east_kingdom_closure_titles.csv` dosyasini opsiyonel ek scope olarak okur
  - `title_relation_master_manuel_new.csv` icinde olmayan closure title'lari da audit input'una ekler
  - mod tarafinda ayni title id varsa fallback mod candidate olarak kullanir
- Yeni source identity sonucu:
  - satir: `1441`
  - `orijinal_dogu = 1148`
  - `modlu_kalan = 195`
  - `manual_review = 98`
  - confidence:
    - `high = 1052`
    - `medium = 282`
    - `low = 107`
- `works/tools/audit_landed_title_parent_from_source.py` genislestirildi:
  - parent audit artik source identity audit satirlarinin tamamini input alir
  - manual csv ile sinirli kalmaz
  - `missing_parent_mapping` durumunda sade raporda raw source parent da gorunur hale getirildi
- Yeni parent audit sonucu:
  - satir: `1441`
  - `ok = 1309`
  - `wrong = 23`
  - `missing_parent_mapping = 11`
  - `manual_review_source = 98`
- `c_yijinai` artik yakalaniyor:
  - source decision: `modlu_kalan`
  - confidence: `high`
  - source title: `c_yijinai`
  - source parent: `d_yijinai`
  - current parent: `d_juyan`
  - status: `missing_parent_mapping`
  - sade rapor satiri:
    - `c_yijinai,d_juyan,modlu_kalan:d_yijinai?,missing_parent_mapping`
- Bu tur read-only:
  - `common/landed_titles/00_landed_titles.txt` degistirilmedi
  - `test_files` degistirilmedi

## 2026-04-24 East Empire Closure Karsilastirma Turu

- Kullanici ayni closure mantiginin `k_` yerine `e_` seviyesinde de denenmesini istedi.
- `works/tools/build_east_kingdom_closure_scope.py` genislestirildi:
  - yeni arguman: `--closure-tier k|e`
  - default halen `k`
  - `e` kullanildiginda seed barony'den ilk `e_` ancestor'a cikilip o `e_` altindaki tum descendant title'lar scope'a alinir
- `k_` closure raporlari korunarak ayri `e_` closure cikti klasoru uretildi:
  - `works/analysis/generated/east_empire_closure_scope/`
- `e_` closure sonucu:
  - mask non-black RGB: `4813`
  - mask province IDs: `4797`
  - mask unmatched RGB: `16`
  - closure tier: `e`
  - seed baronies: `2835`
  - closure ancestors: `20`
  - closure titles: `5156`
  - seed baronies without closure ancestor: `0`
  - tier counts:
    - `b = 3605`
    - `c = 1129`
    - `d = 309`
    - `k = 93`
    - `e = 20`
- `e_` closure source identity ayri klasore uretildi:
  - `works/analysis/generated/landed_title_source_identity_empire_closure/`
- `e_` closure source identity sonucu:
  - satir: `1686`
  - `orijinal_dogu = 1147`
  - `modlu_kalan = 362`
  - `manual_review = 177`
  - confidence:
    - `high = 1219`
    - `medium = 280`
    - `low = 187`
- `e_` closure parent audit ayri klasore uretildi:
  - `works/analysis/generated/landed_title_parent_source_audit_empire_closure/`
- `e_` closure parent audit sonucu:
  - satir: `1686`
  - `ok = 1472`
  - `wrong = 23`
  - `missing_parent_mapping = 14`
  - `manual_review_source = 177`
- `k_` closure ile karsilastirma:
  - `k_` closure titles: `4397`
  - `e_` closure titles: `5156`
  - `e_` closure, `k_` closure'a gore `759` ek title getiriyor
  - non-ok sade parent satiri:
    - `k_` closure: `132`
    - `e_` closure: `214`
    - ek non-ok: `82`
  - `wrong` sayisi degismedi:
    - `k_` closure: `23`
    - `e_` closure: `23`
- Yorum:
  - `e_` closure daha genis ve daha gurultulu
  - eklenen non-ok satirlarin buyuk kismi `manual_review_source`
  - ornek ek gurultu: `e_himalaya`, `e_bengal` gibi imparatorluk closure'i altindaki daha batili/komsu kingdom-county bloklari
  - ana parent-hata havuzu `k_` closure ile zaten yakalaniyor gibi gorunuyor
- Bu tur read-only:
  - `common/landed_titles/00_landed_titles.txt` degistirilmedi
  - `test_files` degistirilmedi

## 2026-04-25 Landed Title Parent Manual Apply

- Kullanici `landed_title_parent_manual_new.csv` dosyasini manuel karar dosyasi olarak olusturdu.
- Karar kolonu: `yusseter_selected_parent`.
- Manuel CSV mevcut `00_landed_titles.txt` ile karsilastirildi:
  - baslangicta `138` satir vardi
  - `117` satir zaten dosya ile uyumluydu
  - `21` satir farkliydi
- Otomatik uygulama:
  - hedef parent'i mevcut olan `16` title blogu tasindi
  - `4` satir `d_yijinai` dosyada olmadigi icin bloke kaldi:
    - `c_yijinai`
    - `c_wentugaole`
    - `c_heihe`
    - `c_mazongshan`
- Validator ayrica gercek tier hatasi yakaladi:
  - `d_SW_heicheziguo` yanlislikla `d_em_wuguguo` altindaydi
  - `d_SW_heicheziguo` `k_shiwei` altina tasindi
- `common/landed_titles/00_landed_titles.txt` degistigi icin ayni dosya `test_files/common/landed_titles/00_landed_titles.txt` ile senkronlandi.
- Son dogrulama:
  - `landed_titles live/test hash match = yes`
  - `missing playable province titles = 0`
  - `validation errors = 0`
  - `validation warnings = 0`
- Son parent audit (`k_` closure):
  - satir: `1441`
  - `ok = 1312`
  - `wrong = 22`
  - `missing_parent_mapping = 10`
  - `manual_review_source = 97`
- Uretilen ana rapor:
  - `works/analysis/generated/landed_title_parent_manual_apply/landed_title_parent_manual_apply_report.csv`

## 2026-04-25 County Culture/Religion Overlay Blocker Incelemesi ve Cozum Kararlari

- Kullanici `county_culture_religion_overlay_blockers_readable.csv` icin okunabilir, az kolonlu CSV istedi.
  - Dosya cok kolonlu olmamali.
  - Kabul edilen readable kolonlar:
    - `status`
    - `target_county`
    - `source_county`
    - `message`
  - Kullanici dosyadaki `"` karakterlerini sildi; bu durum CSV okunurlugu icin kabul edildi.
- `blocker_missing_source_county` icin ana hata sinifi:
  - Bazi `source_county` degerlerinde `c_* (second)` gibi suffixler vardi.
  - Sistem bunu normalize etmeden aradigi icin source county bulunamadi.
  - Karar: source title id okunurken `(second)` benzeri suffixler title lookup oncesi temizlenecek.
- `c_murin_china` orneginden cikan kural:
  - Source tarafinda top barony ve history block aslinda bulunabiliyordu.
  - Ornek: `c_murin_china` top barony province id `12742`.
  - Sorun bazen source bulma degil, target/final generated history block'unun olmamasiydi.
- `blocker_missing_target_history_block` icin kabul edilen cozum:
  - Overlay sadece var olan target block'a culture/religion yazmakla sinirli kalmamali.
  - Target top-barony province id icin generated history block yoksa sistem uygun source province history block'unu alip target province id ile yeni block olusturabilmeli.
  - Bu kural hem mod source hem vanilla source icin source kararina gore calismali.
  - Kaynak secimi kesin kural:
    - province/title kaynaginin source'u neyse o kullanilacak
    - `modlu_kalan` ise Leviathon/source mod history
    - `orijinal_dogu` ise vanilla/current source
    - butun `modlu_kalan`lar korlemesine Leviathon, butunlar korlemesine vanilla olmayacak; source karari belirleyici olacak.
- `c_deungju` ornegi:
  - Current landed_titles icinde target top barony province id `12783`.
  - Generated `history/provinces/00_MB_PROVINCES.txt` icinde `12783 = { ... }` block'u yoksa eski sistem blocker veriyordu.
  - Yeni kural: target block yoksa uygun source history block'undan hedef id ile block olustur.
- `blocker_missing_target_county,c_PHI_ma,c_mait_ph` ornegi:
  - Sebep target county'nin current `common/landed_titles/00_landed_titles.txt` icinde olmamasiydi.
  - Bu tip durumda overlay target title bulamadigi icin dogrudan uygulama yapamaz.
  - Cozum tipi title relation veya landed_titles tarafinda target county varligini/isim eslesmesini duzeltmek.
- `blocker_missing_source_root_culture_or_religion,c_mentawai,c_mentawai_islands` ornegi:
  - Source top-barony history block bulundu, fakat root seviyede `culture` veya `religion` eksikti.
  - Date block icindeki degerler root overlay icin yeterli sayilmadi.
  - Cozum tipi:
    - dogru source block secimi
    - veya source block root culture/religion barindirmiyorsa manuel/source fallback karari.
- Duplicate source history block problemi:
  - Ayni province id icin birden fazla history block olabiliyor.
  - Sistem tek block varsaymamalı.
  - Aday blocklar icinde once root `culture` + `religion` olanlar filtrelenecek.
  - Sonra source barony comment match varsa o secilecek.
  - Hala birden fazla aday varsa blocker veya manuel override gerekecek.
- `c_binh_long -> c_prey_rodum` duplicate ornegi:
  - `blocker_ambiguous_duplicate_source_history_block,c_binh_long,c_prey_rodum`
  - Kullanici Leviathon `00_MB_PROVINCES.txt` line civari `20570` icindeki `culture = khmer`, `religion = shaivism` olan block'un secilmesini istedi.
  - Bu karar manuel override'a yazildi:
    - `c_binh_long,c_prey_rodum,13178,khmer,shaivism`
  - Beklenen sonuc: target `10924` culture/religion degerleri `khmer/shaivism`.
- `works/tools/implement_core_province_integration.ps1` icin bu tur kabul edilen teknik degisiklikler:
  - county overlay icinde source title normalize fix'i
  - source-specific history lookup
  - missing target history block create-from-source fallback
  - duplicate source province history block support
  - source barony comment match ile duplicate cozumleme
  - manuel source history override CSV destegi
  - blocker report/readable report uretimi
- Live integration tekrar calistirildi:
  - komut mantigi: `implement_core_province_integration.ps1 -SkipLandedTitles`
  - landed_titles yeniden yazilmadi.
  - `history/provinces/00_MB_PROVINCES.txt` dahil integration outputlari guncellendi.
- Son blocker sonucu:
  - `county_culture_religion_overlay_summary.md` icinde blocker rows `0`
  - `county_culture_religion_overlay_blockers_readable.csv` sadece header'a dustu.
- `test_files` ile ilgili ara kontrol:
  - `history/provinces/00_MB_PROVINCES.txt` test_files kopyasi guncellenmisti.
  - Ancak `gfx/map/map_object_data` altindaki live locator dosyalari baslangicta `test_files` icine kopyalanmamisti.
  - Sonra bu 6 dosya test_files'a senkronlandi ve hash esitligi dogrulandi.

## 2026-04-25 Core Province Integration ve Son Esleme Duzeltmeleri

- Kullanici `hafiza.md` dosyasini proje hafizasi olarak kullaniyor; yeni net kararlar ve uygulanan duzeltmeler bu dosyaya ayrica hatirlatma beklenmeden islenmeli.
- `works/tools/implement_core_province_integration.ps1` core integration scripti icin son kabul edilen davranis:
  - province history source'u title/province kararindaki gercek source'a gore secilecek
  - `modlu_kalan` icin kaynak Leviathon/source mod history olabilir
  - `orijinal_dogu` icin kaynak vanilla/current source olabilir
  - target generated history block yoksa, uygun source province history block'u hedef province id ile yeni block olarak olusturulabilir
  - source county adlarindaki `(second)` gibi suffixler normalize edilmeli
  - duplicate source history block varsa once source barony comment match aranacak
  - duplicate hala belirsizse manuel override kullanilacak
- `works/manual/county_culture_religion_overlay_source_history_overrides.csv` eklendi.
  - `c_binh_long,c_prey_rodum,13178,khmer,shaivism`
  - Bu override Leviathon `00_MB_PROVINCES.txt` icinde line civari `20570` olan `culture = khmer`, `religion = shaivism` iceren `13178` block'unu secmek icin kullaniliyor.
- Son overlay summary:
  - relation county rows: `895`
  - applied rows: `892`
  - skipped rows: `3`
  - blocker rows: `0`
  - prepared province replacements: `892`
- `county_culture_religion_overlay_blockers_readable.csv` artik sadece header icermeli:
  - `status,target_county,source_county,message`
- `c_bungo` esleme hatasi duzeltildi:
  - Yanlis eski karar: `c_bungo, c_bungo, yes, ,`
  - Dogru karar: `c_bungo, c_bungo_jp, no, ,`
  - `title_relation_master_manuel_new.csv` satiri buna gore duzeltildi.
  - `history/provinces/00_MB_PROVINCES.txt` ve `test_files/history/provinces/00_MB_PROVINCES.txt` icinde `10518 = { # OITA }` root degerleri:
    - `culture = kyushu`
    - `religion = pundarika`
  - `history/titles/00_ASIA_JAPAN.txt` ve `test_files/history/titles/00_ASIA_JAPAN.txt` icinde `c_bungo_jp = {` basligi `c_bungo = {` yapildi.
  - `history/titles/00_ASIA_SOUTH.txt` ve `test_files/history/titles/00_ASIA_SOUTH.txt` icindeki hatali Malay/Srivijaya `c_bungo` history block'u kaldirildi.
  - `county_culture_religion_overlay_report.csv` satiri:
    - target `c_bungo`
    - source `c_bungo_jp`
    - target barony `b_oita`
    - source barony `b_oita`
    - target province `10518`
    - source province `13776`
    - root `kyushu/pundarika`
- `c_momauk` esleme hatasi duzeltildi:
  - 2026-04-26 netlestirme: bir onceki notta `c_bhamo` dogru gibi yazilmisti; bu yanlisti.
  - Dogru karar: `c_momauk, c_mongyang, no, ,`
  - `title_relation_master_manuel_new.csv` satiri buna gore duzeltildi.
  - `history/titles/00_ASIA_SOUTH.txt` ve `test_files/history/titles/00_ASIA_SOUTH.txt` icinde `c_momauk` history block'u `c_mongyang` source history icerigiyle guncellendi.
  - `county_culture_religion_overlay_report.csv` satiri:
    - `c_momauk -> c_mongyang`
    - `b_momauk -> b_mongyang`
    - `10987 -> 13040`
    - root `burmese/burmic`
    - date overrides `800.1.1:culture=kachin|religion=ari; 1050.1.1:culture=tai|religion=theravada; 1100.1.1:culture=shan`
  - `history/provinces/00_MB_PROVINCES.txt` ve `test_files/history/provinces/00_MB_PROVINCES.txt` icinde `10987 = { #b_momauk }` bu `c_mongyang` overlay degerleriyle guncellendi.
- `c_nandian` esleme hatasi duzeltildi:
  - Kullanici ifadesinde `c_mangshuea` yazildi, ama dosyalardaki gercek title id `c_mang_shuea`.
  - Yanlis karar: `c_nandian, c_mongyang, no, ,`
  - Dogru karar: `c_nandian, c_mang_shuea, no, ,`
  - `title_relation_master_manuel_new.csv` satiri buna gore duzeltildi.
  - `history/titles/00_ASIA_SOUTH.txt` ve `test_files/history/titles/00_ASIA_SOUTH.txt` icinde dogru `c_mang_shuea` history block'u `c_nandian` oldu.
  - Duplicate/basit `c_mang_shuea` block'u kaldirildi.
  - `history/provinces/00_MB_PROVINCES.txt` ve `test_files/history/provinces/00_MB_PROVINCES.txt` icinde `11481 = { #b_nandian }` artik:
    - `culture = achang`
    - `religion = burmic`
    - `holding = tribal_holding`
    - `1060.1.1 = { religion = theravada }`
    - `1100.1.1 = { culture = shan }`
  - `county_culture_religion_overlay_report.csv` satiri:
    - target `c_nandian`
    - source `c_mang_shuea`
    - target barony `b_nandian`
    - source barony `b_mang_shuea`
    - target province `11481`
    - source province `10903`
    - root `achang/burmic`
    - date overrides `1060.1.1:religion=theravada; 1100.1.1:culture=shan`
- `gfx/map/map_object_data` altinda live olarak yenilenen 6 dosya `test_files/gfx/map/map_object_data` icine kopyalandi ve hashleri esit dogrulandi:
  - `building_locators.txt`
  - `special_building_locators.txt`
  - `player_stack_locators.txt`
  - `combat_locators.txt`
  - `siege_locators.txt`
  - `activities.txt`

## 2026-04-26 Province Terrain Source-Mask Merge

- `common/province_terrain` dosyalari icin ana kural:
  - final province id korunacak
  - `orijinal_dogu` subset'i vanilla source id'den alinacak
  - `modlu_kalan` subset'i Leviathon/source mod id'den alinacak
  - source id degerleri final output'a yazilmayacak; sadece terrain/province property icerigi final id'ye tasinacak
- Source subset tespiti icin kullanilan maskeler:
  - `works/map_data_sources/provinces_modlu_kalan 2026-04-26.png`
  - `works/map_data_sources/provinces_orijinal_dogu 2026-04-26.png`
- RGB -> final province id eslemesi icin `map_data/definition.csv` kullanildi.
- Final province id -> source old id ve preferred source subset bilgisi icin `works/analysis/generated/final_master_preserve_old_ids.csv` kullanildi.
- Source terrain/property dosyalari:
  - Leviathon/source mod: `F:\Storage\Codding\git\Crusader Kings III\Leviathonlx MoreBookmarks-Plus\BookmarksGit\common\province_terrain`
  - Vanilla: `E:\XboxGames\Crusader Kings III\Content\game\common\province_terrain`
- Uygulama scripti:
  - `works/tools/merge_province_terrain_from_source_masks.py`
- Cikti dosyalari live ve test_files icin birlikte yenilendi:
  - `common/province_terrain/00_province_terrain.txt`
  - `common/province_terrain/01_province_properties.txt`
  - `test_files/common/province_terrain/00_province_terrain.txt`
  - `test_files/common/province_terrain/01_province_properties.txt`
- Son merge ozeti:
  - mask rows seen: `14695`
  - candidate rows: `13294`
  - skipped non-candidate rows: `1401`
  - legacy placeholder RGBs ignored: `34`
  - blockers: `0`
  - warnings: `46`
  - source id missing: `16`
  - terrain written: `11796`
  - terrain source missing: `1482`
  - property written: `13206`
  - property source missing: `72`
- `definition.csv` icinde 14627-14660 araligindaki bazi eski `zz_placeholder_*` province'ler artik normal province olarak kullaniliyor.
- `province_terrain_merge_issues.csv` icindeki eski `warning_rgb_not_in_definition_skipped` satirlari bu yuzden yeniden siniflandirildi:
  - eski placeholder RGB izleri `info_legacy_placeholder_rgb_replaced_by_current_definition` olarak tutuluyor
  - bu 34 satir artik blocker/warning sayilmiyor
- Bu aralikta final_master hala placeholder dedigi icin source old id'i bilinmeyen 16 normal row kaldi; bunlar `warning_missing_source_old_id_for_definition_normal` olarak raporlandi.
- Missing terrain kayitlarinin buyuk kismi explicit source terrain satiri olmayan sea/lake/default kapsaminda kabul edildi; bu yuzden blocker sayilmadi.
- `test_files/common/province_terrain` live ile hash-esit dogrulandi.
- Duplicate numeric province id kontrolu temiz:
  - `00_province_terrain.txt`: `11796` numeric id, duplicate `0`
  - `01_province_properties.txt`: `13206` numeric id, duplicate `0`
- Raporlar:
  - `works/analysis/generated/province_terrain_merge/province_terrain_merge_summary.md`
  - `works/analysis/generated/province_terrain_merge/province_terrain_merge_report.csv`
  - `works/analysis/generated/province_terrain_merge/province_terrain_merge_issues.csv`

## 2026-04-26 Dogu Title Rewrite Sistemi

- Ana hedef: `title_relation_master_manuel_new.csv` eslemelerine gore asli mod/dogu title id referanslarini bizim kullanilan title id'lere cevirmek.
- Rewrite yonu kesin olarak `mod_title_id -> source_title_id`:
  - ornek: `k_jin_china -> k_hedong`
  - ornek: `k_guangxi -> k_lingxi`
  - ornek: `k_guangnanxi -> k_lingxi`
- `is_same_title_id = yes` olan mappingler rewrite edilmez; raporda `same_id_noop` olarak tutulur.
- `&` iceren mappingler atomik mappinglere genisletilir.
- `(second)` suffix'i direct replace degildir:
  - mevcut mod title block'u korunur
  - source title id icin block clone denenir
  - block disi `(second)` referanslar otomatik rewrite/clone edilmez, `second_reference_report_only` olarak raporlanir.
- Rewrite atomiktir; uretilen yeni token tekrar rewrite motorundan gecmez. Bu `c_fuzhou_jiangxi_china -> c_jianchang -> c_jianchang_1` gibi zincir bozulmalarini engeller.
- Yorum satirlari rewrite edilmez; sadece `#` oncesi aktif script kismi title-token bazli islenir.
- Kapsam:
  - `common`
  - `history`
  - `events`
  - `decisions`
  - `map_data/geographical_regions`
- Kapsam disi:
  - `localization`
  - `works`
  - manuel CSV'ler
  - rapor ciktilari
- `common/landed_titles` rewrite hedefi degildir; bu dosyalar sadece full title audit kaynagi olarak okunur.
- `common/landed_titles` icinde token replace, block header rename veya `(second)` clone yapilmaz.
- `history/titles` icin title block header islemleri brace-aware parser ile yapilir.
- Direct block rename veya `(second)` clone mevcut bir hedef title block ile cakisirsa otomatik yazilmaz; `block_collision_would_duplicate` olarak raporlanir.
- Ayni scope icinde birden fazla block islemi ayni hedef title id'yi uretecekse `block_collision_same_run_target_duplicate` olarak raporlanir. Bu, hedef block dosyada zaten var anlamina gelmez; ayni dry-run planinda birden fazla kaynak block ayni hedefe donusuyor anlamina gelir.
- Uygulama scripti:
  - `works/tools/rewrite_east_title_ids.py`
- Rapor ciktilari:
  - `works/analysis/generated/east_title_rewrite/east_title_rewrite_summary.md`
  - `works/analysis/generated/east_title_rewrite/east_title_rewrite_plan.csv`
  - `works/analysis/generated/east_title_rewrite/east_title_rewrite_issues.csv`
  - `works/analysis/generated/east_title_rewrite/east_title_rewrite_info.csv`
  - `works/analysis/generated/east_title_rewrite/east_title_full_mod_title_audit.csv`
- Dry-run sonucu:
  - expanded mappings: `1372`
  - direct rewrite tokens: `668`
  - second mapping tokens: `39`
  - same-id noop: `665`
  - scanned target files: `4823`
  - landed title audit files: `12`
  - planned changed files: `33`
  - planned block header renames: `587`
  - planned second block clones: `36`
  - planned token/header replacements: `4219`
  - issues: `230`
  - info rows: `722`
  - blockers: `110`
- Live/test dosyalara rewrite yazilmadi; plan geregi `110` blocker manuel karar bekliyor.
- Yeni `east_title_rewrite_issues.csv` icinde `common/landed_titles` kaynakli rewrite issue kalmadi.
- `east_title_full_mod_title_audit.csv` mevcut `common/landed_titles` tanimlarina gore `17476` title block raporladi.

## 2026-04-26 Dogu Title Rewrite Annotated Collision Write

- `rewrite_east_title_ids.py` icine manuel temizlik workflow'u icin iki flag eklendi:
  - `--allow-annotated-collisions`
  - `--annotate-second-references`
- Bu modda duplicate uretme riski olan title block rename/clone islemleri atlanmaz; block/satir ustune `EAST_TITLE_REWRITE_*` yorum marker'i yazilir.
- `block_collision_same_run_target_duplicate` ve `block_collision_would_duplicate` durumlari yeni rapor statuslarina donustu:
  - `annotated_collision_rewrite_planned`
  - `annotated_collision_clone_planned`
  - `annotated_second_reference_planned`
- `--write --allow-annotated-collisions --annotate-second-references` calistirildi.
- Son write ozeti:
  - changed_files_planned: `33`
  - block_header_renames: `695`
  - second_block_clones: `38`
  - token_or_header_replacements: `4327`
  - annotated_collision_rewrites: `108`
  - annotated_collision_clones: `2`
  - annotated_collision_comments: `108`
  - annotated_collision_targets_marked: `14`
  - annotated_second_references: `119`
  - issues: `230`
  - blockers: `0`
  - write_performed: `yes`
- `common/landed_titles` ve `test_files/common/landed_titles` icinde `EAST_TITLE_REWRITE_` marker'i yok.
- Marker iceren `test_files` dosyalari live karsiliklariyla hash-esit dogrulandi: `4` dosya, mismatch `0`.
- Manuel temizlik icin dosyalarda `EAST_TITLE_REWRITE_` aranarak merge/review yapilmali.

## 2026-05-15 MPE Province Add 1 Import

- MPE kaynagi: `C:\Program Files (x86)\Steam\steamapps\workshop\content\1158310\3726274827`.
- Overlay kaynak: `works/map_data_sources/MPE/provinces_mpe_add_1.png`.
- Bu turda `map_data/provinces.png` degistirilmedi; kullanici provinces.png final guncellemesini sonda yapacak.
- Bu turda `test_files` senkronu yapilmadi.
- Overlay non-black RGB: `205`; MPE definition eksigi: `0`.
- Target definition icinde zaten olan RGB: `62`; same-id skip: `60`; mevcut manuel MPE mapping: `2`.
- Yeni TECH placeholder assignment: `143`; import/remap toplam old MPE id: `145`.
- Yeni ID secimi sadece `map_data/default.map` icindeki `# TECH PLACEHOLDER PROVINCES` blogunda bulunan `zz_placeholder_*` definition satirlarindan yapildi.
- `map_data/definition.csv` icinde `143` placeholder MPE definition satirina cevrildi.
- `common/landed_titles/00_landed_titles.txt` icine `53` MPE barony block'u eklendi; mevcut baronyler tekrar eklenmedi.
- `common/province_terrain/00_province_terrain.txt` icine `145` MPE terrain satiri eklendi.
- 6 `gfx/map/map_object_data` dosyasina toplam `868` locator/object block'u eklendi.
- `map_data/default.map` TECH placeholder blogundan `145` import target id cikarildi.
- `history/provinces/z_MPE_province.txt` bu turda otomatik import edilmedi; source usage raporunda report-only tutuldu.
- Rapor klasoru: `works/analysis/generated/mpe_import_add_1/`.
- Validation failures: `0`; `provinces.png` unchanged: `True`; `test_files` unchanged: `True`.

## 2026-05-15 MPE Add 1 Landed Hierarchy Import

- Kullanici onceki `parent d_* yoksa otomatik d_ olusturmayalim` yaklasimini degistirdi.
- Yeni kural: MPE province/title importunda eksik `c_*` county bloklari olusturulabilir; parent `d_*` duchy yoksa uygun mevcut `k_*`/`e_*` altinda `d_*` de olusturulabilir.
- Sinir: parent `k_*`/`e_*` hedef landed_titles icinde yoksa otomatik root/subtree migration yapilmaz; satir rapora dusurulur.
- `c_*` ve `d_*` acilis satirlarina `# Yusseter: MPE ... source provinces ...` yorumu eklenecek; `b_*` acilis satirlarinda `# Yusseter: MPE_<old_id>` yorumu korunacak.
- Bu tur icin yeni arac: `works/tools/import_mpe_add_1_landed_hierarchy.py`.
- Arac `map_data/provinces.png` ve `map_data/definition.csv` dosyalarini degistirmez; yalniz eksik landed_titles hiyerarsisini ve localization'i tamamlar.
- Olusturulan duchy: `4`; county: `36`; barony: `89`.
- Localization eklenen title: `116`; source localization bulunamayan: `0`.
- `provinces.png` unchanged: `True`; `definition.csv` unchanged: `True`.
- `test_files` bu MPE turunda yine degistirilmedi: `True`.
- Landed_titles brace depth: `0`.
- Raporlar:
  - `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_hierarchy_import_report.csv`
  - `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_hierarchy_localization_report.csv`
  - `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_hierarchy_import_summary.md`

## 2026-05-15 MPE Add 1 History Import

- Kullanici `test_files` sisteminin artik tekrar kullanacagini soyleyene kadar kullanilmamasini istedi.
- MPE Add 1 icin province history artik `history/provinces/00_yb_MPE_PROVINCES.txt` icine ayri dosya olarak aktarildi.
- Province history source: `C:\Program Files (x86)\Steam\steamapps\workshop\content\1158310\3726274827\history\provinces\z_MPE_province.txt`.
- Province history importunda MPE old id header'lari final target id'lere cevrildi.
- Province history kuralı: `culture` ve `religion` yalnizca county capital barony province'inde tutulur; county icinde explicit `capital = b_*` yoksa en ustteki `b_*` capital kabul edilir.
- Yeni MPE county'lerinin capital province culture/religion'u once ayni `d_*` icindeki `00_MB_PROVINCES.txt`te tanimli capital-province donor'undan alinir.
- Bu donor yoksa ayni `d_*` icindeki culture/religion tasiyan MPE source donor'u fallback olarak kullanilir; o da yoksa kendi MPE source province history'si fallback olur ve raporda gorunur.
- Yeni MPE title history output dosyasi: `history/titles/00_YB_MPE.txt`.
- Yeni MPE county title historyleri ayni duchy'nin capital county history'sinden clone edilir; kaynak yoksa kendi MPE county history'si fallback olarak kullanilir.
- Province history blocks added: `145` / requested `145`.
- Province culture/religion dagilimi: `same_duchy_existing_00_MB_PROVINCES = 24`, `fallback_same_duchy_mpe_source = 2`, `not_county_capital = 119`.
- Title history added: `36`; missing source title history: `129`.
- Missing source title history'nin nedeni: MPE source `history/titles` icinde ilgili imported `b_*` barony ve yeni `d_*` duchy title history bloklari bulunmuyor; bu turda yazilan `36` blok yeni `c_*` county history bloklaridir.
- `test_files` unchanged: `True`.
- Landed_titles conflict havuzu bu islemden sonra ayrica ele alinacak; bu turda conflict barony kararlarina dokunulmadi.
- Raporlar:
  - `works/analysis/generated/mpe_import_add_1/mpe_history_import_summary.md`
  - `works/analysis/generated/mpe_import_add_1/mpe_province_history_import_report.csv`
  - `works/analysis/generated/mpe_import_add_1/mpe_title_history_import_report.csv`

## 2026-05-15 MPE Landed Titles Conflict Decision Worklist

- MPE Add 1 landed_titles conflict havuzu canli dosyalar degistirilmeden karar tablosuna cevrildi.
- Karar tablosu: `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_conflict_decisions.csv`.
- Ozet rapor: `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_conflict_decisions_summary.md`.
- Toplam conflict satiri: `40`; unique barony: `29`; duplicate-key report rows: `0`.
- Otomatik uygulama guvenli satir yoktur; tum satirlar `safe_to_auto_apply = no` olarak isaretlendi.
- Status dagilimi: `county_child_existing_barony_conflict=11`, `county_child_removed_not_in_mpe_overlay=8`, `missing_source_barony=1`, `target_barony_existing_province_conflict=20`.
- `target_barony_existing_province_conflict` ve `county_child_existing_barony_conflict` icin karar secenekleri: mevcut target barony'yi koru, mevcut barony'yi MPE final province'e retarget et, MPE barony'yi ayri/rename title olarak yasat, ya da MPE title linkini dusurup history-only birak.
- `missing_source_barony` icin source landed-title blogu olmadigi icin title block tahmin edilmeyecek; manuel title gerekiyorsa ayrica kurulacak.
- `county_child_removed_not_in_mpe_overlay` satirlari Add 1 overlay/import ID map disinda kaldigi icin simdilik disarida tutulacak; genisletme ancak overlay/definition kapsami buyutulurse yapilacak.
- `landed_titles` unchanged: `True`; `test_files` unchanged: `True`.

## 2026-05-15 MPE Landed Titles Compact Conflict Decision CSV

- Kullanici, `mpe_landed_titles_conflict_decisions.csv` dosyasinin karar vermek icin fazla kalabalik oldugunu belirtti.
- Bu nedenle ayrintili tablo bozulmadan sade bir karar CSV'si uretildi:
  - `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_conflict_decisions_compact.csv`
- Sade CSV satir sayisi: `40`.
- Sade CSV'nin amaci:
  - kullanicinin her conflict icin sadece temel karari verebilmesi
  - teknik/provenance kolonlarini ayri ayrintili CSV'de saklamaya devam etmek
- Sade CSV kolonlari:
  - `decision_id`
  - `conflict_type`
  - `priority`
  - `barony`
  - `mpe_province`
  - `final_target_province`
  - `existing_live_barony_province`
  - `mpe_location`
  - `current_live_location`
  - `suggested_action`
  - `decision_options`
  - `your_decision`
  - `notes`
- Bu turda canli `common/landed_titles/00_landed_titles.txt` veya `test_files` dosyalari degistirilmedi.
- Kullanici bu compact CSV icinde `your_decision` ve gerekirse `notes` kolonlarini doldurabilir; uygulama daha sonra bu kararlara gore ayrica yapilacak.

## 2026-05-15 MPE Landed Titles Conflict Karar Kurali

- Kullanici MPE landed_titles conflict havuzu icin genel karar kuralini netlestirdi:
  - eger `b_*` zaten canli landed_titles icinde varsa ama baska bir `c_*` altindaysa, bu barony MPE'deki olmasi gereken `c_*` altina tasinacak.
  - yani ayni `b_*` icin temel cozum `MOVE_BARONY_TO_MPE_PATH` olacak.
- Bu kural su conflict siniflarini kapsar:
  - `target_barony_existing_province_conflict`
  - `county_child_existing_barony_conflict`
  - pratikte kullanici ornegi nedeniyle `missing_source_barony` icindeki `b_kutur-ogly` satiri da ayni tasima mantigiyla ele alinacak.
- Mevcut compact decision tablosuna gore bu kural:
  - `32` conflict satirini kapsiyor
  - `21` unique barony'ye denk geliyor
- Kapsam disinda kalan conflict havuzu:
  - `8` satir `county_child_removed_not_in_mpe_overlay`
  - bunlar Add 1 overlay/import id map kapsami disinda kaldigi icin ayni barony tasima s ablonuyla otomatik cozulmemeli.
- Kapsam disi kalan barony'ler:
  - `b_tsakhur`
  - `b_tsez`
  - `b_darial`
  - `b_kistani`
  - `b_lazia`
  - `b_rutul`
  - `b_lpink`
  - `b_ushkaloi`
- Bu turda canli landed_titles uygulamasi yapilmadi; sadece karar kurali ve kalan havuz netlesti.

## 2026-05-15 MPE Landed Titles Conflict Relocation Apply

- Kullanici MPE Add 1 landed_titles conflict havuzu icin nihai genel kurali verdi:
  - eger `b_*` zaten canli landed_titles icinde varsa ama MPE'deki olmasi gereken `c_*` disinda duruyorsa, bu barony MPE'deki `c_*` altina tasinacak.
  - MPE Add 1 overlay/import kapsaminda olmayan kalan conflict child barony'ler yokmus gibi ele alinacak.
- Compact karar CSV'si bu kurala gore kodlandi:
  - `MOVE_BARONY_TO_MPE_PATH`: `32` satir
  - `IGNORE_NOT_IN_MPE_ADD_1_OVERLAY`: `8` satir
- Ancak uygulama asamasinda sadece conflict CSV'ye bakmanin yetmedigi goruldu:
  - `b_besinada` gibi bazi `same id / already_present` satirlar conflict tablosuna girmemisti ama MPE'ye gore farkli county altindaydi.
  - Bu nedenle relocation uygulamasi tam `mpe_landed_titles_hierarchy_import_report.csv` uzerinden genisletildi.
- Yeni arac eklendi:
  - `works/tools/apply_mpe_landed_title_relocations.py`
- Uygulama ciktilari:
  - `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_relocation_apply_report.csv`
  - `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_relocation_plan.csv`
  - `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_relocation_apply_summary.md`
  - `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_empty_county_disable_report.csv`
  - `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_empty_county_disable_summary.md`
- Relocation uygulama sonucu:
  - planned barony rows: `34`
  - executable barony rows: `34`
  - ignored not-in-overlay baronies: `8`
  - `replace_or_move_barony_to_existing_county`: `29`
  - `move_barony_into_created_county`: `5`
  - validation errors: `0`
  - duplicate province assignment rows: `0`
  - final landed_titles brace depth: `0`
  - `test_files` unchanged: `True`
- Bu turda yaratilan/aktif hale gelen eksik MPE county bloklari:
  - `c_besinada`
  - `c_majar`
  - `c_lozova`
- Kullanici karariyla yok sayilan overlay disi barony'ler:
  - `b_tsakhur`
  - `b_tsez`
  - `b_darial`
  - `b_kistani`
  - `b_lazia`
  - `b_rutul`
  - `b_lpink`
  - `b_ushkaloi`
- Relocation sonrasi bos kalan eski county bloklari yorum satirina alindi:
  - `c_don_portage`
  - `c_korchev`
- Not:
  - Bos county comment adiminda ilk denemede brace depth gecici olarak bozuldu; hemen duzeltildi.
  - Son durum `final_depth = 0` ve relocation validation temiz.
- Kullanici `test_files` sistemini tekrar kullanacagini soyleyene kadar `test_files` sync yapilmamasi kurali bu turda da korundu.

## 2026-05-16 MPE Add 1 Consistency Audit ve Onarim Turu

- Kullanici MPE Add 1 sonrasi tutarlilik kontrol ve onarim planinin uygulanmasini istedi.
- Bu turda `test_files` sistemi kullanilmadi ve test_files altina yazim yapilmadi.
- Yeni ana araclar Yusseter repo altina eklendi:
  - `works/tools/audit_mpe_add_1_consistency.py`
  - `works/tools/apply_mpe_add_1_consistency_fixes.py`
- Apply sirasinda landed_titles blok tasima mantiginde bozulma yakalandi ve ek repair araclari eklendi:
  - `works/tools/repair_mpe_add_1_landed_titles_structure.py`
  - `works/tools/repair_mpe_add_1_landed_titles_residuals.py`
  - `works/tools/repair_mpe_add_1_caucasus_multiline.py`
- Karar/rapor klasoru:
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/`
- Uretilen karar tablolari:
  - `mpe_history_donor_map.csv`
  - `mpe_barony_alias_locator_map.csv`
  - `mpe_title_structure_fix_map.csv`

### Uygulanan MPE Yapısal Kararlar

- `c_don_portage` current landed_titles icinde yorumlu/silinmis olsa bile Levi kaynakta aktif oldugu icin history donor olarak kullanildi.
- `c_digora` yazimi `c_digoria`, `c_tapanda` yazimi `c_tapanta` olarak normalize edildi.
- `b_gialta`, `b_symbolon`, `b_phoros`, `b_anapa`, `b_soldaia` aktif title association olarak kullanilmadi.
- Bunlarin yerine eski Levi barony keyleri kullanildi:
  - `b_yalta` province `9837`, donor `b_gialta` / MPE old id `22830`
  - `b_yamboli` province `9836`, donor `b_symbolon` / MPE old id `22831`
  - `b_mangup` province `9835`, donor `b_phoros` / MPE old id `22832`
  - `b_batacrim` province `9838`, donor `b_anapa` / MPE old id `21385`
  - `b_sukdak` province `9833`, donor `b_soldaia` / MPE old id `22833`
- Altı map object locator dosyasinda target old ID bloklari donor locator bloklariyla guncellendi:
  - `activities.txt`
  - `building_locators.txt`
  - `combat_locators.txt`
  - `player_stack_locators.txt`
  - `siege_locators.txt`
  - `special_building_locators.txt`
- `c_kerch/c_cherson/c_korchev` ozel mapping uygulandi:
  - `c_kerch` eski Levi/Cherson kimligiyle korundu.
  - MPE `c_kerch` icerigi aktif `c_korchev` altina tasindi.
  - artik residual `d_klimata` blogu aktif kalmadi.
- `b_targim` `c_ossetia` altina tasindi; eski `c_dvaletia` aktif blok olarak tutulmadi.
- `c_lazia` altindaki `b_philan` ve `b_kuli`, `c_avaria` altina tasindi; `c_lazia` aktif blok olarak tutulmadi.
- `c_perekop`, `c_khortytsia`, `c_kerch`, `c_theodosia`, `c_tmutarakan` gibi Levi kokenli renkler repair sirasinda Levi mantigina geri cekildi.

### History ve Culture/Religion Kurali

- Kullanici kuralina gore culture/religion yalnizca target county capital barony province history'sinde kalacak sekilde kontrol edildi.
- Target county title history ve target capital barony province history donor county mantigiyla yeniden kuruldu.
- Non-capital audit sonucu:
  - kontrol edilen non-capital province satiri: `55`
  - kalan top-level culture/religion problemi: `0`
  - missing non-capital history block: `0`
- Elle temizlenen son non-capital culture/religion satirlari:
  - `13284` (`b_burgusan`)
  - `13295` (`b_targim`)
  - `5335` (`b_kopa`)

### Final Validation Sonucu

- Final ana audit:
  - `landed_titles brace depth = 0`
  - `duplicate province rows = 0`
  - `alias donor active title blockers = 0`
  - `locator target/comment issues = 0`
  - `active history issues = 0`
  - `localization missing in all sources = 68`
- `test_files` hash'i degismedi:
  - `0E8250C8DFB20B0653AEB9899FE6C538EDC467B087155C8F97E03BADCA3E3DAD`
- Kalan `duplicate title rows = 6` global/pre-existing gorunuyor; MPE alias veya province duplicate blocker'i degil.
- Localization eksikleri plan geregi otomatik uretilmedi, sadece raporlandi.
- Bilinen localization eksiklerinden:
  - `c_majar` missing all sources
  - `cn_iryston` missing all sources
  - `b_khunzakh` icin kaynak/current kontrolu report-only durumda
- Final ozet raporu:
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_consistency_final_validation_summary.md`

## 2026-05-16 MPE Add 1 Localization ve Alias Donor Duzeltmesi

- Kullanici `c_majar` localization eksigini ve `province 13360` icin aktif `b_` baginin olmamasini sordu.
- Tespit:
  - `c_majar`, `cn_iryston` ve `b_khunzakh` aslinda MPE English localization kaynaginda vardi.
  - Onceki audit regex'i yalnizca `key:0 "..."` formunu yakaladigi icin `key: "..."` bicimindeki MPE localization satirlarini kacirmisti.
  - Bu nedenle `c_majar` ve `cn_iryston` hatali bicimde `missing_all_sources` raporlanmisti.
- Duzeltme:
  - Current localization dosyasina MPE kaynagindan eklendi:
    - `b_khunzakh: "Khunzakh"`
    - `c_majar: "Majar"`
    - `cn_iryston: "Iryston"`
  - `works/tools/apply_mpe_add_1_consistency_fixes.py` localization parser regex'i `key:` ve `key:0` formlarini birlikte yakalayacak sekilde duzeltildi.
- `13360` tespiti:
  - `13360` eski MPE alias donor province idi (`b_symbolon`, MPE old id `22831`).
  - Kullanici karari geregi aktif title tarafinda bunun yerine eski Levi key/province `b_yamboli = 9836` kullaniliyor.
  - Bu yuzden `13360` aktif `b_` altinda olmamali; ancak default.map icinde teknik/non-title sinifa alinmadigi icin onceki durum eksikti.
- Duzeltme:
  - Superseded alias donor ID'leri `default.map` icinde teknik `impassable_mountains` listesine eklendi:
    - `12922 13359 13360 13361 13362`
  - Bu ID'lerin province history bloklari `holding = none` olacak sekilde normalize edildi; eski culture/religion/holding semantigi kaldirildi.
  - Rapor:
    - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_alias_donor_nonplayable_fix_report.csv`
- Son audit:
  - `brace_depth = 0`
  - `duplicate_provinces = 0`
  - `alias_blockers = 0`
  - `locator_issues = 0`
  - `history_issues = 0`
  - `missing_localization = 0`
  - `test_files` hash degismedi
- Bu duzeltmeden sonra `13360` icin aktif `b_` olmamasi artik beklenen durumdur; province teknik/impassable sinifta durur.

## 2026-05-16 MPE Alias Placeholder Residual Cleanup

- Kullanici `12922`, `13359`, `13360`, `13361`, `13362` province'lerini tekrar placeholder'a cevirdigini ve bu province'lerle ilgili kalan yerlerin silinmesini istedi.
- Karar:
  - `definition.csv` icindeki placeholder satirlari kalacak.
  - `default.map` icindeki placeholder/impassable kaydi kalacak.
  - Bunlar disindaki gameplay/artik veriler temizlenecek.
- Yeni arac:
  - `works/tools/cleanup_mpe_alias_placeholder_residuals.py`
- Temizlenenler:
  - `common/province_terrain/00_province_terrain.txt` icinden `4` terrain satiri silindi.
  - `history/provinces/00_yb_MPE_PROVINCES.txt` icinden `4` province history blogu silindi.
  - Altı `gfx/map/map_object_data` locator dosyasindan toplam `24` donor locator blogu silindi:
    - `activities.txt`
    - `building_locators.txt`
    - `combat_locators.txt`
    - `player_stack_locators.txt`
    - `siege_locators.txt`
    - `special_building_locators.txt`
- Rapor:
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_alias_placeholder_residual_cleanup_report.csv`
- Son kontrol:
  - Bu ID'ler artik yalnizca `map_data/definition.csv` ve `map_data/default.map` icinde gorunuyor.
  - `common/province_terrain`, `history/provinces` ve map object data dosyalarinda bu ID'ler kalmadi.
  - MPE consistency audit sonucu temiz:
    - `brace_depth = 0`
    - `duplicate_provinces = 0`
    - `alias_blockers = 0`
    - `locator_issues = 0`
    - `history_issues = 0`
    - `missing_localization = 0`
    - `test_files` hash degismedi

## 2026-05-16 MPE Kimmerikon Alias Cleanup

- Kullanici `b_kimmerikon` icin MPE donor province `13355 / MPE_22826` yerine Levi/current province `9832` kullanma kararini verdi.
- `common/landed_titles/00_landed_titles.txt` icinde `b_kimmerikon` kullanici tarafindan `province = 9832` olacak sekilde duzeltilmisti.
- Bu karar sonrasinda MPE locator verisi donor `13355` bloklarindan `9832` bloklarina kopyalandi.
- Donor `13355` locator bloklari su alti map object data dosyasindan kaldirildi:
  - `activities.txt`
  - `building_locators.txt`
  - `combat_locators.txt`
  - `player_stack_locators.txt`
  - `siege_locators.txt`
  - `special_building_locators.txt`
- `common/province_terrain/00_province_terrain.txt` icindeki `13355=plains # Yusseter: MPE_22826` satiri kaldirildi.
- `history/provinces/00_yb_MPE_PROVINCES.txt` icindeki `13355 = { #b_kimmerikon # Yusseter: MPE_22826 ... }` donor history blogu kaldirildi.
- `map_data/definition.csv` icinde `9832` gercek `Kimmerikon`, `13355` ise `zz_placeholder_13355` olarak kaldi.
- `map_data/provinces.png` icinde `13355` placeholder rengi 1 piksel kullandigi icin `map_data/default.map` teknik placeholder/impassable bloguna `impassable_mountains = RANGE { 13355 13355 }` eklendi.
- `test_files` kullanilmadi ve senkronlanmadi; kullanici tekrar kullanacagiz diyene kadar bu kural devam ediyor.
- Islem raporu: `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_kimmerikon_alias_cleanup_report.csv`

## 2026-05-16 MPE 13365/13366 Placeholder Cleanup

- Kullanici `13365` ve `13366` province'lerini baska bir sey icin kullanmama ve placeholder'a geri cekme karari verdi.
- Kullanici `map_data/definition.csv` icinde su donusumu yapti:
  - `13365;16;237;236;Khizi, MPE_23531;x;` -> `13365;144;112;144;zz_placeholder_13365;x;`
  - `13366;15;171;96;Gilazi, MPE_23532;x;` -> `13366;144;112;176;zz_placeholder_13366;x;`
- Bu karar sonrasinda `c_lupenia` aktif landed_titles blogu kaldirildi; cunku yalnizca `b_khizi = 13365` ve `b_gilazi = 13366` placeholder province'lerine bagliydi.
- `history/titles/00_YB_MPE.txt` icindeki `c_lupenia` title history blogu kaldirildi.
- `common/province_terrain/00_province_terrain.txt` icindeki `13365` ve `13366` terrain satirlari kaldirildi.
- `history/provinces/00_yb_MPE_PROVINCES.txt` icindeki `13365` ve `13366` province history bloklari kaldirildi.
- Alti `gfx/map/map_object_data` locator dosyasindan `id=13365` ve `id=13366` bloklari kaldirildi.
- `map_data/default.map` icinde `13365` ve `13366`, mevcut `impassable_mountains = RANGE { 13365 13421 }` placeholder/impassable araligi icinde kalmaya devam ediyor.
- `test_files` kullanilmadi ve senkronlanmadi.
- Islem raporu: `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_placeholder_13365_13366_cleanup_report.csv`

## 2026-05-16 MPE County History Gap Audit

- Kullanici `c_philan` uzerinden MPE Add 1 sonrasi yeni hata sinifini isaret etti: bazi aktif MPE county'lerin capital province history blogunda `culture`/`religion` yok ve bazi county title history bloklarinda `holder` yok.
- Yeni read-only audit uretildi:
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_county_history_gap_audit.csv`
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_county_history_gap_audit_problem_rows.csv`
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_county_history_gap_audit_summary.md`
- Audit sonucu:
  - aktif MPE county kontrolu: `60`
  - problemli county: `16`
  - `capital_history_missing_culture`: `11`
  - `capital_history_missing_religion`: `11`
  - `title_history_without_holder`: `5`
- `c_philan` icin net bulgu:
  - landed_titles capital barony: `b_khunzakh`
  - capital province: `13322`
  - `history/titles/00_ERE.txt` icinde `c_philan` holder history mevcut
  - ama `history/provinces/00_yb_MPE_PROVINCES.txt` icindeki `13322 = { #b_khunzakh ... }` blogunda `culture`/`religion` yok
  - MPE source `21450 = { #b_khunzakh }` blogunda `culture = khazar`, `religion = kabarism` var; yani eksik veri source'ta var ama aktarimda dusmus
- Kok neden yorumu:
  - onceki MPE audit/repair araclari donor-map uygulamasini kontrol ediyordu, fakat aktif county'nin capital province history culture/religion ve title history holder tutarliligini genel olarak denetlemiyordu
  - import raporunda `21450 -> 13322 b_khunzakh / c_philan` satiri yanlis/eksik sekilde `is_county_capital = no`, `culture_religion_status = not_county_capital` olarak kalmis
- Problemli culture/religion eksik county'ler:
  - `c_alania`, `c_cabardinia`, `c_digoria`, `c_durdzukia`, `c_iron`, `c_kuban`, `c_maskut`, `c_ossetia`, `c_peshe`, `c_philan`, `c_simsir`
- Problemli holder eksik county'ler:
  - `c_derbent`, `c_kerch`, `c_maghas`, `c_theodosia`, `c_tmutarakan`
- Bu tur sadece tespit/rapor turudur; core dosyalara repair henuz uygulanmadi.

## 2026-05-16 MPE County History Gap ve Structure Repair

- Kullanici c_majar'i landed_titles icinde c_don_portage olarak duzelttigini bildirdi; bundan sonra MPE kontrolu bu yeni current duruma gore yorumlandi.
- `works/tools/repair_mpe_county_history_gaps.py` ile MPE active county capital province history kontrolu tekrar yapildi.
- Onceki `c_philan` gibi eksikler gercek culture/religion eksiginden cok `00_yb_MPE_PROVINCES.txt` icinde duplicate/nested province history block yapisindan kaynaklaniyordu.
- `history/provinces/00_yb_MPE_PROVINCES.txt` icinde su yapisal onarimlar yapildi:
  - `13322` icin ikinci unrepaired duplicate block kaldirildi; repaired `b_khunzakh` block'u korundu.
  - `13350` icin ikinci unrepaired duplicate block kaldirildi; repaired `b_kuba` block'u korundu.
  - `13332` nested kalmisti; `13331 b_simsir` kapatildi ve `13332 b_durdzukia` top-level tek block haline getirildi.
  - `5302` nested kalmisti; `5303 b_besinada` kapatildi ve `5302 b_digora` top-level tek block haline getirildi.
- `works/tools/repair_mpe_county_history_gaps.py` apply mode stale-index hatasina karsi duzeltildi:
  - artik her province history block replacement oncesi `00_yb_MPE_PROVINCES.txt` yeniden parse ediliyor.
  - boylece ayni calistirmada birden fazla block degisince sonraki block'lar eski satir indeksleriyle yanlis yere yazilmiyor.
- Uretilen yeni raporlar:
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_county_history_block_structure_repair_report.csv`
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_county_history_block_structure_repair_summary.md`
- Son dogrulama:
  - `00_yb_MPE_PROVINCES.txt` brace depth: `0`
  - nested province history start: `0`
  - duplicate province history block: `0`
  - `repair_mpe_county_history_gaps.py` dry-run sonucu: `problem_rows_before_apply = 0`
  - `audit_mpe_add_1_consistency.py` sonucu: `history_issues = 0`, `duplicate_provinces = 0`, `alias_blockers = 0`, `locator_issues = 0`, `missing_localization = 0`
- `test_files` bu turda kullanici talimatina uygun olarak degistirilmedi.
- Kalan `duplicate_titles = 6` raporu MPE active history/province/link problemi degil; raporlanan title id'ler: `d_cumbria`, `d_map_base_color`, `d_nf_tang_ma`, `d_nf_tang_wang`, `k_cumbria`, `k_mauretania`.

## 2026-05-16 MPE Levi History Donor Kuralı ve c_kuma Düzeltmesi

- Kullanici yeni kuralı netlestirdi:
  - MPE ile eklenen/duzenlenen her `c_*` title history'si ve onun capital `b_*` province history'si asil Levi mod karsiligindan gelmeli.
  - MPE source history veya current/MB fallback yalnizca gecici/yanlis kabul edilmeli; Levi donor varsa ona gore yeniden uygulanmali.
- Kullanici `c_kuma` icin explicit donor verdi:
  - `c_kuma` title history donor: Levi `c_samiran`
  - `c_kuma` capital `b_kale_kuma` province `12898` history donor: Levi `c_samiran` capital `b_samiran`, province `5343`
- Uygulandi:
  - `history/titles/00_YB_MPE.txt` icindeki `c_kuma` block'u Levi `history/titles/00_ERE.txt` icindeki `c_samiran` block'undan yeniden kuruldu.
  - `history/provinces/00_yb_MPE_PROVINCES.txt` icindeki `12898 = { # b_kale_kuma ... }` block'u Levi `history/provinces/00_MB_PROVINCES.txt` icindeki `5343 = { # Samiran }` block'undan yeniden kuruldu.
  - `works/tools/repair_mpe_county_history_gaps.py` donor map'ine `c_kuma -> c_samiran` eklendi.
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_history_donor_map.csv` icine `c_kuma,c_samiran` kaydi eklendi.
- Uretilen raporlar:
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_c_kuma_levi_samiran_repair_report.csv`
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_levi_history_donor_audit.csv`
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_levi_history_missing_donor_counties.csv`
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_levi_history_needs_reapply_from_levi.csv`
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_levi_history_donor_audit_summary.md`
- Son MPE history/consistency dogrulamasi:
  - `repair_mpe_county_history_gaps.py` dry-run: `problem_rows_before_apply = 0`
  - `audit_mpe_add_1_consistency.py`: `history_issues = 0`, `duplicate_provinces = 0`, `alias_blockers = 0`, `locator_issues = 0`, `missing_localization = 0`
- Levi donor kapsam audit sonucu:
  - checked active MPE county rows: `60`
  - `ok_or_already_levi_sourced`: `44`
  - `has_levi_donor_but_current_history_still_mpe_sourced`: `10`
  - `needs_user_levi_donor_mapping`: `6`
- Levi donor verilmesi gereken county'ler:
  - `c_anket`
  - `c_avaria`
  - `c_darginia`
  - `c_lezgin`
  - `c_maskut`
  - `c_ubykh`
- Levi donor'u belli ama mevcut history halen MPE-sourced olan ve yeniden Levi'den uygulanmasi gereken county'ler:
  - `c_cabardinia -> Levi c_cabardinia / b_cabarda / 603`
  - `c_digoria -> Levi c_cabardinia / b_cabarda / 603`
  - `c_iron -> Levi c_cabardinia / b_cabarda / 603`
  - `c_ossetia -> Levi c_cabardinia / b_cabarda / 603`
  - `c_kuban -> Levi c_kuban / b_kuban / 5335`
  - `c_peshe -> Levi c_kuban / b_kuban / 5335`
  - `c_philan -> Levi c_philan / b_kumukh / 675`
  - `c_durdzukia -> Levi c_philan / b_kumukh / 675`
  - `c_malkhia -> Levi c_philan / b_kumukh / 675`
  - `c_simsir -> Levi c_philan / b_kumukh / 675`
- `test_files` bu turda kullanici talimatina uygun olarak degistirilmedi.

## 2026-05-17 MPE History Asıl Mod Donor Uygulaması

- Terminoloji kuralı netleşti:
  - Bundan sonra bu bağlamda `Levi donor` denmeyecek; doğru ifade `asıl mod donor` veya `asıl mod karşılığı` olacak.
  - Eski notlarda geçen `Levi`, tarihsel olarak `asıl mod` anlamındadır.
- Kullanıcı daha önce eksik kalan MPE county donor karşılıklarını verdi:
  - `c_anket -> c_samiran`
  - `c_avaria -> c_philan`
  - `c_darginia -> c_derbent`
  - `c_lezgin -> c_derbent`
  - `c_maskut -> c_derbent`
  - `c_ubykh -> c_jiqeti`
- Ayrıca `c_kuma` için karar teyit edildi:
  - `c_kuma -> c_samiran`
- Bu turda toplam `17` MPE-sourced county için asıl mod donor history uygulandı:
  - `c_cabardinia -> c_cabardinia`
  - `c_digoria -> c_cabardinia`
  - `c_iron -> c_cabardinia`
  - `c_ossetia -> c_cabardinia`
  - `c_kuban -> c_kuban`
  - `c_peshe -> c_kuban`
  - `c_philan -> c_philan`
  - `c_durdzukia -> c_philan`
  - `c_malkhia -> c_philan`
  - `c_simsir -> c_philan`
  - `c_anket -> c_samiran`
  - `c_avaria -> c_philan`
  - `c_darginia -> c_derbent`
  - `c_lezgin -> c_derbent`
  - `c_maskut -> c_derbent`
  - `c_ubykh -> c_jiqeti`
  - `c_kuma -> c_samiran`
- Uygulama mantığı:
  - Target county title history, mümkünse asıl mod donor county title history bloğundan alındı.
  - Target county capital barony province history, asıl mod donor county capital barony province history bloğundan alındı.
  - `culture` ve `religion` sadece target county capital barony province history bloğunda tutulacak kuralı korundu.
  - Aynı isimli ve ana title history dosyalarında zaten yaşayan `c_cabardinia`, `c_kuban`, `c_philan` için `00_YB_MPE.txt` içine duplicate title history eklenmedi.
- Güncellenen ana dosyalar:
  - `history/provinces/00_yb_MPE_PROVINCES.txt`
  - `history/titles/00_YB_MPE.txt`
  - `works/tools/repair_mpe_county_history_gaps.py`
- Yeni raporlar:
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_asli_mod_history_apply_report.csv`
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_asli_mod_history_apply_summary.md`
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_asli_mod_history_post_apply_validation.csv`
  - `works/analysis/generated/mpe_import_add_1/consistency_fix/mpe_asli_mod_history_post_apply_validation.md`
- Sonuç:
  - `donors: 17`
  - `report_rows: 34`
  - `blocked: 0`
  - post-apply validation `non_ok: 0`
- `works/tools/repair_mpe_county_history_gaps.py` dry-run sonucu:
  - `checked: 60`
  - `problem_rows_before_apply: 0`
  - `province_repairs: 0`
  - `title_repair_candidates: 0`
- `works/tools/audit_mpe_add_1_consistency.py` sonucu:
  - `brace_depth: 0`
  - `duplicate_provinces: 0`
  - `alias_blockers: 0`
  - `locator_issues: 0`
  - `history_issues: 0`
  - `missing_localization: 0`
  - `test_files_hash` değişmedi
- Not:
  - Eski `mpe_county_history_gap_current_audit.csv` içindeki `value_source` alanı artık gerçek provenance gibi okunmamalı; bu alan eksik olsaydı hangi resolver adayının kullanılacağını gösteriyor.
  - Gerçek provenance bu turdan sonra `asil_mod donor ...` blok yorumlarında ve yeni `mpe_asli_mod_history_*` raporlarında takip edilecek.

## 2026-05-17 Map Object Locator Position Audit

- Kullanıcının önerisi üzerine `gfx/map/map_object_data` içindeki ana province locator dosyalarının `map_data/provinces.png` üzerindeki kendi province sınırı içine düşüp düşmediğini kontrol eden read-only audit hattı kuruldu.
- Yeni araç:
  - `works/tools/audit_map_object_locator_positions.py`
- Bu araç canlı oyun dosyalarını düzeltmez; yalnızca rapor üretir.
- İlk audit kapsamına alınan dosyalar:
  - `gfx/map/map_object_data/activities.txt`
  - `gfx/map/map_object_data/building_locators.txt`
  - `gfx/map/map_object_data/combat_locators.txt`
  - `gfx/map/map_object_data/player_stack_locators.txt`
  - `gfx/map/map_object_data/siege_locators.txt`
  - `gfx/map/map_object_data/special_building_locators.txt`
- İlk turda özellikle dışarıda bırakılan dosyalar:
  - `game_object_layers.txt`
  - `great_wall_china.txt`
  - gerekçe: bunlar ilk 6 province locator dosyasıyla aynı semantik/format garantisine sahip değil; ayrı kural gerektirebilir.
- Koordinat kalibrasyonu otomatik yapıldı.
- Seçilen koordinat dönüşümü:
  - `floor_height_minus_1_minus_z`
- Üretilen raporlar:
  - `works/analysis/generated/map_object_locator_audit/locator_position_audit.csv`
  - `works/analysis/generated/map_object_locator_audit/locator_position_problem_rows.csv`
  - `works/analysis/generated/map_object_locator_audit/locator_position_summary.md`
  - `works/analysis/generated/map_object_locator_audit/locator_position_transform_calibration.csv`
  - `works/analysis/generated/map_object_locator_audit/mpe_alias_locator_position_audit.csv`
- Genel audit sonucu:
  - `total locator rows: 71994`
  - `inside_exact: 70788`
  - `near_same_province: 1038`
  - `outside_wrong_province: 158`
  - `missing_pixels_in_png: 10`
- MPE alias özel sonucu:
  - `alias locator rows: 36`
  - `alias target locator rows: 36`
  - `alias donor locator rows: 0`
  - `MPE alias status: inside_exact = 36`
- Kontrol edilen MPE alias target province'ler:
  - `9832 Kimmerikon`
  - `9833 Sougdaia`
  - `9835 Mangup`
  - `9836 Yamboli`
  - `9837 Yalta`
  - `9838 BataCrim`
- Sonuç:
  - MPE alias locator aktarımı piksel bazında doğru görünüyor; bu 6 target province'in 6 ana locator dosyasındaki tüm satırları kendi province rengi içine düşüyor.
  - Donor/placeholder ID'ler için aktif alias locator satırı kalmamış görünüyor.
  - Genel `outside_wrong_province` ve `missing_pixels_in_png` havuzu ayrı bir temizlik/backlog konusudur; bu turda otomatik düzeltme uygulanmadı.
- `test_files` bu turda kullanılmadı ve özellikle senkron/düzeltme yapılmadı.

## 2026-05-17 Locator Audit Barony-Only Filtreleri

- Kullanıcı isteğiyle `locator_position_problem_rows_compact.csv` ve `locator_position_near_same_province_compact.csv` raporları, yalnızca `common/landed_titles/00_landed_titles.txt` içinde aktif bir `b_*` bloğunda `province = <id>` olarak tanımlı province satırlarına filtrelendi.
- Filtre aktif satırlara göre yapıldı; yorum içindeki `province` değerleri sayılmadı.
- Üretilen barony-only dosyalar:
  - `works/analysis/generated/map_object_locator_audit/locator_position_problem_rows_compact_landed_barony_only.csv`
  - `works/analysis/generated/map_object_locator_audit/locator_position_near_same_province_compact_landed_barony_only.csv`
- Ayrıca dışarıda kalan satırlar ayrı saklandı:
  - `works/analysis/generated/map_object_locator_audit/locator_position_problem_rows_compact_not_in_landed_barony.csv`
  - `works/analysis/generated/map_object_locator_audit/locator_position_near_same_province_compact_not_in_landed_barony.csv`
- Özet dosyası:
  - `works/analysis/generated/map_object_locator_audit/locator_position_landed_barony_filter_summary.csv`
- Sonuç:
  - problem seti: `168` satırdan `76` satır barony-linked kaldı, `92` satır dışarıda kaldı
  - near_same_province seti: `1038` satırdan `877` satır barony-linked kaldı, `161` satır dışarıda kaldı
- Not:
  - İlk PowerShell denemesinde `$PID` yerleşik değişken adıyla çakışma olduğu için çıktı güvenilir kabul edilmedi; dosyalar sonrasında tam audit CSV'den `province_rgb` korunarak yeniden üretildi.

## 2026-05-17 Building Locator Borderline Ek Raporu

- Kullanıcı `561 Theodosia` örneği üzerinden `building_locators.txt` içinde exact olarak province içinde duran ama sınıra çok yakın olan locator'ların da review raporuna eklenmesini istedi.
- Yeni yardımcı araç eklendi:
  - `works/tools/build_locator_review_compact_reports.py`
- Bu araç şu dosyayı yeniden üretir:
  - `works/analysis/generated/map_object_locator_audit/locator_position_near_same_province_compact_landed_barony_only.csv`
- Dosyaya yeni kolonlar eklendi:
  - `status`
  - `borderline_reason`
- Mevcut `near_same_province` barony-linked satırları korundu.
- Ek olarak sadece `building_locators.txt` içindeki `inside_exact` ama çok sınırda olan satırlar eklendi.
- Borderline kuralı:
  - `status = inside_exact`
  - `file = building_locators.txt`
  - province `common/landed_titles/00_landed_titles.txt` içinde aktif bir `b_*` altında bağlı olacak
  - en yakın farklı RGB mesafesi `<= 1`
  - `radius=2` çevrede aynı province oranı `< 0.70`
- Sonuç:
  - `near_same_province rows kept: 877`
  - `building inside_exact_but_borderline rows added: 19`
  - `total output rows: 896`
- `561 Theodosia` artık bu dosyada ayrıca şu statüyle görünüyor:
  - `inside_exact_but_borderline`
  - reason: `nearest_diff_distance=1;radius2_same_ratio=0.640;pixel=2862,1819`
- Bu turda canlı locator dosyalarına düzeltme uygulanmadı; sadece review raporu yeniden üretildi.

## 2026-05-23 Locator Fix Candidate Dry-Run Raporu

- Kullanıcı isteğiyle `locator_position_problem_rows_compact_landed_barony_only.csv` içindeki düz `building_locators.txt` hariç problem satırları için otomatik düzeltme adayı raporu üretildi.
- Yeni yardımcı araç eklendi:
  - `works/tools/build_locator_fix_candidates.py`
- Üretilen raporlar:
  - `works/analysis/generated/map_object_locator_audit/locator_fix_candidates_landed_problem_non_building.csv`
  - `works/analysis/generated/map_object_locator_audit/locator_fix_candidates_landed_problem_non_building_summary.md`
- Kapsam:
  - compact source rows: `76`
  - plain/manual `building_locators.txt` satırları hariç hedef satır: `73`
  - `special_building_locators.txt`: `37`
  - `activities.txt`: `17`
  - `combat_locators.txt`: `8`
  - `player_stack_locators.txt`: `8`
  - `siege_locators.txt`: `3`
- Aday üretme mantığı:
  - current locator dosyaları tekrar parse edildi; eski audit CSV tek source of truth yapılmadı.
  - `building_locators.txt` hedef dışı tutuldu ve sadece `inside_exact` olduğunda anchor olarak kullanıldı.
  - hedef locator tipi için temiz örneklerden `target_file - building_locator` lokal median offset kullanıldı.
  - aday dışarı düşerse aynı province içinde güvenli/interior pixel fallback'i uygulandı.
  - `special_building_locators.txt` dahil edildi ama high-confidence için daha sıkı sınır mesafesi arandı.
- Sonuç:
  - `candidate_status = inside_exact`: `73`
  - `high`: `63`
  - `medium`: `6`
  - `low`: `4`
- Bu turda canlı map object locator dosyalarına düzeltme uygulanmadı; sadece dry-run aday raporu üretildi.

## 2026-05-23 Locator Fix Candidate Near-Same Far Eşikleri

- Kullanıcı hatırlatmasıyla `locator_position_near_same_province_compact_landed_barony_only.csv` içindeki `# Yusseter: OK; building_locators.txt` satırları düzeltme kapsamı dışında bırakıldı.
- `works/tools/build_locator_fix_candidates.py` scriptine near-same uzak eşik kapsamı eklendi:
  - `special_building_locators.txt` dışı locator'lar için `nearest_same_province_distance >= 8`
  - `special_building_locators.txt` için `nearest_same_province_distance >= 12`
- Düz `building_locators.txt` ve `# Yusseter: ... building_locators.txt` satırları hedef setinden dışlandı.
- `locator_fix_candidates_landed_problem_non_building.csv` yeniden üretildi.
- Sonuç:
  - problem target rows: `73`
  - near-same far target rows: `77`
  - total target rows: `150`
  - `candidate_status = inside_exact`: `150`
  - `high`: `128`
  - `medium`: `12`
  - `low`: `10`
- Bu turda canlı map object locator dosyalarına düzeltme uygulanmadı; sadece dry-run aday raporu güncellendi.

## 2026-05-23 Locator High-Confidence Apply

- Kullanıcı isteğiyle `locator_fix_candidates_landed_problem_non_building.csv` içindeki `confidence = high` ve `candidate_status = inside_exact` satırları canlı locator dosyalarına uygulandı.
- Yeni apply aracı eklendi:
  - `works/tools/apply_locator_fix_candidates.py`
- Apply raporları:
  - `works/analysis/generated/map_object_locator_audit/locator_fix_candidates_high_apply_report.csv`
  - `works/analysis/generated/map_object_locator_audit/locator_fix_candidates_high_apply_summary.md`
- Değiştirilen dosyalar ve satır sayıları:
  - `activities.txt`: `45`
  - `combat_locators.txt`: `18`
  - `player_stack_locators.txt`: `10`
  - `siege_locators.txt`: `9`
  - `special_building_locators.txt`: `46`
- Toplam:
  - selected high-confidence rows: `128`
  - changed rows: `128`
  - skipped rows: `0`
- `building_locators.txt` değiştirilmedi.
- Değişen `position` satırlarına şu marker eklendi:
  - `# Yusseter: Auto fixed from locator candidate`
- Apply sonrası locator audit yeniden üretildi:
  - `inside_exact`: `70935`
  - `near_same_province`: `956`
  - `outside_wrong_province`: `98`
  - `missing_pixels_in_png`: `10`
- Uygulanan `128` satırın tamamı yeni audit'te `inside_exact` çıktı.
- `locator_position_near_same_province_compact_landed_barony_only.csv` yeniden üretildi ve `building_locators.txt` near-same satırları `# Yusseter: OK; building_locators.txt` olarak işaretli tutuldu.

## 2026-07-26 - 2026-07-30 Repo-Geneli Tespit Sistemi ve Güncel Devam Kaydı

### Çalışma Kuralları

- Güncel proje kökü: `F:\Storage\Codding\projects\ck3\Yusseter MoreBookmarksPlus`.
- Canlı mod: `BookmarksGit`.
- Asıl mod: `F:\Storage\Codding\projects\ck3\Leviathonlx MoreBookmarks-Plus`.
- Bu dosya proje-özel authoritative hafızadır. Yeni oturumda önce çalışma kuralları ve son operasyon kaydı okunacak; global Codex hafızası bunun yerine kullanılmayacak.
- Kullanıcının verdiği örnek yalnız başlangıç noktasıdır:
  - somut örnek doğrulanır
  - temsil ettiği genel invariant ve kök mekanizma çıkarılır
  - aynı mekanizma ilgili repo kapsamının tamamında taranır
  - coverage, negatif sonuç ve açık sınırlar birlikte raporlanır
- Riskli veya tasarımsal kararlarda kullanıcıya kısa ve hedefli soru sorulabilir.
- Statik araçla kanıtlanamayan davranışlar için kullanıcıdan açık adımlı oyun içi test, ekran görüntüsü veya log istenebilir.
- Kullanıcı Codex olmadan da sistemi çalıştırabilmelidir:
  - auditlerin repo kökünden çalıştırılabilen açık komutları bulunmalı
  - girdiler, çıktılar ve kabul kriterleri raporda yer almalı
  - kararlar yalnız sohbette değil, düzenlenebilir CSV ve bu hafızada tutulmalı
  - yeni araç yazmadan önce `.codex/works/tools` envanteri kontrol edilmeli
- Tespit aşamasında canlı `BookmarksGit` kaynakları otomatik düzeltilmez. Adayların tamamı açık onay verilene kadar `auto_apply=no` kalır.
- Doğru sınıflandırma aileleri:
  - gerçek Yusseter hatası
  - asıl moddan taşınmış ortak hata
  - bilinçli Yusseter farkı
  - stale veya yanlış audit bulgusu
  - kalite uyarısı
  - runtime testi gereken belirsiz durum

### Güncel Repo Closure Durumu

- Ana closure'ın son deterministik sonucu:
  - finding: `6712`
  - blocker: `274`
  - review: `6177`
  - info: `261`
  - coverage: `32 full + 3 partial`
- Partial alanlar:
  - genel bookmark/runtime oyun içi smoke testi
  - Silk Road market runtime smoke testi
  - target tracking, target image'dan eski olduğu için manuel kalan province-relation refresh
- Stale coverage satırı yoktur.
- Bu sayılar bağımsız hata sayısı değildir; aynı kök neden birden fazla audit veya satırda temsil edilebilir.
- Region ve Silk Road market bulguları ana closure'a exact-overlap ile bağlandı:
  - market kökü: `10`, her biri ana closure'da yalnız bir kez temsil ediliyor
  - region kökü: `920`
  - mevcut ana bulguyla eşleşen region kökü: `200`
  - yalnız dış review olarak kalan region kökü: `720`
- Seçilen `32/32` ana çıktı ikinci tam çalıştırmada aynı SHA-256 hash'ini üretti.

### Repo-Geneli Geographical Region Closure

- Salt-okuma araçları:
  - `.codex/works/tools/audit_geographical_region_closure.py`
  - `.codex/works/tools/run_geographical_region_closure.ps1`
- Normal komut: `.\.codex\works\tools\run_geographical_region_closure.ps1`.
- Hızlı referans-only komut: `.\.codex\works\tools\run_geographical_region_closure.ps1 -SkipGeometry`.
- Çıktı kökü: `.codex/works/analysis/generated/repo_integration_closure/geographical_region_closure`.
- Denetlenen katmanlar:
  - CK3 file-override kuralıyla effective region dosyaları
  - quote-aware yorum ve süslü parantez parser'ı
  - `regions/kingdoms/duchies/counties/baronies/provinces` üyelikleri
  - nested region graph, cycle ve recursive province membership
  - current, pre-merge, asıl mod ve vanilla provenance
  - current landed-title hiyerarşisi
  - `definition.csv`, `provinces.png`, adjacency, component, enclosed gap ve sibling overlap
  - Silk Road situation/route static closure ve kontrol PNG'si
- Son tam pass:
  - effective region: `845`
  - direct membership token: `11652`
  - parser diagnostic: `0`
  - ham review finding: `1216`
  - bağımsız karar kökü: `920`
  - kesin blocker: `0`
  - enclosed landed gap: `434` satır / `201` benzersiz coğrafi küme
  - disconnected landed region: `456`
  - duplicate region definition: `37`
- Spatial bulgular ada, exclave, wasteland veya bilinçli tasarım olabilir; toplu otomatik apply yasaktır.
- Silk Road'un görünen başlıca region adayları:
  - China: `k_longxi_china` altındaki `d_fengxiang/d_xingfeng`, 10 province
  - India: `k_pandya > d_pandya_nadu`, 14 province
  - Khorasan: `c_sarakhs`, 3 province
  - Gharjistan/Guzgan: `c_marvarrud + c_rivsharan`, 8 province
- SEA situation region'ında altı undefined kingdom token'ı vardır. China ve SEA route region'larında eski veya undefined county token'ları açık review olarak kalır.

### Silk Road Market, Building, GUI ve Ok Bağımlılığı

- Salt-okuma araçları:
  - `.codex/works/tools/audit_silk_road_market_closure.py`
  - `.codex/works/tools/run_silk_road_market_closure.ps1`
- Çıktı kökü: `.codex/works/analysis/generated/repo_integration_closure/silk_road_market_closure`.
- Son market pass'i:
  - subregion: `8`
  - effective `silk_road_node` building: `20`
  - ham finding: `15` (`9 blocker`, `6 review`)
  - bağımsız kök: `10` (`4 blocker`, `6 review`)
  - static coverage: `9 full`
  - runtime coverage: `1 partial`
- Kesin ve yüksek güvenli iki kaynak adayı:
  - China center `12743` current map'te denizdir; mevcut Chang'an market yerleşimi `12218` güçlü merkez adayıdır.
  - `building_constantinople_market_01_desc` localization satırının kapanış tırnağı eksiktir.
- SEA/Angkor için sonraki doğrulama önceki apply tasarımını değiştirmiştir:
  - vanilla situation'da SEA subregion ve Angkor market yoktur
  - vanilla connection-arrow dosyasında Angkor'a giden rota yoktur
  - asıl mod `angkor_market_01` ve province `13444`te biten iki özel Angkor rotası eklemiştir
  - Yusseter'ın güncel doğu okları vanilla tabanlıdır ve Angkor bağlantısı içermez
  - bu nedenle yalnız `10819` üzerine Angkor market eklemek görsel ve semantik olarak eksik bir çözüm olur
- Tutarlı iki tasarım seçeneği vardır:
  - vanilla-doğu kuralını koruyup SEA subregion, Angkor market ve decision zincirini güvenli biçimde kapsamdan çıkarmak
  - asıl-mod SEA genişletmesini bilinçli olarak kabul edip Angkor market ile iki rotayı current haritaya yeniden eşlemek ve geometri auditinden geçirmek
- Yalnız market ekleme seçeneği kabul edilmeyecek. Kullanıcı tasarım tercihi vermeden SEA kaynak editine geçilmeyecek.
- China ve Constantinople adayları da upstream/map etkisi yeniden doğrulanmadan uygulanmayacak.

### 2026-07-30 Upstream Fetch-Only Envanteri

- Fetch öncesi güvenlik checkpoint'i:
  - `.codex/works/analysis/generated/upstream_update_inventory/prefetch_git_state.json`
  - `.codex/works/analysis/generated/upstream_update_inventory/prefetch_status_porcelain.txt`
  - `.codex/works/analysis/generated/upstream_update_inventory/prefetch_tracked_worktree.patch`
- Git çapaları:
  - Yusseter HEAD: `b27d8ddb63f568839cd96e024607ab7f0e227497`
  - son merge edilen asıl-mod kaynağı / merge-base: `ed1520220c1e8469a9865e3f69c57bcc399df0c5`
  - fetch öncesi `upstream/main`: `2d55f8c108d67df447145a532f825b29d2227854`
  - fetch sonrası `upstream/main`: `3457500ca690067e322100de853ab6ab0bc8a834`
- Bekleyen upstream aralığı:
  - commit: `6`
  - yeni fetch edilen commit: `1` (`3457500ca`, 7/29)
  - net değişen yol: `1378`
  - canlı `BookmarksGit` yolu: `15`
  - `Other/` extraction/reference yolu: `1362`
  - `error.log`: `1`
  - dirty çalışma ağacıyla doğrudan yol çakışması: `0`
  - landed-title property değişikliği: `0`
- Yeni `3457500ca` commit'i Northeast karakter, dynasty, CoA ve dynasty localization zincirine dokunur.
- Toplam bekleyen aralık `provinces.png`, üç map-object locator dosyası, karakter/title history ve davranış scriptleri içerir.
- `140d6d5cd` ile gelen `Other/` altındaki 1362 dosyanın Yusseter reposuna alınıp alınmayacağı ayrıca kararlaştırılmalıdır.
- Merge kararı: `do_not_merge_yet`.
- Aynı Tiger binary/config ile temiz `ed1520220` ve `3457500ca` snapshot'ları karşılaştırıldı:
  - yeni kararlı Tiger raporu: `109`
  - çözülen kararlı Tiger raporu: `5`
  - merge engelleyici rapor: `66`
  - bağımsız yeni kök: `7`
  - sınıflandırılmamış kök: `0`
- İki merge engelleyici kök:
  - `balhae_mo_identity_collision`: `44` raporun `43`ü merge engeli; `140d6d5cd` ve `6d0a2fed1`
  - `balhae_al_dynasty_parse_failure`: `23` merge engeli; `6d0a2fed1`
- Diğer doğrulanmış kökler:
  - `balhae_go_identity_replacement_regression`: merge tabanında geçerli yedi title-holder zinciri yeni karakter ID kullanımıyla yaşam aralığı dışına çıktı
  - `new_character_name_localization_gap`: on exact English ad anahtarı, `24` kullanım; taban/son asıl mod/vanilla katmanlarında karşılık yok
  - `missing_baijia_coa_assets`: yedi DDS dosyası, `8` kullanım; taban/son asıl mod/vanilla katmanlarında dosya yok
  - `adynasty_house_field_typo`: güçlü `dynasty_house` düzeltme adayı
  - `duplicate_balhae_ha_coa_definitions`: iki kalite uyarısı
- Ayrıntılı raporlar:
  - `.codex/works/analysis/generated/upstream_update_inventory/upstream_update_inventory_summary.md`
  - `.codex/works/analysis/generated/upstream_update_inventory/pending_upstream_commits.csv`
  - `.codex/works/analysis/generated/upstream_update_inventory/pending_live_mod_files.csv`
  - `.codex/works/analysis/generated/upstream_update_inventory/four_way`
  - `.codex/works/analysis/generated/tiger_upstream_delta/upstream_tiger_delta_summary.md`
  - `.codex/works/analysis/generated/tiger_upstream_delta/upstream_tiger_root_causes.csv`
  - `.codex/works/analysis/generated/tiger_upstream_delta/upstream_premerge_decision_summary.md`

### Tiger Hattı Hakkındaki Düzeltme

- Ana closure aracı Tiger'ı kendisi çalıştırmaz; üretilmiş JSON raporlarını okur. Bu nedenle closure'dan önce Tiger baseline aracı çalıştırılmalıdır.
- VS Code eklentisi: `unlomtrois.ck3tiger-for-vscode-1.1.2`.
- VS Code'un kullandığı binary:
  - `C:\Users\bsgho\AppData\Roaming\Code\User\globalStorage\unlomtrois.ck3tiger-for-vscode\ck3-tiger\ck3-tiger.exe`
  - sürüm: `1.19.0`
- Global `ck3tiger.modPath`, eski BILAD yolu değil `C:\Users\bsgho\Documents\Paradox Interactive\Crusader Kings III\mod\mbp_vp.mod` değeridir.
- `mbp_vp.mod` canlı `F:/Storage/Codding/projects/ck3/Yusseter MoreBookmarksPlus/BookmarksGit` yolunu gösterir.
- Eklentinin `tigerPath`, `ck3Path` ve `modPath` ayarları application-scope olduğu için workspace ayarıyla override edilemez. Global ayar kör biçimde değiştirilmemelidir.
- Standalone audit artık VS Code ile aynı binary, canlı mod descriptor'ı ve `BookmarksGit/ck3-tiger.conf` dosyasını kullanır:
  - `.codex/works/tools/run_ck3_tiger_baseline.ps1`
  - `.codex/works/tools/compare_ck3_tiger_json.py`
- VS Code'un mevcut JSON'u ile standalone çıktının nondeterministic `scopes/strict-scopes` dışındaki `19034` kararlı raporu birebir aynıdır.
- Shell üzerinden Tiger çalıştırmak VS Code Problems görünümünü otomatik yenilemez. Arayüz için ayrıca `ck3tiger: Run ck3tiger` veya üretilmiş log yayımlandıysa `ck3tiger: Get problems from the log file` komutu kullanılmalıdır.
- Taze merge-öncesi çıktılar:
  - `.codex/works/analysis/generated/tiger_premerge_baseline`
  - `.codex/works/analysis/generated/tiger_upstream_delta`
- Güncel closure bu taze Tiger kanıtıyla yeniden üretildi; stale coverage `0`dır.

### 2026-07-30 Bekleyen Harita ve Locator Üç Yönlü Auditi

- Salt-okuma aracı:
  - `.codex/works/tools/audit_pending_upstream_map_locator_delta.py`
- Normal komut:
  - `python .codex/works/tools/audit_pending_upstream_map_locator_delta.py`
- Çıktı kökü:
  - `.codex/works/analysis/generated/upstream_map_locator_delta`
- Karşılaştırılan katmanlar:
  - merge tabanı `ed1520220`
  - güncel Yusseter HEAD `b27d8ddb6`
  - yeni asıl mod `3457500ca`
  - etkin vanilla fallback ve mevcut `descriptor.mod` replace-path davranışı
- `provinces.png` sonucu:
  - toplam piksel: `42467328`
  - yalnız Yusseter tarafından değiştirilmiş piksel: `13800085`
  - yeni asıl mod tarafından gerçekten değiştirilmiş RGB pikseli: `0`
  - gerçek piksel çatışması: `0`
  - base ve yeni asıl mod PNG blob hash'leri farklıdır, fakat RGB pixel SHA-256 hash'leri birebirdir
  - yeni asıl mod değişikliği yalnız PNG encoding/metadata katmanındadır
  - merge çözümü: yeni blob'u alma; mevcut Yusseter `provinces.png` dosyasını koru
- `building_locators.txt` sonucu:
  - yeni asıl moddaki tek semantik değişiklik `id=6053 / ALEXANDRIA`
  - position ve rotation değişmiyor
  - scale `0.080000` değerinden `0.685591` değerine çıkıyor
  - konum hem Yusseter hem asıl mod haritasında `inside_exact`
  - değişiklik `140d6d5cd` commitinden geliyor ve vanilla locator kopyası değildir
  - karar: `review_then_take_upstream_scale`, confidence `medium`, `auto_apply=no`
- `special_building_locators.txt` sonucu:
  - yalnız boşluk/biçim değişikliği var; semantik locator değişikliği yok
  - merge sırasında mevcut Yusseter dosyası korunmalı
- `special.txt` sonucu:
  - dosya Yusseter modunda `09588cbb5` commitinde bilinçli olarak kaldırılmıştır
  - `gfx/map/map_object_data` için `replace_path` yoktur; vanilla `special.txt` etkin kalır
  - yeni asıl moddaki `special.txt`, güncel vanilla dosyasıyla byte düzeyinde aynıdır
  - `constantinople_sprawl` objesi, Byzantion province `496` üzerinde etkin vanilla fallback içinde zaten vardır
  - gerekli `ep3_constantinople_sprawl_mesh` asseti vanilla içinde bulunur
  - karar: mod dosyasını yeniden ekleme; vanilla fallback'i koru
- Kontrol görseli:
  - `.codex/works/analysis/generated/upstream_map_locator_delta/provinces_three_way_control.png`
- Canlı `BookmarksGit` harita veya locator kaynakları değiştirilmedi.

### Sonraki İşlem Sırası

1. Merge yapmadan önce `balhae_mo_identity_collision` ve `balhae_al_dynasty_parse_failure` için uygulanacak merge-resolution tasarımını kesinleştir.
2. BalhaeGo kimlik regresyonu, on ad localization'ı, yedi eksik CoA DDS asseti, `adynasty_house` yazım hatası ve duplicate CoA blokları için review kararını tamamla.
3. Merge çözümünde `provinces.png`, `special_building_locators.txt` ve eksik `special.txt` için yukarıdaki keep-current/fallback kararlarını uygula; `id=6053` scale adayını ayrıca review et.
4. `Other/` kaynak paketinin merge kapsamına alınıp alınmayacağını kullanıcıyla kararlaştır.
5. Yalnız bu kanıtlardan sonra normal upstream merge'i `--no-commit` aşamasında aç ve belgelenen source hatalarını merge çözümünde düzelt.
6. Merge uygulanırsa aynı VS Code Tiger binary/config hattını, closure, region, locator ve binary-map auditlerini tekrar çalıştır; VS Code Problems görünümünü ayrıca yenile.
7. Son olarak Silk Road SEA/Angkor tasarım kararına dön.

### 2026-08-01 Bekleyen Asıl Mod Pre-Merge Closure

- Bu bölüm, yukarıdaki `2026-07-30 Upstream Fetch-Only Envanteri` bölümünün güncel devamıdır; eski revision ve sayıların tarihsel kaydını silmez.
- Güncel Git çapaları:
  - Yusseter HEAD: `b27d8ddb63f568839cd96e024607ab7f0e227497`
  - son birleşmiş asıl mod / merge-base: `ed1520220c1e8469a9865e3f69c57bcc399df0c5`
  - önceki asıl mod ucu: `3457500ca690067e322100de853ab6ab0bc8a834`
  - güncel asıl mod ucu: `66fba32c38b49905619118f9f6676e7757b13201`
- Bekleyen aralık yedi commit, 21 canlı `BookmarksGit` yolu, 1.362 `Other/` yolu ve bir `error.log` değişikliği içerir.
- Canlı çalışma ağacındaki beş kullanıcı değişikliği ile bekleyen 21 canlı yol arasında doğrudan çakışma yoktur.
- Merge, stage, commit veya push yapılmadı; canlı `BookmarksGit` kaynakları değiştirilmedi.

#### Revision-Kilitli Karar Sistemi

- Araç: `.codex/works/tools/build_pending_upstream_premerge_closure.py`.
- Düzenlenebilir karar girdisi: `.codex/works/analysis/upstream_update_decisions/pending_upstream_path_decisions_manual.csv`.
- Çıktı kökü: `.codex/works/analysis/generated/pending_upstream_premerge_closure`.
- Araç şu korumaları zorunlu uygular:
  - karar CSV'sindeki base/upstream revisionları güncel Git revisionlarıyla birebir olmalıdır
  - inventory, gerçek `git diff base..upstream` içindeki bütün canlı yolları eksiksiz kapsamalıdır
  - bekleyen canlı yol ile tracked veya untracked çalışma ağacı arasında çakışma olmamalıdır
  - inventory, Tiger, province-history, title-history ve map/locator kanıtlarının revision metadata'sı uyuşmalıdır
  - 17 Tiger kökünün tamamı en az bir dosya kararına bağlanmalıdır
  - merge-engelleyici kök taşıyan her dosyanın kararı `block_*` olmalıdır
  - bütün kararlar `auto_apply=no` kalmalıdır
  - `block`, `hold`, `manual`, `review` veya sınıflandırılmamış karar varken sonuç `ready` olamaz
- Güncel sonuç:
  - merge kararı: `do_not_merge_yet`
  - canlı dosya kapsamı: `21/21`
  - Tiger kök kapsamı: `17/17`
  - merge-engelleyici Tiger kökü: `8`
  - karar grupları: `block=4`, `hold=4`, `manual=1`, `planned_resolution=11`, `review=1`
  - otomatik uygulama: `0`
  - ikinci çalıştırmada deterministik çıktı: `3/3` aynı SHA-256

#### Engelleyici Kökler ve History Kararları

- Sekiz merge-engelleyici kök:
  - `balhae_al_dynasty_parse_failure`
  - `balhae_mo_identity_collision`
  - `removed_dynasty_definitions_break_existing_characters`
  - `indosphere_history_lifetime_regressions`
  - `korean_baek_daeheung_identity_collision`
  - `missing_korean_gim_silla_character`
  - `undefined_goguryo_culture`
  - `undefined_poet_trait`
- Bu kökler dört canlı dosya ailesine bağlanır: `00_dynasties.txt`, `00_ASIA_INDOSPHERE.txt`, `00_ASIA_NORTHEAST.txt` ve `00_ASIA_SOUTH.txt`.
- Province-history üç yönlü sonuçta yalnız `11377` ve `11378` iki tarafça değiştirilmiştir. Asıl moddaki Laos anlamları, Yusseter'daki `b_IDO_Barat_Daya` ve `b_IDO_Tanimbar` kimlikleriyle çakışır; Yusseter blokları korunmalıdır.
- Title-history kanıtı:
  - güvenli bütün blok: `22`
  - entry işlemi: `262`
  - güvenli entry: `256`
  - manuel entry: `6`
- `00_ASIA_NORTH.txt` için güvenli entry'ler ayrı patch adayıdır; iki silme ve BalhaeGo kimlik zinciri manuel inceleme ister.
- `00_ASIA_SOUTH.txt` için Indosphere karakter zinciri düzelmeden güvenli görünen history entry'leri bile canlı dosyaya uygulanmayacaktır.

#### Diğer Kesin Kararlar ve Açık Kapsam

- `z_MB_game_start.txt` içindeki Dai Viet filtresinin `administrative_government` yerine `meritocratic_government` olması canlı title-history ve startup tasarımıyla uyumludur; bu dar upstream değişikliği alınacak adaydır.
- Harita/locator yollarına `3457500ca..66fba32c3` aralığında yeni dokunuş yoktur; önceki üç yönlü kanıt path-fresh olarak kalır:
  - `provinces.png` için Yusseter RGB içeriği korunur
  - `special.txt` moda yeniden eklenmez, vanilla fallback korunur
  - `special_building_locators.txt` için Yusseter biçimi korunur
  - `building_locators.txt` id `6053` scale değişikliği görsel review sonrasında alınabilir
- CoA/template dosyaları eksik Chuhan, Baijia ve Tamga assetleri ile duplicate CoA kararları kapanmadan alınmayacaktır.
- `Other/` altındaki 1.362 extraction/reference dosyası ve kökteki `error.log`, canlı-mod closure kapsamı değildir. Bunlar için ayrı merge politikası verilmeden genel merge yetkisi oluşmaz.
- Güncel yeniden çalıştırma komutu closure özetinde yer alır. Yeni asıl mod commitinde eski karar CSV'si revision kontrolünden bilinçli olarak geçmez; önce inventory, Tiger ve history auditleri yenilenmelidir.

#### Sonraki İşlem Sırası

1. Sekiz engelleyici kök için source-fix adaylarını canlı dosyaya dokunmadan ayrı patch/karar raporu olarak hazırla.
2. Eksik CoA asset paketlerinin gerçekten upstream dışında bulunup bulunmadığını kaynak envanteriyle son kez doğrula.
3. `Other/` ve `error.log` için include/keep-current politikasını açık karara bağla.
4. Yalnız bütün engeller kapandıktan ve kullanıcı merge onayı verdikten sonra normal `git merge --no-commit --no-ff upstream/main` aşamasına geç.
5. Merge çözümünden sonra aynı VS Code Tiger binary/config hattını, history, localization, map, locator, region ve runtime smoke kontrollerini yeniden çalıştır.
6. Upstream turu kapandıktan sonra Silk Road SEA/Angkor tasarım kararına dön.

### 2026-08-10 Asıl Mod Baseline Hatalarını Erteleme Kararı

- Güncel closure revizyonları:
  - Yusseter: `5b9f833f09e66ed169d7de96db1397e617608acd`
  - asıl mod: `835050bb9b104daee0ee0e34f3c6f18b1e1182f4`
- Kullanıcı kararı: asıl modda da aynı biçimde bulunan `shared_asil_mod_baseline` blocker köklerine şimdilik dokunulmayacak; bunlar bütün Yusseter/entegrasyon işleri bittikten sonra son ayrı geçişte ele alınacak.
- Bu karar hataları çözülmüş veya kabul edilmiş saymaz. Severity `blocker` olarak korunacak ve canonical closure raporundan çıkarılmayacak.
- Güncel bağımsız blocker kökleri:
  - toplam: `164`
  - son faza ertelenen asıl-mod kaynaklı küme: `143` kök / `248` ham blocker satırı
  - bunun `97` kökü `shared_asil_mod_baseline`
  - bunun `46` kökü asıl modun kendi history satırı ile kendi character katmanı arasında bulunan `asil_mod_source_native_regression`
  - şimdi ele alınacak gerçek entegrasyon ve Yusseter kümesi: `21` kök / `25` ham blocker satırı
- Closure aracı iki ayrı çalışma listesi üretir:
  - `.codex/works/analysis/generated/repo_integration_closure/repo_integration_active_blocker_roots.csv`
  - `.codex/works/analysis/generated/repo_integration_closure/repo_integration_deferred_asil_mod_roots.csv`
- `58` upstream-integration karakter/title-history kökü source-origin açısından ayrıca ayrılmıştır:
  - `46` source-native asıl-mod regresyonu ertelenmiştir
  - `9` cross-layer character identity/yaşam tarihi çakışması aktif manuel incelemededir
  - `3` Yusseter featured-bookmark karakter bağımlılığı aktif recovery incelemesindedir
- Region review bulguları ve asıl-mod baseline hataları bu aktif karakter düzeltme grubuyla karıştırılmayacaktır.
- İlk karakter recovery dry-run sonucu:
  - ilk yalnız yaşam-tarihi kontrolünde görünen `24` pre-merge aday, dependency ve source-origin denetiminden sonra topluca güvenli sayılmamıştır
  - `21` normal character restore adayı source-native asıl-mod regresyonu olduğu için ertelenmiştir
  - `24` historical asıl-mod donor adayı ve donorsuz `13841 / c_dole` aynı source-native grupta ertelenmiştir
  - featured aday `12782000` bütün doğrudan static bağımlılıkları çözülmüş tek yüksek güvenli satırdı; `BookmarksGit/history/characters/00_YB_UPSTREAM_CHARACTER_RECOVERY.txt` içinde uygulandı
  - featured aday `10125001`, eksik pre-merge parent `10125000` nedeniyle bloklanmıştır
  - featured aday `10125010`, eksik pre-merge parent `11000113` nedeniyle bloklanmıştır
  - `9` cross-layer kimlik/yaşam tarihi çakışması manuel incelemede kalmıştır
  - uygulanan dosyada tek top-level ID `12782000` benzersizdir ve referans tarihi donor yaşam aralığındadır
  - Tiger'da `12782000` eksik-character raporu ve recovery dosyasına ait rapor `0`; VS Code Tiger JSON'u aynı güncel hash ile yayımlandı
  - bookmark runtime auditinde `12782000` artık `alive`; yalnız oyun içi holder/startup davranışı için blocker olmayan smoke-test review'u kalır
  - uygulama sonrası closure: `164` bağımsız kök, `273` blocker satırı, `32 full`, `3 partial`, `0 stale`
  - dry-run önizleme kuyruğu artık `0`; kalan adayların tamamı dependency veya manuel identity incelemesindedir
- Dry-run kanıtları:
  - `.codex/works/analysis/generated/repo_integration_closure/upstream_integration_character_roots/upstream_integration_character_recovery_dry_run.csv`
  - `.codex/works/analysis/generated/repo_integration_closure/upstream_integration_character_roots/upstream_integration_character_recovery_preview.patch`

### 2026-09-09 `.codex` Dizin Düzeni

- Koruma kuralı kesinleştirildi: sabit yol veya ad değil; dosyanın içeriği, işlevi ve kullanıcı sahipliği korunur. Daha iyi bir düzen için yollar değiştirilebilir, ancak bütün etkin tüketiciler birlikte taşınır ve içerik doğrulanır.
- Canlı mod artık doğrudan `BookmarksGit/descriptor.mod` ile kullanıldığı için eski `.codex/test_files/` aynası kaldırıldı. Etkin araçların test aynasına yazma ve senkronlama davranışları kaldırıldı; tarihsel plan ve hafıza kayıtları geçmiş kanıt olarak bırakıldı.
- Province/definition pipeline'ına ait dağınık çıktılar `.codex/works/analysis/generated/province_definition/` altında toplandı. Taşınan 67 kök dosya ile `rgb_conflict_previews/` içeriği dahil toplam 305 dosyanın SHA-256 değerleri taşıma öncesi ve sonrasında birebir doğrulandı.
- Kullanıcının Paint.NET ile düzenlediği kaynaklar `.codex/works/map_data_sources/manual_sources/` altında korunur ve otomasyon bu klasöre yazmaz.
- MPE harita kaynakları `.codex/works/map_data_sources/mpe/` altında tutulur.
- Kullanıcının düzenlediği canonical title relation tablosu `.codex/works/pipeline_inputs/title_relations/curated_title_relations.csv` dosyasıdır; otomasyon bu dosyanın üzerine yazmaz.
- Tarihsel plan dosyaları `YYYY.MM.DD[_HH.mm]-konu.md` standardına geçirildi. Güvenilir saat bilinmiyorsa saat uydurulmaz.
- `_merge_restore_backups` etkin generated alanından `.codex/works/archive/merge_restore_backups/` altına taşındı. Kök `ornek.gitattributes`, `ornek.gitignore` ve yalnız test aynasına ait generated paket kaldırıldı.
- Bu düzenleme turunda canlı `BookmarksGit/` içeriği değiştirilmedi; Git staging veya commit yapılmadı.

### 2026-09-13 Proje Hafızası ve Yerel Codex Alanları

- `.codex/memory/hafiza.md`, içeriği ve SHA-256 değeri korunarak `.codex/memory/project_memory.md` adına taşındı.
- `.codex/memory/project_memory.md` ile `.codex/plans/` kalıcı proje bilgisi oldukları için Git'te tutulur.
- `.codex/prompts/`, kullanıcının Codex'e yazamadığı zamanlarda isteklerini önceden hazırladığı kişisel yerel arşivdir; içeriği silinmeden Git tarafından yok sayılır.
- `.codex/memory/local/`, makineye veya kişiye özel geçici notlar için ayrılmış ve Git tarafından yok sayılan alandır.
- Prompt arşivindeki eski tarihli metinler otomatik olarak güncel talimat kabul edilmez; gerekli kalıcı kararlar proje hafızasına veya planlara aktarılır.

### 2026-09-13 Silk Road SEA/Angkor Karar Doğrulaması

- Kullanıcının `.codex/prompts/2026.08.02_13.44-bazi_tespit_ettigim_hatalar/bazi_tespit_ettigim_hatalar.prompt.md` içindeki özgün talebi, doğu Silk Road ve kalan doğu region üyelikleri için vanilla yapısını yetkili kaynak olarak belirler.
- Vanilla yapısında SEA subregion, Angkor market ve Angkor bağlantı okları bulunmadığından upstream'e özgü eksik SEA/Angkor kolu Yusseter'a kısmen uyarlanmayacaktır.
- SEA/Angkor kolu region, situation, market, building, decision, effect, event, localization ve ok tüketicilerinden birlikte kaldırılacaktır; yalnız market ekleyen yarım çözüm uygulanmayacaktır.
- Önceki “kullanıcı tasarım tercihi bekleniyor” kaydı tarihsel durumu anlatır; karar artık beklemede değildir.

### 2026-09-16 Asıl Mod `74a26a897` Merge Kapanışı

- Asıl modun güncel `main` ucu `74a26a897e8c26e2b1a91680447a3adcffa960c6` olarak yeniden doğrulandı ve `2ef00cf8d` merge commitinde Yusseter'a alındı. Push yapılmadı.
- Asıl mod checkout'undaki ilgisiz kirli harita/descriptor/yerel çalışma dosyaları yok sayılmadı; kapsam açısından incelendi. Merge kaynağı yeniden üretilebilir `upstream/main` Git commit nesnesi olarak tutuldu.
- Gerçek merge çatışmaları yalnız `00_MB_PROVINCES.txt` ve `geographical_region.txt` dosyalarındaydı. Province history çözümü vanilla-doğu, taşınmış MPE history ve Yusseter kimliklerini korudu; region çözümü SEA/Angkor hariç tutma kararını korurken yeni bağımsız upstream regionlarını aldı.
- Merge sonrası Tiger iki tanımsız `c_zhenxi` liege referansı buldu. `d_ningjiang_china -> d_kuizhong` ve `d_xichuan_china -> d_xichuan` düzeltmeleri `88553632a` commitinde uygulandı; yeni holder kronolojisi korundu.
- CK3-Tiger, VS Code eklentisinin kullandığı aynı `1.19.0` binary ve aynı `BookmarksGit/ck3-tiger.conf` ile çalıştırıldı. Yusseter sonucu `16435`, asıl mod sonucu `16139` rapordur; güncel Yusseter JSON'u VS Code Tiger loguna yayımlandı.
- Final repo closure sonucu: `6004` bulgu, `245` ham blocker, `145` bağımsız blocker kökü, `32 full`, `3 partial`, `0 stale`.
- Aktif entegrasyon/Yusseter blocker kökü `0`dır. Kalan `145` kökün tamamı karara uygun biçimde son asıl-mod cleanup geçişine ertelenmiştir: `87` shared baseline ve `58` asıl-mod source-native regresyon kökü.
- Genel geographical-region auditinde blocker yoktur; `11420/11420` doğrudan referans geçerlidir. Silk Road market auditindeki tek blocker ortak asıl-mod Constantinople localization biçim hatasıdır ve şimdilik ertelenmiştir.
- Province-history auditindeki iki blocker (`gaianites`, `religion = buryat`) ortak asıl-mod borcudur. MPE current-state closure blocker üretmemiştir.
- Üç bilinçli partial alan kalır: oyun motoru bookmark/runtime smoke testi, Silk Road market GUI/travel smoke testi ve hedef tracking görüntüsü güncel mapten eski olduğu için province-relation manuel karar katmanı.
- Merge öncesinde saklanan `BookmarksGit/fonts/fonts.font` kullanıcı WIP'i çalışma ağacına hash eşitliğiyle geri getirildi. `pre-upstream-20260914-fonts-wip` stash'i güvenlik yedeği olarak korunur; font değişikliği commitlenmedi.
- Son kullanıcı adımı: VS Code Problems görünümünü yenilemek için `ck3tiger: Get problems from the log file`; ardından uygun olduğunda `1178.10.1` bookmark'ında kısa runtime smoke testi.

### 2026-09-20 Merge Sonrası Silk Road ve Yerel Audit Kapanışı

- Asıl mod `main` ucu 20 Eylül'de salt-okuma sorgusuyla yeniden doğrulandı: `74a26a897e8c26e2b1a91680447a3adcffa960c6`. Bu commit mevcut Yusseter HEAD'in atasıdır; bekleyen upstream merge yoktur.
- Kullanıcının `1178.10.1` Silk Road oyun içi gözlemleri `.codex/works/analysis/reports/2026.09.16_22.27-silk-road-runtime-smoke-test.md` içinde kaydedildi. Bozuk `building_...` adı yoktur ve SEA/Angkor kolu beklendiği gibi yoktur. Lhasa/Potala, Baghdad/Ukbara ve Chang'an/Zhouzhi market yerleşimleri aynı county içindeki özel bina slotu gerekçesiyle korunur. Panel satırları kamerayı taşımıyor; bölgesel `Bazaar`, `Marketplace` ve `Khrom` adları tek başına hata değildir.
- Baghdad ve Constantinople kararlarında yanlış `Shuka of Dvin` etiketi, Constantinople market ikonunun görünmemesi ve eksik localization kapanış tırnağı asıl modla ortak bulgulardır. Mevcut erteleme politikası gereği canlı dosyalarda düzeltilmediler. Chang'an, Baghdad ve Constantinople seyahat kararlarının gerçek varış province'leri henüz oyun içinde doğrulanmadı; Silk Road runtime coverage bu nedenle `partial` kalır. İkonun locator örtüşmesi yüzünden gizlendiği güçlü adaydır, kesin runtime nedeni olarak sunulmaz.
- Yusseter'a özgü Green Death açıklama koşulunda eski `8748` province ID'si (güncel Jingyan) `10108` (güncel Killala) ile değiştirildi: `BookmarksGit/common/epidemics/z_MB_epidemics.txt`.
- Güncel hedef base adıyla birebir eşleşen 83 eksik İngilizce title adjective anahtarı `BookmarksGit/localization/replace/english/z_MB_titles_l_english.yml` dosyasına eklendi. 421 aynı-tier ad uyuşmazlığı ve 1 cross-tier aday otomatik uygulanmadı; manuel inceleme olarak kaldı.
- Audit araçları güncel asıl-mod revisionuna geçirildi; default.map geniş RANGE içindeki pikseli olmayan placeholder'lar yanlış blocker sayılmıyor; classifier freshness girdileri ve deterministik CSV yazımı düzeltildi. Son closure: `6121` bulgu, `245` blocker, `5615` review, `261` info; `32 full`, `3 partial`, `0 stale`. Aktif entegrasyon/Yusseter blocker kökü `0`; asıl-mod kaynaklı `145` kök / `245` ham blocker satırı son faza ertelendi. Bunlar çözülmüş sayılmaz.
- Aynı VS Code eklentisinin Tiger binary/config/mod hattıyla güncel rapor üretildi, fakat VS Code Tiger JSON'u otomatik değiştirilmedi. Eski VS Code raporundaki 83 eksik adjective uyarısı ile kullanıcı `fonts.font` WIP'ine ait 1 uyarı güncel raporda yoktur; kullanıcı Problems görünümünü `ck3tiger: Get problems from the log file` ile yenilemelidir.
- `BookmarksGit/fonts/fonts.font` kullanıcı WIP'i ve `pre-upstream-20260914-fonts-wip` güvenlik stash'i korunur. Bu geçişin canlı düzeltmeleri için oyun içi yeniden test henüz yapılmadı; özellikle Green Death açıklaması ve yeni adjective adları statik/Tiger kanıtıyla doğrulandı.

### 2026-09-20 Title-History Liege Provenance Kontrolü

- `d_sanggan` (740), `d_shimen` (906) ve `k_hedong` (869) için önceki Tiger sınıflandırmasındaki `current_only_or_adapted_line` etiketi semantik kökeni göstermiyor: current title kimlikleri asıl moddaki `d_zhenwu_china`, `d_jianchang` ve `k_jin_china` kimliklerinden yeniden yazılmış. Asıl-mod Tiger aynı tarihlerde aynı holdersız-liege hatalarını raporluyor. `k_hedong` için 954 tarihli preexisting Yusseter satırının da aynı kaynak hatası var.
- Hatalar yanlış pozitif değil; Tiger'a göre bu tarihlerde liege ataması etkisiz. İlk ve sonraki bookmark başlangıçları doğrudan hata tarihlerine denk gelmiyor, fakat bu tarihsel satırları kendiliğinden güvenli yapmaz. Asıl-mod borcunu erteleme kararı geçerli; canlı title-history değiştirilmedi.
- Satır, holder aralığı, kaynak Git blob ve bookmark kanıtı: `.codex/works/analysis/reports/2026.09.20-title-history-liege-provenance.md`. Üç kökü Yusseter'a özgü yeni regresyon olarak düzeltme kuyruğuna koyma.

### 2026-09-20 Kaynakla Ortak Referans Adayları

- 191 title adayı gerçek tanımsız referans değildi: 99 CoA sözdizimi, 2 title-history `name` değeri ve 90 canlı tanımlı title kullanımı. Semantic audit parser'ı bunları artık entegrasyon hatası saymıyor; `e_dai_viet`, `d_luoshi` ve `k_goryeo` başka tier'lara körlemesine çevrilmemeli.
- Dokuz province satırı altı kaynak ID'sine bağlı. Tang, Min, Tibet ve Moğol satırlarında asıl-mod ID'si kendi yorum/bağlamıyla da çelişiyor; Balhae konumu kaynakta belirsiz. Janggala satırı gerçek province projection farkı taşısa da Kahuripan zaten yakındaki Panjalu kaydında kullanıldığından otomatik eşleme güvenli değil.
- Kanıt ve sonraki karar sınırları: `.codex/works/analysis/reports/2026.09.20-source-shared-reference-review.md`. Canlı `BookmarksGit/` dosyaları değiştirilmedi; asıl-moddan gelen hatalara dokunmama kararı sürüyor.
- Bağlı sınıflandırıcılar doğru sırayla yenilendi. Final closure `5930` bulgu, `245` blocker, `5424` review ve `261` info; coverage `32 full`, `3 partial`, `0 stale`. Önceki `6121` bulgudan düşen `191` satır yalnız yanlış title-aday gürültüsüdür; blocker sayısı değişmedi.

### 2026-09-22 Title-History Source-Overwrite İncelemesi

- `title_history_source_overwrite_candidates.csv` içindeki `384` title, ortak Git atası `35211ffab5`, pre-merge Yusseter `09588cbb5` ve birleşmiş asıl mod `74a26a897` arasında katman ve doğrudan entry düzeyinde karşılaştırıldı.
- `355` title'da Yusseter'a özgü kayıp bir delta yoktur. Farklar asıl modun normal tarih gelişimi, iki tarafta aynı değişim veya yalnız biçim farkıdır.
- `25` title'daki `48` benzersiz Yusseter entry'sinin tamamı güncel dosyalarda zaten korunmaktadır. Bunlar için geri yükleme yapılmayacaktır.
- Altı gerçek aynı-key çatışmasının ikisinde mevcut dosya Yusseter kararını korur: `c_BAL_west_hyeondeok / 860.1.1` ve `c_lingzhou / 1227.2.1`.
- Üç çatışmada güncel kaynak kronolojisi korunur: `c_jianchuan / 760.1.1`, `c_xiazhou / 1210.1.1` ve `c_yinzhou / 1210.1.1`. Eski holder'ları geri getirmek, `21` bookmark'ın tamamında geçerli olan yeni zincirleri ezip başka title'larda kullanılan karakterleri yeniden çoğaltacağından güvenli bir regresyon düzeltmesi değildir.
- `c_SUM_riak_nan_berbedur / 750.1.1` içindeki eski holder satırı Yusseter'a özgü değildir; asıl mod commit'i `fb3ecdb9237c51b4ddf10ebda4a3e9227ae446fc` kökenlidir. Tek satırı geri getirmek aktif bookmark'lardaki ertelenmiş `Indonesia*` kaynak borcunu çözmez.
- Sonuç: bu `384` aday için canlı `BookmarksGit` değişikliği gerekmez. Ayrıntılı kanıt `.codex/works/analysis/reports/2026.09.22-title-history-source-overwrite-review.md` dosyasındadır; `fonts.font` kullanıcı WIP'i değişmeden kalmıştır.

### 2026-09-22 Title Adjective Localization İncelemesi

- Önceki P1 raporundaki `422` mapped title-adjective adayı current, vanilla ve raw vanilla landed-title katmanlarıyla yeniden incelendi; hedef title'ların tamamı vanilla'da tanımlıdır.
- `412` hedefin etkin current base adı vanilla base adıyla birebir aynıdır ve vanilla da bunlar için açık `_adj` anahtarı sağlamaz. Bu satırlar `vanilla_native_title_adjective_gap`, `P3` ve `no_action_unless_runtime_evidence_requires_explicit_adjective` olarak sınıflandırılır.
- Yusseter'ın vanilla'dan gerçekten farklı görünen ad verdiği `10` title için current hedef adıyla açık İngilizce adjective anahtarı `BookmarksGit/localization/replace/english/z_MB_titles_l_english.yml` dosyasına eklendi: `c_ca_mau_adj`, `c_hai_dong_adj`, `c_hengzhou_adj`, `c_hequ_adj`, `c_jianchuan_adj`, `c_longzhou_adj`, `c_luyang_adj`, `c_yunzhou_adj`, `d_wuxin_adj` ve `d_youzhou_adj`.
- Tek cross-tier aday `d_qiongguan_adj <- c_wananzhou_adj`, `412` vanilla-native satır içindedir; eski county sıfatı duchy'ye kopyalanmadı. Genel kural: eski mapped source adjective değeri yeni target title'a otomatik taşınmaz.
- Yenilenen P1 raporunda mapped-localization adayı `0`; CK3-Tiger current-only sınıflandırmasında vanilla-native satır tam olarak `412`dir. Ayrıntılı kanıt `.codex/works/analysis/reports/2026.09.22-title-adjective-localization-review.md` dosyasındadır.
- Ertelenen asıl-mod blocker kökleri ile kullanıcının `BookmarksGit/fonts/fonts.font` WIP'i değiştirilmedi.

### 2026-09-22 Duplicate Localization Kaynak Ayrımı

- P1 raporundaki `840` conflicting duplicate localization key, current değer kümesi ile güncel asıl-mod değer kümesi birebir karşılaştırılarak yeniden ayrıldı.
- `838` satırın değer kümesi güncel asıl modla tamamen aynıdır. Bunlar `shared_asil_mod_baseline`, P2 ve `deferred_until_final_asil_mod_cleanup` olarak görünür tutulur; mevcut karara göre son asıl-mod cleanup geçişine kadar canlı dosyada düzeltilmez.
- Yalnız `b_thang_long` ve `d_thang_long` Yusseter'da asıl moddan ek eski değer taşıyordu. `Đại La` ve `Kinh Bắc` adları upstream `35b5dab6c` kimlik yeniden-adlandırmasından kalmış, upstream `c41083975` cleanup commitinde kaldırılmış; Yusseter merge'i kaldırmaları kaçırmıştı.
- Eski `b_thang_long: "Đại La"`, `b_thang_long_adj: "Đại La"`, `d_thang_long: "Kinh Bắc"` ve `d_thang_long_adj: "Kinh Bắc"` satırları kaldırıldı; upstream ile uyumlu `d_thang_long_adj: "Thăng Long"` eklendi. Tekil `b_thang_long: "Thăng Long"` ve `d_thang_long: "Thăng Long"` değerleri korundu.
- Düzeltme sonrası duplicate localization satırı `838`, source-current değer farkı `0`, Thăng Long duplicate satırı `0`dır. Genel aktif P1 review satırı `1034 -> 194` düşerken `838` ortak satır kaybolmadı; ertelenmiş P2 kaynak borcu olarak kaldı.
- Ayrıntılı kanıt `.codex/works/analysis/reports/2026.09.22-localization-duplicate-source-review.md` dosyasındadır. `BookmarksGit/fonts/fonts.font` kullanıcı WIP'i değiştirilmedi.
