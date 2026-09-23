# Globex — 跨境商品检索 Agent MVP

Globex 是一个基于 AgentScope 2.x 的跨境商品检索与比较演示系统。它采用 DDD 分层、FastAPI、SQLite、Redis、Qdrant 与 React，并提供可 Docker Compose 部署的单一浏览器入口。

> **MVP 数据与交易边界**：商品、品牌、价格、库存、订单和历史种子地址均为项目自建的虚构演示数据。本版本支持商品检索、比较、版本化静态规则的模拟到手价，以及**受控模拟订单创建、取消与逻辑删除**。聊天 Agent 只推荐目录 SKU，必须由用户在草案卡明确确认后才会创建订单；不支持真实支付、退款、履约、物流、库存预占/变更或真实售后。新模拟订单不收集实际收件地址。

完整的范围、费用规则、隐私和 API 契约见 [`docs/SIMULATED_ORDERS_V1_DESIGN.md`](docs/SIMULATED_ORDERS_V1_DESIGN.md) 与 [`docs/MVP_READONLY_ORDERS.md`](docs/MVP_READONLY_ORDERS.md)，商品数据说明见 [`docs/catalog-data-foundation.md`](docs/catalog-data-foundation.md)。

## MVP 能力

- **商品检索 Agent**：自然语言检索、查询改写、向量召回、可选 rerank、关键词降级、价格与目的市场硬过滤；
- **跨境信息演示**：商品卡可展示模拟到手价（商品小计、运费与关税），数值仅用于功能演示；
- **长期偏好**：保存和应用稳定的显式偏好；
- **会话与事件流**：WebSocket 推送模型、工具、计划与最终回答事件；
- **多国虚构目录**：超过 100 条结构化 SPU，覆盖 CN、US、EU、GB、JP、KR、SG、AU、NZ、TH、MY、AE、BR、CA 等目的市场，以及多种虚构产地和币种；
- **受控模拟订单中心**：Agent 目录推荐可打开“模拟订单草案”，用户核价后确认创建；可取消或逻辑删除自己的运行时模拟订单。不会支付、履约或变更库存，公开响应不包含买家 ID、姓名、电话、地址、控制令牌或取消原因；
- **生产式前端容器**：React 静态构建由 Nginx 托管，`/api/*` 反向代理 FastAPI，`/ws/*` 代理 WebSocket。

## 运行时结构

```text
浏览器 http://localhost:8080
        │
        ▼
Nginx + React 静态站点（frontend）
  ├── /                 React SPA
  ├── /api/*            → FastAPI app:8000（去除 /api 前缀）
  └── /ws/*             → FastAPI WebSocket（去除 /ws 前缀）
        │
        ├── app          FastAPI + Agent + SQLite
        ├── worker       Redis Stream 意图消费
        ├── redis        缓存、队列与事件背板
        └── qdrant       商品与知识库向量索引
```

主要目录：

```text
app/
├── domain/              Product / Sku / Money / Order / 仓储端口
├── application/         Agent、检索与受控模拟订单用例、工具、提示词
├── infrastructure/      SQLite、Redis、Qdrant、模型、缓存、韧性与种子数据
├── presentation/        FastAPI 路由、WebSocket 与脱敏 DTO
├── composition.py       API / worker 共用的装配根
└── worker.py            队列消费者入口
frontend/                React + Vite 源码、Nginx 生产镜像
knowledge/               品类洞察 Markdown
scripts/                 本地运行辅助脚本
docker/docker-compose.yaml
```

## Docker Compose 部署（推荐）

配置 OpenAI 兼容网关：把配置写进项目根目录的 `.env`（可从 `.env.example` 复制）。

```bash
cp .env.example .env
# 编辑 .env：至少填好 LLM_BASE_URL 与 LLM_API_KEY，
# 并把 LLM_MODEL 设成你的网关实际支持的型号

docker compose -f docker/docker-compose.yaml up -d --build
```

`.env` 是 `app`/`worker` 的唯一权威来源：它通过 compose 的 `env_file` 注入，宿主机同名环境变量
（例如机器级的 `LLM_MODEL`）无法覆盖。若某个型号只存在于宿主机环境变量里，容器不会采用它。

打开：**http://localhost:8080**

- 前端页面和 API/WS 使用同源地址；浏览器请求为 `/api/commerce/*` 与 `/ws/commerce/events`。
- Compose 默认不向宿主机直接暴露 FastAPI `8000`；如需直接调试，可临时为 `app` 添加 `ports: ["8000:8000"]`。
- SQLite、Redis、Qdrant 数据由 `globex_app-data`、`globex_redis-data`、`globex_qdrant-data` Docker volumes 持久化。
- 首次启动会幂等补充缺失的虚构商品和模拟订单；不会覆盖既有同 ID 数据。

常用验证：

```bash
docker compose -f docker/docker-compose.yaml config
curl http://localhost:8080/healthz
curl http://localhost:8080/api/health
```

停止服务：

```bash
docker compose -f docker/docker-compose.yaml down
```

## 本地开发

### 后端

```bash
uv sync
cp .env.example .env   # 首次运行：填好 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
uv run uvicorn app.presentation.server:app --port 8000
```

应用启动时经 `load_dotenv` 读取同一份 `.env`，并以 `.env` 为准（覆盖进程内同名变量）；
也可直接用 `scripts/run_qwen_backend.ps1`，它先通过 `scripts/load_env.ps1` 加载 `.env` 再启动。

如启用 Redis 队列，另起一个终端：

```bash
uv run python -m app.worker
```

### 前端

```bash
cd frontend
npm ci
npm run dev
```

Vite 已将 `/api` 和 `/ws` 代理至本机 `http://localhost:8000`，因此无需在浏览器中配置跨域 API 地址。

## 受控模拟订单 API

```text
POST /commerce/order-quotes
POST /commerce/orders                   # 必须带 Idempotency-Key
POST /commerce/orders/{order_id}/cancellations
DELETE /commerce/orders/{order_id}          # body: one-time control token; logical delete only
GET  /commerce/orders?limit=1..50
GET  /commerce/orders/{order_id}
```

示例（所有金额都是静态规则的演示估算）：

```bash
curl http://localhost:8080/api/commerce/orders
curl http://localhost:8080/api/commerce/orders/DEMO-CN-24001
curl -X POST http://localhost:8080/api/commerce/order-quotes \
  -H "Content-Type: application/json" \
  -d '{"items":[{"product_id":"P1001","sku_id":"P1001-S1","quantity":1}],"destination_country":"US","currency":"USD"}'
```

聊天 Agent 的商品卡只可打开订单草案；草案先请求服务端报价，只有用户点击“确认创建模拟订单”才发起创建。创建只接受虚构目录商品、目的市场和显示币种，不接受真实地址；创建响应一次性返回控制令牌。取消仅适用于运行时创建且处于 `CONFIRMED` 的订单；逻辑删除适用于当前页仍持令牌的 `CONFIRMED` 或 `CANCELLED` 运行时订单，删除后公开列表隐藏、详情为 404，但订单行与幂等审计不会物理删除。公开读取响应仅返回订单号、状态、费用拆分、规则版本、时间、订单行和目的国家；不会返回买家身份、电话号码、详细地址、控制令牌、令牌摘要或取消原因。

## 质量验证

```bash
uv run pytest
cd frontend && npm run build
```

当前测试覆盖领域规则、检索、缓存、队列、SQL 仓储、商品数据底座、Agent 护栏、模拟订单列表与种子幂等性。

## 后续演进

要从受控模拟订单进入真实交易，必须先单独实现真实认证与授权、账户归属、地址与隐私合规、正式报价确认、库存预占、支付/退款状态机、支付回调验证、履约、审计日志和保留策略。不得将当前模拟控制令牌、静态费用规则或模拟写接口直接复用为真实交易能力。
