# Changelog

## 1.5.1

- **Just Zoom** (`justzoom_forge_2.1.1_MC_1.20.1.jar`) pakete eklendi; metafile'ı Modrinth resmî CDN linki ve sha512 hash'i ile üretildi.
- `scripts/packwiz_add_from_jars.py` artık `--add <ad veya alt dize>` ile pakete yeni mod ekleyebiliyor; pakete dahil olmayan yerel JAR'lar konsolda raporlanıyor.
- Paketin mod listesi artık `index.toml` içindeki `mods/*.pw.toml` metafile'larından türetiliyor (yeni format).

## 1.5.0

- Mod indirmeleri Cloudflare R2 ZIP arşivinden çıkarıldı; modlar artık `mods/*.pw.toml` metafile'larındaki resmî indirme linkleriyle (Modrinth / CurseForge CDN) doğrulanıp indiriliyor.
- `mods-manifest.json` ve `pack.toml` içindeki `[karpuz]` bloğu kaldırıldı.
- `index.toml` `packwiz refresh` ile kanonik üretiliyor; `options.txt` ve `servers.dat` `preserve = true` olarak işaretlendi.
- Karpuz Network'e ait özel modlar (`karpuzbadge` vb.) `private-mods/` altında GitHub'da barındırılıyor.
- Yerel JAR'lardan metafile üreten `scripts/packwiz_add_from_jars.py` ve yenilenen `scripts/validate_pack.py` eklendi; eski ZIP tabanlı betik kaldırıldı.

## 1.3.0

- Oyuncuların KARPUZ LAUNCHER kullanımını yakından gösteren istemci rozeti eklendi.
- Paket 95 etkin `.jar` dosyasıyla yeniden doğrulandı.

## 1.2.0

- Paket `modlars` klasöründeki 94 etkin `.jar` dosyasıyla yenilendi.
- Beş devre dışı `.jarbak` dosyası paketin dışında bırakıldı.
- Forge sürümü `47.4.22` olarak sabitlendi.
- Mod arşivi, index ve manifest SHA-256 değerleri birlikte yenilendi.

## 1.1.0

- Güncel `mods.zip` kaynağından 91 benzersiz etkin mod için SHA-256 manifesti üretildi.
- Birebir aynı Placebo kopyası ile `.jarbak` dosyaları kurulum listesinden çıkarıldı.
- FancyMenu, resource pack, `options.txt` ve `servers.dat` dosyaları Packwiz indexine dâhil edildi.
- Arşiv, index ve manifest arasında doğrulanabilir bütünlük zinciri kuruldu.
- Sunucu erişimi gerektirmeyen yerel manifest üretim betiği eklendi.

Tüm önemli değişiklikler bu dosyada belgelenecektir.

Format [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) standardına uygundur.

## [1.0.0] - 2026-08-15

### Eklenen
- 82 mod ile ilk sürüm
- Packwiz tabanlı modpack yönetim sistemi
- GitHub Actions ile otomatik hash doğrulaması
- FancyMenu ile özel menü tasarımı
- Karpuz Resource Pack 0.1
- Önceden yapılandırılmış `options.txt` ve `servers.dat`

### Mod Kategorileri
- **Dünya Üretimi**: Biomes O' Plenty, Blue Skies, TerraBlender, Galosphere
- **Macera & Zindanlar**: Dungeon Crawl, L_Ender's Cataclysm, Aquamirae, Born in Chaos
- **Yaratıklar**: Alex's Mobs, Alex's Caves
- **Boyutlar**: The Aether, Blue Skies
- **Depolama**: Sophisticated Backpacks, Sophisticated Storage, Sophisticated Core
- **Performans**: ModernFix, Canary, Ferrite Core, Fast Furnace
- **Araçlar & Silahlar**: Simply Swords, Apotheosis, Artifacts
- **UI & QoL**: JEI, Jade, Controlling, Mouse Tweaks, Apple Skin, Inventory HUD
- **Sosyal & Ekonomi**: EconMC, Economy, FTB Quests, FTB Teams, FTB Ranks
- **Yapı**: Macaw's Furniture, Building Wands
- **Scripting**: KubeJS, Rhino, MoreJS
