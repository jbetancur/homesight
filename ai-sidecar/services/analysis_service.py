"""AI-powered incident and metric analysis (replaces hard-coded rules)"""

import logging
from typing import Dict, Any, Optional, List
from models.analyze import AnalyzeRequest, AnalyzeResponse
from llm.provider import HybridLLMProvider
from rag.engine import RAGEngine

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    AI-powered analysis service that replaces hard-coded incident rules.

    Uses LLM + RAG to provide intelligent incident analysis and recommendations.
    """

    def __init__(
        self,
        llm_provider: HybridLLMProvider,
        rag_engine: Optional[RAGEngine] = None
    ):
        self.llm = llm_provider
        self.rag = rag_engine

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        """
        Analyze metrics or incidents using AI

        Args:
            request: AnalyzeRequest with type and data

        Returns:
            AnalyzeResponse with analysis, insights, and actions
        """
        if request.type == "metrics":
            return await self._analyze_metrics(request.data, request.context)
        elif request.type == "incident":
            return await self._analyze_incident(request.data, request.context)
        else:
            raise ValueError(f"Unknown analysis type: {request.type}")

    async def _analyze_metrics(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ) -> AnalyzeResponse:
        """Analyze sensor metrics for anomalies"""
        sensor_id = data.get("sensor_id", "unknown")
        values = data.get("values", [])

        if not values:
            return AnalyzeResponse(
                analysis="No metric data provided",
                insights=["Unable to analyze - no data available"]
            )

        # Build analysis prompt
        stats = {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values)
        }

        prompt = f"""Analyze these sensor metrics and identify any anomalies or concerns:

Sensor ID: {sensor_id}
Sample Count: {stats['count']}
Min Value: {stats['min']:.2f}
Max Value: {stats['max']:.2f}
Average: {stats['avg']:.2f}
Recent Values: {values[-10:]}

Provide:
1. Brief analysis of the metrics
2. Any anomalies or patterns detected
3. Recommended actions if needed

Respond in JSON format:
{{
    "analysis": "brief summary",
    "insights": ["insight 1", "insight 2"],
    "actions": ["action 1", "action 2"] or null
}}"""

        response = await self.llm.simple_generate_async(
            prompt=prompt,
            temperature=0.3,
            max_tokens=500
        )

        # Parse JSON response
        try:
            import json
            # Extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
                return AnalyzeResponse(
                    analysis=result.get("analysis", "Analysis completed"),
                    insights=result.get("insights", []),
                    actions=result.get("actions"),
                    metadata={"sensor_id": sensor_id, "stats": stats}
                )
        except Exception as e:
            logger.warning(f"Failed to parse JSON from LLM: {e}")

        # Fallback to simple response
        return AnalyzeResponse(
            analysis=response[:200],
            insights=["Metrics analyzed"],
            metadata={"sensor_id": sensor_id, "stats": stats}
        )

    async def _analyze_incident(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ) -> AnalyzeResponse:
        """
        AI-powered incident analysis with RAG enhancement

        This replaces all the hard-coded if/else rules!
        """
        incident_type = data.get("type", "unknown")
        severity = data.get("severity", "unknown")
        incident_id = data.get("id", "unknown")
        device_id = data.get("device_id")

        # Get relevant documentation from RAG
        rag_context = ""
        rag_sources = []

        if self.rag:
            try:
                # Query RAG for relevant docs
                query = f"{incident_type} {device_id or ''}"
                results = self.rag.query(query, n_results=5)  # Get more results for better context

                if results:
                    rag_parts = ["Relevant documentation:"]
                    for r in results:
                        if r.get('relevance_score', 0) > 0.25:
                            source = r['metadata'].get('source', 'Unknown')
                            # Use full text, not truncated - let LLM decide what's relevant
                            excerpt = r['text'][:1500]  # Increased from 300 to 1500 chars
                            rag_parts.append(f"\n- {source} (relevance: {r['relevance_score']:.2f}):\n{excerpt}")
                            rag_sources.append({
                                "source": source,
                                "relevance": r['relevance_score']
                            })

                    if len(rag_parts) > 1:
                        rag_context = "\n".join(rag_parts)

            except Exception as e:
                logger.error(f"RAG query failed: {e}")

        # Build analysis prompt with emphasis on specificity and citations
        has_docs = bool(rag_context)

        prompt = f"""Analyze this home monitoring incident and provide SPECIFIC, ACTIONABLE recommendations:

Incident Type: {incident_type}
Severity: {severity}
Device ID: {device_id or 'N/A'}
Additional Data: {data}

{rag_context if rag_context else "⚠️  WARNING: No device-specific documentation available in knowledge base. Provide general troubleshooting advice but note the lack of specific documentation."}

CRITICAL REQUIREMENTS:
1. Analysis must be SPECIFIC to this device and incident type
2. {"MUST cite documentation sources for each recommendation when available" if has_docs else "Since no documentation is available, recommend finding manufacturer documentation"}
3. Actions must include SPECIFIC steps (not generic advice like 'check manual')
4. If documentation is available, extract EXACT troubleshooting steps, part numbers, or specifications
5. Include links/references where available

Respond in JSON format:
{{
    "analysis": "specific 1-2 sentence summary focused on THIS device and incident",
    "insights": [
        "specific insight with source citation if available: (Source: XYZ manual, page N)",
        "another specific insight",
        "warning about lack of documentation if none available"
    ],
    "actions": [
        "Step 1: Specific action (e.g., 'Replace CR2032 battery in sensor housing' not 'replace battery')",
        "Step 2: Specific troubleshooting (e.g., 'Press reset button for 10 seconds' not 'reset device')",
        "Step 3: Where to find parts/info (e.g., 'Order replacement at manufacturer.com/parts' not 'check website')"
    ],
    "priority": "low|medium|high|urgent",
    "sources_cited": ["source 1", "source 2"] or [],
    "documentation_available": {has_docs}
}}"""

        system_prompt = """You are an expert home maintenance advisor.

CRITICAL: Your advice must be SPECIFIC and ACTIONABLE, not generic platitudes.
- BAD: "Check the manual for battery replacement"
- GOOD: "Replace with CR2032 3V lithium battery (part #ABC123). Remove sensor from door frame, twist back cover counterclockwise, replace battery with + side up."

- BAD: "Regularly check battery levels"
- GOOD: "Set a reminder to check battery every 6 months, or enable low-battery notifications in the HomeSight app"

If documentation is provided, extract EXACT steps, part numbers, model information, and specifications.
If NO documentation available, acknowledge this limitation and recommend specific sources to find information."""

        response = await self.llm.simple_generate_async(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.4,
            max_tokens=700
        )

        # Parse JSON response
        try:
            import json
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start != -1 and json_end > json_start:
                result = json.loads(response[json_start:json_end])

                metadata = {
                    "type": incident_type,
                    "severity": severity,
                    "incident_id": incident_id,
                    "priority": result.get("priority", "medium"),
                    "documentation_available": result.get("documentation_available", has_docs),
                    "sources_cited": result.get("sources_cited", [])
                }

                if rag_sources:
                    metadata["rag_sources"] = rag_sources
                    # Add note if no docs were available
                    if not has_docs:
                        metadata["warning"] = "No device-specific documentation in knowledge base"

                return AnalyzeResponse(
                    analysis=result.get("analysis", f"Incident: {incident_type}"),
                    insights=result.get("insights", []),
                    actions=result.get("actions"),
                    metadata=metadata
                )

        except Exception as e:
            logger.warning(f"Failed to parse incident analysis JSON: {e}")

        # Fallback: return raw response
        return AnalyzeResponse(
            analysis=f"Incident Analysis: {incident_type} (Severity: {severity})",
            insights=[response[:300]],
            actions=["Review incident details and take appropriate action"],
            metadata={
                "type": incident_type,
                "severity": severity,
                "incident_id": incident_id,
                "parse_error": str(e) if 'e' in locals() else None
            }
        )
