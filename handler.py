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

import runpod
import boto3
from enum import Enum

try:
    from pytubefix import YouTube
    PYTUBEFIX_AVAILABLE = True
except ImportError:
    PYTUBEFIX_AVAILABLE = False
    print("WARNING: pytubefix not available, will only use yt-dlp", file=sys.stderr)


DEFAULT_FONT_NAME = "Noto Sans Myanmar"
DEFAULT_FONT_SIZE = 24
DEFAULT_POLISHED_PREFIX = "storage/polished"
DEFAULT_HARDSUB_PREFIX = "storage/hard-subbed"
DEFAULT_MAX_HEIGHT = 1080


class SubtitleStyle(str, Enum):
    """Subtitle background style options."""
    OPAQUE_BLACK = "opaque_black"      # White text on opaque black box (masks existing subs)
    TRANSPARENT = "transparent"         # White text with outline, no background box
    # Future options:
    # WHITE_BACKGROUND = "white_background"  # Black text on white box


DEFAULT_SUBTITLE_STYLE = SubtitleStyle.OPAQUE_BLACK


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


def download_youtube_video_ytdlp(
    video_id: str, output_dir: str, max_height: int = DEFAULT_MAX_HEIGHT
) -> str:
    """Download full YouTube video (video+audio) up to max_height using yt-dlp."""
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"[YT-DLP] Attempting download: {youtube_url}")

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
    print(f"[YT-DLP] ✓ Successfully downloaded video to: {video_path}")
    return video_path


def download_youtube_video_pytubefix(
    video_id: str, output_dir: str, max_height: int = DEFAULT_MAX_HEIGHT
) -> str:
    """
    Download full YouTube video (video+audio) up to max_height using pytubefix.
    Fallback method when yt-dlp fails.
    """
    if not PYTUBEFIX_AVAILABLE:
        raise RuntimeError("pytubefix is not available")

    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"[PYTUBEFIX] Attempting download: {youtube_url}")

    yt = YouTube(youtube_url)
    print(f"[PYTUBEFIX] Video title: {yt.title}")
    print(f"[PYTUBEFIX] Video length: {yt.length}s")

    # Try to get progressive stream first (has both video and audio, max 720p)
    progressive_stream = yt.streams.filter(
        progressive=True,
        file_extension='mp4'
    ).order_by('resolution').desc().first()

    # Check if progressive stream meets our quality requirements
    if progressive_stream:
        res_height = int(progressive_stream.resolution.replace('p', ''))
        if res_height >= max_height or max_height <= 720:
            print(f"[PYTUBEFIX] Using progressive stream: {progressive_stream.resolution}")
            output_path = progressive_stream.download(
                output_path=output_dir,
                filename=f"{video_id}.mp4"
            )
            print(f"[PYTUBEFIX] ✓ Successfully downloaded video to: {output_path}")
            return output_path

    # Need higher quality - download and merge separate streams
    print(f"[PYTUBEFIX] Downloading separate video and audio streams for higher quality...")

    # Get best video stream up to max_height
    video_streams = yt.streams.filter(
        adaptive=True,
        file_extension='mp4',
        only_video=True
    )

    # Filter by max_height
    suitable_streams = [
        s for s in video_streams
        if s.resolution and int(s.resolution.replace('p', '')) <= max_height
    ]

    if not suitable_streams:
        suitable_streams = list(video_streams)

    video_stream = max(
        suitable_streams,
        key=lambda s: int(s.resolution.replace('p', '')) if s.resolution else 0
    )

    # Get best audio stream
    audio_stream = yt.streams.filter(
        adaptive=True,
        only_audio=True
    ).order_by('abr').desc().first()

    if not video_stream or not audio_stream:
        raise RuntimeError("Could not find suitable video or audio streams")

    print(f"[PYTUBEFIX] Video stream: {video_stream.resolution} ({video_stream.mime_type})")
    print(f"[PYTUBEFIX] Audio stream: {audio_stream.abr} ({audio_stream.mime_type})")

    # Download both to temp files
    output_dir_path = Path(output_dir)
    print(f"[PYTUBEFIX] Downloading video stream...")
    video_temp = video_stream.download(
        output_path=str(output_dir_path),
        filename_prefix="temp_video_"
    )
    print(f"[PYTUBEFIX] Downloading audio stream...")
    audio_temp = audio_stream.download(
        output_path=str(output_dir_path),
        filename_prefix="temp_audio_"
    )

    # Merge with ffmpeg
    output_path = str(output_dir_path / f"{video_id}.mp4")
    print(f"[PYTUBEFIX] Merging video and audio streams with ffmpeg...")
    merge_cmd = [
        "ffmpeg", "-y",
        "-i", video_temp,
        "-i", audio_temp,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        output_path
    ]

    result = subprocess.run(merge_cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"FFmpeg merge failed: {result.stderr}")

    # Cleanup temp files
    os.remove(video_temp)
    os.remove(audio_temp)

    print(f"[PYTUBEFIX] ✓ Successfully downloaded and merged video to: {output_path}")
    return output_path


def download_youtube_video(
    video_id: str, output_dir: str, max_height: int = DEFAULT_MAX_HEIGHT
) -> str:
    """
    Download full YouTube video (video+audio) up to max_height.

    Strategy:
    1. Try yt-dlp first (faster, more reliable when working)
    2. Fall back to pytubefix if yt-dlp fails (better at bypassing bot detection)
    """
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"=" * 70)
    print(f"YOUTUBE DOWNLOAD START: {youtube_url}")
    print(f"=" * 70)

    # Try yt-dlp first
    try:
        print(f"[STRATEGY] Attempting primary method: yt-dlp")
        video_path = download_youtube_video_ytdlp(video_id, output_dir, max_height)
        print(f"[STRATEGY] ✓ PRIMARY METHOD SUCCEEDED (yt-dlp)")
        return video_path
    except Exception as e:
        print(f"[STRATEGY] ✗ Primary method failed (yt-dlp): {e}", file=sys.stderr)
        print(f"[STRATEGY] Attempting fallback method: pytubefix")

    # Fall back to pytubefix
    try:
        video_path = download_youtube_video_pytubefix(video_id, output_dir, max_height)
        print(f"[STRATEGY] ✓ FALLBACK METHOD SUCCEEDED (pytubefix)")
        return video_path
    except Exception as e:
        print(f"[STRATEGY] ✗ Fallback method failed (pytubefix): {e}", file=sys.stderr)
        raise RuntimeError(
            f"All download methods failed for {video_id}. "
            f"yt-dlp and pytubefix both encountered errors. "
            f"Last error: {e}"
        )


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
    subtitle_style: SubtitleStyle = DEFAULT_SUBTITLE_STYLE,
) -> str:
    """Convert WebVTT to ASS using ffmpeg, then adjust style for proper Burmese rendering.

    Args:
        vtt_path: Path to input WebVTT file
        ass_path: Path to output ASS file
        font_name: Font family name for subtitles
        font_size: Font size in points
        subtitle_style: Background style (opaque_black masks existing burned-in subs)
    """
    print(f"Converting VTT to ASS: {vtt_path} -> {ass_path}")
    print(f"Subtitle style: {subtitle_style.value}")

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
            # ASS Style format has 23 fields:
            # 0: Name, 1: Fontname, 2: Fontsize, 3: PrimaryColour, 4: SecondaryColour,
            # 5: OutlineColour, 6: BackColour, 7: Bold, 8: Italic, 9: Underline,
            # 10: StrikeOut, 11: ScaleX, 12: ScaleY, 13: Spacing, 14: Angle,
            # 15: BorderStyle, 16: Outline, 17: Shadow, 18: Alignment,
            # 19: MarginL, 20: MarginR, 21: MarginV, 22: Encoding
            if len(parts) >= 23:
                parts[1] = font_name           # Fontname
                parts[2] = str(font_size)      # Fontsize

                # Apply subtitle style settings
                if subtitle_style == SubtitleStyle.OPAQUE_BLACK:
                    # Opaque black box behind white text - masks existing burned-in subs
                    parts[3] = "&H00FFFFFF"    # PrimaryColour: white text
                    parts[5] = "&H00000000"    # OutlineColour: black outline
                    parts[6] = "&HFF000000"    # BackColour: fully opaque black
                    parts[15] = "3"            # BorderStyle: 3 = opaque box
                    parts[16] = "1"            # Outline: thin outline for readability
                    parts[17] = "0"            # Shadow: no shadow needed with opaque box
                elif subtitle_style == SubtitleStyle.TRANSPARENT:
                    # Traditional transparent background with outline
                    parts[3] = "&H00FFFFFF"    # PrimaryColour: white text
                    parts[5] = "&H00000000"    # OutlineColour: black outline
                    parts[6] = "&H00000000"    # BackColour: transparent
                    parts[15] = "1"            # BorderStyle: 1 = outline + shadow
                    parts[16] = "2"            # Outline: thicker outline for visibility
                    parts[17] = "1"            # Shadow: slight shadow
                # Future: add WHITE_BACKGROUND case here

                # CRITICAL FIX: Set Encoding to 1 (UTF-8)
                # This enables proper HarfBuzz text shaping for complex scripts like Burmese
                parts[22] = "1"                # Encoding: 1 = UTF-8
                line = ",".join(parts)
        new_lines.append(line)

    _Path(ass_path).write_text("\n".join(new_lines), encoding="utf-8")
    print(f"Applied subtitle style '{subtitle_style.value}' with UTF-8 encoding for Burmese")
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

        # Subtitle style option (default: opaque_black to mask existing burned-in subs)
        subtitle_style_input = job_input.get("subtitle_style", DEFAULT_SUBTITLE_STYLE.value)
        try:
            subtitle_style = SubtitleStyle(subtitle_style_input)
        except ValueError:
            valid_styles = [s.value for s in SubtitleStyle]
            return {
                "status": "error",
                "error": f"Invalid subtitle_style '{subtitle_style_input}'. Valid options: {valid_styles}",
                "request_id": request_id,
            }

        print(f"DEBUG: s3_bucket = {s3_bucket}")
        print(f"DEBUG: s3_endpoint = {s3_endpoint}")
        print(f"DEBUG: polished_prefix = {polished_prefix}")
        print(f"DEBUG: hardsub_prefix = {hardsub_prefix}")
        print(f"DEBUG: subtitle_style = {subtitle_style.value}")

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

            # Step 3: Convert VTT to ASS with Burmese font and subtitle style
            ass_path = str(tmpdir_path / f"{video_id}.ass")
            vtt_to_ass(
                vtt_path,
                ass_path,
                font_name=DEFAULT_FONT_NAME,
                font_size=DEFAULT_FONT_SIZE,
                subtitle_style=subtitle_style,
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
            "subtitle_style": subtitle_style.value,
        }

    except Exception as e:
        print(f"Handler error: {str(e)}", file=sys.stderr)
        return {
            "status": "error",
            "error": str(e),
            "request_id": event.get("input", {}).get("request_id", "unknown"),
        }


if __name__ == "__main__":
    print("Starting Runpod Serverless handler for YouTube Burmese hardsub worker v2.2")
    print("Download strategy: yt-dlp (primary) -> pytubefix (fallback)")
    print(f"Default subtitle style: {DEFAULT_SUBTITLE_STYLE.value}")
    runpod.serverless.start({"handler": handler})
