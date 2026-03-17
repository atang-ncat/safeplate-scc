#!/usr/bin/env python3
"""SafePlate SCC — FastAPI Backend."""

import sqlite3
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import llm_service

DB_PATH = os.path.join(os.path.dirname(__file__), "safeplate.db")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start LLM server in background on app startup."""
    import threading
    print("Starting LLM server in background...")
    t = threading.Thread(target=llm_service.start_llm_server, daemon=True)
    t.start()
    yield
    print("Stopping LLM server...")
    llm_service.stop_llm_server()


app = FastAPI(title="SafePlate SCC", lifespan=lifespan)


# ---------- API Models ----------

class ChatRequest(BaseModel):
    message: str
    restaurant_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    sources: list[dict] | None = None


# ---------- API Endpoints ----------

@app.get("/api/stats")
def get_stats():
    """Get aggregate food safety statistics."""
    conn = get_db()
    try:
        stats = {}
        stats["total_businesses"] = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
        stats["total_inspections"] = conn.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
        stats["total_violations"] = conn.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
        stats["critical_violations"] = conn.execute("SELECT COUNT(*) FROM violations WHERE critical = 1").fetchone()[0]
        stats["avg_inspection_score"] = round(
            conn.execute("SELECT AVG(score) FROM inspections WHERE score IS NOT NULL").fetchone()[0] or 0, 1
        )

        # Risk distribution
        risk_dist = {}
        for row in conn.execute("SELECT risk_level, COUNT(*) as cnt FROM businesses GROUP BY risk_level"):
            risk_dist[row["risk_level"]] = row["cnt"]
        stats["risk_distribution"] = risk_dist

        # Top violation types
        top_violations = []
        for row in conn.execute(
            "SELECT description, COUNT(*) as cnt FROM violations GROUP BY description ORDER BY cnt DESC LIMIT 5"
        ):
            top_violations.append({"description": row["description"], "count": row["cnt"]})
        stats["top_violations"] = top_violations

        # Cities
        cities = []
        for row in conn.execute(
            "SELECT city, COUNT(*) as cnt FROM businesses WHERE city != '' GROUP BY city ORDER BY cnt DESC LIMIT 10"
        ):
            cities.append({"city": row["city"], "count": row["cnt"]})
        stats["top_cities"] = cities

        return stats
    finally:
        conn.close()


@app.get("/api/restaurants")
def get_restaurants(
    limit: int = Query(default=500, le=10000),
    offset: int = Query(default=0, ge=0),
    city: str = Query(default=None),
    risk_level: str = Query(default=None),
    search: str = Query(default=None),
    min_risk: float = Query(default=None),
    max_risk: float = Query(default=None),
):
    """Get list of restaurants with filters."""
    conn = get_db()
    try:
        query = """
            SELECT business_id, name, address, city, state, postal_code,
                   latitude, longitude, risk_score, risk_level,
                   total_inspections, total_violations, critical_violations,
                   avg_score, last_inspection_date, last_inspection_score
            FROM businesses
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """
        params = []

        if city:
            query += " AND UPPER(city) = UPPER(?)"
            params.append(city)
        if risk_level:
            query += " AND risk_level = ?"
            params.append(risk_level)
        if search:
            query += " AND (UPPER(name) LIKE UPPER(?) OR UPPER(address) LIKE UPPER(?))"
            params.extend([f"%{search}%", f"%{search}%"])
        if min_risk is not None:
            query += " AND risk_score >= ?"
            params.append(min_risk)
        if max_risk is not None:
            query += " AND risk_score <= ?"
            params.append(max_risk)

        query += " ORDER BY risk_score DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/restaurants/geo")
def get_restaurants_geo():
    """Get all restaurants with coordinates for map display (minimal payload)."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT business_id, name, address, latitude, longitude, risk_score, risk_level,
                   city, avg_score, critical_violations, total_violations,
                   last_inspection_score
            FROM businesses
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
              AND latitude != 0 AND longitude != 0
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/restaurants/{business_id}")
def get_restaurant_detail(business_id: str):
    """Get full detail for a single restaurant."""
    conn = get_db()
    try:
        biz = conn.execute(
            "SELECT * FROM businesses WHERE business_id = ?", (business_id,)
        ).fetchone()
        if not biz:
            raise HTTPException(status_code=404, detail="Restaurant not found")

        # Get inspections
        inspections = conn.execute(
            "SELECT * FROM inspections WHERE business_id = ? ORDER BY date DESC LIMIT 20",
            (business_id,),
        ).fetchall()

        # Get recent violations
        violations = conn.execute(
            """SELECT v.* FROM violations v
               JOIN inspections i ON v.inspection_id = i.inspection_id
               WHERE v.business_id = ?
               ORDER BY i.date DESC LIMIT 30""",
            (business_id,),
        ).fetchall()

        return {
            "business": dict(biz),
            "inspections": [dict(i) for i in inspections],
            "violations": [dict(v) for v in violations],
        }
    finally:
        conn.close()


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Chat with the AI about food safety — with agentic reasoning trace."""
    conn = get_db()
    try:
        context_parts = []
        trace_steps = []  # Reasoning trace for the UI

        # Step 1: Intent recognition
        trace_steps.append({
            "step": "intent",
            "icon": "🧠",
            "text": "Analyzing query intent..."
        })

        # Step 2: If a specific restaurant is provided via context
        if request.restaurant_id:
            trace_steps.append({
                "step": "context",
                "icon": "📍",
                "text": f"Restaurant context detected: {request.restaurant_id}"
            })
            biz = conn.execute(
                "SELECT * FROM businesses WHERE business_id = ?",
                (request.restaurant_id,),
            ).fetchone()
            if biz:
                trace_steps.append({
                    "step": "lookup",
                    "icon": "🔍",
                    "text": f"Found: {biz['name']} — Risk {biz['risk_score']}/100 ({biz['risk_level']})"
                })
                context_parts.append(
                    f"Restaurant: {biz['name']}, {biz['address']}, {biz['city']}\n"
                    f"Risk Score: {biz['risk_score']}/100 ({biz['risk_level']})\n"
                    f"Avg Inspection Score: {biz['avg_score']}/100\n"
                    f"Total Violations: {biz['total_violations']} ({biz['critical_violations']} critical)"
                )

                violations = conn.execute(
                    """SELECT v.description, v.violation_comment, v.critical
                       FROM violations v WHERE v.business_id = ?
                       ORDER BY v.id DESC LIMIT 5""",
                    (request.restaurant_id,),
                ).fetchall()
                if violations:
                    trace_steps.append({
                        "step": "violations",
                        "icon": "⚠️",
                        "text": f"Retrieved {len(violations)} recent violations for analysis"
                    })
                for v in violations:
                    crit = "⚠️ CRITICAL" if v["critical"] else ""
                    context_parts.append(f"- {crit} {v['description']}: {v['violation_comment'][:200]}")

        # Step 3: Extract restaurant name from natural language
        import re
        msg = request.message.strip()
        name_extract = re.sub(
            r'(?i)^(\[Currently viewing:.*?\]\s*|is it safe to eat at|tell me about|how safe is|check|analyze|'
            r'what about|search for|find|look up|give me .* analysis.*? of|'
            r'give me .* analysis.*? for|should i eat at|review)\s*',
            '', msg
        )
        name_extract = re.sub(r'[\?\!\.]+\s*(give me.*|full.*|safety.*)?$', '', name_extract, flags=re.IGNORECASE).strip()

        # Step 4: Database search
        search_terms = [name_extract]
        stopwords = {'the', 'and', 'for', 'are', 'its', 'how', 'what', 'this', 'that', 'with', 'safe', 'eat', 'food', 'place', 'there'}
        words = [w for w in name_extract.split() if len(w) >= 3 and w.lower() not in stopwords]
        if len(words) > 1:
            search_terms.append(' '.join(words))

        matches = []
        for term in search_terms:
            if not term:
                continue
            trace_steps.append({
                "step": "search",
                "icon": "🔎",
                "text": f"Calling safeplate_search(\"{term}\")"
            })
            matches = conn.execute(
                """SELECT name, city, address, risk_score, risk_level, avg_score,
                          critical_violations, total_violations, business_id
                   FROM businesses
                   WHERE UPPER(name) LIKE UPPER(?) OR UPPER(address) LIKE UPPER(?)
                   ORDER BY risk_score DESC LIMIT 5""",
                (f"%{term}%", f"%{term}%"),
            ).fetchall()
            if matches:
                trace_steps.append({
                    "step": "result",
                    "icon": "✅",
                    "text": f"Found {len(matches)} matching restaurant(s)"
                })
                break

        if matches:
            context_parts.append("\nMatching restaurants found:")
            for m in matches:
                context_parts.append(
                    f"- {m['name']} at {m['address']}, {m['city']}: Risk {m['risk_score']}/100 "
                    f"({m['risk_level']}), Avg Inspection Score: {m['avg_score']}/100, "
                    f"{m['critical_violations']} critical violations, {m['total_violations']} total violations"
                )
                violations = conn.execute(
                    """SELECT v.description, v.violation_comment, v.critical
                       FROM violations v WHERE v.business_id = ?
                       ORDER BY v.id DESC LIMIT 5""",
                    (m['business_id'],),
                ).fetchall()
                if violations:
                    trace_steps.append({
                        "step": "violations",
                        "icon": "📋",
                        "text": f"Analyzing {len(violations)} violations for {m['name']}"
                    })
                    context_parts.append(f"  Recent violations for {m['name']}:")
                    for v in violations:
                        crit = "⚠️ CRITICAL" if v["critical"] else "Minor"
                        comment = (v['violation_comment'] or '')[:150]
                        context_parts.append(f"    - [{crit}] {v['description']}: {comment}")

        # Step 5: General stats
        stats = conn.execute(
            "SELECT COUNT(*) as total, AVG(risk_score) as avg_risk FROM businesses"
        ).fetchone()
        context_parts.append(
            f"\nSanta Clara County: {stats['total']} food businesses, "
            f"average risk score: {round(stats['avg_risk'], 1)}"
        )

        # Step 6: Nemotron inference
        trace_steps.append({
            "step": "inference",
            "icon": "🤖",
            "text": "Nemotron-Nano-30B generating safety analysis..."
        })

        context = "\n".join(context_parts)
        response = await llm_service.answer_question(request.message, context)

        # Strip thinking tags from Nemotron response
        if '</think>' in response:
            response = response.split('</think>')[-1].strip()

        return JSONResponse({
            "response": response,
            "trace": trace_steps,
            "sources": None,
        })
    finally:
        conn.close()


# ---------- Static Files & SPA ----------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    """Serve the main web app."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
