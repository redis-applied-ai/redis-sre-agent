"""Default Redis catalog-backed target discovery backend."""

from __future__ import annotations

from typing import List

from .contracts import DiscoveryCandidate, DiscoveryRequest, DiscoveryResponse


class RedisCatalogDiscoveryBackend:
    """Resolve Redis targets from the built-in target catalog."""

    backend_name = "redis_catalog"

    async def resolve(self, request: DiscoveryRequest) -> DiscoveryResponse:
        from redis_sre_agent.core.targets import (
            _build_public_match_from_doc,
            _confidence_from_score,
            _parse_query_hints,
            _score_target_doc,
            get_target_catalog,
        )

        docs = await get_target_catalog(user_id=request.user_id)
        if not docs:
            return DiscoveryResponse(status="no_match")

        hints = _parse_query_hints(request.query)
        ranked: List[DiscoveryCandidate] = []
        for doc in docs:
            score, reasons = _score_target_doc(
                request.query,
                doc,
                preferred_capabilities=request.preferred_capabilities,
                hints=hints,
            )
            if score < 2.5:
                continue
            public_match = _build_public_match_from_doc(
                doc,
                confidence=_confidence_from_score(score),
                match_reasons=reasons,
                score=score,
            )
            ranked.append(
                DiscoveryCandidate(
                    public_match=public_match,
                    binding_strategy="redis_default",
                    binding_subject=doc.resource_id,
                    private_binding_ref={"target_kind": doc.target_kind},
                    discovery_backend=self.backend_name,
                    score=score,
                    confidence=public_match.confidence,
                )
            )

        ranked.sort(key=lambda candidate: (candidate.score, candidate.confidence), reverse=True)
        limited = ranked[: max(1, min(request.max_results, 10))]
        if not limited:
            return DiscoveryResponse(status="no_match")

        top = limited[0]
        selected: List[DiscoveryCandidate] = []
        clarification_required = False

        if request.allow_multiple:
            selected = [
                candidate for candidate in limited if candidate.score >= max(3.0, top.score - 1.5)
            ][: min(3, request.max_results)]
        else:
            if len(limited) > 1 and limited[1].score >= top.score - 0.75:
                clarification_required = True
                selected = limited[: min(3, request.max_results)]
            else:
                selected = [top]

        return DiscoveryResponse(
            status=(
                "clarification_required"
                if clarification_required
                else ("resolved" if selected else "no_match")
            ),
            clarification_required=clarification_required,
            matches=[candidate.public_match for candidate in limited],
            selected_matches=selected,
        )
