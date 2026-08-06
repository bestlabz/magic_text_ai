#!/usr/bin/env python3
"""Generate Magic Write JSON and preview images with the local model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from magic_write_model import MagicWriteModel, save_preview_images


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", help='text to style, e.g. "Sparkle" or "Thank\\nYou"')
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--canvas-width", type=int, default=420)
    parser.add_argument("--canvas-height", type=int, default=420)
    parser.add_argument("-o", "--output", default="magic_write_output.json")
    parser.add_argument("--save-preview-dir", default="magic_write_previews")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    model = MagicWriteModel(
        canvas_width=args.canvas_width,
        canvas_height=args.canvas_height,
    )
    result = model.generate(
        args.text.replace("\\n", "\n"),
        count=args.count,
        modern=True,
        seed=args.seed,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    preview_dir = Path(args.save_preview_dir)
    save_preview_images(result, preview_dir)

    if not args.quiet:
        print(json.dumps(result, indent=2))
    print(f"Wrote {output}")
    print(f"Wrote preview images to {preview_dir}")


if __name__ == "__main__":
    main()
