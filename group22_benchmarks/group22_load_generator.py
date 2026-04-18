import asyncio
import aiohttp
import time
import json
import argparse
import sys
import os
import random

async def send_request(session, url, prompt_id, max_tokens, strategy=None):
    """Sends a single inference request and returns performance metrics."""
    payload = {
        "prompt": f"Write a short story about task {prompt_id}",
        "max_tokens": max_tokens
    }
    target_url = f"{url}?strategy={strategy}" if strategy else url
    start_time = time.time()
    try:
        async with session.post(target_url, json=payload, timeout=180.0) as response:
            result = await response.json()
            latency = (time.time() - start_time) * 1000
            return {
                "prompt_id": prompt_id,
                "status": response.status,
                "latency_ms": latency,
                "node": result.get("node_id", "unknown")
            }
    except Exception as e:
        return {
            "prompt_id": prompt_id,
            "status": "error",
            "error": str(e),
            "latency_ms": (time.time() - start_time) * 1000,
            "node": "unknown"
        }

async def run_benchmark(url, concurrent_requests, total_requests, min_tokens, max_tokens, strategy):
    """Runs a benchmark suite with controlled concurrency and live progress reporting."""
    print(f"Starting benchmark on {url}")
    print(f"Strategy params -> Concurrent: {concurrent_requests}, Total: {total_requests}, Bounds: [{min_tokens}, {max_tokens}], Strategy: {strategy}")
    
    results = []
    # Use a semaphore to strictly respect the concurrency limit
    sem = asyncio.Semaphore(concurrent_requests)

    async def wrapped_request(session, url, i, tokens):
        async with sem:
            return await send_request(session, url, i, tokens, strategy)

    async with aiohttp.ClientSession() as session:
        tasks = []
        
        # Guard against backwards ranges
        safe_min = min(min_tokens, max_tokens)
        safe_max = max(min_tokens, max_tokens)
        if safe_min == safe_max:
            safe_max += 1

        range_delta = safe_max - safe_min

        for i in range(total_requests):
            # Heterogeneous payload simulation (85% Minnows, 15% Whales)
            if random.random() > 0.15:
                # Minnow: fast, simple requests constrained to the lower 20% of the range
                upper_minnow_bound = safe_min + int(range_delta * 0.20)
                t = random.randint(safe_min, max(safe_min, upper_minnow_bound))
            else:
                # Whale: aggressive, system-locking requests constrained to the upper 10% of the extreme
                lower_whale_bound = safe_max - int(range_delta * 0.10)
                t = random.randint(min(safe_max, lower_whale_bound), safe_max)
            tasks.append(asyncio.create_task(wrapped_request(session, url, i, t)))
        
        completed = 0
        for task in asyncio.as_completed(tasks):
            res = await task
            results.append(res)
            completed += 1
            
            # 1. Dashboard Console Output (Professional & Descriptive)
            node_id = res.get('node', 'unknown')
            node_display = node_id.split('-')[-1] if '-' in node_id else node_id
            timestamp = time.strftime("[%H:%M:%S]")
            print(f"{timestamp} [Node-{node_display}] Request {completed}/{total_requests} (Status: {res['status']}, {res['latency_ms']:.0f}ms)", flush=True)
            
            # 2. Machine Readable Data for API Streaming
            progress_data = {
                "id": completed,
                "total": total_requests,
                "node": node_id,
                "latency_ms": res['latency_ms'],
                "status": res['status'],
                "timestamp": time.time()
            }
            print(f"__PROGRESS_DATA__:{json.dumps(progress_data)}", flush=True)
            
    return results

async def wait_for_ready(url, timeout=600, interval=3):
    """Poll the endpoint until it returns HTTP 200, ensuring all pods are ready."""
    health_url = url.replace("/infer", "/health")
    print(f"⏳ Waiting for system readiness on {health_url} ...")
    start = time.time()
    async with aiohttp.ClientSession() as session:
        while time.time() - start < timeout:
            try:
                async with session.get(health_url, timeout=10) as resp:
                    if resp.status == 200:
                        elapsed = time.time() - start
                        print(f"✅ System ready after {elapsed:.1f}s")
                        return True
                    else:
                        print(f"   ... got status {resp.status}, retrying in {interval}s")
            except Exception as e:
                print(f"   ... not ready ({type(e).__name__}), retrying in {interval}s")
            await asyncio.sleep(interval)
    print("❌ Timeout waiting for system readiness!")
    return False

async def warm_up(url, rounds=1):
    """Send a few requests to warm up model caches and JIT paths."""
    print(f"🔥 Warming up with {rounds} sequential requests ...")
    async with aiohttp.ClientSession() as session:
        for i in range(rounds):
            await send_request(session, url, f"warmup_{i}", 10, "round-robin")
    print("   Warm-up complete.\n")

def cooldown(seconds=1):
    """Pause between runs to let CPU/memory telemetry settle."""
    print(f"❄️  Cooling down for {seconds}s ...")
    time.sleep(seconds)
    print("   Cooldown complete.\n")

def save_results_with_tag(results, strategy, load_type, tag):
    """Saves benchmark results to a JSON file with a specific tag."""
    os.makedirs("group22_results", exist_ok=True)
    filename = f"group22_results/{tag}_results_{strategy}_{load_type}_{int(time.time())}.json"
    with open(filename, "w") as f:
        json.dump(results, f, indent=4)
    print(f"\n[SUCCESS] Results saved to {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080/infer")
    parser.add_argument("--strategy", default="hardware-aware")
    parser.add_argument("--tag", default="static")
    args = parser.parse_args()

    # Determine load parameters from environment (dashboard) or defaults
    concurrent = int(os.environ.get("BENCHMARK_CONCURRENT", 2))
    total = int(os.environ.get("BENCHMARK_TOTAL", 20))
    min_tokens = int(os.environ.get("BENCHMARK_MIN_TOKENS", 10))
    max_tokens = int(os.environ.get("BENCHMARK_MAX_TOKENS", 50))
    load_type = "normal" if concurrent < 5 else "stress"

    # Step 1: Wait for system readiness
    ready = asyncio.run(wait_for_ready(args.url))
    if not ready:
        sys.exit(1)

    # Step 2: Widespread warm up across all logical cluster nodes (ensuring Round-Robin hits 3+ nodes)
    asyncio.run(warm_up(args.url, rounds=5))

    # Step 3: Brief cooldown
    cooldown(1)

    # Step 4: Run benchmark
    print("=" * 60)
    results = asyncio.run(run_benchmark(args.url, concurrent, total, min_tokens, max_tokens, args.strategy))
    
    # Step 5: Save final results
    save_results_with_tag(results, args.strategy, load_type, args.tag)
