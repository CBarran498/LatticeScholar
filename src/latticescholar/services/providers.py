from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Tuple
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    name: str
    region: str
    protocol: str
    base_url: str
    fast_model: str
    quality_model: str
    description: str
    docs_url: str
    key_url: str
    official_hosts: Tuple[str, ...]
    base_url_editable: bool = False
    json_mode: bool = True
    notice: str = ""

    def public(self) -> dict:
        value = asdict(self)
        value.pop("official_hosts", None)
        return value


PROVIDERS: Dict[str, ProviderDefinition] = {
    "deepseek": ProviderDefinition(
        "deepseek", "DeepSeek", "中国", "openai_chat", "https://api.deepseek.com",
        "deepseek-v4-flash", "deepseek-v4-pro", "中文科研推理、长文分析与高性价比任务",
        "https://api-docs.deepseek.com/", "https://platform.deepseek.com/api_keys",
        ("api.deepseek.com",),
    ),
    "qwen": ProviderDefinition(
        "qwen", "通义千问 Qwen", "中国", "openai_chat",
        "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3.7-flash", "qwen3.7-max",
        "中文理解、长上下文与阿里云百炼模型生态",
        "https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions",
        "https://bailian.console.aliyun.com/", ("aliyuncs.com",), True,
        notice="工作空间与海外区域可能使用不同 API Host。",
    ),
    "glm": ProviderDefinition(
        "glm", "智谱 GLM", "中国", "openai_chat",
        "https://open.bigmodel.cn/api/paas/v4", "glm-5.2", "glm-5.2",
        "中文推理、结构化生成与工具调用",
        "https://docs.bigmodel.cn/cn/guide/develop/openai/introduction",
        "https://bigmodel.cn/usercenter/proj-mgmt/apikeys", ("open.bigmodel.cn",),
    ),
    "kimi": ProviderDefinition(
        "kimi", "Kimi / Moonshot", "中国", "openai_chat",
        "https://api.moonshot.cn/v1", "kimi-k2.6", "kimi-k2.6",
        "长文理解、中文材料整理与科研写作辅助",
        "https://platform.kimi.ai/docs/api/overview", "https://platform.moonshot.cn/console/api-keys",
        ("api.moonshot.cn", "api.moonshot.ai"), True,
        notice="中国站与国际站密钥不可混用，请匹配对应 Base URL。",
    ),
    "minimax": ProviderDefinition(
        "minimax", "MiniMax", "中国", "openai_chat", "https://api.minimaxi.com/v1",
        "MiniMax-M2.7", "MiniMax-M2.7", "长上下文、中文生成与 OpenAI 兼容接入",
        "https://platform.minimaxi.com/docs/api-reference/api-overview",
        "https://platform.minimaxi.com/user-center/basic-information/interface-key",
        ("api.minimaxi.com",),
    ),
    "hunyuan": ProviderDefinition(
        "hunyuan", "腾讯混元", "中国", "openai_chat",
        "https://api.hunyuan.cloud.tencent.com/v1", "hunyuan-turbos-latest", "hunyuan-turbos-latest",
        "腾讯云兼容接口与中文通用任务",
        "https://cloud.tencent.com/document/product/1729/111007",
        "https://console.cloud.tencent.com/hunyuan/start", ("api.hunyuan.cloud.tencent.com",),
        notice="请留意腾讯云控制台的服务迁移与模型可用性通知。",
    ),
    "doubao": ProviderDefinition(
        "doubao", "豆包 / 火山方舟", "中国", "openai_chat",
        "https://ark.cn-beijing.volces.com/api/v3", "doubao-seed-2-0-lite-260215",
        "doubao-seed-2-0-pro-260215", "低延迟中文任务与火山方舟模型服务",
        "https://www.volcengine.com/docs/82379/1795150",
        "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey", ("volces.com",), True,
        notice="方舟账号可能需要填写控制台中的模型或推理接入点 ID。",
    ),
    "qianfan": ProviderDefinition(
        "qianfan", "百度千帆", "中国", "openai_chat", "https://qianfan.baidubce.com/v2",
        "ernie-4.5-turbo-20260402", "glm-5.1", "文心与国内主流模型的统一兼容网关",
        "https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb",
        "https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application",
        ("qianfan.baidubce.com", "api.baiduqianfan.ai"), True,
    ),
    "openai": ProviderDefinition(
        "openai", "OpenAI", "国际", "openai_chat", "https://api.openai.com/v1",
        "gpt-5.6-luna", "gpt-5.6-sol", "多语言推理、结构化输出与科研任务编排",
        "https://developers.openai.com/api/docs/models", "https://platform.openai.com/api-keys",
        ("api.openai.com",),
    ),
    "anthropic": ProviderDefinition(
        "anthropic", "Anthropic Claude", "国际", "anthropic_messages",
        "https://api.anthropic.com", "claude-haiku-4-5", "claude-sonnet-5",
        "长文阅读、严谨表达与复杂研究材料审阅",
        "https://platform.claude.com/docs/en/api/messages", "https://console.anthropic.com/settings/keys",
        ("api.anthropic.com",), False, False,
    ),
    "gemini": ProviderDefinition(
        "gemini", "Google Gemini", "国际", "openai_chat",
        "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.6-flash",
        "gemini-3.1-pro-preview", "多语言、长上下文与 Google 模型生态",
        "https://ai.google.dev/gemini-api/docs/openai", "https://aistudio.google.com/app/apikey",
        ("generativelanguage.googleapis.com",),
    ),
    "mistral": ProviderDefinition(
        "mistral", "Mistral AI", "国际", "openai_chat", "https://api.mistral.ai/v1",
        "mistral-small-latest", "mistral-large-latest", "多语言、欧洲部署与结构化任务",
        "https://docs.mistral.ai/api/", "https://console.mistral.ai/api-keys", ("api.mistral.ai",),
    ),
    "cohere": ProviderDefinition(
        "cohere", "Cohere", "国际", "cohere_chat", "https://api.cohere.com/v2",
        "command-a-plus-05-2026", "command-a-plus-05-2026", "企业检索增强与多语言生成",
        "https://docs.cohere.com/v2/reference/chat", "https://dashboard.cohere.com/api-keys",
        ("api.cohere.com",), False, True,
    ),
    "xai": ProviderDefinition(
        "xai", "xAI Grok", "国际", "openai_chat", "https://api.x.ai/v1",
        "grok-4.5", "grok-4.5", "通用推理与 OpenAI 兼容接口",
        "https://docs.x.ai/developers/rest-api-reference/inference/chat",
        "https://console.x.ai/", ("api.x.ai",),
    ),
    "openrouter": ProviderDefinition(
        "openrouter", "OpenRouter", "聚合", "openai_chat", "https://openrouter.ai/api/v1",
        "openai/gpt-5.6-luna", "anthropic/claude-sonnet-5", "单一密钥访问多厂商模型的聚合路由",
        "https://openrouter.ai/docs/api/reference/overview", "https://openrouter.ai/settings/keys",
        ("openrouter.ai",), False, True,
        notice="聚合平台的数据处理、价格和路由策略与原厂不同，请单独核对。",
    ),
    "custom": ProviderDefinition(
        "custom", "自定义 OpenAI 兼容", "自定义", "openai_chat", "http://127.0.0.1:11434/v1",
        "local-model", "local-model", "接入校内网关、本地推理或其他兼容服务",
        "https://github.com/CBarran498/LatticeScholar/blob/main/docs/MODEL_PROVIDERS.md", "",
        ("127.0.0.1", "localhost", "::1", "host.docker.internal"), True, True,
        notice="默认只允许本机地址；开放自定义远程主机需要服务端明确授权。",
    ),
}


def provider_definition(provider_id: str) -> ProviderDefinition:
    try:
        return PROVIDERS[provider_id]
    except KeyError as exc:
        raise ValueError("不支持的模型服务商") from exc


def endpoint_for(base_url: str, protocol: str) -> str:
    base = base_url.rstrip("/")
    path = urlparse(base).path.rstrip("/")
    if protocol == "anthropic_messages":
        return base if path.endswith("/v1/messages") else base + "/v1/messages"
    if protocol == "cohere_chat":
        return base if path.endswith("/v2/chat") else base + "/chat"
    return base if path.endswith("/chat/completions") else base + "/chat/completions"
