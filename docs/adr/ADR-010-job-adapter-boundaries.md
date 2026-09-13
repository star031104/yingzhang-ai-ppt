# ADR-010: Replaceable job store, executor, and event bus

Accepted.

## Context

The durable job manager originally owned four concerns at once: SQLite persistence, workflow reconstruction, `asyncio.Task` lifecycle, and WebSocket/SSE fan-out. That implementation was appropriate for a local product, but replacing any one part required modifying orchestration semantics.

## Decision

Keep `JobManager` as the stable orchestration facade and inject three contracts:

- `JobStore`: reads, lists, and saves complete durable job snapshots;
- `JobExecutor`: submits reconstructed workflow coroutines;
- `EventBus`: handles best-effort live WebSocket/SSE fan-out and bounded subscribers.

The default local composition is `SQLiteJobStore + AsyncioJobExecutor + InMemoryEventBus`. Durable snapshots remain authoritative; event delivery is an optimization. Every published event is enriched with the current complete snapshot, so SSE, WebSocket, and polling clients share one payload shape.

The deck generation core receives only a page-progress callback and a cancellation predicate. It does not know which queue, database, or event transport executes the workflow.

## Consequences

- PostgreSQL, ARQ/Redis, and Redis Streams adapters can be added without changing route or generation semantics.
- Local development and tests retain zero external infrastructure.
- In-memory live events are intentionally not durable; reconnecting clients read `JobStore` first.
- Distributed adapters must preserve full-snapshot saves, cooperative cancellation, bounded fan-out, and snapshot-first reconnect behavior.
