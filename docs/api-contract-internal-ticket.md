# Internal Ticket API Contract

## Endpoint

```http
POST /internal/tickets
X-Internal-API-Key: <internal_api_key>
Content-Type: application/json
```

这个接口只给 Agent 服务调用，不使用用户 JWT。

## Request

```json
{
  "external_session_id": "session_demo_001",
  "pending_action_id": "pa_demo_001",
  "idempotency_key": "agent:pa_demo_001:create_ticket",
  "trace_id": "trace_demo_001",
  "tool_call_id": "tool_call_demo_001",
  "tool_name": "create_hr_ticket",
  "ticket_type": "leave_request",
  "title": "年假申请：5月11日-13日",
  "description": "申请年假3天，时间为2026年5月11日至5月13日。",
  "priority": "normal",
  "created_by_external": "agent:session_demo_001",
  "confirmed_by_external": "user:employee_001",
  "confirmed_at": "2026-05-13T10:30:00Z",
  "rag_answer_snapshot": "根据员工年假管理制度，员工申请年假应提前提交申请，并经 HR 审核。",
  "rag_references": [
    {
      "rag_query": "员工年假申请规则",
      "document_id": "doc_annual_leave",
      "document_name": "员工年假管理制度.pdf",
      "chunk_id": "chunk_001",
      "breadcrumb": "第二章 > 第三条",
      "page_number": 4,
      "retrieval_score": 0.87,
      "content_snapshot": "员工申请年假应提前提交申请，并经 HR 审核。"
    }
  ],
  "agent_trace": {
    "agent_type": "function_calling",
    "llm": "qwen",
    "steps": [
      {"type": "tool_call", "tool_name": "rag_search", "output_summary": "命中年假制度"},
      {"type": "pending_action", "action_type": "create_hr_ticket", "requires_confirmation": true}
    ]
  }
}
```

## Required fields

```text
external_session_id
pending_action_id
idempotency_key
ticket_type
title
description
created_by_external
```

## Optional but recommended fields

```text
trace_id
tool_call_id
tool_name
confirmed_by_external
confirmed_at
rag_answer_snapshot
rag_references
agent_trace
```

## Response

```json
{
  "id": "ticket_uuid",
  "ticket_no": "HR-20260513-0001",
  "ticket_type": "leave_request",
  "title": "年假申请：5月11日-13日",
  "status": "open",
  "pending_action_id": "pa_demo_001",
  "idempotency_key": "agent:pa_demo_001:create_ticket"
}
```

## Idempotency behavior

| Case | Behavior |
|---|---|
| First request | Create ticket and persist idempotency / trace / evidence / audit |
| Same key + same payload | Return existing ticket; record replayed call |
| Same key + different payload | Return 409 conflict; record conflict call |

## Why this contract exists

Agent 调用后端时可能遇到超时、重试、重复确认。这个契约保证：

```text
同一个 pending_action 只创建一张真实 ticket。
RAG evidence 被保存为业务依据。
Agent tool call 被保存为可观测记录。
业务操作被 audit_log 记录。
```
