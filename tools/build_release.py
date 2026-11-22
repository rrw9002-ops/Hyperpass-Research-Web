"""Create a source ZIP from a narrow allowlist, never runtime/user data."""
from __future__ import annotations

import hashlib
import argparse
import platform
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hyperpass.team_config import DOCUMENTS

TOP_FILES = {"수강생-시작가이드.html", "app.py", "README.md", "LICENSE", "NOTICE", "Start-Windows.cmd", "Start-Mac.command", "Hyperpass-Research-Web.spec"}
TEAM_FILES = {"team/" + path for path in DOCUMENTS}
FONT_FILES = {"static/fonts/PretendardVariable.woff2", "static/fonts/OFL.txt"}
TREE_SUFFIXES = {
    "hyperpass": {".py"}, "methods": {".md"}, "references": {".md"},
    "static": {".html", ".css", ".js", ".svg"},
    "examples": {".md", ".json"}, "docs": {".md", ".txt"},
    "provenance": {".json", ".txt", ".md"},
    "tests": {".py"}, "tools": {".py"},
    "team": {".md"},
}
DENIED_PARTS = {"__pycache__", ".git", "node_modules", ".venv", "data", "runs", "secrets", "private", "credentials"}


def release_path(name: str) -> bool:
    p = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or p.is_absolute() or str(p) != name:
        return False
    if any(part in {".", ".."} or part.lower() in DENIED_PARTS or part.startswith(".") for part in p.parts):
        return False
    if name in TOP_FILES:
        return True
    if p.parts[0] == "team":
        return name in TEAM_FILES
    if p.parts[:2] == ("static", "fonts"):
        return name in FONT_FILES
    return len(p.parts) > 1 and p.parts[0] in TREE_SUFFIXES and p.suffix.lower() in TREE_SUFFIXES[p.parts[0]]


def files(root: Path) -> list[tuple[str, Path]]:
    root = root.resolve()
    result = []
    candidates = [root / name for name in TOP_FILES]
    for tree in TREE_SUFFIXES:
        parent = root / tree
        if parent.is_symlink():
            raise ValueError(f"Refusing linked directory: {tree}")
        if parent.is_dir():
            candidates.extend(parent.rglob("*"))
    for path in sorted(candidates):
        relative = path.relative_to(root).as_posix()
        if not release_path(relative):
            continue
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
            raise ValueError(f"Refusing symlink: {relative}")
        if path.is_file():
            if not path.resolve().is_relative_to(root):
                raise ValueError(f"Escaped package root: {relative}")
            result.append((relative, path))
    return result


def build(root: Path = ROOT, destination: Path | None = None, windows: bool = False,
          mac: bool = False, architecture: str | None = None) -> Path:
    root = root.resolve()
    if windows and mac:
        raise ValueError("Choose one executable platform per package")
    missing = sorted(name for name in TOP_FILES | TEAM_FILES | FONT_FILES if not (root / name).is_file())
    if missing:
        raise ValueError("Required package files missing: " + ", ".join(missing))
    destination = destination or root / "dist"
    destination.mkdir(parents=True, exist_ok=True)
    if mac:
        architecture = architecture or platform.machine().lower()
        if architecture not in {"arm64", "x86_64"}:
            raise ValueError("macOS architecture must be arm64 or x86_64")
    filename = ("Hyperpass-Research-Web-Windows.zip" if windows else
                f"Hyperpass-Research-Web-macOS-{architecture}.zip" if mac else
                "Hyperpass-Research-Web-source.zip")
    archive = destination / filename
    entries=files(root)
    if windows:
        exe=root/'dist/Hyperpass-Research-Web.exe'
        if not exe.is_file() or exe.is_symlink() or exe.read_bytes()[:2]!=b'MZ':
            raise ValueError('Build and test the Windows executable before packaging')
        entries.append(('Hyperpass-Research-Web.exe',exe))
    if mac:
        binary=root/'dist/Hyperpass-Research-Web'
        magics={b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe',
                b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}
        if not binary.is_file() or binary.is_symlink():
            raise ValueError('Build and test the macOS executable before packaging')
        with binary.open('rb') as stream:
            if stream.read(4) not in magics:
                raise ValueError('The macOS executable must be a Mach-O binary')
        entries.append(('Hyperpass-Research-Web',binary))
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, path in entries:
            info = zipfile.ZipInfo("Hyperpass-Research-Web/" + name, date_time=(2026, 11, 22, 0, 0, 0))
            info.create_system = 3
            executable = name.endswith(".command") or name == "Hyperpass-Research-Web"
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, path.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    return archive


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    platforms=parser.add_mutually_exclusive_group()
    platforms.add_argument('--windows', action='store_true')
    platforms.add_argument('--mac', action='store_true')
    parser.add_argument('--architecture', choices=('arm64','x86_64'))
    args=parser.parse_args()
    print(build(windows=args.windows,mac=args.mac,architecture=args.architecture))
