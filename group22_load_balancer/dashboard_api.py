import os
import json
import time
import subprocess
import threading
import psutil
import yaml
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any

app = FastAPI(title="Distributed Inference Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLOT_DIR = os.path.join(BASE_DIR, "group22_plots/dynamic")
DOCKER_COMPOSE_PATH = os.path.join(BASE_DIR, "docker-compose.yaml")
LB_URL = "http://localhost:8080"

# Telemetry store
telemetry_store: Dict[str, Any] = {}

# ── Telemetry Loop ─────────────────────────────────────────────────────────────
def _telemetry_bridge():
    """Background thread to poll the load balancer's telemetry endpoint."""
    while True:
        try:
            resp = httpx.get(f"{LB_URL}/telemetry", timeout=1.0)
            if resp.status_code == 200:
                data = resp.json()
                node_stats = data.get("stats", {})
                active_reqs = data.get("active_requests", {})
                for node_id, stats in node_stats.items():
                    stats["active_requests"] = active_reqs.get(node_id, 0)
                    telemetry_store[node_id] = stats
        except Exception:
            pass
        time.sleep(0.1)

threading.Thread(target=_telemetry_bridge, daemon=True).start()

# ── API Endpoints ──────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "status": "Backend is working ✅",
        "project": "Distributed Inference Cluster — Group 22 GRS Project",
        "made_by": "Aniket, Aastha and Saloni"
    }

@app.get("/api/telemetry")
async def get_telemetry():
    """Aggregates latest stats from all live nodes as defined in docker-compose."""
    stats = {}
    try:
        with open(DOCKER_COMPOSE_PATH, "r") as f:
            dc = yaml.safe_load(f)
        nodes = [svc for svc in dc.get("services", {}) if svc != "load_balancer"]
    except Exception:
        nodes = ["inference-node-1", "inference-node-2", "inference-node-3"]

    for node_id in nodes:
        display_id = node_id.upper().replace("INFERENCE-", "") + ":8000"
        # Try both raw node_id and node_id:8000 for compatibility
        node_status = telemetry_store.get(node_id) or telemetry_store.get(f"{node_id}:8000", {})
        
        if node_status:
            stats[display_id] = {
                "cpu_percent": float(node_status.get("cpu_percent", 0.0)),
                "memory_mb":   float(node_status.get("memory_mb", 0.0)),
                "active_requests": int(node_status.get("active_requests", 0)),
                "healthy":     bool(node_status.get("healthy") or node_status.get("status") == "healthy")
            }
        else:
            stats[display_id] = {"cpu_percent": 0.0, "memory_mb": 0.0, "active_requests": 0, "healthy": False}
    
    return {"stats": stats, "count": len([s for s in stats.values() if s["healthy"]]), "total": len(stats)}


# ── Benchmark Management ──
class BenchmarkRequest(BaseModel):
    concurrent: int
    total: int
    strategy: str
    tokens: int = 20

_benchmark_status = {"running": False, "logs": [], "strategy": "", "live_data": []}

def _trigger_plot_generation():
    """Auto-generate comparison plots from all available benchmark results."""
    try:
        cmd = [
            "python3", os.path.join(BASE_DIR, "group22_benchmarks/group22_plot_results.py"),
            "--type", "dynamic",
            "--strategies", "Hardware-Aware", "Round-Robin", "Least-Connection", "Hashing",
        ]
        subprocess.run(cmd, check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # Non-critical — don't crash the benchmark flow

def _run_benchmark_proc(req: BenchmarkRequest):
    global _benchmark_status
    try:
        # The benchmark script expects parameters via environment variables
        env = os.environ.copy()
        env["BENCHMARK_CONCURRENT"] = str(req.concurrent)
        env["BENCHMARK_TOTAL"] = str(req.total)
        env["BENCHMARK_TOKENS"] = str(req.tokens)
        
        cmd = [
            "python3", "-u", os.path.join(BASE_DIR, "group22_benchmarks/group22_load_generator.py"),
            "--strategy", req.strategy,
            "--tag", "dynamic"
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        if proc.stdout is not None:
            for line in proc.stdout:  # type: ignore
                line = line.strip()
                if line.startswith("__PROGRESS_DATA__:"):
                    try:
                        data_json = line.replace("__PROGRESS_DATA__:", "")
                        data = json.loads(data_json)
                        _benchmark_status["live_data"].append(data) # type: ignore
                    except:
                        pass
                else:
                    _benchmark_status["logs"].append(line) # type: ignore
        proc.wait()
        # Auto-generate plots after benchmark completes
        _benchmark_status["logs"].append("[SYSTEM] Auto-generating plots...") # type: ignore
        _trigger_plot_generation()
        _benchmark_status["logs"].append("[SYSTEM] ✅ Plots updated.") # type: ignore

    except Exception as e:
        _benchmark_status["logs"].append(f"[SYSTEM ERROR] {e}") # type: ignore
    finally:
        _benchmark_status["running"] = False

@app.post("/api/benchmark")
async def start_benchmark(req: BenchmarkRequest):
    global _benchmark_status
    if _benchmark_status["running"]:
        raise HTTPException(status_code=400, detail="Benchmark already running")
    _benchmark_status = {"running": True, "logs": [], "strategy": req.strategy, "live_data": []}
    threading.Thread(target=_run_benchmark_proc, args=(req,), daemon=True).start()
    return {"status": "started"}

@app.get("/api/benchmark-status")
async def get_benchmark_status():
    return _benchmark_status

class PlotRequest(BaseModel):
    strategies: List[str] = []

@app.post("/api/generate-plots")
async def generate_plots(req: Request):
    try:
        body = await req.json()
        strategies = body.get("strategies", [])
    except Exception:
        strategies = []
        
    try:
        cmd = [
            "python3", os.path.join(BASE_DIR, "group22_benchmarks/group22_plot_results.py"),
            "--type", "dynamic"
        ]
        if strategies and isinstance(strategies, list) and len(strategies) > 0:
            cmd.extend(["--strategies"] + strategies)
            
        subprocess.run(cmd, check=True)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/plots/{filename}")
async def get_plot(filename: str):
    path = os.path.join(PLOT_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(status_code=404, detail="Plot not found")

@app.get("/api/benchmark-results")
def get_benchmark_results():
    results_dir = os.path.join(os.path.dirname(__file__), "..", "group22_results")
    if not os.path.exists(results_dir):
        return []
    
    # Strategy name normalization map
    STRATEGY_MAP = {
        'ha': 'HA', 'hardware-aware': 'HA', 'hardware_aware': 'HA',
        'rr': 'RR', 'round-robin': 'RR', 'round_robin': 'RR',
        'lc': 'LC', 'least-connection': 'LC', 'least_connection': 'LC',
        'hash': 'HS', 'hashing': 'HS', 'hs': 'HS',
    }
        
    summaries = []
    for f in sorted(os.listdir(results_dir)):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(results_dir, f), 'r') as file:
                data = json.load(file)
                if not data: continue
                
                status_200 = [r for r in data if r.get('status') == 200]
                latencies = [r.get('latency_ms', 0) for r in status_200]
                
                # Parse strategy and load from filename
                base = f.replace(".json", "")
                strategy = "unknown"
                load = "unknown"
                
                if base.startswith("group22_results_"):
                    # group22_results_ha_normal.json
                    rest = base.replace("group22_results_", "")
                    parts = rest.rsplit("_", 1)
                    if len(parts) == 2:
                        strategy, load = parts
                elif base.startswith("dynamic_results_"):
                    # dynamic_results_hardware-aware_normal_1776354886.json
                    rest = base.replace("dynamic_results_", "")
                    # Remove trailing timestamp (last segment if numeric)
                    segments = rest.rsplit("_", 1)
                    if len(segments) == 2 and segments[1].isdigit():
                        rest = segments[0]
                    parts = rest.rsplit("_", 1)
                    if len(parts) == 2:
                        strategy, load = parts
                
                # Normalize strategy name
                strategy_norm = STRATEGY_MAP.get(strategy.lower(), strategy.upper())
                
                summaries.append({
                    "filename": f,
                    "strategy": strategy_norm,
                    "load": load.capitalize(),
                    "avg_latency": sum(latencies) / len(latencies) if latencies else 0,
                    "p95_latency": sorted(latencies)[int(len(latencies)*0.95)] if latencies else 0,
                    "success_rate": (len(status_200) / len(data)) * 100 if data else 0,
                    "throughput": len(status_200) / (sum(latencies)/1000) if latencies and sum(latencies) > 0 else 0,
                    "timestamp": os.path.getmtime(os.path.join(results_dir, f))
                })
        except Exception as e:
            print(f"Error reading {f}: {e}")
    
    # Deduplicate: keep only latest file per strategy+load combo
    best = {}
    for s in summaries:
        key = f"{s['strategy']}_{s['load']}"
        if key not in best or s['timestamp'] > best[key]['timestamp']:
            best[key] = s
    
    # Sort by strategy then load for consistent ordering
    SORT_ORDER = {'HA': 0, 'RR': 1, 'LC': 2, 'HS': 3}
    result = sorted(best.values(), key=lambda x: (SORT_ORDER.get(x['strategy'], 9), x['load']))
    # Remove timestamp from response
    for r in result:
        r.pop('timestamp', None)
    return result

@app.get("/api/benchmark-detailed-results")
def get_benchmark_detailed_results(file: str):
    results_dir = os.path.join(os.path.dirname(__file__), "..", "group22_results")
    path = os.path.join(results_dir, file)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Result file not found")
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/plots-list")
async def list_plots():
    """Returns available plot files with their last-modified timestamps for live polling."""
    plots = []
    os.makedirs(PLOT_DIR, exist_ok=True)
    for f in os.listdir(PLOT_DIR):
        if f.endswith('.png'):
            path = os.path.join(PLOT_DIR, f)
            plots.append({"name": f, "mtime": os.path.getmtime(path)})
    return {"plots": plots, "latest_mtime": max((p["mtime"] for p in plots), default=0)}

# ── Report Generation V2 (Parallel LLM) ──────────────────────────────────────
_report_status: Dict[str, Any] = {
    "running": False, "progress": 0, "current_graph": "",
    "completed": [], "report": None, "total_steps": 1,
    "cancel": False,
}


def _collect_benchmark_data():
    """Read all benchmark results and pair with plot images."""
    results_dir = os.path.join(BASE_DIR, "group22_results")
    plot_dir = os.path.join(BASE_DIR, "group22_plots/dynamic")
    plots_with_data = []

    if not os.path.exists(results_dir):
        return []

    STRATEGY_MAP = {
        "hardware-aware": "HA", "round-robin": "RR",
        "least-connection": "LC", "hashing": "HS",
    }

    for filename in sorted(os.listdir(results_dir)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(results_dir, filename)
        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            if not isinstance(data, list) or len(data) == 0:
                continue

            # Extract strategy and load from filename
            # Format: results_hardware-aware_normal_....json
            parts = filename.replace("results_", "").split("_")
            raw_strategy = parts[0] if len(parts) > 0 else "unknown"
            # Handle multi-word strategies like "hardware-aware"
            load_name = "unknown"
            for lp in ["normal", "stress"]:
                if lp in filename:
                    load_name = lp
                    break
            # Re-extract strategy: everything between 'results_' and '_normal' or '_stress'
            prefix = filename.replace("results_", "").replace(".json", "")
            strategy_raw = prefix.split(f"_{load_name}")[0] if load_name != "unknown" else raw_strategy

            strategy_short = STRATEGY_MAP.get(strategy_raw, strategy_raw.upper()[:2])

            # Compute metrics from raw data
            latencies = [r.get("latency_ms", 0) for r in data if isinstance(r, dict)]
            statuses = [r.get("status", 0) for r in data if isinstance(r, dict)]
            successes = sum(1 for s in statuses if s == 200)
            avg_lat = sum(latencies) / len(latencies) if latencies else 0
            sorted_lat = sorted(latencies)
            p95_idx = int(len(sorted_lat) * 0.95)
            p95_lat = sorted_lat[min(p95_idx, len(sorted_lat) - 1)] if sorted_lat else 0
            success_rate = (successes / len(statuses) * 100) if statuses else 0

            # Find matching plot image (best effort)
            image_path = None
            for plot_file in os.listdir(plot_dir) if os.path.exists(plot_dir) else []:
                if plot_file.endswith(".png"):
                    image_path = os.path.join(plot_dir, plot_file)
                    break  # Use any available plot for now

            plots_with_data.append({
                "strategy": strategy_short,
                "load": load_name.capitalize(),
                "image_path": image_path,
                "filename": filename,
                "metrics": {
                    "avg_latency": avg_lat,
                    "p95_latency": p95_lat,
                    "success_rate": success_rate,
                    "total_requests": len(data),
                    "concurrent": "N/A",
                },
            })
        except Exception as e:
            print(f"  [Report] Skipping {filename}: {e}")
            continue

    return plots_with_data


def _format_report(result):
    """Format the parallel analysis result into a structured markdown report."""
    sections = result.get("sections", [])
    synthesis = result.get("synthesis", {})
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    strategies_tested = list(set(s["strategy"] for s in sections))

    lines = [
        "# 🗂️ Unified Cluster Intelligence Report (UCIR)",
        f"\n> Generated: {timestamp}  ",
        f"> Strategies analyzed: {', '.join(strategies_tested)}  ",
        f"> Total benchmarks: {len(sections)}",
        "",
        "---",
    ]

    # ── Per-benchmark sections ──
    for i, section in enumerate(sections):
        s = section["strategy"]
        l = section["load"]
        m = section["metrics"]
        a = section.get("analysis", {})

        lines.append(f"\n## 📊 {i+1}. {s} — {l} Load")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Mean Latency | {m.get('avg_latency', 0):.1f} ms |")
        lines.append(f"| P95 Latency | {m.get('p95_latency', 0):.1f} ms |")
        lines.append(f"| Success Rate | {m.get('success_rate', 0):.1f}% |")
        lines.append(f"| Total Requests | {m.get('total_requests', 'N/A')} |")
        lines.append("")

        if isinstance(a, dict) and "error" not in a:
            rating = a.get("performance_rating", "N/A")
            rating_emoji = {"EXCELLENT": "🟢", "GOOD": "🟡", "MODERATE": "🟠", "POOR": "🔴", "CRITICAL": "⛔"}.get(rating, "⚪")
            lines.append(f"**Performance Rating**: {rating_emoji} {rating}")
            lines.append("")
            lines.append(f"🔍 **Metric Identity**: {a.get('metric_identity', 'N/A')}")
            lines.append("")
            lines.append(f"📶 **Behavioral Trend**: {a.get('behavioral_trend', 'N/A')}")
            lines.append("")
            lines.append(f"⚠️ **Anomalies**: {a.get('anomalies', 'None detected')}")
            lines.append("")
            lines.append(f"🔧 **Bottleneck Analysis**: {a.get('bottleneck_analysis', 'N/A')}")
            lines.append("")
            lines.append(f"💡 **Recommendation**: {a.get('recommendation', 'N/A')}")
        elif isinstance(a, dict) and "error" in a:
            lines.append(f"⚠️ Analysis error: {a['error']}")
            if "raw" in a:
                lines.append(f"\n> Raw LLM output: {a['raw'][:300]}")
        else:
            lines.append(f"Analysis: {a}")

        lines.append("")
        lines.append("---")

    # ── Cross-strategy comparison table ──
    lines.append("\n## 📈 Cross-Strategy Comparison")
    lines.append("")
    lines.append("| Strategy | Load | Mean (ms) | P95 (ms) | Success | Rating |")
    lines.append("|----------|------|-----------|----------|---------|--------|")
    for section in sections:
        m = section["metrics"]
        a = section.get("analysis", {})
        rating = a.get("performance_rating", "—") if isinstance(a, dict) else "—"
        lines.append(
            f"| {section['strategy']} | {section['load']} | "
            f"{m.get('avg_latency', 0):.1f} | {m.get('p95_latency', 0):.1f} | "
            f"{m.get('success_rate', 0):.1f}% | {rating} |"
        )
    lines.append("")

    # ── Executive Synthesis ──
    lines.append("\n## 🏁 Executive Synthesis")
    lines.append("")
    if isinstance(synthesis, dict) and "error" not in synthesis:
        lines.append(f"**Overall Health**: {synthesis.get('overall_health', 'N/A')}")
        lines.append("")
        lines.append(f"**Best Strategy (Normal)**: {synthesis.get('best_strategy_normal', 'N/A')}")
        lines.append("")
        lines.append(f"**Best Strategy (Stress)**: {synthesis.get('best_strategy_stress', 'N/A')}")
        lines.append("")
        findings = synthesis.get("critical_findings", [])
        if findings:
            lines.append("### 🔑 Critical Findings")
            for f in findings:
                lines.append(f"- {f}")
            lines.append("")
        recs = synthesis.get("recommendations", [])
        if recs:
            lines.append("### 🛠️ Recommendations")
            for r in recs:
                lines.append(f"- {r}")
            lines.append("")
        lines.append(f"**Conclusion**: {synthesis.get('conclusion', 'N/A')}")
    elif isinstance(synthesis, dict) and "error" in synthesis:
        lines.append(f"⚠️ Synthesis error: {synthesis['error']}")
    else:
        lines.append(str(synthesis))

    return "\n".join(lines)


def _run_report_gen_v2():
    """V2 report generator: parallel LLM analysis with structured output."""
    global _report_status
    try:
        import sys
        if BASE_DIR not in sys.path:
            sys.path.append(BASE_DIR)

        # ① Generate latest plots first
        _report_status["current_graph"] = "Generating latest plots..."
        _report_status["progress"] = 5
        try:
            plot_cmd = [
                "python3", os.path.join(BASE_DIR, "group22_benchmarks/group22_plot_results.py"),
                "--type", "dynamic",
                "--strategies", "Hardware-Aware", "Round-Robin", "Least-Connection", "Hashing",
            ]
            subprocess.run(plot_cmd, check=True, timeout=60)
        except Exception as e:
            print(f"  [Report] Plot generation warning: {e}")

        # ② Collect benchmark data
        _report_status["current_graph"] = "Reading benchmark results..."
        _report_status["progress"] = 10
        plots_with_data = _collect_benchmark_data()

        if not plots_with_data:
            _report_status["report"] = _format_report({"sections": [], "synthesis": {"error": "No benchmark data found. Run a benchmark first."}})
            return

        total = len(plots_with_data)
        _report_status["total_steps"] = total + 2  # plots + synthesis + formatting

        # ③ Run parallel analysis
        def progress_cb(phase, detail):
            if _report_status.get("cancel"):
                return
            _report_status["current_graph"] = detail
            if phase == "plot_done":
                parts = detail.split("—")
                name = parts[0].strip() if parts else detail
                if name not in _report_status["completed"]:
                    _report_status["completed"].append(name)
                done = len(_report_status["completed"])
                _report_status["progress"] = int(10 + (done / total) * 75)
            elif phase == "synthesis":
                _report_status["progress"] = 90
            elif phase == "complete":
                _report_status["progress"] = 100

        from describe_graph import analyze_plots_parallel
        result = analyze_plots_parallel(plots_with_data, progress_callback=progress_cb)

        # ④ Format into markdown
        _report_status["current_graph"] = "Formatting report..."
        _report_status["progress"] = 95
        report_md = _format_report(result)
        _report_status["report"] = report_md
        _report_status["progress"] = 100
        _report_status["current_graph"] = "✅ Complete"

    except Exception as e:
        _report_status["report"] = f"# ❌ Report Generation Error\n\n{e}"
        import traceback
        traceback.print_exc()
    finally:
        _report_status["running"] = False


# Legacy V1 report (kept for backward compat)
def _run_report_gen():
    global _report_status
    try:
        import sys
        if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
        plot_dir = os.path.join(BASE_DIR, "group22_plots/dynamic")
        num_plots = len([f for f in os.listdir(plot_dir) if f.endswith('.png')]) if os.path.exists(plot_dir) else 0
        total_steps = 3 + (2 * num_plots) if num_plots > 0 else 1
        _report_status["total_steps"] = total_steps
        from describe_graph import analyze_all_plots
        for i, (graph_name, text) in enumerate(analyze_all_plots()):
            if _report_status.get("cancel"): break
            _report_status["current_graph"] = graph_name
            if text.strip():
                if graph_name not in _report_status["completed"]:
                    _report_status["completed"].append(graph_name)
                _report_status["report"] += f"\n\n{text}"
            _report_status["progress"] = min(int(((i + 1) / total_steps) * 100), 100)
    except Exception as e:
        _report_status["report"] += f"\n\n[REPORT ERROR] {e}"
    finally:
        _report_status["running"] = False


@app.post("/api/generate-report")
async def generate_report():
    """V2 report generation with parallel LLM analysis."""
    global _report_status
    if _report_status["running"]: return {"status": "busy"}
    _report_status = {
        "running": True, "cancel": False, "progress": 0,
        "current_graph": "Initializing...", "completed": [],
        "report": None, "total_steps": 1,
    }
    threading.Thread(target=_run_report_gen_v2, daemon=True).start()
    return {"status": "started"}

@app.post("/api/cancel-report")
async def cancel_report():
    global _report_status
    if _report_status["running"]:
        _report_status["cancel"] = True
        _report_status["current_graph"] = "Cancelling..."
    return {"status": "cancelling"}

@app.get("/api/report-status")
async def get_report_status():
    return _report_status

# ── Dynamic Cluster Config ──
class NodeConfig(BaseModel):
    cpu: float
    memory_mb: int

class ClusterDeployRequest(BaseModel):
    nodes: List[NodeConfig]

_deploy_status = {"running": False, "logs": [], "success": None}

def _run_deploy(nodes: List[NodeConfig]):
    global _deploy_status
    def log(msg):
        _deploy_status["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}") # type: ignore
    try:
        log(f"🔧 Generating docker-compose for {len(nodes)} nodes...")
        services: Dict[str, Any] = {}
        node_names: List[str] = []
        for i, node in enumerate(nodes):
            n = i + 1
            svc = f"inference-node-{n}"
            node_names.append(svc)
            services[svc] = {
                "build": "./group22_inference_service",
                "container_name": svc,
                "ports": [f"{8010+n}:8000"],
                "environment": [f"NODE_ID=node-{n}", "N_THREADS=2"],
                "volumes": ["./models:/models"],
                "deploy": {"resources": {"limits": {"cpus": str(node.cpu), "memory": f"{node.memory_mb}M"}}}
            }
        services["load_balancer"] = {
            "build": "./group22_load_balancer",
            "container_name": "load_balancer",
            "ports": ["8080:8080"],
            "environment": [f"NODES={','.join(node_names)}", "ROUTING_STRATEGY=hardware-aware"],
            "volumes": ["/var/run/docker.sock:/var/run/docker.sock"],
            "depends_on": node_names
        }
        with open(DOCKER_COMPOSE_PATH, "w") as f:
            yaml.dump({"version": "3.8", "services": services}, f, sort_keys=False)
        log("🛑 Restarting cluster...")
        subprocess.run(["docker", "compose", "down"], cwd=BASE_DIR, check=False)
        subprocess.run(["docker", "compose", "up", "-d", "--build"], cwd=BASE_DIR, check=True)
        log("✅ Cluster redeployed successfully!")
        _deploy_status["success"] = True
    except Exception as e:
        log(f"❌ Deploy error: {e}")
        _deploy_status["success"] = False
    finally:
        _deploy_status["running"] = False

@app.post("/api/deploy-cluster")
async def deploy_cluster(req: ClusterDeployRequest):
    global _deploy_status
    if _deploy_status["running"]: return {"status": "busy"}
    _deploy_status = {"running": True, "logs": [], "success": None}
    threading.Thread(target=_run_deploy, args=(req.nodes,), daemon=True).start()
    return {"status": "started"}

@app.get("/api/deploy-status")
async def get_deploy_status():
    return _deploy_status

@app.get("/api/cluster-config")
async def get_cluster_config():
    sys_cpu: int = psutil.cpu_count(logical=True) or 4
    sys_ram: int = int(psutil.virtual_memory().total // (1024 * 1024))
    current_nodes: List[Dict[str, Any]] = []
    try:
        with open(DOCKER_COMPOSE_PATH, "r") as f:
            dc = yaml.safe_load(f)
        for svc_name, svc in dc.get("services", {}).items():
            if svc_name == "load_balancer": continue
            limit = svc.get("deploy", {}).get("resources", {}).get("limits", {})
            current_nodes.append({
                "name": svc_name,
                "cpu": float(limit.get("cpus", 1.0)),
                "memory_mb": int(str(limit.get("memory", "1024M")).replace("M", ""))
            })
    except Exception:
        current_nodes = [{"cpu": 1.0, "memory_mb": 1024}] * 3
    
    used_cpu = sum(n["cpu"] for n in current_nodes)
    used_ram = sum(n["memory_mb"] for n in current_nodes)
    return {
        "system": {"total_cpu": sys_cpu, "total_ram_mb": sys_ram},
        "current_nodes": current_nodes,
        "used_cpu": used_cpu, "used_ram_mb": used_ram,
        "avail_cpu": float(max(0.0, float(sys_cpu) - float(used_cpu))),
        "avail_ram_mb": int(max(0, int(sys_ram) - int(used_ram)))
    }

# ── Auto-Benchmark Orchestrator ───────────────────────────────────────────────
STRATEGIES = ["hardware-aware", "round-robin", "least-connection", "hashing"]
LOAD_PROFILES = [
    {"name": "normal",  "concurrent": 2,  "total": 20, "tokens": 20},
    {"name": "stress",  "concurrent": 10, "total": 60, "tokens": 50},
]

_auto_status: Dict[str, Any] = {
    "running": False,
    "phase": "",
    "current_strategy": "",
    "current_load": "",
    "completed": 0,
    "total": len(STRATEGIES) * len(LOAD_PROFILES),
    "log": [],
    "results_summary": [],
    "finished": False,
    "test_generation": 0,
}

def _auto_log(msg: str):
    ts = time.strftime("%H:%M:%S")
    _auto_status["log"].append(f"[{ts}] {msg}")

def _run_auto_orchestrator(selected_strategies=None, selected_loads=None):
    global _auto_status
    strategies = selected_strategies or STRATEGIES
    loads = selected_loads or LOAD_PROFILES
    try:
        total_runs = len(strategies) * len(loads)
        _auto_status["total"] = total_runs
        completed = 0

        for strat in strategies:
            for profile in loads:
                run_label = f"{strat} · {profile['name']}"
                _auto_status["current_strategy"] = strat
                _auto_status["current_load"] = profile["name"]
                _auto_status["test_generation"] = _auto_status.get("test_generation", 0) + 1
                _auto_status["phase"] = f"Switching → {strat}"
                _auto_log(f"🔄 Hot-swapping strategy to: {strat}")

                # ① Hot-swap the load balancer strategy
                try:
                    resp = httpx.post(f"{LB_URL}/strategy", json={"strategy": strat}, timeout=5.0)
                    if resp.status_code == 200:
                        _auto_log(f"✅ Strategy set to {strat}")
                    else:
                        _auto_log(f"⚠️ Strategy switch returned {resp.status_code}")
                except Exception as e:
                    _auto_log(f"❌ Strategy switch failed: {e}")

                # ② Cooldown for telemetry to stabilize
                _auto_status["phase"] = f"Cooldown before {run_label}"
                _auto_log(f"❄️  Cooldown 3s...")
                time.sleep(3)

                # ③ Run benchmark
                _auto_status["phase"] = f"Running: {run_label}"
                _auto_log(f"🚀 Starting benchmark: {run_label} (concurrent={profile['concurrent']}, total={profile['total']}, tokens={profile['tokens']})")

                env = os.environ.copy()
                env["BENCHMARK_CONCURRENT"] = str(profile["concurrent"])
                env["BENCHMARK_TOTAL"] = str(profile["total"])
                env["BENCHMARK_TOKENS"] = str(profile["tokens"])
                cmd = [
                    "python3", "-u",
                    os.path.join(BASE_DIR, "group22_benchmarks/group22_load_generator.py"),
                    "--strategy", strat,
                    "--tag", "dynamic",
                ]
                try:
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
                    if proc.stdout:
                        for line in proc.stdout:
                            line = line.strip()
                            if not line.startswith("__PROGRESS_DATA__:"):
                                _auto_log(f"  [{strat}/{profile['name']}] {line}")
                    proc.wait()
                    exit_code = proc.returncode
                    if exit_code == 0:
                        _auto_log(f"✅ Completed: {run_label}")
                    else:
                        _auto_log(f"⚠️ Benchmark exited with code {exit_code}")
                except Exception as e:
                    _auto_log(f"❌ Benchmark failed: {e}")

                completed += 1
                _auto_status["completed"] = completed
                _auto_status["results_summary"].append({"strategy": strat, "load": profile["name"], "status": "done"})

                # ④ Post-run cooldown
                _auto_status["phase"] = f"Cooldown after {run_label}"
                # Auto-generate plots after each run so gallery updates live
                _auto_log("📊 Updating plots...")
                _trigger_plot_generation()

                _auto_log(f"❄️  Post-run cooldown 5s...")
                time.sleep(5)

        # ⑤ Auto-generate plots
        _auto_status["phase"] = "Generating comparison plots..."
        _auto_log("📊 Auto-generating comparison plots...")
        try:
            plot_cmd = [
                "python3", os.path.join(BASE_DIR, "group22_benchmarks/group22_plot_results.py"),
                "--type", "dynamic",
                "--strategies", "Hardware-Aware", "Round-Robin", "Least-Connection", "Hashing",
            ]
            subprocess.run(plot_cmd, check=True, timeout=60)
            _auto_log("✅ Plots generated successfully!")
        except Exception as e:
            _auto_log(f"⚠️ Plot generation failed: {e}")

        _auto_status["phase"] = "✅ All benchmarks complete!"
        _auto_log(f"🏁 Full research suite finished: {completed}/{total_runs} benchmarks")
        _auto_status["finished"] = True

    except Exception as e:
        _auto_log(f"❌ Orchestrator crashed: {e}")
        _auto_status["phase"] = f"❌ Error: {e}"
    finally:
        _auto_status["running"] = False

class AutoBenchmarkRequest(BaseModel):
    strategies: List[str] = ["hardware-aware", "round-robin", "least-connection", "hashing"]
    loads: List[Dict[str, Any]] = [
        {"name": "normal",  "concurrent": 2,  "total": 20, "tokens": 20},
        {"name": "stress",  "concurrent": 10, "total": 60, "tokens": 50},
    ]

@app.post("/api/auto-benchmark")
async def start_auto_benchmark(req: AutoBenchmarkRequest):
    global _auto_status
    if _auto_status["running"]:
        raise HTTPException(status_code=400, detail="Auto-benchmark already running")
    
    # Clear old results for a clean slate
    results_dir = os.path.join(os.path.dirname(__file__), "..", "group22_results")
    if os.path.exists(results_dir):
        for f in os.listdir(results_dir):
            if f.endswith(".json"):
                try:
                    os.remove(os.path.join(results_dir, f))
                except Exception:
                    pass
    
    selected_strategies = req.strategies if req.strategies else STRATEGIES
    selected_loads = req.loads if req.loads else LOAD_PROFILES
    total = len(selected_strategies) * len(selected_loads)
    _auto_status = {
        "running": True,
        "phase": "Initializing...",
        "current_strategy": "",
        "current_load": "",
        "completed": 0,
        "total": total,
        "log": [],
        "results_summary": [],
        "finished": False,
    }
    threading.Thread(target=_run_auto_orchestrator, args=(selected_strategies, selected_loads), daemon=True).start()
    return {"status": "started", "total_benchmarks": total}

@app.post("/api/benchmark-stop")
async def stop_benchmark():
    global _auto_status, _benchmark_status
    _auto_status["running"] = False
    _auto_status["phase"] = "Stopped by user"
    _auto_status["finished"] = True
    _benchmark_status["running"] = False
    return {"status": "stopped"}

@app.get("/api/auto-benchmark-status")
async def get_auto_benchmark_status():
    return _auto_status

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
