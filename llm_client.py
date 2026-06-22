"""
llm_client.py — Local LLM Client (Zero External Dependencies)
IISc Bangalore · Deep Learning Project · June 2026

Talks to ANY locally running LLM using only Python built-ins (urllib).
Compatible with:
    - Ollama        → ollama serve (default port 11434)
    - LM Studio     → local server (default port 1234)
    - GPT4All       → API mode (port 4891)

NO API KEY NEEDED. NO PAID SERVICE. RUNS 100% OFFLINE.

Supported models (pull one before running):
    ollama pull llama3.2       ← recommended (2GB, fast)
    ollama pull mistral        ← good quality (4GB)
    ollama pull phi3           ← small but smart (2GB)
    ollama pull gemma2         ← Google's model (5GB)

Usage:
    from llm_client import LLMClient
    llm = LLMClient()
    response = llm.chat("Extract device name from: patient MRI burn on PHILIPS")
"""

import json
import urllib.request
import urllib.error
from typing import Optional


# ─────────────────────────────────────────────
# AUTO-DETECT which local server is running
# ─────────────────────────────────────────────

ENDPOINTS = [
    {
        "name":    "Ollama",
        "base":    "http://localhost:11434",
        "chat":    "/api/chat",
        "models":  "/api/tags",
        "format":  "ollama",
        "default_model": "llama3.2"
    },
    {
        "name":    "LM Studio",
        "base":    "http://localhost:1234",
        "chat":    "/v1/chat/completions",
        "models":  "/v1/models",
        "format":  "openai",
        "default_model": "local-model"
    },
    {
        "name":    "GPT4All",
        "base":    "http://localhost:4891",
        "chat":    "/v1/chat/completions",
        "models":  "/v1/models",
        "format":  "openai",
        "default_model": "ggml-model"
    },
]


class LLMClient:
    """
    Lightweight local LLM client.
    Auto-detects which server is running on startup.
    Falls back to rule-based mock if no server found.
    """

    def __init__(self, model: Optional[str] = None, endpoint: Optional[str] = None):
        self.endpoint_cfg = None
        self.model = model

        if endpoint:
            # Manual override
            self.endpoint_cfg = {
                "name": "Custom",
                "base": endpoint,
                "chat": "/api/chat",
                "format": "ollama",
                "default_model": model or "llama3.2"
            }
            self.model = model or "llama3.2"
        else:
            self._auto_detect()

        if self.endpoint_cfg:
            print(f"[LLM] ✅ Connected to {self.endpoint_cfg['name']} "
                  f"→ model: {self.model}")
        else:
            print("[LLM] ⚠️  No local LLM found — using rule-based fallback")
            print("[LLM]    To enable AI: run 'ollama serve' in Terminal")
            print("[LLM]    Then: ollama pull llama3.2")

    def _auto_detect(self):
        """Try each known endpoint and use the first that responds."""
        for cfg in ENDPOINTS:
            try:
                url = cfg["base"] + cfg["models"]
                req = urllib.request.Request(
                    url, headers={"User-Agent": "IISc-MedSig/1.0"}
                )
                with urllib.request.urlopen(req, timeout=2) as resp:
                    data = json.loads(resp.read())
                    # Get first available model
                    if cfg["format"] == "ollama":
                        models = [m["name"] for m in data.get("models", [])]
                    else:
                        models = [m["id"] for m in data.get("data", [])]

                    if models:
                        self.endpoint_cfg = cfg
                        self.model = self.model or models[0]
                        print(f"[LLM] Found {cfg['name']} with models: {models[:3]}")
                        return
            except Exception:
                continue

    def chat(self, prompt: str, system: Optional[str] = None,
             temperature: float = 0.1) -> str:
        """
        Send a chat message and get a response.
        Returns string response (or mock if no server).
        """
        if not self.endpoint_cfg:
            return self._mock_response(prompt)

        cfg = self.endpoint_cfg
        if cfg["format"] == "ollama":
            return self._call_ollama(prompt, system, temperature)
        else:
            return self._call_openai_compat(prompt, system, temperature)

    def _call_ollama(self, prompt: str, system: Optional[str],
                     temperature: float) -> str:
        """Call Ollama API."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model":   self.model,
            "messages": messages,
            "stream":  False,
            "options": {"temperature": temperature}
        }).encode()

        url = self.endpoint_cfg["base"] + self.endpoint_cfg["chat"]
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json",
                     "User-Agent": "IISc-MedSig/1.0"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data["message"]["content"]
        except urllib.error.URLError as e:
            print(f"[LLM] ❌ Ollama call failed: {e}")
            return self._mock_response(prompt)

    def _call_openai_compat(self, prompt: str, system: Optional[str],
                             temperature: float) -> str:
        """Call OpenAI-compatible API (LM Studio, GPT4All)."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model":       self.model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  2048
        }).encode()

        url = self.endpoint_cfg["base"] + self.endpoint_cfg["chat"]
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json",
                     "User-Agent": "IISc-MedSig/1.0"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"]
        except urllib.error.URLError as e:
            print(f"[LLM] ❌ OpenAI-compat call failed: {e}")
            return self._mock_response(prompt)

    def is_available(self) -> bool:
        return self.endpoint_cfg is not None

    # ─────────────────────────────────────────
    # RULE-BASED MOCK — works with zero LLM
    # Good enough to demo the pipeline structure
    # ─────────────────────────────────────────

    def _mock_response(self, prompt: str) -> str:
        """
        Deterministic rule-based fallback.
        Produces valid JSON for every agent without any LLM.
        Used when no local server is running.
        """
        prompt_lower = prompt.lower()

        # ── Extraction response ──
        if "extract" in prompt_lower or "extraction" in prompt_lower or "narrative" in prompt_lower:
            modality = "MRI"
            if "ct" in prompt_lower or "computed tomography" in prompt_lower:
                modality = "CT"
            elif "ultrasound" in prompt_lower:
                modality = "Ultrasound"
            elif "x-ray" in prompt_lower or "xray" in prompt_lower:
                modality = "X-ray"
            elif "pcr" in prompt_lower or "molecular" in prompt_lower:
                modality = "MolDx"

            mfr = "UNKNOWN"
            for brand in ["PHILIPS", "SIEMENS", "GE", "FUJIFILM",
                          "BECKMAN", "MEDTRONIC", "TOSHIBA"]:
                if brand.lower() in prompt_lower:
                    mfr = brand
                    break

            severity = "S3"
            if "death" in prompt_lower or "fatal" in prompt_lower:
                severity = "S5"
            elif "life-threatening" in prompt_lower or "critical" in prompt_lower:
                severity = "S4"
            elif "no injury" in prompt_lower or "no harm" in prompt_lower:
                severity = "S1"
            elif "minor" in prompt_lower or "slight" in prompt_lower:
                severity = "S2"

            software = any(w in prompt_lower for w in [
                "software", "algorithm", "system", "error", "data",
                "image", "display", "crash", "update", "firmware"
            ])

            return json.dumps({
                "modality": modality,
                "manufacturer": mfr,
                "device_model": "Medical Device System",
                "component": "image processing software",
                "failure_mode": "device malfunction causing patient risk",
                "symptom": "abnormal device behaviour observed",
                "event_type": "Injury" if "injury" in prompt_lower else "Malfunction",
                "severity_indicator": severity,
                "software_related": software,
                "is_safety_related": True,
                "usability_concern": "user" in prompt_lower or "operator" in prompt_lower,
                "security_concern": False,
                "qms_complaint_category": "SW-ALGO" if software else "HW-MECH",
                "patient_impact": "potential patient harm",
                "affected_countries": ["US"],
                "complaint_source": "hospital",
                "confidence": 0.65,
                "low_confidence_reason": "Rule-based fallback — no LLM running"
            })

        # ── Risk assessment response ──
        if "risk" in prompt_lower or "iso 14971" in prompt_lower or "capa" in prompt_lower:
            return json.dumps({
                "hazardous_situation": "Device malfunction during medical procedure",
                "harm": "Potential patient injury or delayed diagnosis",
                "severity_level": "S3",
                "severity_label": "Serious",
                "severity_rationale": "Malfunction during active patient care creates serious risk",
                "probability_level": "P3",
                "probability_label": "Occasional",
                "probability_rationale": "Multiple similar events reported in FDA MAUDE database",
                "annex_c_hazard_category": "Energy hazard - software",
                "iec62304_classification": "Class B",
                "immediate_action": "Notify all affected sites. Suspend use pending investigation.",
                "investigation": "Review device logs. Identify root cause of malfunction.",
                "corrective_action": "Apply software patch. Validate on affected units.",
                "preventive_action": "Implement mandatory QA review protocol.",
                "verification_method": "Test on 10 representative cases post-patch.",
                "effectiveness_criteria": "Zero recurrence over 90-day monitoring period.",
                "timeline": "30 days corrective, 60 days preventive",
                "precedent_basis": "Based on similar FDA recall precedents",
                "iso13485_clause": "ISO 13485 §8.5.2",
                "uncertainty": "Root cause under investigation",
                "evidence_basis": ["FDA-RECALL-001", "MAUDE-EVENT-001"]
            })

        # ── Report response ──
        if "report" in prompt_lower or "write" in prompt_lower or "summary" in prompt_lower:
            return json.dumps({
                "summary": (
                    "A medical device adverse event was identified requiring immediate attention. "
                    "Risk assessment indicates ALARP level per ISO 14971 analysis. "
                    "Corrective and preventive actions have been recommended."
                ),
                "device_description": (
                    "Medical imaging device malfunction detected during patient procedure. "
                    "Software-related failure mode identified."
                ),
                "risk_narrative": (
                    "ISO 14971 risk assessment: Severity S3 (Serious) × Probability P3 (Occasional) = ALARP. "
                    "Risk controls required. Evidence from FDA MAUDE database [SOURCE: FDA-RECALL-001]."
                ),
                "capa_summary": (
                    "Immediate: Notify affected sites. "
                    "Corrective: Software patch within 30 days [SOURCE: MAUDE-EVENT-001]. "
                    "Preventive: Mandatory QA double-read protocol."
                ),
                "body": (
                    "## Medical Device Safety Report\n\n"
                    "**Report Generated:** Rule-based fallback (no LLM active)\n\n"
                    "### Executive Summary\n"
                    "A medical device adverse event was identified and assessed per ISO 14971. "
                    "Risk level: ALARP. Immediate action required.\n\n"
                    "### Risk Assessment\n"
                    "- Severity: S3 (Serious) — device malfunction during patient care\n"
                    "- Probability: P3 (Occasional) — based on similar MAUDE events\n"
                    "- Risk Level: ALARP — risk controls required [SOURCE: FDA-RECALL-001]\n\n"
                    "### CAPA Recommendations\n"
                    "1. **Immediate:** Notify all affected sites\n"
                    "2. **Corrective:** Apply software patch within 30 days\n"
                    "3. **Preventive:** Mandatory QA review protocol\n\n"
                    "### Evidence\n"
                    "Based on FDA MAUDE database analysis [SOURCE: MAUDE-EVENT-001]\n"
                ),
                "citations": ["FDA-RECALL-001", "MAUDE-EVENT-001"]
            })

        # Generic fallback
        return json.dumps({"response": "Processed", "confidence": 0.6})

    def list_models(self) -> list[str]:
        """List available models on the local server."""
        if not self.endpoint_cfg:
            return []
        try:
            url = self.endpoint_cfg["base"] + self.endpoint_cfg["models"]
            req = urllib.request.Request(url,
                  headers={"User-Agent": "IISc-MedSig/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                if self.endpoint_cfg["format"] == "ollama":
                    return [m["name"] for m in data.get("models", [])]
                return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []


# ─────────────────────────────────────────────
# SMOKE TEST
# Run: python3 llm_client.py
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== llm_client.py smoke test ===\n")

    llm = LLMClient()

    print(f"\nServer available: {llm.is_available()}")
    if llm.is_available():
        models = llm.list_models()
        print(f"Available models: {models}")

    print("\n--- Test 1: Extraction prompt ---")
    resp = llm.chat(
        prompt="Extract key info from this narrative: "
               "PATIENT EXPERIENCED BURN DURING MRI SCAN ON PHILIPS ACHIEVA 3T.",
        system="You extract medical device information. Return JSON only."
    )
    print(resp[:300])

    print("\n--- Test 2: Risk prompt ---")
    resp2 = llm.chat(
        prompt="Assess risk for: MRI software crash. S3, P3. Return JSON.",
        system="You are an ISO 14971 risk assessor. Return JSON only."
    )
    print(resp2[:300])

    print(f"\n✅ LLM client working. Mode: {'AI' if llm.is_available() else 'Rule-based fallback'}")
