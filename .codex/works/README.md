# Works Layout

## Canonical directories

- `tools/`: yeniden kullanılabilir audit, dönüşüm ve uygulama araçları.
- `pipeline_inputs/`: araçların okuduğu, karar veya istisna taşıyan kalıcı girdiler.
- `map_data_sources/`: harita birleştirme kaynakları ve kullanıcıya ait görsel çalışma dosyaları.
- `analysis/generated/`: araçlar tarafından yeniden üretilebilen ham ve ara sonuçlar; her sistem kendi alt klasörünü kullanır.
- `analysis/reports/`: seçilmiş, kısa ve kalıcı insan-okur kapanış raporları.
- `archive/`: canonical olmayan salt-okunur baseline, eski sürüm ve tarihsel raporlar.

## Ownership rules

- `pipeline_inputs/` dosyaları rapor değildir; otomasyonun davranışını belirler ve değişiklikleri incelenmelidir.
- `map_data_sources/manual_sources/` kullanıcı tarafından düzenlenen kaynak belgelerdir. Araçlar bu klasöre yazmaz.
- `analysis/generated/` elle düzenlenmez ve yeni dosyaları Git tarafından yok sayılır.
- `analysis/generated/` kökünde serbest dosya tutulmaz; province-definition zinciri `province_definition/` altındadır.
- `archive/` etkin araçların girdisi değildir; yalnız tarihsel ve geri başvuru amaçlı içerik barındırır.

## Migration rule

Bir dosya ancak tüm etkin tüketicileri yeni yola geçirildikten ve aynı içerik/hash korunduğu doğrulandıktan sonra taşınır. Yalnız sahiplik adlandırması gibi belgelenmiş metadata normalizasyonlarında işlevsel anahtarların birebir eşitliği ayrıca doğrulanır.
