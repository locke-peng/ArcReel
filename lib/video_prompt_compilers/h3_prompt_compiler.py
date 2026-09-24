"""Deterministic MiniMax H3 Ref2VA prompt compiler for ArcReel.

This module performs formatting/binding, not semantic translation. It converts ArcReel
asset mentions and dialogue markers into H3's six-section execution prompt while keeping
reference-image order stable.

Supported authoring syntax:
- ``@[Name]`` visual mention
- ``@[Name]{台词}`` / ``@[Name]：{台词}``
- existing ``<d>[Chinese] ...</d>`` dialogue tags

The compiler is intentionally stdlib-only and can run before any provider submission.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

H3_MAX_REFERENCE_IMAGES = 9
H3_MIN_DURATION_SECONDS = 4
H3_MAX_DURATION_SECONDS = 15
# The user's AutoDL endpoint declares 500000. Execution should pass the resolved provider
# capability when available; this is only a permissive fallback.
H3_DEFAULT_MAX_PROMPT_CHARS = 500_000

ReferenceKind = Literal["character", "scene", "object", "style", "unknown"]
RetentionMode = Literal[
    "fully_preserved",
    "partially_preserved",
    "attribute_transfer",
    "weak_reference",
]

_MENTION_RE = re.compile(r"@\[(?P<name>[^\]\r\n]+)\]")
_ARCREEL_DIALOGUE_RE = re.compile(
    r"@\[(?P<speaker>[^\]\r\n]+)\][ \t]*(?:[：:][ \t]*)?\{(?P<text>[^{}\r\n]*)\}"
)
_H3_DIALOGUE_RE = re.compile(
    r"<d>\[(?P<language>[^\]\r\n]+)\]\s*(?P<text>.*?)</d>",
    re.DOTALL,
)
_H3_SECTION_RE = re.compile(
    r"(?m)^(subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music):\s*$"
)

_H3_VISIBLE_TEXT_GUARD_MARKER = "ARCREEL_H3_VISUAL_FRAME_POLICY"
_H3_VISIBLE_TEXT_GUARD = """ARCREEL_H3_VISUAL_FRAME_POLICY:
Prompt labels, timestamps, reference labels, camera/lens notation, motion notes, lighting notes, transition notes, and audio notes are generation controls rather than scene content.
Keep the visible frame as natural cinematic imagery. Written characters may appear only when a shot explicitly declares exact on-screen text.
Words inside <d>...</d> are audio-only spoken content for voice and lip synchronization; they must not become visible typography in the image."""
_H3_DIALOGUE_FRAME_NOTE = (
    "Visual-frame note: the spoken words in this shot are audio-only; keep the image free of added "
    "typography or graphic overlays unless exact on-screen text is explicitly requested in this shot."
)
_SCENE_HINTS = (
    "房", "室", "厅", "堂", "院", "宅", "门外", "后巷", "街", "城门", "客栈", "县衙",
    "山", "林", "温泉", "场景", "scene", "room", "house", "street", "forest", "hall", "courtyard",
)


class H3PromptCompileError(ValueError):
    """Fail before a paid provider submission when H3 compilation is invalid."""


@dataclass(frozen=True)
class H3Reference:
    """One actual transmitted reference image."""

    source_name: str
    label: str
    picture_index: int
    kind: ReferenceKind = "unknown"
    description: str = ""
    retention: RetentionMode = "fully_preserved"

    @property
    def subject_label(self) -> str:
        return f"<Subject {self.picture_index}>"

    @property
    def picture_label(self) -> str:
        return f"<Picture {self.picture_index}>"


@dataclass(frozen=True)
class H3Dialogue:
    speaker: str
    text: str
    language: str = "Chinese"
    voice_style: str = ""


@dataclass(frozen=True)
class H3CompileOptions:
    reference_kinds: Mapping[str, ReferenceKind] | None = None
    reference_descriptions: Mapping[str, str] | None = None
    voice_styles: Mapping[str, str] | None = None
    overall_soundscape: str = "N/A"
    non_diegetic_music: str = "N/A"
    style_opening: str = ""
    task_type: str = "reference generation"
    strict_reference_labels: bool = False
    max_prompt_chars: int = H3_DEFAULT_MAX_PROMPT_CHARS

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "H3CompileOptions":
        if not value:
            return cls()
        allowed = {
            "reference_kinds",
            "reference_descriptions",
            "voice_styles",
            "overall_soundscape",
            "non_diegetic_music",
            "style_opening",
            "task_type",
            "strict_reference_labels",
            "max_prompt_chars",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown H3 prompt compiler option(s): {sorted(unknown)!r}")
        return cls(**{key: value[key] for key in allowed if key in value})


def is_h3_model(model: str | None) -> bool:
    """Recognize official H3 ids and common custom-endpoint aliases."""
    if not model:
        return False
    normalized = model.strip().lower().replace("_", "-")
    return normalized == "minimax-h3" or normalized.startswith(("minimax-h3-", "minimax-h3/"))


def _unique_mentions(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for match in _MENTION_RE.finditer(text):
        name = match.group("name").strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _infer_kind(name: str) -> ReferenceKind:
    lowered = name.lower()
    if any(hint in lowered for hint in _SCENE_HINTS):
        return "scene"
    return "unknown"


def _build_references(
    source_prompt: str,
    *,
    reference_count: int,
    reference_source_names: Sequence[str] | None,
    reference_image_labels: Sequence[str] | None,
    options: H3CompileOptions,
) -> tuple[H3Reference, ...]:
    if reference_count < 1:
        raise H3PromptCompileError("H3 Ref2VA compilation requires at least one reference image")
    if reference_count > H3_MAX_REFERENCE_IMAGES:
        raise H3PromptCompileError(
            f"MiniMax H3 supports at most {H3_MAX_REFERENCE_IMAGES} reference images; got {reference_count}"
        )

    inferred = _unique_mentions(source_prompt)
    if reference_source_names is None:
        source_names = inferred[:reference_count]
        if len(source_names) < reference_count:
            source_names.extend(
                f"Reference {idx}" for idx in range(len(source_names) + 1, reference_count + 1)
            )
    else:
        source_names = [str(name).strip() for name in reference_source_names]
        if len(source_names) != reference_count:
            raise H3PromptCompileError(
                "reference_source_names must match reference image count: "
                f"{len(source_names)} names for {reference_count} images"
            )
        if any(not name for name in source_names):
            raise H3PromptCompileError("reference_source_names must not contain blank names")

    if reference_image_labels is None:
        labels = list(source_names)
    else:
        labels = [str(label).strip() for label in reference_image_labels]
        if len(labels) != reference_count:
            raise H3PromptCompileError(
                "reference_image_labels must match reference image count: "
                f"{len(labels)} labels for {reference_count} images"
            )
        if any(not label for label in labels):
            raise H3PromptCompileError("reference_image_labels must not contain blank labels")

    if options.strict_reference_labels and len(set(labels)) != len(labels):
        raise H3PromptCompileError(f"reference_image_labels must be unique; got {labels!r}")

    kinds = options.reference_kinds or {}
    descriptions = options.reference_descriptions or {}
    refs: list[H3Reference] = []
    for index, (source_name, label) in enumerate(zip(source_names, labels, strict=True), start=1):
        kind = kinds.get(source_name, kinds.get(label, _infer_kind(source_name)))
        if kind not in {"character", "scene", "object", "style", "unknown"}:
            raise H3PromptCompileError(f"invalid reference kind for {source_name!r}: {kind!r}")
        description = descriptions.get(source_name, descriptions.get(label, ""))
        refs.append(
            H3Reference(
                source_name=source_name,
                label=label,
                picture_index=index,
                kind=kind,
                description=str(description).strip(),
            )
        )
    return tuple(refs)


def _nearest_speaker_before(text: str, position: int) -> str | None:
    last: str | None = None
    for match in _MENTION_RE.finditer(text, 0, position):
        last = match.group("name").strip()
    return last


def _extract_dialogues(source_prompt: str, options: H3CompileOptions) -> tuple[H3Dialogue, ...]:
    voice_styles = options.voice_styles or {}
    dialogues: list[H3Dialogue] = []
    occupied: list[tuple[int, int]] = []

    for match in _ARCREEL_DIALOGUE_RE.finditer(source_prompt):
        speaker = match.group("speaker").strip()
        text = match.group("text").strip()
        if text:
            dialogues.append(
                H3Dialogue(
                    speaker=speaker,
                    text=text,
                    language="Chinese",
                    voice_style=str(voice_styles.get(speaker, "")).strip(),
                )
            )
        occupied.append(match.span())

    for match in _H3_DIALOGUE_RE.finditer(source_prompt):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        speaker = _nearest_speaker_before(source_prompt, match.start()) or "Speaker"
        text = " ".join(match.group("text").split())
        language = match.group("language").strip() or "Chinese"
        if text:
            dialogues.append(
                H3Dialogue(
                    speaker=speaker,
                    text=text,
                    language=language,
                    voice_style=str(voice_styles.get(speaker, "")).strip(),
                )
            )
    return tuple(dialogues)


def _strip_dialogues(text: str) -> str:
    return _H3_DIALOGUE_RE.sub("", _ARCREEL_DIALOGUE_RE.sub("", text))


def _replace_mentions(text: str, references: Sequence[H3Reference]) -> str:
    # A logical asset may fan out to more than one actual image. Bind its authoring mention
    # to the first transmitted subject; all transmitted views still remain in definitions.
    source_to_subject: dict[str, str] = {}
    for ref in references:
        source_to_subject.setdefault(ref.source_name, ref.subject_label)

    def repl(match: re.Match[str]) -> str:
        name = match.group("name").strip()
        return source_to_subject.get(name, name)

    return _MENTION_RE.sub(repl, text)


_SCREEN_TEXT_QUOTE_RE = re.compile(r'(?P<open>["“])(?P<text>.+?)(?P<close>["”])')
_SCREEN_TEXT_HINTS = (
    "屏", "界面", "标签", "标题", "字幕", "写着", "显示", "亮起", "弹出", "出现", "加载",
)


def _normalize_explicit_screen_text(text: str) -> str:
    """Promote authored visual text literals to exact on-screen text instructions.

    Audio lines are excluded. Asset mentions inside a quoted visual literal stay as
    their authored human-readable names instead of leaking <Subject N> labels.
    """

    rendered: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("声音：", "声音:", "Sound:", "Audio:")):
            rendered.append(line)
            continue
        if not any(hint in line for hint in _SCREEN_TEXT_HINTS):
            rendered.append(line)
            continue

        exact_texts: list[str] = []

        def repl(
            match: re.Match[str],
            exact_texts: list[str] = exact_texts,
        ) -> str:
            literal = _MENTION_RE.sub(lambda item: item.group("name").strip(), match.group("text"))
            literal = literal.strip()
            if not literal:
                return match.group(0)
            exact_texts.append(literal)
            return ""

        normalized = _SCREEN_TEXT_QUOTE_RE.sub(repl, line)
        normalized = re.sub(r"\s+([。！？!?，,])", r"\1", normalized).rstrip()
        if exact_texts:
            suffix = " ".join(
                f'On-screen text: render exactly "{literal}".' for literal in exact_texts
            )
            normalized = f"{normalized} {suffix}".strip()
        rendered.append(normalized)
    return "\n".join(rendered)


def _render_inline_dialogues(
    text: str,
    references: Sequence[H3Reference],
    options: H3CompileOptions,
) -> str:
    """Render ArcReel dialogue markers in place so multi-shot ownership is preserved."""
    source_to_subject: dict[str, str] = {}
    for ref in references:
        source_to_subject.setdefault(ref.source_name, ref.subject_label)

    voice_styles = options.voice_styles or {}
    speaker_ids: dict[str, str] = {}

    def dialogue_repl(match: re.Match[str]) -> str:
        speaker = match.group("speaker").strip()
        speaker_id = speaker_ids.setdefault(speaker, f"S{len(speaker_ids) + 1}")
        subject = source_to_subject.get(speaker)
        source = f"{subject} ({speaker_id})" if subject else f"{speaker} ({speaker_id})"
        voice_style = str(voice_styles.get(speaker, "")).strip()
        delivery = (
            f" in {voice_style},"
            if voice_style
            else " in a natural voice consistent with the speaker,"
        )
        dialogue = match.group("text").strip()
        return f"{source} says{delivery} <d>[Chinese] {dialogue}</d>"

    rendered = _ARCREEL_DIALOGUE_RE.sub(dialogue_repl, text)
    return _replace_mentions(rendered, references)

def _clean_body(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    out: list[str] = []
    empty = False
    for line in lines:
        if line.strip():
            out.append(line.strip())
            empty = False
        elif not empty:
            out.append("")
            empty = True
    return "\n".join(out).strip()


def _subject_definition(ref: H3Reference) -> str:
    identity = ref.label
    if ref.label != ref.source_name:
        identity = f"{ref.label} (ArcReel asset: {ref.source_name})"
    if ref.description:
        return (
            f"{ref.subject_label} is the reusable visible subject derived from {ref.picture_label}, "
            f"corresponding to {identity}. {ref.description}"
        )
    if ref.kind == "scene":
        return (
            f"{ref.subject_label} is the environment derived from {ref.picture_label}, corresponding to {identity}. "
            "Preserve its spatial layout, architecture, major props, and stable visual anchors."
        )
    if ref.kind == "character":
        return (
            f"{ref.subject_label} is the character derived from {ref.picture_label}, corresponding to {identity}. "
            "Preserve facial identity, hairstyle, costume, body proportions, and stable visual traits."
        )
    if ref.kind == "object":
        return (
            f"{ref.subject_label} is the object derived from {ref.picture_label}, corresponding to {identity}. "
            "Preserve shape, material, proportions, and identifying visual details."
        )
    if ref.kind == "style":
        return (
            f"{ref.subject_label} is the visual style reference derived from {ref.picture_label}, corresponding to "
            f"{identity}. Preserve defining palette, texture, lighting, and rendering characteristics."
        )
    return (
        f"{ref.subject_label} is the reusable visible subject derived from {ref.picture_label}, corresponding to "
        f"{identity}. Preserve its stable identity and reference-defining visual attributes."
    )


def _retention_line(ref: H3Reference) -> str:
    if ref.kind == "scene":
        details = "Preserve the referenced environment, layout, architecture, and stable spatial anchors."
    elif ref.kind == "character":
        details = "Preserve character identity, costume, hairstyle, proportions, and stable appearance."
    else:
        details = "Preserve the referenced subject identity and its defining visual attributes."
    return f"{ref.subject_label} (appears in [Shot 1]): {ref.retention} - {details}"


def _render_dialogues(dialogues: Sequence[H3Dialogue], references: Sequence[H3Reference]) -> list[str]:
    if not dialogues:
        return []
    source_to_subject: dict[str, str] = {}
    for ref in references:
        source_to_subject.setdefault(ref.source_name, ref.subject_label)

    speaker_ids: dict[str, str] = {}
    lines: list[str] = []
    for dialogue in dialogues:
        speaker_id = speaker_ids.setdefault(dialogue.speaker, f"S{len(speaker_ids) + 1}")
        subject = source_to_subject.get(dialogue.speaker)
        source = f"{subject} ({speaker_id})" if subject else f"{dialogue.speaker} ({speaker_id})"
        delivery = (
            f" in {dialogue.voice_style},"
            if dialogue.voice_style
            else " in a natural voice consistent with the speaker,"
        )
        text = dialogue.text.strip()
        if text and text[-1] not in ".?!。？！":
            text += "。"
        lines.append(f"{source} says{delivery} <d>[{dialogue.language}] {text}</d>")
    return lines


def ensure_h3_visible_text_guard(prompt: str) -> str:
    """Inject H3 visual-frame policy and local audio-only dialogue notes."""
    marker = "detailed_description:\n"
    if marker not in prompt:
        raise H3PromptCompileError("H3 prompt is missing detailed_description section")

    guarded = prompt
    if _H3_VISIBLE_TEXT_GUARD_MARKER not in guarded:
        guarded = guarded.replace(marker, marker + _H3_VISIBLE_TEXT_GUARD + "\n", 1)

    lines = guarded.splitlines()
    out: list[str] = []
    for index, line in enumerate(lines):
        out.append(line)
        if "<d>[" not in line or "</d>" not in line:
            continue
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if next_line.strip() != _H3_DIALOGUE_FRAME_NOTE:
            out.append(_H3_DIALOGUE_FRAME_NOTE)
    return "\n".join(out)


def compile_h3_ref2va_prompt(
    *,
    source_prompt: str,
    duration_seconds: int,
    reference_count: int,
    reference_source_names: Sequence[str] | None = None,
    reference_image_labels: Sequence[str] | None = None,
    options: H3CompileOptions | Mapping[str, Any] | None = None,
) -> str:
    """Compile one ArcReel reference-video unit into H3's six-section Ref2VA prompt."""
    if not source_prompt or not source_prompt.strip():
        raise H3PromptCompileError("source_prompt must not be blank")
    if not H3_MIN_DURATION_SECONDS <= int(duration_seconds) <= H3_MAX_DURATION_SECONDS:
        raise H3PromptCompileError(
            f"H3 prompt duration must be {H3_MIN_DURATION_SECONDS}-{H3_MAX_DURATION_SECONDS}s; "
            f"got {duration_seconds}s"
        )

    compile_options = options if isinstance(options, H3CompileOptions) else H3CompileOptions.from_mapping(options)

    if _H3_SECTION_RE.search(source_prompt):
        required = {
            "subject_definitions",
            "summary",
            "retention_analysis",
            "detailed_description",
            "overall_soundscape",
            "non_diegetic_music",
        }
        found = {m.group(1) for m in _H3_SECTION_RE.finditer(source_prompt)}
        if required.issubset(found):
            guarded = ensure_h3_visible_text_guard(source_prompt.strip())
            if len(guarded) > compile_options.max_prompt_chars:
                raise H3PromptCompileError(
                    f"compiled H3 prompt exceeds {compile_options.max_prompt_chars} characters"
                )
            return guarded

    references = _build_references(
        source_prompt,
        reference_count=reference_count,
        reference_source_names=reference_source_names,
        reference_image_labels=reference_image_labels,
        options=compile_options,
    )
    authored_body = _normalize_explicit_screen_text(source_prompt)
    body = _clean_body(_render_inline_dialogues(authored_body, references, compile_options))
    if not body:
        body = "Maintain the referenced subjects and perform the requested action in one continuous shot."

    subject_definitions = "\n".join(_subject_definition(ref) for ref in references)
    subject_labels = ", ".join(ref.subject_label for ref in references)
    summary = (
        f"[{compile_options.task_type}] Create one continuous {duration_seconds}-second target video using "
        f"{subject_labels}. Preserve the referenced identities and environment while following the staging, "
        "actions, camera instructions, lighting, and performance described in [Shot 1]."
    )
    retention_analysis = "\n".join(_retention_line(ref) for ref in references)

    detailed_parts: list[str] = []
    if compile_options.style_opening.strip():
        detailed_parts.append(compile_options.style_opening.strip())
    if re.search(r"(?m)^\[Shot\s+\d+\]", body):
        detailed_parts.append(body)
    else:
        detailed_parts.append(f"[Shot 1] {body}")
    detailed_description = "\n".join(detailed_parts)

    prompt = "\n".join(
        [
            "subject_definitions:",
            subject_definitions,
            "",
            "summary:",
            summary,
            "",
            "retention_analysis:",
            retention_analysis,
            "",
            "detailed_description:",
            detailed_description,
            "",
            "overall_soundscape:",
            compile_options.overall_soundscape.strip() or "N/A",
            "",
            "non_diegetic_music:",
            compile_options.non_diegetic_music.strip() or "N/A",
        ]
    ).strip()
    prompt = ensure_h3_visible_text_guard(prompt)

    if len(prompt) > compile_options.max_prompt_chars:
        raise H3PromptCompileError(
            f"compiled H3 prompt is {len(prompt)} characters; limit is {compile_options.max_prompt_chars}. "
            "Shorten the source prompt or reference descriptions before provider submission."
        )
    return prompt
