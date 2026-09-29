"""ArcReel 进程内 CLI 原型（路径 A）。

运行环境：
- 本 CLI 复用 server/tool_runtime.py 中的确定性工具（list_projects、
  create_project、upload_source 等），**不启动任何 Web 服务**。
- 运行前需安装 ArcReel 的全部依赖：在 ArcReel 项目根目录执行 `uv sync`。
- 从 ArcReel 项目根目录运行，以便 `server` / `lib` 包可被正常导入：
      python arcreel_cli.py <子命令> ...

数据共享：
- CLI 与运行中的 Web 服务共享同一份 projects/ 目录与 SQLite DB，
  因为它们都依赖 lib.app_data_dir 自动读取环境变量 ARCREEL_DATA_DIR。
  若要与某个正在运行的实例共享同一份数据，请给本 CLI 进程设置相同的
  ARCREEL_DATA_DIR 环境变量（例如：`ARCREEL_DATA_DIR=/path uv run ...`）。

生成执行说明：
- `batch get --wait` 仅轮询生成批次的状态直至终态；不带 --wait 只查询一次。
- `media submit --wait` 复用 server.media_tools 的 handle_generate_*（内部完成
  submit_media_generation 的 preflight + TaskSpec 编排），并在**进程内启动
  GenerationWorker** 真正消费队列出片，再轮询到终态。不带 --wait 则仅入队退出。
- 真出片需要可用的 provider 配置（在 WebUI / DB 中配置 API Key）；否则任务会被
  worker 认领后执行失败（仍走到终态，可看到失败原因）。可加 `--no-worker` 仅入队、
  交由已运行的 Web 服务消费队列（共享同一 ARCREEL_DATA_DIR）。
- `reference-video prompt-preview` 只读展开某个 video unit 的最终 Provider Prompt；
  核心扩展可用时支持 `prompt_compiler=auto|h3_ref2va|raw`、reference_image_labels 与临时正文覆盖。
- `media submit --type video --dry-run` 批量/单镜展开将提交的最终 Prompt，不入队、不启动 worker、
  不调用视频供应商；适合生成前检查 Subject/Picture 映射与 H3 转换结果。
- `demo seed --project <p>` 写入一份最小 narration+storyboard 样例剧本到项目
  scripts/ 目录；`config setup-image --provider-id <id> --api-key <KEY>` 把图像
  provider 的密钥落 DB；`config verify [--project <p>]` 校验 provider 就绪状态与
  项目图像后端是否可被 worker 解析。配置好一个图像 provider 后即可
  `media submit --type storyboard --wait` 真出片。
"""

import os
import re
import sys

try:
    import argparse
    import asyncio
    import json
    from dataclasses import asdict, is_dataclass
    from pathlib import Path
    from typing import Any, Awaitable, Callable, Dict, List, Optional

    from lib.db import init_db, close_db, async_session_factory
    from lib.db.base import DEFAULT_USER_ID
    from lib.project_manager import get_project_manager
    from lib.config.resolver import ConfigResolver
    from lib.config.service import ConfigService
    from lib.config.registry import PROVIDER_REGISTRY
    from lib.db.repositories.credential_repository import CredentialRepository
    from server.services import workflow_planner
    from server.tool_runtime import (
        Services,
        ToolRequest,
        CallerContext,
        ProjectScope,
        ToolOutcome,
        ToolProblem,
        list_projects,
        create_project,
        upload_source,
        get_generation_batch,
        cancel_generation_batch,
        get_project_content,
        get_episode_script,
        get_script_plan_content,
        get_workflow_plan,
        get_video_capabilities,
        list_source_files,
        get_source_text,
        CreateProjectToolRequest,
        UploadSourceRequest,
        GenerationBatchToolRequest,
        WorkflowPlanRequest,
        # —— 与远程 MCP 对齐的确定性工具（本次补齐）——
        complete_asset_inventory,
        complete_script_plan_rebuild,
        confirm_script_review,
        convert_script_plan,
        discard_draft,
        generate_episode_script,
        generate_script_plan,
        get_prompt_preview,
        list_project_files,
        open_draft,
        patch_draft,
        patch_episode_meta,
        patch_episode_script,
        patch_project,
        plan_episodes,
        promote_draft,
        read_project_file,
        rename_asset,
        reset_episode_planning,
        retry_project_migration,
        CompleteAssetInventoryRequest,
        CompleteScriptPlanRebuildRequest,
        PatchEpisodeMetaRequest,
        PatchEpisodeScriptRequest,
        PatchProjectRequest,
        PlanEpisodesRequest,
        PromptPreviewRequest,
        RenameAssetRequest,
        ResetEpisodePlanningRequest,
        ScriptPlanConversionRequest,
    )
    from server.draft_workflow import (
        DiscardDraftRequest,
        DraftLocator,
        PatchDraftRequest,
        PromoteDraftRequest,
    )
    from server.text_generation import (
        TextGenerationRequest,
        _build_reference_units_from_flat,
        _collect_narration_violations,
        _collect_reference_flat_violations,
        _commit_generated_reference_script_plan,
        _commit_single_script_plan,
        _coverage_source_scope,
        _fetch_caps_with_fallback,
        _fetch_reference_caps_with_fallback,
        _generation_baselines,
        _load_script_plan_source_with_basis,
        _normalize_for_coverage,
    )
    from lib.source_revision import SourceScope, compute_source_revision
    from lib.artifact_provenance import build_script_plan_basis
    from lib.script_models import (
        build_drama_normalized_script_model,
        merge_drama_visual_into_scenes,
    )
    from lib.speech_composition import admit_script_unit
    from lib.draft_quarantine import (
        QUARANTINE_KIND_DRAMA_SCRIPT_PLAN,
        QUARANTINE_KIND_NARRATION_SCRIPT_PLAN,
        QUARANTINE_KIND_SCRIPT_PLAN,
        quarantine_path,
    )
    from lib.episode_paths import episode_script_filename, episode_source_relpath
    from lib.reference_catalog import build_reference_catalog
    from lib.script_skeleton import rewrite_episode_prefix
    from lib.script_plan_entries import (
        SCRIPT_PLAN_REVISION_FIELD,
        plan_entries_from_document,
        plan_entry_content,
        plan_entry_revisions,
        splice_entries,
    )
    from lib import script_review as script_review_lib
except Exception as exc:  # pragma: no cover - 环境/依赖缺失
    print(
        "导入失败：缺少 ArcReel 依赖，或未在 ArcReel 项目根目录运行。\n"
        "请先执行 `uv sync` 安装依赖，并从项目根目录调用本脚本。\n"
        f"原因：{exc}",
        file=sys.stderr,
    )
    sys.exit(2)

# H3 / 参考生视频最终 Provider Prompt 预览由扩展后的 get_prompt_preview 统一提供。

# 媒体生成（submit_media_generation + 进程内 GenerationWorker）为附加功能；
# 导入失败不应影响其他只读/管理命令，故与主依赖隔离。
try:
    from server.media_tools.context import ToolContext
    from server.media_tools.storyboards import handle_generate_storyboards
    from server.media_tools.videos import handle_generate_videos
    from server.media_tools.narration_audio import handle_generate_narration_audio
    from server.media_tools.assets import handle_generate_assets, handle_list_pending_assets
    from server.media_tools.grid import handle_generate_grid
    from lib.generation_worker import GenerationWorker
    from lib.generation_queue import get_generation_queue

    _MEDIA_AVAILABLE = True
except Exception as exc:  # pragma: no cover - 媒体模块为可选
    _MEDIA_AVAILABLE = False
    print(
        f"[warn] 媒体生成模块不可用（media submit 将不可用）：{exc}",
        file=sys.stderr,
    )


# 全局输出开关：True 时所有结果以 JSON 输出。
JSON_OUTPUT: bool = False

# 生成批次的终态集合（小写匹配）。
_TERMINAL_STATUSES = {"done", "failed", "cancelled", "complete", "completed"}

# 最小样例剧本：narration + storyboard 模式（与 `projects create --content-mode
# narration --generation-mode storyboard` 配套）。`demo seed` 会把它写入项目的
# scripts/ 目录，供 `media submit --type storyboard` 直接消费。
# 结构要点（来自 lib.storyboard_sequence.get_storyboard_items / lib.script_skeleton）：
# - 分镜族数组键用 `segments`（narration）；drama 用 `scenes`、参考生视频用 `video_units`。
# - 每条需 `segment_id` + `image_prompt`（分镜图）；`video_prompt` 供后续 video 步骤复用。
MINIMAL_EPISODE_SCRIPT: Dict[str, Any] = {
    "content_mode": "narration",
    "title": "晨光小样（CLI 演示剧本）",
    "segments": [
        {
            "segment_id": "1",
            "image_prompt": (
                "清晨，一位少女站在窗边，柔和的晨光洒在侧脸，暖色调，"
                "写实插画风格，简洁构图，避免文字与水印"
            ),
            "video_prompt": "少女缓缓转头望向窗外的晨光，发丝轻轻飘动",
        },
        {
            "segment_id": "2",
            "image_prompt": (
                "木质书桌上放着一杯冒热气的茶，旁边一本翻开的书，"
                "暖色灯光，宁静氛围，避免文字与水印"
            ),
            "video_prompt": "茶杯上热气缓缓上升，光影微微流动",
        },
    ],
}


def to_dict(v: Any) -> Any:
    """将工具返回的可序列化对象递归转为原生 Python 结构。

    优先级：pydantic model_dump() -> dataclass asdict() -> dict -> list -> 原值。
    """
    if hasattr(v, "model_dump") and callable(getattr(v, "model_dump")):
        return v.model_dump()
    if is_dataclass(v):
        return asdict(v)
    if isinstance(v, dict):
        return v
    if isinstance(v, (list, tuple)):
        return [to_dict(x) for x in v]
    return v


def emit(value: Any, human: Optional[Callable[[Any], None]] = None) -> None:
    """按全局 `--json` 开关输出结果。

    - JSON 模式：美化输出 to_dict(value)。
    - 人类可读模式：优先使用 human 渲染器；否则回退为美化 JSON。
    """
    if JSON_OUTPUT:
        print(json.dumps(to_dict(value), ensure_ascii=False, indent=2, default=str))
        return
    if human is not None:
        human(value)
        return
    print(json.dumps(to_dict(value), ensure_ascii=False, indent=2, default=str))


def _require(outcome: ToolOutcome) -> Any:
    """提取工具结果值；若为错误则向 stderr 报告并以退出码 1 结束。"""
    if outcome.problem is not None:
        problem: ToolProblem = outcome.problem
        print(f"ERROR: {problem.code}: {problem.detail}", file=sys.stderr)
        sys.exit(1)
    return outcome.value


def _project_scope(project: str, pm: Any) -> ProjectScope:
    """解析项目名并校验其 project.json 存在，返回 ProjectScope。"""
    name = pm.normalize_project_name(project)
    pm.get_project_path(name)
    if not pm.project_exists(name):
        raise FileNotFoundError(f"项目 '{name}' 缺少 project.json")
    return ProjectScope(project_name=name, projects_root=pm.projects_root)


def _human_projects(value: Any) -> None:
    """projects list 的人类可读对齐表格渲染。"""
    rows = to_dict(value)
    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        print("(no projects)")
        return
    cols = ["name", "title", "content_mode", "generation_mode"]
    cells = [{c: str(r.get(c, "")) for c in cols} for r in rows]
    widths = {c: max(len(c), *(len(r[c]) for r in cells)) for c in cols}
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for r in cells:
        print(" | ".join(r[c].ljust(widths[c]) for c in cols))


def _print_batch_status(d: Dict[str, Any], batch_id: str) -> None:
    """batch get --wait 非 JSON 模式下每轮打印的精简状态行。"""
    status = d.get("status", "?")
    done = d.get("done", False)
    parts = [f"batch {batch_id}", f"status={status}", f"done={done}"]
    for key in ("progress", "percent", "message", "error"):
        if key in d and d[key] not in (None, ""):
            parts.append(f"{key}={d[key]}")
    print(" | ".join(parts))


async def _cmd_batch_get(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """batch get：单次查询或（带 --wait）轮询至终态。"""
    scope = _project_scope(args.project, pm)
    batch_id = args.batch_id
    while True:
        outcome = await get_generation_batch(
            ToolRequest(GenerationBatchToolRequest(batch_id=batch_id)),
            scope,
            caller,
            services,
        )
        value = _require(outcome)
        d = to_dict(value)
        status = d.get("status")
        done = d.get("done", False)

        if JSON_OUTPUT:
            print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
        elif args.wait:
            _print_batch_status(d, batch_id)
        else:
            print(json.dumps(d, ensure_ascii=False, indent=2, default=str))

        if not args.wait:
            break

        terminal = done is True or (
            isinstance(status, str) and status.lower() in _TERMINAL_STATUSES
        )
        if terminal:
            break

        interval = d.get("poll_after_seconds") or args.interval
        try:
            await asyncio.sleep(float(interval))
        except (TypeError, ValueError):
            await asyncio.sleep(float(args.interval))


# ---------------------------------------------------------------------------
# media submit：复用 handle_generate_*（preflight + TaskSpec 编排）提交，
# 按 --wait 选择性启动进程内 GenerationWorker 真出片并轮询到终态。
# ---------------------------------------------------------------------------

_MEDIA_HANDLERS = {}
if _MEDIA_AVAILABLE:
    _MEDIA_HANDLERS = {
        "storyboard": handle_generate_storyboards,
        "video": handle_generate_videos,
        "narration_audio": handle_generate_narration_audio,
        "assets": handle_generate_assets,
        "grid": handle_generate_grid,
    }


def _split_ids(raw: Optional[str]) -> Optional[List[str]]:
    """把逗号分隔的字符串拆成列表；空或 None 返回 None。"""
    if not raw:
        return None
    return [s.strip() for s in raw.split(",") if s.strip()]


def _build_media_args(args: argparse.Namespace) -> Dict[str, Any]:
    """根据 --type 把扁平 CLI 参数组装成对应 handle_generate_* 的 args dict。"""
    t = args.type
    if t == "storyboard":
        return {"script": Path(args.script).name, "segment_ids": _split_ids(args.segment_ids)}
    if t == "narration_audio":
        return {"script": Path(args.script).name, "segment_ids": _split_ids(args.segment_ids)}
    if t == "grid":
        return {"script": Path(args.script).name, "scene_ids": _split_ids(args.scene_ids), "list_only": False}
    if t == "assets":
        return {"type": args.asset_type, "names": _split_ids(args.asset_names), "all": args.asset_all}
    if t == "video":
        target: Dict[str, Any] = {"scope": args.video_scope}
        if args.video_scope == "episode":
            if args.episode is None:
                raise ValueError("video --video-scope=episode 时必须提供 --episode")
            target["episode"] = args.episode
        if args.video_scope in ("scene", "selected"):
            ids = _split_ids(args.video_ids)
            if not ids:
                raise ValueError("video --video-scope=scene|selected 时必须提供 --video-ids")
            target["ids"] = ids
        return {"script": Path(args.script).name, "target": target, "force": args.force}
    raise ValueError(f"未知媒体类型：{t}")


async def _cmd_media_submit(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """media submit：提交生成；--dry-run 时只展开最终视频 Provider Prompt，不入队。"""
    _project_scope(args.project, pm)
    if getattr(args, "dry_run", False):
        await _cmd_media_video_dry_run(args, pm, services, caller)
        return
    if not _MEDIA_AVAILABLE:
        print("ERROR: 媒体生成模块不可用，无法执行真实 media submit", file=sys.stderr)
        sys.exit(1)
    handler = _MEDIA_HANDLERS[args.type]
    handler_args = _build_media_args(args)

    # ToolContext 复用 CLI 的 caller（source="mcp"）；queue 与 worker 同一队列。
    ctx = ToolContext(
        project_name=pm.normalize_project_name(args.project),
        projects_root=pm.projects_root,
        pm=pm,
        caller=caller,
        queue=services.queue,
    )

    async def _enqueue() -> Any:
        return _require(await handler(ctx, handler_args))

    await _submit_generation(args, pm, services, caller, _enqueue)


# ---------------------------------------------------------------------------
# demo seed：写入最小样例剧本，让项目可直接被 media submit 消费。
# config：provider 配置落库（ConfigService）+ 一键图像 provider 配置 + 就绪校验。
# ---------------------------------------------------------------------------

async def _cmd_demo_seed(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """demo seed：把 MINIMAL_EPISODE_SCRIPT 写入项目的 scripts/ 目录。"""
    _project_scope(args.project, pm)
    filename = args.script_name
    try:
        path = pm.save_script(args.project, MINIMAL_EPISODE_SCRIPT, filename, validate=False)
        # 必须把集数信息同步进 project.json，否则生成工具会拒绝：
        # "script <f> is not bound to episode N in project.json"。
        pm.sync_episode_from_script(args.project, filename)
    except Exception as exc:
        print(f"ERROR: 写入样例剧本失败：{exc}", file=sys.stderr)
        sys.exit(1)
    print(f"已写入样例剧本：{path}（已登记 episode 1）")
    print("该剧本为 narration + storyboard 结构（2 个分镜段）。")
    print("下一步（需先配置一个图像 provider，否则 worker 认领任务后会失败）：")
    print(f"  arcreel.bat config setup-image --provider-id <id> --api-key <KEY>")
    print(f"  arcreel.bat config verify --project {args.project}")
    print(
        f"  arcreel.bat media submit --type storyboard --project {args.project}"
        f" --script {filename} --wait"
    )


async def _cmd_config_set(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """config set：通用 provider 配置键值写入（落 DB）。"""
    async with async_session_factory() as session:
        svc = ConfigService(session)
        try:
            await svc.set_provider_config(args.provider_id, args.key, args.value, flush=True)
        except ValueError as exc:
            print(f"ERROR: 配置写入被拒：{exc}", file=sys.stderr)
            sys.exit(1)
    print(f"OK: provider={args.provider_id} {args.key} 已写入（已 flush）")


async def _cmd_config_setup_image(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """config setup-image：一键配置图像 provider 并激活凭据（落 DB）。

    ArcReel 的 provider「就绪」依赖**生效凭据**（ProviderCredential 表，is_active=True），
    仅写 provider_config 表不足以让 worker 选中该 provider。本命令：
      1) 创建一条 ProviderCredential（api_key / base_url）并强制激活 -> 状态变 READY；
      2) 可选 model 写入 provider_config 表（非密钥字段）。
    api_key 优先读 --api-key，缺失时回退环境变量 ARCREEL_API_KEY，避免密钥留在 shell 历史。
    """
    if args.provider_id not in PROVIDER_REGISTRY:
        print(f"ERROR: 未知 provider id：{args.provider_id}", file=sys.stderr)
        sys.exit(1)
    api_key = args.api_key or os.environ.get("ARCREEL_API_KEY")
    if not api_key:
        print(
            "ERROR: 未提供 api_key。请用 --api-key <KEY> 或先设置环境变量 ARCREEL_API_KEY。",
            file=sys.stderr,
        )
        sys.exit(1)

    # 1) 创建并激活凭据（首条自动激活；非首条也强制激活本凭据）
    async with async_session_factory() as session:
        cred_repo = CredentialRepository(session)
        try:
            cred = await cred_repo.create(
                provider=args.provider_id,
                name=f"cli-{args.provider_id}",
                api_key=api_key,
                base_url=args.base_url,
            )
            await cred_repo.activate(cred.id, args.provider_id)
            await session.commit()
        except ValueError as exc:
            await session.rollback()
            print(f"ERROR: 凭据创建被拒：{exc}", file=sys.stderr)
            sys.exit(1)

    # 2) 可选 model 写入 provider_config（非密钥字段）
    if args.model:
        async with async_session_factory() as session:
            svc = ConfigService(session)
            try:
                await svc.set_provider_config(args.provider_id, "model", args.model, flush=True)
            except ValueError as exc:
                print(f"ERROR: model 配置写入被拒：{exc}", file=sys.stderr)
                sys.exit(1)

    print(f"OK: 图像 provider={args.provider_id} 已创建并激活凭据（api_key 已落库）")
    if args.model:
        print(f"    已写入可选 model={args.model}")
    print("已知 provider id 示例：gemini-aistudio / ark / openai / dashscope / minimax / grok / vidu / agnes / kling")
    print("配置完成后运行 `config verify` 确认状态变为 READY。")


async def _cmd_config_verify(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """config verify：列出 provider 就绪状态，并对（可选）项目验证图像后端可被解析。

    - 仅配置一个图像 provider 时，worker 会自动推断选用它（resolve_image_backend 的
      payload > 项目 > 全局 > 自动推断 链路的末端）。
    """
    async with async_session_factory() as session:
        svc = ConfigService(session)
        statuses = await svc.get_all_providers_status()

    ready_image = [st.name for st in statuses if st.status == "ready" and "image" in st.media_types]
    if JSON_OUTPUT:
        emit([to_dict(st) for st in statuses])
        return

    print("Provider 状态：")
    for st in statuses:
        tag = "READY" if st.status == "ready" else "未配置"
        print(f"  - {st.name} [{st.display_name}] {tag} media={st.media_types}")
    print()
    if ready_image:
        print(f"已就绪且支持 image 的 provider（可出分镜图）：{ready_image}")
    else:
        print("未检测到已就绪的图像 provider。请先 `config setup-image` 配置一个 api_key。")
        print("配置完成后再次运行 `config verify` 确认状态变为 READY。")

    if args.project:
        scope = _project_scope(args.project, pm)
        project_data = await asyncio.to_thread(pm.load_project_readonly, args.project)
        try:
            resolved = await services.capabilities.resolve_image_backend(
                project_data, None, generation_type="t2i"
            )
            print(
                f"项目 {args.project} 图像后端将选用："
                f"provider={resolved.provider_id} model={resolved.model_id}"
            )
        except Exception as exc:
            print(
                f"项目图像后端解析失败（可能尚无就绪的图像 provider）：{exc}",
                file=sys.stderr,
            )


# ---------------------------------------------------------------------------
# 与远程 MCP 对齐的命令（本次补齐）：workflow / script-plan / episode-script /
# draft / projects patch / file / media pending-assets。
# 均为 server.tool_runtime 确定性工具的薄封装：构造 Request -> 调用 -> emit。
# ---------------------------------------------------------------------------


def _json_arg(raw: Optional[str], default: Any = None) -> Any:
    """解析命令行传入的 JSON 字符串；空则返回 default。"""
    if raw is None or raw == "":
        return default
    return json.loads(raw)


def _batch_id_of(value: Any) -> Optional[str]:
    """从生成结果中提取 batch_id（兼容直接 batch 对象与 {generation_batch: {...}}）。"""
    d = to_dict(value)
    if not isinstance(d, dict):
        return None
    batch_id = d.get("batch_id")
    if not batch_id and isinstance(d.get("generation_batch"), dict):
        batch_id = d["generation_batch"].get("batch_id")
    return batch_id


async def _submit_generation(
    args: argparse.Namespace,
    pm: Any,
    services: Services,
    caller: CallerContext,
    submit: Callable[[], Awaitable[Any]],
) -> None:
    """统一的生成提交：按需先启动进程内 worker（入队要求 worker 在线），再执行 submit。

    关键顺序：mcp 来源的入队会校验 ``is_worker_online``（DB 里的 worker lease），
    因此必须**先起 worker 并等其注册 lease，再入队**，否则报 ``queue worker is offline``。
    - 需要 worker：``_MEDIA_AVAILABLE`` 且非 ``--no-worker``。
    - ``--no-worker`` / 媒体模块不可用：直接入队，依赖外部常驻 worker。
    入队后按 ``--wait`` 决定是否轮询到终态；结束时停掉进程内 worker。
    """
    use_worker = _MEDIA_AVAILABLE and not getattr(args, "no_worker", False)
    worker = None
    if use_worker:
        worker = GenerationWorker(queue=services.queue)
        get_generation_queue().set_worker_cancel_callback(worker.request_cancel)
        await worker.start()
        # worker 的 lease 由 _run_loop 首轮异步注册；等它落库（最多约 5s）。
        for _ in range(50):
            try:
                if await services.queue.is_worker_online(name=worker.lease_name):
                    break
            except Exception:
                break
            await asyncio.sleep(0.1)
    try:
        value = await submit()
        batch_id = _batch_id_of(value)
        if not batch_id:
            emit(value)
            return
        print(f"已入队 batch={batch_id}")
        if not getattr(args, "wait", False):
            print(
                "（未指定 --wait：已入队，退出。可 `batch get --batch-id <id> --wait` 轮询，"
                "或加 --wait 由进程内 worker 消费出片）",
                file=sys.stderr,
            )
            return
        if worker is None:
            print("（未启动进程内 worker，仅轮询状态；需外部 worker 消费）", file=sys.stderr)
        args.batch_id = batch_id
        await _cmd_batch_get(args, pm, services, caller)
    finally:
        if worker is not None:
            await worker.stop()
            get_generation_queue().set_worker_cancel_callback(None)


async def _cmd_workflow_asset_inventory(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """workflow asset-inventory：提交资产盘点（对齐 complete_asset_inventory）。

    两条离线便利，都不改服务端语义：

    - ``--revision`` 缺省时按当前源文现算（等价「先查 workflow get 取 source_revision 再提交」），
      显式给出时仍走原来的冲突保护；
    - ``--entries-file`` 从 JSON 文件读盘点条目——省掉在 CMD 里转义嵌套引号的痛苦（与
      ``script-plan seed --units-file`` 同一模式）。条目形如
      ``{"characters": {"角色名": {"description": "一句话外貌/身份"}}}``。

    entries 由调用方（外部 Agent）提供，本就是零 LLM 路径；省略即提交空盘点。
    """
    if args.entries_file:
        try:
            entries = json.loads(Path(args.entries_file).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"ERROR: --entries-file 读取失败：{exc}", file=sys.stderr)
            sys.exit(1)
    else:
        entries = _json_arg(args.entries_json)

    project_name = pm.normalize_project_name(args.project)
    revision = args.revision
    if not revision:
        installed_scope = SourceScope(kind=args.scope_kind, files=_split_ids(args.files) or [])
        computed = compute_source_revision(
            pm.get_project_path(project_name),
            pm.load_project_readonly(project_name),
            installed_scope,
        )
        if computed.revision is None:
            print("ERROR: 无法计算当前 source revision：", file=sys.stderr)
            for blocker in computed.blockers:
                print(f"  - {blocker.path}: {blocker.reason}", file=sys.stderr)
            sys.exit(1)
        revision = computed.revision

    scope = _project_scope(args.project, pm)
    req = CompleteAssetInventoryRequest(
        scope=SourceScope(kind=args.scope_kind, files=_split_ids(args.files) or []),
        expected_source_revision=revision,
        entries=entries,
    )
    value = _require(await complete_asset_inventory(ToolRequest(req), scope, caller, services))
    emit(value)


async def _cmd_workflow_plan_episodes(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """workflow plan-episodes：LLM 规划分集（对齐 plan_episodes）。"""
    scope = _project_scope(args.project, pm)
    req = PlanEpisodesRequest(instructions=args.instructions)

    async def _enqueue() -> Any:
        return _require(await plan_episodes(ToolRequest(req), scope, caller, services))

    await _submit_generation(args, pm, services, caller, _enqueue)


async def _cmd_workflow_reset_planning(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """workflow reset-planning：重置分集规划（对齐 reset_episode_planning）。"""
    scope = _project_scope(args.project, pm)
    req = ResetEpisodePlanningRequest(
        from_episode=args.from_episode, confirm_consumed=args.confirm_consumed
    )
    value = _require(await reset_episode_planning(ToolRequest(req), scope, caller, services))
    emit(value)


async def _cmd_workflow_retry_migration(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """workflow retry-migration：重试项目数据迁移（对齐 retry_project_migration）。"""
    scope = _project_scope(args.project, pm)
    value = _require(await retry_project_migration(ToolRequest(None), scope, caller, services))
    emit(value)


async def _cmd_script_plan_generate(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """script-plan generate：生成剧本规划（对齐 generate_script_plan）。"""
    scope = _project_scope(args.project, pm)
    req = TextGenerationRequest(
        episode=args.episode,
        source=args.source,
        instructions=args.instructions,
        dry_run=args.dry_run,
        scope=args.scope,
        entry_ids=tuple(_split_ids(args.entry_ids) or ()),
    )
    if args.dry_run:
        emit(_require(await generate_script_plan(ToolRequest(req), scope, caller, services)))
        return

    async def _enqueue() -> Any:
        return _require(await generate_script_plan(ToolRequest(req), scope, caller, services))

    await _submit_generation(args, pm, services, caller, _enqueue)


async def _cmd_script_plan_confirm(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """script-plan confirm：确认剧本规划评审门（对齐 confirm_script_review）。"""
    scope = _project_scope(args.project, pm)
    value = _require(
        await confirm_script_review(ToolRequest(args.episode), scope, caller, services)
    )
    emit(value)


async def _cmd_script_plan_convert(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """script-plan convert：剧本规划机械转为正式剧本（对齐 convert_script_plan）。"""
    scope = _project_scope(args.project, pm)
    req = ScriptPlanConversionRequest(
        episode=args.episode, entry_ids=tuple(_split_ids(args.entry_ids) or ())
    )
    value = _require(await convert_script_plan(ToolRequest(req), scope, caller, services))
    emit(value)


async def _cmd_script_plan_rebuild_complete(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """script-plan rebuild-complete：完成过期规划重建（对齐 complete_script_plan_rebuild）。"""
    scope = _project_scope(args.project, pm)
    revision = None if args.revision in (None, "", "-") else args.revision
    req = CompleteScriptPlanRebuildRequest(
        episode=args.episode, expected_stale_script_plan_revision=revision
    )
    value = _require(
        await complete_script_plan_rebuild(ToolRequest(req), scope, caller, services)
    )
    emit(value)


# ---------------------------------------------------------------------------
# script-plan seed：离线（无需 LLM）按原文切分出 narration 结构化 script_plan。
# ---------------------------------------------------------------------------

#: 句末标点，作为 narration 分镜的天然切分点（CJK 与半角并列）。
_SENTENCE_END = "。！？!?"


def _split_narration_sentences(text: str) -> List[str]:
    """按句末标点把（已归一化的）原文切成连续片段。

    逐字符游标切分、标点归属前一段，因此**各片段按序拼接后与原文逐字相等**——
    这正是 ``_covers_source_verbatim`` 的覆盖要求，任何 re.split / strip 都会破坏它。
    """
    parts: List[str] = []
    buf: List[str] = []
    for ch in text:
        buf.append(ch)
        if ch in _SENTENCE_END:
            parts.append("".join(buf))
            buf = []
    if buf:
        parts.append("".join(buf))
    return [part for part in parts if part.strip()]


def _group_narration_parts(parts: List[str], groups: int) -> List[str]:
    """把相邻片段合并成 ``groups`` 组（按字数尽量均衡），保持原序与逐字完整。

    ``groups <= 1`` 时全部并成一段；``groups >= len(parts)`` 时维持一句一段。
    """
    if not parts:
        return []
    if groups <= 1:
        return ["".join(parts)]
    if groups >= len(parts):
        return list(parts)
    total = sum(len(part) for part in parts)
    target = total / groups
    out: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for index, part in enumerate(parts):
        cur.append(part)
        cur_len += len(part)
        left = len(parts) - index - 1
        groups_left = groups - len(out)
        # 已攒够目标字数，且剩余片段仍够后面每组至少一个 → 收一组
        if groups_left > 1 and cur_len >= target and left >= groups_left - 1:
            out.append("".join(cur))
            cur = []
            cur_len = 0
    if cur:
        out.append("".join(cur))
    return out


def _resolve_seed_source(
    args: argparse.Namespace, project_path: Path, episode: int
) -> tuple[str, str, Optional[str]]:
    """script-plan seed 的源文（narration / drama 共用）：本集派生源文，缺失时按项目 source/ 补建。

    返回 ``(source_rel, text, note)``——``note`` 非空表示发生过补建。planner 把 script_plan 判为
    ``current`` 的前提是本集派生源文在场（basis 由它现算），故这里顺手补建，等价分集规划的派生动作。
    缺可用源文时打印错误并退出。
    """
    source_rel = episode_source_relpath(episode)
    source_path = project_path / source_rel
    if source_path.is_file():
        text = source_path.read_text(encoding="utf-8")
        if not text.strip():
            print(f"ERROR: 源文为空：{source_rel}", file=sys.stderr)
            sys.exit(1)
        return source_rel, text, None

    # 本集派生源文缺失（未跑过 plan-episodes）：从项目 source/ 的已上传源文补建。
    src_dir = project_path / "source"
    candidate: Optional[Path] = None
    if args.source:
        candidate = src_dir / Path(args.source).name
    else:
        files = sorted(
            p
            for p in src_dir.glob("*.txt")
            if not p.name.startswith("_") and not p.name.startswith("episode_")
        )
        preferred = [p for p in files if p.name == "source.txt"]
        candidate = preferred[0] if preferred else (files[0] if len(files) == 1 else None)
    if candidate is None or not candidate.is_file():
        print(
            f"ERROR: 未找到本集派生源文 {source_rel}，也无法从 source/ 推断唯一源文。"
            f"请先跑 `workflow plan-episodes`，或用 --source 指定源文件名。",
            file=sys.stderr,
        )
        sys.exit(1)
    text = candidate.read_text(encoding="utf-8")
    if not text.strip():
        print(f"ERROR: 源文为空：source/{candidate.name}", file=sys.stderr)
        sys.exit(1)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(text, encoding="utf-8")
    return source_rel, text, f"已补建本集派生源文 {source_rel}（取自 source/{candidate.name}）"


async def _resolve_seed_durations(
    args: argparse.Namespace,
    services: Services,
    project: Dict[str, Any],
    episode: int,
) -> tuple[int, List[int], Optional[int]]:
    """script-plan seed 的时长档位与本次落盘用时（narration / drama 共用）。

    返回 ``(duration, durations, default_duration)``：档位取自与拆分 / 晋升侧同一个 helper
    （无可用 provider 时软回退到默认档）；``--duration`` 越界即报错退出——时长越界的
    script_plan 会被官方校验 / prompt_authoring 拒绝。
    """
    default_duration, durations = await _fetch_caps_with_fallback(
        project, episode, config_resolver=services.capabilities
    )
    if not durations:
        print("ERROR: 无法解析时长档位，无法生成合法 script_plan。", file=sys.stderr)
        sys.exit(1)
    duration = args.duration if args.duration is not None else (default_duration or durations[0])
    if duration not in durations:
        print(
            f"ERROR: --duration {duration} 不在当前可用档位 {durations}"
            f"（default={default_duration}）内。",
            file=sys.stderr,
        )
        sys.exit(1)
    return int(duration), durations, default_duration


async def _cmd_script_plan_seed(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """script-plan seed：离线（不调 LLM）为 narration 项目按原文切分出结构化 script_plan。

    复用官方拆分侧的同一条校验与落盘出口，而不是自己写文件：
    - 内容须过 ``_collect_narration_violations``（segment_id 格式 ``E{集}S##`` 且唯一、
      ``novel_text`` 按序逐字完整覆盖源文、时长落在当前档位内、资产名已登记）；
    - 经 ``_commit_single_script_plan`` 落盘 ``drafts/episode_N/script_plan_segments.json``
      并登记 basis 指纹——planner 正是拿 ``source/episode_N.txt`` 现算 basis 与清单里的
      摘要比对，据此把 script_plan 判为 ``current``。

    因此 planner 认这份 script_plan 的前提是**本集派生源文存在**；缺失时会先从项目
    ``source/`` 的已上传源文补建 ``source/episode_N.txt``（等价分集规划的派生动作）。
    """
    name = pm.normalize_project_name(args.project)
    _project_scope(args.project, pm)
    project_path = pm.get_project_path(name)
    project = pm.load_project_readonly(name)

    if project.get("generation_mode") == "reference_video":
        await _seed_reference_units(args, pm, services, name, project_path, project)
        return
    if project.get("content_mode") == "drama":
        await _seed_drama_scenes(args, pm, services, name, project_path, project)
        return
    if project.get("content_mode") != "narration":
        print(
            "ERROR: script-plan seed 支持 narration / drama（非 reference_video）与 reference_video "
            f"两类项目；当前 content_mode={project.get('content_mode')!r}、"
            f"generation_mode={project.get('generation_mode')!r}。",
            file=sys.stderr,
        )
        sys.exit(1)

    episode = args.episode
    source_rel, text, source_note = _resolve_seed_source(args, project_path, episode)

    duration, durations, default_duration = await _resolve_seed_durations(
        args, services, project, episode
    )

    normalized = _normalize_for_coverage(text)
    sentences = _split_narration_sentences(normalized)
    if not sentences:
        print("ERROR: 源文切分后无有效片段。", file=sys.stderr)
        sys.exit(1)
    parts = _group_narration_parts(sentences, args.segments) if args.segments else sentences

    segments = [
        {
            "segment_id": f"E{episode}S{index:02d}",
            "novel_text": part,
            "duration_seconds": duration,
            "segment_break": index > 1,
            "characters_in_segment": [],
            "scenes": [],
            "props": [],
        }
        for index, part in enumerate(parts, start=1)
    ]
    content = {"episode": episode, "source": source_rel, "segments": segments}

    violations = _collect_narration_violations(
        segments,
        episode=episode,
        supported_durations=durations,
        catalog=build_reference_catalog(project),
        novel_text=text,
        source_scope=_coverage_source_scope(source_rel, episode=episode),
    )
    if violations:
        print("ERROR: 生成的 script_plan 未通过官方校验，未落盘：", file=sys.stderr)
        for violation in violations:+            print(f"  - {violation}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        emit(
            {
                "source": source_rel,
                "duration_seconds": duration,
                "supported_durations": durations,
                "default_duration": default_duration,
                "content": content,
            }
        )
        return

    plan_path = script_review_lib.script_plan_path(project_path, project, episode)
    if plan_path is None:
        print("ERROR: 该项目变体不走结构化 script_plan。", file=sys.stderr)
        sys.exit(1)
    basis = build_script_plan_basis(text, episode=episode, project=project)
    draft_path = quarantine_path(project_path, episode, QUARANTINE_KIND_NARRATION_SCRIPT_PLAN)
    _draft_baseline, formal_baseline = _generation_baselines(draft_path, plan_path)
    try:
        _commit_single_script_plan(
            project_path,
            episode,
            plan_path,
            QUARANTINE_KIND_NARRATION_SCRIPT_PLAN,
            content,
            formal_baseline,
            basis,
        )
    except Exception as exc:
        print(f"ERROR: script_plan 落盘失败：{exc}", file=sys.stderr)
        sys.exit(1)

    total_chars = sum(len(segment["novel_text"]) for segment in segments)
    total_seconds = sum(segment["duration_seconds"] for segment in segments)
    if source_note:
        print(source_note)
    print(f"已写入结构化 script_plan：{plan_path}")
    print(
        f"统计：{len(segments)} 个分镜 / {total_chars} 字，"
        f"每段 {duration} 秒（档位 {durations}），合计 {total_seconds} 秒"
    )
    print("下一步：")
    print(f"  arcreel.bat --json workflow get --project {args.project}")
    print(f"  arcreel.bat script-plan confirm --project {args.project} --episode {episode}")


# ---------------------------------------------------------------------------
# script-plan seed（drama 变体）
# ---------------------------------------------------------------------------

#: drama 台词行里的引号内容：``“…”`` / ``「…」`` / ``"…"``。
_DRAMA_QUOTED_RE = re.compile(r"[“「\"]([^”」\"\n]+)[”」\"]")
#: drama 行首说话人前缀：``角色：``，允许 ``**角色**`` 与 ``角色（表演提示）：`` 两种写法。
#: 字符类排除括号 / 书名号 / 空白 / 冒号——场景标题（``【场景一：…】``）与纯提示行（``（…）``）
#: 因此不会被当成说话人。
_DRAMA_SPEAKER_PREFIX_RE = re.compile(
    r"^\s*(?:\*\*)?([^\s：:【】〔〕《》\[\]{}（）()]{1,20}?)(?:\*\*)?"
    r"\s*(?:[（(][^）)]*[）)])?\s*[：:]\s*(.*)$"
)
#: 说话人前缀行里的表演提示（``角色（擦拭书架）：台词`` 的括号部分），进画面描述。
_DRAMA_HINT_RE = re.compile(r"[（(]([^）)]+)[）)]")
#: 这些「说话人」实为画外音通道，不产出 dialogue（否则下游会给它们编派角色音色）。
_DRAMA_VOICEOVER_SPEAKERS = frozenset(
    {"旁白", "画外音", "内心独白", "独白", "解说", "字幕", "narrator", "voiceover", "vo"}
)


def _split_drama_blocks(text: str) -> List[List[str]]:
    """把源文切成 drama 分镜块。

    两级边界：

    - **硬边界**——动作行（``△``）、场景标题行（``【…】``）与元信息行（集标题 / 分隔线等）：
      它们天然是镜头起点，故切出一镜；``△`` 行自身是画面内容、进正文，场景标题与元信息行不进。
    - **软边界**——空行：只切段落，不切镜头（剧本里空行多为排版）。

    全文切不出两个以上硬边界时退化为「一段一镜」（纯小说式源文没有 ``△`` / ``【】``，靠空行
    分段才是它的自然粒度）；两者都不足时用 ``--segments`` 指定目标镜数。
    """
    hard: List[List[str]] = []
    paragraphs: List[List[str]] = []
    cur: List[str] = []
    para: List[str] = []

    def _close_hard() -> None:
        nonlocal cur
        if cur and any(line.strip() for line in cur):
            hard.append(cur)
        cur = []

    def _close_para() -> None:
        nonlocal para
        if para and any(line.strip() for line in para):
            paragraphs.append(para)
        para = []

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            _close_para()
            continue
        if _is_meta_line(line):
            _close_hard()
            _close_para()
            continue
        if stripped.startswith("△") or (stripped.startswith("【") and stripped.endswith("】")):
            # 动作行自身是画面内容、场景标题承载时空信息，两者都作为新镜的正文首行。
            _close_hard()
            _close_para()
            cur.append(line)
            para.append(line)
            continue
        cur.append(line)
        para.append(line)
    _close_hard()
    _close_para()
    # 合并「仅含场景标题」的孤立块到下一镜：避免「【场景N】」标题行紧接「△」动作行时被
    # 切成两个空镜（标题镜 + 动作镜）。标题行作为下一镜的起始行（slugline），与 demo-drama2
    # 那种「标题 + 括号动作 + 台词」同属一块的写法保持一致。
    merged: List[List[str]] = []
    for idx, block in enumerate(hard):
        title_only = (
            len(block) == 1
            and block[0].strip().startswith("【")
            and block[0].strip().endswith("】")
        )
        if title_only and idx + 1 < len(hard):
            hard[idx + 1].insert(0, block[0])
            continue
        merged.append(block)
    hard = merged
    if len(hard) > 1:
        return hard
    return paragraphs or hard


def _group_drama_blocks(blocks: List[List[str]], groups: Optional[int]) -> List[List[str]]:
    """把相邻分镜块合并成 ``groups`` 组（按字数尽量均衡），保持原序与逐字完整。

    ``groups`` 缺省时维持动作行、场景标题与空行切出的自然边界（一块一镜）；``groups <= 1``
    把全部并成一镜；``>= 块数`` 时同缺省。
    """
    if not blocks:
        return []
    if groups is None or groups >= len(blocks):
        return [list(block) for block in blocks]
    if groups <= 1:
        return [[line for block in blocks for line in block]]
    total = sum(len(line) for block in blocks for line in block)
    target = total / groups
    out: List[List[str]] = []
    cur: List[str] = []
    cur_len = 0
    for index, block in enumerate(blocks):
        cur.extend(block)
        cur_len += sum(len(line) for line in block)
        left = len(blocks) - index - 1
        groups_left = groups - len(out)
        if groups_left > 1 and cur_len >= target and left >= groups_left - 1:
            out.append(cur)
            cur = []
            cur_len = 0
    if cur:
        out.append(cur)
    return out


def _drama_utterances(lines: List[str]) -> List[Dict[str, Any]]:
    """从一镜的正文行里提取有序口播（``dialogue`` 带说话人 / ``voiceover`` 无说话人）。

    台词来源按剧本约定，从高置信到低置信：

    1. ``**«««角色»»»**`` 标记行 + 紧接着的 ``说："…"`` —— 与参考生视频同款写法，恒为台词；
    2. 行首 ``角色：``（含 ``角色（表演提示）：``）后的内容——剧本里这就是台词；内容带引号时
       只取引号内文本，否则整段冒号后文本即台词；冒号前是「旁白 / 画外音」一类通道名时改判
       画外音（不给它们编派角色）；
    3. 行内只有引号内容——无说话人画外音。

    既无引号也无说话人前缀的叙述行不进 utterances：drama 里那是画面内容，不是口播。
    """
    utterances: List[Dict[str, Any]] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        mark = _SPEAKER_MARK_RE.search(stripped)
        if mark is not None:
            speaker = mark.group(1).strip()
            utterance_text = ""
            if index + 1 < len(lines):
                utterance_match = _UTTERANCE_RE.match(lines[index + 1].strip())
                if utterance_match is not None:
                    utterance_text = utterance_match.group(1).strip()
            if utterance_text:
                utterances.append({"kind": "dialogue", "speaker": speaker, "text": utterance_text})
                index += 2
            else:
                index += 1
            continue

        prefix = _DRAMA_SPEAKER_PREFIX_RE.match(stripped)
        if prefix is not None:
            speaker = prefix.group(1).strip()
            body = prefix.group(2).strip()
            quoted = [match.strip() for match in _DRAMA_QUOTED_RE.findall(body) if match.strip()]
            spoken = quoted or ([body] if body else [])
            for text in spoken:
                if speaker.casefold() in _DRAMA_VOICEOVER_SPEAKERS:
                    utterances.append({"kind": "voiceover", "speaker": None, "text": text})
                else:
                    utterances.append({"kind": "dialogue", "speaker": speaker, "text": text})
            index += 1
            continue

        for text in (match.strip() for match in _DRAMA_QUOTED_RE.findall(stripped)):
            if text:
                utterances.append({"kind": "voiceover", "speaker": None, "text": text})
        index += 1
    return utterances


def _drama_scene_description(lines: List[str]) -> str:
    """分镜视觉描述：剔掉台词后剩下的画面文字（无剩余时回落到整块原文）。

    ``scene_description`` 只承载画面（角色动作 / 神态 / 环境 / 光影），不内嵌口播——与
    ``DramaSceneContent`` 的字段分工一致；prompt_authoring 拿它当画面基底。因此：

    - 无说话人前缀的行（场景标题、动作行、环境描写）整行进描述，行内引号台词先剥掉；
    - 有说话人前缀的行，其余部分已由 ``_drama_utterances`` 收作台词，描述只取其中的
      **表演提示**（``角色（提示）：台词`` 的括号部分）——否则同一句话会在画面与口播里各出现一次。
    """
    parts: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or _SPEAKER_MARK_RE.search(stripped):
            continue
        prefix = _DRAMA_SPEAKER_PREFIX_RE.match(stripped)
        if prefix is not None:
            hint = _DRAMA_HINT_RE.search(stripped)
            if hint is not None and hint.group(1).strip():
                parts.append(hint.group(0).strip())
            continue
        remainder = _DRAMA_QUOTED_RE.sub("", stripped).strip()
        parts.append(remainder or stripped)
    description = " ".join(parts).strip()
    if description:
        return description
    return " ".join(line.strip() for line in lines if line.strip())


def _table_names(project: Dict[str, Any], key: str) -> List[str]:
    """项目某张资产表（characters / scenes / props）已登记的名称列表。"""
    table = project.get(key)
    return [str(name) for name in table.keys()] if isinstance(table, dict) else []


async def _seed_drama_scenes(
    args: argparse.Namespace,
    pm: Any,
    services: Services,
    name: str,
    project_path: Path,
    project: Dict[str, Any],
) -> None:
    """script-plan seed（drama）：离线写 ``script_plan_normalized_script.json``。

    剧情演绎的 script_plan 正规产出走 ``generate_script_plan``（项目文本模型）。本命令让
    **外部 Agent 承担同一份内容生成**，只复用官方的结构契约与落盘出口，因而全程不调 LLM：

    - 结构过 ``build_drama_normalized_script_model(durations)``（与生成侧 response_schema
      同一份动态模型：时长须落在当前档位、必填字段齐备）；
    - 逐分镜过 ``admit_script_unit("scenes", …)``：台词量念不完 / 口播结构不合规的分镜只被
      打上 ``needs_replan`` 标记（与生成侧同口径），不阻塞落盘；
    - ``_commit_single_script_plan`` 在正式文件锁内落盘并登记 basis——planner 正是拿它判
      ``script_plan`` 是否为 ``current``。

    切分以动作行（``△``）与空行为界，可用 ``--scenes`` 合并成目标镜数；口播按剧本约定提取
    台词（``«««角色»»»`` + ``说："…"`` / 已登记角色的 ``角色：``引号内容），其余叙述进
    ``scene_description``。想要更好的分镜，可用 ``script-plan generate``（有 LLM 时）重出。
    """
    episode = args.episode
    source_rel, text, source_note = _resolve_seed_source(args, project_path, episode)
    duration, durations, _default_duration = await _resolve_seed_durations(
        args, services, project, episode
    )

    characters = _table_names(project, "characters")
    scene_names = _table_names(project, "scenes")
    prop_names = _table_names(project, "props")

    groups = _group_drama_blocks(_split_drama_blocks(text), args.segments)
    if not groups:
        print("ERROR: 源文切分后无有效分镜。", file=sys.stderr)
        sys.exit(1)

    scenes: List[Dict[str, Any]] = []
    for index, lines in enumerate(groups, start=1):
        block_text = "\n".join(lines)
        description = _drama_scene_description(lines)
        utterances = _drama_utterances(lines)
        spoken_chars = sum(len(item["text"]) for item in utterances)
        scenes.append(
            {
                "scene_id": f"E{episode}S{index:02d}",
                "duration_seconds": duration,
                "segment_break": index > 1,
                "characters_in_scene": sorted(
                    {item["speaker"] for item in utterances if item.get("speaker")}
                    | {name for name in characters if name and name in block_text}
                ),
                "scenes": [name for name in scene_names if name and name in block_text],
                "props": [name for name in prop_names if name and name in block_text],
                "scene_description": description,
                "utterances": utterances,
                "source_text": block_text,
                "spoken_chars": spoken_chars,
            }
        )
    if args.duration is None:
        # 单镜时长按口播量取「念得完」的最短档位：全部同档会浪费画面时间，同档也非硬要求。
        for scene in scenes:
            scene["duration_seconds"] = _pick_duration(scene.pop("spoken_chars"), durations)
    else:
        for scene in scenes:
            scene.pop("spoken_chars")

    content: Dict[str, Any] = {
        "title": args.title or f"第{episode}集",
        "scenes": scenes,
    }
    model = build_drama_normalized_script_model(durations)
    try:
        content = model.model_validate(content).model_dump()
    except Exception as exc:
        print(f"ERROR: 生成的 script_plan 未通过官方结构校验，未落盘：{exc}", file=sys.stderr)
        sys.exit(1)

    raw_scenes = content.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        print("ERROR: script_plan 结构异常：scenes 必须是非空数组。", file=sys.stderr)
        sys.exit(1)
    replan_ids: List[str] = []
    for scene in raw_scenes:
        admission = admit_script_unit("scenes", scene, ignore_marker=True)
        if admission.allowed:
            scene.pop("needs_replan", None)
        else:
            scene["needs_replan"] = True
            replan_ids.append(str(scene.get("scene_id")))

    if args.dry_run:
        emit(
            {
                "source": source_rel,
                "supported_durations": durations,
                "content": content,
            }
        )
        return

    plan_path = script_review_lib.script_plan_path(project_path, project, episode)
    if plan_path is None:
        print("ERROR: 该项目变体不走结构化 script_plan。", file=sys.stderr)
        sys.exit(1)
    basis = build_script_plan_basis(text, episode=episode, project=project)
    draft_path = quarantine_path(project_path, episode, QUARANTINE_KIND_DRAMA_SCRIPT_PLAN)
    _draft_baseline, formal_baseline = _generation_baselines(draft_path, plan_path)
    try:
        _commit_single_script_plan(
            project_path,
            episode,
            plan_path,
            QUARANTINE_KIND_DRAMA_SCRIPT_PLAN,
            content,
            formal_baseline,
            basis,
        )
    except Exception as exc:
        print(f"ERROR: script_plan 落盘失败：{exc}", file=sys.stderr)
        sys.exit(1)

    total_chars = sum(len(str(scene.get("source_text") or "")) for scene in raw_scenes)
    total_seconds = sum(int(scene.get("duration_seconds") or 0) for scene in raw_scenes)
    spoken = sum(
        len(str(item.get("text") or ""))
        for scene in raw_scenes
        for item in (scene.get("utterances") or [])
        if isinstance(item, dict)
    )
    if source_note:
        print(source_note)
    print(f"已写入 drama script_plan：{plan_path}")
    print(
        f"统计：{len(raw_scenes)} 个分镜 / 原文 {total_chars} 字 / 口播 {spoken} 字，"
        f"合计 {total_seconds} 秒（档位 {durations}）"
    )
    if replan_ids:
        print(f"注意：{len(replan_ids)} 个分镜的台词量在所选时长内念不完，已标 needs_replan：{replan_ids}")
    print("下一步：")
    print(f"  arcreel.bat --json workflow get --project {args.project}")
    print(f"  arcreel.bat script-plan confirm --project {args.project} --episode {episode}")


# ---------------------------------------------------------------------------
# script-plan seed（reference_video 变体）
# ---------------------------------------------------------------------------

#: 剧本里的说话人标记：``**«««角色»»»**（表演提示）``
_SPEAKER_MARK_RE = re.compile(r"[«]{3}\s*([^»\n]{1,40}?)\s*[»]{3}")
#: 台词行：``说："……"`` 或 ``说：“……”``
_UTTERANCE_RE = re.compile(r"^\s*说\s*[：:]\s*[\"“](.+?)[\"”]\s*$")
#: 元信息行前缀（标题 / 引用块 / 表格 / 分隔线），不参与 unit 切分
_META_LINE_PREFIXES = ("#", ">", "|", "---", "***")
#: 中文口播语速保守估计（字/秒），用于给 unit 选「念得完」的最短档位
_CJK_SPEECH_RATE = 4.0


def _is_meta_line(line: str) -> bool:
    """判断是否为不参与 unit 切分的元信息行（空行 / 标题 / 引用 / 表格 / 分隔线）。"""
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith(_META_LINE_PREFIXES):
        return True
    return bool(re.match(r"^[*#\s]*第\s*[0-9０-９一二三四五六七八九十]+\s*[集话章]", stripped))


def _registered_asset_names(project: Dict[str, Any]) -> set:
    """项目已登记资产名集合（characters / scenes / props 三张表的键）。"""
    names = set()
    for key in ("characters", "scenes", "props"):
        table = project.get(key)
        if isinstance(table, dict):
            names.update(str(k) for k in table.keys())
    return names


def _pick_duration(utterance_chars: int, tiers: List[int]) -> int:
    """按台词字数在档位里选「念得完」的最短时长；都不够则退到最大档由官方校验兜底报违约。"""
    if not tiers:
        raise ValueError("空档位")
    need = utterance_chars / _CJK_SPEECH_RATE
    fits = [t for t in sorted(tiers) if t >= need]
    return fits[0] if fits else max(tiers)


def _reference_flat_units_from_script(
    novel_text: str,
    project: Dict[str, Any],
    *,
    caps: Any,
) -> List[Dict[str, Any]]:
    """把（已归一化的）剧本文本切分为引用语法 video unit —— 离线最小实现。

    只认标准剧本文档的三种行：动作行（``△``）、说话人行（``**«««角色»»»**``）、台词行
    （``说："…"``）；元信息行（标题 / 引用块 / 表格 / 分隔线）跳过。切分以「动作段」为界，
    台词块并入最近的动作段。

    - ``source_text`` 取该块在源文中的**逐字片段**（含行间换行），满足官方「原文锚须是源文
      子串」的校验；
    - ``text`` 为引用语法正文：动作描述 + ``@[角色]：{台词}``；说话人未登记时降级为画外音
      ``{台词}``（合法且不产参考图），避免整份产出因未登记 mention 被拒；
    - 时长按该 unit 的引用状态（正文有无 ``@[``）取对应档位，并保证台词念得完。
    """
    asset_names = _registered_asset_names(project)
    lines = novel_text.split("\n")
    blocks: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None

    def _flush() -> None:
        nonlocal cur
        if cur is not None and (cur["desc"] or cur["utt"]):
            blocks.append(cur)
        cur = None

    def _escape_desc(text: str) -> str:
        # 画面描述里不得出现游离花括号（会被解析器原样带入画面），非记号的 { } 换全角。
        return text.replace("{", "｛").replace("}", "｝")

    index = 0
    while index < len(lines):
        line = lines[index]
        if _is_meta_line(line):
            index += 1
            continue
        stripped = line.strip()

        if stripped.startswith("△"):
            _flush()
            cur = {"src": [line], "desc": [_escape_desc(stripped.lstrip("△").strip())], "utt": []}
            index += 1
            continue

        speaker_match = _SPEAKER_MARK_RE.search(stripped)
        if speaker_match is not None:
            speaker = speaker_match.group(1).strip()
            cursor = index + 1
            while cursor < len(lines) and not lines[cursor].strip():
                cursor += 1
            utterance = ""
            if cursor < len(lines):
                utterance_match = _UTTERANCE_RE.match(lines[cursor].strip())
                if utterance_match is not None:
                    utterance = utterance_match.group(1).strip()
            if cur is None:
                cur = {"src": [], "desc": [], "utt": []}
            cur["src"].append(line)
            if utterance:
                cur["src"].append(lines[cursor])
                cur["utt"].append((speaker, utterance))
                index = cursor + 1
            else:
                # 无台词：说话人当普通引用（未登记则仅写文字），不产生台词记号。
                cur["desc"].append(
                    f"@[{speaker}]" if speaker in asset_names else _escape_desc(speaker)
                )
                index += 1
            continue

        if cur is None:
            cur = {"src": [], "desc": [], "utt": []}
        cur["src"].append(line)
        cur["desc"].append(_escape_desc(stripped))
        index += 1

    _flush()

    units: List[Dict[str, Any]] = []
    for block in blocks:
        desc = " ".join(part for part in block["desc"] if part).strip()
        pieces: List[str] = []
        if desc:
            pieces.append(desc)
        for speaker, utterance in block["utt"]:
            if speaker in asset_names:
                pieces.append(f"@[{speaker}]：{{{utterance}}}")
            else:
                pieces.append(f"{{{utterance}}}")
        text = "\n".join(pieces).strip()
        source_text = "\n".join(block["src"]).strip()
        if not text or not source_text:
            continue
        utterances = "".join(utterance for _, utterance in block["utt"])
        has_references = "@[" in text
        tiers = list(caps.tiers_for(has_references=has_references))
        units.append(
            {
                "duration_seconds": _pick_duration(len(utterances), tiers),
                "source_text": source_text,
                "text": text,
            }
        )
    return units


async def _seed_reference_units(
    args: argparse.Namespace,
    pm: Any,
    services: Services,
    name: str,
    project_path: Path,
    project: Dict[str, Any],
) -> None:
    """script-plan seed（reference_video）：离线写 ``script_plan_reference_units.json``。

    参考生视频的 script_plan 正规产出走 ``generate_script_plan``（项目文本模型）。本命令让
    **外部 Agent 承担同一份内容生成**，只复用官方的校验与落盘出口，因而全程不调 LLM：

    - 内容过 ``_collect_reference_flat_violations``：时长落在该 unit 引用状态对应的**生效**
      档位内、``source_text`` 是源文逐字子串、正文引用语法合法且 ``@[名称]`` 已登记、
      台词量念得完；
    - ``_build_reference_units_from_flat`` 按数组序号派生 ``unit_id``（不手写）；
    - ``_commit_generated_reference_script_plan`` 在同一把锁内落盘正式文件并登记产物 basis
      ——planner 正是拿它判 ``script_plan`` 是否为 ``current``。

    ``--units-file`` 提供外部 Agent 写好的扁平 units（``{"units": [{duration_seconds,
    source_text, text}]}``，不含 ``unit_id``）；省略时按 ``source/episode_<N>.txt`` 自动切分。
    """
    episode = args.episode
    source_rel = episode_source_relpath(episode)
    source_path = project_path / source_rel
    if not source_path.is_file():
        print(
            f"ERROR: 未找到本集源文 {source_rel}。reference_video 路径要求 source/episode_<N>.txt "
            "在场——可用 `source upload` 上传，或由外部 Agent 直接落盘（planner 会据它补建分集账本）。",
            file=sys.stderr,
        )
        sys.exit(1)

    # 源文：与拆分 / 晋升侧同一 helper（经归一化），故切片与官方校验同坐标系。
    try:
        novel_text, _prompt_inputs, _variant_basis = await asyncio.to_thread(
            _load_script_plan_source_with_basis,
            project_path,
            args.source,
            project,
            episode,
            "reference_video",
        )
    except Exception as exc:
        print(f"ERROR: 读取源文失败：{exc}", file=sys.stderr)
        sys.exit(1)

    # basis 必须与 planner 的重建口径同源：``_plan_one_script_plan`` 走
    # ``build_script_plan_basis``（prompt 投影**不带** expected_variant），而生成侧的
    # ``build_script_plan_request`` 带 variant 校验、digest 不同——直接沿用后者会让刚写入的
    # script_plan 立刻被判 stale。
    basis = build_script_plan_basis(novel_text, episode=episode, project=project)

    caps = await _fetch_reference_caps_with_fallback(
        project, episode, config_resolver=services.capabilities
    )
    if not caps.durations:
        print("ERROR: 无法解析参考生视频时长档位，无法生成合法 script_plan。", file=sys.stderr)
        sys.exit(1)

    if args.units_file:
        units_file = Path(args.units_file)
        if not units_file.is_file():
            print(f"ERROR: --units-file 不存在：{units_file}", file=sys.stderr)
            sys.exit(1)
        try:
            payload = json.loads(units_file.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"ERROR: --units-file 不是合法 JSON：{exc}", file=sys.stderr)
            sys.exit(1)
        flat_units = payload.get("units") if isinstance(payload, dict) else None
        if not isinstance(flat_units, list) or not flat_units:
            print("ERROR: --units-file 须形如 {\"units\": [{duration_seconds, source_text, text}]}。", file=sys.stderr)
            sys.exit(1)
        origin = f"外部 units 文件 {units_file.name}"
    else:
        flat_units = _reference_flat_units_from_script(novel_text, project, caps=caps)
        origin = f"自动切分 {source_rel}"
        if not flat_units:
            print("ERROR: 源文切分后无有效 unit（检查是否为标准剧本文档格式）。", file=sys.stderr)
            sys.exit(1)

    violations = _collect_reference_flat_violations(
        flat_units,
        project,
        episode=episode,
        novel_text=novel_text,
        caps=caps,
        source_language=project.get("source_language"),
    )
    if violations:
        print("ERROR: units 未通过官方校验，未落盘：", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        if not args.units_file:
            print(
                "  提示：自动切分只做最小转换，可改用具名 units 文件精细控制："
                "`script-plan seed --units-file <json>`。",
                file=sys.stderr,
            )
        sys.exit(1)

    try:
        raw_units = _build_reference_units_from_flat(
            flat_units, project, episode=episode, max_refs=caps.max_refs
        )
    except Exception as exc:
        print(f"ERROR: unit 派生失败：{exc}", file=sys.stderr)
        sys.exit(1)

    formal_path = script_review_lib.official_reference_script_plan_path(project_path, episode)
    _draft_baseline, formal_baseline = _generation_baselines(
        quarantine_path(project_path, episode, QUARANTINE_KIND_SCRIPT_PLAN), formal_path
    )

    if args.dry_run:
        emit(
            {
                "source": source_rel,
                "origin": origin,
                "durations": caps.durations,
                "reference_durations": caps.reference_durations,
                "text_durations": caps.text_durations,
                "max_refs": caps.max_refs,
                "formal_path": str(formal_path),
                "units": raw_units,
            }
        )
        return

    try:
        _commit_generated_reference_script_plan(
            project_path,
            episode,
            {"units": raw_units},
            formal_baseline,
            basis,
        )
    except Exception as exc:
        print(f"ERROR: script_plan 落盘失败：{exc}", file=sys.stderr)
        sys.exit(1)

    total_seconds = sum(int(unit["duration_seconds"]) for unit in raw_units)
    max_mentions = max(
        (len(set(re.findall(r"@\[([^\]]+)\]", str(unit["text"])))) for unit in raw_units),
        default=0,
    )
    print(f"已写入参考生视频 script_plan：{formal_path}")
    print(f"来源：{origin}")
    print(
        f"统计：{len(raw_units)} 个 video unit，合计 {total_seconds} 秒；"
        f"单 unit @提及上限 {max_mentions}/{caps.max_refs}"
    )
    print("下一步：")
    print(f"  arcreel.bat --json workflow get --project {args.project}")
    print(f"  arcreel.bat script-plan confirm --project {args.project} --episode {episode}")


def _synth_visual_segment(segment: Dict[str, Any], style: str) -> Dict[str, Any]:
    """离线合成一条分镜的视觉层（``image_prompt`` / ``video_prompt``）。

    正式剧本的视觉层本该由文本模型按 script_plan 分镜产出；离线路径没有模型，故以分镜
    文本为基底 + 项目画风拼出可用的提示词，保证剧本 schema 合法、分镜/视频步骤能消费。
    想要更好的画面，后续用 ``episode-script generate``（有 LLM 时）按同一 script_plan 重出。
    """
    text = str(segment.get("novel_text") or "").strip().rstrip("。")
    suffix = f"，{style}" if style else ""
    return {
        "segment_id": segment["segment_id"],
        "image_prompt": (
            f"{text}——电影感构图，主体清晰，光影讲究{suffix}，写实插画风格，避免文字与水印"
        ),
        "video_prompt": f"{text}——镜头缓慢自然运动，光影微动，动作连贯流畅",
    }


async def _seed_episode_script_reference(
    args: argparse.Namespace,
    pm: Any,
    name: str,
    project_path: Path,
    project: Dict[str, Any],
) -> None:
    """episode-script seed（reference_video）：离线写 ``scripts/episode_<N>.json``。

    参考生视频的正式剧本走 ``generate_episode_script``（项目文本模型 + prompt_authoring）。
    本命令让**外部 Agent 承担同一份内容生成**，只复用官方的结构契约与写盘出口：

    - 内容层：``plan_entry_content("reference_video", u)`` —— 只取 ``unit_id`` / ``text`` /
      ``duration_seconds``（参考单元的正文本身就是成片视频提示词，无需第二层视觉生成）；
    - 条目指纹：``plan_entry_revisions`` + ``splice_entries`` 盖章，与 planner 的条目级时效
      判定同源，否则刚落盘的剧本会被判整集 stale；
    - ``metadata[script_plan_revision]`` 记整集口径回退指纹；
    - 落盘：``pm.save_script(..., validate=True)`` —— 同时同步 project.json 分集索引并登记
      ``episode-script`` 产物条目。
    """
    episode = args.episode
    plan_path = script_review_lib.script_plan_path(project_path, project, episode)
    if plan_path is None or not plan_path.is_file():
        print(
            "ERROR: 本集还没有 script_plan。请先跑 `script-plan seed`（离线）或 "
            "`script-plan generate`（LLM）。",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"ERROR: 读取 script_plan 失败：{exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(plan, dict):
        print(f"ERROR: script_plan 不是对象：{plan_path}", file=sys.stderr)
        sys.exit(1)

    # 与 planner 同源的归一：条目先经 ReferenceScriptPlanDraft 归一，再取内容层与指纹。
    plan_entries = plan_entries_from_document("reference_video", plan)
    if not plan_entries:
        print(f"ERROR: script_plan 缺少可用的 units 条目：{plan_path}", file=sys.stderr)
        sys.exit(1)
    try:
        plan_revisions = plan_entry_revisions("reference_video", plan_entries, episode=episode)
    except Exception as exc:
        print(f"ERROR: 计算 script_plan 条目指纹失败：{exc}", file=sys.stderr)
        sys.exit(1)

    merged_entries = [
        {**plan_entry_content("reference_video", entry), "transition_to_next": "cut", "note": None}
        for entry in plan_entries
    ]
    try:
        assembled = splice_entries(
            "reference_video",
            plan_revisions=plan_revisions,
            rewritten=merged_entries,
            existing={},
        )
    except Exception as exc:
        print(f"ERROR: 剧本条目装配失败：{exc}", file=sys.stderr)
        sys.exit(1)

    title = args.title or f"第{episode}集"
    script: Dict[str, Any] = {
        "episode": episode,
        "title": title,
        "content_mode": project.get("content_mode"),
        "video_units": assembled,
        "metadata": {SCRIPT_PLAN_REVISION_FIELD: script_review_lib.content_fingerprint(plan_path)},
    }

    if args.dry_run:
        emit({"plan": str(plan_path), "script": script})
        return

    filename = episode_script_filename(episode)
    try:
        path = pm.save_script(name, script, filename, validate=True)
    except Exception as exc:
        print(f"ERROR: 正式剧本落盘失败：{exc}", file=sys.stderr)
        sys.exit(1)

    total_seconds = sum(int(u.get("duration_seconds") or 0) for u in assembled)
    print(f"已写入正式剧本：{path}")
    print(f"统计：{len(assembled)} 个视频单元，合计约 {total_seconds} 秒（内容层透传 script_plan）")
    print("下一步：")
    print(f"  arcreel.bat --json workflow get --project {args.project}")
    print(f"  arcreel.bat media submit --project {args.project} --type video --script {filename}")


def _synth_drama_visual_scene(entry: Dict[str, Any], style: str) -> Dict[str, Any]:
    """离线合成 drama 一条分镜的视觉层（``image_prompt`` / ``video_prompt``）。

    官方的视觉层由 prompt_authoring（文本模型）只产这两项；离线路径没有模型，故以本镜的
    ``scene_description``（缺则退到口播 / 原文锚）为画面基底 + 项目画风拼出可用提示词，保证
    剧本 schema 合法、分镜图与视频步骤能消费。想要更好的画面，后续用
    ``episode-script generate``（有 LLM 时）按同一 script_plan 重出。
    """
    base = str(entry.get("scene_description") or "").strip()
    if not base:
        spoken = " ".join(
            str(item.get("text") or "")
            for item in entry.get("utterances") or []
            if isinstance(item, dict)
        ).strip()
        base = (spoken or str(entry.get("source_text") or "")).strip().rstrip("。")
    suffix = f"，{style}" if style else ""
    return {
        "scene_id": entry["scene_id"],
        "image_prompt": (
            f"{base}——电影感构图，主体清晰，情绪表达到位，光影层次讲究{suffix}，"
            "写实电影质感，避免文字与水印"
        ),
        "video_prompt": f"{base}——镜头缓慢自然运动，人物动作连贯，光影微动，情绪细腻",
    }


async def _seed_episode_script_drama(
    args: argparse.Namespace,
    pm: Any,
    name: str,
    project_path: Path,
    project: Dict[str, Any],
) -> None:
    """episode-script seed（drama）：离线写 ``scripts/episode_<N>.json``。

    剧情演绎的正式剧本走两段式 prompt_authoring：script_plan 内容层（口播 / 时长 / 资产引用 /
    原文锚）逐字透传，文本模型只产视觉层，再按 ``scene_id`` 合并回各分镜。本命令让**外部 Agent
    承担同一份内容生成**，只复用官方的合并与写盘出口：

    - 内容层：条目取自 ``script_plan``（``plan_entries_from_document`` 的原样 dict），
      ``merge_drama_visual_into_scenes`` 按 ``scene_id`` 合并并**剔除**
      ``scene_description``——与官方 ``_generate_drama_prompt_authoring`` 同一条出口；
    - 视觉层：由本镜 ``scene_description`` + 项目画风合成（离线替代 prompt_authoring）；
    - 条目指纹：``plan_entry_revisions`` + ``splice_entries`` 盖章，与 planner 的条目级时效
      判定同源，否则刚落盘的剧本会被判整集 stale；
    - ``metadata[script_plan_revision]`` 记整集口径回退指纹；
    - 落盘：``pm.save_script(..., validate=True)``——同时同步 project.json 分集索引并登记
      ``episode-script`` 产物条目（planner 据此判 ``artifacts.script = current``）。
    """
    episode = args.episode
    plan_path = script_review_lib.script_plan_path(project_path, project, episode)
    if plan_path is None or not plan_path.is_file():
        print(
            "ERROR: 本集还没有 script_plan。请先跑 `script-plan seed`（离线）或 "
            "`script-plan generate`（LLM）。",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"ERROR: 读取 script_plan 失败：{exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(plan, dict):
        print(f"ERROR: script_plan 不是对象：{plan_path}", file=sys.stderr)
        sys.exit(1)

    # drama 无草稿模型：条目即磁盘原文，与 planner 的时效判定读的是同一份 dict。
    plan_entries = plan_entries_from_document("drama", plan)
    if not plan_entries:
        print(f"ERROR: script_plan 缺少可用的 scenes 条目：{plan_path}", file=sys.stderr)
        sys.exit(1)
    # 与官方 _add_metadata 同口径：落盘前把条目 id 的 E\\d+ 前缀改写到本集，避免 LLM/外部
    # Agent 写错集号导致下游分镜图 / 资产键跨集撞车（此处同时让条目 id 与条目指纹的键对齐）。
    for entry in plan_entries:
        entry["scene_id"] = rewrite_episode_prefix(entry.get("scene_id"), episode)
    try:
        plan_revisions = plan_entry_revisions("drama", plan_entries, episode=episode)
    except Exception as exc:
        print(f"ERROR: 计算 script_plan 条目指纹失败：{exc}", file=sys.stderr)
        sys.exit(1)

    style = project.get("style") if isinstance(project.get("style"), str) else ""
    visual_scenes = [_synth_drama_visual_scene(entry, style) for entry in plan_entries]
    try:
        merged_scenes = merge_drama_visual_into_scenes(plan_entries, visual_scenes)
    except Exception as exc:
        print(f"ERROR: 视觉层与 script_plan 内容层合并失败：{exc}", file=sys.stderr)
        sys.exit(1)

    try:
        assembled = splice_entries(
            "drama", plan_revisions=plan_revisions, rewritten=merged_scenes, existing={}
        )
    except Exception as exc:
        print(f"ERROR: 剧本条目装配失败：{exc}", file=sys.stderr)
        sys.exit(1)

    plan_title = plan.get("title") if isinstance(plan.get("title"), str) else None
    title = args.title or plan_title or f"第{episode}集"
    script: Dict[str, Any] = {
        "episode": episode,
        "title": title,
        # 与官方 _add_metadata 同口径：content_mode 落盘为项目真值（非参考集不强制覆盖模型默认）。
        "content_mode": project.get("content_mode"),
        "scenes": assembled,
        "metadata": {SCRIPT_PLAN_REVISION_FIELD: script_review_lib.content_fingerprint(plan_path)},
    }

    if args.dry_run:
        emit({"plan": str(plan_path), "script": script})
        return

    filename = episode_script_filename(episode)
    try:
        path = pm.save_script(name, script, filename, validate=True)
    except Exception as exc:
        print(f"ERROR: 正式剧本落盘失败：{exc}", file=sys.stderr)
        sys.exit(1)

    total_seconds = sum(int(s.get("duration_seconds") or 0) for s in assembled)
    spoken = sum(
        len(str(item.get("text") or ""))
        for s in assembled
        for item in (s.get("utterances") or [])
        if isinstance(item, dict)
    )
    print(f"已写入正式剧本：{path}")
    print(
        f"统计：{len(assembled)} 个分镜，合计约 {total_seconds} 秒、口播 {spoken} 字"
        f"（内容层透传 script_plan，视觉层由分镜描述合成）"
    )
    print("下一步：")
    print(f"  arcreel.bat --json workflow get --project {args.project}")
    print(
        f"  arcreel.bat media submit --project {args.project} --type storyboard --script {filename}"
    )

    registered = set(_table_names(project, "characters"))
    referenced = {
        name for scene in assembled for name in (scene.get("characters_in_scene") or [])
    }
    unregistered = sorted(name for name in referenced if name not in registered)
    if unregistered:
        print()
        print(f"注意：剧本引用了尚未登记的角色 {unregistered}，工作流的结构校验会因此判剧本无效")
        print("（invalid_script_structure）。先登记资产（零 LLM，条目由外部提供）：")
        print(
            f"  arcreel.bat workflow asset-inventory --project {args.project} --scope-kind all "
            "--entries-file characters.json"
        )
        print('  文件形如：{"characters": {"角色名": {"description": "一句话外貌/身份"}}}')
        print(
            "  顺序建议：先 asset-inventory 再 script-plan seed——盘点是项目语义的一部分，"
            "反过来会让已写好的 script_plan / 剧本被判 stale。"
        )
        print(
            f"  仍需重跑时：arcreel.bat script-plan seed --project {args.project} --episode {episode}"
            f" → script-plan confirm → episode-script seed"
        )


async def _cmd_episode_script_seed(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """episode-script seed：离线（不调 LLM）按已确认的 script_plan 合成正式剧本并登记产物账本。

    正式剧本的官方出口是 ``ScriptGenerator``：script_plan 的内容层（``novel_text`` / 时长 /
    break / 资产引用）逐字透传，模型只产视觉层、按 ``segment_id`` 合并回各分镜。离线路径复用
    同一套结构契约，只把视觉层改为由分镜文本合成：

    - 内容层：``plan_entry_content("narration", s)`` 逐字透传 script_plan 条目；+    - 视觉层：由分镜文本 + 项目画风拼出 ``image_prompt`` / ``video_prompt``；
    - 落盘：``pm.save_script(..., validate=True)`` 同一写盘入口——同时同步 project.json 的
      分集索引，并在写盘事务内按 ``resolve_current_artifact_target`` 登记 ``episode-script``
      条目（basis 由 script_plan 内容经 ``build_episode_script_basis`` 派生，与 planner
      后续比对同源）。

    因此 planner 会认 ``artifacts.script = current``，工作流可干净推进到 ASSET_SHEETS → STORYBOARD。
    """
    name = pm.normalize_project_name(args.project)
    _project_scope(args.project, pm)
    project_path = pm.get_project_path(name)
    project = pm.load_project_readonly(name)

    if project.get("generation_mode") == "reference_video":
        await _seed_episode_script_reference(args, pm, name, project_path, project)
        return
    if project.get("content_mode") == "drama":
        await _seed_episode_script_drama(args, pm, name, project_path, project)
        return
    if project.get("content_mode") != "narration":
        print(
            "ERROR: episode-script seed 目前支持 narration / drama 与 reference_video；"
            f"当前 content_mode={project.get('content_mode')!r} 尚未实现。",
            file=sys.stderr,
        )
        sys.exit(1)

    episode = args.episode

    plan_path = script_review_lib.script_plan_path(project_path, project, episode)
    if plan_path is None or not plan_path.is_file():
        print(
            "ERROR: 本集还没有 script_plan。请先跑 `script-plan seed`（离线）或 "
            "`script-plan generate`（LLM）。",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"ERROR: 读取 script_plan 失败：{exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(plan, dict):
        print(f"ERROR: script_plan 不是对象：{plan_path}", file=sys.stderr)
        sys.exit(1)

    # 与 planner / 时效判定同源的归一：条目先经 NarrationScriptPlanDraft 归一，再取内容层与指纹；
    # 否则一侧摘归一后条目、另一侧摘磁盘原文，刚落盘的剧本会立刻被判整集失效。
    plan_entries = plan_entries_from_document("narration", plan)
    if not plan_entries:
        print(f"ERROR: script_plan 缺少可用的 segments 条目：{plan_path}", file=sys.stderr)
        sys.exit(1)
    try:
        plan_revisions = plan_entry_revisions("narration", plan_entries, episode=episode)
    except Exception as exc:
        print(f"ERROR: 计算 script_plan 条目指纹失败：{exc}", file=sys.stderr)
        sys.exit(1)

    style = project.get("style") if isinstance(project.get("style"), str) else ""
    visual_by_id: Dict[str, Dict[str, Any]] = {}
    for entry in plan_entries:
        item = _synth_visual_segment(entry, style)
        sid = item["segment_id"]
        if sid in visual_by_id:
            print(f"ERROR: 视觉层 segment_id 重复：{sid}", file=sys.stderr)
            sys.exit(1)
        visual_by_id[sid] = item

    # 与官方 _merge_narration_visual 同一口径：内容层逐字透传 + 视觉层按 segment_id 合并。
    merged_entries = [
        {**plan_entry_content("narration", entry), **visual_by_id[entry["segment_id"]]}
        for entry in plan_entries
    ]
    # 官方装配出口：按规划顺序排定条目并给每条盖上 ``script_plan_entry_revision`` 指纹——
    # planner 的条目级时效判定正是拿它比对，盖了才不会被判整集失效（stale）。
    try:
        assembled = splice_entries(
            "narration", plan_revisions=plan_revisions, rewritten=merged_entries, existing={}
        )
    except Exception as exc:
        print(f"ERROR: 剧本条目装配失败：{exc}", file=sys.stderr)
        sys.exit(1)

    title = args.title or f"第{episode}集"
    script: Dict[str, Any] = {
        "episode": episode,
        "title": title,
        "segments": assembled,
        # 整集口径回退用：metadata 记下本剧本实际消费的 script_plan 内容指纹（与官方出口一致）。
        "metadata": {SCRIPT_PLAN_REVISION_FIELD: script_review_lib.content_fingerprint(plan_path)},
    }

    if args.dry_run:
        emit({"plan": str(plan_path), "script": script})
        return

    filename = episode_script_filename(episode)
    try:
        path = pm.save_script(name, script, filename, validate=True)
    except Exception as exc:
        print(f"ERROR: 正式剧本落盘失败：{exc}", file=sys.stderr)
        sys.exit(1)

    total_seconds = sum(int(s.get("duration_seconds") or 0) for s in assembled)
    print(f"已写入正式剧本：{path}")
    print(
        f"统计：{len(assembled)} 个分镜，合计约 {total_seconds} 秒"
        f"（内容层透传 script_plan，视觉层由分镜文本合成）"
    )
    print("下一步：")
    print(f"  arcreel.bat --json workflow get --project {args.project}")
    print(
        f"  arcreel.bat media submit --project {args.project} --type storyboard --script {filename}"
    )


async def _cmd_episode_script_generate(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """episode-script generate：生成正式剧本（对齐 generate_episode_script）。"""
    scope = _project_scope(args.project, pm)
    req = TextGenerationRequest(
        episode=args.episode,
        source=args.source,
        instructions=args.instructions,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        emit(_require(await generate_episode_script(ToolRequest(req), scope, caller, services)))
        return

    async def _enqueue() -> Any:
        return _require(await generate_episode_script(ToolRequest(req), scope, caller, services))

    await _submit_generation(args, pm, services, caller, _enqueue)


async def _cmd_episode_script_patch(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """episode-script patch：原子批量编辑剧本（对齐 patch_episode_script）。"""
    scope = _project_scope(args.project, pm)
    operations = _json_arg(args.ops_json, None)
    if not isinstance(operations, list) or not operations:
        print(
            "ERROR: --ops-json 需为非空 JSON 数组（update/insert/remove/split 操作列表）",
            file=sys.stderr,
        )
        sys.exit(1)
    req = PatchEpisodeScriptRequest(
        script=Path(args.script).name,
        base_revision=args.base_revision,
        operations=operations,
    )
    value = _require(await patch_episode_script(ToolRequest(req), scope, caller, services))
    emit(value)


async def _cmd_episode_script_retitle(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """episode-script retitle：修改剧本标题（对齐 patch_episode_meta）。"""
    scope = _project_scope(args.project, pm)
    req = PatchEpisodeMetaRequest(script=Path(args.script).name, field="title", value=args.value)
    value = _require(await patch_episode_meta(ToolRequest(req), scope, caller, services))
    emit(value)


async def _cmd_episode_script_preview(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """episode-script preview：预览某条目最终提示词（对齐 get_prompt_preview，只读）。"""
    scope = _project_scope(args.project, pm)
    req = PromptPreviewRequest(script=Path(args.script).name, item_id=args.item_id)
    value = _require(await get_prompt_preview(ToolRequest(req), scope, caller, services))
    emit(value)



def _reference_image_labels_from_args(args: argparse.Namespace) -> Optional[List[str]]:
    """读取 reference_image_labels；CLI 采用一项一参数或“一行一项”文件，绝不按逗号拆名。"""
    repeated = list(getattr(args, "reference_image_label", None) or [])
    labels_file = getattr(args, "reference_image_labels_file", None)
    if repeated and labels_file:
        raise ValueError("--reference-image-label 与 --reference-image-labels-file 不能同时使用")
    if labels_file:
        path = Path(labels_file)
        if not path.is_file():
            raise ValueError(f"--reference-image-labels-file 不存在：{path}")
        repeated = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    labels = [str(item).strip() for item in repeated if str(item).strip()]
    return labels or None


def _prompt_override_from_args(args: argparse.Namespace) -> Optional[str]:
    """读取临时正文覆盖：--prompt / --prompt-file 二选一，仅用于预览，不落盘。"""
    inline = getattr(args, "prompt", None)
    prompt_file = getattr(args, "prompt_file", None)
    if inline is not None and prompt_file:
        raise ValueError("--prompt 与 --prompt-file 不能同时使用")
    if prompt_file:
        path = Path(prompt_file)
        if not path.is_file():
            raise ValueError(f"--prompt-file 不存在：{path}")
        return path.read_text(encoding="utf-8")
    return inline


def _human_reference_video_prompt_preview(value: Any) -> None:
    """reference-video prompt-preview 的可读输出；JSON 模式仍由 emit 统一处理。"""
    data = to_dict(value)
    if not isinstance(data, dict):
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return

    print("=== Reference Video Provider Prompt Preview ===")
    model_id = data.get("model_id")
    compiler = data.get("prompt_compiler")
    applied = data.get("compiler_applied")
    duration = data.get("duration_seconds")
    prompt_chars = data.get("prompt_chars")
    max_chars = data.get("max_prompt_chars")
    if model_id is not None:
        print(f"model: {model_id}")
    if compiler is not None:
        suffix = " (applied)" if applied is True else ""
        print(f"prompt_compiler: {compiler}{suffix}")
    if duration is not None:
        print(f"duration: {duration}s")
    if prompt_chars is not None:
        limit = f"/{max_chars}" if max_chars else ""
        print(f"prompt_chars: {prompt_chars}{limit}")

    mapping = data.get("reference_mapping")
    if isinstance(mapping, list) and mapping:
        print("\nReference mapping:")
        for item in mapping:
            if not isinstance(item, dict):
                continue
            picture = item.get("picture") or f"<Picture {item.get('index', '?')}>"
            subject = item.get("subject") or f"<Subject {item.get('index', '?')}>"
            label = item.get("label", "")
            print(f"  {picture:<12} -> {subject:<12} -> {label}")

    provider_prompt = data.get("provider_prompt")
    if provider_prompt is None:
        # 兼容旧 get_prompt_preview 的返回结构：尽量寻找常见 prompt 字段。
        provider_prompt = (
            data.get("prompt")
            or data.get("final_prompt")
            or data.get("rendered_prompt")
            or data.get("text")
        )
    print("\nFinal provider prompt:")
    print("-" * 72)
    if provider_prompt is None:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(str(provider_prompt))

    if getattr(value, "_show_rendered", False):  # pragma: no cover - 普通对象无此属性
        rendered = data.get("rendered_prompt")
        if rendered is not None and rendered != provider_prompt:
            print("\nArcReel rendered prompt (before H3 compiler):")
            print("-" * 72)
            print(str(rendered))


async def _reference_video_prompt_preview_value(
    args: argparse.Namespace,
    scope: ProjectScope,
    caller: CallerContext,
    services: Services,
    *,
    item_id: Optional[str] = None,
) -> Any:
    """统一 CLI 预览入口：优先 H3-aware tool_runtime，旧核心仅允许无覆盖的 legacy 预览。"""
    preview_item_id = item_id or getattr(args, "unit_id", None) or getattr(args, "item_id", None)
    if not preview_item_id:
        raise ValueError("缺少 unit/item id")

    script_name = Path(args.script).name
    labels = _reference_image_labels_from_args(args)
    prompt_override = _prompt_override_from_args(args)
    compiler = getattr(args, "prompt_compiler", "auto") or "auto"

    req = PromptPreviewRequest(
        script=script_name,
        item_id=preview_item_id,
        prompt=prompt_override,
        reference_image_labels=labels,
        prompt_compiler=compiler,
    )
    return _require(
        await get_prompt_preview(ToolRequest(req), scope, caller, services)
    )


async def _cmd_reference_video_prompt_preview(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """reference-video prompt-preview：只读预览真正 Provider Prompt，不入队、不调用供应商。"""
    scope = _project_scope(args.project, pm)
    value = await _reference_video_prompt_preview_value(args, scope, caller, services)
    if JSON_OUTPUT:
        emit(value)
        return

    # human renderer 需要知道是否展示 pre-H3 prompt；避免修改 tool 返回对象。
    data = to_dict(value)
    if getattr(args, "show_rendered", False) and isinstance(data, dict):
        _human_reference_video_prompt_preview(data)
        rendered = data.get("rendered_prompt")
        provider = data.get("provider_prompt")
        if rendered is not None and rendered != provider:
            print("\nArcReel rendered prompt (before H3 compiler):")
            print("-" * 72)
            print(str(rendered))
        return
    emit(value, human=_human_reference_video_prompt_preview)


def _unwrap_episode_script(value: Any) -> Dict[str, Any]:
    """兼容 get_episode_script 直接返回 script 或包在 content/script/data 中的形状。"""
    data = to_dict(value)
    if not isinstance(data, dict):
        raise ValueError("episode script 返回值不是对象")
    if isinstance(data.get("video_units"), list):
        return data
    for key in ("script", "content", "data"):
        nested = data.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("video_units"), list):
            return nested
    raise ValueError("剧本中未找到 video_units；--dry-run 仅支持 reference_video 视频单元")


async def _video_dry_run_unit_ids(
    args: argparse.Namespace,
    scope: ProjectScope,
    caller: CallerContext,
    services: Services,
) -> List[str]:
    """按 media video 的 scope 解析 dry-run 目标，不入队。"""
    script_name = Path(args.script).name
    script_value = _require(
        await get_episode_script(ToolRequest(script_name), scope, caller, services)
    )
    script = _unwrap_episode_script(script_value)
    units = [item for item in script.get("video_units", []) if isinstance(item, dict)]
    all_ids = [
        str(item.get("unit_id") or item.get("id") or "").strip()
        for item in units
    ]
    all_ids = [item for item in all_ids if item]
    if not all_ids:
        raise ValueError("video_units 中没有可识别的 unit_id")

    if args.video_scope in ("scene", "selected"):
        requested = _split_ids(args.video_ids) or []
        if not requested:
            raise ValueError("video --video-scope=scene|selected 时必须提供 --video-ids")
        missing = [item for item in requested if item not in set(all_ids)]
        if missing:
            raise ValueError(f"--video-ids 含不存在的 unit：{missing}")
        return requested

    # reference_video 的 episode/all dry-run 均为本 script 全部 video_units。
    return all_ids


async def _cmd_media_video_dry_run(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """media submit --type video --dry-run：展开每个目标 unit 的最终 Provider Prompt，不入队。"""
    if args.type != "video":
        raise ValueError("media submit --dry-run 当前仅支持 --type video")
    if not args.script:
        raise ValueError("media submit --type video --dry-run 必须提供 --script")

    scope = _project_scope(args.project, pm)
    unit_ids = await _video_dry_run_unit_ids(args, scope, caller, services)
    labels = _reference_image_labels_from_args(args)
    if labels is not None and len(unit_ids) != 1:
        raise ValueError(
            "多 unit dry-run 不接受一组全局 --reference-image-label；"
            "请用 --video-scope selected --video-ids <单个unit> 单镜预览，"
            "或留空让每个 unit 按实际 provider reference 顺序自动推导。"
        )

    items: List[Dict[str, Any]] = []
    for unit_id in unit_ids:
        value = await _reference_video_prompt_preview_value(
            args, scope, caller, services, item_id=unit_id
        )
        data = to_dict(value)
        if not isinstance(data, dict):
            data = {"value": data}
        data = {"unit_id": unit_id, **data}
        items.append(data)

    result = {
        "dry_run": True,
        "project": pm.normalize_project_name(args.project),
        "script": Path(args.script).name,
        "video_scope": args.video_scope,
        "requested_units": unit_ids,
        "count": len(items),
        "items": items,
    }
    if JSON_OUTPUT:
        emit(result)
        return

    print(
        f"DRY RUN: project={result['project']} script={result['script']} "
        f"scope={args.video_scope} units={len(items)}"
    )
    print("不会入队、不会启动 worker、不会调用视频供应商。\n")
    for index, data in enumerate(items, start=1):
        print(f"[{index}/{len(items)}] unit={data['unit_id']}")
        _human_reference_video_prompt_preview(data)
        print("\n" + "=" * 88 + "\n")


async def _cmd_draft(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """draft open/patch/promote/discard：剧本规划草稿工作流（对齐 MCP 草稿四件套）。"""
    scope = _project_scope(args.project, pm)
    action = args.action
    if action == "open":
        req = DraftLocator(episode=args.episode, doc_type=args.doc_type, source=args.source)
        value = _require(await open_draft(ToolRequest(req), scope, caller, services))
    elif action == "patch":
        content = _json_arg(args.content_json, None)
        if not isinstance(content, dict):
            print("ERROR: --content-json 需为 JSON 对象（草稿正文）", file=sys.stderr)
            sys.exit(1)
        req = PatchDraftRequest(
            episode=args.episode,
            doc_type=args.doc_type,
            content=content,
            base_revision=args.base_revision,
            accept_formal_revision=args.accept_formal_revision,
            accepts_formal_revision=args.accepts_formal_revision,
            source=args.source,
            updates_source=args.updates_source,
        )
        value = _require(await patch_draft(ToolRequest(req), scope, caller, services))
    elif action == "promote":
        req = PromoteDraftRequest(
            episode=args.episode, doc_type=args.doc_type, base_revision=args.base_revision
        )
        value = _require(await promote_draft(ToolRequest(req), scope, caller, services))
    elif action == "discard":
        req = DiscardDraftRequest(
            episode=args.episode, doc_type=args.doc_type, base_revision=args.base_revision
        )
        value = _require(await discard_draft(ToolRequest(req), scope, caller, services))
    else:
        raise ValueError(f"未知 draft 动作：{action}")
    emit(value)


async def _cmd_projects_patch(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """projects patch：资产 upsert / 顶层 settings / 项目 overview（对齐 patch_project）。

    三选一分支：--table + --entries-json；--settings-json；--overview-json。
    """
    scope = _project_scope(args.project, pm)
    req = PatchProjectRequest(
        table=args.table,
        entries=_json_arg(args.entries_json),
        settings=_json_arg(args.settings_json),
        overview=_json_arg(args.overview_json),
    )
    value = _require(await patch_project(ToolRequest(req), scope, caller, services))
    emit(value)


async def _cmd_projects_rename_asset(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """projects rename-asset：重命名资产并迁移引用（对齐 rename_asset）。"""
    scope = _project_scope(args.project, pm)
    req = RenameAssetRequest(table=args.table, old_name=args.old_name, new_name=args.new_name)
    value = _require(await rename_asset(ToolRequest(req), scope, caller, services))
    emit(value)


async def _cmd_file_list(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """file list：列出项目业务文件（对齐 list_project_files）。"""
    scope = _project_scope(args.project, pm)
    value = _require(await list_project_files(ToolRequest(None), scope, caller, services))
    emit(value)


async def _cmd_file_read(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """file read：读取项目业务文件（对齐 read_project_file）。"""
    scope = _project_scope(args.project, pm)
    value = _require(await read_project_file(ToolRequest(args.path), scope, caller, services))
    emit(value)


async def _cmd_media_pending_assets(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """media pending-assets：列出待生成资产图（对齐 list_pending_assets）。"""
    if not _MEDIA_AVAILABLE:
        print("ERROR: 媒体生成模块不可用", file=sys.stderr)
        sys.exit(1)
    _project_scope(args.project, pm)
    ctx = ToolContext(
        project_name=pm.normalize_project_name(args.project),
        projects_root=pm.projects_root,
        pm=pm,
        caller=caller,
        queue=services.queue,
    )
    handler_args: Dict[str, Any] = {}
    if args.asset_type:
        handler_args["type"] = args.asset_type
    value = _require(await handle_list_pending_assets(ctx, handler_args))
    emit(value)


async def dispatch(
    args: argparse.Namespace, pm: Any, services: Services, caller: CallerContext
) -> None:
    """根据解析后的参数分发到对应工具调用。"""
    group: str = args.group
    action: str = args.action

    if group == "projects":
        if action == "list":
            value = _require(await list_projects(ToolRequest(None), caller, services))
            emit(value, human=_human_projects)
        elif action == "create":
            # CreateProjectToolRequest 校验规则：非 ad 模式下 brief 必须为 None，
            # 否则抛 "target_duration 与 brief 仅广告/短片项目可用"。
            req_kwargs = dict(
                name=args.name,
                title=args.title,
                content_mode=args.content_mode,
                source_kind=args.source_kind,
                generation_mode=args.generation_mode,
                aspect_ratio=args.aspect_ratio,
            )
            if args.brief:
                if args.content_mode == "ad":
                    req_kwargs["brief"] = args.brief
                else:
                    print(
                        f"[warn] --brief 仅在 content_mode=ad 时生效，"
                        f"当前 content_mode={args.content_mode!r} 已忽略 --brief",
                        file=sys.stderr,
                    )
            req = CreateProjectToolRequest(**req_kwargs)
            value = _require(await create_project(ToolRequest(req), caller, services))
            emit(value)
        elif action == "patch":
            await _cmd_projects_patch(args, pm, services, caller)
        elif action == "rename-asset":
            await _cmd_projects_rename_asset(args, pm, services, caller)
        return

    if group == "source":
        scope = _project_scope(args.project, pm)
        if action == "upload":
            text = Path(args.file).read_text(encoding="utf-8")
            req = UploadSourceRequest(
                filename=Path(args.file).name,
                content=text,
                on_conflict=args.on_conflict,
            )
            value = _require(
                await upload_source(ToolRequest(req), scope, caller, services)
            )
            emit(value)
        elif action == "list":
            value = _require(
                await list_source_files(ToolRequest(None), scope, caller, services)
            )
            emit(value)
        elif action == "text":
            value = _require(
                await get_source_text(ToolRequest(args.path), scope, caller, services)
            )
            emit(value)
        return

    if group == "content":
        scope = _project_scope(args.project, pm)
        if action == "get":
            value = _require(
                await get_project_content(ToolRequest(None), scope, caller, services)
            )
            emit(value)
        return

    if group == "script-plan":
        scope = _project_scope(args.project, pm)
        if action == "get":
            value = _require(
                await get_script_plan_content(
                    ToolRequest(args.episode), scope, caller, services
                )
            )
            emit(value)
        elif action == "generate":
            await _cmd_script_plan_generate(args, pm, services, caller)
        elif action == "seed":
            await _cmd_script_plan_seed(args, pm, services, caller)
        elif action == "confirm":
            await _cmd_script_plan_confirm(args, pm, services, caller)
        elif action == "convert":
            await _cmd_script_plan_convert(args, pm, services, caller)
        elif action == "rebuild-complete":
            await _cmd_script_plan_rebuild_complete(args, pm, services, caller)
        return

    if group == "episode-script":
        scope = _project_scope(args.project, pm)
        if action == "get":
            value = _require(
                await get_episode_script(
                    ToolRequest(args.script), scope, caller, services
                )
            )
            emit(value)
        elif action == "generate":
            await _cmd_episode_script_generate(args, pm, services, caller)
        elif action == "seed":
            await _cmd_episode_script_seed(args, pm, services, caller)
        elif action == "patch":
            await _cmd_episode_script_patch(args, pm, services, caller)
        elif action == "retitle":
            await _cmd_episode_script_retitle(args, pm, services, caller)
        elif action == "preview":
            await _cmd_episode_script_preview(args, pm, services, caller)
        return

    if group == "reference-video":
        if action == "prompt-preview":
            await _cmd_reference_video_prompt_preview(args, pm, services, caller)
        return

    if group == "workflow":
        scope = _project_scope(args.project, pm)
        if action == "get":
            req = WorkflowPlanRequest(
                episode=args.episode, confirmed_request_durations={}
            )
            value = _require(
                await get_workflow_plan(ToolRequest(req), scope, caller, services)
            )
            emit(value)
        elif action == "asset-inventory":
            await _cmd_workflow_asset_inventory(args, pm, services, caller)
        elif action == "plan-episodes":
            await _cmd_workflow_plan_episodes(args, pm, services, caller)
        elif action == "reset-planning":
            await _cmd_workflow_reset_planning(args, pm, services, caller)
        elif action == "retry-migration":
            await _cmd_workflow_retry_migration(args, pm, services, caller)
        return

    if group == "video-capabilities":
        scope = _project_scope(args.project, pm)
        if action == "get":
            value = _require(
                await get_video_capabilities(
                    ToolRequest(None), scope, caller, services
                )
            )
            emit(value)
        return

    if group == "batch":
        if action == "get":
            await _cmd_batch_get(args, pm, services, caller)
        elif action == "cancel":
            scope = _project_scope(args.project, pm)
            value = _require(
                await cancel_generation_batch(
                    ToolRequest(GenerationBatchToolRequest(batch_id=args.batch_id)),
                    scope,
                    caller,
                    services,
                )
            )
            emit(value)
        return

    if group == "media":
        if action == "submit":
            # video --dry-run 只走 tool_runtime 预览，不依赖媒体模块/worker。
            if not _MEDIA_AVAILABLE and not getattr(args, "dry_run", False):
                print("ERROR: 媒体生成模块不可用，无法执行真实 media submit", file=sys.stderr)
                sys.exit(1)
            await _cmd_media_submit(args, pm, services, caller)
        elif action == "pending-assets":
            if not _MEDIA_AVAILABLE:
                print("ERROR: 媒体生成模块不可用", file=sys.stderr)
                sys.exit(1)
            await _cmd_media_pending_assets(args, pm, services, caller)
        return

    if group == "demo":
        if action == "seed":
            await _cmd_demo_seed(args, pm, services, caller)
        return

    if group == "config":
        if action == "set":
            await _cmd_config_set(args, pm, services, caller)
        elif action == "setup-image":
            await _cmd_config_setup_image(args, pm, services, caller)
        elif action == "verify":
            await _cmd_config_verify(args, pm, services, caller)
        return

    if group == "draft":
        await _cmd_draft(args, pm, services, caller)
        return

    if group == "file":
        if action == "list":
            await _cmd_file_list(args, pm, services, caller)
        elif action == "read":
            await _cmd_file_read(args, pm, services, caller)
        return

    raise ValueError(f"未知子命令：{group} {action}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """构建 argparse 参数树。"""
    parser = argparse.ArgumentParser(
        prog="arcreel_cli",
        description="ArcReel 进程内 CLI 原型（路径 A）：复用确定性工具，不启动 Web 服务。",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出全部结果")
    sub = parser.add_subparsers(dest="group", required=True)

    # projects
    p_projects = sub.add_parser("projects", help="项目管理")
    ps = p_projects.add_subparsers(dest="action", required=True)
    ps.add_parser("list", help="列出全部项目")
    p_create = ps.add_parser("create", help="创建项目")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--title", default="")
    p_create.add_argument(
        "--content-mode", required=True, choices=["narration", "drama", "ad"]
    )
    p_create.add_argument(
        "--source-kind", required=True, choices=["novel", "screenplay"]
    )
    p_create.add_argument(
        "--generation-mode", required=True, choices=["storyboard", "reference_video"]
    )
    p_create.add_argument("--aspect-ratio", default="9:16")
    p_create.add_argument("--brief", default="")
    p_patch = ps.add_parser("patch", help="修改项目资产/settings/overview（对齐 MCP patch_project）")
    p_patch.add_argument("--project", required=True)
    p_patch.add_argument("--table", default=None, help="资产类型（character/scene/prop/product）")
    p_patch.add_argument("--entries-json", default=None, help="资产 upsert：{名称: 字段对象} JSON")
    p_patch.add_argument("--settings-json", default=None, help="顶层 settings：{字段: 值} JSON")
    p_patch.add_argument("--overview-json", default=None, help="项目概述：{字段: 值} JSON")
    p_rename = ps.add_parser("rename-asset", help="重命名资产并迁移引用（对齐 MCP rename_asset）")
    p_rename.add_argument("--project", required=True)
    p_rename.add_argument("--table", required=True)
    p_rename.add_argument("--old-name", required=True)
    p_rename.add_argument("--new-name", required=True)

    # source
    p_source = sub.add_parser("source", help="素材源管理")
    ss = p_source.add_subparsers(dest="action", required=True)
    ss_upload = ss.add_parser("upload", help="上传素材源文件")
    ss_upload.add_argument("--project", required=True)
    ss_upload.add_argument("--file", required=True)
    ss_upload.add_argument(
        "--on-conflict", default="fail", choices=["fail", "replace", "rename"]
    )
    ss_list = ss.add_parser("list", help="列出素材源文件")
    ss_list.add_argument("--project", required=True)
    ss_text = ss.add_parser("text", help="读取素材源文本")
    ss_text.add_argument("--project", required=True)
    ss_text.add_argument("--path", required=True)

    # content
    p_content = sub.add_parser("content", help="项目内容")
    cs = p_content.add_subparsers(dest="action", required=True)
    cs_get = cs.add_parser("get", help="获取项目内容")
    cs_get.add_argument("--project", required=True)

    # script-plan
    p_sp = sub.add_parser("script-plan", help="脚本规划")
    sps = p_sp.add_subparsers(dest="action", required=True)
    sps_get = sps.add_parser("get", help="获取脚本规划内容")
    sps_get.add_argument("--project", required=True)
    sps_get.add_argument("--episode", type=int, required=True)
    sps_gen = sps.add_parser("generate", help="生成剧本规划（对齐 MCP generate_script_plan）")
    sps_gen.add_argument("--project", required=True)
    sps_gen.add_argument("--episode", type=int, required=True)
    sps_gen.add_argument("--source", default=None, help="素材源文件名（可选）")
    sps_gen.add_argument("--instructions", default=None, help="附加指令")
    sps_gen.add_argument("--dry-run", action="store_true", help="只渲染提示词，不提交生成")
    sps_gen.add_argument("--scope", default="stale", choices=["stale", "all"], help="重写范围")
    sps_gen.add_argument("--entry-ids", default=None, help="逗号分隔条目 id（与 scope=all 互斥）")
    sps_gen.add_argument("--wait", action="store_true", help="启动进程内 worker 并轮询到终态")
    sps_gen.add_argument("--no-worker", action="store_true", help="仅入队，不启动进程内 worker")
    sps_gen.add_argument("--interval", type=float, default=5.0)
    sps_confirm = sps.add_parser("confirm", help="确认剧本规划评审门（对齐 MCP confirm_script_review）")
    sps_confirm.add_argument("--project", required=True)
    sps_confirm.add_argument("--episode", type=int, required=True)
    sps_convert = sps.add_parser("convert", help="规划机械转为正式剧本（对齐 MCP convert_script_plan）")
    sps_convert.add_argument("--project", required=True)
    sps_convert.add_argument("--episode", type=int, required=True)
    sps_convert.add_argument("--entry-ids", default=None, help="逗号分隔：要采用新内容的失效条目 id")
    sps_rebuild = sps.add_parser("rebuild-complete", help="完成过期规划重建（对齐 MCP complete_script_plan_rebuild）")
    sps_rebuild.add_argument("--project", required=True)
    sps_rebuild.add_argument("--episode", type=int, required=True)
    sps_rebuild.add_argument("--revision", default=None, help="expected_stale_script_plan_revision；'-' 表示 None")
    sps_seed = sps.add_parser(
        "seed",
        help="离线（无 LLM）按原文切分出结构化 script_plan 并落盘（narration / drama / reference_video）",
    )
    sps_seed.add_argument("--project", required=True)
    sps_seed.add_argument("--episode", type=int, default=1)
    sps_seed.add_argument(
        "--source", default=None, help="本集派生源文缺失时改用的源文件名（source/ 目录下）"
    )
    sps_seed.add_argument(
        "--segments",
        type=int,
        default=None,
        help="narration / drama：合并成 N 个分镜；缺省按句末标点（narration）或动作行与空行（drama）切",
    )
    sps_seed.add_argument(
        "--duration",
        type=int,
        default=None,
        help="narration / drama：每镜秒数；须落在当前可用档位内，drama 缺省按口播量取最短够用档",
    )
    sps_seed.add_argument("--title", default=None, help="drama：剧集标题；缺省按「第N集」")
    sps_seed.add_argument(
        "--units-file",
        default=None,
        help="reference_video：外部写好的扁平 units JSON（{\"units\": [{duration_seconds, source_text, text}]}，不含 unit_id）；缺省按源文自动切分",
    )
    sps_seed.add_argument("--dry-run", action="store_true", help="只打印将写入的内容，不落盘")

    # episode-script
    p_es = sub.add_parser("episode-script", help="分集剧本")
    ess = p_es.add_subparsers(dest="action", required=True)
    ess_get = ess.add_parser("get", help="获取分集剧本")
    ess_get.add_argument("--project", required=True)
    ess_get.add_argument("--script", required=True)
    ess_seed = ess.add_parser(
        "seed", help="离线（无 LLM）按已确认的 script_plan 合成正式剧本并登记产物账本"
    )
    ess_seed.add_argument("--project", required=True)
    ess_seed.add_argument("--episode", type=int, required=True)
    ess_seed.add_argument("--title", default=None, help="剧集标题；缺省按「第N集」")
    ess_seed.add_argument("--dry-run", action="store_true", help="只打印将写入的剧本，不落盘")
    ess_gen = ess.add_parser("generate", help="生成正式剧本（对齐 MCP generate_episode_script）")
    ess_gen.add_argument("--project", required=True)
    ess_gen.add_argument("--episode", type=int, required=True)
    ess_gen.add_argument("--source", default=None, help="素材源文件名（可选）")
    ess_gen.add_argument("--instructions", default=None, help="附加指令")
    ess_gen.add_argument("--dry-run", action="store_true", help="只渲染提示词，不提交生成")
    ess_gen.add_argument("--wait", action="store_true", help="启动进程内 worker 并轮询到终态")
    ess_gen.add_argument("--no-worker", action="store_true", help="仅入队，不启动进程内 worker")
    ess_gen.add_argument("--interval", type=float, default=5.0)
    ess_patch = ess.add_parser("patch", help="原子批量编辑剧本（对齐 MCP patch_episode_script）")
    ess_patch.add_argument("--project", required=True)
    ess_patch.add_argument("--script", required=True)
    ess_patch.add_argument("--base-revision", required=True, help="sha256-v1:<64位hex>")
    ess_patch.add_argument("--ops-json", required=True, help="update/insert/remove/split 操作 JSON 数组")
    ess_retitle = ess.add_parser("retitle", help="修改剧本标题（对齐 MCP patch_episode_meta）")
    ess_retitle.add_argument("--project", required=True)
    ess_retitle.add_argument("--script", required=True)
    ess_retitle.add_argument("--value", required=True, help="新标题")
    ess_preview = ess.add_parser("preview", help="预览条目最终提示词（对齐 MCP get_prompt_preview）")
    ess_preview.add_argument("--project", required=True)
    ess_preview.add_argument("--script", required=True)
    ess_preview.add_argument("--item-id", required=True)

    # reference-video
    p_rv = sub.add_parser(
        "reference-video",
        help="参考生视频调试/预览（只读，不调用视频供应商）",
    )
    rvs = p_rv.add_subparsers(dest="action", required=True)
    rv_preview = rvs.add_parser(
        "prompt-preview",
        help="预览单个 video unit 真正将提交给 Provider 的最终 Prompt",
    )
    rv_preview.add_argument("--project", required=True)
    rv_preview.add_argument("--script", required=True, help="正式剧本文件名，如 episode_1.json")
    rv_preview.add_argument("--unit-id", required=True, help="video_units[].unit_id")
    rv_preview.add_argument(
        "--prompt-compiler",
        default="auto",
        choices=["auto", "h3_ref2va", "raw"],
        help="auto=按模型自动；h3_ref2va=强制 H3 六段式；raw=跳过 H3 编译",
    )
    rv_preview.add_argument(
        "--reference-image-label",
        action="append",
        default=None,
        help="手工指定一项 reference_image_label；可重复传入，顺序必须与实际 Provider 参考图一致",
    )
    rv_preview.add_argument(
        "--reference-image-labels-file",
        default=None,
        help="UTF-8 文本文件，一行一个 reference_image_label；与 --reference-image-label 二选一",
    )
    rv_preview.add_argument(
        "--prompt",
        default=None,
        help="临时覆盖该 unit 正文，仅预览、不落盘；与 --prompt-file 二选一",
    )
    rv_preview.add_argument(
        "--prompt-file",
        default=None,
        help="从 UTF-8 文件读取临时 unit 正文，仅预览、不落盘",
    )
    rv_preview.add_argument(
        "--show-rendered",
        action="store_true",
        help="若 H3 编译前后不同，同时显示 ArcReel 原始 rendered provider prompt",
    )

    # workflow
    p_wf = sub.add_parser("workflow", help="工作流规划")
    wfs = p_wf.add_subparsers(dest="action", required=True)
    wfs_get = wfs.add_parser("get", help="获取工作流规划")
    wfs_get.add_argument("--project", required=True)
    wfs_get.add_argument("--episode", type=int, default=None)
    wfs_ai = wfs.add_parser("asset-inventory", help="提交资产盘点（对齐 MCP complete_asset_inventory）")
    wfs_ai.add_argument("--project", required=True)
    wfs_ai.add_argument("--scope-kind", default="all", choices=["all", "files"])
    wfs_ai.add_argument("--files", default=None, help="scope-kind=files 时的逗号分隔文件名")
    wfs_ai.add_argument("--revision", default=None, help="expected_source_revision（sha256-v1:...）；缺省按当前源文现算")
    wfs_ai.add_argument("--entries-json", default=None, help="盘点条目 JSON（可选）")
    wfs_ai.add_argument(
        "--entries-file",
        default=None,
        help='盘点条目 JSON 文件（可选，如 {"characters": {"角色名": {"description": "..."}}}）；优先于 --entries-json',
    )
    wfs_pe = wfs.add_parser("plan-episodes", help="LLM 规划分集（对齐 MCP plan_episodes）")
    wfs_pe.add_argument("--project", required=True)
    wfs_pe.add_argument("--instructions", default=None)
    wfs_pe.add_argument("--wait", action="store_true", help="启动进程内 worker 并轮询到终态")
    wfs_pe.add_argument("--no-worker", action="store_true", help="仅入队，不启动进程内 worker")
    wfs_pe.add_argument("--interval", type=float, default=5.0)
    wfs_rp = wfs.add_parser("reset-planning", help="重置分集规划（对齐 MCP reset_episode_planning）")
    wfs_rp.add_argument("--project", required=True)
    wfs_rp.add_argument("--from-episode", type=int, required=True)
    wfs_rp.add_argument("--confirm-consumed", action="store_true")
    wfs_rm = wfs.add_parser("retry-migration", help="重试项目数据迁移（对齐 MCP retry_project_migration）")
    wfs_rm.add_argument("--project", required=True)

    # video-capabilities
    p_vc = sub.add_parser("video-capabilities", help="视频能力")
    vcs = p_vc.add_subparsers(dest="action", required=True)
    vcs_get = vcs.add_parser("get", help="获取视频能力")
    vcs_get.add_argument("--project", required=True)

    # batch
    p_batch = sub.add_parser("batch", help="生成批次")
    bs = p_batch.add_subparsers(dest="action", required=True)
    bs_get = bs.add_parser("get", help="获取/轮询生成批次")
    bs_get.add_argument("--project", required=True)
    bs_get.add_argument("--batch-id", required=True)
    bs_get.add_argument("--wait", action="store_true", help="轮询直到终态")
    bs_get.add_argument("--interval", type=float, default=5.0, help="轮询间隔秒数")
    bs_cancel = bs.add_parser("cancel", help="取消生成批次")
    bs_cancel.add_argument("--project", required=True)
    bs_cancel.add_argument("--batch-id", required=True)

    # media
    p_media = sub.add_parser("media", help="媒体生成（提交 + 可选进程内 worker + 轮询）")
    ms = p_media.add_subparsers(dest="action", required=True)
    ms_submit = ms.add_parser("submit", help="提交生成并（--wait 时）启动 worker 等待出片")
    ms_submit.add_argument("--project", required=True)
    ms_submit.add_argument(
        "--type",+        default="storyboard",
        choices=["storyboard", "video", "narration_audio", "assets", "grid"],
        help="媒体类型",
    )
    ms_submit.add_argument(
        "--script", default=None, help="剧本文件名，如 episode_1.json（storyboard/video/narration_audio/grid 用）"
    )
    ms_submit.add_argument("--episode", type=int, default=None, help="video --video-scope=episode 时的集号")
    ms_submit.add_argument("--segment-ids", default=None, help="逗号分隔单元 ID（storyboard/narration_audio 过滤）")
    ms_submit.add_argument(
        "--video-scope", default="episode", choices=["episode", "scene", "all", "selected"]
    )
    ms_submit.add_argument("--video-ids", default=None, help="逗号分隔 ID（video scene/selected 用）")
    ms_submit.add_argument("--force", action="store_true", help="video：强制重生（默认复用已有成片）")
    ms_submit.add_argument(
        "--dry-run",
        action="store_true",
        help="video：只展开目标 unit 的最终 Provider Prompt，不入队、不启动 worker、不调用供应商",
    )
    ms_submit.add_argument(
        "--prompt-compiler",
        default="auto",
        choices=["auto", "h3_ref2va", "raw"],
        help="video dry-run：auto=按模型自动；h3_ref2va=强制 H3；raw=跳过 H3 编译",
    )
    ms_submit.add_argument(
        "--reference-image-label",
        action="append",
        default=None,
        help="video 单 unit dry-run：手工 reference_image_label，可重复；多 unit 时禁止",
    )
    ms_submit.add_argument(
        "--reference-image-labels-file",
        default=None,
        help="video 单 unit dry-run：一行一个 reference_image_label；多 unit 时禁止",
    )
    ms_submit.add_argument(
        "--prompt",
        default=None,
        help="video 单 unit dry-run：临时覆盖 unit 正文，仅预览、不落盘",
    )
    ms_submit.add_argument(
        "--prompt-file",
        default=None,
        help="video 单 unit dry-run：从 UTF-8 文件读取临时 unit 正文",
    )
    ms_submit.add_argument(
        "--show-rendered",
        action="store_true",
        help="video dry-run：同时显示 H3 编译前的 ArcReel rendered prompt（若可用）",
    )
    ms_submit.add_argument("--asset-type", default=None, help="assets：资产类型（character/scene/prop…）")
    ms_submit.add_argument("--asset-names", default=None, help="逗号分隔资产名（assets，需配合 --asset-type）")
    ms_submit.add_argument("--asset-all", action="store_true", help="assets：生成全部缺失资产图")
    ms_submit.add_argument("--scene-ids", default=None, help="逗号分隔场景 ID（grid 用）")
    ms_submit.add_argument("--wait", action="store_true", help="启动进程内 worker 并轮询直到终态出片")
    ms_submit.add_argument("--interval", type=float, default=5.0, help="轮询间隔秒数")
    ms_submit.add_argument(
        "--no-worker", action="store_true", help="不启动进程内 worker，仅入队（配合外部运行的 Web 服务）"
    )
    ms_pending = ms.add_parser("pending-assets", help="列出待生成资产图（对齐 MCP list_pending_assets）")
    ms_pending.add_argument("--project", required=True)
    ms_pending.add_argument("--asset-type", default=None, help="资产类型；省略则汇总所有类型")

    # demo
    p_demo = sub.add_parser("demo", help="演示脚手架（写最小样例剧本）")
    ds = p_demo.add_subparsers(dest="action", required=True)
    ds_seed = ds.add_parser("seed", help="写入最小样例剧本到项目的 scripts/ 目录")
    ds_seed.add_argument("--project", required=True)
    ds_seed.add_argument("--script-name", default="episode_1.json", help="剧本文件名")

    # config
    p_cfg = sub.add_parser("config", help="Provider 配置与校验")
    cs = p_cfg.add_subparsers(dest="action", required=True)
    cs_set = cs.add_parser("set", help="通用 provider 配置键值写入（落 DB）")
    cs_set.add_argument("--provider-id", required=True)
    cs_set.add_argument("--key", required=True)
    cs_set.add_argument("--value", required=True)
    cs_img = cs.add_parser("setup-image", help="一键配置图像 provider（api_key 必填）")
    cs_img.add_argument("--provider-id", required=True)
    cs_img.add_argument("--api-key", default=None, help="API Key；缺省时读环境变量 ARCREEL_API_KEY")
    cs_img.add_argument("--base-url", default=None, help="可选：自定义 base URL")
    cs_img.add_argument("--model", default=None, help="可选：指定模型 id")
    cs_verify = cs.add_parser("verify", help="列出 provider 就绪状态并（可选）验证项目图像后端")
    cs_verify.add_argument("--project", default=None, help="可选：验证该项目的图像后端可被解析")

    # draft
    _doc_types = [
        "drama_script_plan",
        "narration_script_plan",
        "reference_script_plan",
        "reference_prompt_authoring",
    ]
    p_draft = sub.add_parser(
        "draft", help="剧本规划草稿工作流（对齐 MCP open/patch/promote/discard_draft）"
    )
    ds2 = p_draft.add_subparsers(dest="action", required=True)
    d_open = ds2.add_parser("open", help="打开草稿（返回 base_revision 与正文）")
    d_open.add_argument("--project", required=True)
    d_open.add_argument("--episode", type=int, required=True)
    d_open.add_argument("--doc-type", required=True, choices=_doc_types)
    d_open.add_argument("--source", default=None)
    d_patch = ds2.add_parser("patch", help="原子替换草稿正文")
    d_patch.add_argument("--project", required=True)
    d_patch.add_argument("--episode", type=int, required=True)
    d_patch.add_argument("--doc-type", required=True, choices=_doc_types)
    d_patch.add_argument("--base-revision", required=True)
    d_patch.add_argument("--content-json", required=True, help="草稿正文 JSON 对象")
    d_patch.add_argument("--accept-formal-revision", default=None)
    d_patch.add_argument("--accepts-formal-revision", action="store_true")
    d_patch.add_argument("--source", default=None)
    d_patch.add_argument("--updates-source", action="store_true")
    d_promote = ds2.add_parser("promote", help="校验并晋升草稿为正式文档")
    d_promote.add_argument("--project", required=True)
    d_promote.add_argument("--episode", type=int, required=True)
    d_promote.add_argument("--doc-type", required=True, choices=_doc_types)
    d_promote.add_argument("--base-revision", required=True)
    d_discard = ds2.add_parser("discard", help="丢弃草稿")
    d_discard.add_argument("--project", required=True)
    d_discard.add_argument("--episode", type=int, required=True)
    d_discard.add_argument("--doc-type", required=True, choices=_doc_types)
    d_discard.add_argument("--base-revision", required=True)

    # file
    p_file = sub.add_parser(
        "file", help="项目业务文件（对齐 MCP list_project_files/read_project_file）"
    )
    fs = p_file.add_subparsers(dest="action", required=True)
    fs_list = fs.add_parser("list", help="列出项目业务文件")
    fs_list.add_argument("--project", required=True)
    fs_read = fs.add_parser("read", help="读取项目业务文件")
    fs_read.add_argument("--project", required=True)
    fs_read.add_argument("--path", required=True)

    return parser.parse_args(argv)


async def main() -> None:
    """CLI 入口：启动引导 -> 分发 -> 关闭数据库。"""
    global JSON_OUTPUT
    args = parse_args()
    JSON_OUTPUT = args.json

    try:
        await init_db()  # 建表 + 初始化 async_session_factory
        pm = get_project_manager()  # 自动读 ARCREEL_DATA_DIR / AI_ANIME_PROJECTS
        services = Services(
            projects=pm,
            workflow_planner=workflow_planner.get_workflow_planner(pm),
            capabilities=ConfigResolver(async_session_factory),
        )
        caller = CallerContext(user_id=DEFAULT_USER_ID, source="mcp")
    except Exception as exc:
        print(
            "启动失败：无法初始化数据库或项目管理器。\n"
            "请确认已在 ArcReel 根目录运行、已执行 `uv sync` 安装依赖，\n"
            "且 ARCREEL_DATA_DIR / AI_ANIME_PROJECTS 可访问。\n"
            f"原因：{exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        await dispatch(args, pm, services, caller)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
