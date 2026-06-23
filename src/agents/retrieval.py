import os
from typing import Dict, List, Optional

from rapidfuzz import fuzz

from src.pipeline.schemas import ExtractedSignal, RetrievalEvidence
from src.utils.storage import embed_text

# Live OpenFDA lookup is optional — the import never breaks the pipeline.
try:
    from src.utils.openfda_mcp_client import OpenFDAMCPClient
except Exception:  # pragma: no cover - defensive
    OpenFDAMCPClient = None  # type: ignore


# Product code → OpenFDA device-name search phrase (MAUDE generic terms).
_PRODUCT_CODE_TO_DEVICE_NAME = {
    "LNH": "magnetic resonance imaging",
    "JAK": "computed tomography",
    "IYE": "computed tomography",
    "LLZ": "ultrasound",
    "IZL": "x-ray",
}


class RetrievalAgent:
    """Retrieves nearby archive evidence from events and recalls.

    When ``OPENFDA_LIVE_RETRIEVAL`` is truthy (and the Node OpenFDA MCP server is
    built + available), the agent also augments local evidence with *live* MAUDE
    adverse events and FDA recalls fetched over MCP. The live path is strictly
    additive and fails closed: if anything is unavailable the agent silently
    falls back to its offline archive + vector evidence.
    """

    def __init__(self, openfda_client=None, enable_live: Optional[bool] = None):
        if enable_live is None:
            enable_live = os.environ.get("OPENFDA_LIVE_RETRIEVAL", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        self._live_enabled = bool(enable_live)
        self.openfda = openfda_client
        if self._live_enabled and self.openfda is None and OpenFDAMCPClient is not None:
            try:
                self.openfda = OpenFDAMCPClient()
            except Exception:
                self.openfda = None

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
        issues = {issue.lower() for issue in extracted.key_issues}
        scored: List[RetrievalEvidence] = []

        for event in events_by_code.get(complaint_product_code, []):
            problem_text = " ".join(event.get("product_problems") or [])
            score = self._score_text(problem_text, issues)
            if score <= 0:
                continue
            report_number = event.get("report_number", "unknown")
            scored.append(
                RetrievalEvidence(
                    evidence_id=f"EV-{report_number}",
                    source_type="MAUDE_EVENT",
                    product_code=complaint_product_code,
                    snippet=problem_text[:220] or "No product problem text",
                    score=round(score, 3),
                    metadata={
                        "event_type": event.get("event_type", "Unknown"),
                        "subquery": self._best_subquery(problem_text, subqueries),
                    },
                )
            )

        for recall in recalls:
            if recall.get("product_code") != complaint_product_code:
                continue
            recall_text = f"{recall.get('reason_for_recall', '')} {recall.get('root_cause_description', '')}"
            score = self._score_text(recall_text, issues) + 0.15
            if score <= 0.15:
                continue
            scored.append(
                RetrievalEvidence(
                    evidence_id=f"RC-{recall.get('res_event_number', 'unknown')}",
                    source_type="FDA_RECALL",
                    product_code=complaint_product_code,
                    snippet=(recall.get("reason_for_recall") or "")[:220],
                    score=round(score, 3),
                    metadata={
                        "classification": recall.get("classification", "Unknown"),
                        "root_cause": recall.get("root_cause_description", "Unknown"),
                    },
                )
            )

        if vector_collection is not None and (issues or subqueries):
            queries = subqueries or [" ".join(sorted(issues))]
            seen_vector_ids = set()
            for sub in queries:
                if not sub.strip():
                    continue
                try:
                    result = vector_collection.query(query_embeddings=[embed_text(sub)], n_results=3)
                    docs = result.get("documents", [[]])[0]
                    ids = result.get("ids", [[]])[0]
                    metas = result.get("metadatas", [[]])[0]
                    for idx, doc in enumerate(docs):
                        vector_id = ids[idx]
                        if vector_id in seen_vector_ids:
                            continue
                        seen_vector_ids.add(vector_id)
                        meta = dict(metas[idx]) if idx < len(metas) else {}
                        meta["subquery"] = sub
                        scored.append(
                            RetrievalEvidence(
                                evidence_id=f"VX-{vector_id}",
                                source_type="VECTOR_EVENT",
                                product_code=complaint_product_code,
                                snippet=(doc or "")[:220],
                                score=0.42,
                                metadata=meta,
                            )
                        )
                except Exception:
                    pass

        if self._live_enabled and self.openfda is not None and getattr(self.openfda, "enabled", False):
            try:
                scored.extend(
                    self._live_openfda_evidence(issues, complaint_product_code, top_k)
                )
            except Exception:
                pass

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def _live_openfda_evidence(
        self, issues: set, complaint_product_code: str, top_k: int
    ) -> List[RetrievalEvidence]:
        """Fetch live MAUDE adverse events + FDA recalls over MCP (best effort)."""
        device_name = _PRODUCT_CODE_TO_DEVICE_NAME.get(complaint_product_code)
        limit = max(top_k, 5)
        live: List[RetrievalEvidence] = []

        for event in self.openfda.search_adverse_events(
            device_name=device_name, limit=limit
        ):
            text = event.get("event_description") or ""
            score = self._score_text(text, issues) + 0.1
            report_number = event.get("report_number", "unknown")
            device = event.get("device") or {}
            live.append(
                RetrievalEvidence(
                    evidence_id=f"LIVE-EV-{report_number}",
                    source_type="MAUDE_LIVE",
                    product_code=complaint_product_code,
                    snippet=(text or "Not available")[:220],
                    score=round(score, 3),
                    metadata={
                        "event_type": event.get("event_type", "Unknown"),
                        "date_received": event.get("date_received", ""),
                        "brand_name": device.get("brand_name", ""),
                        "manufacturer": device.get("manufacturer_d_name", ""),
                        "live": True,
                    },
                )
            )

        for recall in self.openfda.search_recalls(
            device_name=device_name, limit=limit
        ):
            text = (
                recall.get("reason_for_recall")
                or recall.get("product_description")
                or recall.get("event_description")
                or ""
            )
            score = self._score_text(text, issues) + 0.2
            recall_id = (
                recall.get("recall_number")
                or recall.get("res_event_number")
                or recall.get("event_id")
                or "unknown"
            )
            live.append(
                RetrievalEvidence(
                    evidence_id=f"LIVE-RC-{recall_id}",
                    source_type="FDA_RECALL_LIVE",
                    product_code=complaint_product_code,
                    snippet=(text or "Not available")[:220],
                    score=round(score, 3),
                    metadata={
                        "classification": recall.get("classification", "Unknown"),
                        "recalling_firm": recall.get("recalling_firm", ""),
                        "live": True,
                    },
                )
            )

        return live

    @staticmethod
    def _best_subquery(text: str, subqueries: Optional[List[str]]) -> Optional[str]:
        if not subqueries:
            return None
        text_l = text.lower()
        best = max(subqueries, key=lambda s: fuzz.partial_ratio(s.lower(), text_l))
        return best

    @staticmethod
    def _score_text(text: str, issues: set) -> float:
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
