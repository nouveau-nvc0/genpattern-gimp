#!/usr/bin/env python3
import subprocess, sys, tempfile, shutil, pathlib

PACKAGE   = "genpattern"
PY_TAG    = f"{sys.version_info.major}{sys.version_info.minor}"
ABI_TAG   = f"cp{PY_TAG}"

PLATFORMS = {
    "linux_x86_64":   "manylinux_2_17_x86_64",
    "linux_arm64":    "manylinux_2_17_aarch64",
    "windows_x86_64": "win_amd64",
}

cwd_pkg   = pathlib.Path.cwd() / PACKAGE
if not cwd_pkg.is_dir():
    sys.exit(f"no '{PACKAGE}' directory in the current working directory")

dist_root = pathlib.Path("dist")
dist_root.mkdir(exist_ok=True)

with tempfile.TemporaryDirectory() as tmp_dir:
    tmp_path = pathlib.Path(tmp_dir)

    for label, plat_tag in PLATFORMS.items():
        # copy local sources ─ dist/<label>/genpattern
        dest_base = dist_root / label / PACKAGE
        if dest_base.exists():
            shutil.rmtree(dest_base)
        shutil.copytree(cwd_pkg, dest_base)

        # download a wheel for the target platform
        subprocess.run(
            [
                sys.executable, "-m", "pip", "download",
                "--no-deps", "--only-binary=:all:",
                f"--platform={plat_tag}",
                f"--python-version={PY_TAG}",
                f"--abi={ABI_TAG}",
                "-q", "-d", str(tmp_path),
                PACKAGE,
            ],
            check=True,
        )

        wheel_file   = next(tmp_path.glob(f"{PACKAGE}-*.whl"))
        extract_here = tmp_path / "extract"
        shutil.unpack_archive(wheel_file, extract_here, format="zip")

        # copy wheel contents ─ dist/<label>/genpattern/genpattern
        shutil.copytree(
            extract_here / PACKAGE,
            dest_base / "genpattern_lib",
            dirs_exist_ok=True,
        )

        # clean temp for next round
        shutil.rmtree(extract_here, ignore_errors=True)
        wheel_file.unlink()
