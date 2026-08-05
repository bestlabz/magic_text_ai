from __future__ import annotations

import base64
import json
from typing import Any

import streamlit as st

try:
    from magic_write_model import MagicWriteModel
except Exception as exc:  # pragma: no cover - shown in Streamlit Cloud logs/UI.
    MagicWriteModel = None
    MODEL_IMPORT_ERROR = exc
else:
    MODEL_IMPORT_ERROR = None


st.set_page_config(page_title="Magic Write", page_icon="*", layout="wide")


@st.cache_resource
def get_model(canvas_width: int, canvas_height: int) -> Any:
    if MagicWriteModel is None:
        raise RuntimeError(f"Could not import magic_write_model: {MODEL_IMPORT_ERROR}")
    return MagicWriteModel(canvas_width=canvas_width, canvas_height=canvas_height)


def data_uri_to_bytes(uri: str) -> bytes:
    if "," not in uri:
        return b""
    return base64.b64decode(uri.split(",", 1)[1])


def generate_magic_text(
    text: str,
    count: int,
    canvas_width: int,
    canvas_height: int,
    seed: int | None,
) -> dict[str, Any]:
    model = get_model(canvas_width, canvas_height)
    return model.generate(text, count=count, modern=True, seed=seed)


st.title("Magic Write")
st.caption("Generate styled transparent text previews and export Konva-compatible JSON.")

if MODEL_IMPORT_ERROR is not None:
    st.error("The app could not load `magic_write_model`.")
    st.exception(MODEL_IMPORT_ERROR)
    st.stop()

with st.sidebar:
    st.header("Settings")
    count = st.slider("Variations", min_value=1, max_value=60, value=12)
    canvas_width = st.number_input("Canvas width", min_value=160, max_value=2000, value=420, step=20)
    canvas_height = st.number_input("Canvas height", min_value=160, max_value=2000, value=420, step=20)
    use_seed = st.checkbox("Use fixed seed")
    seed = st.number_input("Seed", min_value=0, max_value=999999, value=123, step=1) if use_seed else None

text = st.text_area("Text", value="Sparkle", height=100, placeholder="Type text to style")

generate = st.button("Generate", type="primary", use_container_width=True)

if generate:
    if not text.strip():
        st.error("Enter text first.")
    else:
        with st.spinner("Generating previews..."):
            try:
                result = generate_magic_text(
                    text=text,
                    count=count,
                    canvas_width=int(canvas_width),
                    canvas_height=int(canvas_height),
                    seed=int(seed) if seed is not None else None,
                )
            except Exception as exc:
                st.error("Generation failed.")
                st.exception(exc)
            else:
                st.session_state["magic_write_result"] = result

result = st.session_state.get("magic_write_result")
if result:
    json_bytes = json.dumps(result, indent=2).encode("utf-8")
    st.download_button(
        "Download JSON",
        data=json_bytes,
        file_name="magic_write_output.json",
        mime="application/json",
    )

    previews = result.get("preview_image") or []
    columns = st.columns(3)
    for index, preview in enumerate(previews, start=1):
        image_bytes = data_uri_to_bytes(preview.get("image", ""))
        with columns[(index - 1) % len(columns)]:
            st.image(image_bytes, caption=f"Variation {index}", use_container_width=True)
            st.download_button(
                "Download PNG",
                data=image_bytes,
                file_name=f"magic_write_{index}.png",
                mime="image/png",
                key=f"download_{index}",
                use_container_width=True,
            )
