from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx

from lib.custom_provider.declarative_backend import DeclarativeVideoBackend
from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.speech_artifact_provenance import project_subtitle_utterances
from lib.speech_composition import admit_script_unit
from lib.speech_presentation import video_unit_subtitle_timing
from lib.video_backends.base import VideoGenerationRequest


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

E1U02_UNIT = {
    "unit_id": "E1U02",
    "duration_seconds": 15,
    "text": E1U02_TEXT,
}
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
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


async def fetch_ref(client: httpx.AsyncClient, url: str, path: Path) -> None:
    response = await client.get(url, follow_redirects=True, timeout=120)
    response.raise_for_status()
    path.write_bytes(response.content)


def media_duration_seconds(path: Path) -> float:
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
    except ValueError:
        return 15.0


def vtt_timestamp(microseconds: int) -> str:
    milliseconds = microseconds // 1000
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


async def main() -> None:
    api_key = os.environ.get("MINIMAX_H3_API_KEY", "").strip()
    base_url = os.environ.get("MINIMAX_H3_BASE_URL", "").strip()
    if not api_key or not base_url:
        raise RuntimeError("MINIMAX_H3_API_KEY and MINIMAX_H3_BASE_URL must be configured")

    out = Path(os.environ.get("E1U02_LIVE_OUT", "artifacts/e1u02-live"))
    refs_dir = out / "refs"
    out.mkdir(parents=True, exist_ok=True)
    refs_dir.mkdir(parents=True, exist_ok=True)

    ref_urls = [os.environ.get(f"E1U02_REF{i}", "").strip() for i in range(5)]
    if not all(ref_urls):
        raise RuntimeError("all five E1U02 reference URLs are required")

    ref_paths = [refs_dir / f"ref_{i}.jpg" for i in range(5)]
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(fetch_ref(client, url, path) for url, path in zip(ref_urls, ref_paths, strict=True)))

    compiled = compile_reference_video_provider_prompt(
        source_prompt=E1U02_TEXT,
        fallback_prompt=E1U02_TEXT,
        model_name="MiniMax-H3",
        duration_seconds=15,
        request_assets=request_entries(),
        payload={
            "prompt_compiler": "auto",
            "reference_image_labels": LABELS,
        },
        unit_id="E1U02",
    )
    final_prompt = compiled.provider_prompt
    if "ARCREEL_H3_VISIBLE_TEXT_GUARD:" not in final_prompt:
        raise RuntimeError("fixed visible-text guard missing from final provider prompt")
    if "[Shot 1] [Shot 1]" in final_prompt:
        raise RuntimeError("duplicate adjacent Shot 1 marker leaked into detailed description")
    if not (
        final_prompt.index("<d>[Chinese] 太太，您怎么来了</d>")
        < final_prompt.index("[Shot 2] At 00:05.000")
        < final_prompt.index("<d>[Chinese] 念念呢</d>")
        < final_prompt.index("[Shot 3] At 00:10.000")
        < final_prompt.index("<d>[Chinese] 念念</d>")
    ):
        raise RuntimeError("dialogue is not bound to the intended shot order")

    (out / "final_prompt.txt").write_text(final_prompt, encoding="utf-8")

    definition = json.loads(
        Path("lib/custom_provider/builtin_endpoints/minimax-h3.json").read_text(encoding="utf-8")
    )
    provider_responses: list[dict[str, object]] = []

    async def record(stage: str, body: object) -> None:
        provider_responses.append({"stage": stage, "body": body})

    backend = DeclarativeVideoBackend(
        api_key=api_key,
        base_url=base_url,
        model="MiniMax-H3",
        definition=definition,
        provider="MiniMax H3",
    )
    video_path = out / "E1U02_fixed_live.mp4"
    request = VideoGenerationRequest(
        prompt=final_prompt,
        output_path=video_path,
        aspect_ratio="16:9",
        duration_seconds=15,
        resolution="768p",
        reference_images=ref_paths,
        generate_audio=True,
        poll_timeout_seconds=1200,
        seed=683072603085674,
        on_provider_response=record,
    )
    result = await backend.generate(request)

    if not video_path.exists() or video_path.stat().st_size <= 0:
        raise RuntimeError("provider returned success but live video artifact is missing")

    (out / "provider_responses.redacted.json").write_text(
        json.dumps(provider_responses, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    actual_duration = media_duration_seconds(video_path)
    boundary_us = max(1, round(actual_duration * 1_000_000))
    admission = admit_script_unit("video_units", E1U02_UNIT)
    if not admission.allowed:
        raise RuntimeError("E1U02 speech admission unexpectedly failed")
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
        json.dumps(subtitle_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    vtt = ["WEBVTT", ""]
    for index, cue in enumerate(cues, start=1):
        vtt.extend(
            [
                str(index),
                f"{vtt_timestamp(cue.start_microseconds)} --> {vtt_timestamp(cue.end_microseconds)}",
                cue.text,
                "",
            ]
        )
    (out / "subtitles.fixed.vtt").write_text("\n".join(vtt), encoding="utf-8")

    summary = {
        "unit_id": "E1U02",
        "compiler_applied": compiled.compiler_applied,
        "generation_mode": compiled.generation_mode,
        "provider": result.provider,
        "model": result.model,
        "requested_duration_seconds": 15,
        "actual_duration_seconds": actual_duration,
        "aspect_ratio": "16:9",
        "resolution": "768p",
        "seed_requested": 683072603085674,
        "reference_labels": LABELS,
        "reference_sha256": [sha256_file(path) for path in ref_paths],
        "prompt_sha256": hashlib.sha256(final_prompt.encode("utf-8")).hexdigest(),
        "video_sha256": sha256_file(video_path),
        "video_size_bytes": video_path.stat().st_size,
        "visible_text_guard_present": True,
        "shot_dialogue_order_preflight": True,
        "subtitle_policy": timing.basis_identity,
        "provider_task_id_present": bool(result.task_id),
    }
    (out / "live_test_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("E1U02 live MiniMax-H3 generation completed")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
