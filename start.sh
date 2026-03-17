#!/bin/bash
# SafePlate SCC — Full Stack Startup Script
# Starts: Nemotron (GPU) + Web App + Ollama + OpenClaw Gateway

echo "🛡️  SafePlate SCC — Starting Full Stack..."
echo ""

cd /home/nvidia/safeplate

# Activate virtual environment
source .venv/bin/activate

# Kill any existing instances
echo "🔄 Cleaning up old processes..."
pkill -f "python3 app.py" 2>/dev/null
pkill -f "llama-server" 2>/dev/null
sleep 1

# ─── 1. Start LLM server (Nemotron on GPU) ───
echo "🧠 Loading Nemotron-Nano-30B on GPU (takes ~30 seconds)..."
nohup /home/nvidia/llama.cpp/build/bin/llama-server \
  -m /home/nvidia/models/gguf/ggml-org--Nemotron-Nano-3-30B-A3B-GGUF/Nemotron-Nano-3-30B-A3B-Q4_K_M.gguf \
  --port 8899 \
  --host 0.0.0.0 \
  -ngl 999 \
  -c 16384 \
  --threads 8 \
  -fa on \
  > /tmp/llama-server.log 2>&1 &

# ─── 2. Start Ollama (for OpenClaw) ───
echo "🦙 Starting Ollama..."
nohup ollama serve > /tmp/ollama.log 2>&1 &
sleep 2

# ─── 3. Start Web App ───
echo "🌐 Starting SafePlate web app on port 8888..."
nohup python3 app.py > /tmp/safeplate.log 2>&1 &
sleep 2

# ─── 4. Start OpenClaw Gateway ───
echo "🦞 Starting OpenClaw Gateway on port 18789..."
npx openclaw gateway restart 2>/dev/null &
sleep 2

# ─── 5. Wait for Nemotron ───
echo "⏳ Waiting for Nemotron to load..."
for i in $(seq 1 60); do
    if curl -s http://localhost:8899/health > /dev/null 2>&1; then
        echo "✅ Nemotron loaded on GPU!"
        break
    fi
    sleep 2
done

echo ""
echo "════════════════════════════════════════════════════════"
echo "  🛡️  SafePlate SCC — ALL SYSTEMS READY!"
echo ""
echo "  🌐 Web App:       http://localhost:8888"
echo "  🧠 Nemotron LLM:  http://localhost:8899"
echo "  🦞 OpenClaw UI:   http://localhost:18789"
echo "  🦙 Ollama:        http://localhost:11434"
echo ""
echo "  📋 Test MCP tools: python3 openclaw_mcp/server.py --test"
echo "════════════════════════════════════════════════════════"
echo ""
