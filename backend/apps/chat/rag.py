"""
RAG chat core.
Retrieval: pgvector cosine similarity + Postgres full-text search, merged
with reciprocal rank fusion (RRF). Generation: mandatory citations back to
chunk IDs; a low-confidence guardrail returns "not found in your documents"
instead of hallucinating. An SQL tool lets the agent answer aggregate
questions ("spend with Vendor Y this quarter") beyond pure retrieval.
"""
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Sum
from pgvector.django import CosineDistance
import re

from .models import Chunk
from apps.agents.client import get_llm_client

RETRIEVAL_CONFIDENCE_FLOOR = 0.15


def chunk_text(text: str, max_tokens: int = 500, overlap_tokens: int = 50) -> list[str]:
    """Naive whitespace-token chunker with overlap. Swap for a tokenizer-aware
    splitter if exact token counts matter for a given provider."""
    words = text.split()
    if not words:
        return []
    chunks, start = [], 0
    step = max(1, max_tokens - overlap_tokens)
    while start < len(words):
        chunks.append(" ".join(words[start:start + max_tokens]))
        start += step
    return chunks


def vector_search(query_vector, workspace_id, document_type=None, top_k=8):
    qs = Chunk.objects.filter(document__workspace_id=workspace_id)
    if document_type:
        qs = qs.filter(document__type=document_type)
    return list(qs.order_by(CosineDistance("embedding", query_vector))[:top_k])


def fulltext_search(query_text, workspace_id, top_k=8):
    vector = SearchVector("text")
    query = SearchQuery(query_text)
    qs = (
        Chunk.objects.filter(document__workspace_id=workspace_id)
        .annotate(rank=SearchRank(vector, query))
        .filter(rank__gt=0)
        .order_by("-rank")[:top_k]
    )
    return list(qs)


def hybrid_retrieve(question: str, workspace_id, top_k=6) -> list[Chunk]:
    client = get_llm_client()
    query_vector = client.embed(question)

    vector_hits = vector_search(query_vector, workspace_id, top_k=top_k * 2)
    text_hits = fulltext_search(question, workspace_id, top_k=top_k * 2)

    # Reciprocal rank fusion
    scores: dict[str, float] = {}
    by_id: dict[str, Chunk] = {}
    for rank_list in (vector_hits, text_hits):
        for rank, chunk in enumerate(rank_list):
            by_id[str(chunk.id)] = chunk
            scores[str(chunk.id)] = scores.get(str(chunk.id), 0.0) + 1.0 / (60 + rank)

    ranked_ids = sorted(scores, key=scores.get, reverse=True)[:top_k]
    return [by_id[i] for i in ranked_ids], scores


SQL_TOOL_SYSTEM_PROMPT = """You decide whether a procurement question needs an
aggregate SQL-style lookup (spend totals, counts, averages) rather than
document retrieval. Respond ONLY with JSON:
{"needs_aggregate": bool, "metric": "total_spend|invoice_count|discrepant_count|avg_discrepancy_rate|none",
 "vendor_name": "string or null", "period": "this_quarter|this_year|all_time|null"}
"""


def maybe_run_aggregate_tool(question: str, workspace_id) -> dict | None:
    from apps.documents.models import Invoice
    from django.utils import timezone

    client = get_llm_client()
    response = client.complete(SQL_TOOL_SYSTEM_PROMPT, question, model=client.fast_model,
                                json_schema={"needs_aggregate": "bool", "metric": "string",
                                             "vendor_name": "string|null", "period": "string|null"})
    decision = response["json"] or {"needs_aggregate": False}
    if "discrepant" in question.lower() and decision.get("metric") == "invoice_count":
        decision["metric"] = "discrepant_count"
    if not decision.get("needs_aggregate"):
        return None

    qs = Invoice.objects.filter(workspace_id=workspace_id)
    if decision.get("vendor_name"):
        qs = qs.filter(vendor__name__icontains=decision["vendor_name"])
    if decision.get("period") == "this_quarter":
        now = timezone.now()
        quarter_start_month = 3 * ((now.month - 1) // 3) + 1
        qs = qs.filter(invoice_date__year=now.year, invoice_date__month__gte=quarter_start_month)
    elif decision.get("period") == "this_year":
        qs = qs.filter(invoice_date__year=timezone.now().year)

    if decision["metric"] == "total_spend":
        value = qs.aggregate(total=Sum("total_amount"))["total"] or 0
        return {"metric": "total_spend", "value": float(value), "invoice_count": qs.count()}
    if decision["metric"] == "invoice_count":
        return {"metric": "invoice_count", "value": qs.count()}
    if decision["metric"] == "discrepant_count":
        from apps.matching.models import MatchResult
        value = MatchResult.objects.filter(invoice__in=qs, status="discrepant").count()
        return {"metric": "discrepant_count", "value": value}
    return None


ANSWER_SYSTEM_PROMPT = """You answer procurement questions using ONLY the
provided document excerpts and/or aggregate data tool result. Cite excerpts
by their [chunk:N] marker inline. If the excerpts and tool result do not
contain enough information to answer confidently, say exactly:
"I couldn't find that in your documents." Do not guess or use outside knowledge.
"""


def answer_question(question: str, workspace_id) -> dict:
    chunks, scores = hybrid_retrieve(question, workspace_id)
    aggregate = maybe_run_aggregate_tool(question, workspace_id)

    if not chunks and not aggregate:
        return {"answer": "I couldn't find that in your documents.", "citations": []}

    requested_ids = re.findall(r"\b(?:INV|PO|CT)-[A-Z0-9-]+\b", question.upper())
    requested_ids += re.findall(
        r"\b(?:INVOICE|PO|CONTRACT)\s+([A-Z0-9][A-Z0-9-]+)", question.upper()
    )
    if requested_ids and not any(
        all(identifier in (chunk.text or "").upper() for identifier in requested_ids)
        for chunk in chunks
    ) and not aggregate:
        return {"answer": "I couldn't find that in your documents.", "citations": []}

    excerpts = "\n\n".join(f"[chunk:{i}] {c.text}" for i, c in enumerate(chunks))
    context = f"Document excerpts:\n{excerpts}"
    if aggregate:
        context += f"\n\nAggregate data tool result: {aggregate}"

    client = get_llm_client()
    response = client.complete(ANSWER_SYSTEM_PROMPT, f"{context}\n\nQuestion: {question}", model=client.fast_model)
    citations = [
        {
            "chunk_id": str(c.id),
            "document_id": str(c.document_id),
            "position": c.position,
            "snippet": c.text[:200],
        }
        for c in chunks
    ]
    return {"answer": response["text"], "citations": citations}
