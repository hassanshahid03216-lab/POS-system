"""Authenticated API for remote desktop POS clients.

Run locally with ``uvicorn api.main:app --host 0.0.0.0 --port 8000``.
The service talks to PostgreSQL through DATABASE_URL; clients never receive
that credential.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

os.environ["SHOPFLOW_API_SERVER"] = "1"

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db import db


app = FastAPI(title="ShopFlow POS API", version="1.0.0")
_signing_secret = os.environ.get("API_SIGNING_SECRET", "")
if not _signing_secret:
    if os.environ.get("RENDER"):
        raise RuntimeError("Set API_SIGNING_SECRET in the Render service environment.")
    _signing_secret = secrets.token_urlsafe(48)
_signing_key = _signing_secret.encode("utf-8")
_login_attempts = defaultdict(deque)


class LoginPayload(BaseModel):
    pin: str = Field(min_length=4, max_length=8)


class SetupPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    pin: str = Field(min_length=4, max_length=8)


class RpcPayload(BaseModel):
    args: list = Field(default_factory=list)
    kwargs: dict = Field(default_factory=dict)


class ImportPayload(BaseModel):
    filename: str = Field(max_length=255)
    content: str


class SalesExportPayload(BaseModel):
    start_date: str
    end_date: str


RPC_METHODS = {
    "assign_barcode_to_product", "checkout_sale", "save_held_bill", "list_held_bills",
    "get_held_bill", "list_recent_sales", "get_sale_for_return", "process_sale_return",
    "return_voucher_balance", "list_customers", "get_customer", "create_customer",
    "update_customer", "delete_customer", "get_customer_ledger", "record_customer_payment",
    "get_dashboard_insights", "list_categories", "list_products", "get_product",
    "create_product", "update_product", "delete_product", "create_user_with_pin",
    "list_users", "delete_user", "update_user_pin", "active_cash_shift", "start_cash_shift",
    "record_cash_expense", "cash_shift_summary", "close_cash_shift", "list_today_cash_closings",
    "get_day_end_summary", "list_suppliers", "save_supplier", "record_purchase",
    "record_supplier_payment", "supplier_ledger",
}
ADMIN_METHODS = {
    "get_dashboard_insights", "update_product", "delete_product",
    "create_user_with_pin", "list_users", "delete_user", "update_user_pin",
    "list_suppliers", "save_supplier", "record_purchase", "record_supplier_payment",
    "supplier_ledger",
}


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _issue_token(user: dict) -> str:
    payload = {"uid": int(user["id"]), "name": user["name"], "role": user["role"], "exp": int(time.time()) + 12 * 60 * 60}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(_signing_key, body.encode("ascii"), hashlib.sha256).digest())
    return body + "." + signature


def _decode_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(_signing_key, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid token signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("Token expired")
        if payload.get("role") not in {"admin", "cashier"}:
            raise ValueError("Invalid role")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Your sign-in expired. Sign in again.") from exc


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    claims = _decode_token(authorization[7:].strip())
    try:
        active = next((user for user in db.list_users() if int(user["id"]) == int(claims["uid"])), None)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Sign-in service is temporarily unavailable.") from exc
    if not active:
        raise HTTPException(status_code=401, detail="This account is no longer active. Sign in again.")
    claims["name"] = active["name"]
    claims["role"] = active["role"]
    return claims


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access is required.")
    return user


def _login_throttled(request: Request):
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = _login_attempts[key]
    while attempts and now - attempts[0] > 30:
        attempts.popleft()
    if len(attempts) >= 5:
        raise HTTPException(status_code=429, detail="Too many failed sign-in attempts. Wait 30 seconds and try again.")
    return key, attempts


@app.on_event("startup")
def initialize_database():
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL must point to the Neon PostgreSQL database.")
    db.init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/auth/status")
def auth_status():
    return {"users": db.user_count()}


@app.post("/api/auth/setup")
def setup_owner(payload: SetupPayload):
    if db.user_count() != 0:
        raise HTTPException(status_code=409, detail="Owner setup has already been completed.")
    try:
        db.create_user_with_pin(payload.name, "admin", payload.pin)
        user = db.authenticate_pin(payload.pin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not user:
        raise HTTPException(status_code=500, detail="Owner account was created but sign-in failed.")
    return {"user": user, "token": _issue_token(user)}


@app.post("/api/auth/login")
def login(payload: LoginPayload, request: Request):
    key, attempts = _login_throttled(request)
    try:
        user = db.authenticate_pin(payload.pin)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Sign-in service is temporarily unavailable.") from exc
    if not user:
        attempts.append(time.monotonic())
        raise HTTPException(status_code=401, detail="PIN not recognized.")
    _login_attempts.pop(key, None)
    return {"user": user, "token": _issue_token(user)}


@app.post("/api/rpc/{method_name}")
def call_method(method_name: str, payload: RpcPayload, user=Depends(current_user)):
    if method_name not in RPC_METHODS:
        raise HTTPException(status_code=404, detail="Operation is not available through the API.")
    if method_name in ADMIN_METHODS and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access is required.")
    if method_name == "delete_user" and db.user_count() <= 1:
        raise HTTPException(status_code=400, detail="At least one user account must remain.")
    try:
        kwargs = dict(payload.kwargs)
        if method_name == "checkout_sale":
            kwargs["cashier_id"] = user["uid"]
        result = getattr(db, method_name)(*payload.args, **kwargs)
        return {"result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (TypeError, KeyError, IndexError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid request: {exc}") from exc
    except Exception as exc:
        # Keep SQL, credentials, and internal paths out of client error details.
        raise HTTPException(status_code=500, detail="The operation failed on the server.") from exc


@app.post("/api/products/import")
def import_products(payload: ImportPayload, user=Depends(admin_user)):
    try:
        if len(payload.content) > 14 * 1024 * 1024:
            raise ValueError("CSV file is larger than the 10 MB limit.")
        content = base64.b64decode(payload.content, validate=True)
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("CSV file is larger than the 10 MB limit.")
        with tempfile.NamedTemporaryFile(prefix="shopflow-import-", suffix=".csv", delete=False) as source:
            source.write(content)
            path = source.name
        try:
            return db.import_products_csv(path)
        finally:
            Path(path).unlink(missing_ok=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/reports/sales.csv")
def export_sales(payload: SalesExportPayload, user=Depends(admin_user)):
    try:
        start = date.fromisoformat(payload.start_date)
        end = date.fromisoformat(payload.end_date)
        if end < start:
            raise ValueError("End date must be on or after start date.")
        with tempfile.NamedTemporaryFile(prefix="shopflow-sales-", suffix=".csv", delete=False) as output:
            path = output.name
        try:
            count = db.export_sales_csv(path, start.isoformat(), end.isoformat())
            content = Path(path).read_bytes()
            return {"count": count, "content": base64.b64encode(content).decode("ascii")}
        finally:
            Path(path).unlink(missing_ok=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

