# GitHub 开源发布操作手册

本手册对应账号 `CBarran498`、仓库建议名称 `LatticeScholar` 和版本 `v0.9.0`。源码发布包已排除本地数据库、密钥、缓存、虚拟环境、构建产物与宣传素材。

## 一、发布前的最后确认

1. 解压 `LatticeScholar-v0.9.0-github-source.zip` 到一个全新目录；
2. 对照根目录 `OPEN_SOURCE_MANIFEST.txt`，确认不存在 `.env`、`.data`、`.venv`、`.git`；
3. 核对 `SHA256SUMS.txt` 中的压缩包校验值；
4. 阅读 `LICENSE`、`THIRD_PARTY_NOTICES.md` 和 `docs/RELEASE_AUDIT.md`；
5. 确认 README 中的账号、邮箱、定价和产品边界符合你的最终决定；
6. 如果曾在任何文件或 Git 历史里写过真实密钥，先去对应平台撤销并生成新密钥。

## 二、在 GitHub 创建空仓库

登录 GitHub 后点击右上角 `+` → `New repository`：

- Owner：`CBarran498`；
- Repository name：`LatticeScholar`；
- Description：`Local-first, evidence-grounded research workspace for literature discovery, paper analysis, policy signals and falsifiable research ideas.`；
- Visibility：`Public`；
- 不要勾选 Add a README、Add .gitignore 或 Choose a license，因为本地包已包含；
- 点击 `Create repository`。

建议仓库 Topics：

```text
academic-research literature-review research-tools paper-analysis
research-assistant local-first evidence-based fastapi python
semantic-scholar crossref pubmed openalex
```

## 三、第一次提交并推送

在解压后的源码目录执行。提交邮箱可以使用 GitHub 提供的 noreply 邮箱：

```bash
git init -b main
git config user.name "CBarran498"
git config user.email "barranscipitstop@users.noreply.github.com"
git add .
git status --short
git diff --cached --stat
git commit -m "feat: publish LatticeScholar v0.9.0"
git remote add origin https://github.com/CBarran498/LatticeScholar.git
git push -u origin main
```

如果 Git 提示 remote 已存在，先运行 `git remote -v` 确认它是否是你的目标仓库；只有确认错误后才执行 `git remote set-url origin ...`。不要把访问令牌写进 remote URL。

使用 GitHub CLI 的另一种方法：

```bash
gh auth login
gh repo create CBarran498/LatticeScholar --public --source=. --remote=origin --push
```

## 四、GitHub 仓库设置

进入仓库 `Settings`：

### General

- 勾选 Issues；
- 勾选 Discussions，并建立 `公告`、`使用求助`、`研究工作流`、`数据源` 分类；
- 保留 Releases；
- Social preview 上传 `promotion-kit/images/github-social-preview-1280x640.png`；
- 默认分支设为 `main`。

### Rules → Rulesets

为 `main` 新建规则：

- Require a pull request before merging；
- Require status checks to pass：选择 CI 中的测试任务；
- Require conversation resolution before merging；
- Block force pushes；
- Block deletions；
- 单人维护早期可暂不要求批准人数，但仍应通过 PR 自审；有维护者后设为至少 1 人批准。

### Actions

- Actions permissions 允许仓库内工作流运行；
- Workflow permissions 默认 `Read repository contents`；
- 只给需要创建 Release 的工作流 `contents: write`；
- 不接受陌生 PR 工作流访问生产 Secrets。

### Code security and analysis

- 开启 Dependabot alerts 和 Dependabot security updates；
- 开启 Secret scanning 和 Push protection（若账号计划支持）；
- 开启 Private vulnerability reporting；
- 生产 API Key 只放在 GitHub Actions Secrets 或部署平台秘密管理器中。

## 五、发布 v0.9.0

先确认 Actions 绿灯，再创建带说明的标签：

```bash
git tag -a v0.9.0 -m "LatticeScholar v0.9.0"
git push origin v0.9.0
```

仓库中的 Release 工作流会在 `v*` 标签推送后构建发布文件。进入 `Releases` 检查自动生成的标题、变更摘要和附件。正式点击发布前，至少手工验证一个全新环境能按 README 完成安装和启动。

后续更新遵循：新分支 → 修改 → 测试 → Pull Request → CI → 合并 → 更新 CHANGELOG 和版本号 → 新标签。版本建议使用语义化规则：修复为 `0.9.1`，向后兼容功能为 `0.10.0`，破坏性变化到稳定期后使用主版本号。

## 六、首发页面优化

- README 首屏只保留一句定位、截图、三分钟启动和核心差异；
- 在 About 中加入简短描述、网站（如果有）和 Topics；
- 固定一个 Discussion 欢迎帖和一个 Roadmap Issue；
- 建立 `good first issue`、`help wanted`、`pdf`、`data-source`、`policy`、`ui` 标签；
- 不购买星标、不做互星活动，不宣称“100% 准确”或“替代科研判断”；
- 用真实流程截图、可复现实例、响应速度和覆盖率解释工程质量，不把覆盖率当产品正确率。

## 七、收到反馈后如何实时更新

```bash
git switch -c fix/short-description
# 修改并测试
git add path/to/changed-files
git commit -m "fix: describe the user-visible change"
git push -u origin fix/short-description
```

然后在 GitHub 创建 Pull Request，关联 Issue，等待 CI，通过后合并。紧急安全问题先通过私密漏洞报告处理，不要让用户在公开 Issue 上传未脱敏论文、邮箱、密钥或日志。

## 八、首发后 14 天运营节奏

- 第 0 天：Release、Discussion 欢迎帖、演示视频和中文长文同时发布；
- 第 1—3 天：回复安装问题，整理 FAQ，只修阻断性错误；
- 第 4—7 天：发布一篇完整工作流案例，公开 Roadmap；
- 第 8—10 天：邀请 5—10 位真实研究者做任务测试，记录完成率而不是只问“好不好看”；
- 第 11—14 天：发布小版本，列出采纳的社区反馈，标注已知限制；
- 每周：依赖安全与政策候选巡检；
- 每月：数据源条款、模型配置、许可证和文档复核。

