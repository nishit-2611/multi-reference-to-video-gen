#!/usr/bin/env python3
"""
Reference-image-to-video pipeline using fal.ai.

Inputs:
  - Up to 4 reference images (local paths or URLs)
  - Text prompt
Output:
  - Generated .mp4 video saved locally
"""

from __future__ import annotations

import argparse
import os
import pathlib
import ssl
import sys
import urllib.request
from typing import Callable, List, Optional, Tuple

import fal_client


DEFAULT_MODEL = "fal-ai/kling-video/o3/pro/reference-to-video"
SUPPORTED_ASPECT_RATIOS = {"16:9", "9:16", "1:1"}
SUPPORTED_DURATIONS = tuple(range(3, 16))
SUPPORTED_SHOT_TYPES = ("customize", "template")


def is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def upload_if_local(image_input: str) -> str:
    if is_url(image_input):
        return image_input

    path = pathlib.Path(image_input).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Reference image not found: {path}")
    if not path.is_file():
        raise ValueError(f"Reference image is not a file: {path}")

    return fal_client.upload_file(str(path))


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a video from reference images and a prompt via fal.ai"
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="Text prompt describing the target video",
    )
    parser.add_argument(
        "--ref-image",
        action="append",
        required=True,
        help="Reference image path or URL. Pass this argument up to 4 times.",
    )
    parser.add_argument(
        "--aspect-ratio",
        default="16:9",
        choices=sorted(SUPPORTED_ASPECT_RATIOS),
        help="Output video aspect ratio",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="fal model endpoint id",
    )
    parser.add_argument(
        "--duration",
        type=int,
        choices=SUPPORTED_DURATIONS,
        default=5,
        help="Kling output duration in seconds (3-15)",
    )
    parser.add_argument(
        "--shot-type",
        choices=SUPPORTED_SHOT_TYPES,
        default="customize",
        help="Kling multi-shot mode",
    )
    parser.add_argument(
        "--generate-audio",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable native audio generation",
    )
    parser.add_argument(
        "--ca-bundle",
        default=None,
        help="Path to custom CA bundle PEM for HTTPS verification",
    )
    parser.add_argument(
        "--insecure-ssl",
        action="store_true",
        help="Disable SSL verification (unsafe, only for local debugging)",
    )
    parser.add_argument(
        "--output",
        default="output/generated_video.mp4",
        help="Output .mp4 path",
    )
    return parser.parse_args()


def validate_inputs(prompt: str, refs: List[str]) -> None:
    if not prompt.strip():
        raise ValueError("Prompt cannot be empty.")
    if len(refs) == 0:
        raise ValueError("At least one reference image is required.")
    if len(refs) > 4:
        raise ValueError("A maximum of 4 reference images is allowed.")


def _build_ssl_context(
    verify_ssl: bool = True, ca_bundle: Optional[str] = None
) -> ssl.SSLContext:
    if ca_bundle:
        ca_path = pathlib.Path(ca_bundle).expanduser().resolve()
        if not ca_path.exists():
            raise FileNotFoundError(f"CA bundle not found: {ca_path}")
        return ssl.create_default_context(cafile=str(ca_path))
    if verify_ssl:
        return ssl.create_default_context()
    return ssl._create_unverified_context()


def download_video(
    video_url: str,
    output_path: pathlib.Path,
    verify_ssl: bool = True,
    ca_bundle: Optional[str] = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    context = _build_ssl_context(verify_ssl=verify_ssl, ca_bundle=ca_bundle)
    with urllib.request.urlopen(video_url, context=context) as resp:
        output_path.write_bytes(resp.read())


def fetch_video_bytes(
    video_url: str,
    verify_ssl: bool = True,
    ca_bundle: Optional[str] = None,
) -> bytes:
    """Download video from URL into memory (same SSL handling as generate_video)."""
    context = _build_ssl_context(verify_ssl=verify_ssl, ca_bundle=ca_bundle)
    with urllib.request.urlopen(video_url, context=context) as resp:
        return resp.read()


def configure_ssl(verify_ssl: bool = True, ca_bundle: Optional[str] = None) -> None:
    if ca_bundle:
        ca_path = pathlib.Path(ca_bundle).expanduser().resolve()
        if not ca_path.exists():
            raise FileNotFoundError(f"CA bundle not found: {ca_path}")
        os.environ["SSL_CERT_FILE"] = str(ca_path)
        os.environ["REQUESTS_CA_BUNDLE"] = str(ca_path)
        os.environ["CURL_CA_BUNDLE"] = str(ca_path)
        ssl._create_default_https_context = ssl.create_default_context
        return

    if not verify_ssl:
        os.environ["PYTHONHTTPSVERIFY"] = "0"
        os.environ["CURL_CA_BUNDLE"] = ""
        ssl._create_default_https_context = ssl._create_unverified_context
        return

    ssl._create_default_https_context = ssl.create_default_context


def generate_video(
    prompt: str,
    reference_images: List[str],
    output: str = "output/generated_video.mp4",
    aspect_ratio: str = "16:9",
    model: str = DEFAULT_MODEL,
    duration: int = 5,
    shot_type: str = "customize",
    generate_audio: Optional[bool] = None,
    queue_callback: Optional[Callable[[str], None]] = None,
    verify_ssl: bool = True,
    ca_bundle: Optional[str] = None,
) -> Tuple[Optional[pathlib.Path], str]:
    api_key = os.getenv("FAL_KEY")
    if not api_key:
        raise RuntimeError("Missing FAL_KEY environment variable.")

    configure_ssl(verify_ssl=verify_ssl, ca_bundle=ca_bundle)
    validate_inputs(prompt, reference_images)
    uploaded_refs = [upload_if_local(item) for item in reference_images]

    request_payload = {
        "prompt": prompt,
        "image_urls": uploaded_refs,
        "aspect_ratio": aspect_ratio,
        "duration": str(duration),
        "shot_type": shot_type,
    }
    if generate_audio is not None:
        request_payload["generate_audio"] = generate_audio

    def on_queue_update(update):
        status = str(getattr(update, "status", "UNKNOWN"))
        if queue_callback:
            queue_callback(status)

    result = fal_client.subscribe(
        model,
        arguments=request_payload,
        with_logs=True,
        on_queue_update=on_queue_update,
    )

    video_info = result.get("video") if isinstance(result, dict) else None
    video_url = video_info.get("url") if isinstance(video_info, dict) else None
    if not video_url:
        raise RuntimeError(f"Unexpected result shape: {result}")

    output_path = pathlib.Path(output).expanduser().resolve()
    try:
        download_video(
            video_url,
            output_path,
            verify_ssl=verify_ssl,
            ca_bundle=ca_bundle,
        )
    except Exception:
        return None, video_url
    return output_path, video_url


def main() -> int:
    args = build_args()

    try:
        print(f"Submitting request to model: {args.model}")
        print(f"Using {len(args.ref_image)} reference image(s).")
        output_path, video_url = generate_video(
            prompt=args.prompt,
            reference_images=args.ref_image,
            output=args.output,
            aspect_ratio=args.aspect_ratio,
            model=args.model,
            duration=args.duration,
            shot_type=args.shot_type,
            generate_audio=args.generate_audio,
            queue_callback=lambda status: print(f"Queue update: {status}"),
            verify_ssl=not args.insecure_ssl,
            ca_bundle=args.ca_bundle,
        )
    except Exception as exc:
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 1

    print("Video generated successfully.")
    if output_path is not None:
        print(f"Saved to: {output_path}")
    else:
        print("Local download skipped/failed due to SSL; use hosted URL below.")
    print(f"Source URL: {video_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
