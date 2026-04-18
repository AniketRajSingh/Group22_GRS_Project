from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from llama_cpp import Llama
import os
import asyncio
import time
import psutil
import concurrent.futures
import functools

app = FastAPI(title="CPU Inference Node")

# Configuration
MODEL_PATH = os.getenv("MODEL_PATH", "/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")
N_THREADS = int(os.getenv("N_THREADS", os.cpu_count() or 4))

def get_docker_cpu_limit():
    """Reads deep cgroups virtual boundaries to normalize cpu_percent accurately against docker limits."""
    try:
        # Cgroup v1
        if os.path.exists("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"):
            with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as f:
                quota = int(f.read().strip())
            with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as f:
                period = int(f.read().strip())
            if quota > 0 and period > 0:
                return float(quota) / float(period)
        
        # Cgroup v2
        if os.path.exists("/sys/fs/cgroup/cpu.max"):
            with open("/sys/fs/cgroup/cpu.max") as f:
                parts = f.read().strip().split()
                if len(parts) >= 2 and parts[0] != "max":
                    return float(parts[0]) / float(parts[1])
    except Exception:
        pass
    
    return float(os.cpu_count() or 1.0)

# Caches the actual container docker-compose limit instead of total host limit
CPU_LIMIT_BOUNDARY = get_docker_cpu_limit()

# Initialize LLM
# We use a global variable to keep the model in memory
llm = None
_model_lock = None

def get_model_lock():
    global _model_lock
    if _model_lock is None:
        _model_lock = asyncio.Lock()
    return _model_lock

# Initialize system process watcher early to track correct CPU %
_process = psutil.Process(os.getpid())
_process.cpu_percent() # discard first 0.0 reading

@app.on_event("startup")
async def startup_event():
    print("Inference Node starting up... (Model loading in background)", flush=True)
    # Load model in a thread to keep the event loop alive for stats and readiness
    asyncio.create_task(load_model_safe())

async def load_model_safe():
    global llm
    try:
        if not os.path.exists(MODEL_PATH):
            print(f"WARNING: Model file not found at {MODEL_PATH}. Entering MOCK MODE.", flush=True)
            return
            
        print(f"Loading model from {MODEL_PATH}...", flush=True)
        # Llama() is a heavy synchronous call. Must run in a thread.
        llm = await asyncio.to_thread(Llama, model_path=MODEL_PATH, n_threads=N_THREADS, verbose=False)
        print(f"Model loaded successfully on {os.getenv('NODE_ID', 'unknown')}", flush=True)
    except Exception as e:
        print(f"ERROR: Failed to load model: {e}", flush=True)

def get_llm():
    return llm

class InferenceRequest(BaseModel):
    prompt: str
    max_tokens: int = 128
    temperature: float = 0.7

@app.get("/health")
async def health():
    """Health check endpoint for the load balancer."""
    return {
        "status": "healthy",
        "node_id": os.getenv("NODE_ID", "unknown"),
        "threads": N_THREADS
    }

@app.get("/stats")
async def stats():
    """Returns real-time hardware stats normalized accurately against Docker cgroups limits."""
    # cpu_percent measures against fully available cores on the host. 
    # Normalizing against the actual specific CGroup bounds prevents deflated readings.
    cpu_usage = _process.cpu_percent()
    normalized_cpu = min(100.0, (cpu_usage / CPU_LIMIT_BOUNDARY)) if CPU_LIMIT_BOUNDARY > 0 else cpu_usage
    
    return {
        "cpu_percent": normalized_cpu,
        "memory_info": _process.memory_info()._asdict(),
        "load_avg": os.getloadavg(),
        "threads_configured": N_THREADS
    }

@app.post("/infer")
async def infer(request: InferenceRequest):
    """Executes LLM inference."""
    try:
        model = get_llm()
        start_time = time.time()
        
        if model:
            lock = get_model_lock()
            async with lock:
                output = await asyncio.to_thread(
                    model,
                    request.prompt,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature
                )
            text_result = output["choices"][0]["text"]
        else:
            # Improved Simulation: Proportional latency but non-blocking
            tokens = request.max_tokens
            latency_sim = (tokens / 20.0) # 0.05s per token
            await asyncio.sleep(latency_sim)
            
            def hard_burn():
                # A micro-burst to ensure the CPU scales up realistically during Mock profiles
                for i in range(10000): _ = i * i
            
            # Send the pure computational block to a threaded worker so FastAPI Event Loop continues receiving TCP polling safely!
            await asyncio.to_thread(hard_burn)
            text_result = f"MOCK RESPONSE from {os.getenv('NODE_ID', 'unknown')}: Model not found, but system is healthy!"
        
        end_time = time.time()
        
        return {
            "text": text_result,
            "latency_ms": (end_time - start_time) * 1000,
            "node_id": os.getenv("NODE_ID", "unknown"),
            "system": "mock" if not model else "llm"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
