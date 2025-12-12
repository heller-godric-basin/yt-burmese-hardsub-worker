# Deployment Guide for RunPod Serverless - Hardsub Worker

## Overview

This worker creates hardsubbed MP4 videos with embedded Burmese subtitles. It runs as a serverless GPU worker on RunPod.

## Deployment Methods

### Method 1: Docker Hub (Traditional)

1. **Build and Push Docker Image**
   ```bash
   cd /home/heller/yt-burmese-hardsub-worker

   # Build for linux/amd64 platform
   docker build --platform linux/amd64 -t hellergodric/yt-burmese-hardsub-worker:latest .

   # Push to Docker Hub
   docker push hellergodric/yt-burmese-hardsub-worker:latest
   ```

2. **Create RunPod Endpoint**
   - Go to https://www.console.runpod.io/serverless
   - Click **"New Endpoint"**
   - Choose **"Import from Docker Registry"**
   - Enter image: `docker.io/hellergodric/yt-burmese-hardsub-worker:latest`

3. **Configure Endpoint**
   - **Endpoint Name**: `yt-hardsub-burmese`
   - **GPU Type**: RTX 4090 or A100 (needs good encode performance)
   - **Min vCPU**: 4
   - **Min Memory**: 16 GB
   - **Container Disk**: 40 GB
   - **Min Workers**: 0
   - **Max Workers**: 3

4. **Set Environment Variables** (in RunPod Secrets)
   - `RUNPOD_SECRET_S3_BUCKET`: `contained-basket-3vehpxma`
   - `RUNPOD_SECRET_S3_ENDPOINT_URL`: `https://storage.railway.app`
   - `RUNPOD_SECRET_AWS_ACCESS_KEY_ID`: Your Railway storage access key
   - `RUNPOD_SECRET_AWS_SECRET_ACCESS_KEY`: Your Railway storage secret key

### Method 2: GitHub Integration (Automated - Recommended)

1. **Configure RunPod Endpoint with GitHub**
   - Go to https://www.console.runpod.io/serverless
   - Click **"New Endpoint"**
   - Choose **"GitHub Repo"**
   - Connect your GitHub account if not already connected
   - Select repository: `heller-godric-basin/yt-burmese-hardsub-worker`
   - Branch: `main`
   - Dockerfile path: `./Dockerfile`

2. **Configure Endpoint** (same as Method 1)

3. **Set Environment Variables** (same as Method 1)

4. **Auto-Rebuild on Git Push**
   - Every push to `main` branch automatically triggers rebuild
   - RunPod builds and deploys the new image
   - No manual Docker Hub push needed

## Input Specification

```json
{
  "input": {
    "video_id": "lXfEK8G8CUI"
  }
}
```

The worker expects:
- Polished Burmese VTT at: `s3://bucket/storage/polished/{video_id}.my.vtt`
- Original YouTube video accessible at: `https://www.youtube.com/watch?v={video_id}`

## Output Specification

Success:
```json
{
  "status": "done",
  "request_id": "job-id",
  "video_id": "lXfEK8G8CUI",
  "output_key": "storage/hard-subbed/lXfEK8G8CUI.mp4",
  "output_path": "s3://bucket/storage/hard-subbed/lXfEK8G8CUI.mp4",
  "bucket": "contained-basket-3vehpxma"
}
```

Error:
```json
{
  "status": "error",
  "request_id": "job-id",
  "error": "error message"
}
```

## Current Endpoint

- **Endpoint ID**: `75bzw0fqnsk62a`
- **API URL**: `https://api.runpod.ai/v2/75bzw0fqnsk62a`

## Testing

```bash
# Using curl
curl -X POST "https://api.runpod.ai/v2/75bzw0fqnsk62a/run" \
  -H "Authorization: Bearer YOUR_RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"video_id": "lXfEK8G8CUI"}}'

# Check status
curl "https://api.runpod.ai/v2/75bzw0fqnsk62a/status/JOB_ID" \
  -H "Authorization: Bearer YOUR_RUNPOD_API_KEY"
```

## Troubleshooting

### Build Failures
- Ensure all dependencies are in both `requirements.txt` AND `Dockerfile`
- Check that version constraints don't use shell-breaking characters (`<`, `>`)
- Verify base image matches CUDA version needed

### Runtime Failures
- Check RunPod logs for import errors
- Verify S3 credentials are set correctly
- Ensure polished VTT file exists at expected S3 path
- Check that YouTube video is accessible

### Font Rendering Issues
- Noto Sans Myanmar font should be installed during Docker build
- Run `fc-cache -f -v` to rebuild font cache
- Verify libass and libharfbuzz are installed

## Cost Optimization

- **GPU Choice**: RTX 4090 offers best price/performance for video encoding
- **Auto-scaling**: Set min workers to 0, max to 2-3
- **Interruptible**: Enable for 50-80% cost savings on non-urgent jobs

## Sources

- [RunPod GitHub Integration](https://docs.runpod.io/serverless/workers/github-integration)
- [RunPod Deploy with GitHub](https://docs.runpod.io/serverless/github-integration)
