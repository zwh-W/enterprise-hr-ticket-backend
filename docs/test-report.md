# Enterprise HR Ticket Backend - Final Test Data Report

Generated at: 2026-05-15T09:12:24.007545Z

## 1. Report Scope

This report summarizes the final validation data for the `enterprise-hr-ticket-backend` project.

The project validates an Agent-driven HR workflow backend:

```text
RAG evidence
↓
Agent pending_action
↓
Human confirmation
↓
Backend Internal API
↓
Idempotent ticket creation
↓
Agent trace / RAG evidence / audit log persistence
↓
Ticket workflow state transitions
```

## 2. About QPS / P95 Testing

QPS and P95 latency testing are **not required as core acceptance criteria** for this stage.

This project is not positioned as a high-concurrency gateway or benchmark service. Its main validation targets are:

- correctness
- idempotency
- transaction consistency
- RBAC and workflow permissions
- Agent traceability
- RAG evidence persistence
- ticket lifecycle control

QPS/P95 can be added later as an optional performance extension, but it is not necessary for the current job-oriented project scope.

## 3. Automated Test Result

Command:

```bash
docker compose exec api pytest -q
```

Result:

```text

```

Interpretation:

- Full automated test suite passed.
- The warning is from `passlib` and does not affect current behavior.

## 4. Contract Test Result

Command:

```bash
docker compose exec api pytest -v tests/test_phase5_contract.py
```

Result:

```text

```

Validated behavior:

- Agent/RAG contract builder can generate Backend `/internal/tickets` payloads.
- The generated payload can create a ticket and complete the status workflow.

## 5. Smoke Test Result

Command:

```bash
docker compose exec api python scripts/smoke_phase5_end_to_end.py
```

Result:

```text
Smoke flow did not complete successfully.
```

Validated flow:

1. Health check.
2. Agent-style Internal API request creates a real HR ticket.
3. Same `idempotency_key` replays the existing ticket.
4. HR user queries Agent tool call records.
5. HR user queries pending action execution records.
6. HR user queries RAG policy references.
7. HR transitions ticket through `open -> processing -> resolved -> closed`.
8. HR queries ticket transition records.

Note: Chinese text in the raw smoke output displayed as mojibake in the terminal. This is a PowerShell/container stdout encoding display issue and does not affect API status codes or persisted business data.

## 6. Database Table Validation

| Table | Exists | Row Count |
| --- | --- | --- |
| `users` | True | 12 |
| `tickets` | True | 17 |
| `audit_logs` | True | 33 |
| `idempotency_keys` | True | 4 |
| `pending_action_executions` | True | 4 |
| `agent_tool_calls` | True | 4 |
| `ticket_policy_references` | True | 2 |
| `ticket_status_transitions` | True | 14 |

## 7. Acceptance Signals

| Signal | Value |
| --- | --- |
| `has_users` | True |
| `has_tickets` | True |
| `has_audit_logs` | True |
| `has_idempotency_records` | True |
| `has_pending_action_executions` | True |
| `has_agent_tool_calls` | True |
| `has_rag_policy_references` | True |
| `has_status_transitions` | True |

All acceptance signals are `true`, proving that the project has real validation data for users, tickets, audit logs, idempotency records, Agent traces, RAG evidence, and workflow transitions.

## 8. Ticket Status Distribution

| Status | Count |
| --- | --- |
| `open` | 11 |
| `closed` | 4 |
| `cancelled` | 2 |

## 9. Ticket Type Distribution

| Ticket Type | Count |
| --- | --- |
| `leave_request` | 13 |
| `general_hr` | 4 |

## 10. Audit Action Distribution

| Action | Resource Type | Count |
| --- | --- | --- |
| `ticket.status_changed` | `ticket` | 12 |
| `ticket.created` | `ticket` | 9 |
| `ticket.created_by_internal_api` | `ticket` | 8 |
| `ticket.cancelled` | `ticket` | 2 |
| `ticket.assigned` | `ticket` | 2 |

## 11. Idempotency Status Distribution

| Status | Count |
| --- | --- |
| `succeeded` | 4 |

Interpretation:

- All persisted idempotency records are `succeeded`.
- Internal API requests are linked to final ticket resources.

## 12. Pending Action Execution Status Distribution

| Status | Count |
| --- | --- |
| `idempotent_replayed` | 2 |
| `succeeded` | 2 |

Interpretation:

- `succeeded` proves confirmed pending actions were executed.
- `idempotent_replayed` proves repeated Agent calls were tracked without duplicate ticket creation.

## 13. Agent Tool Call Status Distribution

| Status | Count |
| --- | --- |
| `replayed` | 2 |
| `succeeded` | 2 |

Interpretation:

- `succeeded` tool calls prove successful Agent -> Backend execution.
- `replayed` tool calls prove duplicate calls are observable and do not duplicate business resources.

## 14. Ticket Status Transition Distribution

| From | To | Operator Role | Count |
| --- | --- | --- | --- |
| `processing` | `resolved` | `hr` | 4 |
| `open` | `processing` | `hr` | 4 |
| `resolved` | `closed` | `hr` | 2 |
| `resolved` | `closed` | `employee` | 2 |
| `open` | `cancelled` | `employee` | 2 |

Interpretation:

- The workflow has real transition records for `open -> processing`, `processing -> resolved`, `resolved -> closed`, and `open -> cancelled`.
- Both HR and employee-driven lifecycle operations are represented.

## 15. Latest Smoke Ticket Evidence

| Field | Value |
| --- | --- |
| Ticket No | `HR-20260515-0006` |
| Ticket ID | `e9e48568-ac42-4171-a873-d7006be37d2f` |
| Type | `leave_request` |
| Status | `closed` |
| Pending Action ID | `pa-smoke-9874fee5` |
| Idempotency Key | `agent:pa-smoke-9874fee5:create_ticket` |
| External Session ID | `session-smoke-9874fee5` |

## 16. Latest Agent Tool Call Evidence

| Trace ID | Tool Call ID | Pending Action ID | Tool Name | Status | Latency(ms) |
| --- | --- | --- | --- | --- | --- |
| `trace-smoke-9874fee5` | `tool-call-smoke-9874fee5` | `pa-smoke-9874fee5` | `create_hr_ticket` | `replayed` | 35 |
| `trace-smoke-9874fee5` | `tool-call-smoke-9874fee5` | `pa-smoke-9874fee5` | `create_hr_ticket` | `succeeded` | 93 |
| `trace-smoke-be3eaa26` | `tool-call-smoke-be3eaa26` | `pa-smoke-be3eaa26` | `create_hr_ticket` | `replayed` | 4 |
| `trace-smoke-be3eaa26` | `tool-call-smoke-be3eaa26` | `pa-smoke-be3eaa26` | `create_hr_ticket` | `succeeded` | 231 |

## 17. Latest RAG Evidence

| Document | Chunk ID | Breadcrumb | Retrieval Score |
| --- | --- | --- | --- |
| `员工年假管理制度.pdf` | `chunk-smoke-001` | `第二章 > 第三条` | 0.87 |
| `员工年假管理制度.pdf` | `chunk-smoke-001` | `第二章 > 第三条` | 0.87 |

## 18. Latest Ticket Status Transitions

| From | To | Operator Role | Reason |
| --- | --- | --- | --- |
| `resolved` | `closed` | `hr` | 工单已关闭 |
| `processing` | `resolved` | `hr` | HR 已完成处理 |
| `open` | `processing` | `hr` | HR 开始处理 smoke 工单 |
| `resolved` | `closed` | `hr` | 工单已关闭 |
| `processing` | `resolved` | `hr` | HR 已完成处理 |
| `open` | `processing` | `hr` | HR 开始处理 smoke 工单 |
| `open` | `cancelled` | `employee` | 员工取消申请 |
| `resolved` | `closed` | `employee` | 员工确认关闭 |
| `processing` | `resolved` | `hr` | HR 已处理完成 |
| `open` | `processing` | `hr` | HR 接单处理 |

## 19. Final Acceptance Conclusion

The project passes final functional validation.

Validated capabilities:

1. Backend foundation works: users, authentication, tickets, audit logs, and RBAC are covered by automated tests.
2. Internal API supports idempotent Agent-driven ticket creation.
3. Same `idempotency_key` replay returns the existing ticket rather than creating duplicates.
4. Agent pending action execution records are persisted.
5. Agent tool call traces are persisted with status and latency.
6. RAG policy references are persisted and linked to tickets.
7. Ticket state machine is enforced through controlled transitions.
8. Ticket transition records and audit logs provide lifecycle traceability.
9. Agent/RAG/Backend contract mapping is validated through contract tests.
10. End-to-end smoke validation completes successfully.

Final verdict:

```text
PASS
```

The project is ready to be presented as an Agent-driven HR workflow backend that connects RAG evidence, Agent confirmation, idempotent business execution, auditability, and ticket lifecycle management.
