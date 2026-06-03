/**
 * Cloudflare Worker - ETF Premium Monitor Trigger
 *
 * 通过 Cron Trigger 定时调用 Render 上的 Python API，
 * 触发 ETF 溢价率监控流程。
 *
 * 环境变量（在 Cloudflare Dashboard 中设置）：
 * - API_URL: Python 服务的地址，如 https://etf-premium-alert.onrender.com
 */

export default {
  /**
   * Cron Trigger 定时触发
   */
  async scheduled(event, env, ctx) {
    const apiUrl = env.API_URL || "https://etf-premium-alert.onrender.com";

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
    } catch (err) {
      console.error(`[${new Date().toISOString()}] ${endpoint} 触发失败: ${err.message}`);
    }
  },

  /**
   * HTTP 请求（可用于手动测试）
   */
  async fetch(request, env, ctx) {
    const apiUrl = env.API_URL || "https://etf-premium-alert.onrender.com";

    try {
      const response = await fetch(`${apiUrl}/trigger`);
      const data = await response.json();
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
