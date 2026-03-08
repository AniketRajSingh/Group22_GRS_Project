# config.py - Modular Node Management
# Simply add or remove IP:PORT strings to this list to update the cluster.

INFERENCE_NODES = [
    "inference-node-1:8000",
    "inference-node-2:8000",
    "inference-node-3:8000",
]

# Routing Configuration
ROUTING_STRATEGY = "hardware-aware" # "hardware-aware" or "round-robin"

# Telemetry Polling Interval (seconds)
POLLING_INTERVAL = 1.0
