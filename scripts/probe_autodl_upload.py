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
                    marker_snippets = []
                    for marker in ("cg_tool_upload", "uploadModel", "workflow_input", "comfyui/inputs", "large-model", "ref_image_0"):
                        start = 0
                        while True:
                            pos = text.find(marker, start)
                            if pos < 0:
                                break
                            marker_snippets.append({
                                "marker": marker,
                                "snippet": redact(text[max(0, pos - 2500): pos + 4000]),
                            })
                            start = pos + len(marker)
                            if len(marker_snippets) >= 80:
                                break
                    if marker_snippets:
                        row["marker_snippets"] = marker_snippets[:80]
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
        initial_rows = [row for row in rows if row.get("hits")]
        dynamic_candidates: list[str] = []
        for row in rows:
            if row.get("path") != "/assets/index.85084518.js":
                continue
            response = await client.get(urljoin(str(page.url), row["path"]))
            if response.status_code != 200:
                continue
            main_js = response.text
            (out / "main.public.js").write_text(main_js, encoding="utf-8")
            names = re.findall(r'assets/[A-Za-z0-9_.-]+\\.js', main_js)
            for name in names:
                if any(token in name for token in (
                    "large-model", "comfy-ui", "set-image", "detail.", "index.", "upload",
                )):
                    dynamic_candidates.append(name)
        dynamic_candidates = list(dict.fromkeys(dynamic_candidates))[:120]
        dynamic_rows: list[dict[str, object]] = []
        for asset in dynamic_candidates:
            url = urljoin(str(page.url), "/" + asset)
            row: dict[str, object] = {"path": "/" + asset}
            try:
                response = await client.get(url)
                row["status"] = response.status_code
                row["bytes"] = len(response.content)
                text_value = response.text if response.status_code == 200 else ""
                if text_value:
                    wanted = []
                    for marker in (
                        "ref_image_0", "workflow_input", "comfyui/inputs",
                        "upload", "presign", "tos-cn-", "cg-comfyui-prod",
                        "FormData", "/api/v1/file", "large-model",
                    ):
                        start = 0
                        while True:
                            pos = text_value.find(marker, start)
                            if pos < 0:
                                break
                            wanted.append({
                                "marker": marker,
                                "snippet": redact(text_value[max(0, pos - 1800):pos + 3000]),
                            })
                            start = pos + len(marker)
                            if len(wanted) >= 60:
                                break
                    if wanted:
                        row["hits"] = wanted[:60]
                        safe_name = asset.replace("/", "__")
                        (out / safe_name).write_text(text_value, encoding="utf-8")
            except Exception as exc:
                row["error"] = type(exc).__name__
            if row.get("hits"):
                dynamic_rows.append(row)
        result = {
            "page_status": page.status_code,
            "page_path": urlparse(str(page.url)).path,
            "script_count": len(links),
            "scripts_with_hits": initial_rows,
            "dynamic_candidate_count": len(dynamic_candidates),
            "dynamic_scripts_with_hits": dynamic_rows,
        }
        (out / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "page_status": result["page_status"],
            "script_count": result["script_count"],
            "hit_scripts": len(result["scripts_with_hits"]),
        }, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
