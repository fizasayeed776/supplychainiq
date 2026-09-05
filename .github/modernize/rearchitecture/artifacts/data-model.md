# Data Model

## Entity Inventory
- `Workspace`: tenant/company; many-to-many users through `WorkspaceMembership`; owns procurement, workflow, chat and delivery records.
- `WorkspaceMembership`: workspace-user join with owner/admin/reviewer/viewer role.
- `Vendor`: workspace-scoped supplier with contacts, payment terms and risk analysis.
- `Contract`: workspace/vendor contract file, terms, validity dates and lifecycle status.
- `ScanRun`: workspace ingestion run with trigger, statistics and timing.
- `Document`: workspace file with source/type, SHA-256 content hash, OCR status, raw text, extraction and vendor.
- `LineItem`: document child with SKU, quantity, unit price, currency and computed total.
- `PurchaseOrder`, `Invoice`, `DeliveryReceipt`: one-to-one structured records linked to a document, workspace and vendor.
- `MatchResult`: one-to-one invoice match with optional PO/receipt, discrepancies, severity and review state.
- `ApprovalFlow`: one-to-one invoice FSM: draft, pending_review, approved, disputed, paid.
- `ApprovalStep`: ordered approval decision and escalation deadline belonging to a flow.
- `Dispute`: one-to-one match result with drafted email and send status.
- `TriageRule`: workspace rule for amount, vendor risk and required match status.
- `WebhookDelivery`: persisted outbound webhook attempt and response state.
- `Chunk`: document text segment with 1536-dimensional pgvector embedding.
- `ChatSession`: workspace/user chat container.
- `ChatMessage`: ordered user/assistant message with citations.

## Relationships
`Workspace` is the aggregate tenancy root. `Vendor` and `Contract` belong to it. `Document` optionally references `ScanRun` and `Vendor`; each structured document type is one-to-one with `Document`, while `LineItem` and `Chunk` are one-to-many children. `Invoice` has one `MatchResult` and one `ApprovalFlow`; `MatchResult` may have one `Dispute`. `ApprovalFlow` has many `ApprovalStep` records. `ChatSession` has many `ChatMessage` records.

## Schema Hints
All entities inherit UUID primary keys and timestamps from `TimeStampedModel`. Document idempotency is enforced by a unique `(workspace, content_hash)` constraint. Workspace/name and workspace/user uniqueness constraints exist for vendors and memberships. Match and workspace/status/severity indexes support review queries. Chunk positions are unique per document and embeddings have dimension 1536.

## Transaction and State Boundaries
The approval workflow uses `django-fsm` transitions. Document materialization and matching tasks mutate multiple related records as one application workflow; exact transaction decorators are not declared in the inspected model files. Celery tasks and Redis-backed caches/groups form asynchronous state boundaries.

## Key Entities
Workspace: tenancy and authorization boundary.
Document: raw input and extraction lifecycle.
Invoice: payable record driving matching and approvals.
MatchResult: three-way match verdict and discrepancy review state.
ApprovalFlow: invoice payment state machine.
Vendor: supplier identity and risk intelligence.
Chunk: searchable RAG retrieval unit.
ChatSession: user-facing procurement question context.
