# Globex MVP：受控模拟订单与部署边界

> **历史说明**：本文原为“只读订单”边界。根据当前用户明确决定，已由“受控模拟交易”替代；完整、可实施的产品、数据、API、隐私和测试契约见 [`SIMULATED_ORDERS_V1_DESIGN.md`](SIMULATED_ORDERS_V1_DESIGN.md)。保留本文件名仅为兼容已有文档链接。

## 目的

Globex 是可 Docker Compose 部署的跨境商品检索 Agent 演示。订单能力仅用于项目自建虚构商品和数据的**受控模拟**，不应描述为真实电商交易系统。

## 已支持

- 多国目标市场商品检索、筛选、Agent 对话与模拟到手价展示；
- SQLite 持久化的项目自建虚构商品目录和固定演示订单；
- `US`、`EU`、`GB`、`JP`、`CN` 的版本化静态模拟运费/进口税费规则；
- `POST /commerce/order-quotes`：无副作用报价，展示商品小计、模拟运费、模拟进口税费、规则版本与免责声明；
- `POST /commerce/orders`：在前端明确操作后创建受控模拟订单，要求 `Idempotency-Key`，且不收集真实地址；
- 聊天 Agent 的目录推荐卡可打开“模拟订单草案”：先走无副作用报价，只有用户点击确认才调用创建接口；Agent 没有订单写工具或控制令牌；
- `POST /commerce/orders/{order_id}/cancellations`：仅运行时创建且处于 `CONFIRMED` 的模拟订单、且持创建响应一次性返回的控制令牌时可取消；
- `DELETE /commerce/orders/{order_id}`：同一控制令牌可逻辑删除 `CONFIRMED` 或 `CANCELLED` 的运行时订单；公开读取隐藏已删除订单，订单行和幂等审计不物理删除；
- `GET /commerce/orders?limit=1..50` 与 `GET /commerce/orders/{order_id}`：脱敏列表和详情（不含已逻辑删除订单）；
- Docker Compose 中 React 静态站点 + Nginx 同源代理：入口为 `http://localhost:8080`，`/api/*` 转 FastAPI，`/ws/*` 转 WebSocket。

## 数据、隐私与安全边界

- 商品、品牌、订单、历史种子中的买家名称、电话和地址均为**项目自建虚构演示数据**；不来自第三方平台、用户或供应商。
- 新建模拟订单**不接收或存储实际收件人、电话、邮编、州/城市或完整地址**，只接收目的市场代码。
- 公开订单 API、WebSocket 事件、Agent 工具结果和错误响应不返回买家 ID、地址、电话、邮编、控制令牌摘要或取消原因。
- 创建响应中的 `order_control_token` 是一次性 Demo capability token：只允许返回一次，数据库仅保存不可逆摘要；前端只在当前组件内存保留，不能写入 URL、localStorage、事件流或日志。
- 所有费用均是版本化静态规则的模拟估算，不是税务、报关、物流或最终费用承诺。

## 明确不支持

以下能力不属于 MVP：

- 真实下单、真实用户认证、地址簿、付款、支付回调、退款、扣款或发票；
- 履约、发货、物流追踪、售后、消息发送；
- 库存预占、库存扣减、库存回补、库存承诺或真实可售量判断；
- 运行时调用搜索引擎、税务机关、物流商、支付平台或任何外部交易服务；
- Agent 工具创建或取消订单。Agent 仍只可查询脱敏订单。

## 运行

```bash
# 配置写在项目根目录 .env（参见 .env.example），它是 app/worker 的权威来源
docker compose -f docker/docker-compose.yaml up -d --build
# 打开 http://localhost:8080
```

本地前端开发可运行 `npm run dev`；Vite 会把 `/api` 与 `/ws` 分别代理到本机 `8000` 端口。

## 未来演进前提

若要进入任何真实交易能力，必须另行设计并实施真实认证与授权、账户归属、地址与隐私合规、支付/退款状态机、库存预占、并发与幂等控制、支付回调验证、履约、审计日志、保留/删除策略和正式税务/物流集成。不得把当前模拟控制令牌、静态费用规则或历史领域对象直接复用为真实交易实现。
