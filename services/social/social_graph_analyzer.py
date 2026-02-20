"""
Social graph analyzer.

Adds graph-level analytics on top of the existing
``EnhancedSocialRelationManager``:

* **Sentiment polarity**: LLM-based batch sentiment labelling for
  interaction pairs (positive/negative/neutral).
* **Community detection**: Louvain algorithm via ``networkx`` to
  identify tightly-knit subgroups within a chat group.
* **Influence ranking**: PageRank to surface the most influential
  members of a group.

All heavy computation is done via ``networkx`` (already a project
dependency). Sentiment labelling uses the framework LLM adapter
(remote API, no local model).

Design notes:
    - Builds an in-memory ``nx.DiGraph`` from the ORM
      ``UserSocialRelationComponent`` rows.
    - Community detection results are cached per group to avoid
      recomputing on every request.
    - Thread-safe for single-event-loop asyncio usage.
"""

import time
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
from pydantic import BaseModel, Field, field_validator

from astrbot.api import logger

from ...core.framework_llm_adapter import FrameworkLLMAdapter


# Pydantic models for guardrails-ai structured output validation.

class _SentimentItem(BaseModel):
    """Schema for a single sentiment-labelled interaction pair."""

    from_user: str = Field(alias="from", description="Source user identifier.")
    to_user: str = Field(alias="to", description="Target user identifier.")
    sentiment: float = Field(
        ge=-1.0, le=1.0,
        description="Sentiment polarity from -1.0 (hostile) to +1.0 (friendly).",
    )
    label: str = Field(
        description="Categorical label: positive, negative, or neutral.",
    )

    model_config = {"populate_by_name": True}

    @field_validator("label")
    @classmethod
    def normalise_label(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("positive", "negative", "neutral"):
            return "neutral"
        return v


# LLM prompt for batch sentiment labelling of interaction pairs.
_SENTIMENT_BATCH_PROMPT = """Below are interaction summaries between users in a chat group.
For each pair, determine the sentiment polarity of the interaction.

Interactions:
{interactions}

Output a JSON array where each element has the format:
{{"from": "<user_a>", "to": "<user_b>", "sentiment": <float from -1.0 to 1.0>, "label": "positive|negative|neutral"}}

Rules:
- sentiment ranges from -1.0 (hostile) to +1.0 (warm/friendly)
- "neutral" means roughly 0, "positive" means > 0.3, "negative" means < -0.3
- Only output the JSON array, no extra text."""


class SocialGraphAnalyzer:
    """Graph-level social analytics for chat groups.

    Usage::

        analyzer = SocialGraphAnalyzer(llm_adapter, db_manager)
        communities = await analyzer.detect_communities(group_id)
        ranking = await analyzer.get_influence_ranking(group_id)
        sentiments = await analyzer.analyze_interaction_sentiment(
            interactions, group_id
        )
    """

    def __init__(
        self,
        llm_adapter: Optional[FrameworkLLMAdapter] = None,
        db_manager=None,
    ) -> None:
        self._llm = llm_adapter
        self._db = db_manager

        # Per-group community cache: group_id -> (timestamp, communities).
        self._community_cache: Dict[str, Tuple[float, List[Set[str]]]] = {}
        self._cache_ttl = 600 # 10 minutes

    # Public API

    async def build_social_graph(self, group_id: str) -> nx.DiGraph:
        """Build a directed graph from stored social relation components.

        Nodes are user IDs; edges carry ``weight`` (relation value) and
        ``relation_type`` attributes.
        """
        graph = nx.DiGraph()

        if not self._db or not hasattr(self._db, "get_session"):
            return graph

        try:
            from ...models.orm.social_relation import UserSocialRelationComponent
            from sqlalchemy import select

            async with self._db.get_session() as session:
                stmt = select(UserSocialRelationComponent).where(
                    UserSocialRelationComponent.group_id == group_id
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

            for row in rows:
                graph.add_edge(
                    row.from_user_id,
                    row.to_user_id,
                    weight=row.value,
                    relation_type=row.relation_type,
                    frequency=row.frequency,
                )

        except Exception as exc:
            logger.debug(f"[SocialGraph] Failed to build graph: {exc}")

        return graph

    async def detect_communities(
        self, group_id: str, resolution: float = 1.0
    ) -> List[Set[str]]:
        """Detect communities within a group using the Louvain algorithm.

        Args:
            group_id: Chat group to analyse.
            resolution: Louvain resolution parameter (higher = smaller
                communities).

        Returns:
            List of sets, each set containing user IDs that form a
            community.
        """
        # Check cache.
        cached = self._community_cache.get(group_id)
        if cached:
            ts, communities = cached
            if time.time() - ts < self._cache_ttl:
                return communities

        graph = await self.build_social_graph(group_id)
        if graph.number_of_nodes() < 2:
            return []

        # Louvain requires an undirected graph.
        undirected = graph.to_undirected()
        try:
            communities = list(
                nx.community.louvain_communities(
                    undirected, resolution=resolution, seed=42
                )
            )
        except Exception as exc:
            logger.debug(f"[SocialGraph] Community detection failed: {exc}")
            communities = []

        self._community_cache[group_id] = (time.time(), communities)
        return communities

    async def get_influence_ranking(
        self, group_id: str, top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Rank group members by influence using PageRank.

        Returns:
            Sorted list of dicts with ``user_id``, ``pagerank``,
            ``degree`` keys. Most influential first.
        """
        graph = await self.build_social_graph(group_id)
        if graph.number_of_nodes() == 0:
            return []

        try:
            pr = nx.pagerank(graph, weight="weight")
        except Exception:
            pr = {n: 0.0 for n in graph.nodes}

        degree = dict(graph.degree())

        ranking = [
            {
                "user_id": uid,
                "pagerank": round(score, 6),
                "degree": degree.get(uid, 0),
            }
            for uid, score in pr.items()
        ]
        ranking.sort(key=lambda x: x["pagerank"], reverse=True)
        return ranking[:top_k]

    async def analyze_interaction_sentiment(
        self,
        interactions: List[Dict[str, str]],
        group_id: str,
    ) -> List[Dict[str, Any]]:
        """Batch-label sentiment polarity for interaction pairs via LLM.

        Args:
            interactions: List of dicts with ``from``, ``to``, and
                ``summary`` keys describing each interaction.
            group_id: Chat group context.

        Returns:
            List of dicts with ``from``, ``to``, ``sentiment`` (float),
            and ``label`` keys.
        """
        if not self._llm or not interactions:
            return []

        # Format interactions for the prompt.
        lines = []
        for i, item in enumerate(interactions[:20], 1):
            lines.append(
                f"{i}. {item.get('from', '?')} -> {item.get('to', '?')}: "
                f"{item.get('summary', 'general interaction')}"
            )

        prompt = _SENTIMENT_BATCH_PROMPT.format(
            interactions="\n".join(lines)
        )

        try:
            response = await self._llm.generate_response(
                prompt, model_type="filter"
            )
            if not response:
                return []

            # Validate LLM output via guardrails-ai: parse the raw JSON
            # array, then validate each element against the Pydantic schema.
            from ...utils.guardrails_manager import get_guardrails_manager
            gm = get_guardrails_manager()
            parsed = gm.validate_and_clean_json(response, expected_type="array")
            if not isinstance(parsed, list):
                return []

            results: List[Dict[str, Any]] = []
            for raw_item in parsed:
                if not isinstance(raw_item, dict):
                    continue
                try:
                    validated = _SentimentItem.model_validate(raw_item)
                    results.append({
                        "from": validated.from_user,
                        "to": validated.to_user,
                        "sentiment": validated.sentiment,
                        "label": validated.label,
                    })
                except Exception:
                    # Skip malformed items rather than failing the batch.
                    continue
            return results

        except Exception as exc:
            logger.debug(f"[SocialGraph] Sentiment analysis failed: {exc}")
            return []

    async def get_graph_statistics(
        self, group_id: str
    ) -> Dict[str, Any]:
        """Return summary statistics for a group's social graph."""
        graph = await self.build_social_graph(group_id)
        stats: Dict[str, Any] = {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "density": 0.0,
            "communities": 0,
        }

        if graph.number_of_nodes() > 1:
            stats["density"] = round(nx.density(graph), 4)
            communities = await self.detect_communities(group_id)
            stats["communities"] = len(communities)

        return stats
