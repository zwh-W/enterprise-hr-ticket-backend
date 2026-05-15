"""Example adapter used by the Agent project.

这个文件演示 Agent 项目应该如何把 PendingAction / ConfirmResult / RAG Result
转换成后端 /internal/tickets 请求。它不是 FastAPI 路由，只是联调参考代码。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.integrations.agent_contract import (
    AgentConfirmResult,
    AgentPendingAction,
    AgentRagResult,
    AgentTraceContext,
    BackendTicketPayloadBuilder,
)


class HRBackendClient:
    """Agent 项目调用 HR Backend 的最小客户端。"""

    def __init__(self, *, base_url: str | None = None, internal_api_key: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("HR_BACKEND_BASE_URL") or "http://localhost:8000").rstrip("/")
        self.internal_api_key = internal_api_key or os.getenv("INTERNAL_API_KEY") or "change-me-internal-api-key"

    def create_ticket_from_confirmed_action(
        self,
        *,
        pending_action: dict[str, Any],
        confirm_result: dict[str, Any],
        rag_result: dict[str, Any] | None = None,
        trace_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Agent 用户确认 pending_action 后调用。

        真实 Agent 项目只需要在 /v1/confirm 成功后调用这个方法，
        它会负责构造 Backend 标准 payload 并发送 Internal API 请求。
        """
        payload = BackendTicketPayloadBuilder.build_internal_ticket_payload(
            pending_action=AgentPendingAction.model_validate(pending_action),
            confirm_result=AgentConfirmResult.model_validate(confirm_result),
            rag_result=AgentRagResult.model_validate(rag_result) if rag_result else None,
            trace_context=AgentTraceContext.model_validate(trace_context) if trace_context else None,
        )

        response = httpx.post(
            f"{self.base_url}/internal/tickets",
            headers={"X-Internal-API-Key": self.internal_api_key},
            json=payload.model_dump(mode="json"),
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()
