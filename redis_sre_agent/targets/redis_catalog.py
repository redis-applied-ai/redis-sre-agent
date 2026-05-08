"""Default Redis catalog-backed target discovery backend."""

from __future__ import annotations

from typing import List

from .contracts import DiscoveryCandidate, DiscoveryRequest, DiscoveryResponse
from .registry import get_target_integration_registry


class RedisCatalogDiscoveryBackend:
    """Resolve Redis targets from the built-in target catalog."""

    backend_name = "redis_catalog"

    async def resolve(self, request: DiscoveryRequest) -> DiscoveryResponse:
        from redis_sre_agent.core.targets import (
            _confidence_from_score,
            _exact_target_terms,
            _normalize,
            _parse_query_hints,
            _query_mentions_exact_target,
            _score_target_doc,
            build_public_match_from_doc,
            get_target_catalog,
        )

        docs = await get_target_catalog(user_id=request.user_id)
        if not docs:
            return DiscoveryResponse(status="no_match")

        registry = get_target_integration_registry()
        normalized_query = _normalize(request.query)
        hints = _parse_query_hints(request.query)
        ranked: List[DiscoveryCandidate] = []
        exact_ranked: List[DiscoveryCandidate] = []
        for doc in docs:
            score, reasons = _score_target_doc(
                request.query,
                doc,
                preferred_capabilities=request.preferred_capabilities,
                hints=hints,
            )
            if score < 2.5:
                continue
            public_match = build_public_match_from_doc(
                doc,
                confidence=_confidence_from_score(score),
                match_reasons=reasons,
                score=score,
            )
            candidate = DiscoveryCandidate(
                public_match=public_match,
                binding_strategy=registry.default_binding_strategy,
                binding_subject=doc.resource_id,
                private_binding_ref={"target_kind": doc.target_kind},
                discovery_backend=self.backend_name,
                score=score,
                confidence=public_match.confidence,
            )
            ranked.append(candidate)
            exact_query_match = normalized_query and normalized_query in _exact_target_terms(doc)
            if exact_query_match or (
                request.allow_multiple and _query_mentions_exact_target(doc, hints)
            ):
                exact_ranked.append(candidate)

        ranked.sort(key=lambda candidate: (candidate.score, candidate.confidence), reverse=True)
        exact_ranked.sort(
            key=lambda candidate: (candidate.score, candidate.confidence), reverse=True
        )
        limited = ranked[: max(1, min(request.max_results, 10))]
        if not limited:
            return DiscoveryResponse(status="no_match")

        selected: List[DiscoveryCandidate] = []
        clarification_required = False

        if exact_ranked:
            top_exact = exact_ranked[0]
            if request.allow_multiple:
                selected = exact_ranked[: min(3, request.max_results)]
            elif len(exact_ranked) > 1 and exact_ranked[1].score >= top_exact.score - 0.75:
                clarification_required = True
                selected = exact_ranked[: min(3, request.max_results)]
            else:
                selected = [top_exact]
        else:
            clarification_required = True
            selected = limited[: min(3, request.max_results)]

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
