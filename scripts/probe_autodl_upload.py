from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx


PAGE = "https://www.autodl.art/large-model/comfyui/minimax_h3_image_audio_to_video_v2_15s"
MARKERS = (
    "cg-comfyui-prod",
    "tos-cn-beijing",
    "presign",
    "pre-sign",
    "upload",
    "ref_image_0",
    "comfyui/inputs",
    "workflow_input",
)


def redact(text: str) -> str:
    text = re.sub(r"AKL[A-Z0-9]+", "<ACCESS_KEY_ID>", text)
    text = re.sub(r"(?i)(token|authorization|api[_-]?key)(.{0,8})[A-Za-z0-9_\-]{16,}", r"\1\2<REDACTED>", text)
    return text


async def main() -> None:
    out = Path("artifacts/autodl-upload-probe")
    out.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        page = await client.get(PAGE)
        page.raise_for_status()
        html = page.text
        scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.I)
        links = [urljoin(str(page.url), src) for src in scripts]
        rows: list[dict[str, object]] = []
        for index, url in enumerate(links):
            row: dict[str, object] = {"index": index, "path": urlparse(url).path}
            try:
                response = await client.get(url)
                row["status"] = response.status_code
                row["bytes"] = len(response.content)
                text = response.text if response.status_code == 200 else ""
                hits = []
                lower = text.lower()
                for marker in MARKERS:
                    pos = lower.find(marker.lower())
                    if pos >= 0:
                        snippet = text[max(0, pos - 500): pos + 1000]
                        hits.append({"marker": marker, "snippet": redact(snippet)})
                if hits:
                    row["hits"] = hits
                if text:
                    quoted = re.findall(r'["\\\']([^"\\\']{1,500})["\\\']', text)
                    upload_strings = []
                    api_strings = []
                    for value in quoted:
                        lower_value = value.lower()
                        if any(token in lower_value for token in ("upload", "presign", "tos-cn-", "comfyui-prod", "workflow_input")):
                            upload_strings.append(redact(value))
                        if "/api/" in lower_value and any(token in lower_value for token in ("file", "upload", "comfyui", "oss", "tos")):
                            api_strings.append(redact(value))
                    if upload_strings:
                        row["upload_strings"] = list(dict.fromkeys(upload_strings))[:200]
                    if api_strings:
                        row["api_strings"] = list(dict.fromkeys(api_strings))[:200]
            except Exception as exc:
                row["error"] = type(exc).__name__
            rows.append(row)
        result = {
            "page_status": page.status_code,
            "page_path": urlparse(str(page.url)).path,
            "script_count": len(links),
            "scripts_with_hits": [row for row in rows if row.get("hits")],
        }
        (out / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "page_status": result["page_status"],
            "script_count": result["script_count"],
            "hit_scripts": len(result["scripts_with_hits"]),
        }, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
