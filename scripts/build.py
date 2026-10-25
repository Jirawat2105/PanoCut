"""Reproducible Windows bundle, isolated from unrelated DLLs on the shell PATH."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "win32":
        raise RuntimeError("Build the Windows package on Windows.")
    env = os.environ.copy()
    windows = Path(env.get("WINDIR", "C:/Windows"))
    # Image/PDF/CUDA tools can expose same-name, incompatible ICU/OpenSSL DLLs.
    # Let PyInstaller use Python, the package's own DLLs and the Windows runtime.
    env["PATH"] = os.pathsep.join(map(str, [Path(sys.executable).parent,
        Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs", windows / "System32", windows]))
    env.pop("PYTHONPATH", None)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
        "--windowed", "--onedir", "--name", "PanoTess", "--collect-data", "PIL", "main.py"],
        cwd=ROOT, env=env, check=True)
    bundle = ROOT / "dist" / "PanoTess"
    shutil.copy2(ROOT / "README.md", bundle / "README.md")
    subprocess.run([str(bundle / "PanoTess.exe"), "--self-test"], cwd=bundle,
                   env=env, check=True, timeout=45)
    print(f"Build and packaged-app self-test passed: {bundle / 'PanoTess.exe'}")


if __name__ == "__main__":
    main()
