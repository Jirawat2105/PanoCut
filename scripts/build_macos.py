"""Build a native macOS app and DMG/PKG; optionally sign and notarize it."""

import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from panotess import __version__


def run(*args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def make_icon(path):
    # Match the existing in-app panorama icon; ICNS includes all required sizes.
    from PIL import Image, ImageDraw
    image = Image.new("RGBA", (1024, 1024))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((16, 16, 1008, 1008), radius=272, fill="#c0afff")
    draw.rounded_rectangle((224, 272, 800, 752), radius=48, outline="#2b2340", width=48)
    for x in (416, 608):
        draw.line((x, 288, x, 736), fill="#2b2340", width=48)
    image.save(path, format="ICNS")


def notarize(path, profile):
    run("xcrun", "notarytool", "submit", path, "--keychain-profile", profile, "--wait")
    run("xcrun", "stapler", "staple", path)
    run("xcrun", "stapler", "validate", path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("dmg", "pkg", "both"), default="dmg")
    parser.add_argument("--codesign-identity", help="Developer ID Application identity")
    parser.add_argument("--installer-identity", help="Developer ID Installer identity (PKG only)")
    parser.add_argument("--notary-profile", help="Existing notarytool keychain profile")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Build macOS packages on a Mac.")
    arch = platform.machine()
    if arch not in ("arm64", "x86_64"):
        parser.error(f"Unsupported Python architecture: {arch}")
    if args.notary_profile and not args.codesign_identity:
        parser.error("Notarization requires --codesign-identity.")
    if args.notary_profile and args.format in ("pkg", "both") and not args.installer_identity:
        parser.error("Notarizing a PKG also requires --installer-identity.")
    for tool in ("codesign", "hdiutil", "pkgbuild", "ditto"):
        if not shutil.which(tool):
            parser.error(f"Required macOS tool not found: {tool}")

    work = ROOT / "build" / "macos"
    work.mkdir(parents=True, exist_ok=True)
    icon = work / "PanoTess.icns"
    make_icon(icon)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(PANOTESS_TARGET_ARCH=arch, PANOTESS_VERSION=__version__, PANOTESS_ICON=str(icon))
    env["PYINSTALLER_CONFIG_DIR"] = str(work / "cache")
    env.pop("PANOTESS_CODESIGN_IDENTITY", None)
    if args.codesign_identity:
        env["PANOTESS_CODESIGN_IDENTITY"] = args.codesign_identity
    run(sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
        "--workpath", work / "pyinstaller", ROOT / "packaging" / "macos.spec", cwd=ROOT, env=env)
    app = ROOT / "dist" / "PanoTess.app"
    run("codesign", "--verify", "--deep", "--strict", "--verbose=2", app)
    smoke_env = env.copy()
    # Exercise Cocoa, even if the caller ran the offscreen test suite first.
    smoke_env.pop("QT_QPA_PLATFORM", None)
    run(app / "Contents" / "MacOS" / "PanoTess", "--self-test", cwd="/private/tmp",
        env=smoke_env, timeout=60)
    if args.notary_profile:
        archive = work / "PanoTess-notarization.zip"
        archive.unlink(missing_ok=True)
        run("ditto", "-c", "-k", "--keepParent", app, archive)
        run("xcrun", "notarytool", "submit", archive, "--keychain-profile", args.notary_profile, "--wait")
        run("xcrun", "stapler", "staple", app)
        run("xcrun", "stapler", "validate", app)
        run("spctl", "--assess", "--type", "execute", "--verbose=2", app)

    outputs = []
    stem = f"PanoTess-{__version__}-macOS-{arch}"
    if args.format in ("dmg", "both"):
        dmg = ROOT / "dist" / f"{stem}.dmg"
        with TemporaryDirectory(prefix="panotess-dmg-", dir=work) as temporary:
            stage = Path(temporary)
            run("ditto", app, stage / app.name)
            (stage / "Applications").symlink_to("/Applications")
            (stage / "Install.txt").write_text(
                "Drag PanoTess.app to Applications, then launch it from Applications.\n"
                "Requires macOS 14.4 or newer. No Python installation is needed.\n", encoding="utf-8")
            run("hdiutil", "create", "-volname", "PanoTess", "-srcfolder", stage,
                "-ov", "-format", "UDZO", dmg)
        if args.codesign_identity:
            run("codesign", "--sign", args.codesign_identity, "--timestamp", dmg)
        if args.notary_profile:
            notarize(dmg, args.notary_profile)
        run("hdiutil", "verify", dmg)
        outputs.append(dmg)
    if args.format in ("pkg", "both"):
        pkg = ROOT / "dist" / f"{stem}.pkg"
        command = ["pkgbuild", "--component", app, "--install-location", "/Applications",
                   "--identifier", "com.jirawat2105.panotess", "--version", __version__]
        if args.installer_identity:
            command += ["--sign", args.installer_identity, "--timestamp"]
        run(*command, pkg)
        if args.notary_profile:
            notarize(pkg, args.notary_profile)
        outputs.append(pkg)
    for path in outputs:
        print(f"Ready: {path}")
    if not args.notary_profile:
        print("Local test build: not notarized. Use Developer ID signing and --notary-profile before public distribution.")


if __name__ == "__main__":
    main()
