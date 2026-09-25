from __future__ import annotations

import base64
from pathlib import Path

from awsnap.model import RunMetadata, canonical_json

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "viewer.html.tmpl"


def render_html(
    *,
    resources_parquet: bytes,
    metadata_parquet: bytes,
    meta: RunMetadata,
    template_path: Path = TEMPLATE_PATH,
) -> str:
    """Render HTML template with base64-encoded Parquet data.

    Args:
        resources_parquet: Bytes of resources Parquet file
        metadata_parquet: Bytes of metadata Parquet file
        meta: RunMetadata object
        template_path: Path to the HTML template

    Returns:
        Rendered HTML string
    """
    # Read template
    template = template_path.read_text()

    # Encode parquets as base64
    resources_b64 = base64.b64encode(resources_parquet).decode("utf-8")
    metadata_b64 = base64.b64encode(metadata_parquet).decode("utf-8")

    # Prepare metadata JSON with escaped </
    meta_dict = meta.as_dict()
    meta_json = canonical_json(meta_dict)
    meta_json_escaped = meta_json.replace("</", "<\\/")

    # Prepare title
    title = f"awsnap {meta.account_id} {meta.collected_at.strftime('%Y-%m-%d')}"

    # Replace placeholders
    html = template
    html = html.replace("__AWSNAP_RESOURCES_B64__", resources_b64)
    html = html.replace("__AWSNAP_METADATA_B64__", metadata_b64)
    html = html.replace("__AWSNAP_META_JSON__", meta_json_escaped)
    html = html.replace("__AWSNAP_TITLE__", title)
    html = html.replace("__AWSNAP_VERSION__", meta.awsnap_version)

    return html


def output_filename(meta: RunMetadata) -> str:
    """Generate output filename from metadata.

    Args:
        meta: RunMetadata object

    Returns:
        Filename string in format "awsnap-{account_id}-{YYYY-MM-DD}.html"
    """
    date_str = meta.collected_at.strftime("%Y-%m-%d")
    return f"awsnap-{meta.account_id}-{date_str}.html"
