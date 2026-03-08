# A CPU and Memory-Aware Load Balancing Interface for Distributed Inference Workloads

## Project Overview
This project explores system-level analysis of containerized inference workloads. We aim to build and profile a distributed system that uses a hardware-aware load balancer to optimize CPU and memory utilization, reducing tail latencies and preventing resource hotspots.

## Problem Statement
Most load balancers (e.g., Round Robin) do not consider real-time system resource usage. This leads to CPU hotspots and uneven resource utilization in containerized inference tasks. We investigate how hardware-aware routing based on CPU, cgroup throttling, and memory telemetry can improve system performance.

## Objectives
1. **Dynamic Middleware**: A lightweight Python proxy for routing based on real-time hardware metrics.
2. **Real-Time Monitoring**: Tracking CPU/Memory usage and throttling via Docker SDK and cgroups.
3. **Performance Analysis**: Comparing hardware-aware vs. static load balancing across latency, throughput, and stability.
4. **Kubernetes Evaluation**: Observing behavior in K8s environments with varying resource limits.

## Project Structure
- `group22_inference_service/`: CPU-based LLM inference container using `llama-cpp-python`.
- `group22_load_balancer/`: Middleware with hardware-aware routing logic.
- `group22_benchmarks/`: Scripts for load generation and performance analysis.
- `group22_k8s/`: Kubernetes manifests.

## Setup & Implementation Progress
1. **Inference Service**:
    - [x] FastAPI implementation with `llama-cpp-python`.
    - [x] Multi-stage Dockerfile for CPU-optimized builds.
    - [x] Local model download (e.g., TinyLlama GGUF).

2. **Load Balancer**:
    - [x] HTTP-based Telemetry Collector (Universal Support).
    - [x] Weighted "Burden Score" routing logic.
    - [x] Round Robin / Hardware-Aware dynamic strategy switching.

3. **Orchestration & Deployment**:
    - [x] `docker-compose` setup for local development.
    - [x] Kubernetes manifests for production-grade scaling.
    - [x] Automated remote deployment script (`group22_deploy_remote.sh`).

## Prerequisites

Install Python dependencies on your local machine:
```bash
pip install -r requirements.txt
```

## How to Run

### 1. Local Deployment (Docker Compose) — *Optional*
For local-only testing on a single machine. Not needed if using Kubernetes (Step 2).
```bash
# Download model (required only for Docker Compose — K8s pods download it automatically)
mkdir -p models
curl -L https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf -o models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

docker-compose up --build
```
The Load Balancer will be at `http://localhost:8080`.

### 2. Remote Kubernetes Deployment (Windows Host)
Deploy the full distributed stack to the remote `lab` machine:
```bash
./group22_scripts/group22_deploy_remote.sh
```

**What this script does (step by step):**
1. **Syncs code** → `scp` copies all project files to `lab:~/Downloads/GRS_Project`
2. **Checks Docker cache** → Ensures the `python:3.10-slim-bookworm` base image exists
3. **Builds images** → `docker build` for both `inference-node` and `load-balancer`
4. **Deploys to K8s** → `kubectl apply` for inference nodes (with model-downloading `initContainers`) and load balancer
5. **Opens firewall** → Creates Windows firewall rule for port 30000
6. **Waits for pods** → Polls `kubectl get pods` until all inference nodes are Running
7. **Opens SSH tunnel** → Starts `ssh -f -N -L 30000:localhost:30000 lab` in background

> **Why SSH Tunnel?** Docker Desktop on Windows runs Kubernetes inside a WSL2 VM. The NodePort (30000) binds to the VM's internal network (`172.18.0.x`), not the Windows host network. Direct connection to `192.168.194.95:30000` will fail. The SSH tunnel bypasses this by forwarding `localhost:30000` on your Mac through SSH to `localhost:30000` on the Windows host, which Docker Desktop does expose internally.

After deployment, the cluster is accessible at `http://localhost:30000`.

### 3. Running Benchmarks

The load generator has a **3-phase startup** before collecting data:
1. **⏳ Readiness Check** → Polls `/infer` every 3s until HTTP 200 (120s timeout)
2. **🔥 Warm-up** → 3 sequential requests to prime model caches
3. **❄️ Cooldown** → 5-second pause for telemetry to stabilize

```bash
# ── Step 1: Set strategy in group22_k8s/load-balancer.yaml ──
# Change ROUTING_STRATEGY to "round-robin" or "hardware-aware"

# ── Step 2: Deploy ──
./group22_scripts/group22_deploy_remote.sh

# for me (pyenv shell 3.12.6) -> I have my python 3.12.6 have the dependencies

# ── Step 3: Run benchmarks ──
# Normal load (2 concurrent, 20 tokens, 20 requests)
python3 group22_benchmarks/group22_load_generator.py --url http://localhost:30000/infer --strategy round-robin --load normal

# Stress load (10 concurrent, 100 tokens, 50 requests)
python3 group22_benchmarks/group22_load_generator.py --url http://localhost:30000/infer --strategy round-robin --load stress

# Breaking-point (ramps 5→100 concurrent until system fails)
python3 group22_benchmarks/group22_load_generator.py --url http://localhost:30000/infer --strategy round-robin --load breaking
```

Results are saved to the `group22_results/` directory as JSON files.

### 4. Data Visualization
Generate all performance charts from the collected results:
```bash
python3 group22_benchmarks/group22_plot_results.py
```

This generates the following charts in `group22_plots/`:
| Chart | Description |
| :--- | :--- |
| `success_rate.png` | Success rate comparison (Normal vs Stress) |
| `latency_comparison.png` | Mean + p95 latency bar charts |
| `latency_distribution.png` | KDE density overlay (Normal vs Stress) |
| `latency_{rr,ha}_{normal,stress}.png` | Individual latency histograms |
| `global_dashboard.png` | Unified reliability + tail latency dashboard |
| `breaking_point.png` | Success rate degradation as load ramps up |

## Troubleshooting

### Checking Pod Status
```bash
# List all pods and their status
ssh lab "kubectl get pods"

# Watch pods in real-time (useful while initContainers download the model)
ssh lab "kubectl get pods -w"

# Check why a pod is stuck (look for Events section at the bottom)
ssh lab "kubectl describe pod <POD_NAME>"

# View logs for a specific pod
ssh lab "kubectl logs <POD_NAME>"

# View initContainer logs (for model download progress)
ssh lab "kubectl logs <POD_NAME> -c model-downloader"
```

### Checking Connectivity
```bash
# Test if the SSH tunnel is active
curl -s http://localhost:30000/infer -X POST \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"test","max_tokens":5}'

# If the tunnel is dead, restart it manually:
ssh -f -N -L 30000:localhost:30000 lab

# Kill an existing tunnel (if port 30000 is already in use):
lsof -ti:30000 | xargs kill -9

# Test from inside the cluster (bypasses all networking):
ssh lab "kubectl exec debug-node -- python3 -c \"import urllib.request,json; req=urllib.request.Request('http://load-balancer:8080/infer',data=json.dumps({'prompt':'test','max_tokens':5}).encode(),headers={'Content-Type':'application/json'}); print(urllib.request.urlopen(req,timeout=10).read().decode())\""
```

### Common Issues
| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `ClientConnectorError` | SSH tunnel not running | Run `ssh -f -N -L 30000:localhost:30000 lab` |
| `ClientConnectorDNSError` | Using `lab` hostname instead of `localhost` | Always use `http://localhost:30000` |
| `ModuleNotFoundError: aiohttp` | Wrong Python version active | Run `pyenv shell 3.12.6` or `pip install -r requirements.txt` |
| Pods stuck in `ContainerCreating` | initContainer downloading model (~668MB) | Wait 3-5 minutes, monitor with `kubectl get pods -w` |
| Pods stuck in `Init:Error` | Model download failed (network issue) | Delete pod: `kubectl delete pod <NAME>` and let it recreate |
| `Model file not found` error | Volume mount missing | Ensure `group22_k8s/inference-cluster.yaml` has `initContainers` and `emptyDir` volume |
| Old pods not terminating | Rolling update waiting for new pods | Delete old deployments: `kubectl delete deploy inference-node-{1,2,3}` then reapply |

### Force Restart Everything
```bash
# Nuclear option: delete all deployments and redeploy from scratch
ssh lab "kubectl delete deploy --all"
./group22_scripts/group22_deploy_remote.sh
```

## Evaluation
See the [System Architecture Report](group22_report.md) for detailed performance analysis and hardware-aware routing findings.

## Team Members
- Aniket Raj Singh (MT25015)
- Aastha Kalbhor (MT25007)
- Saloni Narang (MT25081)
