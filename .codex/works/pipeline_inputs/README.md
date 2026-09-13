# Pipeline Inputs

Bu klasördeki dosyalar otomasyon tarafından okunan kalıcı girdilerdir. `manual` adı kullanılmaz; bir dosyanın burada bulunması kullanıcının onu elle yönettiği anlamına gelmez.

- `map/`: harita seçim maskeleri, sabit işlem kapsamları, locator seed listeleri ve korunacak piksel istisnaları.
- `province_relations/`: makine üretimli province relation baseline'ı.
- `title_relations/`: makine baseline'ı ile kullanıcı tarafından düzenlenen canonical title kararları.
- `province_history/`: province history aktarım kuralları ve istisnaları.
- `upstream/`: upstream entegrasyonunda verilen ve tekrar kullanılacak kararlar; örneğin `pending_path_decisions.csv`.

Bu girdiler otomatik olarak uygulanabilir kabul edilmez. Her araç kendi dry-run ve validation kurallarını uygulamalıdır.
