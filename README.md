# Magic Write Model Export

Version: `2026.08.05-modern-v1`

This folder is a reusable Magic Write app and local generator.

## Install

```bash
pip install -r requirements.txt
```

## Run the Streamlit app locally

```bash
streamlit run streamlit_app.py
```

## Deploy on Streamlit Community Cloud

1. Push this whole folder to a GitHub repository.
2. Go to `https://share.streamlit.io`.
3. Click `Create app`.
4. Select your repository, branch, and `streamlit_app.py` as the main file.
5. Open `Advanced settings` and select Python `3.11` or `3.12`.
6. Click `Deploy`.

If an existing deployed app was created with a different Python version, delete
that app and deploy it again with Python `3.11` or `3.12`. Streamlit Community
Cloud does not change the Python version of an existing app during a reboot.

Keep these files in the deployed repository:

```text
streamlit_app.py
requirements.txt
magic_write.py
magic_write_trained_dataset.json
.font_cache/
```

Generated preview folders and generated JSON files are sample outputs. They are
not required for the app to run.

## Use

```python
from magic_write import MagicWriteModel

model = MagicWriteModel()
result = model.generate("Sparkle", count=12, modern=True)
```

## CLI

```bash
python3 generate_magic_text.py "Sparkle" \
  --count 12 \
  -o sparkle_glow_check.json \
  --save-preview-dir sparkle_glow_previews
```

The saved trained dataset is in:

```text
magic_write_trained_dataset.json
```
