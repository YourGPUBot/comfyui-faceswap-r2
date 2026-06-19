# RunPod ComfyUI Worker — R2 Model Download Variant
# Portable: models live in Cloudflare R2, fetched at startup.
# Works on RunPod, Vast.ai, Lambda Labs, or anywhere.
#
# Base: Official worker-comfyui 5.8.6 with ComfyUI, handler, FlashBoot support
FROM runpod/worker-comfyui:5.8.6-base

# Install boto3 for S3-compatible R2 access
RUN pip install boto3

# Copy custom R2 model downloader
COPY src/r2_model_loader.py /r2_model_loader.py

# Override start.sh to download models from R2 before launching ComfyUI
COPY src/start-r2.sh /start.sh
RUN chmod +x /start.sh

# Default R2 environment (overridable at endpoint creation)
ENV R2_ENDPOINT=https://38d27e0247b1a8b9aeb73d8ec4648262.r2.cloudflarestorage.com
ENV R2_BUCKET=comfyui-models
ENV MODEL_LIST=flux2-faceswap

# Default entry point — start.sh handles model download + ComfyUI + RunPod handler
CMD ["/start.sh"]
