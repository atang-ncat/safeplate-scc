#!/usr/bin/env python3
"""SafePlate SCC — GPU-Accelerated Data Pipeline using NVIDIA RAPIDS cuDF.

All data loading and risk score computation runs on the Blackwell GPU
via cuDF. Results are written to SQLite for fast query serving.
"""

import sqlite3
import os
import time

# ── GPU-accelerated imports ──
try:
    import cudf
    GPU_AVAILABLE = True
    print("🚀 RAPIDS cuDF detected — using GPU-accelerated pipeline")
except ImportError:
    import pandas as cudf  # Fallback to pandas if no GPU
    GPU_AVAILABLE = False
    print("⚠️  cuDF not found — falling back to pandas (CPU)")

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


def load_and_process_gpu(conn):
    """Load all CSVs on GPU, compute risk scores, and write to SQLite."""

    # ════════════════════════════════════════════════════════════
    # STEP 1: GPU-accelerated CSV loading
    # ════════════════════════════════════════════════════════════
    t0 = time.time()

    print("📊 Loading CSVs onto GPU...")
    biz_df = cudf.read_csv(BUSINESS_CSV, dtype=str)
    insp_df = cudf.read_csv(INSPECTIONS_CSV, dtype=str)
    viol_df = cudf.read_csv(VIOLATIONS_CSV, dtype=str)

    t_load = time.time() - t0
    print(f"  → Loaded {len(biz_df)} businesses, {len(insp_df)} inspections, "
          f"{len(viol_df)} violations in {t_load:.2f}s")

    # ════════════════════════════════════════════════════════════
    # STEP 2: Clean and type-cast on GPU
    # ════════════════════════════════════════════════════════════
    t1 = time.time()
    print("🔧 Cleaning & type-casting on GPU...")

    # Businesses: clean column names and strip whitespace
    biz_df.columns = [c.strip() for c in biz_df.columns]
    for col in ['business_id', 'name', 'address', 'phone_number', 'postal_code']:
        if col in biz_df.columns:
            biz_df[col] = biz_df[col].str.strip()

    # Handle city/state which may be uppercase column names
    if 'CITY' in biz_df.columns:
        biz_df = biz_df.rename(columns={'CITY': 'city'})
    if 'STATE' in biz_df.columns:
        biz_df = biz_df.rename(columns={'STATE': 'state'})
    if 'city' in biz_df.columns:
        biz_df['city'] = biz_df['city'].str.strip()
    if 'state' in biz_df.columns:
        biz_df['state'] = biz_df['state'].str.strip()

    # Convert lat/lon to float on GPU
    if 'latitude' in biz_df.columns:
        biz_df['latitude'] = cudf.to_numeric(biz_df['latitude'], errors='coerce')
    else:
        biz_df['latitude'] = None
    if 'longitude' in biz_df.columns:
        biz_df['longitude'] = cudf.to_numeric(biz_df['longitude'], errors='coerce')
    else:
        biz_df['longitude'] = None

    # Inspections: clean and cast
    insp_df.columns = [c.strip() for c in insp_df.columns]
    for col in ['inspection_id', 'business_id', 'date', 'result', 'description', 'type', 'inspection_comment']:
        if col in insp_df.columns:
            insp_df[col] = insp_df[col].str.strip()

    if 'SCORE' in insp_df.columns:
        insp_df = insp_df.rename(columns={'SCORE': 'score'})
    if 'score' in insp_df.columns:
        insp_df['score'] = cudf.to_numeric(insp_df['score'], errors='coerce')
    else:
        insp_df['score'] = None

    # Violations: clean and cast
    viol_df.columns = [c.strip() for c in viol_df.columns]
    for col in ['inspection_id', 'code', 'violation_comment']:
        if col in viol_df.columns:
            viol_df[col] = viol_df[col].str.strip()
    if 'DESCRIPTION' in viol_df.columns:
        viol_df = viol_df.rename(columns={'DESCRIPTION': 'description'})

    # Critical flag: boolean -> int on GPU
    if 'critical' in viol_df.columns:
        viol_df['critical'] = (viol_df['critical'].str.strip().str.lower() == 'true').astype('int32')
    else:
        viol_df['critical'] = 0

    t_clean = time.time() - t1
    print(f"  → Cleaned in {t_clean:.2f}s")

    # ════════════════════════════════════════════════════════════
    # STEP 3: GPU-accelerated aggregation & risk scoring
    # ════════════════════════════════════════════════════════════
    t2 = time.time()
    print("🧮 Computing risk scores on GPU...")

    # Map inspection -> business for violations
    insp_biz_map = insp_df[['inspection_id', 'business_id']].drop_duplicates()
    viol_df = viol_df.merge(insp_biz_map, on='inspection_id', how='left', suffixes=('_orig', ''))
    # Use the mapped business_id
    if 'business_id_orig' in viol_df.columns:
        viol_df = viol_df.drop(columns=['business_id_orig'])

    # Aggregate inspections per business (all on GPU)
    insp_agg = insp_df.groupby('business_id').agg(
        total_inspections=('inspection_id', 'count'),
        avg_score=('score', 'mean'),
    ).reset_index()

    # Last inspection per business
    insp_sorted = insp_df.sort_values('date', ascending=False)
    last_insp = insp_sorted.groupby('business_id').first().reset_index()[
        ['business_id', 'date', 'score']
    ].rename(columns={'date': 'last_inspection_date', 'score': 'last_inspection_score'})

    # Aggregate violations per business (all on GPU)
    viol_agg = viol_df.groupby('business_id').agg(
        total_violations=('inspection_id', 'count'),
        critical_violations=('critical', 'sum'),
    ).reset_index()

    # Merge all aggregations into businesses (all on GPU)
    biz_df = biz_df.merge(insp_agg, on='business_id', how='left')
    biz_df = biz_df.merge(last_insp, on='business_id', how='left')
    biz_df = biz_df.merge(viol_agg, on='business_id', how='left')

    # Fill NaN
    biz_df['total_inspections'] = biz_df['total_inspections'].fillna(0).astype('int32')
    biz_df['avg_score'] = biz_df['avg_score'].fillna(0)
    biz_df['total_violations'] = biz_df['total_violations'].fillna(0).astype('int32')
    biz_df['critical_violations'] = biz_df['critical_violations'].fillna(0).astype('int32')

    # ── Vectorized risk score computation on GPU ──
    # Base risk from inspection scores (inverted: 100 - avg)
    base_risk = (100 - biz_df['avg_score']).clip(lower=0)

    # Violation penalties
    viol_rate = biz_df['total_violations'] / biz_df['total_inspections'].clip(lower=1)
    crit_penalty = (biz_df['critical_violations'] * 2).clip(upper=30)
    viol_penalty = (viol_rate * 0.5).clip(upper=15)

    # Recent inspection factor
    last_score = biz_df['last_inspection_score'].fillna(100)
    recent_factor = ((70 - last_score) * 0.3).clip(lower=0)

    # Final risk score (all vectorized on GPU)
    risk = (base_risk + crit_penalty + viol_penalty + recent_factor).clip(lower=0, upper=100)

    # Handle uninspected businesses
    no_inspections = biz_df['total_inspections'] == 0
    risk = risk.where(~no_inspections, 50.0)

    biz_df['risk_score'] = risk.round(1)

    # Risk level classification (GPU vectorized)
    biz_df['risk_level'] = 'medium'
    biz_df.loc[biz_df['risk_score'] <= 25, 'risk_level'] = 'low'
    biz_df.loc[biz_df['risk_score'] > 50, 'risk_level'] = 'high'

    t_compute = time.time() - t2
    print(f"  → Risk scores computed in {t_compute:.2f}s")

    # ════════════════════════════════════════════════════════════
    # STEP 4: Transfer from GPU → SQLite
    # ════════════════════════════════════════════════════════════
    t3 = time.time()
    print("💾 Writing to SQLite...")

    # Convert GPU DataFrames to pandas for SQLite insertion
    if GPU_AVAILABLE:
        biz_pd = biz_df.to_pandas()
        insp_pd = insp_df.to_pandas()
        viol_pd = viol_df.to_pandas()
    else:
        biz_pd = biz_df
        insp_pd = insp_df
        viol_pd = viol_df

    # Filter out rows with missing required fields
    biz_pd = biz_pd.dropna(subset=['business_id', 'name'])
    biz_pd = biz_pd[biz_pd['business_id'].str.strip() != '']
    biz_pd = biz_pd[biz_pd['name'].str.strip() != '']
    insp_pd = insp_pd.dropna(subset=['inspection_id', 'business_id'])
    viol_pd = viol_pd.dropna(subset=['inspection_id'])

    # Insert businesses
    biz_cols = ['business_id', 'name', 'address', 'city', 'state', 'postal_code',
                'latitude', 'longitude', 'phone_number', 'risk_score', 'risk_level',
                'total_inspections', 'total_violations', 'critical_violations',
                'avg_score', 'last_inspection_date', 'last_inspection_score']
    for col in biz_cols:
        if col not in biz_pd.columns:
            biz_pd[col] = None

    for _, row in biz_pd.iterrows():
        conn.execute(
            """INSERT OR REPLACE INTO businesses
               (business_id, name, address, city, state, postal_code,
                latitude, longitude, phone_number, risk_score, risk_level,
                total_inspections, total_violations, critical_violations,
                avg_score, last_inspection_date, last_inspection_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(row[c] if str(row[c]) != 'nan' else None for c in biz_cols)
        )
    conn.commit()

    # Insert inspections
    insp_cols = ['inspection_id', 'business_id', 'date', 'score', 'result',
                 'description', 'type', 'inspection_comment']
    for col in insp_cols:
        if col not in insp_pd.columns:
            insp_pd[col] = None

    for _, row in insp_pd.iterrows():
        conn.execute(
            """INSERT OR REPLACE INTO inspections
               (inspection_id, business_id, date, score, result,
                description, type, inspection_comment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(row[c] if str(row[c]) != 'nan' else None for c in insp_cols)
        )
    conn.commit()

    # Insert violations
    viol_cols_db = ['inspection_id', 'business_id', 'description', 'code',
                    'critical', 'violation_comment']
    for col in viol_cols_db:
        if col not in viol_pd.columns:
            viol_pd[col] = None

    for _, row in viol_pd.iterrows():
        conn.execute(
            """INSERT INTO violations
               (inspection_id, business_id, description, code, critical, violation_comment)
               VALUES (?, ?, ?, ?, ?, ?)""",
            tuple(row[c] if str(row[c]) != 'nan' else None for c in viol_cols_db)
        )
    conn.commit()

    t_write = time.time() - t3
    print(f"  → Written to SQLite in {t_write:.2f}s")

    return t_load, t_clean, t_compute, t_write


def main():
    total_start = time.time()
    print("=" * 60)
    if GPU_AVAILABLE:
        print("🚀 SafePlate SCC — GPU-Accelerated Data Pipeline (RAPIDS cuDF)")
    else:
        print("SafePlate SCC — Data Pipeline (pandas CPU fallback)")
    print("=" * 60)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    create_schema(conn)
    t_load, t_clean, t_compute, t_write = load_and_process_gpu(conn)

    # Final stats
    total_time = time.time() - total_start
    print("\n" + "=" * 60)
    print("✅ Database ready!")
    cur = conn.execute("SELECT COUNT(*) FROM businesses")
    n_biz = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM inspections")
    n_insp = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM violations")
    n_viol = cur.fetchone()[0]

    # Risk level summary
    cur = conn.execute(
        "SELECT risk_level, COUNT(*) FROM businesses GROUP BY risk_level ORDER BY risk_level"
    )
    risk_summary = {level: count for level, count in cur.fetchall()}

    print(f"  Businesses:  {n_biz:,}")
    print(f"  Inspections: {n_insp:,}")
    print(f"  Violations:  {n_viol:,}")
    print(f"  🟢 Low risk:    {risk_summary.get('low', 0):,}")
    print(f"  🟡 Medium risk: {risk_summary.get('medium', 0):,}")
    print(f"  🔴 High risk:   {risk_summary.get('high', 0):,}")
    print(f"  Database: {DB_PATH}")
    print(f"  Size: {os.path.getsize(DB_PATH) / 1024 / 1024:.1f} MB")
    print()
    print(f"⏱️  Performance {'(GPU)' if GPU_AVAILABLE else '(CPU)'}:")
    print(f"  CSV Loading:      {t_load:.2f}s")
    print(f"  Data Cleaning:    {t_clean:.2f}s")
    print(f"  Risk Computation: {t_compute:.2f}s")
    print(f"  SQLite Write:     {t_write:.2f}s")
    print(f"  ────────────────────────")
    print(f"  TOTAL:            {total_time:.2f}s")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()
