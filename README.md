# 🍉 Karpuz Pack 1.20.1

Karpuz Network sunucusunun Launcher tarafından yönetilen resmî istemci paketi.

[![Validate Pack](https://github.com/karpuz-network/karpuz-files/actions/workflows/validate.yml/badge.svg)](https://github.com/karpuz-network/karpuz-files/actions/workflows/validate.yml)

## Güncel paket

| Özellik | Değer |
|---|---|
| Minecraft | 1.20.1 |
| Forge | 47.4.22 |
| Benzersiz etkin JAR | 98 |
| Packwiz paket sürümü | 1.5.1 |
| Index hash biçimi | SHA-256 |
| Mod kaynakları | Modrinth + CurseForge resmî CDN + Karpuz özel modları (GitHub) |

Tam ve doğrulanabilir dosya listesi `index.toml` içindedir. Her mod için resmî indirme linki ve hash, `mods/*.pw.toml` metafile dosyalarında tutulur. README bilerek ikinci bir mod listesi tutmaz.

## Bütünlük zinciri

Launcher aşağıdaki zinciri izler:

1. `pack.toml` dosyasını GitHub Raw üzerinden alır ve `index.toml`'un SHA-256 değerini doğrular.
2. `index.toml` içindeki her mod (`metafile = true`) için ilgili `mods/*.pw.toml` dosyasını okuyup resmî indirme linkini ve hash'ini alır.
3. `config`, `resourcepacks`, `options.txt` ve `servers.dat` içindeki her dosyayı ikili SHA-256 ile kontrol eder.
4. Sadece eksik veya bozuk dosyaları indirir: modlar resmî CDN linkinden, diğer dosyalar GitHub Raw'dan. Sağlam dosyalar yeniden indirilmez.
5. `mods` klasöründeki pakete ait olmayan JAR/JARBAK dosyalarını temizler.
6. `options.txt` ve `servers.dat` kullanıcı ayarlarını korur (yalnızca hiç yoksa indirilir; `preserve = true`).
7. `options.txt` içindeki `gamma` değeri 1'in üzerindeyse hile sayılır ve 0.5'e çekilir.
8. Kurulum sonunda yerel paket sürümünü ve index hash'ini `.karpuz-pack.json` dosyasına kaydeder.

## Depo yapısı

```text
karpuz-files/
├── pack.toml                 ← sürüm, index.toml hash'i, MC/Forge sürümleri
├── index.toml                ← packwiz refresh tarafından üretilen kanonik index
├── .packwizignore            ← index'e alınmayacak repo dosyaları + yerel mod JAR'ları
├── mods/
│   └── *.pw.toml             ← her modun resmî indirme linki + hash'i (git'te)
├── private-mods/             ← Karpuz Network'e ait özel mod JAR'ları (git'te)
├── config/
├── resourcepacks/
├── options.txt
├── servers.dat
├── scripts/
│   ├── packwiz_add_from_jars.py   ← yerel JAR'lardan metafile + index üretir
│   ├── private-mods.json          ← özel modların URL eşlemesi
│   └── validate_pack.py           ← bütünlük zinciri doğrulama
└── .github/workflows/
```

Mod JAR dosyaları (`mods/*.jar`) büyük oldukları için Git'e eklenmez; indirme linkleri `mods/*.pw.toml` içindedir.

## Paketi güvenli biçimde yenileme

Ön koşullar: Python 3.12+, [packwiz](https://packwiz.infra.link/installation/) (PATH'te) ve CurseForge API anahtarı (`CF_API_KEY` — yalnızca bu betikte kullanılır, launcher'a asla girmez).

### 1) Mod ekleme / güncelleme / kaldırma

1. Yeni/güncel mod JAR'larını yerel `mods/` klasörüne koyun (kaldırılacakları silin).
2. Resmî linkleri çözümle ve metafile + index üret:
   ```powershell
   py scripts/packwiz_add_from_jars.py --cf-key $env:CF_API_KEY --cf-cdn-fallback
   ```
   Henüz pakette olmayan yeni JAR'ları `--add` ile açıkça belirtin (`--add` verilmezse paket dışı yerel JAR'lar yalnızca raporlanır):
   ```powershell
   py scripts/packwiz_add_from_jars.py --cf-key $env:CF_API_KEY --cf-cdn-fallback --add justzoom
   ```
   Betik Modrinth (hash ile), CurseForge (fingerprint ile) ve `scripts/private-mods.json` sırasını dener;
   çözülemeyen modları rapor eder ve durur. `--report-only` ile önce önizleme alabilirsiniz.
3. Doğrula:
   ```powershell
   py scripts/validate_pack.py
   ```
4. Commit & push:
   ```powershell
   git add pack.toml index.toml mods/ private-mods/ scripts/private-mods.json
   git commit -m "feat: modpack 1.5.1 - mod güncellemeleri"
   git push
   ```

### 2) Config / resource pack / ayar dosyası güncelleme

Mod JAR'larına dokunmadan sadece `config/`, `resourcepacks/`, `options.txt` veya `servers.dat` değiştiğinde:

1. Dosyaları düzenleyin.
2. Index'i yenileyin: `packwiz refresh` (metafile'lar değişmediği için hash'leri korunur; index hash'i ve varsa değişen repo dosyası hash'leri güncellenir).
3. `py scripts/validate_pack.py` ile doğrulayıp commit edin.

> [!CAUTION]
> `packwiz refresh` yerel `mods/*.jar` dosyalarını index'e almamalıdır — bunun için `.packwizignore` içinde `mods/*.jar` kuralı bulunur. Bu kuralı silmeyin.

## Özel modlar (Karpuz Network'e ait)

`karpuzbadge` gibi kendi yazdığımız ve resmî platformlarda bulunmayan modlar `private-mods/` klasöründe barındırılır; `mods/*.pw.toml` metafile'ındaki `url` alanı bu dosyaları GitHub Raw üzerinden işaret eder. Ayrıntılar: `private-mods/README.md`.

## Lisans

All Rights Reserved © Karpuz Network
