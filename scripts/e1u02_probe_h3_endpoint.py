from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx


INTERESTING_KEYS = {
    "prompt",
    "duration",
    "resolution",
    "seed",
    "ref_image_0",
    "ref_image_1",
    "reference_images",
    "model",
    "task_id",
    "video_url",
}


def sha12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def collect_interesting(value: object, path: tuple[str, ...] = ()) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_s = str(key)
            if key_s in INTERESTING_KEYS or key_s.startswith("ref_image_"):
                found.append(
                    {
                        "path": ".".join((*path, key_s)),
                        "value_type": type(child).__name__,
                    }
                )
            found.extend(collect_interesting(child, (*path, key_s)))
    elif isinstance(value, list):
        for index, child in enumerate(value[:50]):
            found.extend(collect_interesting(child, (*path, str(index))))
    return found


async def main() -> None:
    api_key = os.environ.get("MINIMAX_H3_API_KEY", "").strip()
    base_url = os.environ.get("MINIMAX_H3_BASE_URL", "").strip()
    if not api_key or not base_url:
        raise RuntimeError("provider secrets are not configured")

    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    base_path = parsed.path or "/"
    candidates = [
        ("base_options", "OPTIONS", base_url),
        ("base_get", "GET", base_url),
        ("origin_openapi", "GET", urljoin(origin + "/", "openapi.json")),
        ("origin_v1_openapi", "GET", urljoin(origin + "/", "v1/openapi.json")),
        ("origin_docs", "GET", urljoin(origin + "/", "docs")),
        ("docs_comfyui_api", "GET", urljoin(origin + "/", "docs/comfyui_api/")),
        ("docs_comfyui_online", "GET", urljoin(origin + "/", "docs/comfyui_online/")),
        ("base_openapi", "GET", base_url.rstrip("/") + "/openapi.json"),
    ]

    output: dict[str, object] = {
        "base": {
            "scheme": parsed.scheme,
            "host_sha256_prefix": sha12(parsed.netloc),
            "path": base_path,
            "has_query": bool(parsed.query),
        },
        "probes": [],
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for name, method, url in candidates:
            row: dict[str, object] = {"name": name, "method": method}
            try:
                response = await client.request(method, url, headers=headers)
                row.update(
                    {
                        "status_code": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                        "allow": response.headers.get("allow", ""),
                        "content_length": len(response.content),
                        "final_path": urlparse(str(response.url)).path,
                    }
                )
                ctype = response.headers.get("content-type", "")
                if "json" in ctype.lower() and len(response.content) <= 2_000_000:
                    try:
                        body = response.json()
                    except ValueError:
                        pass
                    else:
                        if isinstance(body, dict):
                            paths = body.get("paths")
                            if isinstance(paths, dict):
                                row["openapi_paths"] = list(paths.keys())[:100]
                            row["interesting_fields"] = collect_interesting(body)[:200]
                elif name in {"origin_docs", "docs_comfyui_api", "docs_comfyui_online"} and "text/html" in ctype.lower():
                    sanitized = response.text.replace(base_url, "<BASE_URL>").replace(origin, "<ORIGIN>")
                    target = Path("artifacts/e1u02-provider-probe") / f"{name}.sanitized.html"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(sanitized, encoding="utf-8")
                    lower = sanitized.lower()
                    markers = [
                        "ref_image_0",
                        "video_generation",
                        "minimax",
                        "api_key",
                        "authorization",
                        "duration",
                        "seed",
                        "resolution",
                    ]
                    row["docs_markers_present"] = {
                        marker: marker in lower for marker in markers
                    }
            except Exception as exc:
                row["error_type"] = type(exc).__name__
            output["probes"].append(row)

    out = Path("artifacts/e1u02-provider-probe")
    out.mkdir(parents=True, exist_ok=True)
    (out / "provider_probe.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
