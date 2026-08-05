from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from ..config import Settings
from ..db import Database


class BillingError(RuntimeError):
    pass


class BillingService:
    def __init__(self, config: Settings, db: Database):
        self.config = config
        self.db = db

    @property
    def ready(self) -> bool:
        return bool(
            self.config.billing_enabled
            and self.config.billing_provider == "stripe"
            and self.config.stripe_secret_key
            and self.config.stripe_pro_price_id
        )

    def plans(self) -> Dict[str, Any]:
        return {
            "currency": "CNY",
            "recommended_price": 15,
            "billing_ready": self.ready,
            "provider": self.config.billing_provider if self.config.billing_enabled else "disabled",
            "plans": [
                {
                    "id": "free",
                    "name": "Free",
                    "price": 0,
                    "description": "长期免费，满足个人基础科研工作流",
                    "features": [
                        "Crossref、arXiv、PubMed 检索",
                        "零 Token 规则分析",
                        "每日基础额度",
                        "本地开源社区版不受托管额度限制",
                    ],
                },
                {
                    "id": "pro",
                    "name": "Pro",
                    "price": 15,
                    "description": "建议早鸟价 ¥15/月；实际金额由支付后台价格决定",
                    "features": [
                        "全部托管数据源与更高检索额度",
                        "深度模型分析与高级 Idea Lab",
                        "知网/Scholar 批量题录导入",
                        "更大证据库和优先支持",
                    ],
                },
            ],
        }

    async def create_checkout(self, user: dict) -> str:
        if not self.ready:
            raise BillingError("支付尚未配置；请联系管理员或使用早期免费权益")
        base = self.config.public_base_url.rstrip("/")
        data = {
            "mode": "subscription",
            "line_items[0][price]": self.config.stripe_pro_price_id,
            "line_items[0][quantity]": "1",
            "success_url": base + "/?billing=success",
            "cancel_url": base + "/?billing=cancelled",
            "client_reference_id": str(user["id"]),
            "metadata[user_id]": str(user["id"]),
            "subscription_data[metadata][user_id]": str(user["id"]),
            "allow_promotion_codes": "true",
        }
        if user.get("stripe_customer_id"):
            data["customer"] = user["stripe_customer_id"]
        else:
            data["customer_email"] = user["email"]
        result = await self._post("/v1/checkout/sessions", data)
        if not result.get("url"):
            raise BillingError("支付平台未返回结账地址")
        return result["url"]

    async def create_portal(self, user: dict) -> str:
        if not self.ready or not user.get("stripe_customer_id"):
            raise BillingError("当前账号还没有可管理的订阅")
        result = await self._post(
            "/v1/billing_portal/sessions",
            {
                "customer": user["stripe_customer_id"],
                "return_url": self.config.public_base_url.rstrip("/") + "/",
            },
        )
        if not result.get("url"):
            raise BillingError("支付平台未返回账单管理地址")
        return result["url"]

    async def _post(self, path: str, data: Dict[str, str]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.stripe.com" + path,
                data=data,
                headers={"Authorization": f"Bearer {self.config.stripe_secret_key}"},
            )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message")
            except ValueError:
                detail = response.text[:200]
            raise BillingError(detail or f"支付平台返回 HTTP {response.status_code}")
        return response.json()

    def verify_event(self, payload: bytes, signature_header: str) -> Dict[str, Any]:
        secret = self.config.stripe_webhook_secret
        if not secret:
            raise BillingError("STRIPE_WEBHOOK_SECRET 尚未配置")
        values: Dict[str, list] = {}
        for part in signature_header.split(","):
            if "=" in part:
                key, value = part.split("=", 1)
                values.setdefault(key, []).append(value)
        try:
            timestamp = int(values["t"][0])
        except (KeyError, ValueError, IndexError) as exc:
            raise BillingError("Stripe-Signature 格式无效") from exc
        if abs(int(time.time()) - timestamp) > 300:
            raise BillingError("Webhook 时间戳超过 5 分钟容差")
        signed = str(timestamp).encode() + b"." + payload
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, value) for value in values.get("v1", [])):
            raise BillingError("Webhook 签名无效")
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise BillingError("Webhook JSON 无效") from exc

    def process_event(self, event: Dict[str, Any]) -> bool:
        event_id = str(event.get("id") or "")
        if not event_id:
            raise BillingError("Webhook 缺少事件 ID")
        if self.db.webhook_seen(event_id):
            return False
        event_type = event.get("type") or ""
        obj = (event.get("data") or {}).get("object") or {}
        if event_type == "checkout.session.completed":
            raw_user_id = obj.get("client_reference_id") or (obj.get("metadata") or {}).get(
                "user_id"
            )
            if str(raw_user_id).isdigit():
                self.db.update_subscription(
                    user_id=int(raw_user_id),
                    customer_id=str(obj.get("customer") or ""),
                    subscription_id=str(obj.get("subscription") or ""),
                    status="active",
                )
        elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
            expires_at = self._timestamp_iso(obj.get("current_period_end"))
            self.db.update_subscription(
                customer_id=str(obj.get("customer") or ""),
                subscription_id=str(obj.get("id") or ""),
                status=str(obj.get("status") or "none"),
                expires_at=expires_at,
            )
        self.db.mark_webhook(event_id)
        return True

    @staticmethod
    def _timestamp_iso(value: Optional[int]) -> Optional[str]:
        if not value:
            return None
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
