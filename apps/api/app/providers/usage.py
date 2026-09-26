"""Small, privacy-preserving token usage ledger for project generation."""

from contextvars import ContextVar

from sqlalchemy.exc import SQLAlchemyError

usage_project_id: ContextVar[str | None] = ContextVar("model_usage_project_id", default=None)


def record_model_usage(
    project_id: str | None,
    model_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
    request_count: int,
    usage_requests: int,
) -> None:
    """Persist provider-reported counts only; never capture prompts or responses."""
    if not project_id or request_count < 1:
        return
    try:
        from app.db.models import ModelUsageRecord
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            db.add(ModelUsageRecord(
                project_id=project_id,
                model_id=model_id[:240],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                request_count=request_count,
                usage_requests=usage_requests,
                unreported_requests=max(0, request_count - usage_requests),
            ))
            db.commit()
    except SQLAlchemyError:
        # Observability must never turn a successful generation into a failure.
        return
