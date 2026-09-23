# -*- coding: utf-8 -*-
"""permissions

MVP Agent 运行时不注册订单创建或取消工具。受控模拟交易仅由显式 HTTP 页面流程触发；
权限层只为计划、调度和偏好维护工具追加精确 allow 规则。

不用 BYPASS/DONT_ASK 全局模式：保持权限引擎生效，未来接入 Bash/文件类危险工具时仍受默认策略保护。
"""
from __future__ import annotations

from agentscope.agent import Agent
from agentscope.permission import PermissionBehavior, PermissionRule

# MVP 不注册订单写工具；仅放行计划、调度和偏好写入工具。
_AUTO_ALLOWED_TOOLS = (
    "task_dispatch",
    "remember_preference_tool",
    # 撤回偏好与记住偏好对称：买家已在对话里明确说“以后不用避开塑料了”，
    # 再弹一次工具层确认卡是重复询问；且误删风险由精确匹配兜底
    "forget_preference_tool",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "TaskGet",
)


def allow_business_tools(agent: Agent) -> Agent:
    """给 Agent 的权限上下文追加业务工具 allow 规则（幂等，兼容恢复的持久化状态）。"""
    allow_rules = agent.state.permission_context.allow_rules
    for tool_name in _AUTO_ALLOWED_TOOLS:
        rules = allow_rules.setdefault(tool_name, [])
        if any(rule.source == "projectSettings" for rule in rules):
            continue
        rules.append(
            PermissionRule(
                tool_name=tool_name,
                rule_content=None,
                behavior=PermissionBehavior.ALLOW,
                source="projectSettings",
            ),
        )
    return agent
