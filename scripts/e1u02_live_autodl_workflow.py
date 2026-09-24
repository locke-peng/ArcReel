from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.speech_artifact_provenance import project_subtitle_utterances
from lib.speech_composition import admit_script_unit
from lib.speech_presentation import video_unit_subtitle_timing


WORKFLOW_ID = "minimax_h3_zm_u24"
E1U02_TEXT = """[Shot 1]
@[陆家别墅]门廊，暖黄壁灯。中景、构图门廊居中、35mm浅景深，镜头固定。@[周姨]从门内右侧走出，双手在围裙上擦一下，身体前倾约10度、眼睁大2mm、嘴唇微张。
@[周姨]：{太太，您怎么来了}
声音：夜风、行李轮停。

【转场】硬切

[Shot 2] At 00:05.000
中景、构图双人、35mm，镜头轻微右摇约5度、慢速。@[沈知意]把拉杆前推10cm递出，视线越过周姨扫向门内、眼睑上抬1mm。
@[沈知意]：{念念呢}
声音：门厅声、脚步。

【转场】硬切

[Shot 3] At 00:10.000
@[陆家别墅]二楼走廊，暖黄壁灯。中景、构图门框居中、机位略低、35mm，镜头缓慢推近约0.3米、慢速。@[沈知意]右手推门（门板转约30度），看见@[陆念]趴在矮桌前串@[贝壳项链]、眉心微蹙2mm。
@[沈知意]：{念念}
声音：门轴轻响、贝壳碰撞。"""
E1U02_UNIT = {"unit_id": "E1U02", "duration_seconds": 15, "text": E1U02_TEXT}
LABELS = ["陆家别墅", "周姨", "沈知意", "陆念", "贝壳项链"]


@dataclass(frozen=True)
class Ref:
    type: str
    name: str


@dataclass(frozen=True)
class Entry:
    reference: Ref


def request_entries() -> list[Entry]:
    return [
        Entry(Ref("scene", "陆家别墅")),
        Entry(Ref("character", "周姨")),
        Entry(Ref("character", "沈知意")),
        Entry(Ref("character", "陆念")),
        Entry(Ref("prop", "贝壳项链")),
    ]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def media_duration_seconds(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 15.0


def redact_url(value: str) -> str:
    parsed = urlparse(value)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def vtt_timestamp(microseconds: int) -> str:
    milliseconds = microseconds // 1000
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def provider_error(body: object) -> str:
    if isinstance(body, dict):
        return str(body.get("msg") or body.get("message") or body.get("error") or body)
    return str(body)


async def main() -> None:
    api_key = os.environ.get("MINIMAX_H3_API_KEY", "").strip()
    base_url = os.environ.get("MINIMAX_H3_BASE_URL", "").strip().rstrip("/")
    if not api_key or not base_url:
        raise RuntimeError("MINIMAX_H3_API_KEY and MINIMAX_H3_BASE_URL must be configured")

    ref_urls = [os.environ.get(f"E1U02_REF{i}", "").strip() for i in range(5)]
    if not all(ref_urls):
        raise RuntimeError("all five original E1U02 reference URLs are required")

    out = Path(os.environ.get("E1U02_LIVE_OUT", "artifacts/e1u02-autodl-live"))
    out.mkdir(parents=True, exist_ok=True)

    compiled = compile_reference_video_provider_prompt(
        source_prompt=E1U02_TEXT,
        fallback_prompt=E1U02_TEXT,
        model_name="MiniMax-H3",
        duration_seconds=15,
        request_assets=request_entries(),
        payload={"prompt_compiler": "auto", "reference_image_labels": LABELS},
        unit_id="E1U02",
    )
    final_prompt = compiled.provider_prompt
    if "ARCREEL_H3_VISIBLE_TEXT_GUARD:" not in final_prompt:
        raise RuntimeError("visible-text guard missing")
    if "[Shot 1] [Shot 1]" in final_prompt:
        raise RuntimeError("duplicate adjacent Shot 1 marker leaked")
    ordered = [
        "<d>[Chinese] 太太，您怎么来了</d>",
        "[Shot 2] At 00:05.000",
        "<d>[Chinese] 念念呢</d>",
        "[Shot 3] At 00:10.000",
        "<d>[Chinese] 念念</d>",
    ]
    cursor = -1
    for token in ordered:
        cursor = final_prompt.find(token, cursor + 1)
        if cursor < 0:
            raise RuntimeError(f"shot/dialogue ordering preflight failed at {token!r}")

    (out / "final_prompt.txt").write_text(final_prompt, encoding="utf-8")

    payload: dict[str, object] = {
        "duration": 15,
        "prompt": final_prompt,
        "resolution": "768p横",
        "seed": 683072603085674,
    }
    for index, url in enumerate(ref_urls):
        payload[f"ref_image_{index}"] = url

    create_url = f"{base_url}/api/v1/comfyui/comfyui_workflow/{WORKFLOW_ID}"
    poll_base = f"{base_url}/api/v1/comfyui/comfyui_workflow/result/"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}

    # Do not dump signed reference URLs or the token into artifacts/logs.
    request_summary = {
        "workflow_id": WORKFLOW_ID,
        "duration": 15,
        "resolution": "768p横",
        "seed": 683072603085674,
        "prompt_sha256": hashlib.sha256(final_prompt.encode("utf-8")).hexdigest(),
        "reference_count": len(ref_urls),
        "reference_hosts": [urlparse(url).netloc for url in ref_urls],
        "reference_paths_sha256": [
            hashlib.sha256(urlparse(url).path.encode("utf-8")).hexdigest() for url in ref_urls
        ],
    }
    (out / "request_summary.json").write_text(
        json.dumps(request_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    timeout = httpx.Timeout(connect=20.0, read=60.0, write=60.0, pool=20.0)
    task_id = ""
    submit_sanitized: dict[str, object] = {}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            response = await client.post(create_url, headers=headers, json=payload)
        except (httpx.WriteTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            raise RuntimeError(
                "AutoDL submit became ambiguous; refusing automatic retry to avoid duplicate billing"
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"AutoDL submit returned non-JSON HTTP {response.status_code}"
            ) from exc

        submit_sanitized = {
            "http_status": response.status_code,
            "code": body.get("code") if isinstance(body, dict) else None,
            "msg": body.get("msg") if isinstance(body, dict) else None,
            "workflow": (body.get("data") or {}).get("workflow") if isinstance(body, dict) and isinstance(body.get("data"), dict) else None,
            "status": (body.get("data") or {}).get("status") if isinstance(body, dict) and isinstance(body.get("data"), dict) else None,
            "task_id": (body.get("data") or {}).get("task_id") if isinstance(body, dict) and isinstance(body.get("data"), dict) else None,
        }
        (out / "submit_response.redacted.json").write_text(
            json.dumps(submit_sanitized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if response.status_code >= 400 or not isinstance(body, dict) or body.get("code") != "Success":
            raise RuntimeError(
                f"AutoDL submit rejected request: HTTP {response.status_code}: {provider_error(body)}"
            )
        data = body.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("task_id"), str) or not data["task_id"]:
            raise RuntimeError("AutoDL submit succeeded without task_id")
        task_id = data["task_id"]
        print(f"AutoDL task accepted: {task_id}")

        deadline = time.monotonic() + 1200
        last_status = ""
        final_data: dict[str, object] | None = None
        while time.monotonic() < deadline:
            poll = await client.get(poll_base + task_id, headers=headers)
            try:
                poll_body = poll.json()
            except ValueError:
                await asyncio.sleep(5)
                continue
            if poll.status_code >= 400 or not isinstance(poll_body, dict):
                raise RuntimeError(f"AutoDL poll failed: HTTP {poll.status_code}")
            poll_data = poll_body.get("data")
            if not isinstance(poll_data, dict):
                raise RuntimeError(f"AutoDL poll missing data: {provider_error(poll_body)}")
            status = str(poll_data.get("status") or "").upper()
            if status != last_status:
                print(f"AutoDL task status: {status}")
                last_status = status
            if status == "SUCCESS":
                final_data = dict(poll_data)
                break
            if status == "FAILED":
                raise RuntimeError(f"AutoDL task failed: {provider_error(poll_body)}")
            await asyncio.sleep(5)

        if final_data is None:
            raise RuntimeError("AutoDL task polling timed out")

        results = final_data.get("results")
        if not isinstance(results, list) or not results:
            raise RuntimeError("AutoDL SUCCESS response has no results")
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
            raise RuntimeError("AutoDL SUCCESS response has no video URL")

        sanitized_result = {
            "task_id": task_id,
            "status": final_data.get("status"),
            "duration": final_data.get("duration"),
            "result_count": len(results),
            "video_url_redacted": redact_url(video_url),
        }
        (out / "poll_result.redacted.json").write_text(
            json.dumps(sanitized_result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        video_response = await client.get(video_url, follow_redirects=True, timeout=180)
        video_response.raise_for_status()
        video_path = out / "E1U02_fixed_live.mp4"
        video_path.write_bytes(video_response.content)

    video_path = out / "E1U02_fixed_live.mp4"
    actual_duration = media_duration_seconds(video_path)
    boundary_us = max(1, round(actual_duration * 1_000_000))
    admission = admit_script_unit("video_units", E1U02_UNIT)
    if not admission.allowed:
        raise RuntimeError("E1U02 speech admission failed after generation")
    utterances = project_subtitle_utterances(admission.preparation)
    timing = video_unit_subtitle_timing(E1U02_UNIT, admission.preparation)
    cues = timing.distribute(utterances, boundary_microseconds=boundary_us)

    subtitle_json = {
        "unit_id": "E1U02",
        "timing": timing.basis_identity,
        "video_duration_seconds": actual_duration,
        "cues": [
            {
                "start_microseconds": cue.start_microseconds,
                "duration_microseconds": cue.duration_microseconds,
                "text": cue.text,
                "speaker": cue.speaker,
            }
            for cue in cues
        ],
    }
    (out / "subtitles.fixed.json").write_text(
        json.dumps(subtitle_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    vtt = ["WEBVTT", ""]
    for index, cue in enumerate(cues, start=1):
        vtt.extend([
            str(index),
            f"{vtt_timestamp(cue.start_microseconds)} --> {vtt_timestamp(cue.end_microseconds)}",
            cue.text,
            "",
        ])
    (out / "subtitles.fixed.vtt").write_text("\n".join(vtt), encoding="utf-8")

    summary = {
        "unit_id": "E1U02",
        "workflow_id": WORKFLOW_ID,
        "compiler_applied": compiled.compiler_applied,
        "generation_mode": compiled.generation_mode,
        "requested_duration_seconds": 15,
        "actual_duration_seconds": actual_duration,
        "resolution": "768p横",
        "seed_requested": 683072603085674,
        "task_id": task_id,
        "prompt_sha256": hashlib.sha256(final_prompt.encode("utf-8")).hexdigest(),
        "video_sha256": sha256_file(video_path),
        "video_size_bytes": video_path.stat().st_size,
        "visible_text_guard_present": True,
        "shot_dialogue_order_preflight": True,
        "subtitle_policy": timing.basis_identity,
    }
    (out / "live_test_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("E1U02 AutoDL live generation completed")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
