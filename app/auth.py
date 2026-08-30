"""
auth.py — a deliberately simple auth check for the mock.

One static token, read from an env var (or a default if you haven't set one).
Real DFSPs will do something fancier (OAuth client_credentials, API keys issued
per-partner, etc.) — this exists purely so the Core Connector's auth-handling
code has something real to fail against if the token is missing or wrong,
rather than every call just silently succeeding.
"""
import os

from fastapi import Header, HTTPException

# Change this via an actual env var when running for real —
# this default is only here so the mock works out of the box.
EXPECTED_TOKEN = os.environ.get("AUTH_TOKEN", "1000000000")


def verify_token(authorization: str | None = Header(default=None)) -> None:
    if authorization is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header. Expected: Bearer <token>",
        )

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(
            status_code=401,
            detail="Malformed Authorization header. Expected: Bearer <token>",
        )

    token = parts[1]
    if token != EXPECTED_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")