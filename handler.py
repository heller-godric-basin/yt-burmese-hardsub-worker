#!/usr/bin/env python3
"""
Runpod Serverless Handler for YouTube Burmese Hardsub pipeline

Given a YouTube video_id, this worker:
- Downloads the full YouTube video (max 1080p)
- Fetches an existing polished Burmese WebVTT file from S3 at
  storage/polished/{video_id}.my.vtt
- Converts the VTT to ASS with a large Burmese font (Noto Sans Myanmar)
- Hard-subs the subtitles onto the video using ffmpeg + libass
- Uploads the final hardsubbed MP4 to storage/hard-subbed/{video_id}.mp4

S3 configuration can come from the Runpod input or environment variables.
"""

import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import runpod
    import boto3
except ImportError as e:
    print(f"ERROR: Failed to import required modules: {e}", file=sys.stderr)
    print("This likely indicates a dependency installation issue.", file=sys.stderr)
    sys.exit(1)


DEFAULT_FONT_NAME = "Noto Sans Myanmar"
DEFAULT_FONT_SIZE = 24
DEFAULT_POLISHED_PREFIX = "storage/polished"
DEFAULT_HARDSUB_PREFIX = "storage/hard-subbed"
DEFAULT_MAX_HEIGHT = 1080


def run_cmd(cmd: list[str], timeout: int = 600) -> None:
    """Run a subprocess command, raising on failure, and echoing stderr."""
    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)


def download_youtube_video(
    video_id: str, output_dir: str, max_height: int = DEFAULT_MAX_HEIGHT
) -> str:
    """Download full YouTube video (video+audio) up to max_height using yt-dlp."""
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"Downloading YouTube video: {youtube_url}")

    output_template = os.path.join(output_dir, f"{video_id}.%(ext)s")
    # Prefer best video up to max_height + best audio, falling back to best
    fmt = f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]"

    cmd = [
        "yt-dlp",
        "-f",
        fmt,
        "-o",
        output_template,
        youtube_url,
    ]
    run_cmd(cmd, timeout=900)

    # Find merged file (yt-dlp merges into a container, often .mp4 or .webm)
    candidates = list(Path(output_dir).glob(f"{video_id}.*"))
    if not candidates:
        raise RuntimeError("No video file found after yt-dlp download")

    # Prefer mp4, else take first
    mp4_candidates = [p for p in candidates if p.suffix == ".mp4"]
    video_path = str((mp4_candidates[0] if mp4_candidates else candidates[0]).resolve())
    print(f"Downloaded video to: {video_path}")
    return video_path


def get_s3_client(
    endpoint_url: Optional[str] = None,
    aws_access_key: Optional[str] = None,
    aws_secret_key: Optional[str] = None,
):
    """Construct a boto3 S3 client with optional custom endpoint and credentials."""
    kwargs: Dict[str, Any] = {}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    if aws_access_key and aws_secret_key:
        kwargs["aws_access_key_id"] = aws_access_key
        kwargs["aws_secret_access_key"] = aws_secret_key
    return boto3.client("s3", **kwargs)


def download_polished_vtt(
    s3_client,
    bucket: str,
    video_id: str,
    output_path: str,
    prefix: str = DEFAULT_POLISHED_PREFIX,
) -> str:
    """Download polished Burmese WebVTT file from S3 to output_path."""
    key = f"{prefix}/{video_id}.my.vtt"
    print(f"Downloading polished VTT from s3://{bucket}/{key} -> {output_path}")
    try:
        s3_client.download_file(bucket, key, output_path)
    except Exception as e:
        raise RuntimeError(f"Failed to download polished VTT: {e}")
    return output_path


def vtt_to_ass(
    vtt_path: str,
    ass_path: str,
    font_name: str = DEFAULT_FONT_NAME,
    font_size: int = DEFAULT_FONT_SIZE,
) -> str:
    """Convert WebVTT to ASS using ffmpeg, then adjust style for proper Burmese rendering."""
    print(f"Converting VTT to ASS: {vtt_path} -> {ass_path}")

    # Initial conversion via ffmpeg
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-i",
            vtt_path,
            ass_path,
        ],
        timeout=300,
    )

    # Adjust the default style to use our Burmese font, size, and CRITICAL: UTF-8 encoding
    from pathlib import Path as _Path

    content = _Path(ass_path).read_text(encoding="utf-8")
    lines = content.splitlines()
    new_lines = []
    for line in lines:
        if line.startswith("Style: ") and "," in line:
            parts = line.split(",")
            # ASS Style format has 23 fields, with Encoding being the last (index 20 in 0-indexed)
            # Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour,
            # Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle,
            # Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
            if len(parts) >= 21:
                parts[1] = font_name           # Fontname
                parts[2] = str(font_size)      # Fontsize
                # CRITICAL FIX: Set Encoding to 1 (UTF-8)
                # This enables proper HarfBuzz text shaping for complex scripts like Burmese
                parts[20] = "1"                # Encoding: 1 = UTF-8
                line = ",".join(parts)
        new_lines.append(line)

    _Path(ass_path).write_text("\n".join(new_lines), encoding="utf-8")
    print(f"Applied UTF-8 encoding fix for Burmese text rendering")
    return ass_path


def hard_sub_video(
    video_path: str,
    ass_path: str,
    output_path: str,
    fonts_dir: str = "/usr/share/fonts/truetype/noto",
) -> str:
    """Burn ASS subtitles into the video using ffmpeg/libass with HarfBuzz shaping."""
    print(f"Hard-subbing subtitles: {ass_path} -> {output_path}")

    # Use 'ass' filter (not 'subtitles') for proper ASS rendering with HarfBuzz
    # This ensures complex script shaping works correctly for Burmese text
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-vf",
        f"ass={ass_path}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        output_path,
    ]
    run_cmd(cmd, timeout=1800)
    return output_path


def upload_to_s3(
    s3_client,
    file_path: str,
    bucket: str,
    key: str,
) -> str:
    print(f"Uploading to S3: s3://{bucket}/{key}")
    try:
        s3_client.upload_file(file_path, bucket, key)
        return f"s3://{bucket}/{key}"
    except Exception as e:
        raise RuntimeError(f"S3 upload failed: {e}")


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """Runpod handler for Burmese hardsub worker."""
    try:
        job_input = event.get("input", {})
        video_id = job_input.get("video_id")
        request_id = job_input.get("request_id", video_id or "unknown")

        if not video_id:
            return {
                "status": "error",
                "error": "Missing required input: video_id",
                "request_id": request_id,
            }

        # S3 configuration (can come from input or environment)
        s3_bucket = job_input.get("s3_bucket") or os.getenv("RUNPOD_SECRET_S3_BUCKET")
        s3_endpoint = job_input.get("s3_endpoint_url") or os.getenv(
            "RUNPOD_SECRET_S3_ENDPOINT_URL"
        )
        polished_prefix = job_input.get("polished_prefix", DEFAULT_POLISHED_PREFIX)
        hardsub_prefix = job_input.get("hardsub_prefix", DEFAULT_HARDSUB_PREFIX)
        aws_access_key = job_input.get("aws_access_key") or os.getenv(
            "RUNPOD_SECRET_AWS_ACCESS_KEY_ID"
        )
        aws_secret_key = job_input.get("aws_secret_key") or os.getenv(
            "RUNPOD_SECRET_AWS_SECRET_ACCESS_KEY"
        )

        print(f"DEBUG: s3_bucket = {s3_bucket}")
        print(f"DEBUG: s3_endpoint = {s3_endpoint}")
        print(f"DEBUG: polished_prefix = {polished_prefix}")
        print(f"DEBUG: hardsub_prefix = {hardsub_prefix}")

        if not s3_bucket:
            return {
                "status": "error",
                "error": "S3 bucket not configured",
                "request_id": request_id,
            }

        s3_client = get_s3_client(
            endpoint_url=s3_endpoint,
            aws_access_key=aws_access_key,
            aws_secret_key=aws_secret_key,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Step 1: Download YouTube video
            video_path = download_youtube_video(video_id, tmpdir)

            # Step 2: Download polished VTT from S3
            vtt_path = str(tmpdir_path / f"{video_id}.my.vtt")
            download_polished_vtt(
                s3_client, s3_bucket, video_id, vtt_path, prefix=polished_prefix
            )

            # Step 3: Convert VTT to ASS with Burmese font
            ass_path = str(tmpdir_path / f"{video_id}.ass")
            vtt_to_ass(
                vtt_path,
                ass_path,
                font_name=DEFAULT_FONT_NAME,
                font_size=DEFAULT_FONT_SIZE,
            )

            # Step 4: Hard-sub subtitles into video
            output_filename = f"{video_id}.mp4"
            output_local_path = str(tmpdir_path / output_filename)
            hard_sub_video(video_path, ass_path, output_local_path)

            # Step 5: Upload final MP4 to S3
            output_key = f"{hardsub_prefix}/{output_filename}"
            output_s3_path = upload_to_s3(
                s3_client, output_local_path, s3_bucket, output_key
            )

        return {
            "status": "done",
            "request_id": request_id,
            "video_id": video_id,
            "output_key": output_key,
            "output_path": output_s3_path,
            "bucket": s3_bucket,
        }

    except Exception as e:
        print(f"Handler error: {str(e)}", file=sys.stderr)
        return {
            "status": "error",
            "error": str(e),
            "request_id": event.get("input", {}).get("request_id", "unknown"),
        }


if __name__ == "__main__":
    print("Starting Runpod Serverless handler for YouTube Burmese hardsub worker v1")
    runpod.serverless.start({"handler": handler})
