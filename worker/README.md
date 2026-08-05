# LatticeScholar Mail Proxy (Cloudflare Worker)

验证码邮件发送代理。将 Resend API Key 安全地保管在 Worker 环境变量中，
LatticeScholar 客户端通过 HTTP POST 请求此 Worker 来发送验证码邮件。

## 部署步骤

### 1. 注册服务

- [Resend](https://resend.com) — 免费 3000 封/月，100 封/天
- [Cloudflare Workers](https://workers.cloudflare.com) — 免费 10 万请求/天

### 2. 配置 Resend

在 Resend 控制台添加发件域名（如 `latticescholar.com`），按照提示配置 DNS 记录。
或者直接使用 Resend 提供的测试域名 `onboarding@resend.dev`（仅限发送给自己的邮箱）。

### 3. 部署 Worker

```bash
cd worker
npm install -g wrangler    # 如果尚未安装
wrangler login              # 登录 Cloudflare 账号

# 设置 Resend API Key（安全存储，不会出现在代码中）
wrangler secret put RESEND_API_KEY

# 可选：创建 KV namespace 用于速率限制
wrangler kv namespace create RATE_LIMIT_KV
# 将输出的 id 填入 wrangler.toml：
# [[kv_namespaces]]
# binding = "RATE_LIMIT_KV"
# id = "<your-namespace-id>"

# 部署
wrangler deploy
```

### 4. 更新项目配置

部署后 Worker 会有一个 URL，如 `https://lattice-mail.<your-subdomain>.workers.dev`。
将此 URL 更新到 `src/latticescholar/config.py` 中的 `mail_api_url` 默认值。

## API

### POST /send

```json
{
  "to": "user@example.com",
  "code": "123456"
}
```

成功返回 `{"sent": true}`。

### 速率限制（需要 KV）

- 每个 IP：3 次/分钟
- 每个邮箱：5 次/小时
