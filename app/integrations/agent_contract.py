"""Agent/RAG -> Backend contract mapper.

第五阶段的目标不是继续增加业务表，而是把三项目联调所需的“接口契约”固定下来。

这个文件提供一层轻量 adapter：
- Agent 项目产生 PendingAction。
- RAG 项目返回 answer + sources。
- 用户确认后，Agent 得到 ConfirmResult。
- 本 mapper 把这些结构转换成 Backend 的 InternalTicketCreate。

这样做的好处：
1. Backend 的 /internal/tickets 请求体保持稳定。
2. Agent 项目的内部字段名可以变化，只要 adapter 做映射即可。
3. 面试或演示时可以清晰展示三项目数据如何流动。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.ticket import TicketPriority, TicketType
from app.schemas.agent_trace import RagReferenceCreate
from app.schemas.ticket import InternalTicketCreate


class AgentPendingAction(BaseModel):
    """Agent 项目中的待确认动作抽象。

    真实 Agent 项目里的 PendingAction 可能字段更多，例如 status、expires_at、raw_message 等。
    这里保留联调 Backend 必需的最小字段。
    """

    pending_action_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    action_type: str = Field(default="create_hr_ticket", max_length=100)
    tool_name: str = Field(default="create_hr_ticket", max_length=100)
    arguments: dict[str, Any]

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, value: str) -> str:
        """第五阶段只支持创建 HR 工单这一种 action。"""
        if value != "create_hr_ticket":
            raise ValueError("Only create_hr_ticket pending action is supported by this mapper.")
        return value


class AgentConfirmResult(BaseModel):
    """Agent /v1/confirm 后的确认结果抽象。"""

    confirmed: bool = True
    confirmed_by: str | None = Field(default=None, max_length=128)
    confirmed_at: datetime | None = None

    def effective_confirmed_at(self) -> datetime | None:
        """如果用户确认了但没有传时间，后端 adapter 生成一个 UTC 时间。"""
        if not self.confirmed:
            return None
        return self.confirmed_at or datetime.now(timezone.utc)


class AgentRagSource(BaseModel):
    """RAG 项目返回的一条 source 抽象。

    字段命名兼容常见 RAG 输出：doc/document、chunk、breadcrumb、score、content。
    真正接入你的 RAG 项目时，只要在 adapter 层映射真实字段即可。
    """

    document_id: str | None = None
    document_name: str | None = None
    chunk_id: str | None = None
    breadcrumb: str | None = None
    page_number: int | None = None
    score: float | None = None
    content: str | None = None
    query: str | None = None

    def to_backend_reference(self, *, fallback_query: str | None = None) -> RagReferenceCreate:
        """把 RAG source 转成 Backend 的 RagReferenceCreate。"""
        return RagReferenceCreate(
            rag_query=self.query or fallback_query,
            document_id=self.document_id,
            document_name=self.document_name,
            chunk_id=self.chunk_id,
            breadcrumb=self.breadcrumb,
            page_number=self.page_number,
            retrieval_score=self.score,
            content_snapshot=self.content,
        )


class AgentRagResult(BaseModel):
    """RAG 工具返回结果抽象。"""

    query: str | None = None
    answer: str | None = None
    sources: list[AgentRagSource] = Field(default_factory=list)


class AgentTraceContext(BaseModel):
    """Agent 工具调用链路上下文。

    trace_id：一整条 Agent 会话 / 调用链路。
    tool_call_id：本次 create_hr_ticket 工具调用。
    agent_trace：可选的精简 ReAct / Function Calling trace 摘要。
    """

    trace_id: str | None = None
    tool_call_id: str | None = None
    agent_trace: dict[str, Any] | None = None


class BackendTicketPayloadBuilder:
    """把 Agent/RAG 侧结构转换为 Backend Internal API 请求体。"""

    @staticmethod
    def build_internal_ticket_payload(
        *,
        pending_action: AgentPendingAction,
        confirm_result: AgentConfirmResult,
        rag_result: AgentRagResult | None = None,
        trace_context: AgentTraceContext | None = None,
    ) -> InternalTicketCreate:
        """构造 InternalTicketCreate。

        这个方法是三项目联调时的核心 mapper：
        Agent PendingAction + ConfirmResult + RAG Result -> Backend /internal/tickets payload。
        """
        if not confirm_result.confirmed:
            raise ValueError("Cannot build backend ticket payload from an unconfirmed action.")

        args = pending_action.arguments
        ticket_type = args.get("ticket_type")
        title = args.get("title")
        description = args.get("description")
        priority = args.get("priority", TicketPriority.normal.value)

        missing = [name for name, value in {
            "ticket_type": ticket_type,
            "title": title,
            "description": description,
        }.items() if not value]
        if missing:
            raise ValueError(f"PendingAction arguments missing required fields: {', '.join(missing)}")

        rag_references = []
        if rag_result:
            rag_references = [
                source.to_backend_reference(fallback_query=rag_result.query)
                for source in rag_result.sources
            ]

        trace_context = trace_context or AgentTraceContext()

        return InternalTicketCreate(
            external_session_id=pending_action.session_id,
            pending_action_id=pending_action.pending_action_id,
            idempotency_key=BackendTicketPayloadBuilder.build_idempotency_key(pending_action),
            trace_id=trace_context.trace_id,
            tool_call_id=trace_context.tool_call_id,
            tool_name=pending_action.tool_name,
            ticket_type=TicketType(ticket_type),
            title=title,
            description=description,
            priority=TicketPriority(priority),
            created_by_external=f"agent:{pending_action.session_id}",
            confirmed_by_external=confirm_result.confirmed_by,
            confirmed_at=confirm_result.effective_confirmed_at(),
            rag_answer_snapshot=rag_result.answer if rag_result else None,
            rag_references=rag_references,
            agent_trace=trace_context.agent_trace,
        )

    @staticmethod
    def build_idempotency_key(pending_action: AgentPendingAction) -> str:
        """基于 pending_action_id 生成稳定幂等键。"""
        return f"agent:{pending_action.pending_action_id}:create_ticket"
