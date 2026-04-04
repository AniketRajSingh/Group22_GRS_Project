import base64
import requests  # type: ignore
import json
import os
import time

# Configuration for Ollama
OLLAMA_IP = "192.168.3.173:11434"
MODEL = "qwen3.5:0.8b"

ANALYSIS_PROMPT = """
Analyze this graph using the Unified Cluster Intelligence Report (UCIR) Protocol.
Follow this EXACT 6-point format for the output:
1. 🔍 Metric Identity: 
2. 📶 Behavioral Trend: 
3. ⚖️ Strategy Delta: 
4. ⚠️ Anomaly Detection: 
5. 💡 Efficiency Score: 
6. 🛠️ Strategic Action: 
Use professional technical language. Keep each point concise.
"""

MAX_RETRIES = 3
RETRY_DELAY_S = 15
OLLAMA_TIMEOUT_S = 180

def get_graph_description(image_path):
    """Encodes image and fetches UCIR analysis from Ollama, with automatic retry."""
    if not os.path.exists(image_path):
        return f"Error: Image `{os.path.basename(image_path)}` not found. Generate plots first."

    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        return f"Error reading image file: {str(e)}"

    payload = {
        "model": MODEL,
        "prompt": ANALYSIS_PROMPT,
        "stream": False,
        "images": [base64_image]
    }

    last_error = "Unknown error"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  [Ollama] Attempt {attempt}/{MAX_RETRIES}: {os.path.basename(image_path)}")
            response = requests.post(
                f"http://{OLLAMA_IP}/api/generate",
                json=payload,
                timeout=OLLAMA_TIMEOUT_S
            )
            response.raise_for_status()
            result = response.json()
            text = result.get("response", "").strip()
            if text:
                return text
            last_error = "Empty response from Ollama."
        except requests.exceptions.Timeout:
            last_error = f"Timed out after {OLLAMA_TIMEOUT_S}s (attempt {attempt}/{MAX_RETRIES})."
            print(f"  [Ollama] ⚠ Timeout on attempt {attempt}. {'Retrying in {}s...'.format(RETRY_DELAY_S) if attempt < MAX_RETRIES else 'All retries exhausted.'}")
        except Exception as e:
            last_error = str(e)
            print(f"  [Ollama] ⚠ Error on attempt {attempt}: {e}")

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_S)

    return f"⚠️ Analysis unavailable after {MAX_RETRIES} attempts. Last error: {last_error}"

def analyze_all_plots():
    """Generates analysis for all static plots and yields them for the dashboard."""
    plot_dir = os.path.join(os.path.dirname(__file__), "group22_plots/static")
    if not os.path.exists(plot_dir):
        yield "Error", "⚠️ No plots found. Run a benchmark first."
        return

    plots = sorted([f for f in os.listdir(plot_dir) if f.endswith('.png')])
    if not plots:
        yield "Error", "⚠️ No plots found in directory."
        return

    # Intro
    yield "Initializing...", "## 🗂️ Unified Cluster Intelligence Report (UCIR)\n\nAnalysis generated from recent benchmark data."

    synthesis_notes = []
    
    for filename in plots:
        img_path = os.path.join(plot_dir, filename)
        
        # Format the name for display
        clean_name = filename.replace('group22_', '').replace('.png', '').replace('_', ' ').title()
        
        yield clean_name, "" # Update progress tracker
        
        analysis = get_graph_description(img_path)
        synthesis_notes.append(f"{clean_name}: {analysis[:100]}...") # Keep summary short
        
        # The magical format expected by the frontend parser:
        # ##PLOT_SEPARATOR## [filename] ##PLOT_SEPARATOR## [analysis]
        formatted_chunk = f"## {clean_name}\n\n##PLOT_SEPARATOR##\n{filename}\n##PLOT_SEPARATOR##\n{analysis}\n##PLOT_SEPARATOR##\n"

        
        yield clean_name, formatted_chunk

    # Final Synthesis
    yield "Final Synthesis", ""
    
    synth_prompt = (
        "Based on these brief notes from recent graphs, write a 3-paragraph executive summary of the cluster's health and load balancing efficiency:\n"
        + "\n".join(synthesis_notes)
    )
    
    payload = {
        "model": MODEL,
        "prompt": synth_prompt,
        "stream": False
    }
    
    try:
        response = requests.post(f"http://{OLLAMA_IP}/api/generate", json=payload, timeout=60)
        result = response.json()
        synthesis = result.get("response", "Could not generate synthesis.")
    except Exception as e:
        synthesis = f"Synthesis failed: {e}"

    yield "Complete", f"## 🏁 Executive Synthesis\n\n{synthesis}"

if __name__ == "__main__":

    # Test script
    test_img = "/home/iiitd/Group22_GRS_Project-2/group22_plots/dynamic/group22_latency_comparison.png"
    print(get_graph_description(test_img))
