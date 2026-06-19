# ComfyUI R2 Model Downloader
# Uses only Python standard library — no pip dependencies needed.
# Downloads models from Cloudflare R2 (S3-compatible) at worker startup.
# Atomic rename to prevent ComfyUI reading partial files.

import os
import sys
import json
import hashlib
import hmac
import urllib.request
import time
import xml.etree.ElementTree as ET

R2_ENDPOINT = os.getenv("R2_ENDPOINT", "https://38d27e0247b1a8b9aeb73d8ec4648262.r2.cloudflarestorage.com")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET", "comfyui-models")
MODEL_LIST = os.getenv("MODEL_LIST", "")

MODEL_BASE_PATH = os.getenv("MODEL_BASE_PATH",
    "/runpod-volume" if os.path.exists("/runpod-volume") else "/comfyui")

SMALL_THRESHOLD = 500 * 1024 * 1024

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


def sign_v4(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def get_s3_url(r2_key):
    """Build S3-compatible URL for the object."""
    endpoint = R2_ENDPOINT.rstrip("/")
    return f"{endpoint}/{R2_BUCKET}/{r2_key}"


def get_s3_head(r2_key):
    """Get object metadata via S3 HEAD request with AWS Signature V4."""
    endpoint = R2_ENDPOINT.rstrip("/")
    host = endpoint.replace("https://", "").replace("http://", "")
    path = f"/{R2_BUCKET}/{r2_key}"
    url = f"{endpoint}{path}"

    # AWS Signature V4
    service = "s3"
    region = "auto"
    now = time.gmtime()
    amz_date = time.strftime("%Y%m%dT%H%M%SZ", now)
    date_stamp = time.strftime("%Y%m%d", now)

    # Create canonical request
    method = "HEAD"
    canonical_uri = path
    canonical_querystring = ""
    canonical_headers = f"host:{host}\nx-amz-content-sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\nx-amz-date:{amz_date}\n"
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    payload_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    # Create string to sign
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    cr_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{cr_hash}"

    # Calculate signature
    k_date = sign_v4(R2_SECRET_KEY.encode("utf-8"), date_stamp)
    k_region = sign_v4(k_date, region)
    k_service = sign_v4(k_region, service)
    k_signing = sign_v4(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = f"{algorithm} Credential={R2_ACCESS_KEY}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

    req = urllib.request.Request(url, method="HEAD")
    req.add_header("x-amz-content-sha256", payload_hash)
    req.add_header("x-amz-date", amz_date)
    req.add_header("Authorization", authorization)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return int(resp.headers.get("Content-Length", 0))
    except Exception as e:
        print(f"    ⚠️ HEAD failed: {e}")
        return None


def download_file(r2_key, local_path):
    """Download one model file using S3 GET with AWS Signature V4. Atomic rename."""
    full_path = local_path
    if os.path.exists(full_path):
        size_mb = os.path.getsize(full_path) / 1024 / 1024
        print(f"  ✓ {size_mb:.0f} MB — cached")
        return True

    endpoint = R2_ENDPOINT.rstrip("/")
    host = endpoint.replace("https://", "").replace("http://", "")
    path = f"/{R2_BUCKET}/{r2_key}"
    url = f"{endpoint}{path}"

    service = "s3"
    region = "auto"
    now = time.gmtime()
    amz_date = time.strftime("%Y%m%dT%H%M%SZ", now)
    date_stamp = time.strftime("%Y%m%d", now)
    payload_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    method = "GET"
    canonical_uri = path
    canonical_querystring = ""
    canonical_headers = f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    cr_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{cr_hash}"

    k_date = sign_v4(R2_SECRET_KEY.encode("utf-8"), date_stamp)
    k_region = sign_v4(k_date, region)
    k_service = sign_v4(k_region, service)
    k_signing = sign_v4(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = f"{algorithm} Credential={R2_ACCESS_KEY}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    tmp_path = full_path + ".download"

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("x-amz-content-sha256", payload_hash)
        req.add_header("x-amz-date", amz_date)
        req.add_header("Authorization", authorization)

        print(f"  📥 {r2_key}")
        with urllib.request.urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 8192
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int(downloaded / total * 100)
                        print(f"    {pct}%", end="\r")
        
        os.rename(tmp_path, full_path)
        mb = os.path.getsize(full_path) / 1024 / 1024
        print(f"    ✅ {mb:.0f} MB")
        return True
    except Exception as e:
        print(f"    ❌ {e}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return False


if __name__ == "__main__":
    if not R2_ACCESS_KEY or not R2_SECRET_KEY:
        print("R2: no credentials set")
        sys.exit(0)

    models = parse_model_list()
    if not models:
        print("R2: no models in MODEL_LIST")
        sys.exit(0)

    print(f"📦 Model set: {os.getenv('MODEL_LIST', 'flux2-faceswap')} ({len(models)} models)")

    successes = 0
    failures = 0
    for r2_key, local_path in models:
        ok = download_file(r2_key, local_path)
        if ok:
            successes += 1
        else:
            failures += 1

    print(f"\n✅ {successes} downloaded, {failures} failed")
