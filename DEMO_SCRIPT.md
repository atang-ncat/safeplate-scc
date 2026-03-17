# SafePlate SCC — Demo Script (3 minutes)

## Opening (30 sec)
> "Every year, 1 in 6 Americans gets sick from food. Santa Clara County inspects thousands of restaurants — but that data sits in ugly spreadsheets nobody reads. We built SafePlate SCC to change that."

**Show**: The map loaded with 8,588 color-coded restaurants.

## Feature 1: Interactive Map (30 sec)
- **Zoom into San Jose** — show the density of dots
- **Point out colors**: "Green = safe, yellow = caution, red = high risk"
- **Click a green marker** — show the popup with risk score
- **Click a red marker** — show high risk score, violations count

## Feature 2: Smart Search (30 sec)
- **Type "Habana Cuba"** in search bar
- Show: "2 found" — map zooms to the locations
- **Click on Habana Cuba in Santa Clara** — popup shows Risk 1.2/100
- **Click "View Full Report"** — detail panel opens with inspections + violations

## Feature 3: AI Chat (45 sec)
- **Click "Ask AI" button**
- Notice: "📍 Viewing: HABANA CUBA RESTAURANT" context indicator
- **Type: "Is this place safe?"**
- **Nemotron responds** with specific data about THAT restaurant
- **Say**: "This is NVIDIA Nemotron running locally on the DGX Spark — no cloud, no APIs, 100% private"

## Feature 4: OpenClaw Integration (30 sec)
- **Show terminal**: `python3 openclaw_mcp/server.py --test`
- **Say**: "We built a custom MCP server so OpenClaw agents can autonomously query food safety data"
- **Show the output**: Taco Bell search results, safety check, county stats

## Closing (15 sec)
> "SafePlate SCC: real county data, real AI, running entirely on this DGX Spark. 8,588 restaurants, 64,000 violations, one question — Is it safe to eat here?"

---

## Key Talking Points for Judges
1. **100% local** — no cloud APIs, runs on GB10
2. **Real data** — Santa Clara County open data, not synthetic
3. **Nemotron MoE** — 30B intelligence with 3B speed
4. **Agentic AI** — OpenClaw MCP tools let Nemotron decide how to query the database
5. **Human impact** — 2M+ residents can check restaurant safety for free

## Demo Preparation Checklist
- [ ] Server running: `http://localhost:8888`
- [ ] LLM loaded: `curl http://localhost:8899/health`
- [ ] Map shows dots on load
- [ ] Test one search before demo
- [ ] Test one chat message before demo
- [ ] Have terminal ready for MCP test command
