/**
 * LatticeScholar Mail Proxy — Cloudflare Worker
 *
 * Proxies verification-code emails through Resend so that the
 * Resend API key never leaves the server side.
 */

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

async function rateLimit(key, limitPerWindow, windowSeconds, kv) {
  if (!kv) return true;
  const now = Math.floor(Date.now() / 1000);
  const window = Math.floor(now / windowSeconds);
  const kvKey = `rl:${key}:${window}`;
  const count = parseInt((await kv.get(kvKey)) || "0", 10);
  if (count >= limitPerWindow) return false;
  await kv.put(kvKey, String(count + 1), { expirationTtl: windowSeconds * 2 });
  return true;
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (request.method !== "POST") {
      return json({ error: "Method not allowed" }, 405);
    }

    const url = new URL(request.url);
    if (url.pathname !== "/send") {
      return json({ error: "Not found" }, 404);
    }

    if (!env.RESEND_API_KEY) {
      return json({ error: "Mail service not configured" }, 503);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "Invalid JSON" }, 400);
    }

    const { to, code } = body;
    if (!to || !code || typeof to !== "string" || typeof code !== "string") {
      return json({ error: "Missing required fields: to, code" }, 400);
    }

    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(to)) {
      return json({ error: "Invalid email address" }, 400);
    }

    if (!/^\d{6}$/.test(code)) {
      return json({ error: "Invalid code format" }, 400);
    }

    const clientIP = request.headers.get("CF-Connecting-IP") || "unknown";

    if (env.RATE_LIMIT_KV) {
      const ipOk = await rateLimit(`ip:${clientIP}`, 3, 60, env.RATE_LIMIT_KV);
      if (!ipOk) {
        return json({ error: "Too many requests, please try again later" }, 429);
      }
      const emailOk = await rateLimit(
        `email:${to.toLowerCase()}`,
        5,
        3600,
        env.RATE_LIMIT_KV
      );
      if (!emailOk) {
        return json({ error: "Too many codes sent to this email" }, 429);
      }
    }

    const fromName = env.FROM_NAME || "LatticeScholar";
    const fromEmail = env.FROM_EMAIL || "onboarding@resend.dev";

    const resendPayload = {
      from: `${fromName} <${fromEmail}>`,
      to: [to],
      subject: `${code} — LatticeScholar 登录验证码`,
      html: [
        `<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px">`,
        `<h2 style="color:#1a1a2e;margin-bottom:24px">LatticeScholar 登录验证</h2>`,
        `<p style="color:#555;font-size:15px">你的验证码是：</p>`,
        `<div style="background:#f0f4ff;border-radius:8px;padding:20px;text-align:center;margin:16px 0">`,
        `<span style="font-size:32px;font-weight:700;letter-spacing:8px;color:#1a1a2e">${code}</span>`,
        `</div>`,
        `<p style="color:#888;font-size:13px">验证码 10 分钟内有效，请勿转发此邮件。</p>`,
        `<p style="color:#888;font-size:13px">如果你没有尝试登录 LatticeScholar，请忽略此邮件。</p>`,
        `<hr style="border:none;border-top:1px solid #eee;margin:24px 0">`,
        `<p style="color:#aaa;font-size:11px">LatticeScholar — 本地优先的循证科研智能工作台</p>`,
        `</div>`,
      ].join(""),
      text: `你的 LatticeScholar 验证码是：${code}\n\n10 分钟内有效，请勿转发。\n\n如果你没有尝试登录，请忽略此邮件。`,
    };

    try {
      const resp = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.RESEND_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(resendPayload),
      });

      if (!resp.ok) {
        const err = await resp.text();
        console.error("Resend API error:", resp.status, err);
        return json({ error: "Failed to send email" }, 502);
      }

      return json({ sent: true });
    } catch (err) {
      console.error("Resend fetch error:", err);
      return json({ error: "Mail service unavailable" }, 503);
    }
  },
};
