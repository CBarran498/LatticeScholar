# 数据源与合规

本文件记录 2026-08-03 核验的接口事实。接口条款与额度可能变化，维护者应定期复核官方文档。

## Crossref

- 官方文档：[REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)；
- 无需注册即可访问，建议使用 `mailto` 与可识别 User-Agent；
- 应缓存响应、处理状态码并在延迟升高或 429 时退避；
- 元数据总体开放，但部分由出版商提供的摘要可能仍受版权保护。

用途：DOI、题名、作者、出版年份、期刊、摘要（若提供）、引用计数信号。

## Semantic Scholar Academic Graph API

- 官方入口：[Semantic Scholar API](https://www.semanticscholar.org/product/api)；
- 部分端点需要 API Key，认证用户有更高额度；
- 覆盖和引用计数与其他来源并不一致。

用途：摘要、领域、引用信号、开放 PDF 链接（若明确提供）。

## OpenAlex

- 官方文档：[Authentication & Pricing](https://developers.openalex.org/api-reference/authentication)；
- 数据保持开放，API 自 2026 年按操作类型计费并提供每日免费额度；
- 无 Key 也有试用额度，免费 Key 提供更高每日预算；
- 应读取速率/费用响应头、批量查询并处理 429。

因此 LatticeScholar 在界面中默认不勾选 OpenAlex，由用户主动启用。

## arXiv

用途：开放预印本的题名、摘要、作者、分类和版本页面。arXiv 记录不等于通过同行评审；期刊版本和预印本可能不同。

## PubMed

- 使用 NCBI 官方 E-utilities 的 ESearch 与 EFetch；
- 每次请求带 `tool` 与联系邮箱，无 Key 时按官方低频限制使用，配置 Key 后可获得更高默认速率；
- PubMed 摘要仍可能受版权保护，应用只提供检索、分析与原记录链接，不重新分发全文。

## Web of Science

- 使用 Clarivate Web of Science Starter API v2 与 `X-ApiKey`；
- 必须在 Developer Portal 注册应用，试用、机构成员和机构集成方案有不同日配额；
- 未配置 `WOS_API_KEY` 时界面明确禁用自动检索，仍可通过授权原站与题录导入使用。

## 中国知网与 Google Scholar

- Google Scholar 官方明确不提供批量访问，并要求自动软件遵守 robots.txt，因此不实施网页抓取；
- 知网全文和批量数据受机构订阅、版权与合同约束，不以模拟登录或爬虫绕过；
- 两个平台均可在原站检索后导出 BibTeX、EndNote、RefMan、RefWorks、NoteExpress 或兼容题录，再导入统一 `Paper` 模型；
- 如机构另行取得知网数据接口授权，可在独立适配器中接入，但接口契约和数据再利用范围必须以书面授权为准。

## 政策来源

政策库只收录中央政府、全国人大、教育部、科技部、工信部、国家网信办等官方页面。每条记录必须保存发布方、发布日期和原文链接。主题标签与信号是检索辅助，不替代原文。

## 仍不自动集成的来源

- Journal Impact Factor、Scopus / CiteScore：专有指标，不冒充、不再分发；
- 付费论文全文：不绕过登录、机构授权或付费墙；
- 非官方“期刊黑名单/预警”：来源、时效和申诉机制复杂，纳入前需要单独治理方案。

## 数据质量限制

- 同一 DOI 在不同来源的摘要、作者顺序、引用计数可能冲突；
- 标题去重可能误合并同名论文，也可能漏掉翻译标题；
- 缺失摘要不代表论文质量低；
- 引用量受学科、年代、文献类型和数据库覆盖影响；
- 开放获取链接可能是预印本、作者稿或版本记录，应核验许可与版本。
