from __future__ import annotations

import base64
import io
import json
import uuid
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


def clean_hex(value: Any, default: str = "") -> str:
    if not isinstance(value, str):
        return default
    value = value.strip()
    if not value:
        return default
    if not value.startswith("#"):
        value = f"#{value}"
    if len(value) == 7:
        try:
            int(value[1:], 16)
        except ValueError:
            return default
        return value.upper()
    return default


def canva_text_element(text_obj: dict[str, Any], canvas_width: int, canvas_height: int) -> dict[str, Any]:
    fill = clean_hex(text_obj.get("fill"), "#111111")
    stroke = clean_hex(text_obj.get("stroke"), "")
    shadow = clean_hex(text_obj.get("shadowColor"), "")
    return {
        "id": f"canva_text_{uuid.uuid4()}",
        "type": "TEXT",
        "text": str(text_obj.get("text") or ""),
        "position": {"x": float(text_obj.get("x") or 0), "y": float(text_obj.get("y") or 0)},
        "size": {"width": float(text_obj.get("width") or 0), "height": float(text_obj.get("height") or 0)},
        "transform": {
            "scaleX": float(text_obj.get("scaleX") or 1),
            "scaleY": float(text_obj.get("scaleY") or 1),
            "rotation": float(text_obj.get("rotation") or 0),
            "opacity": float(text_obj.get("opacity") or 1),
        },
        "style": {
            "fontFamily": str(text_obj.get("fontFamily") or "Arial"),
            "fontSize": float(text_obj.get("fontSize") or 36),
            "fontWeight": str(text_obj.get("fontWeight") or "normal"),
            "fontStyle": str(text_obj.get("fontStyle") or "normal"),
            "color": fill,
            "textAlign": str(text_obj.get("textAlign") or text_obj.get("align") or "center"),
            "letterSpacing": float(text_obj.get("letterSpacing") or 0),
            "lineHeight": float(text_obj.get("lineHeight") or 1),
            "textDecoration": str(text_obj.get("textDecoration") or ""),
        },
        "effects": {
            "stroke": {"color": stroke, "width": float(text_obj.get("strokeWidth") or 0) if stroke else 0},
            "shadow": {
                "color": shadow,
                "blur": float(text_obj.get("shadowBlur") or 0) if shadow else 0,
                "offsetX": float(text_obj.get("shadowOffsetX") or 0) if shadow else 0,
                "offsetY": float(text_obj.get("shadowOffsetY") or 0) if shadow else 0,
            },
        },
        "layer": {
            "zIndex": int(text_obj.get("zIndex") or 0),
            "draggable": bool(text_obj.get("draggable", True)),
            "visible": True,
        },
        "canvas": {"width": canvas_width, "height": canvas_height},
        "source": {
            "format": "konva",
            "type": str(text_obj.get("type") or "Text"),
            "id": str(text_obj.get("id") or ""),
            "magicWriteRole": str(text_obj.get("magicWriteRole") or ""),
        },
    }


def konva_text_object(obj: dict[str, Any]) -> dict[str, Any] | None:
    if obj.get("type") == "Text":
        return dict(obj)
    children = obj.get("children")
    if not isinstance(children, list):
        return None
    text_children = [child for child in children if isinstance(child, dict) and child.get("type") == "Text"]
    if not text_children:
        return None
    selected = next(
        (child for child in text_children if str(child.get("magicWriteRole") or "") == "main"),
        max(text_children, key=lambda child: float(child.get("fontSize") or 0)),
    )
    text_obj = dict(selected)
    text_obj["x"] = float(obj.get("x") or 0) + float(text_obj.get("x") or 0)
    text_obj["y"] = float(obj.get("y") or 0) + float(text_obj.get("y") or 0)
    text_obj["zIndex"] = int(obj.get("zIndex") or text_obj.get("zIndex") or 0)
    text_obj["draggable"] = True
    text_obj["listening"] = True
    return text_obj


def convert_result_format(result: dict[str, Any], output_type: str, canvas_width: int, canvas_height: int) -> dict[str, Any]:
    converted = dict(result)
    meta = dict(converted.get("meta") or {})
    meta["output_format"] = output_type
    converted["meta"] = meta
    konva_objects = [
        text_obj
        for obj in converted.get("magic_write") or []
        if isinstance(obj, dict)
        for text_obj in [konva_text_object(obj)]
        if text_obj is not None
    ]
    if output_type == "canva":
        converted["magic_write"] = [
            canva_text_element(obj, canvas_width, canvas_height)
            for obj in konva_objects
        ]
    else:
        converted["magic_write"] = konva_objects
    return converted


def generate_magic_text(
    text: str,
    count: int,
    canvas_width: int,
    canvas_height: int,
    seed: int | None,
    output_type: str,
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
                "output_format": output_type,
            },
        }
    model = get_model(canvas_width, canvas_height)
    try:
        result = model.generate(text, count=count, modern=True, seed=seed, output_type=output_type)
    except TypeError as exc:
        message = str(exc)
        if "output_type" not in message and "output_format" not in message:
            raise
        result = model.generate(text, count=count, modern=True, seed=seed)
    return convert_result_format(result, output_type, canvas_width, canvas_height)


def previews_to_zip(previews: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, preview in enumerate(previews, start=1):
            image_bytes = data_uri_to_bytes(preview.get("image", ""))
            if image_bytes:
                archive.writestr(f"magic_write_{index}.png", image_bytes)
    return buffer.getvalue()


st.title("Magic Write")
st.caption("Generate styled transparent text previews and export Konva or Canva JSON.")

if MODEL_IMPORT_ERROR is not None:
    st.error("The app could not load `magic_write`.")
    st.exception(MODEL_IMPORT_ERROR)
    st.stop()

with st.sidebar:
    st.header("Settings")
    count = st.number_input("Variations", min_value=0, value=12, step=1)
    output_type = st.selectbox("JSON type", options=["konva", "canva"], index=0)

count_too_high = int(count) > MAX_VARIATIONS
if count_too_high:
    st.error(f"Maximum {MAX_VARIATIONS} variations allowed. Please enter {MAX_VARIATIONS} or less.")

text = st.text_area("Text", value="Sparkle", height=100, placeholder="Type text to style")

generate = st.button("Generate", type="primary", use_container_width=True, disabled=count_too_high)

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
                    output_type=output_type,
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
        file_name=f"magic_write_{result.get('meta', {}).get('output_format', 'konva')}.json",
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
