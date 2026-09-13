# Map Pipeline Inputs

- `masks/`: tam kaynak haritalara uygulanan exact siyah/beyaz seçim maskeleri.
- `scopes/`: belirli entegrasyon işlemlerinde kullanılan, tarihli ve sabit province kapsamları.
- `definition_marker_locator_seeds.csv`: definition marker province'leri için locator seed listesi.
- `source_pixel_overrides.csv`: korunması gereken az sayıdaki belgelenmiş piksel istisnası.

Piksel istisnaları hem beklenen kaynak rengini hem replacement rengini taşır. Beklenen renk değişirse yenileme aracı durur; eski karar yeni upstream değişikliğini sessizce ezmez.
