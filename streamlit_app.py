#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import inspect
import tempfile
from datetime import datetime
from typing import List, Optional

import streamlit as st

from reference_to_video_pipeline import (
    DEFAULT_MODEL,
    SUPPORTED_ASPECT_RATIOS,
    SUPPORTED_DURATIONS,
    SUPPORTED_SHOT_TYPES,
    fetch_video_bytes,
    generate_video,
)


st.set_page_config(page_title="FAL Reference-to-Video", page_icon="🎬", layout="centered")
st.title("Reference to Video Generator")
st.caption("Upload up to 4 reference images, enter a prompt, and generate a video with FAL.")


def save_uploaded_files(files) -> List[str]:
    saved_paths: List[str] = []
    for file in files:
        suffix = pathlib.Path(file.name).suffix or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file.getbuffer())
            saved_paths.append(tmp.name)
    return saved_paths


def call_generate_video_compat(**kwargs):
    # Handles stale/reloaded module signatures in long-running Streamlit sessions.
    allowed = set(inspect.signature(generate_video).parameters.keys())
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed}
    return generate_video(**filtered_kwargs)


with st.form("generate_form"):
    prompt = st.text_area(
        "Text prompt",
        height=140,
        placeholder="Describe motion, camera movement, scene, and style...",
    )
    uploaded_images = st.file_uploader(
        "Reference images (1 to 4)",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
    )
    aspect_ratio = st.selectbox("Aspect ratio", sorted(SUPPORTED_ASPECT_RATIOS), index=0)
    model = st.text_input("Model endpoint", value=DEFAULT_MODEL)
    with st.expander("Advanced Kling controls"):
        duration = st.selectbox("Duration (seconds)", SUPPORTED_DURATIONS, index=2)
        shot_type = st.selectbox("Shot type", SUPPORTED_SHOT_TYPES, index=0)
        generate_audio = st.checkbox("Generate native audio", value=False)
    with st.expander("Network / SSL (if certificate errors)"):
        ca_bundle = st.text_input(
            "Custom CA bundle path (optional)",
            placeholder="/path/to/corporate-ca.pem",
        )
        insecure_ssl = st.checkbox(
            "Disable SSL verification (unsafe, debugging only)",
            value=False,
        )
    output_name = st.text_input(
        "Output filename",
        value=f"generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
    )
    submitted = st.form_submit_button("Generate Video")


if submitted:
    if not prompt.strip():
        st.error("Prompt is required.")
        st.stop()
    if not uploaded_images:
        st.error("Please upload at least one reference image.")
        st.stop()
    if len(uploaded_images) > 4:
        st.error("Maximum 4 reference images are allowed.")
        st.stop()

    output_path = pathlib.Path("output") / output_name
    progress = st.empty()

    def queue_update(status: str) -> None:
        progress.info(f"Queue status: {status}")

    try:
        local_refs = save_uploaded_files(uploaded_images)
        with st.spinner("Submitting generation job to FAL..."):
            saved_path, video_url = call_generate_video_compat(
                prompt=prompt.strip(),
                reference_images=local_refs,
                output=str(output_path),
                aspect_ratio=aspect_ratio,
                model=model.strip() or DEFAULT_MODEL,
                duration=int(duration),
                shot_type=shot_type,
                generate_audio=generate_audio,
                queue_callback=queue_update,
                verify_ssl=not insecure_ssl,
                ca_bundle=(ca_bundle.strip() or None),
            )
    except Exception as exc:
        st.error(f"Generation failed: {exc}")
    else:
        progress.success("Video generated successfully.")
        st.video(video_url)

        download_name = pathlib.Path(output_name).name
        video_bytes: Optional[bytes] = None
        effective_path: pathlib.Path | None = saved_path

        if effective_path is not None and effective_path.exists():
            video_bytes = effective_path.read_bytes()
        else:
            try:
                video_bytes = fetch_video_bytes(
                    video_url,
                    verify_ssl=not insecure_ssl,
                    ca_bundle=(ca_bundle.strip() or None),
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(video_bytes)
                effective_path = output_path
                st.info(
                    f"Video saved on this machine (project folder): `{effective_path}`"
                )
            except Exception as exc:
                st.warning(
                    "Could not save the file under `output/` or fetch it for download. "
                    f"({exc}) Try **Network / SSL** options, then use **Download** below if it appears, "
                    "or open the hosted URL."
                )

        st.subheader("Save to your computer")
        st.caption(
            "Use the button to download the `.mp4`. Your browser usually puts it in **Downloads**; "
            "you can move it anywhere after that."
        )
        if not video_bytes and effective_path is not None and effective_path.exists():
            video_bytes = effective_path.read_bytes()
        if video_bytes:
            st.download_button(
                "Download video to my computer (.mp4)",
                data=video_bytes,
                file_name=download_name,
                mime="video/mp4",
                type="primary",
            )

        if effective_path is not None and effective_path.exists():
            st.markdown(f"**On-disk path (this app folder):** `{effective_path}`")
        st.markdown(f"**Hosted URL:** {video_url}")
