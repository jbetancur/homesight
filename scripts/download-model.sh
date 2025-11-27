#!/bin/bash
# Download LLM models to /home/homesight/models
# Supports Llama 3.2 (3B/8B) and DeepSeek models

set -e

MODEL_DIR="/home/homesight/models"

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}LLM Model Downloader${NC}"
echo "===================="
echo ""

# Create directory if it doesn't exist
if [ ! -d "$MODEL_DIR" ]; then
    echo "Creating models directory: $MODEL_DIR"
    mkdir -p "$MODEL_DIR"
fi

# Show menu
echo "Select model to download:"
echo ""
echo "  1) Llama 3.2 3B (Q4_K_M, ~2GB) - No auth required"
echo "  2) Llama 3.1 8B (Q4_K_M, ~4.9GB) - No auth required"
echo "  3) DeepSeek R1 Distill Llama 8B (Q4_K_M, ~4.9GB) - Requires HF token"
echo "  4) Custom model (enter repo ID manually)"
echo ""
read -p "Enter choice [1-4]: " choice

case $choice in
    1)
        REPO_ID="bartowski/Llama-3.2-3B-Instruct-GGUF"
        FILENAME="Llama-3.2-3B-Instruct-Q4_K_M.gguf"
        OUTPUT_NAME="llama-3.2-3b-instruct.gguf"
        REQUIRES_TOKEN=false
        ;;
    2)
        REPO_ID="bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"
        FILENAME="Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
        OUTPUT_NAME="llama-3.1-8b-instruct.gguf"
        REQUIRES_TOKEN=false
        ;;
    3)
        REPO_ID="bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF"
        FILENAME="DeepSeek-R1-Distill-Llama-8B-Q4_K_M.gguf"
        OUTPUT_NAME="deepseek-r1-distill-llama-8b.gguf"
        REQUIRES_TOKEN=true
        ;;
    4)
        read -p "Enter HuggingFace repo ID (e.g. author/model-name): " REPO_ID
        read -p "Enter filename: " FILENAME
        read -p "Enter output name: " OUTPUT_NAME
        read -p "Requires HF token? (y/n): " token_required
        if [ "$token_required" = "y" ]; then
            REQUIRES_TOKEN=true
        else
            REQUIRES_TOKEN=false
        fi
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

MODEL_FILE="$MODEL_DIR/$OUTPUT_NAME"

echo ""
echo -e "${YELLOW}Model Configuration:${NC}"
echo "  Repository: $REPO_ID"
echo "  File: $FILENAME"
echo "  Destination: $MODEL_FILE"
echo ""

# Check if model already exists
if [ -f "$MODEL_FILE" ]; then
    SIZE=$(du -h "$MODEL_FILE" | cut -f1)
    echo -e "${GREEN}✓ Model already exists: $MODEL_FILE ($SIZE)${NC}"
    echo ""
    read -p "Re-download? (y/n): " redownload
    if [ "$redownload" != "y" ]; then
        exit 0
    fi
    rm "$MODEL_FILE"
fi

# Check for HF token if required
if [ "$REQUIRES_TOKEN" = true ]; then
    if [ -z "$HF_TOKEN" ]; then
        echo -e "${YELLOW}This model requires HuggingFace authentication.${NC}"
        echo ""
        echo "To get a token:"
        echo "  1. Go to https://huggingface.co/settings/tokens"
        echo "  2. Create a new token (read access is sufficient)"
        echo "  3. Accept the model license on the model page"
        echo ""
        read -p "Enter your HuggingFace token: " HF_TOKEN
        export HF_TOKEN
    fi
fi

# Install huggingface-hub
echo "Installing huggingface-hub..."
pip3 install --user -q huggingface-hub 2>/dev/null || \
pip3 install --break-system-packages -q huggingface-hub

# Download model using Python
echo ""
echo -e "${BLUE}Downloading model...${NC}"
echo "This may take several minutes depending on model size and connection speed."
echo ""

if [ "$REQUIRES_TOKEN" = true ]; then
    python3 << PYTHON_SCRIPT
import os
os.environ['HF_TOKEN'] = '$HF_TOKEN'
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='$REPO_ID',
    filename='$FILENAME',
    local_dir='$MODEL_DIR',
    local_dir_use_symlinks=False,
    token='$HF_TOKEN'
)
PYTHON_SCRIPT
else
    python3 << PYTHON_SCRIPT
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='$REPO_ID',
    filename='$FILENAME',
    local_dir='$MODEL_DIR',
    local_dir_use_symlinks=False
)
PYTHON_SCRIPT
fi

# Rename to expected filename
if [ -f "$MODEL_DIR/$FILENAME" ] && [ "$FILENAME" != "$OUTPUT_NAME" ]; then
    mv "$MODEL_DIR/$FILENAME" "$MODEL_FILE"
fi

echo ""
echo -e "${GREEN}✓ Model downloaded successfully!${NC}"
echo "  Location: $MODEL_FILE"
SIZE=$(du -h "$MODEL_FILE" | cut -f1)
echo "  Size: $SIZE"
echo ""
echo -e "${YELLOW}To use this model:${NC}"
echo "  1. Update config.yaml:"
echo "     model_path: \"$MODEL_FILE\""
echo "  2. Restart the AI sidecar:"
echo "     docker-compose restart ai-sidecar"
echo ""
