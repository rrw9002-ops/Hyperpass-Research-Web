from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_release import TOP_FILES, TEAM_FILES, build, release_path


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "한글 공백 project"
        self.root.mkdir()
        for name in TOP_FILES:
            (self.root / name).write_text("fixture", encoding="utf-8")
        for name in TEAM_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("default team guidance", encoding="utf-8")
        for name in ("hyperpass/engine.py", "methods/risk-manager.md", "static/index.html", "references/research-framing.md"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("public", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_private_data_and_credentials_excluded(self):
        secret = "PRIVATE-KEY-NOT-FOR-RELEASE-1234"
        for name in (".env", "data/runs/report.json", "data/credentials.json", "secrets/key.txt",
                     "hyperpass/__pycache__/engine.pyc", "static/.env", "docs/private/key.md",
                     ".git/config", "context/investor.md", "dist/user.json", "hyperpass/credentials/key.py",
                     "team/.history/common-private.md", "team/.edit-lock/.instance.lock", "team/roles/custom-role.md"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(secret, encoding="utf-8")
        archive = build(self.root)
        with zipfile.ZipFile(archive) as z:
            self.assertTrue(all(secret.encode() not in z.read(n) for n in z.namelist()))
            self.assertIn("Hyperpass-Research-Web/Start-Windows.cmd", z.namelist())
            self.assertIn("Hyperpass-Research-Web/methods/risk-manager.md", z.namelist())
            self.assertIn("Hyperpass-Research-Web/references/research-framing.md", z.namelist())
            self.assertEqual({n.removeprefix('Hyperpass-Research-Web/') for n in z.namelist() if '/team/' in n}, TEAM_FILES)

    def test_path_traversal_and_unknown_extensions_rejected(self):
        for name in ("../secret", "/app.py", "C:/secret", "docs/../secret.md", "docs\\secret.md",
                     "hyperpass/credentials.json", "docs/personal.sqlite", "static/test.map", "docs//a.md"):
            self.assertFalse(release_path(name), name)

    def test_mac_start_is_executable_and_archive_reproducible(self):
        first = build(self.root, Path(self.temp.name) / "first")
        second = build(self.root, Path(self.temp.name) / "second")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as z:
            mode = z.getinfo("Hyperpass-Research-Web/Start-Mac.command").external_attr >> 16
            self.assertEqual(mode & 0o777, 0o755)
        self.assertIn(hashlib.sha256(first.read_bytes()).hexdigest(), first.with_suffix(".zip.sha256").read_text())

    def test_missing_launcher_refuses_package(self):
        (self.root / "Start-Windows.cmd").unlink()
        with self.assertRaises(ValueError):
            build(self.root)

    def test_missing_team_default_refuses_incomplete_package(self):
        (self.root / 'team/roles/head-manager.md').unlink()
        with self.assertRaises(ValueError):
            build(self.root)

    def test_mac_binary_is_explicit_architecture_and_executable(self):
        (self.root / 'dist').mkdir()
        binary = self.root / 'dist/Hyperpass-Research-Web'
        binary.write_bytes(b'\xcf\xfa\xed\xfe' + b'fixture, not a runnable binary')
        archive = build(self.root, mac=True, architecture='arm64')
        self.assertEqual(archive.name, 'Hyperpass-Research-Web-macOS-arm64.zip')
        with zipfile.ZipFile(archive) as package:
            mode = package.getinfo('Hyperpass-Research-Web/Hyperpass-Research-Web').external_attr >> 16
            self.assertEqual(mode & 0o777, 0o755)
        binary.write_bytes(b'not Mach-O')
        with self.assertRaises(ValueError):
            build(self.root, mac=True, architecture='arm64')


if __name__ == "__main__":
    unittest.main()
