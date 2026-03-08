import httpx
import asyncio
import threading
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Telemetry")

class TelemetryCollector:
    def __init__(self, node_list, polling_interval=1.0):
        """
        node_list: List of strings in format "host:port"
        """
        self.nodes = node_list
        self.polling_interval = polling_interval
        self.stats = {node: {} for node in node_list}
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)

    def start(self):
        logger.info(f"Starting universal telemetry collector for nodes: {self.nodes}")
        self._thread.start()

    def stop(self):
        self.running = False
        self._thread.join()

    def _run_loop(self):
        # We need an event loop for httpx.AsyncClient
        asyncio.run(self._collect_all())

    async def _collect_all(self):
        async with httpx.AsyncClient(timeout=2.0) as client:
            while self.running:
                tasks = [self._fetch_node_stats(client, node) for node in self.nodes]
                await asyncio.gather(*tasks)
                await asyncio.sleep(self.polling_interval)

    async def _fetch_node_stats(self, client, node):
        url = f"http://{node}/stats"
        try:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                # Internal node health + psutil data
                self.stats[node] = {
                    "cpu_percent": data.get("cpu_percent", 100),
                    "memory_mb": data.get("memory_info", {}).get("rss", 0) / (1024 * 1024),
                    "load_avg": data.get("load_avg", [0, 0, 0]),
                    "healthy": True,
                    "timestamp": time.time()
                }
            else:
                self.stats[node]["healthy"] = False
        except Exception as e:
            # logger.warning(f"Node {node} unreachable: {e}")
            self.stats[node] = {"healthy": False, "cpu_percent": 100}

    def get_node_stats(self, node):
        return self.stats.get(node, {"healthy": False, "cpu_percent": 100})

if __name__ == "__main__":
    # Test
    collector = TelemetryCollector(["localhost:8000"])
    collector.start()
    try:
        while True:
            print(f"Stats: {collector.stats}")
            time.sleep(2)
    except KeyboardInterrupt:
        collector.stop()
