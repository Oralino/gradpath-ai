"""Query router (T-006): picks traditional RAG or the agentic workflow and records why."""

from gradpath.router.route import route_request
from gradpath.router.schemas import RouteDecision, RouteRequest

__all__ = ["RouteDecision", "RouteRequest", "route_request"]
