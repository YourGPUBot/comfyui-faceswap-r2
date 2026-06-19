# ComfyUI Worker with R2 Model Download
# Downloads models from Cloudflare R2 at startup.
# Small models (<500MB) download first, big models continue in background via nohup.
# Portable to any GPU provider — uses S3-compatible API.

import os
import boto3
import sys
import json

R2_ENDPOINT = os.getenv("R2_ENDPOINT", "https://38d27e0247b1a8b9aeb73d8ec4648262.r2.cloudflarestorage.com")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET", "comfyui-models")
MODEL_LIST = os.getenv("MODEL_LIST", "")

SMALL_THRESHOLD = 500 * 1024 * 1024  # 500MB

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


def download(s3, r2_key, local_path, label=""):
    """Download one model. Uses temp file + atomic rename to prevent corruption."""
    full_path = local_path
    if os.path.exists(full_path):
        print(f"  ✓ [{label}] {os.path.getsize(full_path)/1024/1024:.0f} MB — cached")
        return True, True  # (success, was_cached)
    try:
        size = s3.head_object(Bucket=R2_BUCKET, Key=r2_key)['ContentLength']
        print(f"  📥 [{label}] {r2_key} ({size/1024/1024:.0f} MB)")
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        tmp = full_path + ".download"
        s3.download_file(R2_BUCKET, r2_key, tmp)
        os.rename(tmp, full_path)
        print(f"    ✅ {os.path.getsize(full_path)/1024/1024:.0f} MB")
        return True, False
    except Exception as e:
        print(f"    ❌ {e}")
        tmp = local_path + ".download"
        if os.path.exists(tmp):
            os.unlink(tmp)
        return False, False


if __name__ == "__main__":
    if not R2_ACCESS_KEY or not R2_SECRET_KEY:
        print("R2: no credentials, skipping")
        sys.exit(0)

    models = parse_model_list()
    if not models:
        print("R2: no models in MODEL_LIST")
        sys.exit(0)

    model_set = os.getenv("MODEL_LIST", "flux2-faceswap")
    print(f"📦 Model set: {model_set} ({len(models)} models)")
    s3 = get_s3()

    # 1) Small models first (so ComfyUI has basic models quickly)
    # 2) Big models after
    for r2_key, local_path in models:
        full_path = local_path
        if os.path.exists(full_path):
            continue  # already handled below

        try:
            size = s3.head_object(Bucket=R2_BUCKET, Key=r2_key)['ContentLength']
        except:
            size = 999 * 1024 * 1024 * 1024  # assume huge

    # Download small models synchronously
    small_success = 0
    big_success = 0
    for r2_key, local_path in models:
        full_path = local_path
        try:
            if os.path.exists(full_path):
                is_big = os.path.getsize(full_path) >= SMALL_THRESHOLD
                label = "big" if is_big else "small"
                print(f"  ✓ [{label}] {os.path.getsize(full_path)/1024/1024:.0f} MB — cached")
                continue
            size = s3.head_object(Bucket=R2_BUCKET, Key=r2_key)['ContentLength']
            is_big = size >= SMALL_THRESHOLD
            label = "big" if is_big else "small"
            ok, _ = download(s3, r2_key, local_path, label)
            if ok and is_big:
                big_success += 1
            elif ok:
                small_success += 1
        except Exception as e:
            print(f"    ⚠️ {e}")

    print(f"\n✅ Done: {small_success} small + {big_success} big models")
