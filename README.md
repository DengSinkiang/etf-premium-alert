# QDII ETF 溢价率监控工具

实时监控 QDII ETF（513500 博时标普500ETF、159501 嘉实纳斯达克100ETF）溢价率，根据预设规则自动计算建议买入金额区间，并通过 Telegram Bot 推送监控结果。

## 功能特性

- **溢价率计算** — 实时计算 ETF 当前价格与估算净值（IOPV）的溢价率
- **买入建议** — 根据溢价率阈值和剩余目标仓位自动计算建议买入金额区间
- **Telegram 推送** — 监控结果自动推送到 Telegram，盘中及时提醒
- **HTTP API** — 提供 `/trigger` 接口，可由 Cloudflare Worker 定时调用
- **双数据源容错** — AKShare 为主、HaoETF 为备用，单一数据源故障不影响监控

## 安装方式

```bash
git clone <repo-url> etf-premium-alert
cd etf-premium-alert

# 安装依赖
pip install -r requirements.txt

# 复制配置模板并修改
cp config.yaml.example config.yaml
```

## 配置说明

编辑 `config.yaml`：

```yaml
etfs:
  - code: "513500"                # ETF 代码
    name: "博时标普500ETF"         # ETF 名称
    target_amount: 100000         # 目标仓位金额（元）
    bought_amount: 30000          # 已买入金额（元）
    sell_threshold: 8.0           # 满仓后卖出提醒阈值（%）
    group: "sp500"                # 可选，同类 ETF 对比分组
    discount_threshold: 1.0       # 折价提醒阈值（%）
    premium_rules:                # 溢价率买入规则（按溢价率从低到高排列）
      - max_premium: 1.0          # 溢价率 ≤ 1%
        min_ratio: 0.6            # 建议买入 剩余目标 × 60%
        max_ratio: 1.0            #        至 剩余目标 × 100%
      - max_premium: 3.0          # 溢价率 1%~3%
        min_ratio: 0.3
        max_ratio: 0.5
      - max_premium: 5.0          # 溢价率 3%~5%
        min_ratio: 0.1
        max_ratio: 0.2
      # 溢价率 ≥ 5% 时不建议买入，建议金额为 0

  - code: "159501"
    name: "嘉实纳斯达克100ETF"
    target_amount: 80000
    bought_amount: 20000
    premium_rules:
      - max_premium: 1.0
        min_ratio: 0.6
        max_ratio: 1.0
      - max_premium: 3.0
        min_ratio: 0.2
        max_ratio: 0.4
      - max_premium: 5.0
        min_ratio: 0.0
        max_ratio: 0.1

telegram:
  enabled: true                   # 是否启用 Telegram 推送
  bot_token: "YOUR_BOT_TOKEN"     # Bot Token
  chat_id: "YOUR_CHAT_ID"        # 接收消息的 Chat ID

alert_threshold: 3.0              # 溢价率提醒阈值（%）
lookback_days: 7                  # 动态阈值历史窗口（天）
data_dir: "data"                  # 运行数据目录
summary_time: "15:30"             # 每日摘要时间（北京时间）
```

## 运行方式

### 命令行单次运行（默认）

```bash
python -m src.main --once
```

### 指定配置文件

```bash
python -m src.main --config /path/to/config.yaml
```

### 其他命令行选项

```bash
python -m src.main --force      # 跳过交易日判断，强制运行
python -m src.main --summary    # 生成并推送每日摘要
python -m src.main --no-quiet   # 禁用安静模式，推送所有结果
```

### 快捷入口

```bash
python main.py
```

### HTTP API 模式

启动 Flask 服务后可通过 HTTP 触发监控：

```bash
python -m flask --app src.api run --host 0.0.0.0 --port 5000
```

API 端点：

- `GET /trigger` — 触发监控，返回 JSON 格式结果
- `GET /summary` — 生成每日摘要并按配置推送 Telegram
- `GET /health` — 健康检查
- `POST /record` — 记录买入/卖出交易，JSON: `{"code":"513500","type":"buy","amount":5000}`
- `POST /telegram/webhook` — Telegram Bot webhook，支持 `/buy`、`/sell`、`/undo`、`/history CODE`、`/status`、`/help`
- `GET /data/backup` — 导出运行数据，供 Worker KV 备份
- `POST /data/restore` — 从 Worker KV 恢复运行数据

如果设置环境变量 `ETF_API_SECRET`（或 `API_SECRET`），除 `/health` 和 `/telegram/webhook` 外的 API 请求需要携带：

```http
X-API-Key: <secret>
```

或：

```http
Authorization: Bearer <secret>
```

如果设置 `TELEGRAM_WEBHOOK_SECRET`，`/telegram/webhook` 只接受带有匹配
`X-Telegram-Bot-Api-Secret-Token` 头的请求。该值应与 Telegram `setWebhook`
时传入的 `secret_token` 一致。

### Docker 方式（可选）

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "flask", "--app", "src.api", "run", "--host", "0.0.0.0", "--port", "5000"]
```

## Telegram Bot 配置步骤

1. **创建 Bot** — 在 Telegram 中搜索 `@BotFather`，发送 `/newbot`，按提示设置名称
2. **获取 bot_token** — 创建成功后 BotFather 会返回形如 `123456:ABC-DEF1234...` 的 Token
3. **获取 chat_id**：
   - 向你的 Bot 发送任意消息
   - 浏览器访问 `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - 在返回的 JSON 中找到 `"chat":{"id": 123456789}`，该数字即为 chat_id
4. **填入配置** — 将 bot_token 和 chat_id 填入 `config.yaml` 的 telegram 部分

## crontab 定时运行

每 15 分钟在交易时间（周一至周五 9:00-15:00）执行监控：

```cron
*/15 9-15 * * 1-5 cd /path/to/etf-premium-alert && python -m src.main --once >> logs/cron.log 2>&1
```

注意事项：

- **仅交易日运行** — cron 表达式中 `1-5` 表示周一到周五，法定节假日需额外处理
- **时区设置** — 确保服务器时区为 `Asia/Shanghai`，可通过 `timedatectl set-timezone Asia/Shanghai` 设置
- **日志查看** — 运行日志位于 `logs/` 目录，文件名格式 `monitor_YYYYMMDD.log`

## Cloudflare Worker 部署

通过 Cloudflare Worker 定时触发 HTTP API：

1. **部署 Flask API** — 在服务器上以 HTTP API 模式运行本工具（见上方运行方式）
2. **配置 Worker 环境变量和 KV**：
   - `API_URL` — Python 服务地址，如 `https://etf-premium-alert.onrender.com`
   - `ETF_CODES` — 逗号分隔 ETF 代码，如 `513500,159501`
   - `API_SECRET` — 可选；如果 Python API 设置了 `ETF_API_SECRET`/`API_SECRET`，这里填同一个值。设置后，公网访问 Worker 的 `/record` 或手动触发入口也需要携带同样的 `X-API-Key` 或 Bearer Token
   - `ETF_DATA` — Workers KV 绑定，用于保存 `positions` 和 `premium_<code>` 数据
3. **创建 Worker** — `worker/src/index.js` 已包含定时触发、KV 恢复/备份和 `/record` 代理逻辑。简化示例：

```javascript
export default {
  async scheduled(event, env, ctx) {
    const response = await fetch("https://your-server.com/trigger");
    const data = await response.json();
    console.log("Monitor triggered:", data.status);
  },
};
```

4. **设置 Cron Trigger** — `worker/wrangler.toml` 默认配置为北京时间 9:00-15:00 每 15 分钟触发，并在 15:30 触发每日摘要

## 项目结构

```
etf-premium-alert/
├── main.py                    # 快捷启动入口
├── config.yaml.example        # 配置模板
├── requirements.txt           # Python 依赖
├── README.md
├── logs/                      # 运行日志目录
│   └── monitor_YYYYMMDD.log
├── src/
│   ├── __init__.py
│   ├── main.py                # CLI 入口
│   ├── api.py                 # HTTP API (Flask)
│   ├── config.py              # 配置加载
│   ├── monitor.py             # 监控编排器
│   ├── data_source.py         # 数据源管理器
│   ├── akshare_source.py      # AKShare 数据源
│   ├── haoetf_source.py       # HaoETF 数据源
│   ├── premium_calculator.py  # 溢价率计算
│   ├── formatter.py           # 输出格式化
│   ├── notifier.py            # Telegram 推送
│   ├── models.py              # 数据模型
│   ├── exceptions.py          # 自定义异常
│   └── logger.py              # 日志配置
└── tests/
    ├── test_premium_calculator.py
    ├── test_formatter.py
    ├── test_monitor.py
    ├── test_akshare_source.py
    ├── test_haoetf_source.py
    └── properties/            # Property-Based Tests
```

## 风险提示

⚠️ **本工具仅做辅助提醒，不构成任何投资建议。**

ETF 投资存在市场波动风险，溢价率数据可能存在延迟或误差。用户应根据自身风险承受能力独立做出投资决策，本工具作者不对使用本工具产生的任何投资损失承担责任。
