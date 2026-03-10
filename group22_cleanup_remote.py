#!/usr/bin/env python3
import os
import platform
import subprocess
import argparse
import sys

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
                
    except Exception as e:
        print(f"Error detecting remote OS: {e}")
    
    # Fallback to linux
    return "linux"

def kill_local_port(port, os_type):
    print(f"--- Killing local port {port} ---")
    if os_type == "windows":
        try:
            # find PID using port
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            print("  ✓ SSH tunnel stopped")
        except Exception as e:
            print(f"  ⚠ Failed to stop SSH tunnel: {e}")
    else: # mac or linux
        subprocess.run(f"lsof -ti:{port} 2>/dev/null | xargs kill -9 2>/dev/null || true", shell=True)
        print("  ✓ SSH tunnel stopped")

def run_remote_command(host, cmd, shell=False):
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no", host, cmd]
    if shell:
        subprocess.run(" ".join(ssh_cmd), shell=True)
    else:
        subprocess.run(ssh_cmd)

def main():
    parser = argparse.ArgumentParser(description="Clean up lab resources across OS")
    parser.add_argument("--host", default="192.168.192.178", help="Remote host (default: 192.168.192.178)")
    parser.add_argument("--path", default="Downloads/GRS_Project", help="Remote project path")
    args = parser.parse_args()

    local_os = detect_local_os()
    print(f"Detected Local OS: {local_os.upper()}")

    print(f"--- Checking connectivity to {args.host} ---")
    result = subprocess.run(["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no", args.host, "echo ok"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Cannot reach {args.host}.")
        sys.exit(1)
        
    remote_os = detect_remote_os(args.host)
    print(f"Detected Remote OS: {remote_os.upper()}")
    
    kill_local_port(30000, local_os)

    print(f"--- Deleting Kubernetes Resources on {args.host} ---")
    if remote_os == "windows":
        run_remote_command(args.host, "kubectl delete deploy --all --ignore-not-found 2>nul")
        run_remote_command(args.host, "kubectl delete svc inference-node-1 inference-node-2 inference-node-3 load-balancer --ignore-not-found 2>nul")
        run_remote_command(args.host, "kubectl delete pod debug-node --ignore-not-found 2>nul")
    else:
        run_remote_command(args.host, "kubectl delete deploy --all --ignore-not-found 2>/dev/null || true")
        run_remote_command(args.host, "kubectl delete svc inference-node-1 inference-node-2 inference-node-3 load-balancer --ignore-not-found 2>/dev/null || true")
        run_remote_command(args.host, "kubectl delete pod debug-node --ignore-not-found 2>/dev/null || true")
    print("  ✓ All K8s resources deleted")

    print(f"--- Removing Docker Images on {args.host} ---")
    if remote_os == "windows":
        run_remote_command(args.host, 'powershell -Command "docker rmi inference-node:latest load-balancer:latest --force 2>$null"')
    else:
        run_remote_command(args.host, "docker rmi inference-node:latest load-balancer:latest --force 2>/dev/null || true")
    print("  ✓ Docker images removed")

    print(f"--- Pruning unused Docker data on {args.host} ---")
    if remote_os == "windows":
        run_remote_command(args.host, 'powershell -Command "docker system prune -f 2>$null"')
    else:
        run_remote_command(args.host, "docker system prune -f 2>/dev/null || true")
    print("  ✓ Docker cache pruned")

    print(f"--- Deleting Project Files on {args.host} ---")
    if remote_os == "windows":
        run_remote_command(args.host, f'powershell -Command "Remove-Item -Recurse -Force -Path $HOME/{args.path} -ErrorAction SilentlyContinue"')
    else:
        run_remote_command(args.host, f"rm -rf ~/{args.path}")
    print("  ✓ Project directory removed")

    if remote_os == "windows":
        print("--- Removing Windows Firewall Rule ---")
        run_remote_command(args.host, 'powershell -Command "Remove-NetFirewallRule -DisplayName \'K8s-LoadBalancer\' -ErrorAction SilentlyContinue"')
        print("  ✓ Firewall rule removed")
        
        print("--- Removing Port Proxy Rules ---")
        run_remote_command(args.host, 'powershell -Command "netsh interface portproxy reset"')
        print("  ✓ Port proxy rules cleared")

    print("\n==========================================")
    print("Cleanup complete!")
    print(f"All traces of GRS_Project removed from {args.host}.")
    print("==========================================")

if __name__ == "__main__":
    main()
