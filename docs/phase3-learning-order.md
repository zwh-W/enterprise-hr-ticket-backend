# Phase 3 Learning Order: Agent Trace + RAG Evidence

第三阶段不是普通 CRUD 扩展，而是把 Agent / RAG 项目的上下文落到业务后端。

## 1. 先看三张新表

- `pending_action_executions`：记录 pending_action 后端执行结果。
- `agent_tool_calls`：记录 Agent 工具调用请求、响应、状态和耗时。
- `ticket_policy_references`：记录工单创建依据的 RAG sources 快照。

## 2. 再看 InternalTicketCreate

重点字段：

- `trace_id`
- `tool_call_id`
- `tool_name`
- `confirmed_by_external`
- `confirmed_at`
- `rag_answer_snapshot`
- `rag_references`
- `agent_trace`

这些字段用于把 Agent 决策、用户确认、RAG 依据、后端执行串起来。

## 3. 重点看 TicketService.create_ticket_from_internal

你要重点 debug 三种路径：

1. 首次请求：创建 ticket + 写 trace/evidence/audit/idempotency。
2. 重复请求：不创建新 ticket，记录 replayed。
3. 冲突请求：返回 409，记录 conflict。

## 4. 最后看查询接口

- `GET /agent-tool-calls`
- `GET /pending-action-executions`
- `GET /pending-action-executions/{pending_action_id}`
- `GET /tickets/{ticket_id}/policy-references`

这些接口用于验证和展示 Agent 执行链路。

## 5. 需要掌握的问题

- audit log 和 agent tool call log 有什么区别？
- pending_action_execution 和 idempotency_key 有什么区别？
- RAG evidence 为什么要落库？
- 失败调用和重复调用为什么也要记录？
- 为什么工具调用日志不能替代业务审计日志？
