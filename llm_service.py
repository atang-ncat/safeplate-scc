#!/usr/bin/env python3
"""SafePlate SCC — LLM Service via llama.cpp server."""

import httpx
import subprocess
import os
import time
import signal
import glob

LLAMA_SERVER_BIN = os.path.expanduser("~/llama.cpp/build/bin/llama-server")
MODELS_DIR = os.path.expanduser("~/models/gguf")
LLM_PORT = 8899
LLM_BASE_URL = f"http://localhost:{LLM_PORT}"

# System prompt for food safety analysis
SYSTEM_PROMPT = """You are SafePlate AI, a food safety expert for Santa Clara County, California.
You help people understand restaurant food safety data including inspection scores, violations, and risk assessments.

When given restaurant data, you should:
1. Explain violation codes in plain, understandable language
2. Assess the overall safety of a restaurant based on its history
3. Highlight critical health risks that could affect diners
4. Provide actionable recommendations
5. Be honest but not alarmist — context matters

Keep responses concise and helpful. Use emoji to make information scannable.
Format important warnings clearly. If you don't have enough data, say so."""

_server_process = None


def find_best_model():
    """Find the best available GGUF model for our use case."""
    # Prioritize Nemotron (NVIDIA's own model — critical for hackathon!)
    preferences = [
        "ggml-org--Nemotron-Nano-3-30B-A3B-GGUF",  # 30B MoE, 3B active — fast + NVIDIA
        "Qwen--Qwen3-4B-GGUF",
        "Qwen--Qwen3-8B-GGUF",
        "unsloth--Llama-3.2-3B-Instruct-GGUF",
        "Qwen--Qwen3-14B-GGUF",
    ]

    for model_name in preferences:
        model_dir = os.path.join(MODELS_DIR, model_name)
        if os.path.isdir(model_dir):
            # Find a GGUF file inside
            gguf_files = glob.glob(os.path.join(model_dir, "*.gguf"))
            if gguf_files:
                # Prefer Q4_K_M or similar medium quantization
                for f in sorted(gguf_files):
                    basename = os.path.basename(f).lower()
                    if "q4_k_m" in basename or "q4_0" in basename:
                        return f
                # Fallback to any GGUF
                return sorted(gguf_files)[0]

    # Last resort: find any GGUF file
    for model_dir_name in os.listdir(MODELS_DIR):
        model_dir = os.path.join(MODELS_DIR, model_dir_name)
        if os.path.isdir(model_dir):
            gguf_files = glob.glob(os.path.join(model_dir, "*.gguf"))
            if gguf_files:
                return sorted(gguf_files)[0]

    return None


def start_llm_server():
    """Start the llama.cpp server with the best available model."""
    global _server_process

    if _server_process is not None:
        return True

    model_path = find_best_model()
    if not model_path:
        print("ERROR: No GGUF model found!")
        return False

    print(f"Starting llama.cpp server with: {os.path.basename(model_path)}")

    cmd = [
        LLAMA_SERVER_BIN,
        "-m", model_path,
        "--port", str(LLM_PORT),
        "--host", "0.0.0.0",
        "-ngl", "999",       # Offload all layers to GPU
        "-c", "4096",        # Context size
        "--threads", "8",
        "-fa", "on",         # Flash attention
    ]

    _server_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready
    print("Waiting for LLM server to start...")
    for i in range(180):  # Wait up to 6 minutes for large models
        try:
            resp = httpx.get(f"{LLM_BASE_URL}/health", timeout=2.0)
            if resp.status_code == 200:
                print(f"LLM server ready on port {LLM_PORT}!")
                return True
        except Exception:
            pass
        time.sleep(2)

    print("WARNING: LLM server did not start in time")
    return False


def stop_llm_server():
    """Stop the llama.cpp server."""
    global _server_process
    if _server_process:
        _server_process.terminate()
        _server_process.wait()
        _server_process = None


async def chat_completion(messages: list[dict], max_tokens: int = 512) -> str:
    """Send a chat completion request to the LLM."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{LLM_BASE_URL}/v1/chat/completions",
                json={
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *messages,
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                    "stream": False,
                },
            )
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                return f"LLM Error: {response.status_code} — {response.text[:200]}"
    except Exception as e:
        return f"LLM service unavailable: {str(e)}. The AI assistant is still loading — please try again in a moment."


async def analyze_restaurant(name: str, violations_text: str, avg_score: float) -> str:
    """Generate an AI analysis of a restaurant's safety."""
    messages = [
        {
            "role": "user",
            "content": f"""Analyze the food safety of this restaurant:

**Restaurant:** {name}
**Average Inspection Score:** {avg_score}/100
**Recent Violations:**
{violations_text}

Provide a brief safety assessment with:
1. Overall safety rating (Safe / Caution / Concern)
2. Key issues to be aware of
3. Whether it's getting better or worse
Keep it to 3-4 sentences.""",
        }
    ]
    return await chat_completion(messages, max_tokens=300)


async def answer_question(question: str, context: str) -> str:
    """Answer a food safety question with context from the database."""
    messages = [
        {
            "role": "user",
            "content": f"""Based on this Santa Clara County food safety data:

{context}

User question: {question}

Answer the question using the data provided. Be specific with restaurant names, scores, and violation details when relevant.""",
        }
    ]
    return await chat_completion(messages, max_tokens=512)


if __name__ == "__main__":
    model = find_best_model()
    if model:
        print(f"Best model found: {model}")
        print(f"Size: {os.path.getsize(model) / 1024 / 1024 / 1024:.1f} GB")
    else:
        print("No model found!")
