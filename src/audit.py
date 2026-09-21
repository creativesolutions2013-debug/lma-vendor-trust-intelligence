import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.authz import Principal
from src.db import AuditLog


DEFAULT_DEDUPE_WINDOW_SECONDS = 5


def _serialize_details(
    details: Optional[dict[str, Any]],
) -> Optional[str]:
    if not details:
        return None

    return json.dumps(
        details,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def record_audit_event(
    session,
    *,
    principal: Principal,
    action: str,
    object_type: str,
    object_id: Optional[str] = None,
    vendor_id: Optional[int] = None,
    outcome: str = "success",
    details: Optional[dict[str, Any]] = None,
    dedupe_window_seconds: int = DEFAULT_DEDUPE_WINDOW_SECONDS,
) -> AuditLog:
    """
    Persist one audit event while suppressing immediate duplicate submissions.

    Events are considered duplicates when the same actor, action, target,
    outcome, and serialized details were recorded within the configured
    deduplication window.

    Set dedupe_window_seconds=0 to disable duplicate suppression for a
    specific event.
    """
    normalized_object_id = (
        str(object_id)
        if object_id is not None
        else None
    )
    serialized_details = _serialize_details(details)

    if dedupe_window_seconds > 0:
        cutoff = _utc_now_naive() - timedelta(
            seconds=dedupe_window_seconds
        )

        existing = (
            session.query(AuditLog)
            .filter(
                AuditLog.actor_subject == principal.subject,
                AuditLog.action == action,
                AuditLog.object_type == object_type,
                AuditLog.object_id == normalized_object_id,
                AuditLog.vendor_id == vendor_id,
                AuditLog.outcome == outcome,
                AuditLog.details_json == serialized_details,
                AuditLog.created_at >= cutoff,
            )
            .order_by(AuditLog.created_at.desc())
            .first()
        )

        if existing is not None:
            return existing

    event = AuditLog(
        actor_subject=principal.subject,
        actor_name=principal.display_name,
        actor_email=principal.email,
        actor_role=principal.role,
        action=action,
        object_type=object_type,
        object_id=normalized_object_id,
        vendor_id=vendor_id,
        outcome=outcome,
        details_json=serialized_details,
    )

    session.add(event)
    session.flush()

    return event
