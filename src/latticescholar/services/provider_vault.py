from __future__ import annotations

import base64
import hashlib
import ipaddress
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from ..config import Settings
from ..db import Database
from .providers import PROVIDERS, provider_definition


class ProviderVaultError(ValueError):
    pass


def _derived_fernet_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


class ProviderVault:
    def __init__(self, config: Settings, db: Database):
        self.config = config
        self.db = db
        self.key_source = "environment" if config.credential_encryption_key else "local-file"
        self._cipher = Fernet(self._load_key())

    def _load_key(self) -> bytes:
        if self.config.credential_encryption_key:
            return _derived_fernet_key(self.config.credential_encryption_key)
        key_path = Path(self.config.data_dir) / "credential.key"
        if key_path.exists():
            key = key_path.read_bytes().strip()
            try:
                Fernet(key)
                return key
            except (ValueError, TypeError) as exc:
                raise ProviderVaultError("本地密钥文件无效，无法安全读取模型凭据") from exc
        key = Fernet.generate_key()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(key)
        return key

    def _encrypt(self, value: str) -> str:
        return self._cipher.encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt(self, value: str) -> str:
        try:
            return self._cipher.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise ProviderVaultError("模型密钥无法解密，请删除后重新配置") from exc

    def validate_base_url(self, provider_id: str, value: str) -> str:
        definition = provider_definition(provider_id)
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        host = (parsed.hostname or "").lower()
        local = host in {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
        if not host or parsed.username or parsed.password:
            raise ProviderVaultError("Base URL 格式无效")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
            raise ProviderVaultError("远程模型地址必须使用 HTTPS")
        if provider_id != "custom":
            if not any(host == suffix or host.endswith("." + suffix) for suffix in definition.official_hosts):
                raise ProviderVaultError("该服务商只允许使用已核验的官方 API 域名")
        elif not local and not self.config.allow_custom_model_hosts:
            raise ProviderVaultError(
                "自定义远程模型地址默认关闭；请由管理员设置 LATTICE_ALLOW_CUSTOM_MODEL_HOSTS=true"
            )
        self._reject_private_resolution(host, local)
        return cleaned

    @staticmethod
    def _reject_private_resolution(host: str, local: bool) -> None:
        if local:
            return
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
        except socket.gaierror:
            return
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ProviderVaultError("模型地址解析到私有或保留网络，已拒绝连接")

    def save(
        self,
        owner_id: int,
        provider_id: str,
        *,
        api_key: str,
        base_url: str = "",
        fast_model: str = "",
        quality_model: str = "",
        enabled: bool = True,
        priority: int = 100,
    ) -> dict:
        definition = provider_definition(provider_id)
        existing = self.db.get_provider_credential(owner_id, provider_id)
        raw_key = api_key.strip()
        if not raw_key and not existing:
            raise ProviderVaultError("请输入 API Key")
        if len(raw_key) > 4096:
            raise ProviderVaultError("API Key 长度异常")
        resolved_base = self.validate_base_url(provider_id, base_url or definition.base_url)
        resolved_fast = (fast_model or definition.fast_model).strip()[:160]
        resolved_quality = (quality_model or definition.quality_model).strip()[:160]
        if not resolved_fast or not resolved_quality:
            raise ProviderVaultError("快速模型和深度模型 ID 不能为空")
        encrypted = self._encrypt(raw_key) if raw_key else existing["encrypted_api_key"]
        hint = ("••••" + raw_key[-4:]) if raw_key else existing["key_hint"]
        self.db.upsert_provider_credential(
            owner_id, provider_id, encrypted, hint, resolved_base, resolved_fast,
            resolved_quality, enabled, priority,
        )
        return self.public_provider(owner_id, provider_id)

    def delete(self, owner_id: int, provider_id: str) -> bool:
        provider_definition(provider_id)
        return self.db.delete_provider_credential(owner_id, provider_id)

    def public_provider(self, owner_id: int, provider_id: str) -> dict:
        definition = provider_definition(provider_id)
        row = self.db.get_provider_credential(owner_id, provider_id)
        value = definition.public()
        value.update(
            {
                "configured": bool(row),
                "enabled": bool(row and row["enabled"]),
                "key_hint": row["key_hint"] if row else "",
                "base_url": row["base_url"] if row else definition.base_url,
                "fast_model": row["fast_model"] if row else definition.fast_model,
                "quality_model": row["quality_model"] if row else definition.quality_model,
                "priority": int(row["priority"]) if row else 100,
                "updated_at": row["updated_at"] if row else "",
            }
        )
        return value

    def list_public(self, owner_id: int) -> List[dict]:
        return [self.public_provider(owner_id, key) for key in PROVIDERS]

    def resolved(self, owner_id: int, provider_id: str) -> Dict[str, Any]:
        row = self.db.get_provider_credential(owner_id, provider_id)
        if not row or not row["enabled"]:
            raise ProviderVaultError("该模型服务商尚未启用")
        return {**row, "api_key": self._decrypt(row["encrypted_api_key"])}

    def available(self, owner_id: int) -> bool:
        return bool(self.db.list_provider_credentials(owner_id, enabled_only=True))

    def routing(self, owner_id: int) -> dict:
        value = self.db.get_model_routing(owner_id)
        if value:
            return value
        return {
            "mode": "balanced",
            "primary_provider": "",
            "fallback_enabled": True,
            "updated_at": "",
        }

    def save_routing(
        self, owner_id: int, mode: str, primary_provider: str, fallback_enabled: bool
    ) -> dict:
        if mode not in {"economy", "balanced", "quality"}:
            raise ProviderVaultError("路由模式无效")
        primary = primary_provider.strip()
        if primary:
            provider_definition(primary)
            if not self.db.get_provider_credential(owner_id, primary):
                raise ProviderVaultError("主模型服务尚未配置")
        self.db.upsert_model_routing(owner_id, mode, primary, fallback_enabled)
        return self.routing(owner_id)

    def candidates(self, owner_id: int, task: str, explicit_provider: str = "") -> List[dict]:
        routing = self.routing(owner_id)
        rows = self.db.list_provider_credentials(owner_id, enabled_only=True)
        if explicit_provider:
            rows = [row for row in rows if row["provider_id"] == explicit_provider]
        primary = routing.get("primary_provider") or ""
        rows.sort(key=lambda row: (row["provider_id"] != primary, int(row["priority"])))
        if not routing.get("fallback_enabled", True) and rows:
            rows = rows[:1]
        quality_tasks = {"paper_analysis", "idea", "research_discussion"}
        mode = routing.get("mode", "balanced")
        model_type = "quality_model" if mode == "quality" or (
            mode == "balanced" and task in quality_tasks
        ) else "fast_model"
        result = []
        for row in rows:
            result.append(
                {
                    **row,
                    "api_key": self._decrypt(row["encrypted_api_key"]),
                    "model": row[model_type],
                    "protocol": provider_definition(row["provider_id"]).protocol,
                    "routing_mode": mode,
                }
            )
        return result

    def security_status(self) -> dict:
        return {
            "encrypted_at_rest": True,
            "key_source": self.key_source,
            "plaintext_returned": False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
