# LatticeScholar Mail Proxy (Cloudflare Worker)

验证码邮件发送代理。将 Resend API Key 安全地保管在 Worker 环境变量中，
LatticeScholar 客户端通过 HTTP POST 请求此 Worker 来发送验证码邮件。

## 快速部署（5 分钟）

### 前提条件

- 一个 [Resend](https://resend.com) 账号（免费注册，3000 封/月）
- 一个 [Cloudflare](https://dash.cloudflare.com/sign-up) 账号（免费注册）
- Node.js 16+ 已安装

### 步骤一：安装 Wrangler CLI

```bash
npm install -g wrangler
```

### 步骤二：登录 Cloudflare

```bash
wrangler login
```

浏览器会自动打开授权页面，点击 Allow。

### 步骤三：进入 worker 目录

```bash
cd worker
```

### 步骤四：设置 Resend API Key

```bash
wrangler secret put RESEND_API_KEY
```

系统会提示输入，粘贴你的 Resend API Key（以 `re_` 开头）。
此 Key 安全存储在 Cloudflare 的加密存储中，不会出现在代码里。

### 步骤五：部署

```bash
wrangler deploy
```

部署成功后会显示 Worker URL，如：
```
Published lattice-mail (0.5s)
  https://lattice-mail.xxx.workers.dev
```

### 步骤六：更新项目配置

将 Worker URL 更新到 `src/latticescholar/config.py` 中的 `mail_api_url` 默认值：

```python
mail_api_url: str = os.getenv(
    "LATTICE_MAIL_API_URL",
    "https://lattice-mail.你的子域名.workers.dev",  # 替换为你的实际 URL
)
```

## 域名配置（正式使用）

测试阶段使用 `onboarding@resend.dev` 只能发给 Resend 账号邮箱。
正式使用需要在 Resend 中验证你的域名：

1. 在 [Resend Domains](https://resend.com/domains) 添加你的域名
2. 按照提示在 DNS 管理中添加 MX / TXT / CNAME 记录
3. 验证通过后，修改 `wrangler.toml` 中的 `FROM_EMAIL` 为 `noreply@你的域名`

## 可选：速率限制 KV

```bash
wrangler kv namespace create RATE_LIMIT_KV
```

将输出的 id 添加到 `wrangler.toml`：

```toml
[[kv_namespaces]]
binding = "RATE_LIMIT_KV"
id = "你的-namespace-id"
```

然后重新部署 `wrangler deploy`。

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
