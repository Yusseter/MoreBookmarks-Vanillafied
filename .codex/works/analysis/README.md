# Analysis Layout

- `generated/`: yeniden üretilebilir ham JSON, CSV, PNG, patch ve ara raporlar. Elle düzenlenmez ve kökünde serbest dosya tutulmaz.
- `reports/`: uzun süre saklanması gereken kısa karar ve kapanış raporları.

`generated/province_definition/` province haritası, definition, ID politikası ve tracking zincirinin ortak çıktı alanıdır. Diğer audit sistemleri kendi adlarıyla ayrı alt klasörler kullanır.
`generated/` yeni dosyalar için ignore edilir; kalıcı karar girdileri burada tutulmaz.
Tarihsel çalışma planları `.codex/plans/` altında tutulur; `analysis/` köküne serbest dosya eklenmez.
