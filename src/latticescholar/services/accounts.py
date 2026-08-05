from __future__ import annotations

import hashlib
import hmac
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


class AuthenticationError(RuntimeError):
    pass


class UpgradeRequired(RuntimeError):
    pass


class QuotaExceeded(RuntimeError):
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
        return self.db.get_or_create_user(email, self.config.trial_days, email in self.admins)

    def issue_session(self, user_id: int) -> str:
        return self.sessions.issue(30 * 24 * 60 * 60, subject=str(user_id))

    def user_from_token(self, token: str) -> Optional[dict]:
        subject = self.sessions.subject(token)
        if not subject or not subject.isdigit():
            return None
        return self.db.get_user_by_id(int(subject))

    def entitlement(self, user: Optional[dict]) -> Dict[str, Any]:
        if not self.enabled:
            return self._entitlement("community", "开源社区版：自行部署时全部本地能力可用", True)
        if not user:
            return self._entitlement("anonymous", "请登录", False)
        now = datetime.now(timezone.utc)
        if user.get("role") == "admin":
            return self._entitlement("admin", "管理员全功能", True)
        grant = self.db.get_grant(user["email"])
        grant_expiry = _parse_time(grant.get("expires_at")) if grant else None
        if grant and (grant_expiry is None or grant_expiry > now):
            return self._entitlement("complimentary", "管理员赠送全功能", True, grant_expiry)
        if user.get("subscription_status") in {"active", "trialing"}:
            return self._entitlement(
                "pro", "LatticeScholar Pro 订阅", True, _parse_time(user.get("subscription_expires_at"))
            )
        early = _parse_time(self.config.early_access_until)
        if early and early > now:
            return self._entitlement("early_access", "早期用户全功能期", True, early)
        trial = _parse_time(user.get("trial_ends_at"))
        if trial and trial > now:
            return self._entitlement("trial", "Pro 免费试用", True, trial)
        return self._entitlement("free", "免费版", False)

    def _entitlement(
        self, plan: str, label: str, pro: bool, expires_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        return {
            "plan": plan,
            "label": label,
            "is_pro": pro,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "features": {
                "premium_sources": pro,
                "bibliography_import": pro,
                "deep_analysis": pro,
                "advanced_ideas": pro,
                "billing": self.config.billing_enabled,
            },
        }

    def public_user(self, user: dict) -> Dict[str, Any]:
        return {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "entitlement": self.entitlement(user),
            "usage": self.usage_snapshot(user),
            "billing_customer": bool(user.get("stripe_customer_id")),
        }

    def usage_snapshot(self, user: dict) -> Dict[str, Any]:
        entitlement = self.entitlement(user)
        limits = {
            "search": self.config.free_searches_per_day,
            "analysis": self.config.free_analyses_per_day,
            "journal_match": self.config.free_journal_matches_per_day,
            "idea": self.config.free_ideas_per_day,
            "library": self.config.free_library_items,
        }
        return {
            feature: {
                "used": self.db.count_library_items(user["id"])
                if feature == "library"
                else self.db.usage(user["id"], feature),
                "limit": None if entitlement["is_pro"] else limit,
            }
            for feature, limit in limits.items()
        }

    def check_daily(self, user: Optional[dict], feature: str) -> None:
        if not self.enabled or not user or self.entitlement(user)["is_pro"]:
            return
        limits = {
            "search": self.config.free_searches_per_day,
            "analysis": self.config.free_analyses_per_day,
            "journal_match": self.config.free_journal_matches_per_day,
            "idea": self.config.free_ideas_per_day,
        }
        limit = limits[feature]
        if self.db.usage(user["id"], feature) >= limit:
            raise QuotaExceeded(f"今日免费额度已用完（{limit} 次），升级 Pro 后可继续使用")

    def record(self, user: Optional[dict], feature: str) -> None:
        if self.enabled and user:
            self.db.add_usage(user["id"], feature)

    def require_pro(self, user: Optional[dict], feature_label: str) -> None:
        if self.enabled and not self.entitlement(user)["is_pro"]:
            raise UpgradeRequired(f"{feature_label}属于 Pro 功能；可升级、等待试用期或联系管理员赠送权限")

    def validate_sources(self, user: Optional[dict], sources: list) -> None:
        if not self.enabled or self.entitlement(user)["is_pro"]:
            return
        premium = set(sources) - {"crossref", "arxiv", "pubmed"}
        if premium:
            raise UpgradeRequired("Semantic Scholar、OpenAlex 与 Web of Science 托管接入属于 Pro 功能")

    def check_library(self, user: Optional[dict]) -> None:
        if not self.enabled or not user or self.entitlement(user)["is_pro"]:
            return
        if self.db.count_library_items(user["id"]) >= self.config.free_library_items:
            raise QuotaExceeded(
                f"免费版最多保存 {self.config.free_library_items} 条证据，升级 Pro 后可继续保存"
            )
