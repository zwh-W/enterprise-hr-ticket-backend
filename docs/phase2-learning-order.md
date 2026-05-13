# Phase 2 Learning Order: Internal API Idempotency

## 1. 先看 schema

- `app/schemas/ticket.py`
- 重点看 `InternalTicketCreate`
- 理解 `pending_action_id` 与 `idempotency_key` 的区别

## 2. 再看 model

- `app/models/idempotency.py`
- `app/models/ticket.py`
- 理解 `idempotency_keys` 表和 `tickets.idempotency_key`

## 3. 再看 repository

- `app/repositories/idempotency_repo.py`
- `app/repositories/ticket_repo.py`
- 重点看 `get_by_key()`、`create_processing()`、`mark_succeeded()`

## 4. 最后看 service

- `app/services/ticket_service.py`
- 重点看 `create_ticket_from_internal()`

## 5. 跑测试

```bash
docker compose exec api pytest -v tests/test_internal.py
```

## 6. 跑直接函数调用 debug

```bash
docker compose exec api python scripts/debug_direct_phase2_flow.py
```

## 7. 数据流

```text
InternalTicketCreate
→ TicketService.create_ticket_from_internal
→ IdempotencyRepository.get_by_key
→ IdempotencyRepository.create_processing
→ TicketRepository.create
→ AuditRepository.create
→ IdempotencyRepository.mark_succeeded
→ db.commit
```
