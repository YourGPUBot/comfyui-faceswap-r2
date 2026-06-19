# ComfyUI Worker with R2 Model Download
# Portable: same S3-compatible credentials work on RunPod, Vast.ai, Lambda Labs.
# Small models download synchronously (fast worker startup).
# Big models (Flux checkpoint ~17GB, text encoder ~8GB) download in background.

import os
import boto3
import sys
import json
from threading import Thread

# R2/S3 Config from env
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "https://38d27e0247b1a8b9aeb73d8ec4648262.r2.cloudflarestorage.com")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET", "comfyui-models")
MODEL_LIST = os.getenv("MODEL_LIST", "")

# Models under this size download synchronously
SMALL_THRESHOLD = 500 * 1024 * 1024  # 500MB

# Where models live inside the container
MODEL_BASE_PATH = os.getenv("MODEL_BASE_PATH",
    "/runpod-volume" if os.path.exists("/runpod-volume") else "/comfyui")

MODEL_SETS = {
    "flux2-faceswap": [
        ("unet/flux-2-klein-9b.safetensors", f"{MODEL_BASE_PATH}/models/diffusion_models/flux-2-klein-9b.safetensors"),
        ("flux2-faceswap/vae/flux2-vae.safetensors", f"{MODEL_BASE_PATH}/models/vae/flux2-vae.safetensors"),
        ("text_encoders/qwen_3_8b_fp8mixed.safetensors", f"{MODEL_BASE_PATH}/models/text_encoders/qwen_3_8b_fp8mixed.safetensors"),
        ("loras/bfs_head_v1_flux-klein_9b_step3750_rank64.safetensors", f"{MODEL_BASE_PATH}/models/loras/bfs_head_v1_flux-klein_9b_step3750_rank64.safetensors"),
    ],
    "sdxl": [
        ("checkpoints/sd_xl_base_1.0.safetensors", f"{MODEL_BASE_PATH}/models/checkpoints/sd_xl_base_1.0.safetensors"),
        ("vae/sdxl_vae.safetensors", f"{MODEL_BASE_PATH}/models/vae/sdxl_vae.safetensors"),
    ],
    "flux1-schnell": [
        ("unet/flux1-schnell.safetensors", f"{MODEL_BASE_PATH}/models/unet/flux1-schnell.safetensors"),
        ("clip/clip_l.safetensors", f"{MODEL_BASE_PATH}/models/clip/clip_l.safetensors"),
        ("clip/t5xxl_fp8_e4m3fn.safetensors", f"{MODEL_BASE_PATH}/models/clip/t5xxl_fp8_e4m3fn.safetensors"),
        ("vae/ae.safetensors", f"{MODEL_BASE_PATH}/models/vae/ae.safetensors"),
    ],
}


def parse_model_list():
    if not MODEL_LIST:
        return MODEL_SETS.get("flux2-faceswap", [])
    if MODEL_LIST in MODEL_SETS:
        return MODEL_SETS[MODEL_LIST]
    try:
        models = json.loads(MODEL_LIST)
        return [(m["r2_key"], m["local_path"]) for m in models]
    except (json.JSONDecodeError, KeyError):
        pass
    models = []
    for item in MODEL_LIST.split(","):
        if ":" in item:
            r2_key, local_path = item.split(":", 1)
            models.append((r2_key.strip(), local_path.strip()))
    return models


def get_s3():
    return boto3.client('s3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name='auto')


def download_one(s3, r2_key, local_path):
    full_path = local_path
    if os.path.exists(full_path):
        size_mb = os.path.getsize(full_path) / 1024 / 1024
        print(f"  ✓ {local_path} ({size_mb:.0f} MB) — cached")
        return True
    try:
        size = s3.head_object(Bucket=R2_BUCKET, Key=r2_key)['ContentLength']
        print(f"  📥 {r2_key} ({size/1024/1024:.0f} MB)")
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        s3.download_file(R2_BUCKET, r2_key, full_path)
        print(f"    ✅ Downloaded ({os.path.getsize(full_path)/1024/1024:.0f} MB)")
        return True
    except Exception as e:
        print(f"    ❌ {e}")
        return False


if __name__ == "__main__":
    if not R2_ACCESS_KEY or not R2_SECRET_KEY:
        print("R2 credentials not set — skipping model download")
        sys.exit(0)

    models = parse_model_list()
    if not models:
        print("No models configured in MODEL_LIST")
        sys.exit(0)

    print(f"📦 Model set: {os.getenv('MODEL_LIST', 'flux2-faceswap (default)')} ({len(models)} models)")
    s3 = get_s3()

    # Phase 1: Download small models synchronously
    # Phase 2: Big models go to background thread
    big_models = []
    for r2_key, local_path in models:
        full_path = local_path
        if os.path.exists(full_path):
            try:
                size = os.path.getsize(full_path)
                label = "small" if size < SMALL_THRESHOLD else "big"
                print(f"  ✓ [{label}] {local_path} ({size/1024/1024:.0f} MB) — cached")
            except:
                pass
            continue
        try:
            size = s3.head_object(Bucket=R2_BUCKET, Key=r2_key)['ContentLength']
            if size < SMALL_THRESHOLD:
                download_one(s3, r2_key, local_path)
            else:
                big_models.append((r2_key, local_path))
        except Exception:
            big_models.append((r2_key, local_path))

    if big_models:
        print(f"\n📦 Large models ({len(big_models)} remaining — downloading in background)...")
        for r2_key, local_path in big_models:
            try:
                size = s3.head_object(Bucket=R2_BUCKET, Key=r2_key)['ContentLength']
                print(f"  ⏳ {r2_key} ({size/1024/1024:.0f} MB) — will start after worker boots")
            except:
                print(f"  ⏳ {r2_key}")
        t = Thread(target=lambda: [download_one(get_s3(), k, p) for k, p in big_models],
                   daemon=True)
        t.start()
        print("  Worker startup continues — models stream in as background download finishes")

    print("\n✅ Model load phase complete")
