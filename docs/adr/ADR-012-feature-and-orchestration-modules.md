# ADR-012: Incremental feature and orchestration module boundaries

Accepted.

## Context

The original backend workflow router and frontend application shell accumulated unrelated responsibilities. A single large rewrite would create unnecessary regression risk in generation, export, and editing behavior.

## Decision

Apply incremental extraction while preserving public routes and component behavior:

- move durable project-job orchestration into `workflows/project_jobs.py`;
- keep HTTP handlers responsible for validation and delegation only;
- centralize job snapshots, user-safe errors, and progress publication in `jobs/progress.py`;
- move complete frontend pages into `features/<domain>` modules;
- keep shared presentation components and metadata outside page implementations;
- require the full existing test suite after every extraction slice.

The first slice moves project workflow execution/recovery out of `workflow_routes.py`, moves model and skill pages out of `App.tsx`, and centralizes shared notice, empty-state, and skill metadata components. The second slice gives source ingestion a dedicated API/storage boundary and moves the complete creation experience into its own frontend feature. The third slice moves the project workspace into its own feature and gives slide versions, layout edits, revision conflicts, and rollback an ownership-checked API boundary. The final slice separates project workspace, asset/brand, editing, quality/evaluation, governance/publication, delivery/PowerPoint, and skill/reference APIs, leaving the workflow router as the composition root for generation only.

## Consequences

- Route and application-shell size decreases without changing APIs.
- Domain dependencies become explicit at service construction and component props.
- API domains can evolve and test independently while sharing explicit ownership and storage helpers.
- The remaining workflow module is intentionally the generation composition root, not a general-purpose HTTP monolith.
