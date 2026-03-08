import asyncio
import aiohttp
import time
import json
import random
import argparse
import sys
import os

async def send_request(session, url, prompt_id, max_tokens):
    payload = {
        "prompt": f"Write a short story about task {prompt_id}",
        "max_tokens": max_tokens
    }
    start_time = time.time()
    try:
        async with session.post(url, json=payload, timeout=120) as response:
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
            "latency_ms": (time.time() - start_time) * 1000
        }

async def run_benchmark(url, concurrent_requests, total_requests, max_tokens):
    print(f"Starting benchmark on {url}")
    print(f"Mode: {'Normal' if concurrent_requests < 5 else 'Stress'}")
    print(f"Concurrent: {concurrent_requests}, Total: {total_requests}, Tokens: {max_tokens}")
    
    results = []
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(total_requests):
            if len(tasks) >= concurrent_requests:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    results.append(await task)
                tasks = list(pending)
            
            tasks.append(asyncio.create_task(send_request(session, url, i, max_tokens)))
            
        if tasks:
            done = await asyncio.gather(*tasks)
            results.extend(done)
            
    return results

async def wait_for_ready(url, timeout=120, interval=3):
    """Poll the endpoint until it returns HTTP 200, ensuring all pods are ready."""
    print(f"⏳ Waiting for system readiness on {url} ...")
    start = time.time()
    async with aiohttp.ClientSession() as session:
        while time.time() - start < timeout:
            try:
                payload = {"prompt": "health check", "max_tokens": 5}
                async with session.post(url, json=payload, timeout=15) as resp:
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

async def warm_up(url, rounds=3):
    """Send a few requests to warm up model caches and JIT paths."""
    print(f"🔥 Warming up with {rounds} sequential requests ...")
    async with aiohttp.ClientSession() as session:
        for i in range(rounds):
            await send_request(session, url, f"warmup_{i}", 10)
    print("   Warm-up complete.\n")

def cooldown(seconds=5):
    """Pause between runs to let CPU/memory telemetry settle."""
    print(f"❄️  Cooling down for {seconds}s ...")
    time.sleep(seconds)
    print("   Cooldown complete.\n")

async def run_breaking_point(url, max_tokens=50):
    """
    Ramp concurrency until the system breaks.
    Each wave fires `concurrency` simultaneous requests and measures success rate.
    Stops when success rate < 50% or we reach max concurrency.
    """
    levels = [5, 10, 15, 20, 30, 40, 50, 75, 100]
    requests_per_wave = 20
    all_results = []
    wave_summary = []
    test_start = time.time()

    print("=" * 60)
    print("🔨 BREAKING-POINT TEST — Ramping load until failure")
    print(f"   Levels: {levels}")
    print(f"   Requests per wave: {requests_per_wave}")
    print(f"   Max tokens: {max_tokens}")
    print("=" * 60)

    for level in levels:
        wave_start = time.time()
        print(f"\n--- Wave: {level} concurrent ---")

        wave_results = await run_benchmark(url, level, requests_per_wave, max_tokens)

        successes = sum(1 for r in wave_results if r.get('status') == 200)
        failures  = len(wave_results) - successes
        sr = (successes / len(wave_results)) * 100 if wave_results else 0
        wave_elapsed = time.time() - wave_start

        ok_latencies = [r['latency_ms'] for r in wave_results if r.get('status') == 200]
        mean_lat = sum(ok_latencies) / len(ok_latencies) if ok_latencies else 0
        max_lat  = max(ok_latencies) if ok_latencies else 0

        wave_info = {
            'concurrency': level,
            'success_rate': sr,
            'successes': successes,
            'failures': failures,
            'mean_latency_ms': mean_lat,
            'max_latency_ms': max_lat,
            'wave_duration_s': wave_elapsed,
            'elapsed_since_start_s': time.time() - test_start
        }
        wave_summary.append(wave_info)

        # Tag each result with the concurrency level
        for r in wave_results:
            r['concurrency'] = level
            r['wave_elapsed_s'] = wave_elapsed
        all_results.extend(wave_results)

        print(f"   ✅ {successes}/{len(wave_results)} succeeded ({sr:.0f}%)  "
              f"Mean: {mean_lat:.0f}ms  Max: {max_lat:.0f}ms  "
              f"Wave time: {wave_elapsed:.1f}s")

        if sr < 50:
            print(f"\n💥 SYSTEM BROKE at concurrency={level}  (success rate {sr:.0f}%)")
            print(f"   Time to failure: {time.time() - test_start:.1f}s from test start")
            break

        # Brief cooldown between waves
        await asyncio.sleep(2)

    # Final summary
    total_elapsed = time.time() - test_start
    print("\n" + "=" * 60)
    print("📊 BREAKING-POINT SUMMARY")
    print(f"{'Concurrency':>12} | {'Success %':>10} | {'Mean (ms)':>10} | {'Max (ms)':>10} | {'Wave (s)':>9}")
    print("-" * 60)
    for w in wave_summary:
        print(f"{w['concurrency']:>12} | {w['success_rate']:>9.0f}% | "
              f"{w['mean_latency_ms']:>10.0f} | {w['max_latency_ms']:>10.0f} | "
              f"{w['wave_duration_s']:>8.1f}s")
    print(f"\nTotal test time: {total_elapsed:.1f}s")

    return all_results, wave_summary

def save_results(results, strategy, load_type):
    os.makedirs("group22_results", exist_ok=True)
    filename = f"group22_results/group22_results_{strategy}_{load_type}_{int(time.time())}.json"
    with open(filename, "w") as f:
        json.dump(results, f, indent=4)
    print(f"\n[SUCCESS] Results saved to {filename}")

def save_breaking_point(wave_summary, strategy):
    os.makedirs("group22_results", exist_ok=True)
    filename = f"group22_results/group22_breaking_point_{strategy}_{int(time.time())}.json"
    with open(filename, "w") as f:
        json.dump(wave_summary, f, indent=4)
    print(f"[SUCCESS] Breaking-point summary saved to {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080/infer")
    parser.add_argument("--strategy", default="hardware-aware")
    parser.add_argument("--load", choices=["normal", "stress", "breaking"], help="Load type to simulate")
    args = parser.parse_args()
    
    load_type = args.load
    if not load_type:
        print("\n--- Benchmark Mode Selection ---")
        print("1. Normal  (Low Load: 2 concurrent, 20 tokens, 20 total)")
        print("2. Stress  (High Load: 10 concurrent, 100 tokens, 50 total)")
        print("3. Breaking Point  (Ramp from 5→100 concurrent until failure)")
        choice = input("Select mode (1/2/3): ").strip()
        if choice == "1":
            load_type = "normal"
        elif choice == "2":
            load_type = "stress"
        else:
            load_type = "breaking"

    # Step 1: Wait until all pods respond with 200
    ready = asyncio.run(wait_for_ready(args.url))
    if not ready:
        print("Aborting: system not ready.")
        sys.exit(1)

    # Step 2: Warm up model caches
    asyncio.run(warm_up(args.url))

    # Step 3: Cooldown to let telemetry stabilize
    cooldown(5)

    # Step 4: Run the selected benchmark
    print("=" * 50)

    if load_type == "breaking":
        results, wave_summary = asyncio.run(run_breaking_point(args.url))
        save_results(results, args.strategy, "breaking")
        save_breaking_point(wave_summary, args.strategy)
    else:
        if load_type == "normal":
            concurrent, total, tokens = 2, 20, 20
        else:
            concurrent, total, tokens = 10, 50, 100
        results = asyncio.run(run_benchmark(args.url, concurrent, total, tokens))
        save_results(results, args.strategy, load_type)
