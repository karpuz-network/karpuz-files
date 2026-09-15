# private-mods

Karpuz Network'e ait (kendi geliştirdiğimiz) ve resmî platformlarda barındırılmayan mod JAR'ları.

- Bu dosyalar `mods/*.pw.toml` metafile'larındaki `[download] url` alanı ile referans verilir
  (`raw.githubusercontent.com/karpuz-network/karpuz-files/...`).
- `.packwizignore` içindeki `private-mods/**` kuralı sayesinde `packwiz refresh` bu dosyaları index'e almaz.
- Yeni bir özel mod eklerken:
  1. JAR'ı bu klasöre koyun,
  2. `scripts/private-mods.json` dosyasına dosya adı → url eşlemesini ekleyin,
  3. `py scripts/packwiz_add_from_jars.py --cf-key <KEY>` çalıştırın (metafile + index yenilenir).

Not: CurseForge veya Modrinth'te bulunmayan bu modlar için GitHub Release asset'i de kullanılabilir;
tek yapılması gereken `scripts/private-mods.json` içindeki `url` değerini release asset adresine çevirmektir.