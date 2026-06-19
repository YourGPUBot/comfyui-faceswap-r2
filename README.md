# ComfyUI Face Swap — R2 Model Downloader

Serverless ComfyUI worker that downloads face-swap models from Cloudflare R2 at startup.

**Models (26GB total):**
- Flux2-Klein-9B (diffusion model)
- Qwen 3 8B fp8 (text encoder)
- Flux2-VAE
- BFS Face Swap LoRA

**Deploy:**
1. RunPod console → New Endpoint → Import from GitHub
2. Select this repo, branch `main`
3. Set env vars: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`
4. Deploy

**API Payload:**
```json
{
  "input": {
    "workflow": "faceswap",
    "images": [
      {"name": "source_image.jpg", "url": "https://..."},
      {"name": "target_image.jpg", "url": "https://..."}
    ]
  }
}
```
