# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

project_root = Path(SPECPATH)
sys.path.insert(0, str(project_root))
from tools.build_release import files

# Use the same allowlist as the ZIP builder, including only the 33 fixed team
# documents. Runtime edit history and lock files must never enter the binary.
resource_trees = {'static', 'methods', 'references', 'examples', 'docs', 'provenance', 'team'}
resource_files = [
    (str(path), str(Path(name).parent))
    for name, path in files(project_root)
    if Path(name).parts[0] in resource_trees or name in {'LICENSE', 'NOTICE', '수강생-시작가이드.html'}
]


a = Analysis(
    [str(project_root / 'app.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=resource_files,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Hyperpass-Research-Web',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
