/**
 * Cloudflare Worker - ETF Premium Monitor Trigger
 *
 * 通过 Cron Trigger 定时调用 Render 上的 Python API，
 * 触发 ETF 溢价率监控流程。
 *
 * 环境变量（在 Cloudflare Dashboard 中设置）：
 * - API_URL: Python 服务的地址，如 https://etf-premium-alert.onrender.com
 * - ETF_CODES: 逗号分隔的 ETF 代码列表，如 "513500,513650,159501,159696,159612"
 *
 * KV 绑定：
 * - ETF_DATA: Workers KV 命名空间，用于持久化数据
 */

export default {
  /**
   * Cron Trigger 定时触发
   */
  async scheduled(event, env, ctx) {
    const apiUrl = env.API_URL || "https://etf-premium-alert.onrender.com";

    // 0. Pre-warm: wake up Render instance from cold sleep
    try {
      await fetch(`${apiUrl}/health`, { method: "GET" });
    } catch (e) {
      // Ignore — just a wake-up call
    }

    // 1. Restore from KV before trigger
    await restoreFromKV(env, apiUrl);

    // 判断是盘中监控还是收盘摘要
    // UTC 7:30 = 北京 15:30，触发每日摘要
    const hour = new Date(event.scheduledTime).getUTCHours();
    const minute = new Date(event.scheduledTime).getUTCMinutes();
    const isSummary = hour === 7 && minute === 30;

    const endpoint = isSummary ? "/summary" : "/trigger";

    try {
      const response = await fetch(`${apiUrl}${endpoint}`, {
        method: "GET",
        headers: { "User-Agent": "Cloudflare-Worker-ETF-Monitor" },
      });

      const data = await response.json();
      console.log(`[${new Date().toISOString()}] ${endpoint} 触发成功: status=${data.status}`);

      if (data.results) {
        for (const r of data.results) {
          if (r.error) {
            console.log(`  [${r.code}] 错误: ${r.error}`);
          } else {
            console.log(`  [${r.code}] 溢价率=${r.premium_rate}%, 建议=${r.suggestion}`);
          }
        }
      }

      // 3. Backup to KV after successful trigger
      if (data.status === "success") {
        await backupToKV(env, apiUrl);
      }
    } catch (err) {
      console.error(`[${new Date().toISOString()}] ${endpoint} 触发失败: ${err.message}`);
    }
  },

  /**
   * HTTP 请求处理
   * - POST /record: 代理到 Python API /record，成功后备份到 KV
   * - 其他请求: 代理到 /trigger（手动测试）
   */
  async fetch(request, env, ctx) {
    const apiUrl = env.API_URL || "https://etf-premium-alert.onrender.com";
    const url = new URL(request.url);

    // Handle /record route
    if (url.pathname === "/record" && request.method === "POST") {
      try {
        // Forward POST /record request body to Python API /record endpoint
        const body = await request.text();
        const response = await fetch(`${apiUrl}/record`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "User-Agent": "Cloudflare-Worker-ETF-Monitor",
          },
          body: body,
        });

        const responseData = await response.text();

        // On Python API error, return error without performing backup
        if (!response.ok) {
          return new Response(responseData, {
            status: response.status,
            headers: { "Content-Type": "application/json" },
          });
        }

        // On success response from Python API, call backupToKV()
        await backupToKV(env, apiUrl);

        // Return Python API response to the original caller
        return new Response(responseData, {
          status: response.status,
          headers: { "Content-Type": "application/json" },
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }
    }

    // Existing: proxy to /trigger (manual test) with backup
    try {
      const response = await fetch(`${apiUrl}/trigger?force=true`);
      const data = await response.json();

      // Backup to KV after successful trigger
      if (data.status === "success") {
        await backupToKV(env, apiUrl);
      }

      return new Response(JSON.stringify(data, null, 2), {
        headers: { "Content-Type": "application/json" },
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }
  },
};

/**
 * 解析 ETF_CODES 环境变量为代码数组
 */
function getETFCodes(env) {
  return (env.ETF_CODES || "").split(",").map((c) => c.trim()).filter(Boolean);
}

/**
 * 从 KV 恢复数据到 Python API
 * - 读取 positions 和所有 premium_{code} 键
 * - 如果任一键有数据，POST 到 /data/restore
 * - 如果所有键为 null，跳过恢复调用
 * - 出错时记录日志并继续
 */
async function restoreFromKV(env, apiUrl) {
  try {
    const codes = getETFCodes(env);
    const payload = {};
    let hasData = false;

    // Read positions key from KV
    const positionsData = await env.ETF_DATA.get("positions");
    if (positionsData !== null) {
      payload.positions = JSON.parse(positionsData);
      hasData = true;
    } else {
      payload.positions = null;
    }

    // Read all premium_{code} keys from KV
    for (const code of codes) {
      const key = `premium_${code}`;
      const value = await env.ETF_DATA.get(key);
      if (value !== null) {
        payload[key] = JSON.parse(value);
        hasData = true;
      } else {
        payload[key] = null;
      }
    }

    // If all keys are null, skip restore call
    if (!hasData) {
      console.log("[restoreFromKV] KV 中无数据，跳过恢复");
      return;
    }

    // POST to /data/restore with timeout of 10 seconds
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    try {
      const response = await fetch(`${apiUrl}/data/restore`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "User-Agent": "Cloudflare-Worker-ETF-Monitor",
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        console.error(`[restoreFromKV] 恢复失败: HTTP ${response.status}`);
      } else {
        console.log("[restoreFromKV] 数据恢复成功");
      }
    } catch (fetchErr) {
      clearTimeout(timeoutId);
      throw fetchErr;
    }
  } catch (err) {
    console.error(`[restoreFromKV] 错误: ${err.message}`);
  }
}

/**
 * 备份 Python API 数据到 KV
 * - 调用 GET /data/backup（30 秒超时）
 * - 将响应中每个非 null 的键写入 KV
 * - 跳过 null/undefined 值
 * - 出错时记录日志并继续（不阻塞监控）
 */
async function backupToKV(env, apiUrl) {
  try {
    // Call GET /data/backup with 30-second timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    let response;
    try {
      response = await fetch(`${apiUrl}/data/backup`, {
        method: "GET",
        headers: { "User-Agent": "Cloudflare-Worker-ETF-Monitor" },
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
    } catch (fetchErr) {
      clearTimeout(timeoutId);
      throw fetchErr;
    }

    if (!response.ok) {
      console.error(`[backupToKV] 备份请求失败: HTTP ${response.status}`);
      return;
    }

    const data = await response.json();

    // Write each non-null key from response to KV
    for (const [key, value] of Object.entries(data)) {
      if (value === null || value === undefined) {
        continue;
      }
      try {
        await env.ETF_DATA.put(key, JSON.stringify(value));
      } catch (kvErr) {
        console.error(`[backupToKV] KV 写入失败 (${key}): ${kvErr.message}`);
      }
    }

    console.log("[backupToKV] 数据备份成功");
  } catch (err) {
    console.error(`[backupToKV] 错误: ${err.message}`);
  }
}
