#!/usr/bin/env bash
#
# RunPod ComfyUI start.sh — R2 Model Download
# Downloads models from R2, then launches ComfyUI + RunPod handler.
#
set -o pipefail

# ---------------------------------------------------------------------------
# Step 1: Download models from R2 (small files first, 120s total cap)
# ---------------------------------------------------------------------------
if [ -n "$R2_ACCESS_KEY_ID" ] && [ -n "$R2_SECRET_ACCESS_KEY" ]; then
    echo "worker-comfyui: Downloading models from R2..."
    python /r2_model_loader.py
fi

# ---------------------------------------------------------------------------
# Step 2: Standard ComfyUI startup
# ---------------------------------------------------------------------------

# Use libtcmalloc for better memory management
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

# Ensure ComfyUI-Manager offline mode
comfy-manager-set-mode offline 2>/dev/null || true

echo "worker-comfyui: Starting ComfyUI"

: "${COMFY_LOG_LEVEL:=DEBUG}"
COMFY_PID_FILE="/tmp/comfyui.pid"

# Start ComfyUI in background, handler in foreground
python -u /comfyui/main.py --disable-auto-launch --disable-metadata \
    --verbose "${COMFY_LOG_LEVEL}" --log-stdout &
echo $! > "$COMFY_PID_FILE"

echo "worker-comfyui: Starting RunPod Handler"
exec python -u /handler.py
