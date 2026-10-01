from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Any
from sherlock import __version__
from sherlock.baseline import _json_default
from sherlock.desktop import DesktopService


def default_database_path() -> Path:
    override = os.environ.get("SHERLOCK_DB_PATH")
    if override:
        return Path(override).expanduser()
    return Path.cwd() / "data" / "sherlock.db"


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
            "bridge": "desktop-bridge-v1",
            "database": str(service.database_path),
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


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("expected a JSON request on stdin")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("request must be a JSON object")
        result = handle_request(payload)
        response = {"ok": True, "result": result}
        exit_code = 0
    except (ValueError, TypeError, OSError, json.JSONDecodeError) as error:
        response = {"ok": False, "error": str(error)}
        exit_code = 2
    except Exception as error:
        response = {"ok": False, "error": f"backend failure: {error}"}
        exit_code = 1

    print(json.dumps(response, ensure_ascii=False, allow_nan=False, default=_json_default))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
