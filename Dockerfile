# RunPod ComfyUI Worker — R2 Model Download Variant
# Fork of upstream worker-comfyui with:
#  - CUDA 12.4.1 instead of 12.6.3 (RunPod nodes have older NVIDIA drivers)
#  - R2 model downloader instead of s3fs mount
#  - Simplified startup (no s3fs/fuse dependencies)
#
# Upstream base (CUDA 12.6.3) causes "cuda>=12.6" driver error on nodes.
# CUDA 12.4+ requires driver >= 525.60.13 (same as 12.1-12.4), widely
# available on all RunPod serverless node types.

ARG BASE_IMAGE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu24.04
FROM ${BASE_IMAGE} AS base

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_PREFER_BINARY=1
ENV PYTHONUNBUFFERED=1
ENV CMAKE_BUILD_PARALLEL_LEVEL=8

# Install Python, git, and utilities
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    git \
    wget \
    curl \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    openssh-server \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN wget -qO- https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv \
    && ln -s /root/.local/bin/uvx /usr/local/bin/uvx \
    && uv venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Install comfy-cli + ComfyUI
RUN uv pip install comfy-cli pip setuptools wheel
RUN /usr/bin/yes | comfy --workspace /comfyui install --nvidia

# Mirror ComfyUI deps into launch venv
RUN uv pip install -r /comfyui/requirements.txt \
    && for r in /comfyui/custom_nodes/*/requirements.txt; do \
        [ -f "$r" ] && uv pip install -r "$r"; done

# Install runpod SDK
RUN uv pip install runpod requests websocket-client

# Install ComfyUI-Manager
RUN comfy --workspace /comfyui node install ComfyUI-Manager

WORKDIR /comfyui
COPY src/extra_model_paths.yaml ./
WORKDIR /

# Copy handler and start scripts
COPY handler.py /handler.py
COPY r2_model_loader.py /r2_model_loader.py
COPY start.sh /start.sh
COPY rp_handler.sh /rp_handler.sh
RUN chmod +x /start.sh /rp_handler.sh

# Install custom scripts
COPY scripts/comfy-manager-set-mode.sh /usr/local/bin/comfy-manager-set-mode
RUN chmod +x /usr/local/bin/comfy-manager-set-mode

ENV COMFYUI_PATH=/comfyui
ENV COMFY_LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1
ENV R2_ENDPOINT=https://38d27e0247b1a8b9aeb73d8ec4648262.r2.cloudflarestorage.com
ENV R2_BUCKET=comfyui-models
ENV MODEL_LIST=flux2-faceswap

CMD ["/rp_handler.sh"]
