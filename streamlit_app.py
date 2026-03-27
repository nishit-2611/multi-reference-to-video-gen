#!/usr/bin/env python3
from __future__ import annotations

import inspect
import pathlib
import tempfile
from datetime import datetime
from typing import Dict, List, Optional

import streamlit as st

st.set_page_config(page_title="FAL Reference-to-Video", page_icon="🎬", layout="centered")

try:
    from reference_to_video_pipeline import (
        DEFAULT_MODEL,
        SUPPORTED_ASPECT_RATIOS,
        SUPPORTED_DURATIONS,
        SUPPORTED_SHOT_TYPES,
        fetch_video_bytes,
        generate_video,
    )
except Exception as exc:
    st.error("Failed to load the video pipeline. Check Streamlit logs and `requirements.txt`.")
    st.code(str(exc), language="text")
    st.stop()

st.title("Reference to Video Generator")
st.caption(
    "Generate single videos or queue multiple prompt+reference sets and run them sequentially."
)

if "job_queue" not in st.session_state:
    st.session_state["job_queue"] = []
if "last_batch_results" not in st.session_state:
    st.session_state["last_batch_results"] = []


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


def finalize_video_download(
    output_name: str,
    output_path: pathlib.Path,
    saved_path: Optional[pathlib.Path],
    video_url: str,
    insecure_ssl: bool,
    ca_bundle: str,
) -> Dict[str, object]:
    video_bytes: Optional[bytes] = None
    effective_path: Optional[pathlib.Path] = saved_path
    warnings: List[str] = []

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
        except Exception as exc:
            warnings.append(
                "Could not save locally or fetch bytes for download. "
                f"({exc}) Try SSL options or use hosted URL."
            )

    return {
        "video_bytes": video_bytes,
        "effective_path": effective_path,
        "warnings": warnings,
        "download_name": pathlib.Path(output_name).name,
    }


def run_generation_job(
    prompt: str,
    local_refs: List[str],
    output_name: str,
    model: str,
    aspect_ratio: str,
    duration: int,
    shot_type: str,
    generate_audio: bool,
    insecure_ssl: bool,
    ca_bundle: str,
    status_prefix: str = "",
) -> Dict[str, object]:
    output_path = pathlib.Path("output") / output_name
    progress = st.empty()

    def queue_update(status: str) -> None:
        progress.info(f"{status_prefix}Queue status: {status}")

    with st.spinner(f"{status_prefix}Submitting generation job to FAL..."):
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
    progress.success(f"{status_prefix}Video generated successfully.")
    download_info = finalize_video_download(
        output_name=output_name,
        output_path=output_path,
        saved_path=saved_path,
        video_url=video_url,
        insecure_ssl=insecure_ssl,
        ca_bundle=ca_bundle,
    )
    return {"video_url": video_url, "download_info": download_info}


with st.sidebar:
    st.header("Generation Settings")
    model = st.text_input("Model endpoint", value=DEFAULT_MODEL)
    aspect_ratio = st.selectbox("Aspect ratio", sorted(SUPPORTED_ASPECT_RATIOS), index=0)
    duration = st.selectbox("Duration (seconds)", SUPPORTED_DURATIONS, index=2)
    shot_type = st.selectbox("Shot type", SUPPORTED_SHOT_TYPES, index=0)
    generate_audio = st.checkbox("Generate native audio", value=False)
    st.subheader("Network / SSL")
    ca_bundle = st.text_input(
        "Custom CA bundle path (optional)",
        placeholder="/path/to/corporate-ca.pem",
    )
    insecure_ssl = st.checkbox(
        "Disable SSL verification (unsafe, debugging only)",
        value=False,
    )

single_tab, batch_tab = st.tabs(["Single Generate", "Batch Queue"])

with single_tab:
    with st.form("single_generate_form"):
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

        try:
            local_refs = save_uploaded_files(uploaded_images)
            result = run_generation_job(
                prompt=prompt,
                local_refs=local_refs,
                output_name=output_name,
                model=model,
                aspect_ratio=aspect_ratio,
                duration=int(duration),
                shot_type=shot_type,
                generate_audio=generate_audio,
                insecure_ssl=insecure_ssl,
                ca_bundle=ca_bundle,
            )
        except Exception as exc:
            st.error(f"Generation failed: {exc}")
        else:
            video_url = str(result["video_url"])
            download_info = result["download_info"]
            st.video(video_url)
            for warning in download_info["warnings"]:
                st.warning(warning)
            if download_info["video_bytes"]:
                st.download_button(
                    "Download video to my computer (.mp4)",
                    data=download_info["video_bytes"],
                    file_name=download_info["download_name"],
                    mime="video/mp4",
                    type="primary",
                )
            if download_info["effective_path"] is not None:
                st.markdown(
                    f"**On-disk path (this app folder):** `{download_info['effective_path']}`"
                )
            st.markdown(f"**Hosted URL:** {video_url}")

with batch_tab:
    st.subheader("Batch Queue")
    st.caption(
        "Add multiple jobs (prompt + refs), then run all sequentially with one click."
    )

    with st.form("batch_enqueue_form"):
        batch_prompt = st.text_area(
            "Prompt for this queue item",
            height=120,
            placeholder="Describe scene/camera for this specific job...",
            key="batch_prompt_input",
        )
        batch_refs = st.file_uploader(
            "Reference images for this item (1 to 4)",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="batch_refs_input",
        )
        batch_output_name = st.text_input(
            "Output filename for this item",
            value=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
        )
        add_to_queue = st.form_submit_button("Add to Queue")

    if add_to_queue:
        if not batch_prompt.strip():
            st.error("Prompt is required for queue item.")
        elif not batch_refs:
            st.error("Please upload at least one reference image for queue item.")
        elif len(batch_refs) > 4:
            st.error("Maximum 4 reference images per queue item.")
        else:
            local_refs = save_uploaded_files(batch_refs)
            st.session_state["job_queue"].append(
                {
                    "prompt": batch_prompt.strip(),
                    "refs": local_refs,
                    "output_name": batch_output_name.strip() or f"batch_{len(st.session_state['job_queue']) + 1}.mp4",
                }
            )
            st.success(f"Added item #{len(st.session_state['job_queue'])} to queue.")

    queue_items = st.session_state["job_queue"]
    if queue_items:
        st.markdown("### Pending Queue")
        for idx, item in enumerate(queue_items, start=1):
            st.markdown(
                f"- **#{idx}** `{item['output_name']}` | refs: {len(item['refs'])} | prompt: {item['prompt'][:80]}"
            )

        col1, col2 = st.columns(2)
        run_all = col1.button("Run All Queue Items", type="primary")
        clear_all = col2.button("Clear Queue")

        if clear_all:
            st.session_state["job_queue"] = []
            st.info("Queue cleared.")
            st.stop()

        if run_all:
            st.session_state["last_batch_results"] = []
            total = len(queue_items)
            overall = st.progress(0.0)
            for index, item in enumerate(queue_items, start=1):
                try:
                    result = run_generation_job(
                        prompt=item["prompt"],
                        local_refs=item["refs"],
                        output_name=item["output_name"],
                        model=model,
                        aspect_ratio=aspect_ratio,
                        duration=int(duration),
                        shot_type=shot_type,
                        generate_audio=generate_audio,
                        insecure_ssl=insecure_ssl,
                        ca_bundle=ca_bundle,
                        status_prefix=f"[{index}/{total}] ",
                    )
                    st.session_state["last_batch_results"].append(
                        {
                            "success": True,
                            "item": item,
                            "video_url": result["video_url"],
                            "download_info": result["download_info"],
                        }
                    )
                except Exception as exc:
                    st.session_state["last_batch_results"].append(
                        {
                            "success": False,
                            "item": item,
                            "error": str(exc),
                        }
                    )
                overall.progress(index / total)
            st.session_state["job_queue"] = []
            st.success("Batch run completed.")
    else:
        st.info("Queue is empty. Add items above.")

    if st.session_state["last_batch_results"]:
        st.markdown("### Last Batch Results")
        for idx, result in enumerate(st.session_state["last_batch_results"], start=1):
            item = result["item"]
            if not result["success"]:
                st.error(f"#{idx} `{item['output_name']}` failed: {result['error']}")
                continue

            video_url = result["video_url"]
            download_info = result["download_info"]
            with st.expander(f"#{idx} {item['output_name']}", expanded=False):
                st.video(video_url)
                for warning in download_info["warnings"]:
                    st.warning(warning)
                if download_info["video_bytes"]:
                    st.download_button(
                        f"Download #{idx} (.mp4)",
                        data=download_info["video_bytes"],
                        file_name=download_info["download_name"],
                        mime="video/mp4",
                        key=f"batch_dl_{idx}",
                    )
                if download_info["effective_path"] is not None:
                    st.markdown(f"**On-disk path:** `{download_info['effective_path']}`")
                st.markdown(f"**Hosted URL:** {video_url}")
