"""Stable HTTP API for using Self Learning as a capability hub."""

from __future__ import annotations

from quart import Blueprint, request

from ..dependencies import get_container
from ..middleware.hub_aspects import HubApiError, hub_route, hub_success
from ..services.hub_service import HubService

hub_bp = Blueprint("hub", __name__, url_prefix="/api/hub/v1")


def _service() -> HubService:
    return HubService(get_container())


async def _body() -> dict:
    data = await request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@hub_bp.route("/manifest", methods=["GET"])
@hub_route
async def manifest():
    """Return the stable API contract and capability map."""
    return hub_success(_service().manifest())


@hub_bp.route("/status", methods=["GET"])
@hub_route
async def status():
    """Return runtime health and delegation state."""
    return hub_success(await _service().status())


@hub_bp.route("/context", methods=["POST"])
@hub_route
async def build_context():
    """Build prompt-ready context for companion plugins."""
    try:
        return hub_success(await _service().build_context(await _body()))
    except ValueError as exc:
        raise HubApiError(str(exc), 400, "invalid_request") from exc


@hub_bp.route("/memories/remember", methods=["POST"])
@hub_route
async def remember():
    """Persist a selected memory and link it into learning stores."""
    try:
        return hub_success(await _service().remember(await _body()), message="remembered")
    except ValueError as exc:
        raise HubApiError(str(exc), 400, "invalid_request") from exc


@hub_bp.route("/messages/ingest", methods=["POST"])
@hub_route
async def ingest_message():
    """Ingest one external message into the learning pipeline."""
    try:
        return hub_success(await _service().ingest_message(await _body()), message="ingested")
    except ValueError as exc:
        raise HubApiError(str(exc), 400, "invalid_request") from exc


@hub_bp.route("/learning/trigger", methods=["POST"])
@hub_route
async def trigger_learning():
    """Trigger learning for a group."""
    try:
        return hub_success(await _service().trigger_learning(await _body()), message="learning_started")
    except ValueError as exc:
        raise HubApiError(str(exc), 400, "invalid_request") from exc


@hub_bp.route("/reviews", methods=["GET"])
@hub_route
async def reviews():
    """List review queue items."""
    limit = HubService._bounded_int(request.args.get("limit"), 1, 100, 50)
    offset = HubService._bounded_int(request.args.get("offset"), 0, 100000, 0)
    status_filter = str(request.args.get("status") or "pending")
    return hub_success(await _service().reviews(limit=limit, offset=offset, status_filter=status_filter))


@hub_bp.route("/reviews/<review_id>/decision", methods=["POST"])
@hub_route
async def decide_review(review_id: str):
    """Approve or reject a review queue item."""
    try:
        return hub_success(await _service().decide_review(review_id, await _body()))
    except ValueError as exc:
        raise HubApiError(str(exc), 400, "invalid_request") from exc


@hub_bp.route("/graphs/memory", methods=["GET"])
@hub_route
async def memory_graph():
    """Return memory graph data."""
    limit = HubService._bounded_int(request.args.get("limit"), 10, 300, 120)
    group_id = request.args.get("group_id")
    return hub_success(await _service().memory_graph(group_id=group_id, limit=limit))


@hub_bp.route("/graphs/knowledge", methods=["GET"])
@hub_route
async def knowledge_graph():
    """Return knowledge graph data."""
    limit = HubService._bounded_int(request.args.get("limit"), 10, 300, 120)
    group_id = request.args.get("group_id")
    return hub_success(await _service().knowledge_graph(group_id=group_id, limit=limit))


@hub_bp.route("/metrics", methods=["GET"])
@hub_route
async def metrics():
    """Return hub-level metrics for a group."""
    group_id = str(request.args.get("group_id") or "default")
    return hub_success(await _service().metrics(group_id=group_id))
