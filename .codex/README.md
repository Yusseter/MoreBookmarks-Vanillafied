# Project Codex Files

Bu klasör, proje için Codex destek dosyalarını ve yerel çalışma verilerini tutar.
Canlı CK3 modu `BookmarksGit/` altındadır ve `BookmarksGit/descriptor.mod` ile doğrudan oyunda açılır; ayrı bir test aynası kullanılmaz.

## Kalıcı alanlar

- `memory/project_memory.md`: projeye özel uzun süreli bilgi ve karar kaydı. Git'te tutulur; kullanıcı açıkça istemeden güncellenmez.
- `plans/`: tarihsel veya etkin çalışma planları.
- `works/`: araçlar, pipeline girdileri, harita kaynakları ve analiz sonuçları.

## Yerel alanlar

- `prompts/`: kullanıcının Codex'e hemen yazamadığı zamanlarda hazırladığı kişisel istek ve görsel arşivi. Yerelde korunur, Git tarafından yok sayılır ve otomatik olarak güncel gerçek kabul edilmez.
- `memory/local/`: makineye veya kişiye özel geçici notlar. Yerelde tutulur ve Git tarafından yok sayılır.

## Düzen ilkeleri

- Klasör ve dosya adları gerektiğinde değişebilir; korunması gereken içerik, işlev ve kullanıcı sahipliğidir.
- Kullanıcının elle düzenlediği kaynaklar otomasyon çıktılarından ayrı tutulur ve araçlar tarafından üzerine yazılmaz.
- Yeniden üretilebilir çıktılar işlevsel sistemlerine göre `works/analysis/generated/` altında gruplanır.
- Eski yollar ancak etkin tüketicileri yeni konuma geçirildikten ve içerik korunduğu doğrulandıktan sonra kaldırılır.

Git index temizliği, staging veya commit bu klasör düzenlemesinin parçası değildir.
