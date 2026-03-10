#!/usr/bin/env python3
import os
import platform
import subprocess
import argparse
import sys
import time

def detect_local_os():
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "mac"
    else:
        return "linux"

def detect_remote_os(host):
    try:
        # Check if Windows (cmd/powershell output)
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no", host, "cmd.exe /c echo %OS%"],
            capture_output=True, text=True
        )
        if result.returncode == 0 and "Windows" in result.stdout:
            return "windows"
        
        # Check if Unix/Linux/Mac
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no", host, "uname -s"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            out = result.stdout.strip().lower()
            if "darwin" in out:
                return "mac"
            else:
                return "linux"
    except Exception:
        pass
    return "linux"

def kill_local_port(port, os_type):
    if os_type == "windows":
        try:
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        except Exception:
            pass
    else: # mac/linux
        subprocess.run(f"lsof -ti:{port} 2>/dev/null | xargs kill -9 2>/dev/null || true", shell=True)

def run_remote_command(host, cmd, check=False):
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no", host, cmd]
    return subprocess.run(ssh_cmd, capture_output=True, text=True, check=check)

def main():
    parser = argparse.ArgumentParser(description="Deploy to lab remote across OS")
    parser.add_argument("--host", default="192.168.192.178", help="Remote host (default: 192.168.192.178)")
    parser.add_argument("--path", default="Downloads/GRS_Project", help="Remote project path")
    args = parser.parse_args()

    local_os = detect_local_os()
    
    print(f"--- Checking connectivity to {args.host} ---")
    result = subprocess.run(["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no", args.host, "echo ok"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Cannot reach {args.host}. Is the machine on and connected to the network?")
        sys.exit(1)
    print(f"  ✓ {args.host} is reachable")
        
    remote_os = detect_remote_os(args.host)
    
    print(f"--- Syncing code to {args.host} ---")
    if remote_os == "windows":
        run_remote_command(args.host, f'powershell -Command "if (-not (Test-Path $HOME/{args.path})) {{ New-Item -ItemType Directory -Force -Path $HOME/{args.path} }}"')
    else:
        run_remote_command(args.host, f"mkdir -p ~/{args.path}")
        
    # Exclude the scripts dir or existing python cache? We'll sync as the script does: scp -r ./* ...
    subprocess.run(f"scp -o StrictHostKeyChecking=no -o BatchMode=yes -o PasswordAuthentication=no -r ./* {args.host}:{args.path}", shell=True)
    
    print("--- Checking Remote Docker Cache ---")
    if remote_os == "windows":
        res = run_remote_command(args.host, 'powershell -Command "docker images -q python:3.10-slim-bookworm"')
    else:
        res = run_remote_command(args.host, "docker images -q python:3.10-slim-bookworm")
        
    if not res.stdout.strip():
        print(f"--- Base image missing on remote. Pulling locally and piping to {args.host} ---")
        subprocess.run(["docker", "pull", "--platform", "linux/amd64", "python:3.10-slim-bookworm"])
        
        load_cmd = "powershell -Command docker load" if remote_os == "windows" else "docker load"
        pipe_cmd = f"docker save python:3.10-slim-bookworm | ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o PasswordAuthentication=no {args.host} '{load_cmd}'"
        subprocess.run(pipe_cmd, shell=True)
    
    if remote_os == "windows":
        run_remote_command(args.host, f'powershell -Command "cd $HOME/{args.path}/group22_inference_service; docker build -t inference-node:latest ."')
    else:
        run_remote_command(args.host, f"bash -c 'cd ~/{args.path}/group22_inference_service && docker build -t inference-node:latest .'")
    print(f"--- Building Load Balancer Image on {args.host} ---")
    if remote_os == "windows":
        run_remote_command(args.host, f'powershell -Command "cd $HOME/{args.path}/group22_load_balancer; docker build -t load-balancer:latest ."')
    else:
        run_remote_command(args.host, f"bash -c 'cd ~/{args.path}/group22_load_balancer && docker build -t load-balancer:latest .'")

    print(f"--- Deploying to Kubernetes on {args.host} ---")
    if remote_os == "windows":
        run_remote_command(args.host, f'powershell -Command "cd $HOME/{args.path}; kubectl delete -f group22_k8s/load-balancer.yaml --ignore-not-found; kubectl apply -f group22_k8s/inference-cluster.yaml; kubectl apply -f group22_k8s/load-balancer.yaml"')
    else:
        run_remote_command(args.host, f"bash -c 'cd ~/{args.path} && kubectl delete -f group22_k8s/load-balancer.yaml --ignore-not-found; kubectl apply -f group22_k8s/inference-cluster.yaml && kubectl apply -f group22_k8s/load-balancer.yaml'")

    if remote_os == "windows":
        print("--- Opening Firewall for Load Balancer (Port 30000) ---")
        run_remote_command(args.host, 'powershell -Command "if (-not (Get-NetFirewallRule -DisplayName \'K8s-LoadBalancer\' -ErrorAction SilentlyContinue)) { New-NetFirewallRule -DisplayName \'K8s-LoadBalancer\' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 30000 }"')

    print("--- Waiting for pods to be ready ---")
    for i in range(1, 41):
        res = run_remote_command(args.host, "kubectl get pods -l app=inference-cluster -o jsonpath='{.items[*].status.phase}'")
        ready_status = res.stdout.strip()
        if ready_status and "Running" in ready_status and not any(s in ready_status for s in ["Pending", "ContainerCreating", "Init"]):
            print("  ✓ All inference pods are running.")
            break
        if i == 40:
            print(f"  ⚠ Timeout waiting for pods. Check: ssh {args.host} \"kubectl get pods\"")
        print(f"  Waiting for pods... ({i}/40)")
        time.sleep(5)

    print(f"--- Setting up SSH tunnel (localhost:30000 -> {args.host} K8s) ---")
    kill_local_port(30000, local_os)
    
    # Start tunnel
    tunnel = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no", "-f", "-N", "-L", f"30000:localhost:30000", args.host])
    if tunnel.returncode == 0:
        print(f"  ✓ SSH tunnel active: localhost:30000 -> {args.host}:30000")
    else:
        print("  ❌ Failed to create SSH tunnel. Run manually:")
        print(f"     ssh -f -N -L 30000:localhost:30000 {args.host}")
        sys.exit(1)

    print("\n==========================================")
    print("Deployment complete!")
    print("Cluster is accessible via http://localhost:30000")
    print("==========================================")
    print("\nRun benchmarks with:")
    print("  python3 group22_benchmarks/group22_load_generator.py --url http://localhost:30000/infer --strategy round-robin --load normal")

if __name__ == "__main__":
    main()
