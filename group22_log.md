# Development Log

## Project Details
- **Project Title**: A CPU and Memory-Aware Load Balancing Interface for Distributed Inference Workloads
- **Team**: Aniket Raj Singh, Aastha Kalbhor, Saloni Narang
- **Start Date**: 2026-02-22

---

## Log Entries

### [2026-02-22] - Initial Setup and Technology Selection

#### Status: Initializing Repository
- Created `README.md`, `.gitignore`, and placeholder `Dockerfile`.
- Drafted `group22_report.md` with core architecture.

#### Key Decision: llama-cpp-python vs. Ollama
**Selected**: `llama-cpp-python`

**Why not Ollama?**
1. **Granular Control**: `llama-cpp-python` allows us to pin exactly how many CPU threads (`n_threads`) are used per inference. This is critical for simulating resource contention and monitoring cgroup behavior.
2. **Predictable Observability**: Ollama runs a background daemon with its own internal queue management. This "opaqueness" would make it harder to build a custom load balancer, as the daemon might optimize things behind the scenes, masking the very system-level metrics (throttling, raw CPU spikes) we want to study.
3. **Single Process Architecture**: `llama-cpp-python` runs as a standard Python process, making it easier to track via standard Docker SDK metrics without the overhead of an intermediate management layer.
4. **Lightweight Footprint**: Better suited for running multiple concurrent containers on a single-node system without wasting memory on multiple management daemons.

#### Implementation Details
- **Base OS**: Mac (Development), Linux/Docker (Deployment)
- **Primary Language**: Python 3.10+
- **Inference Engine**: llama-cpp-python
- **Telemetry**: Docker SDK for Python, `/proc` filesystem analysis
- **Proxy/LB**: `aiohttp` / `FastAPI`
- **Containerization**: Docker & Kubernetes (Local/Single-node)

---

### [2026-02-22] - Inference Service Implementation

#### Status: Core Node Prototype Built
- Created `group22_inference_service/group22_app.py`:
    - Uses **FastAPI** for a clean HTTP interface.
    - Integrates **llama-cpp-python** for CPU-bound GGUF inference.
    - Added `/stats` endpoint using `psutil` to track container-internal metrics (CPU %, memory, load).
    - Added `/health` endpoint for load balancer heartbeat.
- Created `group22_inference_service/Dockerfile`:
    - Multi-stage build to reduce final image size.
    - Pre-installs `build-essential` and `cmake` for compiling `llama-cpp-python`.
    - Configurable via ENV variables (`MODEL_PATH`, `N_THREADS`, `NODE_ID`).

### [2026-02-22] - Load Balancer & Telemetry Implementation

#### Status: Middleware Layer Complete
- Created `group22_load_balancer/group22_telemetry.py`:
    - Uses **Docker SDK for Python** to poll `container.stats()`.
    - Handles asynchronous stats collection in a background thread to avoid blocking proxy requests.
    - Implements CPU percentage calculation based on system and container delta time (matching Docker CLI logic).
- Created `group22_load_balancer/group22_middleware.py`:
    - Implements two routing strategies: `round-robin` and `hardware-aware`.
    - **Hardware-Aware Logic**: Calculates a "Burden Score" for each node based on weighted CPU and Memory indices.
    - Provides a `/telemetry` endpoint to export aggregated cluster health.

### [2026-02-22] - Container Orchestration & Resource Limits

#### Status: Infrastructure for Testing Ready
- Created `docker-compose.yaml`:
    - Manages 3 inference nodes (`node-1`, `node-2`, `node-3`).
    - **Experimental Setup**: Node 2 is deliberately throttled to `0.5` CPUs, while Nodes 1 and 3 have `1.0` CPUs. This allows us to verify if the middleware correctly identifies Node 2 as "burdened" even if its internal queue is empty.
    - Mounts a local `./models` directory to avoid re-downloading LLM weights.
    - Grants the Load Balancer access to `/var/run/docker.sock` for telemetry collection.
- Created `group22_load_balancer/Dockerfile`: Standard Python slim image with `docker` and `fastapi` dependencies.

#### Observation
The differential CPU limits between nodes are key to proving the "hardware-aware" thesis. Static Round Robin should treat Node 2 as equal, while our middleware should avoid it under load.

### [2026-02-22] - Benchmarking Suite Implementation

#### Status: Testing Framework Ready
- Created `group22_benchmarks/group22_load_generator.py`:
    - Asynchronous request generator using `aiohttp`.
    - Supports concurrent request limits to stress test the middleware.
    - Captures end-to-end latency and the target node ID for each request.
- Created `group22_benchmarks/group22_analyze_results.py`:
    - Parses JSON results to calculate key performance indicators (KPIs).
    - **KPIs**: Mean Latency, Median, p95, p99, and Node Distribution %.

### [2026-02-22] - "Plug and Play" Modular Refactor

#### Status: Modular Architecture Active
- Created `group22_load_balancer/group22_config.py`:
    - Centralized node management. Users can now add/remove LLM hosts by simply updating the `INFERENCE_NODES` list.
- Refactored `group22_load_balancer/group22_telemetry.py`:
    - **Universal Polling**: Switched from Docker-specific SDK to cross-platform HTTP polling.
    - Collector now queries each node's `/stats` endpoint. This allows monitoring of nodes hosted on different machines, VMs, or cloud providers as long as they run our `inference_service`.
- Refactored `group22_load_balancer/group22_middleware.py`:
    - Now dynamically reads configuration and handles node health checks. Requests are only routed to nodes confirmed "healthy" by the telemetry collector.

#### Observation
The system is now infrastructure-agnostic. We can scale the inference cluster by adding plain IP addresses without modifying core proxy logic or Docker Compose files.

### [2026-02-22] - Remote Kubernetes Integration (lab)

#### Status: Remote Cluster Orchestration Ready
- Created `group22_k8s/inference-cluster.yaml`:
    - Defines a heterogeneous cluster on Kubernetes.
    - Uses **NodePort** (30001-30003) to expose pods to the local network.
    - Implements hardcoded resource limits (0.5 vs 1.0 CPU) at the K8s pod level for performance profiling.
- Created `group22_scripts/group22_deploy_remote.sh`:
    - Automated SSH/SCP script to sync code, build images, and apply K8s specs on `lab` remotely.
- Refactored `group22_load_balancer/group22_config.py` to point to the `lab` NodePort endpoints.

#### Observation
By using K8s resource limits, we can now observe how **Kubernetes CFS Throttling** impacts inference latency and how our hardware-aware load balancer dynamically shifts load to unthrottled pods.
### [2026-02-22] - Remote Service Startup (Troubleshooting)

#### Status: Cold Starting Daemon
- **Docker**: Package installed, process started, but daemon API is not yet reachable.
- **Kubernetes**: Not yet answering on `localhost:8080`.
- **Diagnosis**: Windows likely needs a **reboot** to finalize virtualization (Hyper-V/WSL2). Kubernetes must also be manually toggled in the Docker Desktop UI.

#### Observation
Automating Docker/K8s startup via SSH on Windows is limited by the GUI requirement of Docker Desktop. Manual intervention in the host UI is mandatory for the initial cluster enablement.
- Created `group22_scripts/group22_cleanup_remote.sh`:
    - Designed to be run from the local Mac.
    - Uses SSH to delete K8s deployments, prune unused Docker images, and recursively delete the project folder on the remote `lab` machine.
- Updated `task.md` to track the mandatory project teardown.

#### Observation
Ensuring a clean exit on the remote host is part of responsible system experimentation, especially when using shared or non-dedicated hardware like a "lab" PC.
### [2026-02-22] - Zero-Intervention Remote Automation

#### Status: Bypassing Windows SSH Restrictions
- **Challenge**: Windows SSH sessions block Docker's credential helper, stalling base image pulls.
- **Solution**: Updated `group22_deploy_remote.sh` to use the `docker --config` flag pointing to a temporary, empty configuration directory.
- **Benefit**: This forces Docker to operate in "anonymous" mode for the public base image, eliminating the need for manual `docker pull` on the host machine.
