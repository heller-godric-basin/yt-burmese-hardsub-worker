#!/usr/bin/env python3
"""
Convert VTT to ASS with proper Burmese font and UTF-8 encoding.
This implements the fix for broken Burmese character rendering.
"""
import subprocess
import sys
from pathlib import Path

def run_cmd(cmd):
    """Run a command and print output."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: Command failed with exit code {result.returncode}")
        print(result.stderr)
        sys.exit(1)
    if result.stdout:
        print(result.stdout)
    return result

def vtt_to_ass_with_encoding_fix(
    vtt_path: str,
    ass_path: str,
    font_name: str = "Noto Sans Myanmar",
    font_size: int = 24,
):
    """Convert VTT to ASS with proper UTF-8 encoding for Burmese."""
    print(f"\n=== Converting VTT to ASS with UTF-8 encoding fix ===")
    print(f"Input: {vtt_path}")
    print(f"Output: {ass_path}")
    print(f"Font: {font_name} ({font_size}pt)")

    # Step 1: Convert VTT to ASS using ffmpeg
    print("\nStep 1: Converting VTT to ASS...")
    run_cmd(["ffmpeg", "-y", "-i", vtt_path, ass_path])

    # Step 2: Modify ASS file to set proper encoding and font
    print("\nStep 2: Applying UTF-8 encoding fix...")
    content = Path(ass_path).read_text(encoding="utf-8")
    lines = content.splitlines()
    new_lines = []

    for line in lines:
        if line.startswith("Style: "):
            # ASS Style format:
            # Style: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,
            #        Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,
            #        Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
            parts = line.split(",")
            if len(parts) >= 21:
                # Update font settings
                parts[1] = font_name      # Fontname
                parts[2] = str(font_size) # Fontsize

                # CRITICAL FIX: Set Encoding to 1 (UTF-8)
                # This tells libass to properly handle Unicode and trigger HarfBuzz shaping
                parts[20] = "1"           # Encoding: 1 = UTF-8

                line = ",".join(parts)
                print(f"Modified style line:")
                print(f"  Font: {parts[1]}")
                print(f"  Size: {parts[2]}")
                print(f"  Encoding: {parts[20]} (UTF-8)")

        new_lines.append(line)

    # Write back with UTF-8 encoding
    Path(ass_path).write_text("\n".join(new_lines), encoding="utf-8")
    print(f"\n✓ ASS file created with UTF-8 encoding fix: {ass_path}")

    # Show a sample of the ASS file
    print("\n=== ASS File Preview (first 30 lines) ===")
    for i, line in enumerate(new_lines[:30], 1):
        print(f"{i:3d}: {line}")

if __name__ == "__main__":
    vtt_file = "lXfEK8G8CUI.my.vtt"
    ass_file = "lXfEK8G8CUI.ass"

    if not Path(vtt_file).exists():
        print(f"ERROR: VTT file not found: {vtt_file}")
        sys.exit(1)

    vtt_to_ass_with_encoding_fix(vtt_file, ass_file)
