# -*- coding: utf-8 -*-
"""AgentScope RAG 的 OpenAI-compatible embedding 适配器。

部分网关在同一个 OpenAI `/embeddings` 请求带多条 input 时，响应会只给第一项赋值，
其余项返回 ``None``。AgentScope KnowledgeBase 需要每个 chunk 都有 ``list[float]``，
因此这里将 RAG 模型的单批大小固定为 1；基类仍负责重试和把多个批次合并为
``EmbeddingResponse``，不改变 AgentScope 的公共协议。
"""
from __future__ import annotations

from agentscope.embedding import OpenAIEmbeddingModel


class RagCompatibleOpenAIEmbeddingModel(OpenAIEmbeddingModel):
    """对多输入响应不完整的 OpenAI-compatible embedding 网关使用单条批次。"""

    _TEXT_BATCH_SIZE = 1
