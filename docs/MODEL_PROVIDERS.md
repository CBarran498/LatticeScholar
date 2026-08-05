# 多模型接入与 BYOK 安全指南

LatticeScholar v0.9 把模型当作可替换的科研计算资源，而不是一个新的聊天窗口。每项任务仍由项目问题、检索证据、PDF 原文和政策原文约束；模型只负责结构化生成与推理。

## 支持矩阵

| 分组 | 服务 | 默认协议 | 默认快速 / 深度模型 | 说明 |
|---|---|---|---|---|
| 国内 | DeepSeek | OpenAI Chat compatible | `deepseek-v4-flash` / `deepseek-v4-pro` | 保留任务级 thinking 控制 |
| 国内 | 通义千问 | OpenAI Chat compatible | `qwen3.7-flash` / `qwen3.7-max` | 百炼工作空间和海外区域可能使用不同 Host |
| 国内 | 智谱 GLM | OpenAI Chat compatible | `glm-5.2` | 模型 ID 可在界面修改 |
| 国内 | Kimi / Moonshot | OpenAI Chat compatible | `kimi-k2.6` | 中国站与国际站密钥、地址需匹配 |
| 国内 | MiniMax | OpenAI Chat compatible | `MiniMax-M2.7` | 以账号当前模型列表为准 |
| 国内 | 腾讯混元 | OpenAI Chat compatible | `hunyuan-turbos-latest` | 留意控制台迁移通知 |
| 国内 | 豆包 / 火山方舟 | OpenAI Chat compatible | Seed 2.0 Lite / Pro | 部分账号需填写推理接入点 ID |
| 国内 | 百度千帆 | OpenAI Chat compatible | ERNIE / GLM | 统一网关可调用多种模型 |
| 国际 | OpenAI | OpenAI Chat | `gpt-5.6-luna` / `gpt-5.6-sol` | 使用结构化 JSON 模式 |
| 国际 | Anthropic Claude | Messages API | Haiku 4.5 / Sonnet 5 | 原生 `x-api-key` 与版本头 |
| 国际 | Google Gemini | OpenAI compatible | Gemini Flash / Pro | 使用 Google 官方兼容端点 |
| 国际 | Mistral AI | OpenAI Chat compatible | Small / Large latest | JSON 提示和本地结构校验 |
| 国际 | Cohere | Chat v2 | Command A+ | 原生 Chat 与 JSON response format |
| 国际 | xAI Grok | OpenAI compatible | `grok-4.5` | 模型 ID 可编辑 |
| 聚合 | OpenRouter | OpenAI compatible | 用户可选 | 价格、数据处理与原厂不同 |
| 自定义 | 本地 / 校内网关 | OpenAI compatible | 用户填写 | 默认只允许 loopback 地址 |

默认模型只是安装时的合理起点，不是永久常量。连接测试若提示模型不存在，应进入厂商控制台确认账号所在区域、模型权限、正式模型 ID 或推理接入点 ID，再回到模型控制台修改。

“主流模型”不等于把所有云产品伪装成同一种 API Key。Azure OpenAI 需要资源端点、部署名和 API 版本，Amazon Bedrock 与 Vertex AI 通常依赖机构 IAM、区域、角色和短期凭据；它们没有被塞进单一 Key 表单。机构部署应把这三类服务实现为独立企业连接器，使用工作负载身份和短期凭据。当前版本可先通过受控的校内 OpenAI-compatible 网关接入，但必须由管理员启用远程自定义地址并限制出站网络。

## 用户操作

1. 打开“模型控制台”，选择服务商并点击“连接服务”。
2. 从厂商官方控制台复制 API Key；不要从第三方购买或共享密钥。
3. 核对 Base URL、快速模型和深度模型；阅读数据发送与费用确认。
4. 加密保存后点击该服务商卡片上的“测试”。
5. 在智能路由中选择节省、均衡或质量，并可指定首选服务。

保存成功不等于模型一定可用。最小连接测试同时检查鉴权、模型权限和 JSON 响应；真实论文任务还会检查简体中文、四问结构、证据编号与行动项。

## 路由与费用

- `economy`：全部任务使用快速模型；
- `balanced`：检索式和连接测试使用快速模型，论文解剖、Idea Lab、课题研讨使用深度模型；
- `quality`：全部任务使用深度模型。

平台一次只选择一个模型。启用故障切换时，只会在超时、限流或厂商 5xx 等暂时性错误后尝试下一服务；API Key 无效、余额不足、输入被拒绝或输出结构不合格不会跨厂商重试。用量页展示实际提供方、模型、Token 和耗时，但无法代替厂商账单。

## 凭据与网络安全

- BYOK 密钥使用 Fernet 加密；数据库不保存明文，GET 接口不返回密钥；
- 个人本机使用 `.data/credential.key`；生产环境使用 `LATTICE_CREDENTIAL_ENCRYPTION_KEY`；
- 官方服务商只允许其已核验域名；远程地址必须是 HTTPS；
- 自定义服务默认只允许 `localhost`、`127.0.0.1`、`::1` 和 `host.docker.internal`；
- 开放任意远程兼容网关需设置 `LATTICE_ALLOW_CUSTOM_MODEL_HOSTS=true`，生产环境仍应配置 DNS 与出站网络白名单；
- 密钥不会写入模型用量日志，论文正文、问题与回答也不会进入该日志。

## 科研可信度边界

结构正确的 JSON 仍可能包含语义错误。平台因此采用分层防线：数据源状态与元数据覆盖可见；PDF 先报告解析质量；四问输出必须中文且证据独立；项目研讨只接受真实存在的证据编号；Idea 明确标为待证伪假设。引用、数字、统计结论、政策适用性、伦理合规和新颖性最终必须回到原文与人工判断。

## 生产运维

生产部署应备份 SQLite 与加密密钥，但两者分开保存；轮换加密密钥前需要实现密文重加密，不能直接替换环境变量。删除用户时应同步删除其 `provider_credentials`、模型用量元数据和项目数据。运营方不得要求用户通过客服、Issue 或邮件发送密钥。
