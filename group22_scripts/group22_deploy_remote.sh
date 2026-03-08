#!/bin/bash
# group22_deploy_remote.sh - Full stack zero-intervention deployment.
# Run from your Mac. Syncs code, builds images, and deploys to K8s on the remote host.

set -e  # Exit on first error

REMOTE_HOST="lab"
REMOTE_PATH="Downloads/GRS_Project"

# ── Pre-flight: check if remote host is reachable ──
echo "--- Checking connectivity to $REMOTE_HOST ---"
if ! ssh -o ConnectTimeout=5 $REMOTE_HOST "echo ok" &>/dev/null; then
    echo "❌ Cannot reach $REMOTE_HOST. Is the machine on and connected to the network?"
    echo "   Verify: ping 192.168.194.95"
    exit 1
fi
echo "  ✓ $REMOTE_HOST is reachable"

# ── Step 1: Sync code ──
echo "--- Syncing code to $REMOTE_HOST ---"
ssh $REMOTE_HOST "powershell -Command \"if (-not (Test-Path \$HOME/$REMOTE_PATH)) { New-Item -ItemType Directory -Force -Path \$HOME/$REMOTE_PATH }\""
scp -r ./* $REMOTE_HOST:$REMOTE_PATH

# ── Step 2: Check Docker cache ──
echo "--- Checking Remote Docker Cache ---"
REMOTE_IMAGE_EXISTS=$(ssh $REMOTE_HOST "powershell -Command \"docker images -q python:3.10-slim-bookworm\"")

if [ -z "$REMOTE_IMAGE_EXISTS" ]; then
    echo "--- Base image missing on remote. Pulling locally and piping to $REMOTE_HOST ---"
    docker pull --platform linux/amd64 python:3.10-slim-bookworm
    docker save python:3.10-slim-bookworm | ssh $REMOTE_HOST "powershell -Command docker load"
fi

# ── Step 3: Build images ──
echo "--- Building Inference Node Image on $REMOTE_HOST ---"
ssh $REMOTE_HOST "powershell -Command \"cd \$HOME/$REMOTE_PATH/group22_inference_service; docker build -t inference-node:latest .\""

echo "--- Building Load Balancer Image on $REMOTE_HOST ---"
ssh $REMOTE_HOST "powershell -Command \"cd \$HOME/$REMOTE_PATH/group22_load_balancer; docker build -t load-balancer:latest .\""

# ── Step 4: Deploy to K8s ──
echo "--- Deploying to Kubernetes on $REMOTE_HOST ---"
ssh $REMOTE_HOST "powershell -Command \"cd \$HOME/$REMOTE_PATH; kubectl delete -f group22_k8s/load-balancer.yaml --ignore-not-found; kubectl apply -f group22_k8s/inference-cluster.yaml; kubectl apply -f group22_k8s/load-balancer.yaml\""

# ── Step 5: Firewall ──
echo "--- Opening Firewall for Load Balancer (Port 30000) ---"
ssh $REMOTE_HOST "powershell -Command \"if (-not (Get-NetFirewallRule -DisplayName 'K8s-LoadBalancer' -ErrorAction SilentlyContinue)) { New-NetFirewallRule -DisplayName 'K8s-LoadBalancer' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 30000 }\""

# ── Step 6: Wait for pods ──
echo "--- Waiting for pods to be ready ---"
for i in $(seq 1 40); do
    READY=$(ssh $REMOTE_HOST "kubectl get pods -l app=inference-cluster -o jsonpath='{.items[*].status.phase}'" 2>/dev/null)
    # Check that we got output AND all phases are "Running"
    if [ -n "$READY" ] && echo "$READY" | grep -q "Running" && ! echo "$READY" | grep -q "Pending\|ContainerCreating\|Init"; then
        echo "  ✓ All inference pods are running."
        break
    fi
    if [ "$i" -eq 40 ]; then
        echo "  ⚠ Timeout waiting for pods. Check: ssh $REMOTE_HOST \"kubectl get pods\""
    fi
    echo "  Waiting for pods... ($i/40)"
    sleep 5
done

# ── Step 7: SSH tunnel ──
echo "--- Setting up SSH tunnel (localhost:30000 → $REMOTE_HOST K8s) ---"
# Kill any existing tunnel on port 30000
lsof -ti:30000 2>/dev/null | xargs kill -9 2>/dev/null || true
# Start background SSH tunnel
if ssh -f -N -L 30000:localhost:30000 $REMOTE_HOST; then
    echo "  ✓ SSH tunnel active: localhost:30000 → $REMOTE_HOST:30000"
else
    echo "  ❌ Failed to create SSH tunnel. Run manually:"
    echo "     ssh -f -N -L 30000:localhost:30000 $REMOTE_HOST"
    exit 1
fi

echo ""
echo "=========================================="
echo "Deployment complete!"
echo "Cluster is accessible via http://localhost:30000"
echo "=========================================="
echo ""
echo "Run benchmarks with:"
echo "  python3 group22_benchmarks/group22_load_generator.py --url http://localhost:30000/infer --strategy round-robin --load normal"
