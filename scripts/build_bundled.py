"""Build the personal ZenCloak installer with the CloakBrowser kernel bundled.

Internal-use build only: the CloakBrowser Binary License forbids
redistributing or packaging the binary into products distributed to third
parties (see CloakBrowser-ref/BINARY-LICENSE.md). Never upload the output
of this script to a public repository.

Steps:
  1. PyInstaller onedir build (dist/ZenCloak/)
  2. Copy the locally cached CloakBrowser kernel into dist/ZenCloak/engine/
  3. Compile installer/zencloak-bundled.iss with Inno Setup

Usage:
  python scripts/build_bundled.py [--skip-pyinstaller] [--skip-inno]
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=str(ROOT))


def cloakbrowser_kernel() -> Path:
    from cloakbrowser.config import CHROMIUM_VERSION, get_binary_path

    version_dir = get_binary_path(CHROMIUM_VERSION).parent
    if not version_dir.is_dir():
        raise SystemExit(
            f"未找到本机内核 {version_dir}；先运行 python -m cloakbrowser install 下载"
        )
    return version_dir


def iscc_executable() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"
    if local.exists():
        return local
    raise SystemExit("未找到 Inno Setup 6（winget install --id JRSoftware.InnoSetup -e）")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-pyinstaller", action="store_true")
    parser.add_argument("--skip-inno", action="store_true")
    args = parser.parse_args()

    if not args.skip_pyinstaller:
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "zencloak-dir.spec"])

    kernel = cloakbrowser_kernel()
    engine_target = ROOT / "dist" / "ZenCloak" / "engine" / kernel.name
    print(f"内置内核: {kernel} -> {engine_target}")
    if engine_target.exists():
        shutil.rmtree(engine_target)
    engine_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(kernel, engine_target)

    if not args.skip_inno:
        run([iscc_executable(), "installer/zencloak-bundled.iss"])
        print("完成: installer/ZenCloak-Setup-0.3.0-bundled.exe（仅自用，勿公开分发）")


if __name__ == "__main__":
    main()
