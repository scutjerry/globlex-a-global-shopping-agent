# Embedding 与 Category Insight 知识库故障：问题、修复与验证

> 状态：已修复并在 Docker Compose 实例中验证  
> 适用版本：Globex MVP 当前工作区  
> 记录目的：说明商品向量索引和品类知识库在同一 embedding 网关下表现不同的原因，以及如何避免回归。

## 1. 摘要

Globex 的 embedding 网关配置修正后，商品向量索引已经可以正常写入 Qdrant；但 `category_insight` 品类知识库仍在启动时失败，并记录：

```text
1 validation error for VectorRecord
vector
```

故障不是 Qdrant 不可用、模型名称错误或 API Key 无效。实际根因是：当前 OpenAI-compatible embedding 网关在**单个请求包含多条 `input`** 时，只返回第一条向量；AgentScope 将缺失的后续向量表示为 `None`。知识库写入时，AgentScope 需要为每个文本块构造：

```python
VectorRecord(vector: list[float], document_id: str, chunk: Chunk)
```

当它处理 `vector=None` 时，Pydantic 的类型校验立即失败，导致整篇知识文档不入库。

修复后，RAG 知识库改用项目内的兼容 embedding 适配器，将每个 API 请求固定为一条文本。实际启动验证结果：

```text
品类知识库就绪：新增 5 篇，累计 5 篇
```

并且 Qdrant 中 `globex_category_kb` collection 已从 `0` 个点变为 **9 个分块向量点**，状态为 `green`。

---

## 2. 系统背景

项目存在两条独立但复用同一网关的 embedding 链路：

| 链路 | 用途 | 实现 |
|---|---|---|
| 商品索引 | 商品自然语言搜索、向量召回、rerank 前候选集 | `OpenAIEmbeddingClient` + `QdrantProductIndex` |
| 品类知识库 | `category_insight_tool` 的 RAG 洞察、选购规则和跨境通则 | AgentScope `KnowledgeBase` + `QdrantStore` |

对应 Qdrant collection：

```text
globex_products      商品向量
globex_category_kb   品类知识片段向量
```

商品目录中的 108 个虚构演示商品能够完成索引，不代表 AgentScope RAG 链路必然兼容；两条链路使用的客户端与批处理策略不同。

---

## 3. 故障现象

修正 `.env` 中的 embedding 配置后，日志表现为：

```text
POST .../embeddings -> HTTP/1.1 200 OK
向量索引就绪：108 个商品（dim=1024）
品类知识库建库失败，category_insight 将不可用：
1 validation error for VectorRecord
vector
```

这造成以下差异：

| 功能 | 故障前状态 |
|---|---|
| 商品 embedding 请求 | 成功，HTTP 200 |
| 商品向量索引 | 成功，108 个商品 |
| 商品向量搜索 | 可用 |
| 品类知识库 collection | 已创建但 points 为 0 |
| `category_insight_tool` | 不可用或无知识内容 |

因此仅观察 HTTP 200 或仅观察 `globex_products` 并不足以证明整个 RAG 系统可用。

---

## 4. 证据与根因

### 4.1 网关多输入响应不完整

在运行中的 `app` 容器中，以 AgentScope 的 `OpenAIEmbeddingModel` 请求三条文本，实测结果为：

```text
response = EmbeddingResponse
count = 3
item_types = ['list', 'NoneType', 'NoneType']
item_lens = [1024, None, None]
```

即：

```python
response.embeddings == [
    [0.012, -0.034, ...],  # 第 1 条：1024 维向量
    None,                  # 第 2 条缺失
    None,                  # 第 3 条缺失
]
```

接口仍返回 HTTP 200，所以普通 HTTP 状态检查不能识别该数据完整性问题。

### 4.2 AgentScope 的知识库契约

当前 AgentScope `KnowledgeBase.insert_document()` 会：

1. 将 Markdown 分块为多个 `Chunk`；
2. 一次调用 embedding 模型处理这些 chunks；
3. 遍历 `response.embeddings`；
4. 对每一块创建 `VectorRecord`；
5. 写入 `QdrantStore`。

核心逻辑等价于：

```python
records = [
    VectorRecord(vector=vector, document_id=document_id, chunk=chunk)
    for vector, chunk in zip(response.embeddings, chunks)
]
```

而 `VectorRecord` 的公开契约是：

```python
class VectorRecord(BaseModel):
    vector: list[float]
    document_id: str
    chunk: Chunk
```

当第二个或后续 chunk 获得 `None` 时，Pydantic 拒绝该记录，于是知识库灌库失败。

### 4.3 为什么商品索引没有失败

商品向量使用项目自有的 `OpenAIEmbeddingClient`：

- 按 `EMBEDDING_MAX_BATCH` 分片；
- 每批最多 10 条；
- 根据 OpenAI `data[].index` 排序回位；
- 输出强类型 `list[list[float]]`。

品类知识库则使用 AgentScope `OpenAIEmbeddingModel`，其默认单批大小为 2048，足以把一个知识文件的多个 chunks 放在同一请求中。当前网关无法正确提供多 input 对应的每一项 embedding，两个链路由此出现行为差异。

---

## 5. 修复方案

### 5.1 新增 RAG 兼容适配器

新增文件：

```text
app/infrastructure/embedding/rag_compatible_embedding_model.py
```

核心实现：

```python
class RagCompatibleOpenAIEmbeddingModel(OpenAIEmbeddingModel):
    _TEXT_BATCH_SIZE = 1
```

该类继承 AgentScope `OpenAIEmbeddingModel`，不复制 HTTP 调用、认证、重试、响应模型或缓存逻辑。只将 RAG 的单批最大文本数设为 `1`。

因此 AgentScope 基类仍会：

- 接收全部 chunk；
- 自动拆成单条批次；
- 调用原有 OpenAI-compatible embedding API；
- 将每一条确定有效的向量合并为 `EmbeddingResponse(embeddings=[...])`；
- 交给 `KnowledgeBase` 构造合法的 `VectorRecord`。

### 5.2 将适配器只应用到知识库

修改文件：

```text
app/infrastructure/rag/category_knowledge.py
```

知识库从：

```python
OpenAIEmbeddingModel(...)
```

改为：

```python
RagCompatibleOpenAIEmbeddingModel(...)
```

商品索引仍使用原有 `OpenAIEmbeddingClient`，避免改变商品搜索的既有批量性能和行为。

### 5.3 为什么不修改第三方库

未修改 `agentscope` 包源码，原因如下：

- `KnowledgeBase` 的 `EmbeddingResponse` / `VectorRecord` 契约是合理的；
- 故障来自上游网关多输入结果不完整；
- 本地子类是升级风险更低、边界更清晰的基础设施适配层；
- 未来网关恢复完整多输入支持时，只需提升该适配器的 batch size 或删除该适配器，不影响领域与应用层。

---

## 6. 验证记录

### 6.1 回归测试

执行：

```powershell
uv run pytest tests/test_phase3.py
```

结果：

```text
14 passed
```

新增测试确认：

```python
RagCompatibleOpenAIEmbeddingModel._TEXT_BATCH_SIZE == 1
```

### 6.2 Docker 运行时验证

使用项目根目录 `.env` 重建：

```powershell
docker compose --env-file ".env" -f docker/docker-compose.yaml `
  up -d --build --force-recreate app worker
```

运行时日志确认：

```text
POST .../embeddings -> HTTP/1.1 200 OK
向量索引就绪：108 个商品（dim=1024）
品类知识库就绪：新增 5 篇，累计 5 篇
```

Qdrant 实际状态：

```text
collection = globex_category_kb
status = green
points_count = 9
```

### 6.3 实际语义检索验证

在运行中的 `app` 容器内通过 `KnowledgeBase.search()` 查询：

```text
美国免税额度和旅行装备怎么选择
```

返回 `3` 条结果，最高分 `0.6193`。首条命中内容为“跨境选购通则 / 到手价的构成”，并包含到手价、国际运费、关税和目的国规则等相关信息；另外两条命中旅行装备避坑与数码配件跨境限制内容。这证明修复后不仅能够建库，向量也可被 Qdrant 正常检索并返回给 AgentScope。

已灌入的知识来源：

```text
cross-border-guide.md
travel-gear.md
home-living.md
digital-accessories.md
outdoor-sports.md
```

### 6.4 服务健康检查

```text
http://localhost:8080/healthz              -> 200
http://localhost:8080/api/health           -> 200
http://localhost:8080/api/commerce/orders  -> 200
```

---

## 7. 运行与排障手册

### 7.1 重建知识库

正常情况下，更新 `.env` 后可执行：

```powershell
cd "D:\文档\ChatGPT\globlex\globex-agent"
docker compose --env-file ".env" -f docker/docker-compose.yaml `
  up -d --build --force-recreate app worker
```

或者直接双击：

```text
start-all.cmd
```

知识库按文件名（不含扩展名）做幂等识别；已入库的文档不会重复写入。

### 7.2 查看知识库启动状态

```powershell
docker compose --env-file ".env" -f docker/docker-compose.yaml `
  logs --tail=200 app worker
```

成功标志：

```text
品类知识库就绪：新增 N 篇，累计 N 篇
```

失败标志：

```text
品类知识库建库失败
```

### 7.3 查询 Qdrant collection 状态

```powershell
Invoke-RestMethod http://localhost:6333/collections/globex_category_kb
Invoke-RestMethod http://localhost:6333/collections/globex_products
```

重点检查：

```text
status       应为 green
points_count 品类知识库应大于 0
```

---

## 8. 仍需注意的兼容性告警

运行日志仍会显示：

```text
Qdrant client version 1.19.0 is incompatible with server version 1.12.4
```

当前服务和两个 collection 均可正常运行；该告警不影响本次 embedding/RAG 修复。但它表示 Python 客户端与 Qdrant 服务端的 minor 版本跨度较大。

为了保护当前已经存在的 `qdrant-data` Docker volume，本次没有强制升级 Qdrant 服务端。后续若要消除该告警，应单独规划：

1. 导出或备份当前 Qdrant 数据；
2. 查阅目标 Qdrant 版本的存储兼容性说明；
3. 在测试环境完成 migration；
4. 再升级 Compose 的 Qdrant image；
5. 验证商品与知识库 collection 可读、可写、可搜索。

不建议直接将运行中的 `v1.12.4` 容器改为 `v1.19.0` 后复用旧卷；实际尝试表明旧卷会使较新服务端退出重启。

---

## 9. 结论

本次问题不是 embedding API 无法调用，而是网关的**多输入返回完整性不满足 OpenAI-compatible / AgentScope RAG 的预期**。通过在基础设施层把知识库 embedding 请求限制为单条输入，系统已恢复：

- 商品向量索引：108 条，1024 维；
- 品类知识文档：5 篇已入库；
- `category_insight` 可重新使用；
- 前端、订单中心、API 与 WebSocket 保持可用。
