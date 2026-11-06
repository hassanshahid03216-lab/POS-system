"""HTTP transport used by desktop installations connected to a cloud API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from app_settings import load_settings

_token = None


def api_url() -> str:
    return str(os.environ.get("SHOPFLOW_API_URL") or load_settings().get("cloud_api_url", "")).strip().rstrip("/")


def set_token(token):
    global _token
    _token = token


def clear_token():
    global _token
    _token = None


def request(path: str, payload=None, *, auth=True, timeout=30):
    base = api_url()
    if not base:
        raise RuntimeError("Cloud API URL is not configured on this computer.")
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if auth and _token:
        headers["Authorization"] = f"Bearer {_token}"
    req = urllib.request.Request(base + path, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read().decode("utf-8")).get("detail", str(exc))
        except (ValueError, UnicodeDecodeError):
            message = str(exc)
        if exc.code == 401:
            clear_token()
        raise RuntimeError(str(message)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Could not reach the cloud POS service: {exc}") from exc
    try:
        return json.loads(body.decode("utf-8")) if body else None
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("The cloud POS service returned an invalid response.") from exc


def login(pin: str):
    result = request("/api/auth/login", {"pin": pin}, auth=False)
    set_token(result["token"])
    return result["user"]


def setup_admin(name: str, pin: str):
    result = request("/api/auth/setup", {"name": name, "pin": pin}, auth=False)
    set_token(result["token"])
    return result["user"]["id"]


def rpc(name: str, args, kwargs):
    return request(f"/api/rpc/{name}", {"args": args, "kwargs": kwargs})["result"]

