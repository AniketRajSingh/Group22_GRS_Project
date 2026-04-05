from fastapi import FastAPI, Request, HTTPException
from typing import Optional, Dict
import httpx
import logging
import group22_config
from group22_telemetry import TelemetryCollector
import os
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LoadBalancer")

app = FastAPI(title="Modular Hardware-Aware Load Balancer")

# Load settings from group22_config.py, allow ENV overrides
env_nodes = os.getenv("NODES")
if env_nodes:
    # Handle both "node1,node2" and "node1:8000,node2:8000" formats
    NODES = []
    for n in env_nodes.split(","):
        n = n.strip()
        if ":" not in n:
            n = f"{n}:8000"
        NODES.append(n)
else:
    NODES = group22_config.INFERENCE_NODES

ROUTING_STRATEGY = os.getenv("ROUTING_STRATEGY", group22_config.ROUTING_STRATEGY)
POLLING_INTERVAL = float(os.getenv("POLLING_INTERVAL", group22_config.POLLING_INTERVAL))

collector = TelemetryCollector(NODES, polling_interval=POLLING_INTERVAL)
collector.start()

# Global persistent client to avoid socket exhaustion
client = httpx.AsyncClient(timeout=3600.0)

@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()

# For round-robin and tracking
current_node_index = 0
active_requests = {node: 0 for node in NODES}

def get_next_node_round_robin():
    global current_node_index
    # Only route to healthy nodes
    healthy_nodes = [n for n in NODES if collector.get_node_stats(n).get("healthy", False)]
    if not healthy_nodes:
        return NODES[0] # Fallback
        
    node_name = healthy_nodes[current_node_index % len(healthy_nodes)]
    current_node_index = (current_node_index + 1)
    return node_name

def get_best_node_hardware_aware():
    """Selects the node with the lowest 'burden score'."""
    best_node = None
    min_score = float('inf')
    
    for name in NODES:
        stats = collector.get_node_stats(name)
        if not stats.get("healthy", False):
            continue
            
        # Burden Score Formula (Refined):
        # Score = (CPU % * 0.4) + (Memory Usage % * 0.1) + (Active Requests * 50)
        cpu = stats.get("cpu_percent", 100)
        mem = stats.get("memory_mb", 1024) / 1024 * 100
        busy_factor = active_requests.get(name, 0) * 50
        
        score = (cpu * 0.4) + (mem * 0.1) + busy_factor
        
        if score < min_score:
            min_score = score
            best_node = name
            
    return best_node or get_next_node_round_robin()

def get_node_least_connection():
    best_node = None
    min_reqs = 9999999 # type: int
    healthy_nodes = [n for n in NODES if collector.get_node_stats(n).get("healthy", False)]
    if not healthy_nodes:
        return NODES[0]
        
    for name in healthy_nodes:
        reqs = active_requests.get(name, 0)
        if reqs < min_reqs:
            min_reqs = reqs
            best_node = name
    return best_node or get_next_node_round_robin()

def get_node_hashing(body: dict):
    healthy_nodes = [n for n in NODES if collector.get_node_stats(n).get("healthy", False)]
    if not healthy_nodes:
        return NODES[0]
    
    prompt = body.get("prompt", "")
    hash_val = int(hashlib.md5(prompt.encode('utf-8')).hexdigest(), 16)
    
    return healthy_nodes[hash_val % len(healthy_nodes)]

@app.post("/infer")
async def proxy_infer(request: Request, strategy: Optional[str] = None):
    # Determine which node to use based on dynamic strategy
    effective_strategy = strategy or ROUTING_STRATEGY
    
    # Critical: Await JSON body FIRST to prevent asyncio yield from causing a race
    # condition when selecting a hardware-aware node concurrently.
    body = await request.json()
    
    target_node: str = ""
    if effective_strategy == "round-robin":
        target_node = str(get_next_node_round_robin())
    elif effective_strategy == "least-connection":
        target_node = str(get_node_least_connection())
    elif effective_strategy == "hashing":
        target_node = str(get_node_hashing(body))
    else:
        target_node = str(get_best_node_hardware_aware())
        
    target_url = f"http://{target_node}/infer"
    logger.info(f"Routing to {target_node} [Active: {active_requests[target_node]}] using {effective_strategy}")
    
    active_requests[target_node] += 1
    
    try:
        resp = await client.post(
            f"http://{target_node}/infer",
            json=body
        )
        # Log any non-200 status for easier debugging
        if resp.status_code != 200:
            logger.warning(f"Node {target_node} returned status {resp.status_code}")
            
        return resp.json()
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        logger.error(f"Error proxying request to {target_node}: {e}\n{error_msg}")
        raise HTTPException(status_code=502, detail=f"Target node {target_node} unreachable: {str(e)}")
    finally:
        active_requests[target_node] -= 1

@app.get("/health")
async def health():
    return {
        "status": "up", 
        "configured_nodes": NODES, 
        "strategy": ROUTING_STRATEGY,
        "polling_interval": POLLING_INTERVAL
    }

@app.get("/telemetry")
async def get_all_telemetry():
    return {
        "stats": collector.stats, 
        "active_requests": active_requests
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
