# Reference-to-Video Pipeline (FAL AI)

This project provides a simple Python pipeline for generating a video from:

- Up to 4 reference images
- A text prompt

It uses the FAL endpoint `fal-ai/kling-video/o3/pro/reference-to-video`.

You can use:
- CLI script: `reference_to_video_pipeline.py`
- Web UI app: `streamlit_app.py` (recommended for no-terminal workflow)

## Requirements from FAL docs

From the current public FAL model docs:

- `prompt` is required.
- `image_urls` supports reference images for style/appearance.
- Kling-specific controls include `duration` (3-15), `shot_type`, and optional `generate_audio`.
- Output includes `video.url`.
- Authentication is via `FAL_KEY` environment variable.

Docs used:

- https://fal.ai/models/fal-ai/kling-video/o3/pro/reference-to-video/api
- https://fal.ai/docs/api-reference/client-libraries/python/fal_client

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FAL_KEY="YOUR_FAL_API_KEY"
```

## Usage

Pass 1 to 4 reference images using repeated `--ref-image`.
Each reference can be:
- Local file path (auto-uploaded to FAL storage)
- Public image URL

```bash
python reference_to_video_pipeline.py \
  --prompt "A cinematic orbit around the subject, windy field, golden hour" \
  --ref-image ./refs/subject_front.jpg \
  --ref-image ./refs/subject_side.jpg \
  --duration 8 \
  --shot-type customize \
  --no-generate-audio \
  --output ./output/shot1.mp4
```

## Streamlit UI (no manual generation commands)

Start the app:

```bash
streamlit run streamlit_app.py
```

Then in the browser UI:
- Enter prompt
- Upload 1 to 4 reference images
- Optionally set Kling advanced controls (`duration`, `shot_type`, audio)
- Click **Generate Video**
- Preview and download the generated `.mp4`

## Batch queue mode

The Streamlit UI includes a **Batch Queue** tab:

- Add multiple items where each item has:
  - its own prompt
  - 1 to 4 reference images
  - output filename
- Click **Run All Queue Items** to process jobs sequentially, one by one.
- Review results per item and download each generated video.

This helps reduce manual waiting/interaction because you can enqueue all jobs once.

With 4 references:

```bash
python reference_to_video_pipeline.py \
  --prompt "The character walks through neon city rain, cinematic camera movement" \
  --ref-image ./refs/1.jpg \
  --ref-image ./refs/2.jpg \
  --ref-image ./refs/3.jpg \
  --ref-image ./refs/4.jpg \
  --aspect-ratio 16:9 \
  --output ./output/final.mp4
```

## Notes

- This pipeline enforces max 4 references (your requested constraint).
- If generation succeeds but local download fails, the script still prints the hosted video URL.
- You can switch model via `--model` if needed.
- `FAL_KEY` must be set in your shell before running either CLI or Streamlit app.
