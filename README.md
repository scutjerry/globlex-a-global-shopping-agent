# Globex — 跨境商品检索与模拟下单 Agent

用一句话说清需求，Agent 负责理解、检索、比价与推荐；用户确认后，可以创建一笔**受控模拟订单**。

Globex 是一个可 `docker compose` 一键部署的跨境电商检索演示系统：基于 AgentScope 2.x 构建对话式
购物 Agent，配合向量召回、品类洞察知识库与版本化静态费用规则，完成从「自然语言找货」到
「模拟到手价 → 确认下单」的完整链路。后端 DDD 分层（FastAPI + SQLite + Redis + Qdrant），
前端 React + Vite 由 Nginx 托管，浏览器只需访问**一个入口**。

> **作者**：**jerry** ｜ 仓库：<https://github.com/scutjerry/gloshopping-agent>

> **数据与交易边界**：商品、品牌、价格、库存、订单、费用规则和历史种子地址**全部是项目自建的虚构演示数据**，
> 与任何真实商家、商品或监管认证无关。本版本支持检索、比较、模拟到手价，以及**受控模拟订单的创建、取消与逻辑删除**。
> 不支持真实支付、退款、履约、物流、库存预占/变更或真实售后；新模拟订单不收集真实收件地址。
> 聊天 Agent **不具备**创建/取消/删除订单的能力，下单必须由用户在草案卡上明确确认。

---

## 功能特性

### 1. 对话式商品检索（Agent）

- **自然语言意图理解**：SearchAgent 把买家的口语 query 改写为标准化检索规格
  （目的市场、价格上限、品类意图），而不是把原句直接丢给向量库。
- **二阶段召回 + 显式降级链**：`embedding_only` → `embedding_rerank` → `keyword_2gram`。
  每一步降级都会如实写入响应的 `recall_strategy` 字段，**不会把降级结果伪装成语义召回**。
- **硬过滤可观测**：被目的市场（`ship_to`）或价格上限挡掉的候选，以 `filtered_out` 摘要回传，
  便于定位「为什么这件商品没出现」。
- **推荐卡**：展示商品、SKU、价格与**可寄送市场**，并可直接从卡片发起下单草案。
- **多国虚构目录**：100+ 条结构化 SPU、4 大品类、100+ 虚构品牌、15 种显示币种、20+ 目的市场。

### 2. 品类洞察知识库（RAG）

5 篇品类的选购知识沉淀为向量知识库，Agent 通过 `category_insight` 工具按需检索，
让推荐理由基于知识而非模型臆测（`knowledge/*.md` → Qdrant 1024 维索引）。

### 3. 模拟到手价（报价）

- `POST /commerce/order-quotes`：**无副作用**报价，拆分商品小计、模拟运费、模拟进口税费，
  并返回规则版本与免责声明。
- V1 版本化静态规则覆盖 `US`、`EU`、`GB`、`JP`、`CN` 五个市场。
- 目的地会与商品的 `ships_to` 求交集：**不寄送该市场的商品不会给出报价**，且报错明确指出原因。

### 4. 受控模拟订单

- **创建**：聊天推荐 → 草案卡核价 → 用户点击确认 → 携带一次性控制令牌创建。必须带 `Idempotency-Key`，
  重复提交不会产生第二笔订单。
- **取消**：仅限运行时创建且处于 `CONFIRMED` 的订单。
- **逻辑删除**：订单行与幂等审计**保留**，仅置为 `DELETED` 并从公开列表隐藏（详情 404），
  重放幂等键也不会让已删订单复活。删除后前端丢弃控制令牌。
- **固定演示订单**：`DEMO-*` 种子订单可读，但**不可取消、不可删除**。
- **隐私最小化**：公开响应只返回订单号、状态、费用拆分、规则版本、时间、订单行与目的国家；
  绝不返回买家 ID、收件人姓名、电话、详细地址、控制令牌或其摘要、取消原因。
- **令牌安全**：控制令牌为一次性随机值，库内**仅存 SHA-256 摘要**，明文只驻留前端内存
  （不写入 localStorage / sessionStorage / URL / 日志）。

### 5. 长期偏好记忆

Agent 可通过 `remember_preference` / `forget_preference` 工具维护跨会话的稳定显式偏好，
并按相关性筛选后注入上下文（偏好与子 Agent 注入共用同一实例，口径不会两头漂移）。

### 6. Agent 护栏与稳定性

- **权限层**：不注册任何订单写工具，仅对计划、调度与偏好工具追加精确 `allow` 规则，
  不使用 BYPASS 全局放行。
- **序列校验 / 循环检测 / 漂移检测**：按会话累积状态，检测工具调用顺序违规、重复打转与目标漂移。
- **上下文策略**：工具结果字符上限与上下文压缩，防止商品卡 JSON 挤爆上下文；摘要数字必须来自工具返回。
- **网关配额闸门**：全进程唯一的并发/间隔限流，三个 Agent 工厂共用（各限一份等于没限）。
- **熔断与超时**：业务工具带超时与熔断保护，熔断状态可选经 Redis 跨实例共享。
- **语义缓存**：缓存 key 混入**模型名 + 提示词文件指纹**——改提示词或换模型后旧回复自动失效。

### 7. 工程与可观测

- **按需降级**：没 Redis 就退化为单进程直跑；`DATABASE_URL=file` 则用 JSON 文件存储；
  未配 reranker / Tavily / OTLP 就分别关闭对应能力。**缺配置不会导致启动失败。**
- **事件流**：WebSocket 逐条推送模型输出、工具调用、计划与最终回答，前端渲染为可视化时间线。
- **跨进程事件背板**：API 与 worker 是两个进程，若不接背板前端收不到 worker 产生的事件（已处理）。
- **可观测**：可选 OpenTelemetry 追踪；评测与压测脚本见 `eval/`、`scripts/`。

---

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
├── domain/              Product / Sku / Money / Order / 检索规格 / 仓储端口
├── application/
│   ├── agents/          主 Agent、检索与交易子 Agent、编排器、权限与上下文策略
│   ├── tools/           检索、品类洞察、订单查询、Web 搜索、偏好、子 Agent 派发
│   ├── harness/         序列校验、循环检测、漂移检测、工具契约断言
│   ├── memory/          偏好选取
│   ├── prompts/         提示词（globex.yml）
│   └── usecases/        检索用例与受控模拟订单用例
├── infrastructure/      SQLite / Redis / Qdrant / 模型 / 缓存 / 韧性 / 种子数据
├── presentation/        FastAPI 路由、WebSocket 与脱敏 DTO
├── composition.py       装配根（API 与 worker 共用，避免行为漂移）
└── worker.py            队列消费者入口
frontend/                React + Vite 源码、Nginx 生产镜像
knowledge/               品类洞察 Markdown（5 篇）
docs/                    设计契约、边界说明与故障复盘
eval/                    评测用例与标注集
scripts/                 本地运行、评测、压测与验证脚本
docker/docker-compose.yaml
```

---

## 快速开始（Docker Compose）

把配置写进项目根目录的 `.env`（可从 `.env.example` 复制）：

```bash
cp .env.example .env
# 编辑 .env：至少填好 LLM_BASE_URL 与 LLM_API_KEY，
# 并把 LLM_MODEL 设成你的网关实际支持的型号

docker compose -f docker/docker-compose.yaml up -d --build
```

打开 **<http://localhost:8080>**

`.env` 是 `app`/`worker` 的**唯一权威来源**：它通过 compose 的 `env_file` 注入，宿主机同名环境变量
（例如机器级的 `LLM_MODEL`）无法覆盖它。

- 前端页面与 API/WS 同源；浏览器请求 `/api/commerce/*` 与 `/ws/commerce/events`。
- Compose 默认不向宿主机暴露 FastAPI `8000`；如需直接调试，可临时为 `app` 加 `ports: ["8000:8000"]`。
- 数据由 `globex_app-data`、`globex_redis-data`、`globex_qdrant-data` 三个 volume 持久化。
- 首次启动幂等补充缺失的虚构商品与演示订单，**不会覆盖**既有同 ID 数据。

常用验证：

```bash
docker compose -f docker/docker-compose.yaml ps
curl http://localhost:8080/healthz
curl http://localhost:8080/api/health
```

> 注意：`docker compose up -d --build app worker` 未加 `--no-deps` 时，依赖协调可能与正在运行的
> qdrant 争抢 `6333` 端口而整体中止，导致 app 换新、worker 留旧。**只重建后端时请加 `--no-deps`。**

---

## 本地开发

### 后端

```bash
uv sync
cp .env.example .env   # 首次运行：填好 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
uv run uvicorn app.presentation.server:app --port 8000
```

应用启动时经 `load_dotenv` 读取同一份 `.env` 并以它为准（覆盖进程内同名变量）；
也可直接用 `scripts/run_qwen_backend.ps1`，它会先通过 `scripts/load_env.ps1` 加载 `.env` 再启动。

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

Vite 已将 `/api` 与 `/ws` 代理至本机 `http://localhost:8000`，无需另配跨域地址。

---

## 受控模拟订单 API

```text
POST   /commerce/order-quotes                     报价（无副作用）
POST   /commerce/orders                           创建（必须带 Idempotency-Key）
POST   /commerce/orders/{order_id}/cancellations  取消
DELETE /commerce/orders/{order_id}                逻辑删除（body 带一次性控制令牌）
GET    /commerce/orders?limit=1..50               列表
GET    /commerce/orders/{order_id}                详情
```

示例（所有金额均为静态规则的演示估算）：

```bash
curl http://localhost:8080/api/commerce/orders
curl http://localhost:8080/api/commerce/orders/DEMO-CN-24001
curl -X POST http://localhost:8080/api/commerce/order-quotes \
  -H "Content-Type: application/json" \
  -d '{"items":[{"product_id":"P1001","sku_id":"P1001-S1","quantity":1}],
       "destination_country":"US","currency":"USD"}'
```

聊天 Agent 的商品卡只能打开订单草案；草案先请求服务端重新报价，只有用户点击
「确认创建模拟订单」才会发起创建。创建只接受虚构目录商品、目的市场与显示币种，不接受真实地址。

---

## 质量验证

```bash
uv run pytest                          # 338 项测试
cd frontend && npm run build           # tsc -b && vite build（含类型检查）
```

前端镜像的构建阶段就会执行 `tsc -b && vite build`，因此**镜像构建成功即证明类型检查通过**。

测试覆盖领域规则、检索与降级、缓存、队列、SQL 仓储、商品数据底座、Agent 护栏与权限、
偏好记忆、模拟订单全流程（含 HTTP 契约、幂等、取消、逻辑删除）与种子幂等性。

评测与压测：

```bash
uv run python scripts/eval_regression.py     # 召回回归（商品 / 品类）
uv run python scripts/smoke_e2e.py           # 端到端冒烟
uv run python scripts/loadtest.py            # 或 scripts/locustfile.py
```

---

## 已知边界

要从受控模拟订单进入真实交易，必须先单独实现真实认证与授权、账户归属、地址与隐私合规、
正式报价确认、库存预占、支付/退款状态机、支付回调验证、履约、审计日志与保留策略。
**不得**将当前的模拟控制令牌、静态费用规则或模拟写接口直接复用为真实交易能力。

---

## 文档

| 文档 | 内容 |
| --- | --- |
| [`docs/SIMULATED_ORDERS_V1_DESIGN.md`](docs/SIMULATED_ORDERS_V1_DESIGN.md) | 模拟订单的产品、数据、API、隐私与测试契约 |
| [`docs/MVP_READONLY_ORDERS.md`](docs/MVP_READONLY_ORDERS.md) | 产品与部署边界说明 |
| [`docs/catalog-data-foundation.md`](docs/catalog-data-foundation.md) | 商品数据底座：表结构、导入顺序与索引流程 |
| [`docs/embedding-rag-vectorrecord-incident.md`](docs/embedding-rag-vectorrecord-incident.md) | Embedding 网关导致知识库写入失败的根因与防回归 |

---

## 作者

**jerry** — <https://github.com/scutjerry>