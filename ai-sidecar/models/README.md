# AI Models Directory

This directory contains the local LLM models used by HomeSight AI Sidecar.

## Model Files Not Included

Model files (`.gguf`) are **not committed to git** due to their large size (4-5GB).

## Download Required Model

HomeSight uses **Llama 3.2 8B Instruct** (Q4_K_M quantized) for local inference.

**Note**: Llama 3.2 8B models are gated by Meta and require HuggingFace authentication.

### Option 1: Automatic Download (with HuggingFace Token)

Set your HuggingFace token to enable automatic downloads:

```bash
export HF_TOKEN="your_huggingface_token_here"
./scripts/homesight.sh restart
```

Get your token from: <https://huggingface.co/settings/tokens>

### Option 2: Manual Download (Recommended)

```bash
cd ai-sidecar
source venv/bin/activate
pip install huggingface_hub

python3 << EOF
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='bartowski/Llama-3.2-8B-Instruct-GGUF',
    filename='Llama-3.2-8B-Instruct-Q4_K_M.gguf',
    local_dir='./models',
    local_dir_use_symlinks=False
)
EOF

# Rename to match config
mv models/Llama-3.2-8B-Instruct-Q4_K_M.gguf models/llama-3.2-8b-instruct.gguf
```

### Manual Download

Alternatively, download directly from HuggingFace:

**Llama 3.2 8B Instruct (Recommended - 4.9GB)**

- URL: <https://huggingface.co/bartowski/Llama-3.2-8B-Instruct-GGUF/resolve/main/Llama-3.2-8B-Instruct-Q4_K_M.gguf>
- Save as: `models/llama-3.2-8b-instruct.gguf`

**Alternative Models:**

For faster inference (less RAM):

- **Llama 3.2 3B**: <https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF>
- **Llama 3.2 1B**: <https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF>

For better quality (more RAM):

- **Llama 3.1 8B**: <https://huggingface.co/bartowski/Llama-3.1-8B-Instruct-GGUF>

## Model Requirements

| Model | Size | RAM Required | Speed (CPU) |
|-------|------|--------------|-------------|
| Llama 3.2 1B | 1.2GB | 4GB | ~30 tok/sec |
| Llama 3.2 3B | 2.0GB | 6GB | ~20 tok/sec |
| **Llama 3.2 8B** | **4.9GB** | **10GB** | **~10 tok/sec** |
| Llama 3.1 8B | 5.2GB | 10GB | ~10 tok/sec |

*Q4_K_M quantization provides good quality/speed balance*

## Configuration

Update `config.yaml` to use a different model:

```yaml
ai:
  llm:
    local:
      model_path: "./models/your-model-name.gguf"

      # Configure download source (HuggingFace)
      download_source:
        repo_id: "hugging-quants/Llama-3.2-3B-Instruct-Q4_K_M-GGUF"
        filename: "llama-3.2-3b-instruct-q4_k_m.gguf"
```

**Popular Model Sources:**

Llama 3.2 8B (Default):

```yaml
repo_id: "hugging-quants/Llama-3.2-8B-Instruct-Q4_K_M-GGUF"
filename: "llama-3.2-8b-instruct-q4_k_m.gguf"
```

Llama 3.2 3B (Faster):

```yaml
repo_id: "hugging-quants/Llama-3.2-3B-Instruct-Q4_K_M-GGUF"
filename: "llama-3.2-3b-instruct-q4_k_m.gguf"
```

Llama 3.2 1B (Smallest):

```yaml
repo_id: "hugging-quants/Llama-3.2-1B-Instruct-Q4_K_M-GGUF"
filename: "llama-3.2-1b-instruct-q4_k_m.gguf"
```

Phi-3.5 Mini (Microsoft - 3.8B):

```yaml
repo_id: "microsoft/Phi-3.5-mini-instruct-gguf"
filename: "Phi-3.5-mini-instruct-q4.gguf"
```

## GPU Acceleration

If you have an NVIDIA GPU:

1. Install CUDA-enabled llama-cpp-python:

   ```bash
   CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir
   ```

2. Update config.yaml:

   ```yaml
   ai:
     llm:
       local:
         n_gpu_layers: 35  # Offload all layers to GPU
   ```

## Verify Installation

```bash
# Check model file
ls -lh models/*.gguf

# Test inference
./scripts/homesight.sh restart
curl http://localhost:8001/health

# Should show: {"llm": {"loaded": true, "provider": "local"}}
```
