#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

V6_MARKER = "canonical_director"
BASE_COMMIT = "a0a2521c90bb80f38cda2c12c9c06669d2e7b095"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one source anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def git_output(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def verify(root: Path, skip_git_check: bool) -> None:
    if not skip_git_check:
        try:
            head = git_output(root, "rev-parse", "HEAD")
            subprocess.check_call(
                ["git", "merge-base", "--is-ancestor", BASE_COMMIT, head],
                cwd=root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            raise RuntimeError(
                f"repository must contain {BASE_COMMIT} as an ancestor"
            ) from exc

    execution = root / "lib/reference_video/h3_prompt_execution.py"
    if not execution.exists() or V6_MARKER not in execution.read_text(encoding="utf-8"):
        raise RuntimeError("V6 must be applied before V6.1")


def apply(root: Path) -> None:
    execution = root / "lib/reference_video/h3_prompt_execution.py"
    replace_once(
        execution,
        "from dataclasses import dataclass\nfrom typing import Any\n",
        "from dataclasses import dataclass\nimport hashlib\nimport hmac\nimport re\nfrom typing import Any\n",
        "execution-hash-imports",
    )
    anchor = '''class ProviderPromptCompilation:
    provider_prompt: str
    rendered_prompt: str
    model_id: str | None
    prompt_compiler: PromptCompilerMode
    compiler_applied: bool
    generation_mode: str
    duration_seconds: int
    reference_source_names: tuple[str, ...]
    reference_image_labels: tuple[str, ...]
    max_prompt_chars: int | None
'''
    helper = anchor + '''

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def provider_prompt_sha256(prompt: str) -> str:
    """Stable fingerprint of the exact UTF-8 provider prompt text."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def assert_provider_prompt_matches_preview(
    *,
    provider_prompt: str,
    expected_sha256: object | None,
) -> None:
    """Refuse provider submission if the prompt differs from the previewed text."""
    if expected_sha256 is None:
        return
    expected = str(expected_sha256).strip().lower()
    if not _SHA256_RE.fullmatch(expected):
        raise H3PromptCompileError(
            "expected_provider_prompt_sha256 must be a 64-character lowercase SHA-256 hex digest"
        )
    actual = provider_prompt_sha256(provider_prompt)
    if not hmac.compare_digest(actual, expected):
        raise H3PromptCompileError(
            "final provider prompt changed after preview; preview again before generation"
        )
'''
    replace_once(execution, anchor, helper, "execution-hash-helper")

    preview_file = root / "lib/reference_video/prompt_preview.py"
    replace_once(
        preview_file,
        "from lib.reference_video.h3_prompt_execution import ProviderPromptCompilation\n",
        "from lib.reference_video.h3_prompt_execution import (\n"
        "    ProviderPromptCompilation,\n"
        "    provider_prompt_sha256,\n"
        ")\n",
        "preview-hash-import",
    )
    replace_once(
        preview_file,
        '        "provider_prompt": prompt,\n        "rendered_prompt": compilation.rendered_prompt,\n',
        '        "provider_prompt": prompt,\n        "provider_prompt_sha256": provider_prompt_sha256(prompt),\n        "rendered_prompt": compilation.rendered_prompt,\n',
        "preview-hash-field",
    )

    router = root / "server/routers/reference_videos.py"
    replace_once(
        router,
        '''    # Request-scoped Canonical Director input. It may be a full episode payload,
    # {unit, registries} bundle, or one unit object. It is never persisted into the script.
    canonical_director: dict[str, Any] | None = None
''',
        '''    # Request-scoped Canonical Director input. It may be a full episode payload,
    # {unit, registries} bundle, or one unit object. It is never persisted into the script.
    canonical_director: dict[str, Any] | None = None
    # If supplied, worker must prove that the exact prompt submitted to the provider
    # is byte-for-byte identical (UTF-8 text) to the previewed provider_prompt.
    expected_provider_prompt_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{64}$",
    )
''',
        "router-expected-hash-field",
    )
    replace_once(
        router,
        '''                **(
                    {"canonical_director": request_body.canonical_director}
                    if request_body.canonical_director is not None
                    else {}
                ),
            },
''',
        '''                **(
                    {"canonical_director": request_body.canonical_director}
                    if request_body.canonical_director is not None
                    else {}
                ),
                **(
                    {"expected_provider_prompt_sha256": request_body.expected_provider_prompt_sha256.lower()}
                    if request_body.expected_provider_prompt_sha256 is not None
                    else {}
                ),
            },
''',
        "router-expected-hash-payload",
    )

    queue = root / "lib/generation_queue.py"
    replace_once(
        queue,
        '_REFERENCE_VIDEO_ENQUEUE_PAYLOAD_KEYS = frozenset({"script_file", "reference_request_options"})\n',
        '''_REFERENCE_VIDEO_ENQUEUE_PAYLOAD_KEYS = frozenset(
    {
        "script_file",
        "reference_request_options",
        "reference_image_labels",
        "prompt_compiler",
        "canonical_director",
        "expected_provider_prompt_sha256",
    }
)
_REFERENCE_PROMPT_REQUEST_KEYS = frozenset(
    {
        "reference_image_labels",
        "prompt_compiler",
        "canonical_director",
        "expected_provider_prompt_sha256",
    }
)
''',
        "queue-preserve-compiler-facts",
    )
    narration_anchor = '''def _narration_request_facts(task_type: str, payload: dict[str, Any] | None) -> dict[str, object] | None:
    key = _NARRATION_REQUEST_KEY_BY_TASK_TYPE.get(task_type)
    if key is None:
        return None

    from lib.narration_delivery import NarrationDeliveryRequestOptions

    return NarrationDeliveryRequestOptions.from_payload(payload or {}, key=key).to_payload()
'''
    narration_new = narration_anchor + '''


def _reference_prompt_request_facts(
    task_type: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Request-scoped compiler facts that must match before reusing an active task."""
    if task_type != "reference_video":
        return None
    source = payload or {}
    facts = {key: source[key] for key in _REFERENCE_PROMPT_REQUEST_KEYS if key in source}
    return facts or None
'''
    replace_once(queue, narration_anchor, narration_new, "queue-prompt-facts-helper")
    replace_once(
        queue,
        '''        requested_facts = _narration_request_facts(task_type, payload)
        text_request_facts = _text_request_facts(task_type, payload)

        def _guard_deduped(existing_payload: dict[str, Any], existing_task_id: str) -> None:
''',
        '''        requested_facts = _narration_request_facts(task_type, payload)
        text_request_facts = _text_request_facts(task_type, payload)
        reference_prompt_request_facts = _reference_prompt_request_facts(task_type, payload)

        def _guard_deduped(existing_payload: dict[str, Any], existing_task_id: str) -> None:
''',
        "queue-dedupe-facts-bind",
    )
    replace_once(
        queue,
        '''            if (
                text_request_facts is not None
                and _text_request_facts(task_type, existing_payload) != text_request_facts
            ):
                raise ActiveTaskRequestConflict(resource_id=resource_id, existing_task_id=existing_task_id)
''',
        '''            if (
                text_request_facts is not None
                and _text_request_facts(task_type, existing_payload) != text_request_facts
            ):
                raise ActiveTaskRequestConflict(resource_id=resource_id, existing_task_id=existing_task_id)
            if (
                reference_prompt_request_facts is not None
                and _reference_prompt_request_facts(task_type, existing_payload)
                != reference_prompt_request_facts
            ):
                raise ActiveTaskRequestConflict(resource_id=resource_id, existing_task_id=existing_task_id)
''',
        "queue-dedupe-prompt-facts-guard",
    )

    tasks = root / "server/services/reference_video_tasks.py"
    replace_once(
        tasks,
        '''from lib.reference_video.h3_prompt_execution import (
    compile_reference_video_provider_prompt,
    should_compile_reference_video_h3,
)
''',
        '''from lib.reference_video.h3_prompt_execution import (
    assert_provider_prompt_matches_preview,
    compile_reference_video_provider_prompt,
    should_compile_reference_video_h3,
)
''',
        "tasks-preview-lock-import",
    )
    replace_once(
        tasks,
        '''    provider_prompt = prompt_compilation.provider_prompt
    reference_audio_files, reference_audio_targets = _build_reference_audio_wiring(
''',
        '''    provider_prompt = prompt_compilation.provider_prompt
    # Hard pre-provider invariant: a preview-locked generation may never silently
    # submit different text. Any script/asset/model/compiler drift becomes a free
    # pre-submit failure instead of a paid generation with an unseen prompt.
    assert_provider_prompt_matches_preview(
        provider_prompt=provider_prompt,
        expected_sha256=payload.get("expected_provider_prompt_sha256"),
    )
    reference_audio_files, reference_audio_targets = _build_reference_audio_wiring(
''',
        "tasks-preview-lock-check",
    )

    ts = root / "frontend/src/types/reference-video.ts"
    replace_once(
        ts,
        '''  /** Request-scoped structured director data; not persisted to the script. */
  canonical_director?: Record<string, unknown>;
''',
        '''  /** Request-scoped structured director data; not persisted to the script. */
  canonical_director?: Record<string, unknown>;
  /** Lock generation to the exact provider_prompt returned by Preview. */
  expected_provider_prompt_sha256?: string;
''',
        "frontend-request-hash",
    )
    replace_once(
        ts,
        '''export interface ReferencePromptPreview {
  provider_prompt: string;
  rendered_prompt: string;
''',
        '''export interface ReferencePromptPreview {
  provider_prompt: string;
  provider_prompt_sha256: string;
  rendered_prompt: string;
''',
        "frontend-preview-hash",
    )

    dialog = root / "frontend/src/components/canvas/reference/PromptPreviewDialog.tsx"
    replace_once(
        dialog,
        '''  error?: string | null;
  onClose: () => void;
}
''',
        '''  error?: string | null;
  onClose: () => void;
  onGenerate?: () => void;
  generateDisabled?: boolean;
}
''',
        "dialog-generate-props",
    )
    replace_once(
        dialog,
        '''  preview,
  error,
  onClose,
}: PromptPreviewDialogProps) {
''',
        '''  preview,
  error,
  onClose,
  onGenerate,
  generateDisabled = false,
}: PromptPreviewDialogProps) {
''',
        "dialog-generate-destructure",
    )
    replace_once(
        dialog,
        '''          <SecondaryButton size="sm" onClick={onClose} disabled={loading}>
            关闭
          </SecondaryButton>
''',
        '''          {preview && onGenerate && (
            <button
              type="button"
              onClick={onGenerate}
              disabled={loading || generateDisabled}
              title={generateDisabled ? "请先保存当前编辑内容，再使用已预览 Prompt 生成" : undefined}
              className="focus-ring inline-flex h-8 items-center justify-center rounded-md border border-[var(--color-accent)]/45 bg-[var(--color-accent-soft)] px-3 text-[11.5px] font-semibold text-[var(--color-accent-2)] hover:bg-[var(--color-accent-soft)]/80 disabled:cursor-not-allowed disabled:opacity-45"
            >
              使用此 Prompt 生成
            </button>
          )}
          <SecondaryButton size="sm" onClick={onClose} disabled={loading}>
            关闭
          </SecondaryButton>
''',
        "dialog-generate-button",
    )

    canvas = root / "frontend/src/components/canvas/reference/ReferenceVideoCanvas.tsx"
    replace_once(
        canvas,
        '''  const [promptPreview, setPromptPreview] = useState<ReferencePromptPreview | null>(null);
  const [promptPreviewError, setPromptPreviewError] = useState<string | null>(null);
''',
        '''  const [promptPreview, setPromptPreview] = useState<ReferencePromptPreview | null>(null);
  const [promptPreviewUnitId, setPromptPreviewUnitId] = useState<string | null>(null);
  const [promptPreviewError, setPromptPreviewError] = useState<string | null>(null);
''',
        "canvas-preview-unit-state",
    )
    replace_once(
        canvas,
        '''  const handleReferenceImageLabelsChange = useCallback(
    (value: string) => {
      if (!selected) return;
      const key = draftKey(projectName, episode, selected.unit_id);
      setReferenceImageLabelDrafts((current) =>
        value.trim() ? { ...current, [key]: value } : withoutKey(current, key),
      );
    },
    [selected, projectName, episode],
  );
''',
        '''  const handleReferenceImageLabelsChange = useCallback(
    (value: string) => {
      if (!selected) return;
      const key = draftKey(projectName, episode, selected.unit_id);
      setReferenceImageLabelDrafts((current) =>
        value.trim() ? { ...current, [key]: value } : withoutKey(current, key),
      );
      if (promptPreviewUnitId === selected.unit_id) {
        setPromptPreview(null);
        setPromptPreviewUnitId(null);
      }
    },
    [selected, projectName, episode, promptPreviewUnitId],
  );
''',
        "canvas-labels-invalidate-preview",
    )
    replace_once(
        canvas,
        '''  const handlePromptCompilerChange = useCallback(
    (value: ReferencePromptCompiler) => {
      if (!selected) return;
      const key = draftKey(projectName, episode, selected.unit_id);
      setPromptCompilerDrafts((current) =>
        value === DEFAULT_REFERENCE_PROMPT_COMPILER
          ? withoutKey(current, key)
          : { ...current, [key]: value },
      );
    },
    [selected, projectName, episode],
  );
''',
        '''  const handlePromptCompilerChange = useCallback(
    (value: ReferencePromptCompiler) => {
      if (!selected) return;
      const key = draftKey(projectName, episode, selected.unit_id);
      setPromptCompilerDrafts((current) =>
        value === DEFAULT_REFERENCE_PROMPT_COMPILER
          ? withoutKey(current, key)
          : { ...current, [key]: value },
      );
      if (promptPreviewUnitId === selected.unit_id) {
        setPromptPreview(null);
        setPromptPreviewUnitId(null);
      }
    },
    [selected, projectName, episode, promptPreviewUnitId],
  );
''',
        "canvas-compiler-invalidate-preview",
    )
    replace_once(
        canvas,
        '''    (unitId: string): Pick<
      ReferenceGenerationRequestOptions,
      "reference_image_labels" | "prompt_compiler"
    > => {
      const key = draftKey(projectName, episode, unitId);
      const labels = parseReferenceImageLabels(referenceImageLabelDrafts[key] ?? "");
      const compiler = promptCompilerDrafts[key] ?? DEFAULT_REFERENCE_PROMPT_COMPILER;
      return {
        ...(labels ? { reference_image_labels: labels } : {}),
        ...(compiler === DEFAULT_REFERENCE_PROMPT_COMPILER ? {} : { prompt_compiler: compiler }),
      };
    },
    [projectName, episode, referenceImageLabelDrafts, promptCompilerDrafts],
  );
''',
        '''    (unitId: string): Pick<
      ReferenceGenerationRequestOptions,
      "reference_image_labels" | "prompt_compiler" | "expected_provider_prompt_sha256"
    > => {
      const key = draftKey(projectName, episode, unitId);
      const labels = parseReferenceImageLabels(referenceImageLabelDrafts[key] ?? "");
      const compiler = promptCompilerDrafts[key] ?? DEFAULT_REFERENCE_PROMPT_COMPILER;
      const expectedHash =
        promptPreview && promptPreviewUnitId === unitId
          ? promptPreview.provider_prompt_sha256
          : undefined;
      return {
        ...(labels ? { reference_image_labels: labels } : {}),
        ...(compiler === DEFAULT_REFERENCE_PROMPT_COMPILER ? {} : { prompt_compiler: compiler }),
        ...(expectedHash ? { expected_provider_prompt_sha256: expectedHash } : {}),
      };
    },
    [
      projectName,
      episode,
      referenceImageLabelDrafts,
      promptCompilerDrafts,
      promptPreview,
      promptPreviewUnitId,
    ],
  );
''',
        "canvas-generation-preview-lock",
    )
    replace_once(
        canvas,
        '''  const handlePromptChange = useCallback(
    (next: string) => {
      if (!selected) return;
      const key = draftKey(projectName, episode, selected.unit_id);
      const baseText = selected.text;
''',
        '''  const handlePromptChange = useCallback(
    (next: string) => {
      if (!selected) return;
      if (promptPreviewUnitId === selected.unit_id) {
        setPromptPreview(null);
        setPromptPreviewUnitId(null);
      }
      const key = draftKey(projectName, episode, selected.unit_id);
      const baseText = selected.text;
''',
        "canvas-text-invalidate-preview",
    )
    replace_once(
        canvas,
        '''    [selected, projectName, episode],
  );

  const currentText = useMemo(() => {
''',
        '''    [selected, projectName, episode, promptPreviewUnitId],
  );

  const currentText = useMemo(() => {
''',
        "canvas-text-handler-deps",
    )
    replace_once(
        canvas,
        '''    const unitId = selected.unit_id;
    setPromptPreviewOpen(true);
    setPromptPreviewLoading(true);
    setPromptPreviewError(null);
    setPromptPreview(null);
''',
        '''    const unitId = selected.unit_id;
    setPromptPreviewOpen(true);
    setPromptPreviewLoading(true);
    setPromptPreviewError(null);
    setPromptPreview(null);
    setPromptPreviewUnitId(unitId);
''',
        "canvas-preview-unit-bind",
    )
    replace_once(
        canvas,
        '''      <PromptPreviewDialog
        open={promptPreviewOpen}
        loading={promptPreviewLoading}
        preview={promptPreview}
        error={promptPreviewError}
        onClose={() => setPromptPreviewOpen(false)}
      />
''',
        '''      <PromptPreviewDialog
        open={promptPreviewOpen}
        loading={promptPreviewLoading}
        preview={promptPreview}
        error={promptPreviewError}
        generateDisabled={isDirty || !selected || promptPreviewUnitId !== selected?.unit_id}
        onGenerate={() => {
          if (!selected || !promptPreview) return;
          setPromptPreviewOpen(false);
          void handleGenerate(selected.unit_id);
        }}
        onClose={() => setPromptPreviewOpen(false)}
      />
''',
        "canvas-preview-exact-generate",
    )

    test_file = root / "tests/unit/test_h3_preview_runtime_lock.py"
    test_file.write_text('''from __future__ import annotations

import pytest

from lib.generation_queue import GenerationQueue, reference_video_enqueue_payload
from lib.reference_video.h3_prompt_execution import (
    H3PromptCompileError,
    ProviderPromptCompilation,
    assert_provider_prompt_matches_preview,
    provider_prompt_sha256,
)
from lib.reference_video.prompt_preview import build_reference_prompt_preview_payload


def test_preview_fingerprint_hashes_exact_provider_prompt() -> None:
    compilation = ProviderPromptCompilation(
        provider_prompt="subject_definitions:\\n完整 Prompt",
        rendered_prompt="legacy",
        model_id="minimax_h3_zm_u24",
        prompt_compiler="auto",
        compiler_applied=True,
        generation_mode="t2va",
        duration_seconds=8,
        reference_source_names=(),
        reference_image_labels=(),
        max_prompt_chars=7000,
    )
    payload = build_reference_prompt_preview_payload(compilation)
    assert payload["provider_prompt_sha256"] == provider_prompt_sha256(payload["provider_prompt"])


def test_runtime_preview_lock_accepts_exact_text_and_rejects_any_change() -> None:
    prompt = "A\\nB\\nC"
    expected = provider_prompt_sha256(prompt)
    assert_provider_prompt_matches_preview(provider_prompt=prompt, expected_sha256=expected)
    with pytest.raises(H3PromptCompileError, match="changed after preview"):
        assert_provider_prompt_matches_preview(
            provider_prompt=prompt + " ",
            expected_sha256=expected,
        )


def test_reference_queue_payload_preserves_v6_compiler_facts() -> None:
    canonical = {"unit": {"unit_id": "E01-U06"}, "registries": {}}
    payload = reference_video_enqueue_payload(
        {
            "reference_request_options": {"narration_delivery": "post_production"},
            "reference_image_labels": ["沈知意", "陆念"],
            "prompt_compiler": "auto",
            "canonical_director": canonical,
            "expected_provider_prompt_sha256": "a" * 64,
            "discard_me": "x",
        },
        script_file="scripts/episode_1.json",
    )
    assert payload["reference_image_labels"] == ["沈知意", "陆念"]
    assert payload["prompt_compiler"] == "auto"
    assert payload["canonical_director"] == canonical
    assert payload["expected_provider_prompt_sha256"] == "a" * 64
    assert "discard_me" not in payload


async def test_active_reference_task_rejects_a_different_preview_lock(db_factory) -> None:
    queue = GenerationQueue(session_factory=db_factory)
    base = {
        "reference_request_options": {"narration_delivery": "post_production"},
        "prompt_compiler": "auto",
        "expected_provider_prompt_sha256": "a" * 64,
    }
    first = await queue.enqueue_task(
        project_name="demo",
        task_type="reference_video",
        media_type="video",
        resource_id="E1U1",
        payload=base,
        script_file="episode_01.json",
        provider_id="video-provider",
    )
    assert first["deduped"] is False

    same = await queue.enqueue_task(
        project_name="demo",
        task_type="reference_video",
        media_type="video",
        resource_id="E1U1",
        payload=base,
        script_file="episode_01.json",
        provider_id="video-provider",
    )
    assert same["deduped"] is True
    assert same["task_id"] == first["task_id"]

    with pytest.raises(RuntimeError):
        await queue.enqueue_task(
            project_name="demo",
            task_type="reference_video",
            media_type="video",
            resource_id="E1U1",
            payload={**base, "expected_provider_prompt_sha256": "b" * 64},
            script_file="episode_01.json",
            provider_id="video-provider",
        )
''', encoding="utf-8")


def run_tests(root: Path) -> None:
    commands = [
        [
            "uv", "run", "pytest",
            "tests/unit/test_h3_prompt_compiler.py",
            "tests/unit/test_h3_v6_director.py",
            "tests/unit/test_h3_preview_runtime_lock.py",
            "-q",
        ],
        [
            "uv", "run", "ruff", "check",
            "lib/reference_video/h3_prompt_execution.py",
            "lib/reference_video/prompt_preview.py",
            "lib/generation_queue.py",
            "server/routers/reference_videos.py",
            "server/services/reference_video_tasks.py",
            "tests/unit/test_h3_preview_runtime_lock.py",
        ],
    ]
    for cmd in commands:
        print("+", " ".join(cmd))
        subprocess.check_call(cmd, cwd=root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply ArcReel H3 V6.1 preview/runtime prompt lock")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--skip-git-check", action="store_true")
    args = parser.parse_args()

    root = args.repo.resolve()
    verify(root, args.skip_git_check)
    apply(root)
    if args.test:
        run_tests(root)

    print("V6.1 preview/runtime prompt lock applied.")
    print("Invariant: preview.provider_prompt SHA-256 == runtime provider prompt SHA-256.")
    print("Review with: git diff --check && git diff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())