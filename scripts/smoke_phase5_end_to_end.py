"""Phase 5 end-to-end smoke script.

运行方式：
    docker compose exec api python scripts/smoke_phase5_end_to_end.py

它会通过真实 HTTP 接口验证核心演示链路：
1. health check
2. Agent Internal API 创建 ticket
3. HR 登录
4. 查看 agent trace / pending action execution / policy evidence
5. HR 执行状态流转 open -> processing -> resolved -> closed
6. 查看 transition records

这个脚本不是 pytest，而是面试演示 / 本地联调用的 smoke test。
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "change-me-internal-api-key")
PASSWORD = "Password123!"


def print_step(title: str, response: httpx.Response | None = None) -> None:
    print("\n" + "=" * 90)
    print(title)
    if response is not None:
        print("STATUS:", response.status_code)
        try:
            print("BODY:", response.json())
        except Exception:
            print("BODY:", response.text)


def ensure_user(client: httpx.Client, *, email: str, username: str, role: str) -> None:
    response = client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": PASSWORD, "role": role},
    )
    # 201: created. 409: already exists. Both are acceptable for smoke script.
    if response.status_code not in {201, 409}:
        raise RuntimeError(f"failed to ensure user {email}: {response.status_code} {response.text}")


def login(client: httpx.Client, *, email: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def build_internal_payload(unique: str) -> dict[str, Any]:
    return {
        "external_session_id": f"session-smoke-{unique}",
        "pending_action_id": f"pa-smoke-{unique}",
        "idempotency_key": f"agent:pa-smoke-{unique}:create_ticket",
        "trace_id": f"trace-smoke-{unique}",
        "tool_call_id": f"tool-call-smoke-{unique}",
        "tool_name": "create_hr_ticket",
        "ticket_type": "leave_request",
        "title": "Smoke 年假申请",
        "description": "这是第五阶段 smoke 脚本创建的 Agent-driven HR 工单。",
        "priority": "normal",
        "created_by_external": f"agent:session-smoke-{unique}",
        "confirmed_by_external": "user:smoke-employee",
        "confirmed_at": "2026-05-13T10:30:00Z",
        "rag_answer_snapshot": "根据员工年假管理制度，员工申请年假应提前提交申请。",
        "rag_references": [
            {
                "rag_query": "员工年假申请规则",
                "document_id": "doc-smoke-annual-leave",
                "document_name": "员工年假管理制度.pdf",
                "chunk_id": "chunk-smoke-001",
                "breadcrumb": "第二章 > 第三条",
                "page_number": 4,
                "retrieval_score": 0.87,
                "content_snapshot": "员工申请年假应提前提交申请，并经 HR 审核。",
            }
        ],
        "agent_trace": {
            "agent_type": "function_calling",
            "steps": [
                {"type": "tool_call", "tool_name": "rag_search", "output_summary": "命中年假制度"},
                {"type": "pending_action", "action_type": "create_hr_ticket", "requires_confirmation": True},
            ],
        },
    }


def main() -> None:
    unique = uuid.uuid4().hex[:8]
    hr_email = f"smoke_hr_{unique}@example.com"

    with httpx.Client(base_url=BASE_URL, timeout=15.0) as client:
        health = client.get("/health")
        print_step("1. Health check", health)
        health.raise_for_status()

        ensure_user(client, email=hr_email, username=f"smoke_hr_{unique}", role="hr")
        hr_headers = login(client, email=hr_email)
        print_step("2. HR user ready")

        payload = build_internal_payload(unique)
        created = client.post(
            "/internal/tickets",
            headers={"X-Internal-API-Key": INTERNAL_API_KEY},
            json=payload,
        )
        print_step("3. Agent Internal API creates ticket", created)
        created.raise_for_status()
        ticket_id = created.json()["id"]

        replayed = client.post(
            "/internal/tickets",
            headers={"X-Internal-API-Key": INTERNAL_API_KEY},
            json=payload,
        )
        print_step("4. Same idempotency_key replays existing ticket", replayed)
        replayed.raise_for_status()

        tool_calls = client.get("/agent-tool-calls", headers=hr_headers)
        print_step("5. HR views agent tool calls", tool_calls)
        tool_calls.raise_for_status()

        executions = client.get("/pending-action-executions", headers=hr_headers)
        print_step("6. HR views pending action executions", executions)
        executions.raise_for_status()

        references = client.get(f"/tickets/{ticket_id}/policy-references", headers=hr_headers)
        print_step("7. HR views RAG policy references", references)
        references.raise_for_status()

        for to_status, reason in [
            ("processing", "HR 开始处理 smoke 工单"),
            ("resolved", "HR 已完成处理"),
            ("closed", "工单已关闭"),
        ]:
            response = client.patch(
                f"/tickets/{ticket_id}/status",
                headers=hr_headers,
                json={"status": to_status, "reason": reason},
            )
            print_step(f"8. HR transitions ticket to {to_status}", response)
            response.raise_for_status()

        transitions = client.get(f"/tickets/{ticket_id}/transitions", headers=hr_headers)
        print_step("9. HR views ticket transitions", transitions)
        transitions.raise_for_status()

    print("\nSmoke flow completed successfully.")


if __name__ == "__main__":
    main()
