#!/bin/bash
# group22_cleanup_remote.sh - Run this on your local Mac to clean up lab.
# Removes: K8s deployments, Docker images, project files, downloaded models, SSH tunnels.

REMOTE_HOST="lab"
REMOTE_PATH="Downloads/GRS_Project"

echo "--- Killing local SSH tunnel (port 30000) ---"
lsof -ti:30000 2>/dev/null | xargs kill -9 2>/dev/null || true
echo "  ✓ SSH tunnel stopped"

echo "--- Deleting Kubernetes Resources on $REMOTE_HOST ---"
ssh $REMOTE_HOST "kubectl delete deploy --all --ignore-not-found 2>nul"
ssh $REMOTE_HOST "kubectl delete svc inference-node-1 inference-node-2 inference-node-3 load-balancer --ignore-not-found 2>nul"
ssh $REMOTE_HOST "kubectl delete pod debug-node --ignore-not-found 2>nul"
echo "  ✓ All K8s resources deleted"

echo "--- Removing Docker Images on $REMOTE_HOST ---"
ssh $REMOTE_HOST "powershell -Command \"docker rmi inference-node:latest load-balancer:latest --force 2>\$null\""
echo "  ✓ Docker images removed"

echo "--- Pruning unused Docker data on $REMOTE_HOST ---"
ssh $REMOTE_HOST "powershell -Command \"docker system prune -f 2>\$null\""
echo "  ✓ Docker cache pruned"

echo "--- Deleting Project Files on $REMOTE_HOST ---"
ssh $REMOTE_HOST "powershell -Command \"Remove-Item -Recurse -Force -Path \$HOME/$REMOTE_PATH -ErrorAction SilentlyContinue\""
echo "  ✓ Project directory removed"

echo "--- Removing Windows Firewall Rule ---"
ssh $REMOTE_HOST "powershell -Command \"Remove-NetFirewallRule -DisplayName 'K8s-LoadBalancer' -ErrorAction SilentlyContinue\""
echo "  ✓ Firewall rule removed"

echo "--- Removing Port Proxy Rules ---"
ssh $REMOTE_HOST "powershell -Command \"netsh interface portproxy reset\""
echo "  ✓ Port proxy rules cleared"

# --- FULL TEARDOWN (Commented Out) ---
# Use these lines ONLY if you want to completely remove Docker and Kubernetes from the lab
# echo "--- Uninstalling Docker and Kubectl ---"
# ssh $REMOTE_HOST "powershell -Command winget uninstall --id Docker.DockerDesktop"
# ssh $REMOTE_HOST "powershell -Command winget uninstall --id Kubernetes.kubectl"

echo ""
echo "=========================================="
echo "Cleanup complete!"
echo "All traces of GRS_Project removed from $REMOTE_HOST."
echo "=========================================="
