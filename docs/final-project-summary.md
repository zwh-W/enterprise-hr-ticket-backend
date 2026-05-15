# Final Project Summary

## 项目定位

本项目不是普通 HR 工单 CRUD，而是一个面向企业内部 Agent 场景的业务执行后端：

```text
Agent-driven HR Workflow Backend
```

它承接 Agent 在用户确认后的真实业务写操作，保证 AI 自动化动作可靠、可追踪、可解释、可审计。

## 三项目闭环

```text
RAG 项目
  企业制度文档解析、混合检索、重排、RAGAS 评估、sources 溯源

Agent 项目
  Function Calling、RAG 工具调用、PendingAction、Human-in-the-loop、ReAct Trace、自动化评测

Backend 项目
  Internal API、幂等、request_hash、Agent trace、RAG evidence、audit log、工单状态机
```

## 五阶段能力

### Phase 1：基础业务后端

- FastAPI 标准分层结构
- SQLAlchemy 2.0
- Alembic
- PostgreSQL
- JWT
- RBAC
- 工单创建和查询
- Internal API
- Audit log
- pytest / Docker Compose

### Phase 2：Internal API 幂等

- pending_action_id
- idempotency_key
- request_hash
- 重复请求不重复建单
- 同 key 不同 payload 返回 409

### Phase 3：Agent Trace + RAG Evidence

- pending_action_executions
- agent_tool_calls
- ticket_policy_references
- replayed / conflict trace
- RAG sources 依据快照

### Phase 4：状态机 + 工单生命周期

- ticket_status_transitions
- open -> processing -> resolved -> closed
- open -> cancelled
- HR / admin / employee 权限控制
- 状态变化和 audit 同事务提交

### Phase 5：联调契约 + 项目包装

- Agent/RAG -> Backend contract mapper
- Agent backend adapter 示例
- End-to-end smoke script
- Contract tests
- 架构说明和面试问答

## 核心技术点

```text
FastAPI
Pydantic v2
SQLAlchemy 2.0
Alembic
PostgreSQL
JWT / API Key
RBAC
Idempotency
Request Hash
Transaction
Audit Log
Agent Trace
RAG Evidence
State Machine
pytest
Docker Compose
```

## 面试一句话

> 我做了一个企业 HR AI 应用闭环。RAG 负责制度知识检索和来源溯源，Agent 负责意图识别、工具调用、PendingAction 和 Human-in-the-loop，Backend 负责用户确认后的真实业务执行，通过 Internal API 幂等创建工单，并记录 Agent trace、RAG evidence、audit log 和状态流转，保证 AI 自动化业务动作可靠、可追踪、可解释。
