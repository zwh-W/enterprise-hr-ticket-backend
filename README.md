# enterprise-hr-ticket-backend

企业级 HR 工单后台管理系统。第一阶段完成基础 FastAPI 后端骨架；第二阶段新增 Internal API 幂等机制，用于和 Agent pending_action 确认流程对接。

## 1. 当前能力

### Phase 1

- FastAPI 标准分层结构
- SQLAlchemy 2.0 ORM
- Alembic 迁移
- PostgreSQL / Redis / Docker Compose
- JWT 登录鉴权
- RBAC 基础权限
- 工单创建、列表、详情
- Internal API 创建工单
- 基础 audit log
- pytest 基础测试

### Phase 2

- `config.yaml` 非敏感默认配置
- `idempotency_keys` 幂等表
- `tickets.pending_action_id`
- `tickets.idempotency_key`
- Internal API 幂等创建工单
- 相同 `idempotency_key` + 相同请求体返回同一个 ticket
- 相同 `idempotency_key` + 不同请求体返回 409
- 第二阶段 pytest 覆盖
- 直接函数调用 debug 脚本

## 2. 启动服务

```bash
docker compose up -d
```

查看 API 日志：

```bash
docker compose logs -f api
```

访问文档：

```text
http://localhost:8000/docs
```

## 3. 第二阶段依赖变更

第二阶段新增 `PyYAML`，用于读取 `config.yaml`。
如果你的镜像里还没有该依赖，需要重建 api 镜像：

```bash
docker compose build api
docker compose up -d api
```

## 4. 数据库迁移

如果你已经完成第一阶段迁移，第二阶段修改了 model，需要重新生成一条迁移：

```bash
docker compose exec api alembic revision --autogenerate -m "add idempotency keys"
docker compose exec api alembic upgrade head
```

检查表：

```bash
docker compose exec postgres psql -U postgres -d enterprise_hr_ticket -c "\dt"
```

应包含：

- `users`
- `tickets`
- `audit_logs`
- `idempotency_keys`
- `alembic_version`

## 5. Internal API 请求示例

```http
POST /internal/tickets
X-Internal-API-Key: change-me-internal-api-key
Content-Type: application/json
```

```json
{
  "external_session_id": "test-session-ticket-001",
  "pending_action_id": "pa-test-001",
  "idempotency_key": "agent:pa-test-001:create_ticket",
  "ticket_type": "leave_request",
  "title": "年假申请：5月11日-13日",
  "description": "申请年假 3 天，时间为 2026 年 5 月 11 日至 5 月 13 日。",
  "created_by_external": "agent:test-session-ticket-001",
  "priority": "normal"
}
```

## 6. 跑测试

全部测试：

```bash
docker compose exec api pytest -q
```

只跑第二阶段 Internal API 测试：

```bash
docker compose exec api pytest -v tests/test_internal.py
```

## 7. 直接函数调用 debug

```bash
docker compose exec api python scripts/debug_direct_phase2_flow.py
```

这个脚本不走 HTTP，直接调用：

```text
InternalTicketCreate
→ TicketService.create_ticket_from_internal
→ IdempotencyRepository
→ TicketRepository
→ AuditRepository
→ DB
```

## 8. 配置优先级

```text
init 参数 > 环境变量 > .env > config.yaml > 类默认值
```

敏感信息不要放进 `config.yaml`，应放在 `.env` 或部署平台的环境变量中。
