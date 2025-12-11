# YouTube Burmese Hardsub Worker

Serverless worker that:

- Downloads a YouTube video by `video_id` (up to 1080p)
- Fetches an existing polished Burmese WebVTT file from S3 at `storage/polished/{video_id}.my.vtt`
- Converts the VTT to ASS with a large Burmese font (Noto Sans Myanmar)
- Hard-subs the subtitles onto the video using ffmpeg
- Uploads the final hardsubbed MP4 to `storage/hard-subbed/{video_id}.mp4`

Designed to run as a Runpod serverless worker, similar to the original `yt-whisper-worker`.

