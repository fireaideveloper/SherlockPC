"""Structured JSON bridge for the SherlockPC desktop sidecar.

The bridge exposes a deliberately small allow-list of application operations.
It can run as a normal Python module during development or as a PyInstaller
sidecar embedded in the Tauri application.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from sherlock import __version__
from sherlock.baseline import _json_default
from sherlock.desktop import DesktopService


def default_database_path() -> Path:
    """Return a writable per-user database path.

    A packaged desktop app may be installed below Program Files, so its data
    must never be stored next to the executable. SHERLOCK_DB_PATH remains an
    explicit escape hatch for tests and advanced users.
    """
    override = os.environ.get("SHERLOCK_DB_PATH")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "SherlockPC" / "data" / "sherlock.db"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home).expanduser() if xdg_data_home else Path.home() / ".local" / "share"
    return base / "sherlockpc" / "sherlock.db"


def handle_request(
    payload: dict[str, Any],
    *,
    service: DesktopService | None = None,
) -> dict[str, Any]:
    action = payload.get("action")
    if not isinstance(action, str):
        raise ValueError("action must be a string")

    service = service or DesktopService(default_database_path())

    if action == "ping":
        return {
            "version": __version__,
            "bridge": "desktop-bridge-v2",
            "database": str(service.database_path),
            "packaged": bool(getattr(sys, "frozen", False)),
        }
    if action == "overview":
        return service.overview()
    if action == "capture_state":
        return service.capture_state()
    if action == "recent_states":
        return service.recent_states(limit=int(payload.get("limit", 6)))
    if action == "investigate":
        return service.investigate_current(
            str(payload.get("question", "")),
            hours=float(payload.get("hours", 24.0)),
            limit=int(payload.get("limit", 200)),
            min_samples=int(payload.get("min_samples", 30)),
            min_span_seconds=float(payload.get("min_span_seconds", 300.0)),
        )

    raise ValueError(f"unsupported desktop action: {action}")


def _request_from_args(argv: Sequence[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--request-json")
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        raise ValueError(f"unsupported arguments: {' '.join(unknown)}")

    raw = args.request_json if args.request_json is not None else sys.stdin.read()
    if not raw.strip():
        raise ValueError("expected a JSON request")

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")
    return payload


def main(argv: Sequence[str] | None = None) -> None:
    try:
        payload = _request_from_args(argv)
        result = handle_request(payload)
        response = {"ok": True, "result": result}
        exit_code = 0
    except (ValueError, TypeError, OSError, json.JSONDecodeError) as error:
        response = {"ok": False, "error": str(error)}
        exit_code = 2
    except Exception as error:  # keep bridge failures structured for the UI
        response = {"ok": False, "error": f"backend failure: {error}"}
        exit_code = 1

    print(json.dumps(response, ensure_ascii=False, allow_nan=False, default=_json_default))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
