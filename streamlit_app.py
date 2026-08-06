from __future__ import annotations

import base64
import io
import json
import zipfile
from typing import Any

import streamlit as st
from PIL import Image, ImageDraw

try:
    from magic_write import MagicWriteModel
except Exception as exc:  # pragma: no cover - shown in Streamlit Cloud logs/UI.
    MagicWriteModel = None
    MODEL_IMPORT_ERROR = exc
else:
    MODEL_IMPORT_ERROR = None


st.set_page_config(page_title="Magic Write", page_icon="*", layout="wide")

MAX_VARIATIONS = 1000
DEFAULT_CANVAS_WIDTH = 420
DEFAULT_CANVAS_HEIGHT = 420


@st.cache_resource
def get_model(canvas_width: int, canvas_height: int) -> Any:
    if MagicWriteModel is None:
        raise RuntimeError(f"Could not import magic_write: {MODEL_IMPORT_ERROR}")
    return MagicWriteModel(canvas_width=canvas_width, canvas_height=canvas_height)


def data_uri_to_bytes(uri: str) -> bytes:
    if "," not in uri:
        return b""
    return base64.b64decode(uri.split(",", 1)[1])


@st.cache_data(show_spinner=False)
def preview_on_checkerboard(image_bytes: bytes) -> bytes:
    text_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    pad = 28
    tile = 16
    width = max(text_img.width + pad * 2, 360)
    height = max(text_img.height + pad * 2, 210)
    bg = Image.new("RGBA", (width, height), "#F8FAFC")
    draw = ImageDraw.Draw(bg)
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            if (x // tile + y // tile) % 2:
                draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill="#E5E7EB")
    bg.alpha_composite(text_img, ((width - text_img.width) // 2, (height - text_img.height) // 2))
    out = io.BytesIO()
    bg.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def generate_magic_text(
    text: str,
    count: int,
    canvas_width: int,
    canvas_height: int,
    seed: int | None,
) -> dict[str, Any]:
    if count <= 0:
        return {
            "magic_write": [],
            "preview_image": [],
            "meta": {
                "canvas_width": canvas_width,
                "canvas_height": canvas_height,
                "count": 0,
                "mode": "modern_composition",
                "seed": seed,
            },
        }
    model = get_model(canvas_width, canvas_height)
    return model.generate(text, count=count, modern=True, seed=seed)


def previews_to_zip(previews: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, preview in enumerate(previews, start=1):
            image_bytes = data_uri_to_bytes(preview.get("image", ""))
            if image_bytes:
                archive.writestr(f"magic_write_{index}.png", image_bytes)
    return buffer.getvalue()


st.title("Magic Write")
st.caption("Generate styled transparent text previews and export Konva-compatible JSON.")

if MODEL_IMPORT_ERROR is not None:
    st.error("The app could not load `magic_write`.")
    st.exception(MODEL_IMPORT_ERROR)
    st.stop()

with st.sidebar:
    st.header("Settings")
    count = st.number_input("Variations", min_value=0, max_value=MAX_VARIATIONS, value=12, step=1)

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
                    count=int(count),
                    canvas_width=DEFAULT_CANVAS_WIDTH,
                    canvas_height=DEFAULT_CANVAS_HEIGHT,
                    seed=None,
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
    if previews:
        st.download_button(
            "Download all PNGs as ZIP",
            data=previews_to_zip(previews),
            file_name="magic_write_pngs.zip",
            mime="application/zip",
        )
    st.info(f"Generated {len(previews)} variations. Showing all generated previews below.")

    columns = st.columns(3)
    for index, preview in enumerate(previews, start=1):
        image_bytes = data_uri_to_bytes(preview.get("image", ""))
        if not image_bytes:
            continue
        with columns[(index - 1) % len(columns)]:
            st.image(preview_on_checkerboard(image_bytes), caption=f"Variation {index}", use_container_width=True)
            st.download_button(
                "Download PNG",
                data=image_bytes,
                file_name=f"magic_write_{index}.png",
                mime="image/png",
                key=f"download_{index}",
                use_container_width=True,
            )
