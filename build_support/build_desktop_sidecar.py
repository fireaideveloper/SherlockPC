"""Build the Python desktop bridge as a Tauri externalBin sidecar."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "sherlock" / "desktop_bridge.py"
BINARY_NAME = "sherlock-backend"
BUILD_ROOT = ROOT / "build" / "desktop-sidecar"
DIST_DIR = BUILD_ROOT / "dist"
WORK_DIR = BUILD_ROOT / "work"
SPEC_DIR = BUILD_ROOT / "spec"
TAURI_BIN_DIR = ROOT / "desktop" / "src-tauri" / "binaries"


def target_triple() -> str:
    try:
        result = subprocess.run(
            ["rustc", "--print", "host-tuple"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Rust/rustc is required to resolve the Tauri target triple: {error}")

    value = result.stdout.strip()
    if not value:
        raise SystemExit("rustc returned an empty host target triple")
    return value


def destination_for(triple: str) -> Path:
    extension = ".exe" if os.name == "nt" else ""
    return TAURI_BIN_DIR / f"{BINARY_NAME}-{triple}{extension}"


def newest_source_mtime() -> float:
    candidates = [ROOT / "pyproject.toml", ENTRYPOINT]
    candidates.extend((ROOT / "sherlock").rglob("*.py"))
    return max(path.stat().st_mtime for path in candidates if path.exists())


def build(*, if_needed: bool = False) -> Path:
    triple = target_triple()
    destination = destination_for(triple)

    if if_needed and destination.exists() and destination.stat().st_mtime >= newest_source_mtime():
        smoke_test(destination)
        print(f"Sidecar is up to date: {destination}")
        return destination

    TAURI_BIN_DIR.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    SPEC_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        BINARY_NAME,
        "--paths",
        str(ROOT),
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(WORK_DIR),
        "--specpath",
        str(SPEC_DIR),
        str(ENTRYPOINT),
    ]

    print("Building SherlockPC Python sidecar...")
    subprocess.run(command, cwd=ROOT, check=True)

    extension = ".exe" if os.name == "nt" else ""
    built = DIST_DIR / f"{BINARY_NAME}{extension}"
    if not built.exists():
        raise SystemExit(f"PyInstaller finished but sidecar was not found: {built}")

    shutil.copy2(built, destination)
    smoke_test(destination)
    print(f"Sidecar ready: {destination}")
    return destination


def smoke_test(binary: Path) -> None:
    request = json.dumps({"action": "ping"}, separators=(",", ":"))
    result = subprocess.run(
        [str(binary), "--request-json", request],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"Sidecar smoke test returned invalid JSON: {error}; stderr={result.stderr.strip()}"
        ) from error

    if result.returncode != 0 or payload.get("ok") is not True:
        raise SystemExit(
            f"Sidecar smoke test failed (exit={result.returncode}): "
            f"{payload}; stderr={result.stderr.strip()}"
        )
    print("Sidecar smoke test: OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--if-needed",
        action="store_true",
        help="skip PyInstaller when the current target sidecar is newer than Python sources",
    )
    args = parser.parse_args()
    build(if_needed=args.if_needed)


if __name__ == "__main__":
    main()
