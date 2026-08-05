# Third-party notices

LatticeScholar 自有源码使用 Apache License 2.0。依赖包仍分别受其原始许可证约束；本文件用于帮助发布者审核，不替代依赖项目的完整许可证文本，也不构成法律意见。

## 默认核心依赖

| 包 | 本项目约束 | 上游许可证（发布审计） | 用途 |
|---|---:|---|---|
| FastAPI | `>=0.115,<1` | MIT | Web API |
| HTTPX | `>=0.27,<1` | BSD-3-Clause | HTTP 客户端 |
| Pydantic | `>=2.8,<3` | MIT | 数据校验 |
| cryptography | `>=43,<47` | Apache-2.0 OR BSD-3-Clause | BYOK 密钥加密 |
| python-multipart | `>=0.0.12,<1` | Apache-2.0 | 文件上传 |
| PDFPlumber | `>=0.11,<1` | MIT | 默认 PDF 版面提取 |
| pdfminer.six | PDFPlumber 间接依赖 | MIT | PDF 文字解析 |
| pypdfium2 | PDFPlumber 间接依赖 | BSD-3-Clause / Apache-2.0；同时包含上游依赖许可 | PDF 渲染后端 |
| Pillow | PDFPlumber 间接依赖 | HPND | 图像支持 |
| pypdf | `>=5,<7` | BSD-3-Clause | PDF 兼容兜底 |
| Uvicorn | `>=0.30,<1` | BSD-3-Clause | ASGI 服务器 |

测试环境额外使用 pytest、pytest-asyncio、pytest-cov、Ruff 和 ReportLab；它们不会打入源码发布包的运行时依赖。

## 可选高级 PDF 依赖

`pip install -e ".[advanced-pdf]"` 会安装 PyMuPDF 与 PyMuPDF4LLM。它们采用 **GNU AGPL v3 或 Artifex 商业许可**，不因 LatticeScholar 使用 Apache-2.0 就自动变成 Apache 许可。只有用户明确设置 `LATTICE_PDF_ENGINE=pymupdf` 时，程序才会动态加载这些组件。

公网服务、商业部署、闭源修改或向第三方提供基于它们的数据处理能力前，应阅读上游当前许可条款，并根据自身场景履行 AGPL 义务或购买商业许可：

- PyMuPDF 文档与许可入口：https://pymupdf.readthedocs.io/
- PyMuPDF4LLM 许可说明：https://pymupdf.readthedocs.io/en/latest/faq/index.html

## 发布与复核说明

- GitHub 源码归档不包含上述依赖的 wheel、二进制文件或源代码；用户安装时由包管理器从上游获取。
- 依赖版本和许可证可能变化。每次正式发布都应重新生成依赖清单，并核对上游许可证文件。
- 如果组织有法务或开源办公室，生产部署前应由其完成最终复核。
