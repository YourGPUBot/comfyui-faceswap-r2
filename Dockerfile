# RunPod ComfyUI Worker — R2 Model Download Variant
# Portable: models live in Cloudflare R2, fetched at startup.
# Uses requests + raw S3 API — no boto3 dependency.
# Works on RunPod, Vast.ai, Lambda Labs, or anywhere.
#
# Base: Official worker-comfyui 5.8.6 with ComfyUI, handler, FlashBoot support
FROM runpod/worker-comfyui:5.6.0-base

# Upgrade runpod SDK — the base image pins runpod~=1.7.12 which has known
# serverless worker routing bugs (jobs stay IN_QUEUE despite idle workers).
# Latest runpod SDK (>1.9.0) includes critical fixes for job dispatch.
RUN uv pip install "runpod>=1.9.1"

# Copy custom R2 model downloader (uses requests — already in base image)
COPY r2_model_loader.py /r2_model_loader.py

# Override start.sh — adds model download, GPU check, SSH, same handler
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Default R2 environment (overridable at endpoint creation)
ENV R2_ENDPOINT=https://38d27e0247b1a8b9aeb73d8ec4648262.r2.cloudflarestorage.com
ENV R2_BUCKET=comfyui-models
ENV MODEL_LIST=flux2-faceswap

CMD ["/start.sh"]
