# ComfyUI Worker with S3/R2 Model Loading
# Download models from R2/S3 on cold start based on environment configuration

import os
import boto3
import sys
import json

# R2/S3 Config from env
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "https://38d27e0247b1a8b9aeb73d8ec4648262.r2.cloudflarestorage.com")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET", "comfyui-models")

# Model configuration via env var
# Format: JSON array of {r2_key, local_path} objects
# Or simple format: "r2_path:local_path,r2_path2:local_path2"
MODEL_LIST = os.getenv("MODEL_LIST", "")

# Predefined model sets for common workflows
# Base path for models - use volume if mounted, otherwise default to /comfyui
MODEL_BASE_PATH = os.getenv("MODEL_BASE_PATH", "/runpod-volume" if os.path.exists("/runpod-volume") else "/comfyui")

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
    """Parse MODEL_LIST env var into list of (r2_key, local_path) tuples"""
    if not MODEL_LIST:
        # Default to flux2-faceswap if nothing specified
        return MODEL_SETS.get("flux2-faceswap", [])
    
    # Check if it's a predefined set name
    if MODEL_LIST in MODEL_SETS:
        return MODEL_SETS[MODEL_LIST]
    
    # Try JSON format
    try:
        models = json.loads(MODEL_LIST)
        return [(m["r2_key"], m["local_path"]) for m in models]
    except (json.JSONDecodeError, KeyError):
        pass
    
    # Try simple format: "r2/path:local/path,r2/path2:local/path2"
    models = []
    for item in MODEL_LIST.split(","):
        if ":" in item:
            r2_key, local_path = item.split(":", 1)
            models.append((r2_key.strip(), local_path.strip()))
    return models

def download_models():
    """Download required models from R2 to local ComfyUI paths"""
    if not R2_ACCESS_KEY or not R2_SECRET_KEY:
        print("⚠️  R2 credentials not set, skipping model download")
        return
    
    models = parse_model_list()
    if not models:
        print("⚠️  No models configured in MODEL_LIST")
        return
    
    print(f"📦 Model set: {os.getenv('MODEL_LIST', 'flux2-faceswap (default)')}")
    print(f"📦 Downloading {len(models)} models from R2...")
    
    s3 = boto3.client('s3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name='auto'
    )
    
    downloaded = 0
    skipped = 0
    failed = 0
    
    for r2_key, local_path in models:
        # local_path already includes MODEL_BASE_PATH prefix
        full_path = local_path
        
        if os.path.exists(full_path):
            size_mb = os.path.getsize(full_path) / 1024 / 1024
            print(f"✓ {local_path} already exists ({size_mb:.0f} MB)")
            skipped += 1
            continue
        
        print(f"📥 {r2_key} -> {local_path}...")
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        try:
            s3.download_file(R2_BUCKET, r2_key, full_path)
            size_mb = os.path.getsize(full_path) / 1024 / 1024
            print(f"  ✅ Downloaded ({size_mb:.0f} MB)")
            downloaded += 1
        except Exception as e:
            print(f"  ❌ Error: {e}", file=sys.stderr)
            failed += 1
            # Continue with other models instead of crashing
    
    print(f"\n✅ Complete: {downloaded} downloaded, {skipped} cached, {failed} failed")
    
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    download_models()
