# Curated Title Relations

`curated_title_relations.csv` güncel title karşılıkları için canonical ve kullanıcı tarafından düzenlenen tek tablodur.
`title_relation_baseline.csv` araçların ürettiği karşılaştırma baseline'ıdır; kullanıcı karar tablosu değildir.

## Ownership

- Dosyanın sahibi kullanıcıdır; araçlar bu dosyayı yerinde yeniden yazmaz.
- Otomatik adaylar ve refresh sonuçları `analysis/generated/` altında ayrı dosyalara yazılır.
- Bir aday ancak kullanıcı kararıyla bu tabloya alınır.
- Mevcut kolon adları araç uyumluluğu için korunur; dosya adı eski `manual/new/master` süreç adlarını taşımaz.

## Validation

Dosya taşınırken içerik SHA-256 değeri korunmalıdır. Tüketen araçlar varsayılan olarak yalnız bu canonical yolu kullanmalıdır.
