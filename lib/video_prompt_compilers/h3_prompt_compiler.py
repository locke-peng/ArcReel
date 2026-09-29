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

from dataclasses import dataclass
import re
from typing import Any, Literal, Mapping, Sequence

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

REF2VA_SECTIONS = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)
BASE_SECTIONS = (
    "integrated_multimodal_description",
    "overall_soundscape",
    "non_diegetic_music",
)

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
_NATIVE_SECTION_RE = re.compile(
    r"(?m)^(subject_definitions|summary|retention_analysis|detailed_description|"
    r"integrated_multimodal_description|overall_soundscape|non_diegetic_music):[ \t]*$"
)
_SHOT_HEADER_RE = re.compile(
    r"(?m)^\[Shot\s+(?P<number>\d+)\](?:\s+At\s+"
    r"(?P<minutes>\d{2}):(?P<seconds>\d{2})\.(?P<millis>\d{3}))?"
)
_SPEAKER_ID_RE = re.compile(r"\((?P<ids>S\d+(?:,S\d+)*)\)")
_SUBJECT_SPEAKER_RE = re.compile(
    r"(?P<subject><Subject\s+\d+>)\s+\((?P<sid>S\d+)\)"
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
    subject_index: int
    kind: ReferenceKind = "unknown"
    description: str = ""
    retention: RetentionMode = "fully_preserved"

    @property
    def subject_label(self) -> str:
        return f"<Subject {self.subject_index}>"

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
    subject_by_source: dict[str, int] = {}
    refs: list[H3Reference] = []
    for index, (source_name, label) in enumerate(
        zip(source_names, labels, strict=True),
        start=1,
    ):
        subject_index = subject_by_source.setdefault(
            source_name,
            len(subject_by_source) + 1,
        )
        kind = kinds.get(source_name, kinds.get(label, _infer_kind(source_name)))
        if kind not in {"character", "scene", "object", "style", "unknown"}:
            raise H3PromptCompileError(
                f"invalid reference kind for {source_name!r}: {kind!r}"
            )
        description = descriptions.get(source_name, descriptions.get(label, ""))
        refs.append(
            H3Reference(
                source_name=source_name,
                label=label,
                picture_index=index,
                subject_index=subject_index,
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


def _subject_groups(
    references: Sequence[H3Reference],
) -> tuple[tuple[H3Reference, ...], ...]:
    groups: dict[int, list[H3Reference]] = {}
    for ref in references:
        groups.setdefault(ref.subject_index, []).append(ref)
    return tuple(tuple(groups[index]) for index in sorted(groups))


def _subject_definition(group: Sequence[H3Reference]) -> str:
    ref = group[0]
    pictures = " and ".join(item.picture_label for item in group)
    labels = [item.label for item in group]
    identity = ref.source_name
    if labels != [ref.source_name]:
        identity += " (views: " + ", ".join(labels) + ")"
    descriptions = [item.description for item in group if item.description]
    detail = " ".join(dict.fromkeys(descriptions))

    if ref.kind == "scene":
        sentence = (
            f"{ref.subject_label} is the environment defined by {pictures}, "
            f"corresponding to {identity}. Preserve its spatial layout, architecture, "
            "major props, and stable visual anchors."
        )
    elif ref.kind == "character":
        sentence = (
            f"{ref.subject_label} is the character defined by {pictures}, "
            f"corresponding to {identity}. Preserve facial identity, hairstyle, costume, "
            "body proportions, and stable visual traits."
        )
    elif ref.kind == "object":
        sentence = (
            f"{ref.subject_label} is the object defined by {pictures}, "
            f"corresponding to {identity}. Preserve shape, material, proportions, "
            "and identifying visual details."
        )
    elif ref.kind == "style":
        sentence = (
            f"{ref.subject_label} is the visual style reference defined by {pictures}, "
            f"corresponding to {identity}. Preserve defining palette, texture, lighting, "
            "and rendering characteristics."
        )
    else:
        sentence = (
            f"{ref.subject_label} is the reusable visible subject defined by {pictures}, "
            f"corresponding to {identity}. Preserve its stable identity and "
            "reference-defining visual attributes."
        )
    return sentence + (f" {detail}" if detail else "")


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


def _split_native_sections(
    prompt: str,
    expected: Sequence[str],
) -> dict[str, str]:
    matches = list(_NATIVE_SECTION_RE.finditer(prompt))
    names = [match.group(1) for match in matches]
    if names != list(expected):
        raise H3PromptCompileError(
            "H3 native section order mismatch: expected "
            + " -> ".join(expected)
            + f"; got {names!r}"
        )
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(prompt)
        value = prompt[start:end].strip()
        if not value:
            raise H3PromptCompileError(
                f"H3 native section {match.group(1)!r} must not be empty"
            )
        sections[match.group(1)] = value
    return sections


def _timestamp_seconds(match: re.Match[str]) -> float | None:
    if match.group("minutes") is None:
        return None
    return (
        int(match.group("minutes")) * 60
        + int(match.group("seconds"))
        + int(match.group("millis")) / 1000
    )


def _validate_native_shots(
    text: str,
    *,
    duration_seconds: int,
    field_name: str,
) -> None:
    matches = list(_SHOT_HEADER_RE.finditer(text))
    if not matches:
        raise H3PromptCompileError(
            f"H3 native {field_name} requires at least [Shot 1]"
        )
    numbers = [int(match.group("number")) for match in matches]
    if numbers != list(range(1, len(matches) + 1)):
        raise H3PromptCompileError(
            f"H3 shot numbers must be sequential from 1; got {numbers!r}"
        )
    if _timestamp_seconds(matches[0]) is not None:
        raise H3PromptCompileError("H3 [Shot 1] must not include a timestamp")
    previous = 0.0
    for match in matches[1:]:
        timestamp = _timestamp_seconds(match)
        if timestamp is None:
            raise H3PromptCompileError(
                "Every H3 shot after [Shot 1] must use 'At MM:SS.mmm'"
            )
        if timestamp <= previous:
            raise H3PromptCompileError(
                "H3 shot timestamps must be strictly increasing"
            )
        if timestamp >= duration_seconds:
            raise H3PromptCompileError(
                f"H3 shot timestamp {timestamp:.3f}s must fall inside the "
                f"{duration_seconds}s target duration"
            )
        previous = timestamp


def _validate_dialogue_scope(
    sections: Mapping[str, str],
    *,
    detailed_key: str,
) -> None:
    for name, value in sections.items():
        if name != detailed_key and _H3_DIALOGUE_RE.search(value):
            raise H3PromptCompileError(
                f"H3 dialogue/lyrics <d> blocks are only allowed inside {detailed_key}"
            )


def _validate_speaker_ids(detailed: str) -> None:
    subject_to_sid: dict[str, str] = {}
    for match in _SUBJECT_SPEAKER_RE.finditer(detailed):
        subject = match.group("subject")
        sid = match.group("sid")
        previous = subject_to_sid.setdefault(subject, sid)
        if previous != sid:
            raise H3PromptCompileError(
                f"H3 speaker ID changed for {subject}: {previous} -> {sid}"
            )

    first_seen: list[int] = []
    for dialogue in _H3_DIALOGUE_RE.finditer(detailed):
        line_start = detailed.rfind("\n", 0, dialogue.start()) + 1
        prefix = detailed[line_start:dialogue.start()]
        speaker_match = None
        for candidate in _SPEAKER_ID_RE.finditer(prefix):
            speaker_match = candidate
        if speaker_match is None:
            raise H3PromptCompileError(
                "Every H3 <d> dialogue/lyric block must have a speaker ID "
                "inside its vocal event"
            )
        for token in speaker_match.group("ids").split(","):
            number = int(token[1:])
            if number not in first_seen:
                first_seen.append(number)
    if first_seen and first_seen != list(range(1, len(first_seen) + 1)):
        raise H3PromptCompileError(
            "H3 speaker IDs must follow first actual vocal appearance; "
            f"first-seen order was {first_seen!r}"
        )


def _defined_subjects(subject_definitions: str) -> set[str]:
    labels: set[str] = set()
    for line in subject_definitions.splitlines():
        match = re.match(r"^(<Subject\s+\d+>)\s+is\s+", line.strip())
        if not match:
            continue
        label = match.group(1)
        if label in labels:
            raise H3PromptCompileError(
                f"H3 reference label is defined more than once: {label}"
            )
        labels.add(label)
    return labels


def _validate_ref2va_references(
    sections: Mapping[str, str],
    *,
    reference_count: int,
) -> None:
    definitions = sections["subject_definitions"]
    if not 1 <= reference_count <= H3_MAX_REFERENCE_IMAGES:
        raise H3PromptCompileError(
            f"H3 Ref2VA requires 1-{H3_MAX_REFERENCE_IMAGES} actual reference images"
        )
    for index in range(1, reference_count + 1):
        if f"<Picture {index}>" not in definitions:
            raise H3PromptCompileError(
                f"H3 provider reference image {index} is not bound as <Picture {index}>"
            )
    picture_ids = [
        int(value)
        for value in re.findall(r"<Picture\s+(\d+)>", definitions)
    ]
    if any(index < 1 or index > reference_count for index in picture_ids):
        raise H3PromptCompileError(
            "H3 Ref2VA references a Picture that is not an actual provider image"
        )

    subjects = _defined_subjects(definitions)
    if not subjects:
        raise H3PromptCompileError(
            "H3 Ref2VA subject_definitions must define at least one Subject"
        )
    subject_numbers = sorted(
        int(match.group(1))
        for label in subjects
        if (match := re.fullmatch(r"<Subject\s+(\d+)>", label))
    )
    if subject_numbers != list(range(1, len(subject_numbers) + 1)):
        raise H3PromptCompileError(
            f"H3 Subject labels must be sequential from 1; got {subject_numbers!r}"
        )

    retention_labels = {
        match.group(1)
        for line in sections["retention_analysis"].splitlines()
        if (match := re.match(r"^(<Subject\s+\d+>)", line.strip()))
    }
    if retention_labels != subjects:
        raise H3PromptCompileError(
            "H3 retention_analysis must contain exactly one entry per Subject"
        )

    detailed = sections["detailed_description"]
    for subject in sorted(subjects):
        if subject not in detailed:
            raise H3PromptCompileError(
                f"H3 {subject} is defined but never applied inside detailed_description"
            )


def validate_h3_native_ref2va_structure(
    prompt: str,
    *,
    duration_seconds: int,
    reference_count: int,
) -> str:
    """Validate native Ref2VA structure without semantic translation."""
    duration = int(duration_seconds)
    if not H3_MIN_DURATION_SECONDS <= duration <= H3_MAX_DURATION_SECONDS:
        raise H3PromptCompileError(
            f"H3 prompt duration must be {H3_MIN_DURATION_SECONDS}-"
            f"{H3_MAX_DURATION_SECONDS}s; got {duration_seconds}s"
        )
    normalized = prompt.strip()
    sections = _split_native_sections(normalized, REF2VA_SECTIONS)
    _validate_dialogue_scope(sections, detailed_key="detailed_description")
    _validate_native_shots(
        sections["detailed_description"],
        duration_seconds=duration,
        field_name="detailed_description",
    )
    _validate_speaker_ids(sections["detailed_description"])
    _validate_ref2va_references(
        sections,
        reference_count=reference_count,
    )
    return normalized


def validate_h3_native_t2va_structure(
    prompt: str,
    *,
    duration_seconds: int,
) -> str:
    """Validate native T2VA structure without semantic translation."""
    duration = int(duration_seconds)
    if not H3_MIN_DURATION_SECONDS <= duration <= H3_MAX_DURATION_SECONDS:
        raise H3PromptCompileError(
            f"H3 prompt duration must be {H3_MIN_DURATION_SECONDS}-"
            f"{H3_MAX_DURATION_SECONDS}s; got {duration_seconds}s"
        )
    normalized = prompt.strip()
    sections = _split_native_sections(normalized, BASE_SECTIONS)
    _validate_dialogue_scope(
        sections,
        detailed_key="integrated_multimodal_description",
    )
    detailed = sections["integrated_multimodal_description"]
    _validate_native_shots(
        detailed,
        duration_seconds=duration,
        field_name="integrated_multimodal_description",
    )
    _validate_speaker_ids(detailed)
    if re.search(r"<(?:Subject|Picture|Video|Audio)\s+\d+>", normalized):
        raise H3PromptCompileError(
            "T2VA must not contain full-reference labels"
        )
    return normalized


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
            if len(source_prompt) > compile_options.max_prompt_chars:
                raise H3PromptCompileError(
                    f"compiled H3 prompt exceeds {compile_options.max_prompt_chars} characters"
                )
            return validate_h3_native_ref2va_structure(
                source_prompt,
                duration_seconds=duration_seconds,
                reference_count=reference_count,
            )

    references = _build_references(
        source_prompt,
        reference_count=reference_count,
        reference_source_names=reference_source_names,
        reference_image_labels=reference_image_labels,
        options=compile_options,
    )
    body = _clean_body(_render_inline_dialogues(source_prompt, references, compile_options))
    if not body:
        body = "Maintain the referenced subjects and perform the requested action in one continuous shot."

    groups = _subject_groups(references)
    subject_definitions = "\n".join(
        _subject_definition(group)
        for group in groups
    )
    subject_labels = ", ".join(
        group[0].subject_label
        for group in groups
    )
    summary = (
        f"[{compile_options.task_type}] Create one continuous {duration_seconds}-second target video using "
        f"{subject_labels}. Preserve the referenced identities and environment while following the staging, "
        "actions, camera instructions, lighting, and performance described in [Shot 1]."
    )
    retention_analysis = "\n".join(
        _retention_line(group[0])
        for group in groups
    )

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

    if len(prompt) > compile_options.max_prompt_chars:
        raise H3PromptCompileError(
            f"compiled H3 prompt is {len(prompt)} characters; limit is {compile_options.max_prompt_chars}. "
            "Shorten the source prompt or reference descriptions before provider submission."
        )
    return validate_h3_native_ref2va_structure(
        prompt,
        duration_seconds=duration_seconds,
        reference_count=reference_count,
    )
