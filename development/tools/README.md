# Tools

Bu klasör yeniden kullanılabilir audit, üretim ve kontrollü uygulama araçlarını tutar.

## Path rules

- Proje kökü araç dosyasının konumundan bulunur; kullanıcıya özgü mutlak Yusseter yolları varsayılan yapılmaz.
- Canlı mod `BookmarksGit/`, kalıcı girdiler `development/pipeline_inputs/` altındadır; ayrı test aynası yoktur.
- Yeniden üretilebilir çıktılar yalnız `development/analysis/generated/` altında ve işlevsel sistem alt klasörlerinde yazılır.
- Upstream MBP için varsayılan, proje kökünün yanındaki `Leviathonlx MoreBookmarks-Plus/` klasörüdür; komut satırı parametreleriyle değiştirilebilir.
- Vanilla, Workshop modları, Tiger ve CK3 kullanıcı verileri makineye özgü dış bağımlılıklardır. Bir araçtaki eski `0backup` yolu yoksa güncel upstream onun yerine kendiliğinden kullanılmaz; doğru tarihsel kaynak açıkça verilmelidir.

## Safety rules

- Audit araçları canlı mod dosyalarını değiştirmez.
- Uygulama araçları mümkün olduğunda dry-run varsayılanıyla çalışır ve yazma için açık bir seçenek ister.
- Araçlar `map_data_sources/manual_sources/` veya `curated_title_relations.csv` üzerine otomatik yazmaz.
- `__pycache__/` ve diğer derlenmiş önbellekler kaynak değildir; Git'e alınmaz.

Araçlar şimdilik aynı klasörde tutulur, çünkü bazı Python araçları birbirini sibling import ile kullanır. Konu alt klasörlerine taşıma ancak import ve komut bağımlılıkları birlikte güncellendiğinde yapılır.
