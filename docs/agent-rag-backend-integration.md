# Agent / RAG / Backend 联调说明

## 三项目职责

```text
RAG Service
  负责企业制度文档解析、混合检索、重排、sources 溯源。

Agent Service
  负责理解用户意图、调用 RAG 工具、生成 PendingAction、等待用户确认。

Backend Service
  负责用户确认后的真实业务执行：幂等创建 ticket、保存 trace/evidence/audit、管理工单生命周期。
```

## 推荐联调流程

```text
1. 用户：我想申请 5 月 11 日到 13 日的年假。
2. Agent 识别出 create_hr_ticket 意图。
3. Agent 调用 RAG 工具查询年假制度。
4. RAG 返回 answer + sources。
5. Agent 生成 PendingAction，状态为 pending。
6. 用户确认 PendingAction。
7. Agent 调用 Backend POST /internal/tickets。
8. Backend 根据 idempotency_key 做幂等检查。
9. Backend 创建 ticket，并保存 pending_action_execution、agent_tool_call、ticket_policy_references、audit_log。
10. Backend 返回 ticket_no。
11. HR 后续把 ticket 从 open 流转到 processing / resolved / closed。
```

## Agent 侧最小改造

Agent 项目原来可能是：

```python
ticket_service.create_ticket(...)
```

联调后建议变成：

```python
HRBackendClient().create_ticket_from_confirmed_action(
    pending_action=pending_action_dict,
    confirm_result=confirm_result_dict,
    rag_result=rag_result_dict,
    trace_context=trace_context_dict,
)
```

参考文件：

```text
examples/agent_backend_adapter.py
```

## 字段映射

| Agent/RAG 字段 | Backend 字段 |
|---|---|
| session_id | external_session_id |
| pending_action_id | pending_action_id |
| pending_action_id | idempotency_key = agent:{id}:create_ticket |
| tool_call_id | tool_call_id |
| trace_id | trace_id |
| action arguments.ticket_type | ticket_type |
| action arguments.title | title |
| action arguments.description | description |
| confirm_result.confirmed_by | confirmed_by_external |
| confirm_result.confirmed_at | confirmed_at |
| rag_result.answer | rag_answer_snapshot |
| rag_result.sources | rag_references |

## 验证联调是否成功

Backend 创建 ticket 后，检查：

```bash
GET /agent-tool-calls
GET /pending-action-executions
GET /tickets/{ticket_id}/policy-references
GET /tickets/{ticket_id}/transitions
```

如果都能查到数据，说明三项目闭环成立。
