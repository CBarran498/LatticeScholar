from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


class AccessManager:
    cookie_name = "lattice_session"

    def __init__(self, password: str, secret: str):
        self.password = password
        self.secret = (secret or hashlib.sha256((password + ":lattice").encode()).hexdigest()).encode()

    @property
    def required(self) -> bool:
        return bool(self.password)

    def check_password(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate.encode(), self.password.encode())

    def issue(self, lifetime_seconds: int = 12 * 60 * 60, subject: str = "shared") -> str:
        payload = json.dumps(
            {"exp": int(time.time()) + lifetime_seconds, "sub": subject},
            separators=(",", ":"),
        )
        encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        signature = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
        return encoded + "." + signature

    def subject(self, token: str):
        try:
            encoded, signature = token.split(".", 1)
            expected = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return None
            padded = encoded + "=" * (-len(encoded) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode())
            if int(payload.get("exp", 0)) <= int(time.time()):
                return None
            return str(payload.get("sub") or "") or None
        except (ValueError, TypeError, json.JSONDecodeError):
            return None

    def valid(self, token: str) -> bool:
        return self.subject(token) is not None
