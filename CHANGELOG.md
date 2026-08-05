# Changelog

All notable changes are documented here. The format follows Keep a Changelog and semantic versioning.

## [Unreleased]

- 新增 PyInstaller 桌面打包：用户无需安装 Python，从 GitHub Releases 下载压缩包后双击即可运行。
- GitHub Actions 自动构建 macOS (ARM64)、Windows (x64) 和 Linux (x64) 三个平台的独立可执行文件。
- 打包模式下数据目录自动使用 `~/.latticescholar/`，与源码开发模式互不干扰。
- 新增 `docs/LOCAL_SETUP.md` 本地安装与使用完整指南。
- 全面开源化：移除 Stripe 计费系统、Pro/Free 会员分层和使用次数限制，所有功能对所有登录用户免费开放。
- 简化用户角色为管理员和普通用户两种，不再区分会员等级。
- 本地运行时验证码自动显示在页面上（无需配置 SMTP），部署到服务器时配置 SMTP 通过邮件发送验证码。

## [0.9.0] - 2026-08-04

- Idea Lab 新增拖放/选择已有工作，支持 PDF、DOCX、PPTX、XLSX、ODT、TXT、Markdown、RTF、HTML、CSV、JSON、BibTeX、RIS、NBIB、LaTeX 和 Jupyter Notebook。
- 文件先在当前服务内存中提取，页面显示格式、字符数、警告与解析预览；用户可移除文件，手动补充保留。
- 增加文件数、单文件大小、压缩包展开体积和模型上下文长度上限，并将导入材料按不可信数据处理以降低提示注入风险。
- 总览页右侧升级为动态研究证据引擎；重做指标卡、数据源选择、模型说明和 Idea Lab 的视觉层级。
- 全局改用严格中文换行与均衡标题策略，避免一两个汉字孤立换行。
- 自动化测试增加到 57 项；总代码覆盖率 86.53%。

## [0.8.0] - 2026-08-04

- 新增 16 类模型接入路径：8 类国内、6 类国际、OpenRouter 聚合和本地/校内 OpenAI-compatible 网关。
- 新增用户级 BYOK 凭据保险箱：Fernet 加密、末四位提示、读取接口不回显、删除与账号隔离。
- 新增模型控制台：服务商分组、官方文档、区域地址、快速/深度模型、自助测试和安全确认。
- 新增 economy / balanced / quality 智能路由、首选服务、有限故障切换和实际路由记录。
- Anthropic Messages 与 Cohere Chat 使用原生适配器，其余支持服务使用各厂商官方兼容接口。
- 自定义地址增加 HTTPS、官方域名、私网解析与显式管理员授权检查，降低 SSRF 风险。
- 文献雷达新增本轮检索质量审计：数据源成功、摘要/DOI 覆盖、多源印证、去重和解释边界。
- 论文解剖、Idea Lab、双语检索式与课题研讨新增结构、中文、证据编号和行动项质量门元数据。
- 统一升级总览、表单、卡片、模型控制台、检索摘要、动效、暗色和移动端视觉层级。
- 自动化测试增加到 53 项；总代码覆盖率 85.86%。

## [0.7.0] - 2026-08-04

- 新增 DeepSeek 原生提供方，默认兼容 `deepseek-v4-flash` 与 `deepseek-v4-pro`。
- 新增 `balanced` / `economy` / `quality` 任务路由、自适应 thinking、推理强度、有限重试和中文错误提示。
- 文献雷达新增 DeepSeek 中英文检索式生成、关键词拆解、排除项与可编辑结果。
- 新增“科研研讨室”，围绕当前项目证据和已选政策输出结论、判断、不确定性与本周行动。
- 新增“模型中心”，展示连接状态、任务路由、近 30 天 Token、缓存、推理用量和耗时。
- 新增只含元数据的模型调用日志；不保存论文正文、问题、回答或 API Key。
- 论文分析、Idea Lab 和科研研讨使用非个人化内部用户标识，不向 DeepSeek 发送邮箱。
- 深度解剖继续采用全宽“四问中文回答”，删除重复长面板并折叠原文引文。
- 自动化测试增加到 47 项；总覆盖率 85.41%，DeepSeek 与科研助手服务均达到 85%。

## [0.6.0] - 2026-08-04

- 重做核心视觉层级、字号、卡片、导航、动效与移动端适配。
- 文献雷达支持中英文双检索式、语言/摘要/OA/引用/年份高级筛选与独立结果分组。
- “摘要缺失”卡片改为简洁的仅题录状态，不再重复展示长警告。
- PDF 优先使用 PyMuPDF4LLM Markdown 多栏阅读流，保留 OCR 与兼容回退。
- 增加使用指南、科研任务台、复现清单和交流平台治理路线。
- 测试增加到 42 项，并强制总代码覆盖率不低于 85%。


## [0.5.0] - 2026-08-04

### Added

- PyMuPDF block-based PDF reading with page-aware evidence locations, repeated header/footer removal, de-hyphenation, multi-column ordering heuristics and pypdf layout fallback;
- Optional local Tesseract OCR for image-only pages, plus extraction quality, language, section coverage, truncation and OCR diagnostics;
- A four-question quick-read layer covering field pain points, innovation delta, experimental support and details requiring source review;
- Section-aware evidence-window selection for long-document model analysis to reduce latency and token waste.

### Changed

- All analytical explanations now remain in Simplified Chinese even in zero-token mode, while verbatim evidence stays in the source language for fidelity;
- Paper analysis is presented as a document-health panel, cautious verdict cards and a collapsible detailed evidence layer;
- Long titles, identifiers, URLs and unbroken English text now wrap or clamp safely across project, evidence, library and analysis views.

## [0.4.0] - 2026-08-04

### Added

- Project-centered research workspaces with active-project context, status, evidence counts and safe container deletion;
- Reproducible search history recording query, sources, year window, limit, result count, source status, latency and cache state;
- Incremental official-policy discovery, content hashes, version records, sync runs and an explicit administrator review queue;
- BibTeX/RIS export, result sorting and GitHub Release update checks;
- Structured GitHub Issue Forms, Pull Request template, Dependabot, release notes and tag-based release automation;
- Product audit and maintenance/policy operations runbooks.

### Changed

- The primary user flow now begins with a research question and project rather than disconnected feature menus;
- Imported bibliography runs can be associated with a project and are recorded in its search history;
- Policy records discovered automatically are never user-visible until approved by a local or hosted administrator.

## [0.3.0] - 2026-08-04

### Added

- Apache-2.0 open-source Community edition and hosted Free/Pro business model;
- Verified email OTP accounts, 30-day signed sessions, per-user evidence libraries, daily Free quotas, trial and early-access periods;
- Administrator console for permanent or expiring complimentary Pro access by normalized email;
- Stripe subscription Checkout, Customer Portal, signed five-minute Webhook verification, idempotent event handling, and provider-independent entitlement logic;
- Account, usage, pricing, subscription, and complimentary-access pages in the web interface;
- Production SMTP, billing, plan and quota configuration plus a detailed monetization guide.

### Changed

- Default self-hosted mode is now open Community with all local workflows available;
- Official hosted mode gates costly managed sources, model analysis, advanced Idea Lab and batch imports while preserving a useful permanent Free plan;
- Evidence library records are isolated by account owner in hosted account mode.

## [0.2.0] - 2026-08-04

### Added

- Larger, more polished private-service interface and protected login screen;
- Official PubMed E-utilities and licensed Web of Science Starter API adapters;
- Compliant BibTeX/RIS/EndNote/NBIB import path for CNKI and Google Scholar;
- Multi-source journal evidence, 16 curated policies, and 32 all-sector official policy portals;
- Private HTTPS deployment prototype with Caddy and production Compose configuration (superseded by the 0.3 open-core model).

### Changed

- Product positioning temporarily changed from public distribution to private deployment (reversed in 0.3.0);
- Evidence imported from restricted platforms now participates in analysis, journal matching, Idea Lab, library, and export workflows.

## [0.1.0] - 2026-08-03

### Added

- Local FastAPI application with a responsive, dependency-free web interface;
- Crossref, Semantic Scholar, arXiv, and optional OpenAlex literature search;
- SQLite caching, DOI/title deduplication, explainable ranking, and local library;
- Evidence-grounded abstract/PDF analysis with optional local or remote LLM;
- Evidence-based journal matching and official Chinese policy radar;
- Falsifiable Idea Lab, Markdown research brief export, tests, Docker, and governance docs.
