#!/bin/bash
# SafePlate SCC — Quick Start Script
# Run this to start everything for the demo

echo "🛡️  SafePlate SCC — Starting..."

cd /home/nvidia/safeplate

# Activate virtual environment
source .venv/bin/activate

# Kill any existing instances
pkill -f "python3 app.py" 2>/dev/null
pkill -f "llama-server" 2>/dev/null
sleep 1

# Start LLM server (Nemotron)
echo "🧠 Loading Nemotron-Nano-30B (this takes ~60 seconds)..."
nohup /home/nvidia/llama.cpp/build/bin/llama-server \
  -m /home/nvidia/models/gguf/ggml-org--Nemotron-Nano-3-30B-A3B-GGUF/Nemotron-Nano-3-30B-A3B-Q4_K_M.gguf \
  --port 8899 \
  --host 0.0.0.0 \
  -ngl 999 \
  -c 4096 \
  --threads 8 \
  -fa on \
  > /tmp/llama-server.log 2>&1 &

# Start web app
echo "🌐 Starting web app on port 8888..."
nohup python3 app.py > /tmp/safeplate.log 2>&1 &
sleep 2

# Wait for LLM
echo "⏳ Waiting for Nemotron to load..."
for i in $(seq 1 120); do
    if curl -s http://localhost:8899/health > /dev/null 2>&1; then
        echo "✅ Nemotron loaded!"
        break
    fi
    sleep 2
done

echo ""
echo "════════════════════════════════════════"
echo "  🛡️  SafePlate SCC is READY!"
echo "  🌐 Web App:  http://localhost:8888"
echo "  🧠 LLM:      http://localhost:8899"
echo "════════════════════════════════════════"
echo ""
echo "To test MCP tools: python3 openclaw_mcp/server.py --test"
