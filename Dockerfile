FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

WORKDIR /

# Install system dependencies including libass with HarfBuzz support
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    ffmpeg \
    libass9 \
    libharfbuzz0b \
    fontconfig \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    yt-dlp>=2024.12.6 \
    boto3>=1.28.85 \
    runpod>=1.5.4 \
    requests>=2.31.0 \
    aiohttp>=3.9.0 \
    aiodns>=3.1.0 \
    cchardet>=2.1.7

# Install Noto Sans Myanmar font for proper Burmese rendering
# This font supports complex script shaping required for Burmese diacritics
RUN mkdir -p /usr/share/fonts/truetype/noto && \
    wget -O /usr/share/fonts/truetype/noto/NotoSansMyanmar-Regular.ttf \
      https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSansMyanmar/NotoSansMyanmar-Regular.ttf && \
    fc-cache -f -v

ADD handler.py /handler.py

CMD ["python3", "-u", "/handler.py"]
