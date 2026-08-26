# 🍉 Karpuz Pack 1.20.1

Karpuz Network sunucusunun Launcher tarafından yönetilen resmî istemci paketi.

[![Validate Pack](https://github.com/karpuz-network/karpuz-files/actions/workflows/validate.yml/badge.svg)](https://github.com/karpuz-network/karpuz-files/actions/workflows/validate.yml)

## Güncel paket

| Özellik | Değer |
|---|---|
| Minecraft | 1.20.1 |
| Forge | 47.4.22 |
| Benzersiz etkin JAR | 94 |
| Packwiz paket sürümü | 1.2.0 |
| Hash biçimi | SHA-256 |
| Mod arşivi | `https://mods.karpuz.network/Karpuz-Network-Modpack-1.2.0.zip` |

Tam ve doğrulanabilir dosya listesi `index.toml`, mod arşivi envanteri ise `mods-manifest.json` içindedir. README bilerek ikinci bir mod listesi tutmaz; böylece dokümantasyon ile canlı paket birbirinden kopmaz.

Paketin öne çıkan içerikleri arasında Blue Skies, The Aether, Alex's Caves, Alex's Mobs, L_Ender's Cataclysm, Apotheosis, Biomes O' Plenty, Born in Chaos, Aquamirae ve Galosphere bulunur.

## Bütünlük zinciri

Launcher aşağıdaki zinciri izler:

1. `pack.toml` dosyasını GitHub Raw üzerinden alır.
2. `index.toml` ve `mods-manifest.json` dosyalarının SHA-256 değerlerini `pack.toml` ile karşılaştırır.
3. `mods`, `config`, `resourcepacks`, `options.txt` ve `servers.dat` içindeki her yönetilen dosyayı ikili SHA-256 ile kontrol eder.
4. Sadece eksik veya bozuk dosyaları indirir; sağlam dosyaları yeniden indirmez.
5. `mods` klasöründeki pakete ait olmayan JAR/JARBAK dosyalarını temizler.
6. Kurulum sonunda yerel paket sürümünü ve index hash'ini `.karpuz-pack.json` dosyasına kaydeder.

Mod JAR'ları büyük oldukları için Git'e eklenmez. `mods-manifest.json`, R2'deki ZIP arşivinin boyutunu/hash'ini ve arşivde kurulacak her benzersiz JAR'ın boyutunu/hash'ini taşır.

## Depo yapısı

```text
karpuz-files/
├── pack.toml
├── index.toml
├── mods-manifest.json
├── config/
├── resourcepacks/
├── options.txt
├── servers.dat
├── scripts/build_packwiz_from_zip.py
└── .github/workflows/
```

## Paketi güvenli biçimde yenileme

Yeni `mods.zip` hazırlandıktan sonra mevcut arşivi ve bu depodaki manifestleri aynı sürümde tut:

```powershell
python scripts/build_packwiz_from_zip.py "C:\paketler\mods.zip" --version 1.2.0
```

Betik:

- `.jarbak` ve diğer devre dışı dosyaları pakete katmaz;
- aynı SHA-256 değerine sahip birebir JAR kopyalarını eler;
- bütün yönetilen dosyalar için `index.toml` üretir;
- ZIP ve JAR hash'leriyle `mods-manifest.json` üretir;
- `pack.toml` sürümünü ve kök hash'lerini günceller.

Ardından ZIP dosyasını önce sürümlü adıyla, sonra `Karpuz-Network-Modpack.zip` sabit bağlantısıyla R2'de yayımla; değişiklikleri incele ve üç metadata dosyasını birlikte commit et. Arşiv ile manifest hash'i uyuşmadan Launcher kuruluma başlamaz.

## Lisans

All Rights Reserved © Karpuz Network
