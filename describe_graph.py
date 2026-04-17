import base64
import requests  # type: ignore
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Configuration ──────────────────────────────────────────────────────────────
OLLAMA_IP = "192.168.3.173:11434"
MODEL = "qwen3.5:0.8b"
MAX_RETRIES = 2
RETRY_DELAY_S = 10
OLLAMA_TIMEOUT_S = 180
MAX_PARALLEL = 1

# ── Per-Plot Analysis Prompt ───────────────────────────────────────────────────
ANALYSIS_PROMPT_TEMPLATE = """You are a distributed systems performance analyst. Analyze this benchmark graph for strategy "{strategy}" under "{load}" load.

Benchmark Metrics:
- Mean Latency: {mean_latency}ms
- P95 Latency: {p95_latency}ms
- Success Rate: {success_rate}%
- Total Requests: {total_requests}
- Concurrent Users: {concurrent}

Provide your analysis in this EXACT JSON format (no markdown, no code fences, just raw JSON):
{{
  "metric_identity": "What metric this graph shows and why it matters",
  "behavioral_trend": "Key patterns observed in the data distribution",
  "performance_rating": "EXCELLENT / GOOD / MODERATE / POOR / CRITICAL",
  "anomalies": "Any outliers, spikes, or unexpected patterns (or 'None detected')",
  "bottleneck_analysis": "Where the main bottleneck lies based on the data",
  "recommendation": "One specific, actionable improvement suggestion"
}}
"""

# ── Synthesis Prompt ───────────────────────────────────────────────────────────
SYNTHESIS_PROMPT_TEMPLATE = """You are a senior distributed systems architect. Based on these benchmark results, write a strategic synthesis.

Benchmark Summary:
{summary_table}

Provide your synthesis in this EXACT JSON format (no markdown, no code fences, just raw JSON):
{{
  "overall_health": "Brief cluster health assessment (1-2 sentences)",
  "best_strategy_normal": "Which strategy performed best under normal load and why",
  "best_strategy_stress": "Which strategy performed best under stress load and why",
  "critical_findings": ["Finding 1", "Finding 2", "Finding 3"],
  "recommendations": ["Recommendation 1", "Recommendation 2", "Recommendation 3"],
  "conclusion": "2-3 sentence executive conclusion"
}}
"""


def _encode_image(image_path):
    """Encode image to base64 for Ollama vision API."""
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception:
        return None


def _call_ollama(prompt, image_b64=None):
    """Send a single request to Ollama with retry logic."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if image_b64:
        payload["images"] = [image_b64]

    last_error = "Unknown error"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  [Ollama] Attempt {attempt}/{MAX_RETRIES}")
            response = requests.post(
                f"http://{OLLAMA_IP}/api/generate",
                json=payload,
                timeout=OLLAMA_TIMEOUT_S
            )
            response.raise_for_status()
            result = response.json()
            text = result.get("response", "").strip()
            if text:
                return text
            last_error = "Empty response from Ollama."
        except requests.exceptions.Timeout:
            last_error = f"Timed out after {OLLAMA_TIMEOUT_S}s"
            print(f"  [Ollama] ⚠ Timeout on attempt {attempt}")
        except Exception as e:
            last_error = str(e)
            print(f"  [Ollama] ⚠ Error on attempt {attempt}: {e}")

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_S)

    return json.dumps({"error": f"Analysis unavailable after {MAX_RETRIES} attempts: {last_error}"})


def _parse_json_response(text):
    """Try to parse JSON from LLM response, handling common issues."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    
    # Fallback: return error dict
    return {"error": "Could not parse LLM response", "raw": text[:500]}


def _analyze_single_plot(plot_info):
    """Analyze a single plot with its benchmark data. Called in parallel."""
    strategy = plot_info["strategy"]
    load = plot_info["load"]
    image_path = plot_info.get("image_path")
    metrics = plot_info.get("metrics", {})

    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        strategy=strategy,
        load=load,
        mean_latency=f"{metrics.get('avg_latency', 0):.1f}",
        p95_latency=f"{metrics.get('p95_latency', 0):.1f}",
        success_rate=f"{metrics.get('success_rate', 0):.1f}",
        total_requests=metrics.get("total_requests", "N/A"),
        concurrent=metrics.get("concurrent", "N/A"),
    )

    image_b64 = _encode_image(image_path) if image_path and os.path.exists(image_path) else None
    
    print(f"  [Report] Analyzing {strategy} ({load})...")
    raw_response = _call_ollama(prompt, image_b64)
    parsed = _parse_json_response(raw_response)

    return {
        "strategy": strategy,
        "load": load,
        "metrics": metrics,
        "analysis": parsed,
        "image_path": image_path,
    }


def _generate_synthesis(all_results):
    """Generate final synthesis from all per-plot analyses."""
    # Build summary table
    rows = []
    for r in all_results:
        m = r["metrics"]
        a = r["analysis"]
        rating = a.get("performance_rating", "N/A") if isinstance(a, dict) else "N/A"
        rows.append(
            f"- {r['strategy']} ({r['load']}): "
            f"Mean={m.get('avg_latency', 0):.1f}ms, "
            f"P95={m.get('p95_latency', 0):.1f}ms, "
            f"Success={m.get('success_rate', 0):.1f}%, "
            f"Rating={rating}"
        )
    summary_table = "\n".join(rows)

    prompt = SYNTHESIS_PROMPT_TEMPLATE.format(summary_table=summary_table)
    print("  [Report] Generating executive synthesis...")
    raw_response = _call_ollama(prompt)
    return _parse_json_response(raw_response)


def analyze_plots_parallel(plots_with_data, progress_callback=None):
    """
    Main entry point. Analyzes all plots in parallel (3 at a time) and generates synthesis.
    
    Args:
        plots_with_data: list of dicts with keys: strategy, load, image_path, metrics
        progress_callback: optional fn(phase, detail) called at each step
    
    Returns:
        dict with keys: sections (list of per-plot results), synthesis (dict)
    """
    if not plots_with_data:
        return {"sections": [], "synthesis": {"error": "No benchmark data available"}}

    total = len(plots_with_data)
    if progress_callback:
        progress_callback("init", f"Analyzing {total} benchmarks with {MAX_PARALLEL} parallel workers")

    # ── Phase 1: Parallel per-plot analysis ──
    results = [None] * total
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
        future_to_idx = {}
        for i, plot_info in enumerate(plots_with_data):
            future = executor.submit(_analyze_single_plot, plot_info)
            future_to_idx[future] = i

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                results[idx] = {
                    "strategy": plots_with_data[idx]["strategy"],
                    "load": plots_with_data[idx]["load"],
                    "metrics": plots_with_data[idx].get("metrics", {}),
                    "analysis": {"error": str(e)},
                }
            
            completed_count = sum(1 for r in results if r is not None)
            if progress_callback:
                r = results[idx]
                progress_callback(
                    "plot_done",
                    f"{r['strategy']} ({r['load']}) — {completed_count}/{total}",
                )

    # Filter out None (shouldn't happen but safety)
    results = [r for r in results if r is not None]

    # ── Phase 2: Synthesis ──
    if progress_callback:
        progress_callback("synthesis", "Generating executive synthesis...")

    synthesis = _generate_synthesis(results)

    if progress_callback:
        progress_callback("complete", "Report generation complete")

    return {"sections": results, "synthesis": synthesis}


# ── Legacy compatibility ───────────────────────────────────────────────────────
def get_graph_description(image_path):
    """Legacy single-image analysis (kept for backward compatibility)."""
    b64 = _encode_image(image_path)
    if not b64:
        return f"Error: Could not read {os.path.basename(image_path)}"
    prompt = "Analyze this graph. Describe the key trends, anomalies, and performance insights."
    return _call_ollama(prompt, b64)


def analyze_all_plots():
    """Legacy sequential analysis (kept for backward compatibility)."""
    plot_dir = os.path.join(os.path.dirname(__file__), "group22_plots/static")
    if not os.path.exists(plot_dir):
        yield "Error", "⚠️ No plots found. Run a benchmark first."
        return

    plots = sorted([f for f in os.listdir(plot_dir) if f.endswith('.png')])
    if not plots:
        yield "Error", "⚠️ No plots found in directory."
        return

    yield "Initializing...", "## 🗂️ Unified Cluster Intelligence Report (UCIR)\n\nAnalysis generated from recent benchmark data."

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
    synth_prompt = (
        "Based on these brief notes from recent graphs, write a 3-paragraph executive summary:\n"
        + "\n".join(synthesis_notes)
    )
    payload = {"model": MODEL, "prompt": synth_prompt, "stream": False}
    try:
        response = requests.post(f"http://{OLLAMA_IP}/api/generate", json=payload, timeout=60)
        result = response.json()
        synthesis = result.get("response", "Could not generate synthesis.")
    except Exception as e:
        synthesis = f"Synthesis failed: {e}"

    yield "Complete", f"## 🏁 Executive Synthesis\n\n{synthesis}"


if __name__ == "__main__":
    test_img = "/home/iiitd/Group22_GRS_Project-2/group22_plots/dynamic/group22_latency_comparison.png"
    print(get_graph_description(test_img))
