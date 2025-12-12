# YouTube Burmese Hardsub Worker

Serverless worker that:

- Downloads a YouTube video by `video_id` (up to 1080p)
- Fetches an existing polished Burmese WebVTT file from S3 at `storage/polished/{video_id}.my.vtt`
- Converts the VTT to ASS with proper Burmese font (Noto Sans Myanmar) and UTF-8 encoding
- Hard-subs the subtitles onto the video using ffmpeg with HarfBuzz text shaping
- Uploads the final hardsubbed MP4 to `storage/hard-subbed/{video_id}.mp4`

Designed to run as a Runpod serverless worker, similar to the original `yt-whisper-worker`.

## Technical Details

### Burmese Text Rendering Fix

This worker implements proper complex script rendering for Burmese text:

1. **UTF-8 Encoding**: ASS subtitles are configured with `Encoding=1` to enable proper Unicode handling
2. **HarfBuzz Text Shaping**: Uses FFmpeg's libass with HarfBuzz support for correct diacritic positioning
3. **Noto Sans Myanmar Font**: Includes full OpenType shaping tables for Burmese script
4. **ASS Filter**: Uses `ass` filter (not `subtitles`) for optimal HarfBuzz integration

Without these fixes, Burmese diacritics render as disconnected marks instead of being properly attached to their base characters.

## Local Testing

### Prerequisites
- Docker with NVIDIA GPU support
- NVIDIA drivers installed
- Environment variables in `~/.env`:
  ```bash
  AWS_ACCESS_KEY_ID=tid_...
  AWS_SECRET_ACCESS_KEY=tsec_...
  AWS_S3_BUCKET_NAME=contained-basket-3vehpxma
  AWS_ENDPOINT_URL=https://storage.railway.app
  ```

### Run with Docker Compose

```bash
# Load environment variables
source ~/.env

# Build and run
docker-compose up --build

# Or run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Build Docker Image

```bash
# Build for local testing
docker build -t hellergodric/yt-burmese-hardsub-worker:latest .

# Build for RunPod (linux/amd64)
docker build --platform linux/amd64 -t hellergodric/yt-burmese-hardsub-worker:latest .

# Push to Docker Hub
docker push hellergodric/yt-burmese-hardsub-worker:latest
```

## Deployment

See [DEPLOYMENT.md](./DEPLOYMENT.md) for complete RunPod deployment instructions.

