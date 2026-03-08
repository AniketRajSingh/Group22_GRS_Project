from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from llama_cpp import Llama
import os
import time
import psutil

app = FastAPI(title="CPU Inference Node")

# Configuration
MODEL_PATH = os.getenv("MODEL_PATH", "/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")
N_THREADS = int(os.getenv("N_THREADS", os.cpu_count() or 4))

# Initialize LLM
# We use a global variable to keep the model in memory
llm = None

def get_llm():
    global llm
    if llm is None:
        if not os.path.exists(MODEL_PATH):
            raise RuntimeError(f"Model file not found at {MODEL_PATH}")
        llm = Llama(model_path=MODEL_PATH, n_threads=N_THREADS, verbose=False)
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
    """Returns real-time hardware stats from the container's perspective."""
    process = psutil.Process(os.getpid())
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_info": process.memory_info()._asdict(),
        "load_avg": os.getloadavg(),
        "threads_configured": N_THREADS
    }

@app.post("/infer")
async def infer(request: InferenceRequest):
    """Executes LLM inference."""
    try:
        model = get_llm()
        start_time = time.time()
        
        # Emulate CPU Stress - proportional to tokens
        # We perform some redundant math to spike CPU percent
        load_factor = request.max_tokens * 100000 
        for _ in range(load_factor):
            _ = 123.456 * 789.012
            
        output = model(
            request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature
        )
        
        end_time = time.time()
        
        return {
            "text": output["choices"][0]["text"],
            "latency_ms": (end_time - start_time) * 1000,
            "node_id": os.getenv("NODE_ID", "unknown")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
