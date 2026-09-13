# ADR-009: Durable job state and snapshot-first events

Accepted. SQLite is the source of truth for single-node job state. Every resumable generation job persists the workflow version and reconstruction payload before execution. The in-process executor may be replaced later, but clients consume a stable snapshot-first SSE protocol with polling fallback. Cancellation is cooperative at declared safe workflow boundaries. Page writes use optimistic revisions to reject stale clients.
