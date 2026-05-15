# Phase 4 Learning Order: Ticket State Machine

第四阶段目标：让 Agent / 用户创建出来的真实工单进入一个可控生命周期，而不是任意修改 `status` 字段。

## 1. 先看状态机规则

文件：`app/services/ticket_service.py`

重点看：

- `ALLOWED_STATUS_TRANSITIONS`
- `_ensure_status_transition_allowed()`
- `_ensure_status_transition_permission()`
- `_ensure_cancel_permission()`

你要能解释：为什么状态不能随便改，为什么 closed / cancelled 是终态。

## 2. 看状态流转表

文件：`app/models/ticket_transition.py`

重点理解：

- `ticket_id`
- `from_status`
- `to_status`
- `operator_id`
- `operator_role`
- `reason`

这张表记录的是“状态怎么变来的”，不是当前状态。

## 3. 看 Repository

文件：`app/repositories/ticket_transition_repo.py`

Repository 只负责：

- 创建 transition record
- 查询某张 ticket 的 transition history

不要在 repository 里写权限判断。

## 4. 看 API

文件：`app/api/routers/tickets.py`

新增接口：

- `PATCH /tickets/{ticket_id}/status`
- `PATCH /tickets/{ticket_id}/assign`
- `POST /tickets/{ticket_id}/cancel`
- `GET /tickets/{ticket_id}/transitions`

Router 只接收请求、注入依赖、调用 service。

## 5. 看测试

文件：`tests/test_ticket_status_flow.py`

重点测试：

- HR 可以 open -> processing -> resolved
- employee 不能直接 resolved
- employee 可以取消自己的 open ticket
- cancelled ticket 不能再处理
- HR 可以分配 assignee

## 6. 直接调用 debug

运行：

```bash
docker compose exec api python scripts/debug_direct_phase4_flow.py
```

观察：

- ticket.status 怎么变化
- ticket_status_transitions 怎么写入
- audit_logs 怎么记录状态变化

## 7. 面试表达

第四阶段不是为了多写几个 PATCH 接口，而是为了说明：

> AI / Agent 创建出来的真实业务资源不能停留在“创建成功”这个点，后端还要管理它后续的业务生命周期。状态机和 transition record 能保证状态变化合法、可追踪、可审计。
