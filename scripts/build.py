"""Reproducible Windows bundle, isolated from unrelated DLLs on the shell PATH."""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from panotess import __version__


def make_icon(path):
    from PIL import Image, ImageDraw
    with Image.new("RGBA", (256, 256)) as icon:
        draw = ImageDraw.Draw(icon)
        draw.rounded_rectangle((4, 4, 252, 252), radius=68, fill="#c0afff")
        draw.rounded_rectangle((56, 68, 200, 188), radius=12, outline="#2b2340", width=12)
        for x in (104, 152):
            draw.line((x, 72, x, 184), fill="#2b2340", width=12)
        icon.save(path, format="ICO", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onedir", action="store_true", help="Build a folder package instead of the default single EXE")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise RuntimeError("Build the Windows package on Windows.")
    work = ROOT / "build" / "windows"
    work.mkdir(parents=True, exist_ok=True)
    icon = work / "PanoTess.ico"
    make_icon(icon)
    env = os.environ.copy()
    windows = Path(env.get("WINDIR", "C:/Windows"))
    # Image/PDF/CUDA tools can expose same-name, incompatible ICU/OpenSSL DLLs.
    # Let PyInstaller use Python, the package's own DLLs and the Windows runtime.
    env["PATH"] = os.pathsep.join(map(str, [Path(sys.executable).parent,
        Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs", windows / "System32", windows]))
    env.pop("PYTHONPATH", None)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
        "--windowed", "--onedir" if args.onedir else "--onefile", "--name", "PanoTess",
        "--icon", str(icon), "--collect-data", "PIL",
        "--add-data", f"{ROOT / 'LICENSE'}{os.pathsep}.",
        "--add-data", f"{ROOT / 'README.md'}{os.pathsep}.", "main.py"],
        cwd=ROOT, env=env, check=True)
    bundle = ROOT / "dist" / "PanoTess" if args.onedir else ROOT / "dist"
    executable = bundle / "PanoTess.exe"
    if args.onedir:
        for filename in ("README.md", "LICENSE"):
            shutil.copy2(ROOT / filename, bundle / filename)
    smoke_env = env.copy()
    smoke_env.pop("QT_QPA_PLATFORM", None)
    # Test the native Windows backend from outside the source checkout.
    subprocess.run([str(executable), "--self-test"], cwd=env.get("TEMP", str(bundle)),
                   env=smoke_env, check=True, timeout=90)
    if not args.onedir:
        release = bundle / f"PanoTess-{__version__}-Windows-x64.exe"
        shutil.copy2(executable, release)
        digest = hashlib.sha256(release.read_bytes()).hexdigest()
        (bundle / "SHA256SUMS.txt").write_text(f"{digest}  {release.name}\n", encoding="utf-8")
        print(f"Release EXE: {release}")
        print(f"SHA256: {digest}")
    print(f"Build and packaged-app self-test passed: {executable}")


if __name__ == "__main__":
    main()
