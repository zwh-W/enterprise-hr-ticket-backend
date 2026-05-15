# Phase 3 Code Changes

## 新增文件

```text
app/models/agent_trace.py
app/repositories/agent_trace_repo.py
app/schemas/agent_trace.py
app/services/agent_trace_service.py
app/api/routers/agent_trace.py
scripts/debug_direct_phase3_flow.py
docs/phase3-learning-order.md
docs/phase3-code-changes.md
tests/test_agent_trace.py
```

## 修改文件

```text
app/models/__init__.py
app/schemas/ticket.py
app/services/ticket_service.py
app/api/routers/tickets.py
app/main.py
README.md
```

## 核心变化

1. `InternalTicketCreate` 增加 Agent trace、用户确认信息、RAG evidence 字段。
2. `TicketService.create_ticket_from_internal()` 从“幂等创建 ticket”升级为“幂等创建 ticket + trace/evidence 落库”。
3. 新增 `pending_action_executions`，记录 pending_action 执行状态。
4. 新增 `agent_tool_calls`，记录 Agent 工具调用请求、响应、状态、耗时。
5. 新增 `ticket_policy_references`，记录工单创建依据的 RAG sources 快照。
6. 新增查询接口，便于调试和面试展示完整链路。
