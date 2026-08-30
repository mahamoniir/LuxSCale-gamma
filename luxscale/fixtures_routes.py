"""
/api/fixtures/*  ·  smart fixture catalog — merges the calc-engine fixture map
(assets/<active_fixture_map_basename()>) with the real product catalog
(assets/fixtures_online.json) so one call returns both the IES reference AND the
sellable product info (name, images, spec sheet) for each fixture.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from luxscale import fixtures_lookup as fl

fixtures_bp = Blueprint("fixtures_api", __name__, url_prefix="/api/fixtures")

@fixtures_bp.route("", methods=["GET"])
def api_fixtures_list():
    """
    Full smart catalog. Optional query filters:
      type       substring match on api_luminaire_name, e.g. ?type=flood
      q          substring match across fixture name + matched product name/title
      min_power  minimum power_w
      max_power  maximum power_w
    """
    type_filter = request.args.get("type")
    q = request.args.get("q")
    min_power = request.args.get("min_power", type=float)
    max_power = request.args.get("max_power", type=float)
    items = fl.list_fixtures(type_filter=type_filter, q=q, min_power=min_power, max_power=max_power)
    return jsonify({"status": "success", "count": len(items), "fixtures": items})


@fixtures_bp.route("/types", methods=["GET"])
def api_fixtures_types():
    return jsonify({"status": "success", "types": fl.list_fixture_types()})


@fixtures_bp.route("/resolve", methods=["GET"])
def api_fixtures_resolve():
    """
    Exact lookup by name + power — same match the calculation engine itself uses,
    enriched with product info. Query: ?name=SC%20flood%20light%20exterior&power_w=100
    """
    name = request.args.get("name", "").strip()
    power_w = request.args.get("power_w", type=float)
    if not name or power_w is None:
        return jsonify({"status": "error", "message": "name and power_w are required"}), 400
    fixture = fl.get_fixture(name, power_w)
    if not fixture:
        return jsonify(
            {"status": "error", "message": "No fixture entry for that name + power_w", "name": name, "power_w": power_w}
        ), 404
    return jsonify({"status": "success", "fixture": fixture})


@fixtures_bp.route("/products", methods=["GET"])
def api_fixtures_products():
    """Raw storefront catalog passthrough. Optional ?category_id=high-power|indoor|solar-aio."""
    category_id = request.args.get("category_id")
    return jsonify(
        {
            "status": "success",
            "categories": fl.list_product_categories(),
            "products": fl.list_products(category_id=category_id),
        }
    )
