#!/usr/bin/env python3
"""
Test hardsubbing with Burmese subtitles - first 3 minutes only.
"""
import subprocess
import sys

def run_cmd(cmd, timeout=600):
    """Run a command and show output."""
    print(f"\nRunning: {' '.join(cmd)}")
    print("=" * 80)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        print(f"ERROR: Command failed with exit code {result.returncode}")
        print(result.stderr)
        sys.exit(1)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    print("=" * 80)
    return result

def hardsub_video(
    video_path: str,
    ass_path: str,
    output_path: str,
    duration: int = 180,  # 3 minutes
):
    """Hard-sub video with ASS subtitles, processing only first N seconds."""
    print(f"\n=== Hardsubbing Video (first {duration} seconds) ===")
    print(f"Input video: {video_path}")
    print(f"Subtitles: {ass_path}")
    print(f"Output: {output_path}")

    # Font should already be installed
    print("\nUsing Noto Sans Myanmar font...")

    # Hardsub command with:
    # - Duration limit: -t 180 (first 3 minutes)
    # - Subtitles filter with ASS file
    # - Fast encoding for testing: -preset veryfast
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-t", str(duration),  # Only process first N seconds
        "-vf", f"ass={ass_path}",  # Use ass filter (better than subtitles for ASS files)
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        output_path,
    ]

    run_cmd(cmd, timeout=1800)
    print(f"\n✓ Hardsubbed video created: {output_path}")

if __name__ == "__main__":
    video_file = "lXfEK8G8CUI.webm"
    ass_file = "lXfEK8G8CUI.ass"
    output_file = "lXfEK8G8CUI_hardsubbed_test.mp4"

    hardsub_video(video_file, ass_file, output_file, duration=180)
