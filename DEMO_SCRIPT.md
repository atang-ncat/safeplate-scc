# SafePlate SCC — Demo Script (2 minutes)
# The Winning Pitch for NVIDIA DGX Spark Hackathon

## 🏁 BEFORE THE DEMO — Checklist
```bash
# Verify all services are running:
curl -s http://localhost:8899/health   # ✅ Nemotron GPU
curl -s http://localhost:8888          # ✅ Web App
curl -s http://localhost:18789/        # ✅ OpenClaw Gateway
python3 openclaw_mcp/server.py --test  # ✅ MCP Tools
```

---

## 🎤 THE 2-MINUTE PITCH (Say This)

### [0:00-0:20] The Hook
> "Every year, 48 million Americans get sick from contaminated food — and one in six of us gets hospitalized. Santa Clara County inspects thousands of restaurants, but that data is buried in spreadsheets that nobody reads."
>
> "We built SafePlate SCC — a fully local, agentic AI that turns raw county health data into something any resident can understand in seconds. And it runs ENTIRELY on this DGX Spark. No cloud. No API keys. Just the GB10 chip doing the work."

**[Show the map — 8,588 color-coded dots]**

### [0:20-0:50] The Web App
> "8,588 restaurants. 64,000 violations. All ingested, scored, and geo-coded locally."

- **Zoom into downtown San Jose** — show the dot density
- **Click a RED marker** — "This restaurant has a risk score of 73. Let me ask the AI about it."
- **Click Ask AI** — type: **"Is this place safe to eat?"**

> "Watch the reasoning trace. You can see exactly how the AI thinks — it detects the intent, queries our SQLite database, finds the violations, and passes it all to Nemotron for analysis."

**[Agent trace animates in ⟶ then the answer appears]**

> "That entire pipeline — intent detection, database query, and natural language generation — just happened locally on the GPU in under 3 seconds."

### [0:50-1:30] OpenClaw + Agentic AI
> "Now here's what makes this an AGENTIC demo, not just a chatbot."

**[Switch to OpenClaw web UI — split screen]**

- Type this EXACT prompt in OpenClaw:
> **"I'm choosing between Taco Bell on Aborn Road and McDonald's on 1st Street. Which one is statistically safer and what were their worst violations?"**

> "Watch the OpenClaw agent. It's not a script — Nemotron is DECIDING which MCP tools to call. It queries both restaurants independently, compares the risk scores, and writes a recommendation."

**[While it thinks, show terminal with `openclaw logs --follow`]**

> "On the right, you can see the actual tool calls being orchestrated by OpenClaw. This is the Model Context Protocol in action — our Python MCP server exposes 4 tools that any agent can call."

### [1:30-2:00] The Closer
> "To be clear about what's running:
> - **Nemotron-Nano-30B** — a 30-billion parameter Mixture of Experts model running on the Blackwell GPU
> - **OpenClaw** — orchestrating the agent loop with MCP tools
> - **86,000 spatial records** processed and indexed locally
> - **Zero cloud dependencies** — this could run in a food inspector's truck with no WiFi
>
> SafePlate SCC proves that local, agentic AI on NVIDIA hardware isn't a future promise — it's running right now on this DGX Spark."

---

## 🎯 KEY PHRASES FOR JUDGES
Use these exact phrases — they hit every judging category:

| Category | What to Say |
|----------|------------|
| **Innovation** | "Fully autonomous agent that DECIDES which database queries to run" |
| **Hardware Fit** | "30B model on the GB10 — no cloud, zero latency, runs in the field" |
| **OpenClaw** | "4 custom MCP tools that any OpenClaw agent can call autonomously" |
| **Human Impact** | "2 million Santa Clara County residents can check if their restaurant is safe" |
| **Data** | "Real county government data — 8,588 restaurants, 86,000 inspections" |

---

## 🖥️ SCREEN LAYOUT FOR DEMO
```
┌──────────────────────────┬──────────────────────────┐
│                          │                          │
│   SafePlate Web App      │   OpenClaw Web UI        │
│   localhost:8888         │   localhost:18789        │
│                          │                          │
│   [Map + Search + Chat]  │   [Agent Chat]           │
│                          │                          │
│                          │                          │
└──────────────────────────┴──────────────────────────┘
       Terminal: openclaw logs --follow (optional)
```
