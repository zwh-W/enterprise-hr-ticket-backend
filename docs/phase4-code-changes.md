# Phase 4 Code Changes

## New files

- `app/models/ticket_transition.py`
- `app/repositories/ticket_transition_repo.py`
- `app/schemas/ticket_transition.py`
- `app/services/internal_ticket_service.py`
- `tests/test_ticket_status_flow.py`
- `scripts/debug_direct_phase4_flow.py`
- `docs/phase4-learning-order.md`
- `docs/phase4-code-changes.md`

## Modified files

- `app/models/__init__.py`
- `app/models/ticket.py`
- `app/api/routers/internal.py`
- `app/api/routers/tickets.py`
- `app/services/ticket_service.py`
- `README.md`
- `config.yaml`

## Main capability

Phase 4 adds a lightweight ticket state machine:

```text
open -> processing
processing -> resolved
resolved -> closed
open -> cancelled
```

Every status change writes:

- current `tickets.status`
- one `ticket_status_transitions` row
- one `audit_logs` row

These writes are committed together to avoid partial business state.
