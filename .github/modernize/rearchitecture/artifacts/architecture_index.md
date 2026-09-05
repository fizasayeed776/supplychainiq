# Architecture Index

This index is not the full contract. Do not implement from this file alone; follow the artifact paths below.

## Global Artifacts
- `unit_graph.yaml`: unit boundaries, triggers, dependencies, dynamic entrypoints and shared references.
- `migration_boundary.yaml`: observation scope only; future implementation scope must use `must_rewrite`.
- `wire_contracts.yaml`: filter by `unit` for REST, WebSocket and Celery contracts.
- `shared_modules.yaml`: filter by `used_by_units`; use field lists as the allowed shared surface.
- `cross_unit_state.yaml`: filter flows where a unit is writer or reader; runtime-confirm unmatched flows.
- `seams.yaml`: filter `cut_between`; preserve frozen-side rules and bridge mappings.
- `project-structure.md`, `tech-stack.md`, `data-model.md`: global design evidence.

## Implementation Guide

Each unit below must read its three unit files plus matching rows in the global artifacts. Completion evidence should report `artifacts_read`, implemented `must_preserve` items, unresolved/deferred contracts, and tests/build/runtime evidence.

### Units

- `auth-api`: `units/auth-api/{behavior,bindings,unit_decomposition}.yaml`; trigger JWT token endpoints.
- `core-api`: `units/core-api/{behavior,bindings,unit_decomposition}.yaml`; trigger core CRUD APIs.
- `document-api`: `units/document-api/{behavior,bindings,unit_decomposition}.yaml`; trigger document APIs.
- `document-pipeline`: `units/document-pipeline/{behavior,bindings,unit_decomposition}.yaml`; trigger Celery ingestion/OCR/extraction/embedding tasks.
- `matching-pipeline`: `units/matching-pipeline/{behavior,bindings,unit_decomposition}.yaml`; trigger matching Celery tasks.
- `workflow-api`: `units/workflow-api/{behavior,bindings,unit_decomposition}.yaml`; trigger workflow CRUD and decisions.
- `workflow-automation`: `units/workflow-automation/{behavior,bindings,unit_decomposition}.yaml`; trigger approval, notification and scheduled workflow tasks.
- `chat-api`: `units/chat-api/{behavior,bindings,unit_decomposition}.yaml`; trigger chat session and RAG APIs.
- `realtime`: `units/realtime/{behavior,bindings,unit_decomposition}.yaml`; trigger authenticated WebSocket routes.
- `partner-webhook`: `units/partner-webhook/{behavior,bindings,unit_decomposition}.yaml`; trigger signed partner webhook.
- `vendor-risk`: `units/vendor-risk/{behavior,bindings,unit_decomposition}.yaml`; trigger vendor risk Celery tasks.
- `frontend-spa`: `units/frontend-spa/{behavior,bindings,unit_decomposition}.yaml`; trigger browser routes and page actions.

Global row filters: `wire_contracts.unit == unit`; `shared_modules.used_by_units` contains unit; `cross_unit_state.writer.unit == unit OR reader.unit == unit`; `seams.cut_between` contains unit. Candidate splits are advisory only because every decomposition file has `commit: false`.
