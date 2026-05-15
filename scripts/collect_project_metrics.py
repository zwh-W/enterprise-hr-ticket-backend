"""Collect final project validation metrics.

这个脚本用于第五阶段项目验收。

它不会修改数据库，只读取当前 PostgreSQL 中的真实数据，
输出一份 JSON 报告，证明项目的核心表、核心链路、核心状态都已经跑通。

运行方式：

    docker compose exec api python scripts/collect_project_metrics.py

输出文件：

    reports/project_metrics.json

建议先运行 smoke 脚本，再运行本脚本，这样数据库中会有完整演示数据。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


REPORT_DIR = Path("reports")
REPORT_FILE = REPORT_DIR / "project_metrics.json"


TABLES = [
    "users",
    "tickets",
    "audit_logs",
    "idempotency_keys",
    "pending_action_executions",
    "agent_tool_calls",
    "ticket_policy_references",
    "ticket_status_transitions",
]


def json_default(value: Any) -> str:
    """Convert datetime/date objects to JSON strings."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def fetch_all(db: Session, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run raw SQL and return rows as dictionaries."""
    result = db.execute(text(sql), params or {})
    return [dict(row._mapping) for row in result.fetchall()]


def fetch_one(db: Session, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Run raw SQL and return one row as dictionary."""
    result = db.execute(text(sql), params or {})
    row = result.fetchone()
    return dict(row._mapping) if row else None


def table_exists(db: Session, table_name: str) -> bool:
    """Check whether a table exists in public schema."""
    row = fetch_one(
        db,
        """
        select exists (
            select 1
            from information_schema.tables
            where table_schema = 'public'
              and table_name = :table_name
        ) as exists
        """,
        {"table_name": table_name},
    )
    return bool(row and row["exists"])


def count_table(db: Session, table_name: str) -> int:
    """Count rows in a table."""
    if not table_exists(db, table_name):
        return 0
    row = fetch_one(db, f"select count(*) as count from {table_name}")
    return int(row["count"]) if row else 0


def build_report(db: Session) -> dict[str, Any]:
    """Build final project metrics report from PostgreSQL."""
    existing_tables = [table for table in TABLES if table_exists(db, table)]

    report: dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "database_tables": {
            table: {
                "exists": table in existing_tables,
                "row_count": count_table(db, table),
            }
            for table in TABLES
        },
        "ticket_status_distribution": [],
        "ticket_type_distribution": [],
        "audit_action_distribution": [],
        "idempotency_status_distribution": [],
        "pending_action_execution_status_distribution": [],
        "agent_tool_call_status_distribution": [],
        "transition_distribution": [],
        "latest_tickets": [],
        "latest_idempotency_records": [],
        "latest_agent_tool_calls": [],
        "latest_pending_action_executions": [],
        "latest_policy_references": [],
        "latest_status_transitions": [],
        "acceptance_signals": {},
    }

    if table_exists(db, "tickets"):
        report["ticket_status_distribution"] = fetch_all(
            db,
            """
            select cast(status as text) as status, count(*) as count
            from tickets
            group by cast(status as text)
            order by count desc
            """,
        )

        report["ticket_type_distribution"] = fetch_all(
            db,
            """
            select cast(ticket_type as text) as ticket_type, count(*) as count
            from tickets
            group by cast(ticket_type as text)
            order by count desc
            """,
        )

        report["latest_tickets"] = fetch_all(
            db,
            """
            select
                id::text,
                ticket_no,
                cast(ticket_type as text) as ticket_type,
                title,
                cast(status as text) as status,
                cast(priority as text) as priority,
                external_session_id,
                pending_action_id,
                idempotency_key,
                created_by_external,
                created_at
            from tickets
            order by created_at desc
            limit 10
            """,
        )

    if table_exists(db, "audit_logs"):
        report["audit_action_distribution"] = fetch_all(
            db,
            """
            select action, resource_type, count(*) as count
            from audit_logs
            group by action, resource_type
            order by count desc
            """,
        )

    if table_exists(db, "idempotency_keys"):
        report["idempotency_status_distribution"] = fetch_all(
            db,
            """
            select cast(status as text) as status, count(*) as count
            from idempotency_keys
            group by cast(status as text)
            order by count desc
            """,
        )

        report["latest_idempotency_records"] = fetch_all(
            db,
            """
            select
                id::text,
                "key" as idempotency_key,
                cast(status as text) as status,
                resource_type,
                resource_id,
                created_at
            from idempotency_keys
            order by created_at desc
            limit 10
            """,
        )

    if table_exists(db, "pending_action_executions"):
        report["pending_action_execution_status_distribution"] = fetch_all(
            db,
            """
            select cast(status as text) as status, count(*) as count
            from pending_action_executions
            group by cast(status as text)
            order by count desc
            """,
        )

        report["latest_pending_action_executions"] = fetch_all(
            db,
            """
            select
                id::text,
                external_session_id,
                pending_action_id,
                idempotency_key,
                action_type,
                cast(status as text) as status,
                result_resource_type,
                result_resource_id,
                error_code,
                error_message,
                created_at
            from pending_action_executions
            order by created_at desc
            limit 10
            """,
        )

    if table_exists(db, "agent_tool_calls"):
        report["agent_tool_call_status_distribution"] = fetch_all(
            db,
            """
            select cast(status as text) as status, count(*) as count
            from agent_tool_calls
            group by cast(status as text)
            order by count desc
            """,
        )

        report["latest_agent_tool_calls"] = fetch_all(
            db,
            """
            select
                id::text,
                trace_id,
                tool_call_id,
                external_session_id,
                pending_action_id,
                tool_name,
                cast(status as text) as status,
                error_code,
                error_message,
                latency_ms,
                created_at
            from agent_tool_calls
            order by created_at desc
            limit 10
            """,
        )

    if table_exists(db, "ticket_policy_references"):
        report["latest_policy_references"] = fetch_all(
            db,
            """
            select
                id::text,
                ticket_id::text,
                external_session_id,
                pending_action_id,
                rag_query,
                document_id,
                document_name,
                chunk_id,
                breadcrumb,
                page_number,
                retrieval_score,
                created_at
            from ticket_policy_references
            order by created_at desc
            limit 10
            """,
        )

    if table_exists(db, "ticket_status_transitions"):
        report["transition_distribution"] = fetch_all(
            db,
            """
            select
                cast(from_status as text) as from_status,
                cast(to_status as text) as to_status,
                operator_role,
                count(*) as count
            from ticket_status_transitions
            group by cast(from_status as text), cast(to_status as text), operator_role
            order by count desc
            """,
        )

        report["latest_status_transitions"] = fetch_all(
            db,
            """
            select
                id::text,
                ticket_id::text,
                cast(from_status as text) as from_status,
                cast(to_status as text) as to_status,
                operator_id::text,
                operator_role,
                reason,
                created_at
            from ticket_status_transitions
            order by created_at desc
            limit 10
            """,
        )

    # Acceptance signals summarize whether the important project capabilities have data evidence.
    report["acceptance_signals"] = {
        "has_users": count_table(db, "users") > 0,
        "has_tickets": count_table(db, "tickets") > 0,
        "has_audit_logs": count_table(db, "audit_logs") > 0,
        "has_idempotency_records": count_table(db, "idempotency_keys") > 0,
        "has_pending_action_executions": count_table(db, "pending_action_executions") > 0,
        "has_agent_tool_calls": count_table(db, "agent_tool_calls") > 0,
        "has_rag_policy_references": count_table(db, "ticket_policy_references") > 0,
        "has_status_transitions": count_table(db, "ticket_status_transitions") > 0,
    }

    return report


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        report = build_report(db)
        REPORT_FILE.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=json_default),
            encoding="utf-8",
        )

        print("=" * 80)
        print("Project metrics collected")
        print("=" * 80)
        print(f"Output file: {REPORT_FILE}")
        print()
        print("Acceptance signals:")
        for key, value in report["acceptance_signals"].items():
            print(f"- {key}: {value}")
        print()
        print("Table row counts:")
        for table, info in report["database_tables"].items():
            print(f"- {table}: exists={info['exists']}, rows={info['row_count']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()