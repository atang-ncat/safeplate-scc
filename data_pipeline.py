#!/usr/bin/env python3
"""SafePlate SCC — Data Pipeline: CSV → SQLite with risk scoring."""

import csv
import sqlite3
import os
import math
from datetime import datetime, timedelta

DATA_DIR = os.path.expanduser("~/data")
DB_PATH = os.path.join(os.path.dirname(__file__), "safeplate.db")

BUSINESS_CSV = os.path.join(DATA_DIR, "SCC_DEH_Food_Data_BUSINESS_20260306.csv")
INSPECTIONS_CSV = os.path.join(DATA_DIR, "SCC_DEH_Food_Data_INSPECTIONS_20260306.csv")
VIOLATIONS_CSV = os.path.join(DATA_DIR, "SCC_DEH_Food_Data_VIOLATIONS_20260306.csv")


def create_schema(conn):
    """Create database tables."""
    conn.executescript("""
        DROP TABLE IF EXISTS violations;
        DROP TABLE IF EXISTS inspections;
        DROP TABLE IF EXISTS businesses;

        CREATE TABLE businesses (
            business_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT,
            city TEXT,
            state TEXT,
            postal_code TEXT,
            latitude REAL,
            longitude REAL,
            phone_number TEXT,
            risk_score REAL DEFAULT 50.0,
            risk_level TEXT DEFAULT 'medium',
            total_inspections INTEGER DEFAULT 0,
            total_violations INTEGER DEFAULT 0,
            critical_violations INTEGER DEFAULT 0,
            avg_score REAL DEFAULT 0.0,
            last_inspection_date TEXT,
            last_inspection_score INTEGER
        );

        CREATE TABLE inspections (
            inspection_id TEXT PRIMARY KEY,
            business_id TEXT NOT NULL,
            date TEXT,
            score INTEGER,
            result TEXT,
            description TEXT,
            type TEXT,
            inspection_comment TEXT,
            FOREIGN KEY (business_id) REFERENCES businesses(business_id)
        );

        CREATE TABLE violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspection_id TEXT NOT NULL,
            business_id TEXT,
            description TEXT,
            code TEXT,
            critical INTEGER DEFAULT 0,
            violation_comment TEXT,
            FOREIGN KEY (inspection_id) REFERENCES inspections(inspection_id)
        );

        CREATE INDEX idx_inspections_business ON inspections(business_id);
        CREATE INDEX idx_violations_inspection ON violations(inspection_id);
        CREATE INDEX idx_violations_business ON violations(business_id);
        CREATE INDEX idx_businesses_city ON businesses(city);
        CREATE INDEX idx_businesses_name ON businesses(name);
        CREATE INDEX idx_businesses_risk ON businesses(risk_score);
    """)


def load_businesses(conn):
    """Load business data from CSV."""
    print("Loading businesses...")
    count = 0
    with open(BUSINESS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat = None
            lon = None
            try:
                lat = float(row.get("latitude", "")) if row.get("latitude") else None
                lon = float(row.get("longitude", "")) if row.get("longitude") else None
            except (ValueError, TypeError):
                pass

            conn.execute(
                """INSERT OR REPLACE INTO businesses
                   (business_id, name, address, city, state, postal_code,
                    latitude, longitude, phone_number)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row.get("business_id", "").strip(),
                    row.get("name", "").strip(),
                    row.get("address", "").strip(),
                    row.get("CITY", "").strip(),
                    row.get("STATE", "").strip(),
                    row.get("postal_code", "").strip(),
                    lat, lon,
                    row.get("phone_number", "").strip(),
                ),
            )
            count += 1
    conn.commit()
    print(f"  → Loaded {count} businesses")


def load_inspections(conn):
    """Load inspection data from CSV."""
    print("Loading inspections...")
    count = 0
    with open(INSPECTIONS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            score = None
            try:
                score = int(row.get("SCORE", "")) if row.get("SCORE") else None
            except (ValueError, TypeError):
                pass

            conn.execute(
                """INSERT OR REPLACE INTO inspections
                   (inspection_id, business_id, date, score, result,
                    description, type, inspection_comment)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row.get("inspection_id", "").strip(),
                    row.get("business_id", "").strip(),
                    row.get("date", "").strip(),
                    score,
                    row.get("result", "").strip(),
                    row.get("description", "").strip(),
                    row.get("type", "").strip(),
                    row.get("inspection_comment", "").strip(),
                ),
            )
            count += 1
    conn.commit()
    print(f"  → Loaded {count} inspections")


def load_violations(conn):
    """Load violation data from CSV."""
    print("Loading violations...")
    # First, build a mapping of inspection_id -> business_id
    insp_to_biz = {}
    cur = conn.execute("SELECT inspection_id, business_id FROM inspections")
    for iid, bid in cur.fetchall():
        insp_to_biz[iid] = bid

    count = 0
    with open(VIOLATIONS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            iid = row.get("inspection_id", "").strip()
            is_critical = 1 if row.get("critical", "").strip().lower() == "true" else 0

            conn.execute(
                """INSERT INTO violations
                   (inspection_id, business_id, description, code, critical, violation_comment)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    iid,
                    insp_to_biz.get(iid, ""),
                    row.get("DESCRIPTION", "").strip(),
                    row.get("code", "").strip(),
                    is_critical,
                    row.get("violation_comment", "").strip(),
                ),
            )
            count += 1
    conn.commit()
    print(f"  → Loaded {count} violations")


def compute_risk_scores(conn):
    """Compute risk scores for each business.

    Risk Score formula (0-100, lower = safer):
    - Base from avg inspection score (inverted: 100 - avg_score)
    - Critical violation penalty: +2 per critical violation
    - Non-critical violation rate: +0.5 per violation
    - Recency boost: recent bad inspections weigh more
    - Clamped to 0-100 range
    """
    print("Computing risk scores...")

    # Aggregate inspection stats per business
    conn.execute("""
        UPDATE businesses SET
            total_inspections = (
                SELECT COUNT(*) FROM inspections WHERE inspections.business_id = businesses.business_id
            ),
            avg_score = (
                SELECT COALESCE(AVG(score), 0) FROM inspections
                WHERE inspections.business_id = businesses.business_id AND score IS NOT NULL
            ),
            last_inspection_date = (
                SELECT MAX(date) FROM inspections
                WHERE inspections.business_id = businesses.business_id
            ),
            last_inspection_score = (
                SELECT score FROM inspections
                WHERE inspections.business_id = businesses.business_id
                ORDER BY date DESC LIMIT 1
            )
    """)

    # Aggregate violation stats per business
    conn.execute("""
        UPDATE businesses SET
            total_violations = (
                SELECT COUNT(*) FROM violations WHERE violations.business_id = businesses.business_id
            ),
            critical_violations = (
                SELECT COUNT(*) FROM violations
                WHERE violations.business_id = businesses.business_id AND critical = 1
            )
    """)

    # Compute risk score
    cur = conn.execute("""
        SELECT business_id, avg_score, total_inspections,
               total_violations, critical_violations, last_inspection_score
        FROM businesses
    """)

    updates = []
    for row in cur.fetchall():
        bid, avg_score, total_insp, total_viol, crit_viol, last_score = row

        if total_insp == 0:
            risk = 50.0  # Unknown risk for uninspected businesses
        else:
            # Base risk from inspection scores (inverted)
            base_risk = max(0, 100 - (avg_score or 0))

            # Violation penalties
            viol_rate = total_viol / max(total_insp, 1)
            crit_penalty = min(crit_viol * 2, 30)  # Cap at 30 points
            viol_penalty = min(viol_rate * 0.5, 15)  # Cap at 15 points

            # Recent inspection factor
            recent_factor = 0
            if last_score is not None and last_score < 70:
                recent_factor = (70 - last_score) * 0.3

            risk = base_risk + crit_penalty + viol_penalty + recent_factor
            risk = max(0, min(100, risk))  # Clamp to 0-100

        # Determine risk level
        if risk <= 25:
            level = "low"
        elif risk <= 50:
            level = "medium"
        else:
            level = "high"

        updates.append((round(risk, 1), level, bid))

    conn.executemany(
        "UPDATE businesses SET risk_score = ?, risk_level = ? WHERE business_id = ?",
        updates,
    )
    conn.commit()
    print(f"  → Computed risk scores for {len(updates)} businesses")

    # Print summary
    cur = conn.execute(
        "SELECT risk_level, COUNT(*) FROM businesses GROUP BY risk_level ORDER BY risk_level"
    )
    for level, count in cur.fetchall():
        emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(level, "⚪")
        print(f"    {emoji} {level}: {count}")


def main():
    print("=" * 60)
    print("SafePlate SCC — Data Pipeline")
    print("=" * 60)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    create_schema(conn)
    load_businesses(conn)
    load_inspections(conn)
    load_violations(conn)
    compute_risk_scores(conn)

    # Final stats
    print("\n" + "=" * 60)
    print("Database ready!")
    cur = conn.execute("SELECT COUNT(*) FROM businesses")
    print(f"  Businesses: {cur.fetchone()[0]}")
    cur = conn.execute("SELECT COUNT(*) FROM inspections")
    print(f"  Inspections: {cur.fetchone()[0]}")
    cur = conn.execute("SELECT COUNT(*) FROM violations")
    print(f"  Violations: {cur.fetchone()[0]}")
    print(f"  Database: {DB_PATH}")
    print(f"  Size: {os.path.getsize(DB_PATH) / 1024 / 1024:.1f} MB")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()
