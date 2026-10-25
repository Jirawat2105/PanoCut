"""Build on macOS using scripts/build_macos.py."""
import os
from pathlib import Path

root = Path(SPECPATH).parent
identity = os.environ.get("PANOTESS_CODESIGN_IDENTITY")
a = Analysis([str(root / "main.py")], pathex=[str(root)],
             binaries=[], datas=[(str(root / "LICENSE"), "."), (str(root / "README.md"), ".")],
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PanoTess",
          console=False, target_arch=os.environ["PANOTESS_TARGET_ARCH"],
          codesign_identity=identity)
coll = COLLECT(exe, a.binaries, a.datas, name="PanoTess")
app = BUNDLE(coll, name="PanoTess.app", icon=os.environ["PANOTESS_ICON"],
             bundle_identifier="com.jirawat2105.panotess",
             version=os.environ["PANOTESS_VERSION"],
             info_plist={
                 "CFBundleDisplayName": "PanoTess",
                 "NSHighResolutionCapable": True,
                 "LSMinimumSystemVersion": "14.4",
                 "LSApplicationCategoryType": "public.app-category.photography",
                 "NSHumanReadableCopyright": "Copyright © 2026 Jirawat Pratuangtip",
             })
