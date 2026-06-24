ARG BASE_IMAGE=nvidia/cuda:12.5.1-runtime-ubuntu24.04
FROM ${BASE_IMAGE} AS base

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_PREFER_BINARY=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    python3.12 python3.12-venv python3-pip \
    git wget curl libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    ffmpeg openssh-server \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel
RUN pip install comfy-cli
RUN /usr/bin/yes | comfy --workspace /comfyui install --nvidia
RUN pip install runpod requests websocket-client
RUN comfy --workspace /comfyui node install ComfyUI-Manager
COPY src/extra_model_paths.yaml /comfyui/

COPY handler.py /handler.py
COPY r2_model_loader.py /r2_model_loader.py
COPY start.sh /start.sh
COPY rp_handler.sh /rp_handler.sh
RUN chmod +x /start.sh /rp_handler.sh

COPY scripts/comfy-manager-set-mode.sh /usr/local/bin/comfy-manager-set-mode
RUN chmod +x /usr/local/bin/comfy-manager-set-mode

ENV COMFYUI_PATH=/comfyui COMFY_LOG_LEVEL=INFO PYTHONUNBUFFERED=1
ENV R2_ENDPOINT=https://38d27e0247b1a8b9aeb73d8ec4648262.r2.cloudflarestorage.com
ENV R2_BUCKET=comfyui-models MODEL_LIST=flux2-faceswap

CMD ["/rp_handler.sh"]
