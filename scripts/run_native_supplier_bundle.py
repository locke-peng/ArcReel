from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def origin_from_base_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return value.strip().rstrip("/")


def redact_url(value: str) -> str:
    parsed = urlparse(value)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def data_uri(path: Path) -> str:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def media_duration(path: Path) -> float | None:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        return float(proc.stdout.strip())
    except (TypeError, ValueError):
        return None


def provider_error(body: object) -> str:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("type") or error)
        return str(body.get("msg") or body.get("message") or error or body)
    return str(body)


async def main() -> None:
    api_key = os.environ.get("MINIMAX_H3_API_KEY", "").strip()
    base_url = os.environ.get("MINIMAX_H3_BASE_URL", "").strip()
    if not api_key or not base_url:
        raise RuntimeError("MINIMAX_H3_API_KEY and MINIMAX_H3_BASE_URL are required")

    bundle_dir = Path(os.environ.get("SUPPLIER_BUNDLE_DIR", "/tmp/supplier-bundle"))
    output_dir = Path(os.environ.get("SUPPLIER_OUTPUT_DIR", "artifacts/supplier-live"))
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = bundle_dir / "manifest.json"
    prompt_path = bundle_dir / "prompt.txt"
    if not manifest_path.exists() or not prompt_path.exists():
        raise RuntimeError("decrypted supplier bundle is incomplete")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    unit_id = str(manifest["unit_id"])
    workflow_id = str(manifest["workflow_id"])
    duration = int(manifest["duration_seconds"])
    resolution = str(manifest["resolution"])
    test_resolution = os.environ.get("SUPPLIER_TEST_RESOLUTION", "").strip()
    if test_resolution:
        resolution = test_resolution
    prompt = prompt_path.read_text(encoding="utf-8")

    prompt_sha = sha256_bytes(prompt.encode("utf-8"))
    if prompt_sha != manifest["prompt_sha256"]:
        raise RuntimeError(
            f"prompt SHA mismatch: expected {manifest['prompt_sha256']}, got {prompt_sha}"
        )

    refs = manifest.get("references") or []
    ref_paths: list[Path] = []
    for ref in refs:
        path = bundle_dir / str(ref["filename"])
        if not path.exists():
            raise RuntimeError(f"missing reference file {path.name}")
        actual_sha = sha256_file(path)
        if actual_sha != ref["sha256"]:
            raise RuntimeError(
                f"reference SHA mismatch for {path.name}: expected {ref['sha256']}, got {actual_sha}"
            )
        if path.stat().st_size != int(ref["size_bytes"]):
            raise RuntimeError(f"reference size mismatch for {path.name}")
        ref_paths.append(path)

    payload: dict[str, object] = {
        "duration": duration,
        "prompt": prompt,
        "resolution": resolution,
    }
    seed = manifest.get("seed")
    if seed is not None:
        payload["seed"] = int(seed)
    for index, path in enumerate(ref_paths):
        payload[f"ref_image_{index}"] = data_uri(path)

    request_summary = {
        "unit_id": unit_id,
        "workflow_id": workflow_id,
        "duration": duration,
        "resolution": resolution,
        "seed": seed,
        "prompt_sha256": prompt_sha,
        "reference_count": len(ref_paths),
        "reference_sha256": [sha256_file(path) for path in ref_paths],
        "reference_size_bytes": [path.stat().st_size for path in ref_paths],
        "data_uri_lengths": [len(str(payload[f"ref_image_{i}"])) for i in range(len(ref_paths))],
        "payload_json_size_bytes_approx": len(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ),
    }
    (output_dir / "request_summary.json").write_text(
        json.dumps(request_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "final_prompt.txt").write_text(prompt, encoding="utf-8")

    origin = origin_from_base_url(base_url)
    create_url = f"{origin}/api/v1/comfyui/comfyui_workflow/{workflow_id}"
    poll_url = f"{origin}/api/v1/comfyui/comfyui_workflow/result/"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    timeout = httpx.Timeout(connect=30.0, read=120.0, write=300.0, pool=30.0)

    task_id = ""
    final_data: dict[str, object] | None = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            response = await client.post(create_url, headers=headers, json=payload)
        except (httpx.WriteTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            raise RuntimeError(
                "supplier submit became ambiguous; refusing automatic retry to avoid duplicate billing"
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"supplier submit returned non-JSON HTTP {response.status_code}"
            ) from exc

        data = body.get("data") if isinstance(body, dict) else None
        redacted_submit = {
            "http_status": response.status_code,
            "code": body.get("code") if isinstance(body, dict) else None,
            "msg": body.get("msg") if isinstance(body, dict) else None,
            "task_id": data.get("task_id") if isinstance(data, dict) else None,
            "status": data.get("status") if isinstance(data, dict) else None,
            "workflow": data.get("workflow") if isinstance(data, dict) else None,
        }
        (output_dir / "submit_response.redacted.json").write_text(
            json.dumps(redacted_submit, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if response.status_code >= 400 or not isinstance(body, dict) or body.get("code") != "Success":
            raise RuntimeError(
                f"supplier submit rejected request: HTTP {response.status_code}: {provider_error(body)}"
            )
        if not isinstance(data, dict) or not isinstance(data.get("task_id"), str) or not data["task_id"]:
            raise RuntimeError("supplier submit succeeded without task_id")
        task_id = data["task_id"]
        print(f"{unit_id} supplier task accepted: {task_id}")

        deadline = time.monotonic() + 1200
        last_status = ""
        while time.monotonic() < deadline:
            poll = await client.get(poll_url + task_id, headers=headers)
            try:
                poll_body = poll.json()
            except ValueError:
                await asyncio.sleep(5)
                continue
            if poll.status_code >= 400 or not isinstance(poll_body, dict):
                raise RuntimeError(f"supplier poll failed: HTTP {poll.status_code}")
            poll_data = poll_body.get("data")
            if not isinstance(poll_data, dict):
                raise RuntimeError(f"supplier poll missing data: {provider_error(poll_body)}")
            status = str(poll_data.get("status") or "").upper()
            if status != last_status:
                print(f"{unit_id} supplier task status: {status}")
                last_status = status
            if status in {"SUCCESS", "COMPLETED", "SUCCEEDED"}:
                final_data = dict(poll_data)
                break
            if status in {"FAILED", "ERROR", "CANCELLED", "CANCELED"}:
                raise RuntimeError(f"supplier task failed: {provider_error(poll_body)}")
            await asyncio.sleep(5)

        if final_data is None:
            raise RuntimeError("supplier task polling timed out")

        results = final_data.get("results")
        if not isinstance(results, list) or not results:
            raise RuntimeError("supplier success response has no results")

        video_url = ""
        for item in results:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                if str(item.get("type") or "").lower() in {"video", ""}:
                    video_url = item["url"]
                    break
            elif isinstance(item, str):
                video_url = item
                break
        if not video_url:
            raise RuntimeError("supplier success response has no video URL")

        redacted_result = {
            "task_id": task_id,
            "status": final_data.get("status"),
            "provider_duration": final_data.get("duration"),
            "result_count": len(results),
            "video_url_redacted": redact_url(video_url),
        }
        (output_dir / "poll_result.redacted.json").write_text(
            json.dumps(redacted_result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        video_response = await client.get(video_url, follow_redirects=True, timeout=180)
        video_response.raise_for_status()
        video_path = output_dir / f"{unit_id}.mp4"
        video_path.write_bytes(video_response.content)

    video_path = output_dir / f"{unit_id}.mp4"
    summary = {
        "unit_id": unit_id,
        "workflow_id": workflow_id,
        "task_id": task_id,
        "requested_duration_seconds": duration,
        "actual_duration_seconds": media_duration(video_path),
        "resolution_requested": resolution,
        "prompt_sha256": prompt_sha,
        "video_sha256": sha256_file(video_path),
        "video_size_bytes": video_path.stat().st_size,
        "reference_count": len(ref_paths),
        "reference_sha256": [sha256_file(path) for path in ref_paths],
        "supplier_status": "SUCCESS",
    }
    (output_dir / "live_test_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
