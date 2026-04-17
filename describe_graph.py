import base64
import requests  # type: ignore
import json
import os
import time
import ollama
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Configuration ──────────────────────────────────────────────────────────────
OLLAMA_IP = "192.168.3.173:11434"
MODEL = "qwen3.5:35b"
MAX_RETRIES = 3
RETRY_DELAY_S = 5
OLLAMA_TIMEOUT_S = 600
MAX_PARALLEL = 1

# Initialize Client
client = ollama.Client(host=f"http://{OLLAMA_IP}")

# ── Unified Cluster Analysis Prompt ──────────────────────────────────────────
UNIFIED_PROMPT_TEMPLATE = """You are a senior distributed systems architect.
Analyze the following {count} benchmarks. I provide matching images (plots) in sequence.

REQUIRED: Respond ONLY with a single JSON object. No conversational text.
CONCISENESS IS CRITICAL. Follow word limits strictly to avoid truncation.

Response Schema:
{{
  "per_plot_analysis": [
    {{
      "i": index_number,
      "metric_identity": "Short name of metric (Max 8 words)",
      "behavioral_trend": "Key data pattern (Max 15 words)",
      "performance_rating": "EXCELLENT / GOOD / MODERATE / POOR / CRITICAL",
      "anomalies": "Spikes or outliers (Max 10 words)",
      "bottleneck_analysis": "Primary system constraint (Max 12 words)",
      "recommendation": "One actionable fix (Max 15 words)"
    }},
    ... (one for each of the {count} benchmarks)
  ],
  "synthesis": {{
    "overall_health": "Health summary (Max 20 words)",
    "best_strategy_normal": "Best for Normal load + reason (Max 15 words)",
    "best_strategy_stress": "Best for Stress load + reason (Max 15 words)",
    "critical_findings": ["Finding 1 (Max 15 words)", "Finding 2 (Max 15 words)"],
    "recommendations": ["Refinement 1 (Max 15 words)", "Refinement 2 (Max 15 words)"],
    "conclusion": "Final architect verdict (Max 25 words)"
  }}
}}

Benchmarks to analyze:
{benchmarks_text}
"""


def _call_ollama_unified(prompt, image_paths=None):
    """Send a single massive request using the Ollama SDK."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  [Ollama-SDK] Unified Request (Attempt {attempt}/{MAX_RETRIES})...")
            print(f"  [Debug] Prompt length: {len(prompt)} chars, Images: {len(image_paths) if image_paths else 0}")
            
            # Using SDK (Text-only mode for Qwen 3.5 35B)
            response = client.generate(
                model=MODEL,
                prompt=prompt,
                options={
                    "num_ctx": 16384,
                    "temperature": 0.1
                }
            )
            
            text = response.get("response", "").strip()
            if text:
                print(f"  [Debug] Raw response start: {text[:150]}...")
                return text
            
        except Exception as e:
            print(f"  [Ollama-SDK] ⚠ Error: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_S)

    return json.dumps({"error": "Failed to get unified analysis via SDK."})


def _fuzzy_get(data, keys, default=None):
    """Get value from dict using a list of potential keys (case-insensitive)."""
    if not isinstance(data, dict):
        return default
    # Try exact matches first
    for k in keys:
        if k in data:
            val = data[k]
            return val if val is not None else default
    # Try case-insensitive
    lkeys = [k.lower() for k in keys]
    for dk in data.keys():
        if dk.lower() in lkeys:
            val = data[dk]
            return val if val is not None else default
    return default


def _parse_unified_json(text):
    """Extract and repair JSON from LLM response."""
    if not text: return None
    text = text.strip()

    if "```" in text:
        import re
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match: text = match.group(1).strip()
    
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0: return None
    
    candidate = text[start:end]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        fixed = candidate
        if fixed.count('"') % 2 != 0: fixed += '"'
        while fixed.count("[") > fixed.count("]"): fixed += "]"
        while fixed.count("{") > fixed.count("}"): fixed += "}"
        try:
            return json.loads(fixed)
        except:
            last_bracket = fixed.rfind("]")
            if last_bracket > 0:
                truncated = fixed[:last_bracket+1] + "}"
                try: return json.loads(truncated)
                except: pass
            return None


def analyze_unified_cluster(plots_with_data, progress_callback=None):
    """Analyzes the entire cluster in ONE single LLM call using the Ollama SDK."""
    if not plots_with_data:
        return {"sections": [], "synthesis": {"error": "No data available"}}

    if progress_callback:
        progress_callback("init", f"Preparing unified analysis for {len(plots_with_data)} benchmarks...")

    # 1. Prepare benchmarks text and collected image paths
    benchmarks_text = []
    image_paths = []
    
    for i, p in enumerate(plots_with_data):
        m = p.get("metrics", { })
        dt = (
            f"[{i+1}] {p['strategy']} {p['load']}: Mean={m.get('avg_latency',0):.1f}ms, "
            f"P95={m.get('p95_latency',0):.1f}ms, Success={m.get('success_rate',0):.1f}%"
        )
        benchmarks_text.append(dt)
        ipath = p.get("image_path")
        if ipath and os.path.exists(ipath):
            image_paths.append(ipath)

    prompt = UNIFIED_PROMPT_TEMPLATE.format(
        count=len(plots_with_data),
        benchmarks_text="\n".join(benchmarks_text)
    )

    if progress_callback:
        progress_callback("analysis", "Analyzing cluster state (Unified SDK Request)...")

    # 2. Call LLM (SDK handles file reading/encoding internally)
    raw_response = _call_ollama_unified(prompt, image_paths)
    parsed = _parse_unified_json(raw_response)

    # 3. Direct Mapping
    sections = []
    analyses_list = _fuzzy_get(parsed, ["per_plot_analysis", "analyses", "results"], [])
    
    # Handle dict-based output
    if isinstance(analyses_list, dict):
        try:
            analyses_list = [analyses_list[k] for k in sorted(analyses_list.keys(), key=lambda x: str(x))]
        except:
            analyses_list = []

    for i, p in enumerate(plots_with_data):
        analysis = {}
        if i < len(analyses_list):
            raw_a = analyses_list[i]
            # Map exactly to what _format_report expects
            analysis = {
                "metric_identity": _fuzzy_get(raw_a, ["metric_identity", "id", "identity"], "N/A"),
                "behavioral_trend": _fuzzy_get(raw_a, ["behavioral_trend", "trend", "behavior"], "N/A"),
                "performance_rating": _fuzzy_get(raw_a, ["performance_rating", "rating", "status"], "N/A"),
                "anomalies": _fuzzy_get(raw_a, ["anomalies", "spikes", "outliers"], "None detected"),
                "bottleneck_analysis": _fuzzy_get(raw_a, ["bottleneck_analysis", "bottleneck"], "N/A"),
                "recommendation": _fuzzy_get(raw_a, ["recommendation", "fix", "suggestion"], "N/A")
            }
        else:
            analysis = {"error": "Analysis missing from model response"}
        
        sections.append({
            "strategy": p["strategy"],
            "load": p["load"],
            "metrics": p["metrics"],
            "analysis": analysis,
            "image_path": p.get("image_path"),
            "b64_image": p.get("b64_image")
        })

    # Exact synthesis mapping
    s_raw = _fuzzy_get(parsed, ["synthesis", "summary", "overview"], { })
    synthesis = {
        "overall_health": _fuzzy_get(s_raw, ["overall_health", "health"], "N/A"),
        "best_strategy_normal": _fuzzy_get(s_raw, ["best_strategy_normal", "best_overall", "best_normal"], "N/A"),
        "best_strategy_stress": _fuzzy_get(s_raw, ["best_strategy_stress", "best_stress"], "N/A"),
        "critical_findings": _fuzzy_get(s_raw, ["critical_findings", "findings"], []),
        "recommendations": _fuzzy_get(s_raw, ["recommendations", "fixes"], []),
        "conclusion": _fuzzy_get(s_raw, ["conclusion", "summary"], "")
    }
    
    if progress_callback:
        progress_callback("complete", "Analysis successfully mapped via SDK.")

    return {"sections": sections, "synthesis": synthesis}


# ── Legacy wrapper ───────────────────────────────────────────────────────────
def analyze_plots_parallel(plots_with_data, progress_callback=None):
    """Wrapper to maintain compatibility with dashboard_api.py."""
    return analyze_unified_cluster(plots_with_data, progress_callback)


# ── Legacy compatibility ───────────────────────────────────────────────────────
def get_graph_description(image_path):
    """Legacy single-image analysis using SDK."""
    if not os.path.exists(image_path):
        return f"Error: File not found {os.path.basename(image_path)}"
    
    try:
        response = client.generate(
            model=MODEL,
            prompt="Analyze this graph. Describe key trends and insights.",
            images=[image_path]
        )
        return response.get("response", "No response")
    except Exception as e:
        return f"Error: {e}"


def analyze_all_plots():
    """Legacy sequential analysis using SDK."""
    plot_dir = os.path.join(os.path.dirname(__file__), "group22_plots/static")
    if not os.path.exists(plot_dir):
        yield "Error", "⚠️ No plots found."
        return

    plots = sorted([f for f in os.listdir(plot_dir) if f.endswith('.png')])
    if not plots:
        yield "Error", "⚠️ No plots found."
        return

    yield "Initializing...", "## 🗂️ Unified Cluster Intelligence Report (UCIR)"

    synthesis_notes = []
    for filename in plots:
        img_path = os.path.join(plot_dir, filename)
        clean_name = filename.replace('group22_', '').replace('.png', '').replace('_', ' ').title()
        yield clean_name, ""
        analysis = get_graph_description(img_path)
        synthesis_notes.append(f"{clean_name}: {analysis[:100]}...")
        formatted_chunk = f"## {clean_name}\n\n##PLOT_SEPARATOR##\n{filename}\n##PLOT_SEPARATOR##\n{analysis}\n##PLOT_SEPARATOR##\n"
        yield clean_name, formatted_chunk

    yield "Final Synthesis", ""
    try:
        synth_prompt = f"Executive summary for:\n" + "\n".join(synthesis_notes)
        response = client.generate(model=MODEL, prompt=synth_prompt)
        synthesis = response.get("response", "N/A")
    except Exception as e:
        synthesis = f"Synthesis failed: {e}"

    yield "Complete", f"## 🏁 Executive Synthesis\n\n{synthesis}"


if __name__ == "__main__":
    test_img = "/home/iiitd/Group22_GRS_Project-2/group22_plots/dynamic/group22_latency_comparison.png"
    print(get_graph_description(test_img))
