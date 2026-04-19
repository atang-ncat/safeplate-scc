

https://github.com/user-attachments/assets/8501e6bc-9f01-42d6-8374-371240f6aa44


# SafePlate SCC — AI-Powered Food Safety Intelligence

**Know Before You Eat.** Real-time food safety intelligence for Santa Clara County, powered by NVIDIA Nemotron running locally on DGX Spark.

---

## The Problem

Every year, **48 million Americans** get sick from foodborne illness — that's 1 in 6 people. **128,000 are hospitalized** and **3,000 die** (CDC). Behind every statistic is someone who just wanted a safe meal.

Santa Clara County — home to **2 million residents** and the heart of Silicon Valley — conducts **21,895 restaurant inspections** annually and documents **64,364 violations** across **8,588 food establishments**. This data is public, but it's effectively invisible:

- **Buried in spreadsheets** — raw CSVs on a government open data portal that most residents will never find
- **No risk context** — individual inspection scores mean nothing without historical trend analysis
- **No spatial awareness** — you can't ask "which restaurants near me are safe?" and get an answer
- **No intelligence** — the data just sits there; nobody is analyzing patterns across 86,000+ records

**The result?** A family picks a restaurant based on Yelp stars and vibes — completely unaware that it had 12 critical health violations in the past year, including improper food temperature storage and pest infestations.

**SafePlate SCC changes that.** I built an AI-powered food safety intelligence platform that turns raw county data into something any resident can understand in seconds — powered entirely by NVIDIA Nemotron running locally on the DGX Spark. No cloud. No API keys. Just the GB10 chip protecting public health.

## Solution

SafePlate SCC transforms raw county inspection data into an **interactive, AI-powered food safety map** that anyone can use:

- **Interactive Map** — 8,588 restaurants plotted with color-coded risk markers (green/yellow/red)
- **Smart Search** — Find 

https://github.com/user-attachments/assets/4a02755c-f750-4ae5-9295-7e3e9adfc0c1

any restaurant by name, address, or city
- **AI Chat (Nemotron)** — Ask natural language questions: *"Is it safe to eat at Habana Cuba Restaurant?"*
- **Risk Scoring** — Proprietary algorithm weighing violation severity, recency, and frequency
- **OpenClaw MCP Tools** — Agentic AI integration for autonomous food safety queries

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    SafePlate SCC                     │
├──────────────┬──────────────┬───────────────────────┤
│  Frontend    │  Backend     │  AI Layer             │
│  Leaflet.js  │  FastAPI     │  Nemotron-Nano-30B    │
│  Dark Mode   │  SQLite DB   │  via llama.cpp        │
│  Map + Chat  │  REST API    │  RAG Pipeline         │
├──────────────┴──────────────┴───────────────────────┤
│              OpenClaw MCP Server                     │
│  safeplate_search | safeplate_check | safeplate_stats│
├─────────────────────────────────────────────────────┤
│         NVIDIA DGX Spark (GB10 Blackwell GPU)        │
│              128GB UMA · CUDA 13.0                   │
└─────────────────────────────────────────────────────┘
```

## NVIDIA Models Used

| Model | Role | How |
|-------|------|-----|
| **Nemotron-Nano-3-30B-A3B** | Core AI Brain | Powers AI chat with RAG context; reasons over real inspection data to answer food safety questions |
| **OpenClaw MCP** | Agentic AI | Custom MCP server exposes SafePlate tools so Nemotron can autonomously decide when/how to query the database |
| **DGX Spark (GB10)** | Local Inference | 100% local execution — no cloud APIs. Demonstrates edge AI for field use (food inspectors, public health) |

### Why Nemotron?
- **MoE architecture** (30B total, 3B active) = smart as a 30B model, fast as a 3B model
- **Runs entirely on DGX Spark** — demonstrates NVIDIA's local AI vision
- **OpenClaw integration** — becomes an agentic AI that makes decisions, not just generates text

## Data Pipeline (GPU-Accelerated with RAPIDS cuDF)

**Source**: Santa Clara County Open Data (3 public CSV datasets)

| Dataset | Records | Content |
|---------|---------|---------|
| Businesses | 8,588 | Restaurant names, addresses, coordinates |
| Inspections | 21,895 | Inspection dates, scores, results |
| Violations | 64,364 | Violation descriptions, criticality, comments |

**GPU Performance** (NVIDIA RAPIDS cuDF on Blackwell GB10):
| Stage | Time |
|-------|------|
| CSV Loading (onto GPU) | 0.60s |
| Data Cleaning (GPU) | 0.10s |
| Risk Score Computation (GPU vectorized) | 0.26s |
| SQLite Write | 2.10s |
| **TOTAL** | **3.06s** |

**Risk Score Algorithm** (0-100, lower = safer):
- Weighted inspection scores (recent scores count more)
- Violation severity multipliers (critical = 3x weight)
- Recency decay (recent violations weigh heavier)
- Consistency penalty (repeated violations increase risk)

## Quick Start

```bash
# One command to start everything:
bash start.sh

# Or manually:
cd /home/nvidia/safeplate
source .venv/bin/activate
python3 data_pipeline.py   # GPU-accelerated data processing
python3 app.py             # Web app on port 8888
```

## OpenClaw Integration

SafePlate exposes its intelligence as MCP tools for OpenClaw agents:

```json
{
  "mcpServers": {
    "safeplate": {
      "command": "python3",
      "args": ["/home/nvidia/safeplate/openclaw_mcp/server.py"]
    }
  }
}
```

**Tools Available:**
- `safeplate_search(query)` — Search restaurants by name/address/city
- `safeplate_check(name)` — Get detailed safety report with violation history
- `safeplate_stats(city?)` — Aggregate food safety analytics

**Example**: User asks OpenClaw: *"Is it safe to eat at Taco Bell on Aborn Road?"*
→ Nemotron calls `safeplate_check("taco bell aborn")` → Gets risk score 8.5/100 (LOW) → Responds with data-backed safety analysis.

## Impact

### Human Impact
- **Consumer Protection**: Empowers 2M+ Santa Clara County residents to make informed dining choices
- **Health Equity**: Free, accessible tool — no app download needed, works in any browser
- **Inspector Support**: Food inspectors can use this on DGX Spark in the field with no internet

### Environmental Impact
- **100% Local AI**: Zero cloud computing — no data center energy for inference
- **Edge Computing**: Demonstrates sustainable AI deployment model

## Project Structure

```
safeplate/
├── app.py                    # FastAPI backend (search, detail, chat, stats APIs)
├── data_pipeline.py          # GPU-accelerated CSV → SQLite via RAPIDS cuDF
├── llm_service.py            # Nemotron LLM management via llama.cpp
├── safeplate.db              # Processed database (37.5 MB)
├── requirements.txt          # Python dependencies
├── start.sh                  # One-command full stack startup
├── static/
│   ├── index.html            # Frontend (map, search, chat UI)
│   └── style.css             # Premium dark mode design
└── openclaw_mcp/
    ├── server.py             # MCP server for OpenClaw integration
    └── README.md             # OpenClaw setup instructions
```

## Team

Built at **Hack for Impact: The Open Source AI Challenge** (GTC 2026)

## Tech Stack

- **AI**: NVIDIA Nemotron-Nano-3-30B-A3B (GGUF) via llama.cpp
- **Data Processing**: NVIDIA RAPIDS cuDF (GPU-accelerated)
- **Backend**: Python, FastAPI, SQLite
- **Frontend**: HTML/JS, Leaflet.js, CSS (dark mode)
- **Hardware**: NVIDIA DGX Spark (Dell Pro Max, GB10 Blackwell GPU)
- **Agent Framework**: OpenClaw MCP (Model Context Protocol)
- **Data**: Santa Clara County DEH Open Data
