import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sync_crafty_mods", ROOT / "scripts" / "sync_crafty_mods.py")
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)


class SyncCraftyModsTests(unittest.TestCase):
    def test_only_active_jars_are_published_deterministically(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "mods.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mods/Beta.jar", b"beta")
                archive.writestr("mods/alpha.jar", b"alpha")
                archive.writestr("mods/disabled.jarbak", b"off")
            first = temp / "first.zip"
            second = temp / "second.zip"
            manifest = SYNC.prepare_pack(source, first, "https://mods.example")
            repeated = SYNC.prepare_pack(source, second, "https://mods.example")
            self.assertEqual([item["name"] for item in manifest["files"]], ["alpha.jar", "Beta.jar"])
            self.assertEqual(manifest, repeated)
            self.assertEqual(SYNC.sha256_file(first), SYNC.sha256_file(second))

    def test_duplicate_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_name:
            source = Path(temp_name) / "mods.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("one/Same.jar", b"a")
                archive.writestr("two/same.jar", b"b")
            with self.assertRaisesRegex(RuntimeError, "Yinelenen"):
                SYNC.prepare_pack(source, Path(temp_name) / "out.zip", "https://mods.example")


if __name__ == "__main__":
    unittest.main()
