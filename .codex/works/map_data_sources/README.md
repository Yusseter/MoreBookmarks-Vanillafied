# Map Data Sources

Bu klasör province haritası birleştirme pipeline'ının kaynak verilerini tutar. Canlı oyun haritası `BookmarksGit/map_data/provinces.png` dosyasıdır ve bu klasördeki yenileme aracı tarafından değiştirilmez.

## Source roles

- `provinces_modlu.png`: upstream MBP tam province haritası.
- `provinces_orijinal.png`: vanilla tam province haritası ve belgelenmiş yerel piksel istisnaları.
- `definition_modlu*.csv` / `definition_orijinal*.csv`: tam kaynakların ve seçili parçaların province kimlik sözlükleri.
- `provinces_modlu_dogu.png` / `provinces_modlu_kalan.png`: upstream kaynağın seçim maskeleriyle üretilmiş parçaları.
- `provinces_orijinal_dogu.png` / `provinces_orijinal_kalan.png`: vanilla kaynağın seçim maskeleriyle üretilmiş parçaları.
- `provinces_birlesim.png`: vanilla doğu ile upstream kalan bölümünün kaynak birleşimi. Canlı haritanın yerine otomatik kopyalanmaz.
- `mpe/`: MPE import işlemlerinin harita kaynakları.
- `manual_sources/`: kullanıcının Paint.NET ile düzenlediği PDN ve görsel kaynaklar. Otomasyon bu klasöre yazmaz.

Sabit işlem kapsamları `pipeline_inputs/map/scopes/`, province/title relation baseline'ları ise kendi `pipeline_inputs/*_relations/` klasörlerinde tutulur. Bu klasör karar tabloları veya tarihsel kapsam kopyaları için kullanılmaz.

## Refresh workflow

İlk kurulumda mevcut seçim PNG'lerinden exact siyah/beyaz maskeleri bir kez üret:

```powershell
python .codex/works/tools/refresh_map_data_sources.py --bootstrap-masks
```

Kullanıcı PDN kaynaklarında seçim sınırını bilinçli olarak değiştirdikten ve dört seçim PNG'sini yeniden export ettikten sonra maskeleri açıkça yenile:

```powershell
python .codex/works/tools/refresh_map_data_sources.py --force-bootstrap-masks
```

`--force-bootstrap-masks` normal upstream yenilemesinde kullanılmaz.

Sonraki upstream/vanilla değişikliklerinde yalnız önizleme ve fark raporu üret:

```powershell
python .codex/works/tools/refresh_map_data_sources.py
```

Rapor beklendiği gibiyse yalnız bu klasördeki kaynak PNG'leri güncelle:

```powershell
python .codex/works/tools/refresh_map_data_sources.py --apply
```

Onaylı maskeler `.codex/works/pipeline_inputs/map/masks/`, önizlemeler ve manifest ise `.codex/works/analysis/generated/map_data_source_refresh/` altında tutulur. RGB değerleri ölçekleme, anti-aliasing veya palet dönüşümü olmadan korunur.

İlk doğrulanan maskeler bütün 9216x4608 tuvali kapsar ve doğu/batı sınırında iki piksellik belgelenmiş örtüşme taşır. Bu iki piksel `source_pixel_overrides.csv` ile açıkça çözülür. Kaynak birleşimini canlı haritaya geçirmek ayrı definition/remap closure kontrolü gerektirir.
