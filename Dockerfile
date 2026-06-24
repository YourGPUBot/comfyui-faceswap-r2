# RunPod ComfyUI Worker — R2 Model Download Variant
# Portable: models live in Cloudflare R2, fetched at startup.
# Uses requests + raw S3 API — no boto3 dependency.
# Works on RunPod, Vast.ai, Lambda Labs, or anywhere.
#
# Self-contained build using CUDA 12.1 for max RunPod node compatibility.
# Upstream runpod/worker-comfyui images all use CUDA 12.6+ which requires
# newer host drivers than most RunPod serverless nodes provide.

ARG BASE_IMAGE=nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04
FROM ${BASE_IMAGE} AS base

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_PREFER_BINARY=1
ENV PYTHONUNBUFFERED=1
ENV CMAKE_BUILD_PARALLEL_LEVEL=8

# Install Python, git, and utility packages
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-venv \
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
    util-linux \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Install uv for fast Python package installs
RUN wget -qO- https://astral.sh/uv/install.sh | sh \
    && ln -sf /root/.local/bin/uv /usr/local/bin/uv \
    && ln -sf /root/.local/bin/uvx /usr/local/bin/uvx
ENV PATH="/root/.local/bin:${PATH}"

# Install ComfyUI via uv (faster)
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN uv pip install comfy-cli
RUN /usr/bin/yes | comfy --workspace /comfyui install --nvidia

# Install runpod and other Python deps
RUN uv pip install runpod requests websocket-client

# Install ComfyUI-Manager
RUN comfy --workspace /comfyui node install ComfyUI-Manager

WORKDIR /comfyui
COPY src/extra_model_paths.yaml ./
WORKDIR /

# Copy handler, scripts, and custom files
COPY handler.py /handler.py
COPY r2_model_loader.py /r2_model_loader.py
COPY start.sh /start.sh
COPY rp_handler.sh /rp_handler.sh
RUN chmod +x /start.sh /rp_handler.sh

# Install custom scripts
COPY scripts/comfy-manager-set-mode.sh /usr/local/bin/comfy-manager-set-mode
RUN chmod +x /usr/local/bin/comfy-manager-set-mode

# Environment
ENV COMFYUI_PATH=/comfyui
ENV COMFY_LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1
ENV R2_ENDPOINT=https://38d27e0247b1a8b9aeb73d8ec4648262.r2.cloudflarestorage.com
ENV R2_BUCKET=comfyui-models
ENV MODEL_LIST=flux2-faceswap

# RunPod expects this entry point for serverless
CMD ["/rp_handler.sh"]
