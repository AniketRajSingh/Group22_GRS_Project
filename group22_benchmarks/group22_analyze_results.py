import json
import statistics
import glob
import os
import argparse

def analyze_json_results(filepath):
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return

    with open(filepath, "r") as f:
        data = json.load(f)

    # Filter out errors
    valid_results = [r for r in data if r.get("status") == 200]
    errors = [r for r in data if r.get("status") != 200]

    if not valid_results:
        print(f"No valid results found in {filepath}.")
        return

    latencies = [r["latency_ms"] for r in valid_results]
    
    # Node distribution
    node_counts = {}
    for r in valid_results:
        node = r.get("node", "unknown")
        node_counts[node] = node_counts.get(node, 0) + 1
#metrics for comparison
    stats = {
        "total_requests": len(data),
        "success_rate": (len(valid_results) / len(data)) * 100,
        "mean_latency": statistics.mean(latencies),
        "median_latency": statistics.median(latencies),
        "p95_latency": sorted(latencies)[int(len(latencies) * 0.95)],
        "p99_latency": sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) >= 100 else "N/A",
        "min_latency": min(latencies),
        "max_latency": max(latencies),
        "node_distribution": node_counts
    }

    print(f"\n--- Analysis for {os.path.basename(filepath)} ---")
    print(f"Strategy Identification: {filepath.split('_')[1]}")
    print(f"Success Rate: {stats['success_rate']:.2f}%")
    print(f"Average Latency: {stats['mean_latency']:.2f} ms")
    print(f"p95 Latency: {stats['p95_latency']:.2f} ms")
    print(f"Max Latency: {stats['max_latency']:.2f} ms")
    print("Node Distribution:")
    for node, count in node_counts.items():
        print(f"  - {node}: {count} requests ({(count/len(valid_results))*100:.1f}%)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Specific JSON file to analyze")
    args = parser.parse_args()

    if args.file:
        analyze_json_results(args.file)
    else:
        # Analyze all results in the group22_results directory
        files = glob.glob("group22_results/group22_results_*.json")
        for f in files:
            analyze_json_results(f)
