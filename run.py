import os
import subprocess
import time
import sys
import signal
import socket
import threading
import psutil
import yaml

# ── Configuration ──────────────────────────────────────────────────────────────
LOG_DIR            = ".group22_logs"
MODEL_DIR          = "models"
MODEL_FILE         = "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
MODEL_URL          = "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
DASHBOARD_API_PATH = "group22_load_balancer/dashboard_api.py"
FRONTEND_DIR       = "group22_dashboard"
DOCKER_COMPOSE     = "docker-compose.yaml"

components = {
    "dashboard_api": {
        "cmd": ["python3", "-u", DASHBOARD_API_PATH],
        "process": None,
        "log": f"{LOG_DIR}/dashboard_api.log",
        "restarts": 0
    },
    "frontend_dev": {
        "cmd": ["npm", "run", "dev"],
        "cwd": FRONTEND_DIR,
        "process": None,
        "log": f"{LOG_DIR}/frontend.log",
        "restarts": 0
    }
}

MAX_RESTARTS = 3

# ── Colors ─────────────────────────────────────────────────────────────────────
BLUE  = "\033[94m"
GREEN = "\033[92m"
YELLOW= "\033[93m"
RED   = "\033[91m"
CYAN  = "\033[96m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
RESET = "\033[0m"

def c(color, msg):  return f"{color}{msg}{RESET}"
def banner(msg):    print(f"\n{BLUE}{'─'*60}\n  {BOLD}{msg}{RESET}\n{BLUE}{'─'*60}{RESET}")
def ok(msg):        print(f"  {GREEN}✔  {RESET}{msg}")
def info(msg):      print(f"  {BLUE}→  {RESET}{msg}")
def warn(msg):      print(f"  {YELLOW}⚠  {RESET}{msg}")
def err(msg):       print(f"  {RED}✘  {RESET}{msg}")

# ── Signal handler ─────────────────────────────────────────────────────────────
def signal_handler(sig, frame):
    print(f"\n\n{YELLOW}[!] Shutdown signal received. Cleaning up...{RESET}")
    for name, data in components.items():
        p = data["process"]  # type: ignore
        if p and p.poll() is None:  # type: ignore
            print(f"    Stopping {name} (PID {p.pid})...")  # type: ignore
            p.terminate()  # type: ignore
            try:
                p.wait(timeout=3)  # type: ignore
            except:
                p.kill()  # type: ignore
    print("    Stopping Docker cluster...")
    try:
        subprocess.run(["docker", "compose", "down", "--remove-orphans"],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass
    print(f"{GREEN}[+] All components offline. Clean exit.{RESET}\n")
    os._exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ── Helpers ────────────────────────────────────────────────────────────────────
def start_component(name):
    data = components[name]
    log_file = open(data["log"], "a")  # type: ignore
    log_file.write(f"\n--- RESTART AT {time.ctime()} ---\n")
    p = subprocess.Popen(
        data["cmd"],  # type: ignore
        cwd=data.get("cwd"),  # type: ignore
        stdout=log_file, stderr=log_file,
        stdin=subprocess.DEVNULL, text=True, bufsize=1
    )
    data["process"] = p  # type: ignore
    return p

def setup_environment():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)
    model_path = os.path.join(MODEL_DIR, MODEL_FILE)
    if not os.path.exists(model_path):
        info(f"Model missing. Downloading {MODEL_FILE} (638 MB)...")
        try:
            subprocess.run(["curl", "-L", MODEL_URL, "-o", model_path], check=True)
        except:
            err("Model download failed. Exiting.")
            sys.exit(1)
    else:
        ok(f"Model verified in {MODEL_DIR}/")

def wait_for_ready(url, name, timeout=60):
    print(f"  {DIM}→ Probing {name} on {url} ...{RESET}", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                host_port = url.replace("http://", "").split("/")[0].split(":")
                host, port = host_port[0], int(host_port[1])
                if s.connect_ex((host, port)) == 0:
                    print(f" {GREEN}READY{RESET}")
                    return True
        except:
            pass
        print(".", end="", flush=True)
        time.sleep(2)
    print(f" {RED}TIMED OUT{RESET}")
    return False

# ── Docker Compose Generator ───────────────────────────────────────────────────
def generate_docker_compose(node_configs):
    """
    node_configs: list of dicts with keys 'cpu' (float) and 'memory_mb' (int)
    """
    services = {}
    node_names = []
    port_base = 8010

    for i, node in enumerate(node_configs):
        n         = i + 1
        svc_name  = f"inference-node-{n}"
        host_port = port_base + n
        node_names.append(svc_name)
        services[svc_name] = {
            "build":     "./group22_inference_service",
            "container_name": svc_name,
            "ports":     [f"{host_port}:8000"],
            "environment": [f"NODE_ID=node-{n}", "N_THREADS=2"],
            "volumes":   ["./models:/models"],
            "deploy": {
                "resources": {
                    "limits": {
                        "cpus":   str(node["cpu"]),
                        "memory": f"{node['memory_mb']}M"
                    }
                }
            }
        }

    services["load_balancer"] = {
        "build": {"context": "./group22_load_balancer", "dockerfile": "Dockerfile"},
        "container_name": "load_balancer",
        "ports": ["8080:8080"],
        "environment": [
            f"NODES={','.join(node_names)}",
            "ROUTING_STRATEGY=hardware-aware"
        ],
        "volumes": ["/var/run/docker.sock:/var/run/docker.sock"],
        "depends_on": node_names
    }

    return {"version": "3.8", "services": services}

# ── Automatic Cluster Startup ──────────────────────────────────────────────────
def get_or_create_default_config():
    """Load existing docker-compose or create a standard 3-node default."""
    if os.path.exists(DOCKER_COMPOSE):
        try:
            with open(DOCKER_COMPOSE, "r") as f:
                dc = yaml.safe_load(f)
            if "services" in dc:
                nodes = []
                for k, v in dc["services"].items():
                    if k == "load_balancer": continue
                    limits = v.get("deploy", {}).get("resources", {}).get("limits", {})
                    nodes.append({
                        "cpu": float(limits.get("cpus", 1.0)),
                        "memory_mb": int(str(limits.get("memory", "1024M")).replace("M", ""))
                    })
                return nodes
        except Exception:
            pass
    
    info("No valid configuration found. Using default 3-node layout...")
    nodes = [{"cpu": 1.0, "memory_mb": 1024}] * 3
    compose = generate_docker_compose(nodes)
    with open(DOCKER_COMPOSE, "w") as f:
        yaml.dump(compose, f, default_flow_style=False, sort_keys=False)
    return nodes

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print()
    print(f"{BLUE}{'═'*60}")
    print(f"   {BOLD}⚡ DISTRIBUTED INFERENCE CLUSTER LAUNCHER{RESET}{BLUE}")
    print(f"   Group 22 · GRS Project · Zero-Touch Startup")
    print(f"{'═'*60}{RESET}")

    # ── Step 1: Prep Config (Automatic) ──
    node_configs = get_or_create_default_config()

    # ── Step 2: Clear ports ──
    banner("🔧  PREPARING ENVIRONMENT")
    info("Clearing ports 5173, 8001, 8080...")
    for port in [5173, 8001, 8080]:
        subprocess.run(f"fuser -k {port}/tcp", shell=True, stderr=subprocess.DEVNULL)

    setup_environment()

    # ── Step 3: Start Docker cluster ──
    banner("🚀  STARTING INFERENCE CLUSTER")
    info(f"Using cluster config: {len(node_configs)} nodes...")
    result = subprocess.run(["docker", "compose", "up", "--build", "-d"])
    if result.returncode != 0:
        err("Docker failed to start. Check if Docker is running.")
        sys.exit(1)
    ok(f"All {len(node_configs)} containers online.")

    # ── Step 4: Start backend + frontend ──
    banner("🌐  STARTING DASHBOARD SERVICES")
    start_component("dashboard_api")
    ok("Dashboard API starting on port 8001...")

    frontend_path = os.path.join(FRONTEND_DIR, "node_modules")
    if not os.path.exists(frontend_path):
        warn("npm modules missing. Installing...")
        subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True)
    start_component("frontend_dev")
    ok("Frontend starting on port 5173...")

    # ── Step 5: Readiness probes ──
    banner("🔍  READINESS PROBES")
    lb_ok  = wait_for_ready("http://localhost:8080", "Load Balancer")
    api_ok = wait_for_ready("http://localhost:8001", "Dashboard API")

    print()
    if lb_ok and api_ok:
        print(f"{GREEN}{'═'*60}")
        print(f"   {BOLD}✅ CLUSTER ONLINE · {len(node_configs)} NODES ACTIVE{RESET}{GREEN}")
        print(f"{'─'*60}")
        print(f"   UI Dashboard   →  http://localhost:5173")
        print(f"   API Interface  →  http://localhost:8001")
        print(f"   Logs           →  ./{LOG_DIR}/")
        print(f"{'─'*60}")
        print(f"   Nodes configured:")
        for i, n in enumerate(node_configs):
            print(f"     Node {i+1}: {n['cpu']} CPU, {n['memory_mb']}MB RAM")
        print(f"{'═'*60}{RESET}")
        print()
        print(f"  {DIM}Press Ctrl+C to stop the cluster.{RESET}\n")
    else:
        warn("One or more services failed. Check logs in .group22_logs/")

    # ── Step 6: Self-healing watchdog ──
    try:
        while True:
            time.sleep(2)
            for name, data in components.items():
                p = data["process"]  # type: ignore
                if p and p.poll() is not None:  # type: ignore
                    exit_code = p.returncode  # type: ignore
                    warn(f"{name} (PID {p.pid}) died (exit {exit_code}).")  # type: ignore
                    if data["restarts"] < MAX_RESTARTS:  # type: ignore
                        data["restarts"] += 1  # type: ignore
                        info(f"Auto-healing: restarting {name} ({data['restarts']}/{MAX_RESTARTS})...")  # type: ignore
                        start_component(name)
                    else:
                        err(f"{name} failed too many times. Crashing cluster.")
                        signal_handler(None, None)
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()
