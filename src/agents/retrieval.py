"""
Project/src/agents/retrieval.py
Retrieval Agent — Agent 3
Owner : Pothukanuri Sai Venkat
Team  : IISc Bangalore · Deep Learning · June 2026

Aligned with team codebase (kapil_Report_GenerationAgent branch):
  - Input  : ExtractedSignal  (from extraction agent)
  - Output : List[RetrievalEvidence]  (consumed by risk agent)
  - State  : WorkflowState["extraction"] → WorkflowState["retrieval"]
  - Scoring: rapidfuzz fuzzy matching (same as team)
  - Sources: pre-loaded events_by_code + recalls + optional vector_collection
             (same as team — NOT live OpenFDA API calls)

LangGraph node:
    graph.add_node("retrieve", self._retrieve)
    graph.add_edge("memory", "retrieve")
    graph.add_edge("retrieve", "merge")
"""

from typing import Dict, List, Optional

from rapidfuzz import fuzz

from src.pipeline.schemas import ExtractedSignal, RetrievalEvidence
from src.utils.storage import embed_text


class RetrievalAgent:
    """
    Retrieves nearby archive evidence from pre-loaded events and recalls.

    Three evidence sources (in priority order):
      1. MAUDE_EVENT  — pre-loaded adverse events matched by key_issues
      2. FDA_RECALL   — pre-loaded recall records matched by key_issues
      3. VECTOR_EVENT — ChromaDB semantic search (when vector_collection provided)
    """

    # ── Scoring thresholds (aligned with team MIN_RETRIEVAL_SCORE = 0.3) ──
    MIN_EVENT_SCORE  = 0.0    # keep any event with any match
    MIN_RECALL_SCORE = 0.15   # recalls get +0.15 bonus → threshold is 0.15
    RECALL_BONUS     = 0.15   # gives recalls a slight boost (team convention)
    VECTOR_SCORE     = 0.42   # fixed score for vector results (team convention)
    VECTOR_TOP_K     = 3      # vector results per sub-query (team convention)

    def retrieve(
        self,
        extracted: ExtractedSignal,
        complaint_product_code: str,
        events_by_code: Dict[str, List[dict]],
        recalls: List[dict],
        vector_collection=None,
        top_k: int = 5,
        subqueries: Optional[List[str]] = None,
    ) -> List[RetrievalEvidence]:
        """
        Main retrieval method — called by LangGraph _retrieve node.

        Args:
            extracted:              ExtractedSignal from Extraction Agent
            complaint_product_code: e.g. "LNH" for MRI
            events_by_code:         dict of product_code → list of MAUDE events
            recalls:                list of all FDA recall records
            vector_collection:      ChromaDB collection (optional)
            top_k:                  max results to return downstream
            subqueries:             LLM-generated sub-queries from Orchestrator

        Returns:
            List[RetrievalEvidence] sorted by score descending, capped at top_k
        """
        issues = {issue.lower() for issue in extracted.key_issues}
        scored: List[RetrievalEvidence] = []

        # ── Source 1: MAUDE adverse events ──────────────────────────────────
        for event in events_by_code.get(complaint_product_code, []):
            problem_text = " ".join(event.get("product_problems") or [])
            score = self._score_text(problem_text, issues)
            if score <= self.MIN_EVENT_SCORE:
                continue
            report_number = event.get("report_number", "unknown")
            scored.append(
                RetrievalEvidence(
                    evidence_id  = f"EV-{report_number}",
                    source_type  = "MAUDE_EVENT",
                    product_code = complaint_product_code,
                    snippet      = problem_text[:220] or "No product problem text",
                    score        = round(score, 3),
                    metadata     = {
                        "event_type": event.get("event_type", "Unknown"),
                        "subquery":   self._best_subquery(problem_text, subqueries),
                    },
                )
            )

        # ── Source 2: FDA recall records ─────────────────────────────────────
        for recall in recalls:
            if recall.get("product_code") != complaint_product_code:
                continue
            recall_text = (
                f"{recall.get('reason_for_recall', '')} "
                f"{recall.get('root_cause_description', '')}"
            )
            score = self._score_text(recall_text, issues) + self.RECALL_BONUS
            if score <= self.MIN_RECALL_SCORE:
                continue
            scored.append(
                RetrievalEvidence(
                    evidence_id  = f"RC-{recall.get('res_event_number', 'unknown')}",
                    source_type  = "FDA_RECALL",
                    product_code = complaint_product_code,
                    snippet      = (recall.get("reason_for_recall") or "")[:220],
                    score        = round(score, 3),
                    metadata     = {
                        "classification": recall.get("classification", "Unknown"),
                        "root_cause":     recall.get("root_cause_description", "Unknown"),
                    },
                )
            )

        # ── Source 3: ChromaDB vector search ─────────────────────────────────
        if vector_collection is not None and (issues or subqueries):
            queries      = subqueries or [" ".join(sorted(issues))]
            seen_vector_ids: set = set()
            for sub in queries:
                if not sub.strip():
                    continue
                try:
                    result = vector_collection.query(
                        query_embeddings=[embed_text(sub)],
                        n_results=self.VECTOR_TOP_K,
                    )
                    docs  = result.get("documents",  [[]])[0]
                    ids   = result.get("ids",         [[]])[0]
                    metas = result.get("metadatas",   [[]])[0]
                    for idx, doc in enumerate(docs):
                        vid = ids[idx]
                        if vid in seen_vector_ids:
                            continue
                        seen_vector_ids.add(vid)
                        meta = dict(metas[idx]) if idx < len(metas) else {}
                        meta["subquery"] = sub
                        scored.append(
                            RetrievalEvidence(
                                evidence_id  = f"VX-{vid}",
                                source_type  = "VECTOR_EVENT",
                                product_code = complaint_product_code,
                                snippet      = (doc or "")[:220],
                                score        = self.VECTOR_SCORE,
                                metadata     = meta,
                            )
                        )
                except Exception:
                    # Vector search failure is non-fatal
                    pass

        # ── Sort by score descending, return top_k ───────────────────────────
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    # ── Scoring helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _score_text(text: str, issues: set) -> float:
        """
        Combined exact + fuzzy match score.
        Normalised to [0, 1] range.
        Mirrors team implementation exactly.
        """
        text_l = text.lower()
        if not issues:
            return 0.0
        exact_hits = sum(1 for issue in issues if issue and issue in text_l)
        fuzzy_hits = 0.0
        for issue in issues:
            if not issue:
                continue
            fuzzy_hits += fuzz.partial_ratio(issue, text_l) / 100.0
        return (exact_hits + fuzzy_hits) / max(len(issues) * 2, 1)

    @staticmethod
    def _best_subquery(
        text: str, subqueries: Optional[List[str]]
    ) -> Optional[str]:
        """Return the subquery with the highest partial match to text."""
        if not subqueries:
            return None
        text_l = text.lower()
        return max(subqueries, key=lambda s: fuzz.partial_ratio(s.lower(), text_l))
