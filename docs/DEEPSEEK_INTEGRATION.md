# DeepSeek 集成指南

## 目标

LatticeScholar 不把 DeepSeek 做成一个与课题脱节的聊天窗口。模型只进入需要语言理解或跨证据推理的环节，并始终保留项目上下文、结构化输出、证据编号、人工核验提示和可见用量。

## 当前任务路由

| 任务 | `balanced` 默认模型 | 推理 | 原因 |
|---|---|---|---|
| 中英文检索式生成 | `deepseek-v4-flash` | 关闭 | 高频、短上下文、需要低延迟 |
| 连接测试 | `deepseek-v4-flash` | 关闭 | 只做最小 JSON 响应 |
| 论文深度解剖 | `deepseek-v4-pro` | 开启 | 需要长文证据选择与四问判断 |
| Idea Lab | `deepseek-v4-pro` | 开启 | 需要区分已有能力、证据缺口和待证伪假设 |
| 科研研讨室 | `deepseek-v4-pro` | 开启 | 需要在项目证据边界内综合判断 |

`economy` 将所有任务路由到 Flash，`quality` 将所有任务路由到 Pro。模型输出质量也受论文解析质量、证据完整度和提示内容影响；切换到 Pro 不代表结论自动准确。

## 五分钟启用

只在本机或服务器密钥管理器中填写真实 Key。本机直接运行时在同一个终端导出变量：

```bash
export LATTICE_LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sk-your-key
export LATTICE_ALLOW_REMOTE_LLM=true
export LATTICE_DEEPSEEK_ROUTING=balanced
latticescholar
```

Docker Compose 用户可把不带 `export` 的同名配置写入项目根目录 `.env`，再运行 `docker compose up -d --build`。直接运行 `latticescholar` 不会自动读取 `.env`；也可以先执行 `set -a; source .env; set +a` 将其加载到当前终端。

启动应用后进入“模型中心”。页面只显示“密钥已配置/未配置”，不会返回或渲染真实 Key。点击“测试模型连接”会发出一次最小 JSON 请求。

官方兼容接口基址为 `https://api.deepseek.com`，LatticeScholar 调用 `/chat/completions`，并使用 `response_format={"type":"json_object"}`。DeepSeek 的 JSON 输出要求提示中明确出现 JSON 及输出字段，因此每条模型工作流都有独立、固定的结构化协议。相关官方说明：

- [DeepSeek API 首次调用](https://api-docs.deepseek.com/guides/function_calling/)
- [Chat Completion API](https://api-docs.deepseek.com/api/create-chat-completion/)
- [JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
- [限流与用户隔离](https://api-docs.deepseek.com/quick_start/rate_limit/)
- [当前定价](https://api-docs.deepseek.com/quick_start/pricing/)

## 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 空 | 服务端 Key；不要提交到 Git |
| `LATTICE_DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | 可替换为兼容代理；使用前核验其隐私和日志政策 |
| `LATTICE_DEEPSEEK_FAST_MODEL` | `deepseek-v4-flash` | 高频轻任务模型 |
| `LATTICE_DEEPSEEK_REASONING_MODEL` | `deepseek-v4-pro` | 深度推理任务模型 |
| `LATTICE_DEEPSEEK_ROUTING` | `balanced` | `balanced` / `economy` / `quality` |
| `LATTICE_DEEPSEEK_THINKING` | `adaptive` | 按任务启用，或强制 `enabled` / `disabled` |
| `LATTICE_DEEPSEEK_REASONING_EFFORT` | `high` | `low` / `high` / `max`；以当前官方模型支持为准 |
| `LATTICE_DEEPSEEK_TIMEOUT_SECONDS` | `180` | 单次请求超时 |
| `LATTICE_DEEPSEEK_MAX_RETRIES` | `1` | 网络、限流、服务资源不足或空输出时重试次数 |
| `LATTICE_LLM_MAX_INPUT_CHARS` | `14000` | 进入远程模型前的字符上限 |
| `LATTICE_LLM_MAX_OUTPUT_TOKENS` | `1400` | 单次输出上限 |

## 数据到底会发送什么

| 工作流 | 发送内容 | 不发送内容 |
|---|---|---|
| 双语检索式 | 用户主题、领域提示、当前课题名称与研究问题 | 检索历史、证据库全文、邮箱 |
| 论文解剖 | 经长度限制和证据窗口选择的论文文字 | API Key、账号邮箱、PDF 文件本体 |
| Idea Lab | 用户已有工作、研究目标、所选论文/政策的有限字段 | 整个证据库、未选择的项目内容 |
| 科研研讨 | 当前项目问题、最多 12 条证据的摘要/笔记/分析要点、最多 8 条已选政策 | 其他项目证据、邮箱、订阅信息 |

API 的 `user_id` 使用内部 `lattice_u_<数字ID>`，不包含邮箱或其他直接身份信息。项目数据库的 `llm_runs` 只保存提供方、模型、任务、输入/输出/缓存/推理 Token、耗时和时间；不保存提示词、论文正文、回答或 API Key。

远程模型仍然意味着内容会离开本机。不要提交患者身份、未公开专利核心、保密协议材料、账号凭据、国家秘密、工作秘密或受限原始数据。

## 可靠性设计

1. 输入先限长，论文优先选择包含方法、实验、结果和局限的证据窗口。
2. 所有任务要求 JSON 对象，并由 Pydantic 再次校验字段、数量和类型。
3. 论文分析与科研研讨要求简体中文；不满足时拒绝结果或回退到零 Token 模式。
4. 科研研讨只能保留数据库中真实存在的 `E<编号>`，模型虚构的证据编号会被删除。
5. 项目证据被标记为不可信数据，其中可能出现的提示注入指令不会被当作系统指令执行。
6. 网络失败、429、部分 5xx、资源不足和偶发空 JSON 会有限重试；不会无限循环消耗 Token。
7. `length`、内容安全限制、余额不足、Key 错误和服务错误会转换为用户可理解的中文提示。

“结构化、可追溯”不等于“准确无误”。引用、数字、实验充分性、政策适用性和新颖性仍要由研究者回到原文与官方来源核验。

## 成本和性能

- 默认让 Flash 承担高频检索式扩展，避免为短任务使用更慢、更贵的推理路线。
- 模型中心展示近 30 天输入、输出、缓存命中、推理 Token 和平均耗时；据此调整路由与上限。
- 提示缓存由提供方决定，平台只记录官方返回的命中数据，不承诺命中率。
- 不在代码中硬编码人民币售价或用户扣费规则。官方模型价格和峰谷策略可能变化，托管服务应定期从提供方账单核对成本。
- 自托管 Community 用户直接承担自己的 DeepSeek 账户费用；官方 Hosted 版本应在模型调用前继续应用 Free/Pro 配额。

## 常见故障

| 页面提示 | 处理方式 |
|---|---|
| DeepSeek API Key 尚未配置 | 在服务端设置 `DEEPSEEK_API_KEY` 并重启 |
| 远程模型默认关闭 | 阅读隐私说明后设置 `LATTICE_ALLOW_REMOTE_LLM=true` |
| API Key 无效或未授权 | 到 DeepSeek 控制台检查 Key，不要在聊天或 Issue 中粘贴 Key |
| 账户余额不足 | 检查提供方余额与账单；可暂时切换本地 Ollama |
| 请求过于频繁 | 稍后重试，降低并发；托管部署增加队列和按用户限流 |
| 输出达到长度上限 | 提高输出上限或缩小问题范围；不要盲目无限增加 |
| 未按要求返回中文/JSON | 重试一次；仍失败则缩短输入并检查模型版本兼容性 |

## 发布前测试

```bash
ruff check .
pytest -q --cov=src/latticescholar --cov-report=term-missing
```

测试覆盖任务路由、请求体、授权头、非个人化 `user_id`、推理开关、缓存 Token、空响应重试、错误映射、证据引用过滤、用量聚合和 API 路径。发布到 GitHub 前还应使用自己的测试 Key 在非敏感样例上做一次模型中心连接测试与端到端论文分析。
