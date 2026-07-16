from flask import Blueprint, request
from flask_login import login_required

from ..extensions import limiter
from ..services import place_service
from ..utils.response import success_response

place_bp = Blueprint("places", __name__)


@place_bp.get("/search")
@login_required
@limiter.limit("20 per minute")
def search_places():
    query = request.args.get("q", "")
    region = request.args.get("region")
    results = place_service.search_places(query, region)
    return success_response({"places": results})
