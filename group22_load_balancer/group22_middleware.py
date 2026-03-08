from fastapi import FastAPI, Request, HTTPException
import httpx
import logging
import group22_config
from group22_telemetry import TelemetryCollector
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LoadBalancer")

app = FastAPI(title="Modular Hardware-Aware Load Balancer")

# Load settings from group22_config.py, allow ENV overrides
NODES = group22_config.INFERENCE_NODES
ROUTING_STRATEGY = os.getenv("ROUTING_STRATEGY", group22_config.ROUTING_STRATEGY)
POLLING_INTERVAL = float(os.getenv("POLLING_INTERVAL", group22_config.POLLING_INTERVAL))

collector = TelemetryCollector(NODES, polling_interval=POLLING_INTERVAL)
collector.start()

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

@app.post("/infer")
async def proxy_infer(request: Request):
    # Determine which node to use based on dynamic strategy
    if ROUTING_STRATEGY == "round-robin":
        target_node = get_next_node_round_robin()
    else:
        target_node = get_best_node_hardware_aware()
        
    target_url = f"http://{target_node}/infer"
    logger.info(f"Routing to {target_node} [Active: {active_requests[target_node]}] using {ROUTING_STRATEGY}")
    
    body = await request.json()
    active_requests[target_node] += 1
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(target_url, json=body, timeout=120.0)
            return response.json()
        except Exception as e:
            logger.error(f"Error proxying request to {target_node}: {e}")
            raise HTTPException(status_code=502, detail=f"Target node {target_node} unreachable")
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
    return collector.stats

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
