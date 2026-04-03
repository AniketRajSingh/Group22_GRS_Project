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

def _run_benchmark_proc(req: BenchmarkRequest):
    global _benchmark_status
    try:
        # The benchmark script expects parameters via environment variables
        env = os.environ.copy()
        env["BENCHMARK_CONCURRENT"] = str(req.concurrent)
        env["BENCHMARK_TOTAL"] = str(req.total)
        env["BENCHMARK_TOKENS"] = str(req.tokens)
        
        cmd = [
            "python3", os.path.join(BASE_DIR, "group22_benchmarks/group22_load_generator.py"),
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

@app.post("/api/generate-plots")
async def generate_plots():
    try:
        # Use the specialized plotting script
        cmd = [
            "python3", os.path.join(BASE_DIR, "group22_benchmarks/group22_plot_results.py"),
            "--type", "dynamic"
        ]
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

# ── Report Generation ──
_report_status = {"running": False, "progress": 0, "current_graph": "", "completed": [], "report": "", "total_steps": 9}


def _run_report_gen():
    global _report_status
    try:
        import sys
        if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
        
        # Dynamically calculate total steps for the progress bar
        # 1 (Init) + (2 yields per plot) + 2 (Synthesis generation and completion)
        plot_dir = os.path.join(BASE_DIR, "group22_plots/dynamic")
        num_plots = len([f for f in os.listdir(plot_dir) if f.endswith('.png')]) if os.path.exists(plot_dir) else 0
        total_steps = 3 + (2 * num_plots) if num_plots > 0 else 1
        _report_status["total_steps"] = total_steps # type: ignore

        from describe_graph import analyze_all_plots
        for i, (graph_name, text) in enumerate(analyze_all_plots()):
            if _report_status.get("cancel"): # type: ignore
                _report_status["report"] += "\n\n## ⚠️ [ANALYSIS CANCELLED BY USER]" # type: ignore
                break
                
            _report_status["current_graph"] = graph_name # type: ignore
            
            # Only mark as completed once the text segment is actually generated
            if text.strip():
                if graph_name not in _report_status["completed"]: # type: ignore
                    _report_status["completed"].append(graph_name) # type: ignore
                _report_status["report"] += f"\n\n{text}" # type: ignore
                
            progress = int(((i + 1) / total_steps) * 100)
            _report_status["progress"] = min(progress, 100) # type: ignore

    except Exception as e:
        _report_status["report"] += f"\n\n[REPORT ERROR] {e}" # type: ignore
    finally:
        _report_status["running"] = False

@app.post("/api/generate-report")
async def generate_report():
    global _report_status
    if _report_status["running"]: return {"status": "busy"}
    _report_status = {"running": True, "cancel": False, "progress": 0, "current_graph": "Initializing...", "completed": [], "report": ""}
    threading.Thread(target=_run_report_gen, daemon=True).start()
    return {"status": "started"}

@app.post("/api/cancel-report")
async def cancel_report():
    global _report_status
    if _report_status["running"]:
        _report_status["cancel"] = True # type: ignore
        _report_status["current_graph"] = "Cancelling (waiting for current graph)..." # type: ignore
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
