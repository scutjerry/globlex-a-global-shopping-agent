# Globex 受控模拟订单与到手价估算 V1 设计

> 状态：**已按用户批准实施，并已在真实 Docker 栈上完成全量测试与端到端运行验证（见 9.4）**  
> 适用范围：现有 Docker 化 Globex MVP  
> 统一入口：`http://localhost:8080`  
> 不是法律、税务、报关、物流或支付意见；所有金额、规则、订单、商品和身份均为项目自建的虚构演示数据。

## 1. 文档目的与已确认决策

本文件将“严格只读模拟订单中心”变更为“受控模拟交易”的产品、数据、接口、隐私和实施约束一次性固定，供后续后端、前端、测试和部署改动共同遵守。

已经由用户确认的决定：

1. 订单中心不再严格只读；V1 允许创建和取消**模拟**订单。
2. 禁止接入真实支付、退款、履约、发货、物流、库存预占、库存扣减、库存回补或任何外部交易执行。
3. 订单到手价必须包含商品小计、模拟运费和模拟进口税费；费用使用可审计、版本化的静态规则，而不是订单创建时联网搜索。
4. 静态规则 V1 目的市场为 `US`、`EU`、`GB`、`JP`、`CN`；其他市场可以继续浏览商品，但不能创建费用规则缺失的模拟订单。
5. 公开订单响应仍不得返回 `buyer_id`、收件人姓名、电话、邮编、州/城市、完整地址、`shipping_address` 或 `cancel_reason`。

## 2. 产品目标、角色与非目标

### 2.1 产品目标

在不改变现有 FastAPI + SQLite + React/Vite + Nginx + Docker Compose MVP 架构的前提下，使用户可以：

- 以目录中的虚构 SKU 和数量创建一笔模拟订单；
- 在创建前看到固定规则计算出的商品、运费、关税/税费和模拟到手价；
- 在订单中心查看脱敏订单、冻结的费用拆分及规则版本；
- 使用创建响应一次性发放的控制令牌取消或逻辑删除自己刚创建的模拟订单；删除不会物理清除最小审计和幂等记录。

### 2.2 角色

| 角色 | 身份来源 | 可做操作 | 不可做操作 |
| --- | --- | --- | --- |
| 演示买家 | 当前浏览器本地生成的 `buyer_id` | 从 Agent 已验证的目录推荐打开草案、核价后确认创建；读取公共演示订单；持控制令牌取消或逻辑删除自己创建的模拟订单 | 访问真实交易、读隐私字段、无令牌取消/删除订单、写库存 |
| 公开订单中心访客 | 无认证上下文 | 查看脱敏订单列表和详情 | 读取控制令牌、买家或地址、取消或删除订单 |
| Agent | AgentScope 工具上下文 | 检索目录、推荐 SKU、查询脱敏订单；其结果可作为 UI 草案的入口 | 创建/确认/取消/删除订单、接收地址或控制令牌、调用外部结算 |

> 说明：当前 MVP 没有真实认证或账户系统，因此 `buyer_id` 不构成安全授权。创建/取消 API 使用随机、高熵、一次性返回且仅保存摘要的控制令牌，作为演示环境的能力令牌；这不是生产授权模型。

### 2.3 明确非目标（禁止能力）

- 真实用户、账号、地址簿、支付方式、支付回调、退款、税务申报、报关、物流、履约或售后；
- 商品库存预占、扣减、回补、可售量承诺或库存竞争处理；
- 创建时向搜索引擎、税务机关、物流商或支付服务发送任何订单数据；
- Agent 直接下单、直接取消或获取取消控制令牌；
- 将规则金额展示成保证报价、税单、进口申报或最终应付款。

## 3. V1 用户旅程与状态机

### 3.1 费用估算与创建旅程

前置条件：商品存在、SKU 存在、数量为 1..10、商品可寄往目的市场、目的市场属于 V1 费用规则覆盖范围。

1. 前端提交商品项、`destination_country` 和显示币种，请求报价；不传递收件人、电话或街道地址。
2. 服务端从目录重建 SKU 价格和类别，忽略客户端价格；将项目规则计算为 `subtotal + shipping + import_tax`。
3. 前端用返回报价展示费用拆分、规则版本、来源核验说明与“仅为模拟估算”提示。
4. 用户明确点击“创建模拟订单”后，前端以相同商品、目的地和显示币种请求创建。
5. 服务端再次独立计算报价，生成 `SIM-<12 位大写十六进制>` 订单、冻结金额/规则快照，状态为 `CONFIRMED`；不操作任何 SKU 库存。
6. 服务端仅在该创建响应中返回 `order_control_token`；前端仅放在组件内存中，不写入 `localStorage`、URL、事件流或日志。
7. 前端刷新订单中心，展示脱敏详情和费用明细。

### 3.1.1 聊天推荐草案（已实施）

1. Agent 仍仅调用 `product_search_tool` 等查询工具，返回本地目录已验证的商品卡；没有订单写工具。
2. 用户在推荐商品卡点击“创建模拟订单草案”。前端仅取目录卡的 `product_id`/`sku_id`，由用户选数量、目的市场和显示币种。
3. 草案组件调用同一个无副作用报价接口，服务端重新根据目录与静态规则校验/报价；不信任模型提供的价格、地址、令牌、买家或自由文本。
4. 用户可“取消草案”（只清 React 内存、零数据库写）或“确认创建模拟订单”（才调用创建接口）。成功后令牌仅留在 App 内存并进入订单中心。

失败情形：未知商品/SKU、超量、商品不支持该市场、市场无规则、币种不支持、重复项、无效目标市场均为 `422`；不会写任何订单。

### 3.2 取消旅程

1. 用户在当前页面对状态为 `CONFIRMED` 的新创建订单输入/持有控制令牌并明确点击“取消模拟订单”。
2. 服务端比对令牌的不可逆摘要，调用领域状态机 `CONFIRMED → CANCELLED`，写入取消时间和内部原因码 `buyer_requested`。
3. 响应只返回脱敏的订单详情；绝不返回或在事件流中发送取消原因、地址、买家标识或控制令牌。
4. 不进行退款、库存回补、消息发送、外部调用或其他副作用。

失败情形：订单不存在为 `404`；令牌不匹配为 `403`；种子订单或已经取消的订单为 `409`。失败不得泄露订单是否属于某一买家。

### 3.3 逻辑删除旅程（已实施）

1. 当前页面仍持创建时一次性控制令牌的用户，可对 `CONFIRMED` 或 `CANCELLED` 的 `USER_SIMULATION` 点击“删除此模拟订单”，并完成浏览器二次确认。
2. `DELETE /commerce/orders/{order_id}` 用单条条件更新比对订单种类、状态、`deleted_at is null` 和令牌摘要，写入 `DELETED` 与内部 `deleted_at`。
3. 成功返回 `204 No Content`；公开列表排除该记录，详情/取消/二次删除按不存在或不可执行处理。订单行和幂等键保留，绝不通过重试复活订单。
4. `DEMO-*` 种子订单不可删除；删除不退款、不回补库存、不发消息、不做外部调用。

### 3.4 订单状态机

```text
创建模拟订单 ──> CONFIRMED ──(控制令牌 + 显式取消)──> CANCELLED
                         │                                      │
                         └────(控制令牌 + 显式逻辑删除)──────────┘
                                                ↓
                                             DELETED（不公开）
```

- V1 不公开 `DRAFT`，也不实现支付、履约等状态。
- `CANCELLED` 不能恢复、再次取消或产生退款，但当前页仍持令牌时允许随后逻辑删除。
- `DELETED` 是不可逆内部终态，不会出现在公开 DTO、列表、详情、Agent 或 WebSocket 中。
- 内置 `DEMO-*` 种子订单保持可读，但为避免改写既有固定数据，不可取消或删除。
- 所有状态转换均记录最少审计元数据；订单中心公开 DTO 仅展示状态和时间。

## 4. 到手价与静态规则

### 4.1 统一计算口径

所有金额在目标显示币种中以 `Money` 最小单位保存和相加，避免浮点误差：

```text
商品小计 subtotal   = Σ (SKU 当前价格 × 数量)，再转为目标显示币种
模拟运费 shipping   = 目的市场首件基础运费 + 续件增量，再转为目标显示币种
应税基数 taxable    = subtotal + shipping（规则可定义是否包含运费）
模拟税费 import_tax = taxable 的适用部分 × 税率；规则可包含免税阈值
模拟到手价 total     = subtotal + shipping + import_tax
```

创建订单时，必须将 `subtotal`、`shipping`、`import_tax`、`total`、目的地、目标币种、规则集版本和规则来源 ID 一并冻结。商品后续调价、汇率规则变更或费用规则发布不能改变历史订单。

### 4.2 配置模型与来源可审计性

新增项目内版本化配置（建议 `app/domain/shipping/simulated_fee_rules.py` 或等效纯领域模块），每一条目的市场规则包含：

| 字段 | 含义 |
| --- | --- |
| `rule_set_version` | 例如 `simulated-fees-2026-01-v1`，订单冻结此值 |
| `destination_country` | `US` / `EU` / `GB` / `JP` / `CN` |
| `taxable_base` | `subtotal` 或 `subtotal_plus_shipping` |
| `import_tax_rate` | 演示税费率；不是产品 HS 归类或最终法定税率 |
| `duty_threshold_minor` | 用规则基准币种表示的免税/免关税阈值；若资料只支持结构性结论，不伪造精确阈值 |
| `base_shipping_minor` | 演示首件运费 |
| `additional_item_ratio` | 续件运费比例 |
| `source_id` | 对应下表的来源与核验记录 |
| `last_verified` | 人工核验日期（仅发布日期写入；不从运行时获取） |
| `assumption_note` | 与真实规则的差异、覆盖和排除项 |

`ShippingQuote`/公开报价 DTO 需新增：`import_tax_major`（或保留兼容名 `tariff_major` 并同时给出语义清楚的新字段）、`shipping_major`、`rule_set_version`、`estimate_disclaimer`、`source_summary`。所有页面都必须显示“模拟估算，不是税务、报关或最终费用”。

### 4.3 V1 市场资料与建模边界

下表是规则设计的资料目录，不将主管机关资料直接复制为商品最终税率。它们说明了阈值、税基或按品类变化等结构；具体 V1 数值须作为显式演示假设放入版本化规则。

| 市场 | 已核验的官方/权威资料 | 可用于 V1 的结构性结论 | V1 建模限制 |
| --- | --- | --- | --- |
| US | [U.S. Customs and Border Protection: Internet Purchases](https://www.cbp.gov/trade/basic-import-export/internet-purchases) | CBP 表明进口可能产生税费；其面向邮寄进口的说明提及一般低于 800 美元包裹的简化处理，但保留要求正式申报的权力。 | 不按真实 HS、原产地、配额或商品监管状态结算；所有商品只使用演示类别率。 |
| EU | [European Commission: Buying goods online from a non-EU country](https://taxation-customs.ec.europa.eu/customs/customs-procedures-import-and-export/importation/buying-goods-online-coming-non-european-union-country_en) | 非欧盟发货商品不论价值可能有进口 VAT；超过 €150 可能有关税；VAT 税基可包括海关价值、税费和运费。 | `EU` 是区域演示代码，并非成员国税务结算；不使用实际成员国 VAT 或 TARIC。 |
| GB | [GOV.UK: Tax and customs for goods sent from abroad](https://www.gov.uk/goods-sent-from-abroad/tax-and-duty) | 商品通常计 VAT；超过 £135 的非消费税商品可能有 Customs Duty；VAT 可基于货值、运费和关税。 | 不覆盖北爱尔兰、消费税货物或实际 UK Trade Tariff 分类。 |
| JP | [Japan Customs: Duty Rates for Major Products](https://www.customs.go.jp/english/c-answer_e/imtsukan/1204_e.htm) | 税率依物品、材质、加工和用途而变，资料明确要求仅供参考并建议使用最新税则。 | 不使用真实申报价格折减、消费税或具体归类；统一模拟规则必须标注假设。 |
| CN | 当前仓库已有跨境演示口径，但初始公开链接未成功核验。 | 仅保留 `CN` 作为明确的静态演示市场；不得将现有硬编码视为官方已核验税率。 | 在规则配置中标为 `source_status=assumption_pending_official_revalidation`，界面清楚显示“演示假设”。 |

核验结果只应由人工版本发布流程更新；不得在生产/API 请求期间爬取或搜索，也不得将用户地址、商品清单、订单号或买家标识发送至这些网站。

## 5. 数据模型蓝图

### 5.1 `Order` 聚合（修改）

保留：`order_id`、私有 `buyer_id`、内部地址载体、`lines`、`status`、创建/确认/取消时间。为无真实地址的 V1 创建流程，地址载体只存 `country`；其余字段使用非个人化占位值，或改为专用 `Destination` 值对象以避免伪造 PII。

新增/修改字段：

| 字段 | 类型 | 作用与敏感度 |
| --- | --- | --- |
| `order_kind` | `SEEDED_DEMO` / `USER_SIMULATION` | 区分固定种子和运行时创建订单；普通 |
| `is_cancellable` | 派生字段 | 仅 `USER_SIMULATION + CONFIRMED` 可取消；普通 |
| `pricing` | `OrderPricingSnapshot` | 冻结的费用和规则元数据；普通但不可修改 |
| `control_token_hash` | 可空字符串 | 只保存 SHA-256 摘要，用于演示能力令牌校验；敏感，永不公开 |
| `cancel_reason_code` | 可空固定枚举 | 仅 `buyer_requested`；替代自由文本，敏感且不公开 |

`Order.total_amount()` 改为返回 `pricing.landed_total`；保留 `merchandise_subtotal()` 用于订单行小计。`Order.place_simulation()` 必须在构造时进入 `CONFIRMED` 并要求完整定价快照。`Order.cancel_by_control_token()` 只执行状态变换，绝无库存操作。

### 5.2 `OrderPricingSnapshot`（新增值对象）

| 字段 | 类型 | 不变量 |
| --- | --- | --- |
| `merchandise_subtotal` | `Money` | 非负，币种与其余费用一致 |
| `shipping_amount` | `Money` | 非负，同币种 |
| `import_tax_amount` | `Money` | 非负，同币种 |
| `landed_total` | `Money` | 必须精确等于前三项之和 |
| `destination_country` | str | 仅五个 V1 市场 |
| `rule_set_version` | str | 非空、创建后不可变 |
| `source_ids` | tuple[str, ...] | 非空；只引用项目的静态来源目录 |
| `source_summary` | str | 创建时冻结的来源展示摘要，公开展示 |
| `source_status` | str | 创建时冻结的来源核验/假设状态，公开展示；例如 CN 的待官方复核状态 |
| `estimate_disclaimer` | str | 非空、公开展示 |

### 5.3 `OrderLine`（保持价格快照）

继续冻结 SKU 标题、SKU ID、单价、数量。V1 不保存库存快照、不锁库存；创建时仅验证 SKU 当前存在、数量 1..10、且 `destination_country in product.ships_to`。

### 5.4 SQLite 映射

现有 `orders` 表增加以下列（MVP 保持 `create_all`，但实现时要兼容已有 Docker volume：不能仅依赖 `create_all` 添加列）：

- `order_kind VARCHAR(24) NOT NULL DEFAULT 'SEEDED_DEMO'`
- `merchandise_subtotal_minor INTEGER NOT NULL DEFAULT 0`
- `shipping_amount_minor INTEGER NOT NULL DEFAULT 0`
- `import_tax_amount_minor INTEGER NOT NULL DEFAULT 0`
- `pricing_rule_set_version VARCHAR(64) NOT NULL DEFAULT 'legacy-seed-v1'`
- `pricing_source_ids_json JSON NOT NULL DEFAULT '[]'`（SQLite 实际 default 需按现有 SQLAlchemy/SQLite 能力确认）
- `control_token_hash VARCHAR(64) NULL`
- `cancel_reason_code VARCHAR(32) NULL`

约束/索引：

- `orders(order_kind, status, created_at DESC)` 用于订单中心；
- `control_token_hash` 不建公开可查询接口；实现可加普通索引以支持校验，但不在日志输出；
- 应用层保证金额币种一致、金额和等式、状态转换与种子订单不可取消。

由于已有 Docker volume，实施必须使用一个幂等的 SQLite schema-upgrade 函数（检查 `PRAGMA table_info(orders)` 后仅 `ALTER TABLE ADD COLUMN` 缺失列），并在集成测试中从旧 schema 实例验证升级。不得清空 `app-data` volume。

### 5.5 保留、删除与审计

- V1 不提供导出或物理删除 API。`DELETE /commerce/orders/{id}` 是令牌授权的**逻辑删除**：订单行、幂等键和最小删除审计仍保留在 SQLite demo volume 中，公开读取隐藏该订单；随 volume 的运维生命周期才可整体移除。
- 最小审计字段：创建/取消/删除时间、订单 ID、订单种类、状态、规则版本；不记录控制令牌明文、地址、买家 ID 或取消/删除自由文本。
- 日志中仅允许订单 ID、状态、目的市场、规则版本和错误码；禁止打印请求原文、token 或私有字段。

## 6. API 契约

所有路径由 Nginx 同源代理，经 `http://localhost:8080/api/*` 访问；FastAPI 实际路径不含 `/api`。

### 6.1 公开读取与报价

| Method | Path | 用途 | 结果 |
| --- | --- | --- | --- |
| `POST` | `/commerce/order-quotes` | 对商品项、目的市场和显示币种进行无副作用模拟报价 | `OrderQuoteResponse` |
| `GET` | `/commerce/orders?limit=1..50` | 脱敏订单摘要列表 | `OrderListResponse` |
| `GET` | `/commerce/orders/{order_id}` | 脱敏订单详情与冻结费用拆分 | `OrderDetailResponse` |

`POST /commerce/order-quotes` 请求：

```json
{
  "items": [{"product_id": "P1001", "sku_id": "P1001-S1", "quantity": 1}],
  "destination_country": "US",
  "currency": "USD"
}
```

响应必须包括：商品项、`merchandise_subtotal_major`、`shipping_amount_major`、`import_tax_amount_major`、`landed_total_major`、`currency`、`destination_country`、`rule_set_version`、`estimate_disclaimer`、`source_summary`。不得包含价格规则内部 URL 的未验证数据、买家数据或地址。

### 6.2 受控写接口

| Method | Path | 用途 | 授权/幂等 | 响应 |
| --- | --- | --- | --- | --- |
| `POST` | `/commerce/orders` | 明确创建一笔模拟订单 | 请求头 `Idempotency-Key`（UUID/随机串，24h 仅同一内容复用）；服务端生成控制令牌 | `CreatedSimulatedOrderResponse` |
| `POST` | `/commerce/orders/{order_id}/cancellations` | 取消一笔运行时模拟订单 | body 中的 `order_control_token` 只用于校验；不可记录 | `OrderDetailResponse` |
| `DELETE` | `/commerce/orders/{order_id}` | 逻辑删除 `CONFIRMED` 或 `CANCELLED` 的运行时模拟订单 | body 中的同一控制令牌；种子不可删；不物理删除 | `204 No Content` |

创建请求与报价请求相同，另含可选的非敏感 `client_reference`（最长 64 字，前端不需要传则不实现）。创建响应在 `OrderDetailResponse` 基础上仅增加：

```json
{
  "order_control_token": "仅此一次返回的随机控制令牌",
  "control_token_warning": "请在当前页面保存以取消该模拟订单；不会再次显示。"
}
```

取消请求：

```json
{"order_control_token": "创建响应中一次性返回的令牌"}
```

### 6.3 公共 DTO 禁返字段

在所有公开响应、WebSocket 事件和异常正文中，禁止出现：

```text
buyer_id, recipient_name, phone, postal_code, state, city, address_line,
shipping_address, control_token_hash, order_control_token（创建成功响应除外）, 
cancel_reason, cancel_reason_code
```

创建响应的 `order_control_token` 必须由专用 DTO 精准限制；不能被列表、详情、取消响应、Agent 工具或 WebSocket 事件复用。

### 6.4 错误与审计约定

- `422`: 输入验证、规则不支持、商品/SKU/数量/可寄送市场不合法；
- `404`: 订单不存在；
- `403`: 取消/删除控制令牌无效，分别使用固定通用消息，不泄露所有权或令牌比对细节；
- `409`: 种子订单、非 `CONFIRMED` 订单或重复取消；删除种子或不再可删订单也使用固定冲突消息；
- `204`: 控制令牌授权的逻辑删除成功，不回显订单或令牌；
- `409`: 同一个 `Idempotency-Key` 与不同请求内容冲突；
- `201`: 新建模拟订单；相同幂等请求返回已建订单和**不再重发明文控制令牌**，因此 UI 必须防重复提交；
- `503`: 容器尚未就绪。

## 7. 模块与运行时边界

- **领域层**：`Order`、`OrderPricingSnapshot`、静态 `SimulatedFeeSchedule`。不得依赖 FastAPI、数据库、搜索或 AgentScope。
- **应用层**：`QuoteSimulatedOrderUseCase`、`CreateSimulatedOrderUseCase`、`CancelSimulatedOrderUseCase`、`DeleteSimulatedOrderUseCase`。创建/取消/删除均不得调用 `ProductRepository.save()`，即不写库存。
- **基础设施层**：SQLite 订单快照持久化、固定规则来源目录、控制令牌的 CSPRNG 生成与 SHA-256 摘要、幂等请求记录（独立小表）、`deleted_at` 的幂等 schema 升级。
- **表现层**：Pydantic 请求/响应 DTO、HTTP 路由、React 订单中心与聊天草案卡。Agent 工具保持仅查询；聊天草案只消费 Agent 已验证的目录卡，报价和创建仍由用户 UI 明确触发。
- **运行时**：保持 `app` healthcheck，`worker`/`frontend` 等待 `app: service_healthy`。无需增加服务、消息队列消费者或第三方 SDK。

## 8. 隐私、安全与风险控制

### 8.1 数据分类

| 数据 | 分类 | 允许位置/流向 |
| --- | --- | --- |
| 商品、费用规则版本、目的市场、金额、公开订单号 | NORMAL | API、前端、测试、脱敏日志 |
| 内部 `buyer_id`、控制令牌摘要、取消原因码 | SENSITIVE | 订单持久化与最小审计；不得在公开 API/Agent/WS/日志展示 |
| 收件人、电话、邮编、完整地址 | HIGH_SENSITIVE | V1 创建流程根本不收集；历史种子中已有的虚构值仅内部持久化，绝不返回或传给模型/搜索 |
| API key / secret | HIGH_SENSITIVE | 仅 `.env`/运行时环境；不读回显、不写日志或文档 |

### 8.2 控制令牌安全

- 使用 `secrets.token_urlsafe(32)` 或等强 CSPRNG；库中仅保存 SHA-256 十六进制摘要。
- 明文 token 仅出现在创建的 HTTPS/本地开发响应中一次；不得进入浏览器持久存储、URL、事件总线、任务队列、异常、数据库或日志。
- 使用恒定时间摘要比对；令牌失败信息统一，避免枚举。
- 这是 Demo capability token，不代替认证、RBAC、CSRF、防重放或生产级账户安全。

### 8.3 外部资料边界

官方资料只用于离线人工整理的版本化演示规则。运行时不能联网检索、抓取、调用税务/物流/支付网站；不发送任何订单、商品、买家或地址数据到外部资料来源。

### 8.4 风险登记

| 风险 | 可能性 | 影响 | 缓解 | 阶段 |
| --- | --- | --- | --- | --- |
| 将模拟税率误认为真实报价 | 中 | 高 | 明显免责声明、规则版本/来源显示、禁止真实结算 | V1 |
| 重用旧用例导致库存被写 | 中 | 高 | 新用例不接受 product save；测试断言库存不变 | V1 |
| 令牌泄露或重放 | 低 | 中 | 仅摘要存储、一次返回、内存保存、取消后终态 | V1 |
| 公开接口泄露 PII | 中 | 高 | 专用 DTO、字段负面测试、禁止 WS/Agent 回传 | V1 |
| 已有 SQLite volume 缺列 | 高 | 中 | 幂等 schema upgrade 集成测试；不清卷 | V1 |
| EU/GB/JP/CN 规则不适用于实际商品/地区 | 高 | 高 | 静态演示规则、来源目录、只支持模拟、禁止真实交易 | V1 |

## 9. 测试与验收标准

### 9.1 单元与应用测试

- 订单报价等于 `merchandise + shipping + import_tax`，货币不混用，所有五个市场都可得到版本号和免责声明；
- `US`/`EU`/`GB`/`JP`/`CN` 规则来源状态与限制在公开摘要中可见，未覆盖市场拒绝创建；
- 创建确认订单后，任意 SKU 库存与创建前完全相同；取消后同样不变；
- 创建时冻结金额和规则版本；修改当前规则或 SKU 价格不能改变历史订单；
- 相同输入只接受一次幂等创建；不同 body 复用 key 为冲突；
- 仅有效 token 可取消运行时订单；种子订单、二次取消和无效 token 均失败且不泄露私有字段；
- 所有公开 DTO、返回 JSON、错误和 WS 事件的字段负面测试均不含 PII、token 或取消原因。

### 9.2 HTTP/前端测试

- `POST /commerce/order-quotes` 成功及五类 422 失败；
- `POST /commerce/orders` 返回 201、一次性 token 和完整费用拆分；
- `POST /commerce/orders/{id}/cancellations` 成功后列表/详情为 `CANCELLED`；
- 订单中心可以报价、确认创建、显示费用拆分和固定免责声明、取消当前页面订单；
- 订单中心永远不渲染地址、买家、电话、邮编、取消原因或 token（创建后的仅当前操作控件除外）；
- `npm run build` 成功。

### 9.3 Docker 运行验证

保持并实际验证：

```powershell
cmd.exe /c "start-all.cmd < nul"
docker compose --env-file ".env" -f docker/docker-compose.yaml ps
uv run pytest
cd frontend; npm run build
Invoke-WebRequest http://localhost:8080/healthz
Invoke-WebRequest http://localhost:8080/api/health
```

再以 `http://localhost:8080/api` 端到端验证：报价 → 创建 → 脱敏读取 → 使用一次性 token 取消 → 库存未变。验证过程不能在终端输出 `.env` 值或控制令牌明文；令牌可在进程内短暂用于测试，但不得写入项目文件或最终报告。

### 9.4 已完成的实际验证记录

以下结果来自真实执行，不是推断：

| 验证项 | 实际结果 |
|---|---|
| 后端全量测试 `uv run pytest -q` | **332 passed**（历史基线 301，本特性新增 31 项） |
| 前端生产构建 `npm run build` | **成功**：`tsc -b && vite build`，产物 `index-Ce951VUk.js` 155.86 kB / gzip 51.45 kB |
| Compose 重建 `up -d --build` | **成功**：`app`/`worker`/`frontend` 重建，`app` healthy，`database=sqlite`、`redis=ok` |
| 既有 volume 兼容升级 | **成功**：重建后 5 笔 `DEMO-*` 订单全部保留，且 `order_kind` 正确回填为 `SEEDED_DEMO`；未删库、未重建表 |
| 前端静态资源 | `http://localhost:8080/` 200；新 bundle 已被 Nginx 提供 |
| 端到端 API 链路 | **35/35 项检查全部通过** |

端到端实测要点（`CN` + `P1001-S1` × 2）：

- 报价三段合计一致：`390 + 运费 + 税 = 418.0`，`landed_total_major` 与三项之和精确相等；
- `POST /commerce/orders` 返回 `201`，`order_kind=USER_SIMULATION`、`status=CONFIRMED`，一次性 token 长度 43；
- 同 key 同 body 重放返回 `200`、同一 `order_id`、token 为空（不重发）；
- 同 key 不同 body 返回 `409`；
- 顶层与嵌套 PII 字段均返回 `422` 且响应体为固定 `{"detail":"请求格式无效"}`，未回显提交值，且未持久化任何订单（订单数不变）；
- 固定种子订单取消返回 `409` 且状态保持 `CONFIRMED`；
- 错误 token 返回 `403` 且不回显 token；
- 正确 token 取消返回 `200`、`status=CANCELLED`；二次取消返回 `409`；
- 取消后重新读取订单仍为 `CANCELLED`，且详情从未包含 token 明文；
- `CN` 的 `assumption_pending_official_revalidation` 在报价、创建、取消和 SQLite 回读全链路保留；
- 目录库存 `catalog_skus` 中 `P1001-S1` 创建+取消前后均为 `50`，**无任何库存副作用**。

验证结束后已按用户要求复位演示状态：事务删除全部 `USER_SIMULATION` 订单及其订单行与幂等键，使数据库回到 5 笔 `SEEDED_DEMO` 种子订单的干净基线（细节与快照路径见 `docs/agent-memory.md`）。因此上表中“订单数不变”等断言描述的是验证当时的状态，并非当前数据基线。

## 10. 实现准备度与顺序

实现仅在用户确认本设计后开始。建议顺序：

1. 以本设计替换旧只读范围文档、README 描述和测试标题；
2. 实现静态演示规则与费用快照值对象，先补领域测试；
3. 改造订单聚合和用例，确保没有库存副作用；
4. 实现可兼容既有 SQLite volume 的 schema upgrade、仓储和幂等记录；
5. 定义 DTO 与路由，先加入 PII/token 负面测试；
6. 更新 React 类型与订单中心的报价、创建、取消交互；
7. 执行后端、前端、Compose/API 运行验证；
8. 将最终已验证规则版本、验证命令和边界更新到 `docs/agent-memory.md`。

## 11. 实施前待确认项

本设计以用户已经选择的市场范围、静态可审计规则和受控模拟交易为基础。唯一实施门禁是：确认接受上述设计，尤其是以下安全取舍：

- V1 创建订单不收集实际地址，仅使用目的市场代码；
- V1 不做真实账户认证，取消必须持创建响应一次性返回的控制令牌；
- Agent 不获得任何创建或取消工具；
- `CN` 规则在再次完成官方核验前显式标作演示假设；
- 订单数据和规则仅是演示，永远不代表真实交易或税务结算。
