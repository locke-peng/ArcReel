"""MiniMax H3 Ref2VA prompt compiler.

This module is intentionally deterministic and stdlib-only. It does not call an LLM.
It converts ArcReel's authoring-layer prompt conventions into MiniMax H3's six-section
full-reference prompt format while preserving reference-image order.

The compiler supports both:
- ArcReel mention syntax: ``@[Name]``
- ArcReel canonical dialogue lines: ``@[Name]：{台词}``
- Existing H3 dialogue tags: ``<d>[Chinese] ...</d>``

Important:
MiniMax's official prompt-writing guide recommends English rewrite sections. This
compiler does not translate arbitrary prose; it preserves the author's descriptive
text after replacing ArcReel asset mentions with H3 subject labels. If strict English
rewriting is required, generate the authoring description in English upstream or add
a semantic rewrite stage before calling this deterministic renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import TYPE_CHECKING, Any, Literal, Mapping, Sequence

if TYPE_CHECKING:
    from lib.video_backends.base import VideoGenerationRequest

H3_MAX_REFERENCE_IMAGES = 9
H3_MAX_PROMPT_CHARS = 7000
H3_MIN_DURATION_SECONDS = 4
H3_MAX_DURATION_SECONDS = 15

ReferenceKind = Literal["character", "scene", "object", "style", "unknown"]
RetentionMode = Literal[
    "fully_preserved",
    "partially_preserved",
    "attribute_transfer",
    "weak_reference",
]

_MENTION_RE = re.compile(r"@\[(?P<name>[^\]\r\n]+)\]")
_CANONICAL_DIALOGUE_RE = re.compile(
    r"@\[(?P<speaker>[^\]\r\n]+)\][ \t]*(?:[：:][ \t]*)?\{(?P<text>[^{}\r\n]*)\}"
)
_H3_DIALOGUE_RE = re.compile(
    r"<d>\[(?P<language>[^\]\r\n]+)\]\s*(?P<text>.*?)</d>",
    re.DOTALL,
)
_H3_SECTION_RE = re.compile(
    r"(?m)^(subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music):\s*$"
)

# Conservative scene-name hints. Explicit kinds supplied by the caller always win.
_SCENE_HINTS = (
    "房",
    "室",
    "厅",
    "堂",
    "院",
    "宅",
    "门外",
    "后巷",
    "街",
    "城门",
    "客栈",
    "县衙",
    "山",
    "林",
    "温泉",
    "场景",
    "scene",
    "room",
    "house",
    "street",
    "forest",
    "hall",
    "courtyard",
)


@dataclass(frozen=True)
class H3Reference:
    """One H3 visual subject backed by one ArcReel reference image."""

    name: str
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
    """Optional caller-supplied semantic hints.

    reference_kinds/reference_descriptions are keyed by the ArcReel asset label.
    The order still comes exclusively from reference_images/reference_image_labels.
    """

    reference_kinds: Mapping[str, ReferenceKind] | None = None
    reference_descriptions: Mapping[str, str] | None = None
    voice_styles: Mapping[str, str] | None = None
    overall_soundscape: str = "N/A"
    non_diegetic_music: str = "N/A"
    style_opening: str = ""
    task_type: str = "reference generation"
    strict_reference_labels: bool = True
    max_prompt_chars: int = H3_MAX_PROMPT_CHARS

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


class H3PromptCompileError(ValueError):
    """Raised before a paid provider submission when H3 prompt compilation is invalid."""


def is_h3_model(model: str | None) -> bool:
    """Return True for official MiniMax-H3 and common custom-endpoint aliases."""
    if not model:
        return False
    normalized = model.strip().lower().replace("_", "-")
    return (
        normalized == "minimax-h3"
        or normalized.startswith("minimax-h3-")
        or normalized.startswith("minimax-h3/")
    )


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
    if reference_image_labels is None:
        names = inferred[:reference_count]
        if len(names) < reference_count:
            names.extend(f"Reference {idx}" for idx in range(len(names) + 1, reference_count + 1))
    else:
        names = [str(label).strip() for label in reference_image_labels]
        if len(names) != reference_count:
            raise H3PromptCompileError(
                "reference_image_labels must be the same length and order as reference_images: "
                f"{len(names)} labels for {reference_count} images"
            )
        if any(not name for name in names):
            raise H3PromptCompileError("reference_image_labels must not contain blank labels")

    if options.strict_reference_labels and len(set(names)) != len(names):
        raise H3PromptCompileError(f"reference_image_labels must be unique; got {names!r}")

    kinds = options.reference_kinds or {}
    descriptions = options.reference_descriptions or {}
    refs: list[H3Reference] = []
    for index, name in enumerate(names, start=1):
        kind = kinds.get(name, _infer_kind(name))
        if kind not in {"character", "scene", "object", "style", "unknown"}:
            raise H3PromptCompileError(f"invalid reference kind for {name!r}: {kind!r}")
        refs.append(
            H3Reference(
                name=name,
                picture_index=index,
                kind=kind,
                description=str(descriptions.get(name, "")).strip(),
            )
        )
    return tuple(refs)


def _nearest_speaker_before(text: str, position: int) -> str | None:
    last: str | None = None
    for match in _MENTION_RE.finditer(text, 0, position):
        last = match.group("name").strip()
    return last


def _extract_dialogues(
    source_prompt: str,
    *,
    options: H3CompileOptions,
) -> tuple[H3Dialogue, ...]:
    dialogues: list[H3Dialogue] = []
    voice_styles = options.voice_styles or {}

    # ArcReel canonical dialogue syntax has the clearest speaker binding.
    occupied: list[tuple[int, int]] = []
    for match in _CANONICAL_DIALOGUE_RE.finditer(source_prompt):
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

    # Preserve already-authored H3 dialogue tags. Avoid duplicating text that happened
    # to sit inside a canonical line.
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
    text = _CANONICAL_DIALOGUE_RE.sub("", text)
    text = _H3_DIALOGUE_RE.sub("", text)
    return text


def _replace_mentions(text: str, references: Sequence[H3Reference]) -> str:
    labels = {ref.name: ref.subject_label for ref in references}

    def repl(match: re.Match[str]) -> str:
        name = match.group("name").strip()
        return labels.get(name, name)

    return _MENTION_RE.sub(repl, text)


def _clean_body(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    # Trim leading/trailing empty lines and collapse >2 empty lines.
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
    if ref.description:
        return (
            f"{ref.subject_label} is the reusable visible subject derived from {ref.picture_label}, "
            f"corresponding to {ref.name}. {ref.description}"
        )
    if ref.kind == "scene":
        return (
            f"{ref.subject_label} is the environment derived from {ref.picture_label}, corresponding to "
            f"{ref.name}. Preserve its spatial layout, architecture, major props, and stable visual anchors."
        )
    if ref.kind == "character":
        return (
            f"{ref.subject_label} is the character derived from {ref.picture_label}, corresponding to "
            f"{ref.name}. Preserve facial identity, hairstyle, costume, body proportions, and stable visual traits."
        )
    if ref.kind == "object":
        return (
            f"{ref.subject_label} is the object derived from {ref.picture_label}, corresponding to "
            f"{ref.name}. Preserve its shape, material, proportions, and identifying visual details."
        )
    if ref.kind == "style":
        return (
            f"{ref.subject_label} is the visual style reference derived from {ref.picture_label}, corresponding to "
            f"{ref.name}. Preserve the defining palette, texture, lighting, and rendering characteristics."
        )
    return (
        f"{ref.subject_label} is the reusable visible subject derived from {ref.picture_label}, corresponding to "
        f"{ref.name}. Preserve the stable identity and reference-defining visual attributes visible in the source image."
    )


def _retention_line(ref: H3Reference) -> str:
    if ref.kind == "scene":
        details = "Preserve the referenced environment, layout, architecture, and stable spatial anchors."
    elif ref.kind == "character":
        details = "Preserve the referenced character identity, costume, hairstyle, proportions, and stable appearance."
    else:
        details = "Preserve the referenced subject identity and its defining visual attributes."
    return f"{ref.subject_label} (appears in [Shot 1]): {ref.retention} - {details}"


def _render_dialogues(
    dialogues: Sequence[H3Dialogue],
    references: Sequence[H3Reference],
) -> list[str]:
    if not dialogues:
        return []
    subjects = {ref.name: ref.subject_label for ref in references}
    speaker_ids: dict[str, str] = {}
    lines: list[str] = []
    for dialogue in dialogues:
        speaker_id = speaker_ids.setdefault(dialogue.speaker, f"S{len(speaker_ids) + 1}")
        subject = subjects.get(dialogue.speaker)
        source = f"{subject} ({speaker_id})" if subject else f"{dialogue.speaker} ({speaker_id})"
        delivery = (
            f" in {dialogue.voice_style},"
            if dialogue.voice_style
            else " in a natural voice consistent with the speaker,"
        )
        text = dialogue.text.strip()
        if text and text[-1] not in ".?!。？！":
            # H3 guide requests complete dialogue statements to end in punctuation.
            text += "。"
        lines.append(
            f"{source} says{delivery} <d>[{dialogue.language}] {text}</d>"
        )
    return lines


def compile_h3_ref2va_prompt(
    *,
    source_prompt: str,
    duration_seconds: int,
    reference_count: int,
    reference_image_labels: Sequence[str] | None = None,
    options: H3CompileOptions | Mapping[str, Any] | None = None,
) -> str:
    """Compile one ArcReel reference-video unit into MiniMax H3 Ref2VA format."""
    if not source_prompt or not source_prompt.strip():
        raise H3PromptCompileError("source_prompt must not be blank")
    if not H3_MIN_DURATION_SECONDS <= int(duration_seconds) <= H3_MAX_DURATION_SECONDS:
        raise H3PromptCompileError(
            f"H3 prompt duration must be {H3_MIN_DURATION_SECONDS}-{H3_MAX_DURATION_SECONDS}s; "
            f"got {duration_seconds}s"
        )

    compile_options = (
        options if isinstance(options, H3CompileOptions) else H3CompileOptions.from_mapping(options)
    )
    if _H3_SECTION_RE.search(source_prompt):
        # Idempotency: do not wrap an already compiled six-section prompt again.
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
            if len(source_prompt) > compile_options.max_prompt_chars:
                raise H3PromptCompileError(
                    f"compiled H3 prompt exceeds {compile_options.max_prompt_chars} characters"
                )
            return source_prompt.strip()

    references = _build_references(
        source_prompt,
        reference_count=reference_count,
        reference_image_labels=reference_image_labels,
        options=compile_options,
    )
    dialogues = _extract_dialogues(source_prompt, options=compile_options)

    body = _replace_mentions(_strip_dialogues(source_prompt), references)
    body = _clean_body(body)
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
    detailed_parts.append(f"[Shot 1] {body}")
    detailed_parts.extend(_render_dialogues(dialogues, references))
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

    if len(prompt) > compile_options.max_prompt_chars:
        raise H3PromptCompileError(
            f"compiled H3 prompt is {len(prompt)} characters; limit is {compile_options.max_prompt_chars}. "
            "Shorten the source prompt or reference descriptions before provider submission."
        )
    return prompt


def compile_h3_video_request(
    request: "VideoGenerationRequest",
    *,
    reference_image_labels: Sequence[str] | None = None,
    options: H3CompileOptions | Mapping[str, Any] | None = None,
) -> "VideoGenerationRequest":
    """Return a copy of VideoGenerationRequest with only ``prompt`` replaced."""
    refs = request.reference_images or []
    prompt = compile_h3_ref2va_prompt(
        source_prompt=request.prompt,
        duration_seconds=request.duration_seconds,
        reference_count=len(refs),
        reference_image_labels=reference_image_labels,
        options=options,
    )
    return replace(request, prompt=prompt)
