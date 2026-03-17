# SafePlate SCC — OpenClaw MCP Integration

## What is this?

SafePlate SCC exposes its food safety intelligence as an **MCP (Model Context Protocol) server** that OpenClaw agents can use. When connected, any OpenClaw agent powered by NVIDIA Nemotron can answer food safety questions by querying our database of 8,500+ restaurants and 64,000+ violations in Santa Clara County.

## Tools Available

| Tool | Description |
|------|-------------|
| `safeplate_search` | Search restaurants by name, address, or city. Returns risk scores and violation counts. |
| `safeplate_check` | Get detailed safety report for a specific restaurant with full violation history. |
| `safeplate_stats` | Aggregate food safety statistics for the county or a specific city. |

## OpenClaw Configuration

Add this to your OpenClaw MCP config (`~/.openclaw/config.json`):

```json
{
  "mcpServers": {
    "safeplate": {
      "command": "python3",
      "args": ["/home/nvidia/safeplate/openclaw_mcp/server.py"],
      "env": {}
    }
  }
}
```

## Example Interactions

**User → OpenClaw:** "Is it safe to eat at Taco Bell on Aborn Road?"

**OpenClaw (Nemotron)** calls `safeplate_check(name="taco bell aborn")` and gets:
- Risk Score: 8.5/100 (🟢 LOW)
- Avg Inspection Score: 93/100
- 0 Critical Violations
- Last Score: 95/100

**OpenClaw responds:** "Yes! The Taco Bell on Aborn Road in San Jose has an excellent food safety record with a low risk score of 8.5/100 and zero critical violations."

## Running

```bash
# Test the MCP tools directly
python3 /home/nvidia/safeplate/openclaw_mcp/server.py --test

# Run as MCP server (stdio mode for OpenClaw)
python3 /home/nvidia/safeplate/openclaw_mcp/server.py
```

## Built with
- NVIDIA DGX Spark (Dell Pro Max GB10)
- NVIDIA Nemotron-Nano-3-30B via llama.cpp
- SafePlate SCC food safety database (Santa Clara County open data)
