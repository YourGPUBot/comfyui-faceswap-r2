#!/usr/bin/env bash
# RunPod ComfyUI start.sh — minimal R2 model download, then standard flow

# Download models in background (never blocks startup)
if [ -n "$R2_ACCESS_KEY_ID" ] && [ -n "$R2_SECRET_ACCESS_KEY" ]; then
    echo "worker-comfyui: Spawning R2 model download in background..."
    nohup python /r2_model_loader.py > /tmp/r2-download.log 2>&1 &
    echo "worker-comfyui: Background PID $! — continuing to ComfyUI immediately"
fi

# Use libtcmalloc
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

comfy-manager-set-mode offline 2>/dev/null || true

echo "worker-comfyui: Starting ComfyUI"
: "${COMFY_LOG_LEVEL:=DEBUG}"
COMFY_PID_FILE="/tmp/comfyui.pid"

# Start ComfyUI in background
python -u /comfyui/main.py --disable-auto-launch --disable-metadata \
    --verbose "${COMFY_LOG_LEVEL}" --log-stdout &
echo $! > "$COMFY_PID_FILE"

# Start RunPod handler (foreground — keeps container alive)
echo "worker-comfyui: Starting RunPod Handler"
exec python -u /handler.py
