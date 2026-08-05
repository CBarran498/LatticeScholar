from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import smtplib
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import Settings
from ..db import Database
from .auth import AccessManager

logger = logging.getLogger(__name__)


class AuthenticationError(RuntimeError):
    pass


def load_or_create_session_secret(config: Settings) -> str:
    if config.session_secret:
        return config.session_secret
    path = Path(config.data_dir) / "session-secret"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    secret = secrets.token_urlsafe(48)
    path.write_text(secret, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class AccountService:
    cookie_name = "lattice_account"

    def __init__(self, config: Settings, db: Database):
        self.config = config
        self.db = db
        self.sessions = AccessManager("", load_or_create_session_secret(config))
        self.admins = {
            email.strip().casefold() for email in config.admin_emails.split(",") if email.strip()
        }
        if self.enabled:
            if not self.admins:
                logger.warning(
                    "当前为 accounts 模式但未设置 LATTICE_ADMIN_EMAILS。"
                    "第一个登录的用户不会自动获得管理员权限。"
                    "建议在 .env 或环境变量中设置 LATTICE_ADMIN_EMAILS=your@email.com"
                )
            if config.dev_auth:
                logger.info(
                    "SMTP 未配置，已自动启用开发模式：验证码将直接显示在登录页面上"
                )

    @property
    def enabled(self) -> bool:
        return self.config.auth_mode == "accounts"

    def _code_hash(self, email: str, code: str) -> str:
        return hmac.new(
            self.sessions.secret, f"{email}:{code}".encode(), hashlib.sha256
        ).hexdigest()

    def request_code(self, email: str) -> Optional[str]:
        previous = self.db.get_auth_code(email)
        if previous:
            created = _parse_time(previous.get("created_at"))
            if created and (datetime.now(timezone.utc) - created).total_seconds() < 60:
                raise AuthenticationError("验证码发送过于频繁，请一分钟后再试")
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.db.save_auth_code(email, self._code_hash(email, code), int(time.time()) + 600)
        if self.config.dev_auth:
            preview = Path(self.config.data_dir) / "auth-preview.log"
            with preview.open("a", encoding="utf-8") as handle:
                handle.write(f"{datetime.now(timezone.utc).isoformat()} {email} {code}\n")
            return code
        self._send_code(email, code)
        return None

    def _send_code(self, email: str, code: str) -> None:
        if not self.config.smtp_host or not self.config.smtp_from_email:
            raise AuthenticationError("邮件服务尚未配置，请联系管理员")
        message = EmailMessage()
        message["Subject"] = f"{code} 是你的 LatticeScholar 登录验证码"
        message["From"] = self.config.smtp_from_email
        message["To"] = email
        message.set_content(
            f"你的 LatticeScholar 验证码是：{code}\n\n10 分钟内有效，请勿转发。"
        )
        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=12) as server:
            if self.config.smtp_use_tls:
                server.starttls()
            if self.config.smtp_username:
                server.login(self.config.smtp_username, self.config.smtp_password)
            server.send_message(message)

    def verify_code(self, email: str, code: str) -> Dict[str, Any]:
        record = self.db.get_auth_code(email)
        if not record or record["expires_at"] < int(time.time()):
            raise AuthenticationError("验证码已过期，请重新获取")
        if int(record["attempts"]) >= 5:
            raise AuthenticationError("验证码尝试次数过多，请重新获取")
        if not hmac.compare_digest(record["code_hash"], self._code_hash(email, code)):
            self.db.fail_auth_code(email)
            raise AuthenticationError("验证码不正确")
        self.db.consume_auth_code(email)
        return self.db.get_or_create_user(email, 0, email in self.admins)

    def issue_session(self, user_id: int) -> str:
        return self.sessions.issue(30 * 24 * 60 * 60, subject=str(user_id))

    def user_from_token(self, token: str) -> Optional[dict]:
        subject = self.sessions.subject(token)
        if not subject or not subject.isdigit():
            return None
        return self.db.get_user_by_id(int(subject))

    def entitlement(self, user: Optional[dict]) -> Dict[str, Any]:
        if not self.enabled:
            return self._entitlement("community", "开源社区版：全部功能可用")
        if not user:
            return self._entitlement("anonymous", "请登录")
        if user.get("role") == "admin":
            return self._entitlement("admin", "管理员")
        return self._entitlement("user", "注册用户")

    def _entitlement(self, plan: str, label: str) -> Dict[str, Any]:
        return {
            "plan": plan,
            "label": label,
            "is_pro": plan not in ("anonymous",),
            "features": {
                "premium_sources": True,
                "bibliography_import": True,
                "deep_analysis": True,
                "advanced_ideas": True,
            },
        }

    def public_user(self, user: dict) -> Dict[str, Any]:
        return {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "entitlement": self.entitlement(user),
        }
