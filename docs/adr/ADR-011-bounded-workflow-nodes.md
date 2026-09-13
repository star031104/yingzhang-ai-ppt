# ADR-011: Bounded, schema-validated workflow nodes

Accepted.

## Context

Durable jobs and page-level rendering make execution recoverable, but a long handler is still difficult to reason about unless its boundaries, retry behavior, and outputs are explicit. Generic agent loops are not permitted to decide evidence, rendering, or delivery policy without deterministic gates.

## Decision

Project background jobs execute through `BoundedWorkflowRunner`. Every `NodeContract` declares:

- a stable node name;
- Pydantic input and output models;
- a deterministic SHA-256 idempotency key derived from canonical input;
- maximum attempts and an explicit retryable-exception allowlist;
- expected and produced artifact paths;
- a bounded handler with no implicit recursive agent loop.

Node transitions are persisted under `checkpoint.nodes`. A completed node with the same idempotency key reuses its validated output after process recovery. Failed business validation is never retried unless its exception type is explicitly declared.

The generated-deck graph is:

```text
source_ready → evidence_gate → render_candidates → visual_gate
             → targeted_repair → assemble → delivery_gate
```

Outline and representative-sample jobs use the same contracts around `plan` and `render_sample`. Whole-deck generation relies on page-level failure isolation instead of retrying the entire deck. Representative-sample engine failures may be retried once because that node is small and safely replayable.

## Consequences

- Checkpoints explain exactly which contract ran, with which attempt and artifacts.
- Recovery can skip completed deterministic nodes.
- Retry policy becomes reviewable rather than hidden in exception handlers.
- Future workflow engines may implement the same contracts, but are not required for local execution.
