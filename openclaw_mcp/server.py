#!/usr/bin/env python3
"""SafePlate SCC — MCP Server for OpenClaw Integration.

This MCP server exposes SafePlate's food safety intelligence as tools
that OpenClaw agents (powered by NVIDIA Nemotron) can call.

Usage with OpenClaw:
  1. Add this as an MCP server in your OpenClaw config
  2. The agent can then call safeplate_search, safeplate_check, safeplate_stats
  3. Nemotron reasons over the results to answer food safety questions

Protocol: JSON-RPC over stdio (MCP standard)
"""

import json
import sys
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "safeplate.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ==================== Tool Implementations ====================

def handle_safeplate_search(args: dict) -> dict:
    """Search restaurants by name, city, or cuisine type."""
    query = args.get("query", "")
    limit = min(args.get("limit", 10), 20)

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT name, address, city, risk_score, risk_level,
                      avg_score, critical_violations, total_violations,
                      last_inspection_score, business_id
               FROM businesses
               WHERE UPPER(name) LIKE UPPER(?) OR UPPER(address) LIKE UPPER(?) OR UPPER(city) LIKE UPPER(?)
               ORDER BY risk_score DESC
               LIMIT ?""",
            (f"%{query}%", f"%{query}%", f"%{query}%", limit),
        ).fetchall()

        if not rows:
            return {"results": [], "message": f"No restaurants found matching '{query}'."}

        results = []
        for r in rows:
            risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(r["risk_level"], "⚪")
            results.append({
                "name": r["name"],
                "address": f"{r['address']}, {r['city']}",
                "risk_score": r["risk_score"],
                "risk_level": f"{risk_emoji} {r['risk_level'].upper()}",
                "avg_inspection_score": round(r["avg_score"] or 0),
                "critical_violations": r["critical_violations"] or 0,
                "total_violations": r["total_violations"] or 0,
                "last_inspection_score": r["last_inspection_score"],
                "business_id": r["business_id"],
            })

        return {
            "results": results,
            "count": len(results),
            "message": f"Found {len(results)} restaurants matching '{query}'.",
        }
    finally:
        conn.close()


def handle_safeplate_check(args: dict) -> dict:
    """Get detailed safety report for a specific restaurant."""
    name = args.get("name", "")

    conn = get_db()
    try:
        # Find the restaurant
        biz = conn.execute(
            "SELECT * FROM businesses WHERE UPPER(name) LIKE UPPER(?) LIMIT 1",
            (f"%{name}%",),
        ).fetchone()

        if not biz:
            return {"error": f"Restaurant '{name}' not found. Try a different search term."}

        # Get recent violations
        violations = conn.execute(
            """SELECT v.description, v.code, v.critical, v.violation_comment
               FROM violations v
               WHERE v.business_id = ?
               ORDER BY v.id DESC LIMIT 10""",
            (biz["business_id"],),
        ).fetchall()

        # Get inspection history
        inspections = conn.execute(
            """SELECT date, score, type FROM inspections
               WHERE business_id = ? AND score IS NOT NULL
               ORDER BY date DESC LIMIT 5""",
            (biz["business_id"],),
        ).fetchall()

        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(biz["risk_level"], "⚪")

        violation_list = []
        for v in violations:
            violation_list.append({
                "type": "⚠️ CRITICAL" if v["critical"] else "ℹ️ Minor",
                "description": v["description"],
                "details": (v["violation_comment"] or "")[:300],
            })

        inspection_list = []
        for i in inspections:
            inspection_list.append({
                "date": i["date"],
                "score": i["score"],
                "type": i["type"],
            })

        return {
            "restaurant": {
                "name": biz["name"],
                "address": f"{biz['address']}, {biz['city']}, {biz['state']} {biz['postal_code']}",
                "phone": biz["phone_number"],
                "risk_score": biz["risk_score"],
                "risk_level": f"{risk_emoji} {biz['risk_level'].upper()}",
                "avg_inspection_score": round(biz["avg_score"] or 0),
                "total_inspections": biz["total_inspections"],
                "total_violations": biz["total_violations"],
                "critical_violations": biz["critical_violations"],
            },
            "recent_violations": violation_list,
            "inspection_history": inspection_list,
            "safety_summary": (
                f"{biz['name']} has a risk score of {biz['risk_score']}/100 "
                f"({biz['risk_level']}). It has had {biz['total_violations']} total violations "
                f"({biz['critical_violations']} critical) across {biz['total_inspections']} inspections, "
                f"with an average score of {round(biz['avg_score'] or 0)}/100."
            ),
        }
    finally:
        conn.close()


def handle_safeplate_stats(args: dict) -> dict:
    """Get aggregate food safety statistics for Santa Clara County."""
    city = args.get("city", None)

    conn = get_db()
    try:
        where = ""
        params = []
        if city:
            where = "WHERE UPPER(city) = UPPER(?)"
            params = [city]

        total = conn.execute(f"SELECT COUNT(*) FROM businesses {where}", params).fetchone()[0]
        avg_risk = conn.execute(f"SELECT AVG(risk_score) FROM businesses {where}", params).fetchone()[0]

        risk_counts = {}
        for row in conn.execute(
            f"SELECT risk_level, COUNT(*) as cnt FROM businesses {where} GROUP BY risk_level", params
        ):
            risk_counts[row["risk_level"]] = row["cnt"]

        total_violations = conn.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
        critical_violations = conn.execute("SELECT COUNT(*) FROM violations WHERE critical = 1").fetchone()[0]

        # Top violation categories
        top_violations = []
        for row in conn.execute(
            "SELECT description, COUNT(*) as cnt FROM violations GROUP BY description ORDER BY cnt DESC LIMIT 5"
        ):
            top_violations.append({"category": row["description"], "count": row["cnt"]})

        scope = f"in {city}" if city else "in Santa Clara County"
        return {
            "scope": scope,
            "total_restaurants": total,
            "average_risk_score": round(avg_risk or 0, 1),
            "risk_distribution": {
                "🟢 low_risk": risk_counts.get("low", 0),
                "🟡 medium_risk": risk_counts.get("medium", 0),
                "🔴 high_risk": risk_counts.get("high", 0),
            },
            "total_violations_recorded": total_violations,
            "critical_violations": critical_violations,
            "top_violation_categories": top_violations,
            "summary": (
                f"{scope}: {total} food businesses tracked, "
                f"average risk score {round(avg_risk or 0, 1)}/100. "
                f"{risk_counts.get('high', 0)} high-risk establishments."
            ),
        }
    finally:
        conn.close()

def handle_safeplate_find_safest_nearby(args: dict) -> dict:
    """Find the safest restaurants near given GPS coordinates."""
    import math

    lat = args.get("latitude")
    lon = args.get("longitude")
    radius_km = args.get("radius_km", 0.5)  # Default 500m walking distance
    limit = min(args.get("limit", 5), 10)

    if lat is None or lon is None:
        return {"error": "latitude and longitude are required"}

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    conn = get_db()
    try:
        # Use bounding box for fast SQL filter, then Haversine in Python
        delta = radius_km / 111.0  # ~111km per degree latitude
        rows = conn.execute(
            """SELECT name, address, city, risk_score, risk_level,
                      avg_score, critical_violations, total_violations,
                      latitude, longitude, business_id
               FROM businesses
               WHERE latitude IS NOT NULL AND longitude IS NOT NULL
               AND latitude BETWEEN ? AND ?
               AND longitude BETWEEN ? AND ?
               ORDER BY risk_score ASC""",
            (lat - delta, lat + delta, lon - delta * 1.3, lon + delta * 1.3),
        ).fetchall()

        results = []
        for r in rows:
            dist = haversine(lat, lon, r["latitude"], r["longitude"])
            if dist <= radius_km:
                risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(r["risk_level"], "⚪")
                results.append({
                    "name": r["name"],
                    "address": f"{r['address']}, {r['city']}",
                    "risk_score": r["risk_score"],
                    "risk_level": f"{risk_emoji} {r['risk_level'].upper()}",
                    "avg_inspection_score": round(r["avg_score"] or 0),
                    "critical_violations": r["critical_violations"] or 0,
                    "distance_meters": round(dist * 1000),
                    "coordinates": {"lat": r["latitude"], "lon": r["longitude"]},
                    "business_id": r["business_id"],
                })

        # Sort by risk_score ascending (safest first)
        results.sort(key=lambda x: x["risk_score"])
        results = results[:limit]

        return {
            "search_center": {"lat": lat, "lon": lon},
            "radius_km": radius_km,
            "results": results,
            "count": len(results),
            "message": (
                f"Found {len(results)} restaurants within {radius_km}km. "
                f"Sorted by safety (lowest risk score first)."
            ),
        }
    finally:
        conn.close()


# ==================== MCP Protocol ====================

TOOLS = [
    {
        "name": "safeplate_search",
        "description": (
            "Search for restaurants in Santa Clara County by name, address, or city. "
            "Returns risk scores, inspection scores, and violation counts. "
            "Use this when someone asks about places to eat or restaurant safety."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Restaurant name, cuisine type, street name, or city to search for",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10, max 20)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "safeplate_check",
        "description": (
            "Get a detailed food safety report for a specific restaurant, including "
            "its full violation history, inspection scores over time, and risk assessment. "
            "Use this when someone asks 'Is it safe to eat at X?' or wants details about a place."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Restaurant name to look up",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "safeplate_stats",
        "description": (
            "Get aggregate food safety statistics for Santa Clara County or a specific city. "
            "Shows risk distribution, top violations, and overall safety metrics. "
            "Use this for general questions about food safety in the area."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Optional city name to filter stats (e.g. 'SAN JOSE', 'SANTA CLARA')",
                },
            },
        },
    },
    {
        "name": "safeplate_find_safest_nearby",
        "description": (
            "Find the safest restaurants near given GPS coordinates. Uses spatial search "
            "to find establishments within walking/driving distance, sorted by safety score. "
            "Use this when someone says 'find safe restaurants near me' or gives a location."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "number",
                    "description": "GPS latitude of the search center",
                },
                "longitude": {
                    "type": "number",
                    "description": "GPS longitude of the search center",
                },
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in kilometers (default 0.5 = walking distance)",
                    "default": 0.5,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 5, max 10)",
                    "default": 5,
                },
            },
            "required": ["latitude", "longitude"],
        },
    },
]

TOOL_HANDLERS = {
    "safeplate_search": handle_safeplate_search,
    "safeplate_check": handle_safeplate_check,
    "safeplate_stats": handle_safeplate_stats,
    "safeplate_find_safest_nearby": handle_safeplate_find_safest_nearby,
}


def handle_request(request: dict) -> dict:
    """Handle a single MCP JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "safeplate-scc",
                    "version": "1.0.0",
                    "description": "AI Food Safety Intelligence for Santa Clara County — powered by NVIDIA Nemotron on DGX Spark",
                },
            },
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    elif method == "tools/call":
        tool_name = request.get("params", {}).get("name", "")
        tool_args = request.get("params", {}).get("arguments", {})

        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                },
            }

        try:
            result = handler(tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "isError": True,
                },
            }

    elif method == "notifications/initialized":
        return None  # Notification, no response needed

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def main():
    """Run the MCP server over stdio."""
    print("SafePlate MCP Server starting...", file=sys.stderr)
    print(f"Database: {DB_PATH}", file=sys.stderr)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            response = handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            error_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            sys.stdout.write(json.dumps(error_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    # If run directly with --test flag, demo the tools
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=== SafePlate MCP Tool Test ===\n")

        print("1. Search for 'taco bell':")
        result = handle_safeplate_search({"query": "taco bell", "limit": 3})
        print(json.dumps(result, indent=2))

        print("\n2. Check a specific restaurant:")
        if result["results"]:
            name = result["results"][0]["name"]
            detail = handle_safeplate_check({"name": name})
            print(json.dumps(detail, indent=2))

        print("\n3. County-wide stats:")
        stats = handle_safeplate_stats({})
        print(json.dumps(stats, indent=2))

        print("\n4. City stats for SAN JOSE:")
        stats = handle_safeplate_stats({"city": "SAN JOSE"})
        print(json.dumps(stats, indent=2))

        print("\n5. Find safest restaurants near San Jose Convention Center:")
        nearby = handle_safeplate_find_safest_nearby({
            "latitude": 37.3305,
            "longitude": -121.8883,
            "radius_km": 0.5,
            "limit": 3
        })
        print(json.dumps(nearby, indent=2))
    else:
        main()
