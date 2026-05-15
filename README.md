# Agent-driven HR Workflow Backend

这是一个面向企业内部 Agent 场景的 HR 业务执行后端。

它不是普通工单 CRUD 项目，而是承接 Agent 在 Human-in-the-loop 用户确认后的真实业务写操作，通过 Internal API 幂等创建 HR 工单，并记录 Agent tool call trace、pending_action 执行状态、RAG 制度依据、业务审计日志和工单状态流转。

## 1. 三项目整体定位

```text
RAG Service
  企业制度文档解析、混合检索、重排、引用溯源、RAGAS 评估

Agent Service
  意图识别、Function Calling、RAG 工具调用、PendingAction、Human-in-the-loop

Backend Service
  用户确认后的真实业务执行、幂等、审计、trace、evidence、状态机
```

完整链路：

```text
User request
-> Agent intent recognition
-> RAG policy search
-> Agent creates PendingAction
-> User confirms
-> Agent calls Backend Internal API
-> Backend idempotency check
-> Backend creates ticket
-> Backend persists trace / evidence / audit
-> HR processes ticket lifecycle
```

## 2. 技术栈

```text
Python 3.11
FastAPI
SQLAlchemy 2.0
Alembic
PostgreSQL
Redis
Pydantic v2
pydantic-settings
JWT
passlib[bcrypt]
pytest
httpx
Docker Compose
```

## 3. 五阶段功能

### Phase 1：基础后端

- FastAPI 分层结构
- User / Ticket / AuditLog
- JWT 登录鉴权
- RBAC
- 工单创建和查询
- Internal API
- pytest
- Docker Compose

### Phase 2：Internal API 幂等

- `pending_action_id`
- `idempotency_key`
- `request_hash`
- 同 key 同 payload 返回已有 ticket
- 同 key 不同 payload 返回 409 conflict

### Phase 3：Agent Trace + RAG Evidence

- `pending_action_executions`
- `agent_tool_calls`
- `ticket_policy_references`
- replayed / conflict trace
- RAG sources 依据快照

### Phase 4：状态机 + 工单生命周期

- `ticket_status_transitions`
- `open -> processing -> resolved -> closed`
- `open -> cancelled`
- HR/admin/employee 权限控制
- 状态变化和 audit 同事务提交

### Phase 5：联调契约 + 项目包装

- Agent/RAG -> Backend contract mapper
- Agent backend adapter 示例
- End-to-end smoke script
- Contract tests
- 架构说明和面试问答

## 4. 项目结构

```text
app/
  api/routers/              HTTP 路由
  core/                     配置、安全、异常、权限
  db/                       SQLAlchemy Base / Session
  integrations/             Agent/RAG 到 Backend 的契约映射
  models/                   ORM 模型
  repositories/             数据访问层
  schemas/                  Pydantic 请求/响应模型
  services/                 业务逻辑层

tests/                      pytest
scripts/                    debug / smoke 脚本
docs/                       学习顺序、架构说明、面试问答
examples/                   Agent 联调示例
alembic/                    数据库迁移
```

## 5. 启动

复制环境变量：

```bash
cp .env.example .env
```

启动服务：

```bash
docker compose up -d
```

查看日志：

```bash
docker compose logs -f api
```

访问：

```text
http://localhost:8000/docs
```

## 6. 数据库迁移

生成迁移：

```bash
docker compose exec api alembic revision --autogenerate -m "your migration message"
```

执行迁移：

```bash
docker compose exec api alembic upgrade head
```

查看表：

```bash
docker compose exec postgres psql -U postgres -d enterprise_hr_ticket -c "\dt"
```

## 7. 测试

全部测试：

```bash
docker compose exec api pytest -q
```

第五阶段 contract 测试：

```bash
docker compose exec api pytest -v tests/test_phase5_contract.py
```

## 8. Smoke 演示

运行完整后端演示链路：

```bash
docker compose exec api python scripts/smoke_phase5_end_to_end.py
```

它会验证：

```text
health check
Internal API 创建 ticket
幂等 replay
查询 agent tool calls
查询 pending action executions
查询 RAG policy references
HR 状态流转 open -> processing -> resolved -> closed
查询 transitions
```

## 9. Internal API 示例

```http
POST /internal/tickets
X-Internal-API-Key: <internal_api_key>
```

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
  "rag_answer_snapshot": "根据员工年假管理制度，员工申请年假应提前提交申请。",
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
  ]
}
```

## 10. 状态机

合法状态流转：

```text
open -> processing
processing -> resolved
resolved -> closed
open -> cancelled
```

权限规则：

```text
employee：可以取消自己的 open 工单，可以关闭自己的 resolved 工单
hr：可以处理、解决、关闭工单，可以分配 assignee
admin：可以执行所有合法流转
```

## 11. Agent 联调代码

契约 mapper：

```text
app/integrations/agent_contract.py
```

Agent 客户端示例：

```text
examples/agent_backend_adapter.py
```

标准 payload 样例：

```text
examples/sample_agent_payload.json
examples/sample_internal_ticket_request.json
```

## 12. 面试表达

一句话：

> 我做了一个企业 HR AI 应用闭环。RAG 负责制度知识检索和来源溯源，Agent 负责意图识别、工具调用、PendingAction 和 Human-in-the-loop，Backend 负责用户确认后的真实业务执行，通过 Internal API 幂等创建工单，并记录 Agent trace、RAG evidence、audit log 和状态流转，保证 AI 自动化业务动作可靠、可追踪、可解释。
