"""MiniMax H3 native prompt compiler and validator for ArcReel.

The contract in this module follows MiniMax H3's official ``h3-prompt-writing``
skill:
- Ref2VA uses exactly six sections in the documented order.
- T2VA / I2VA / FL2VA / L2VA use the base three-field format.
- Rewrite prose is English; only dialogue/lyrics inside ``<d>`` and text that is
  visibly present in the scene may remain in the source language.
- Shot timing, speaker IDs, reference labels, and visible text are fail-closed.

This module deliberately does not perform semantic machine translation.  A
free-form ArcReel authoring prompt that still contains Chinese execution prose is
rejected before a paid provider submission.  Semantic rewriting belongs to the
authoring/IR layer; this deterministic compiler only binds and validates the
provider prompt so preview/runtime remain byte-stable.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

H3_MAX_REFERENCE_IMAGES = 9
H3_MIN_DURATION_SECONDS = 4
H3_MAX_DURATION_SECONDS = 15
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
_ALLOWED_TASK_TYPES = {
    "keyframe completion",
    "reference generation",
    "video editing",
    "video continuation",
    "audio reuse",
    "audio reference",
}
_ALLOWED_RETENTION = {
    "fully_preserved",
    "partially_preserved",
    "attribute_transfer",
    "weak_reference",
}

_MENTION_RE = re.compile(r"@\[(?P<name>[^\]\r\n]+)\]")
_ARCREEL_DIALOGUE_RE = re.compile(
    r"@\[(?P<speaker>[^\]\r\n]+)\][ \t]*(?:[：:][ \t]*)?\{(?P<text>[^{}\r\n]*)\}"
)
_H3_DIALOGUE_RE = re.compile(
    r"<d>\[(?P<language>[^\]\r\n]+)\]\s*(?P<text>.*?)</d>", re.DOTALL
)
_ANY_SECTION_RE = re.compile(r"(?m)^([a-z_]+):[ \t]*")
_SHOT_HEADER_RE = re.compile(
    r"(?m)^\[Shot\s+(?P<number>\d+)\](?:\s+At\s+(?P<minutes>\d{2}):(?P<seconds>\d{2})\.(?P<millis>\d{3}))?"
)
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_SCREEN_TEXT_QUOTE_RE = re.compile(r'"[^"\r\n]*"')
_SPEAKER_ID_RE = re.compile(r"\((?P<ids>S\d+(?:,S\d+)*)\)")
_SUBJECT_SPEAKER_RE = re.compile(r"(?P<subject><Subject\s+\d+>)\s+\((?P<sid>S\d+)\)")
_TASK_PREFIX_RE = re.compile(r"^\[(?P<types>[^\]]+)\]\s+")
_RETENTION_LINE_RE = re.compile(
    r"^(?P<label><(?:Subject|Picture|Video)\s+\d+>).*?:\s*"
    r"(?P<mode>fully_preserved|partially_preserved|attribute_transfer|weak_reference)\s*-\s+.+$"
)
_PICTURE_DEFINITION_RE = re.compile(r"^<Picture\s+\d+>\s+is\s+", re.IGNORECASE)
_FRAME_ANCHOR_TERMS = (
    "first frame",
    "last frame",
    "keyframe",
    "storyboard",
    "composition anchor",
    "shot-planning",
    "shot planning",
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
    overall_soundscape: str = ""
    non_diegetic_music: str = "N/A"
    style_opening: str = (
        "The target video uses live-action visual treatment consistent with the referenced assets, "
        "with naturalistic lighting and camera behavior defined by each shot."
    )
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


def _fail(message: str) -> None:
    raise H3PromptCompileError(message)


def _assert_duration(duration_seconds: int) -> int:
    duration = int(duration_seconds)
    if not H3_MIN_DURATION_SECONDS <= duration <= H3_MAX_DURATION_SECONDS:
        _fail(
            f"H3 prompt duration must be {H3_MIN_DURATION_SECONDS}-{H3_MAX_DURATION_SECONDS}s; "
            f"got {duration_seconds}s"
        )
    return duration


def _split_exact_sections(prompt: str, expected: Sequence[str]) -> dict[str, str]:
    matches = list(_ANY_SECTION_RE.finditer(prompt))
    names = [m.group(1) for m in matches]
    if names != list(expected):
        _fail(
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
            _fail(f"H3 native section {match.group(1)!r} must not be empty")
        sections[match.group(1)] = value
    return sections


def _without_allowed_original_language(text: str, *, allow_visible_text: bool) -> str:
    masked = _H3_DIALOGUE_RE.sub("", text)
    if allow_visible_text:
        masked = _SCREEN_TEXT_QUOTE_RE.sub("", masked)
    return masked


def _assert_english_execution_prose(text: str, *, section: str, allow_visible_text: bool = False) -> None:
    masked = _without_allowed_original_language(text, allow_visible_text=allow_visible_text)
    if _CJK_RE.search(masked):
        _fail(
            f"H3 native {section} contains non-English execution prose. "
            "Only dialogue/lyrics inside <d> and visible scene text inside English double quotes may retain "
            "their original language. Rewrite the execution prose in English before provider submission."
        )


def _timestamp_seconds(match: re.Match[str]) -> float | None:
    if match.group("minutes") is None:
        return None
    return (
        int(match.group("minutes")) * 60
        + int(match.group("seconds"))
        + int(match.group("millis")) / 1000
    )


def _validate_shots(text: str, *, duration_seconds: int, field_name: str) -> None:
    matches = list(_SHOT_HEADER_RE.finditer(text))
    if not matches:
        _fail(f"H3 native {field_name} requires at least [Shot 1]")
    numbers = [int(m.group("number")) for m in matches]
    if numbers != list(range(1, len(matches) + 1)):
        _fail(f"H3 shot numbers must be sequential from 1; got {numbers!r}")
    if _timestamp_seconds(matches[0]) is not None:
        _fail("H3 [Shot 1] must not include a timestamp")
    previous = 0.0
    for match in matches[1:]:
        ts = _timestamp_seconds(match)
        if ts is None:
            _fail("Every H3 shot after [Shot 1] must use 'At MM:SS.mmm'")
        if ts <= previous:
            _fail("H3 shot timestamps must be strictly increasing")
        if ts >= duration_seconds:
            _fail(
                f"H3 shot timestamp {ts:.3f}s must fall inside the {duration_seconds}s target duration"
            )
        previous = ts


def _validate_dialogue_scope(sections: Mapping[str, str], *, detailed_key: str) -> None:
    for name, value in sections.items():
        if name != detailed_key and _H3_DIALOGUE_RE.search(value):
            _fail(f"H3 dialogue/lyrics <d> blocks are only allowed inside {detailed_key}")


def _validate_speaker_ids(detailed: str) -> None:
    subject_to_sid: dict[str, str] = {}
    for match in _SUBJECT_SPEAKER_RE.finditer(detailed):
        subject = match.group("subject")
        sid = match.group("sid")
        previous = subject_to_sid.setdefault(subject, sid)
        if previous != sid:
            _fail(f"H3 speaker ID changed for {subject}: {previous} -> {sid}")

    first_seen: list[int] = []
    for dialogue in _H3_DIALOGUE_RE.finditer(detailed):
        prefix_start = max(detailed.rfind("\n", 0, dialogue.start()), 0)
        prefix = detailed[prefix_start:dialogue.start()]
        speaker_match = None
        for candidate in _SPEAKER_ID_RE.finditer(prefix):
            speaker_match = candidate
        if speaker_match is None:
            _fail("Every H3 <d> dialogue/lyric block must have a speaker ID immediately in its vocal event")
        for token in speaker_match.group("ids").split(","):
            number = int(token[1:])
            if number not in first_seen:
                first_seen.append(number)
    if first_seen and first_seen != list(range(1, len(first_seen) + 1)):
        _fail(
            "H3 speaker IDs must be assigned once in order of actual vocal events; "
            f"first-seen order was {first_seen!r}"
        )


def _validate_task_prefix(summary: str) -> None:
    match = _TASK_PREFIX_RE.match(summary)
    if match is None:
        _fail("H3 Ref2VA summary must begin with a square-bracketed task-type prefix")
    task_types = [part.strip() for part in match.group("types").split("+")]
    if not task_types or any(part not in _ALLOWED_TASK_TYPES for part in task_types):
        _fail(f"H3 Ref2VA summary contains unsupported task type(s): {task_types!r}")
    if len(set(task_types)) != len(task_types):
        _fail("H3 Ref2VA summary task types must not be repeated")


def _validate_reference_definitions(subject_definitions: str, *, reference_count: int) -> None:
    if reference_count < 1:
        _fail("H3 Ref2VA requires at least one actual provider reference image")
    if reference_count > H3_MAX_REFERENCE_IMAGES:
        _fail(f"MiniMax H3 supports at most {H3_MAX_REFERENCE_IMAGES} reference images; got {reference_count}")
    for index in range(1, reference_count + 1):
        if f"<Picture {index}>" not in subject_definitions:
            _fail(
                f"H3 Ref2VA provider reference image {index} is not bound in subject_definitions as <Picture {index}>"
            )
    picture_ids = [int(x) for x in re.findall(r"<Picture\s+(\d+)>", subject_definitions)]
    if any(index < 1 or index > reference_count for index in picture_ids):
        _fail("H3 Ref2VA references a <Picture N> that is not an actual provider image")
    for line in subject_definitions.splitlines():
        if not _PICTURE_DEFINITION_RE.match(line.strip()):
            continue
        lowered = line.lower()
        if not any(term in lowered for term in _FRAME_ANCHOR_TERMS):
            _fail(
                "A standalone <Picture N> definition is only valid for a first/last/keyframe, storyboard, "
                "or concrete composition anchor. Images used only for identity/style must be cited inside "
                "the corresponding <Subject N> definition."
            )


def _defined_reference_labels(subject_definitions: str) -> set[str]:
    labels: set[str] = set()
    for line in subject_definitions.splitlines():
        stripped = line.strip()
        match = re.match(r"^(<(?:Subject|Picture|Video|Audio)\s+\d+>)\s+is\s+", stripped)
        if match:
            label = match.group(1)
            if label in labels:
                _fail(f"H3 reference label is defined more than once: {label}")
            labels.add(label)
    return labels


def _validate_reference_label_semantics(sections: Mapping[str, str]) -> None:
    definitions = sections["subject_definitions"]
    defined = _defined_reference_labels(definitions)
    if not defined:
        _fail("H3 Ref2VA subject_definitions must define at least one reference label")

    subject_numbers = sorted(
        int(match.group(1))
        for label in defined
        if (match := re.fullmatch(r"<Subject\s+(\d+)>", label))
    )
    if subject_numbers and subject_numbers != list(range(1, len(subject_numbers) + 1)):
        _fail(f"H3 Subject labels must be sequential from 1; got {subject_numbers!r}")

    standalone_pictures = {label for label in defined if label.startswith("<Picture ")}
    retention_labels = {
        match.group(1)
        for line in sections["retention_analysis"].splitlines()
        if (match := re.match(r"^(<(?:Subject|Picture|Video|Audio)\s+\d+>)", line.strip()))
    }
    if retention_labels != defined:
        missing = sorted(defined - retention_labels)
        extra = sorted(retention_labels - defined)
        _fail(
            "H3 retention_analysis must contain exactly one entry for every independently defined reference "
            f"label; missing={missing!r}, extra={extra!r}"
        )

    allowed_source_pictures = set(re.findall(r"<Picture\s+\d+>", definitions))
    for section_name in ("summary", "detailed_description", "overall_soundscape", "non_diegetic_music"):
        value = sections[section_name]
        for label in re.findall(r"<(?:Subject|Picture|Video|Audio)\s+\d+>", value):
            if label.startswith("<Picture "):
                if label not in standalone_pictures:
                    _fail(
                        f"{label} is only a source image for a Subject and must not be used as an independent "
                        f"reference in {section_name}; define it as a concrete frame/storyboard anchor first"
                    )
            elif label not in defined:
                _fail(f"H3 {section_name} uses undefined reference label {label}")

    detailed = sections["detailed_description"]
    for label in sorted(label for label in defined if label.startswith("<Subject ")):
        if label not in detailed:
            _fail(
                f"H3 {label} is defined but never applied inside detailed_description. Every reusable Subject "
                "must be bound at the shot where it visibly appears or takes effect."
            )

    # All provider Picture labels must still be traceable in subject definitions even
    # when they are not independent Picture entities.
    if not allowed_source_pictures:
        _fail("H3 Ref2VA subject_definitions contain no provider Picture provenance")


def _validate_visible_original_language(text: str) -> None:
    masked_dialogue = _H3_DIALOGUE_RE.sub("", text)
    for match in _SCREEN_TEXT_QUOTE_RE.finditer(masked_dialogue):
        literal = match.group(0)
        if not _CJK_RE.search(literal):
            continue
        context = masked_dialogue[max(0, match.start() - 140):match.start()].lower()
        visible_terms = (
            "reads", "reading", "displays", "displaying", "shows", "showing", "visible",
            "screen", "sign", "label", "banner", "interface", "written", "text", "glows",
        )
        if not any(term in context for term in visible_terms):
            _fail(
                "Original-language text outside <d> is only allowed when it is explicitly described as visible "
                f"scene text; ambiguous quoted literal {literal!r}"
            )


def _validate_retention(retention: str) -> None:
    if _SPEAKER_ID_RE.search(retention):
        _fail("H3 retention_analysis must not contain speaker IDs (Sx)")
    for line in [x.strip() for x in retention.splitlines() if x.strip()]:
        if line.startswith("<Audio "):
            if not re.search(r":\s*(fully_copy|partially_copy|reference|weak_reference)\s*-\s+", line):
                _fail(f"Invalid H3 audio retention line: {line!r}")
            continue
        match = _RETENTION_LINE_RE.match(line)
        if match is None or match.group("mode") not in _ALLOWED_RETENTION:
            _fail(f"Invalid H3 visible-content retention line: {line!r}")


def validate_h3_native_ref2va_prompt(
    prompt: str,
    *,
    duration_seconds: int,
    reference_count: int,
) -> str:
    """Validate and return an already-native Ref2VA prompt without mutating it."""
    duration = _assert_duration(duration_seconds)
    prompt = prompt.strip()
    sections = _split_exact_sections(prompt, REF2VA_SECTIONS)
    _validate_reference_definitions(sections["subject_definitions"], reference_count=reference_count)
    _validate_task_prefix(sections["summary"])
    _validate_retention(sections["retention_analysis"])
    _validate_reference_label_semantics(sections)
    _validate_dialogue_scope(sections, detailed_key="detailed_description")

    detailed = sections["detailed_description"]
    first_shot = detailed.find("[Shot 1]")
    if first_shot <= 0 or not detailed[:first_shot].strip():
        _fail(
            "H3 Ref2VA detailed_description must establish one or two English style sentences before [Shot 1]"
        )
    _validate_shots(detailed, duration_seconds=duration, field_name="detailed_description")
    _validate_speaker_ids(detailed)
    _validate_visible_original_language(detailed)

    _assert_english_execution_prose(
        sections["subject_definitions"], section="subject_definitions"
    )
    _assert_english_execution_prose(sections["summary"], section="summary")
    _assert_english_execution_prose(
        sections["retention_analysis"], section="retention_analysis"
    )
    _assert_english_execution_prose(
        detailed, section="detailed_description", allow_visible_text=True
    )
    _assert_english_execution_prose(
        sections["overall_soundscape"], section="overall_soundscape"
    )
    _assert_english_execution_prose(
        sections["non_diegetic_music"], section="non_diegetic_music"
    )
    return prompt


def validate_h3_native_t2va_prompt(prompt: str, *, duration_seconds: int) -> str:
    """Validate and return a native T2VA prompt in the official three-field format."""
    duration = _assert_duration(duration_seconds)
    prompt = prompt.strip()
    sections = _split_exact_sections(prompt, BASE_SECTIONS)
    _validate_dialogue_scope(sections, detailed_key="integrated_multimodal_description")
    detailed = sections["integrated_multimodal_description"]
    _validate_shots(detailed, duration_seconds=duration, field_name="integrated_multimodal_description")
    _validate_speaker_ids(detailed)
    _validate_visible_original_language(detailed)
    if re.search(r"<(?:Subject|Picture|Video|Audio)\s+\d+>", prompt):
        _fail("T2VA must not contain full-reference labels; use the appropriate keyframe mode or Ref2VA")
    _assert_english_execution_prose(
        detailed, section="integrated_multimodal_description", allow_visible_text=True
    )
    _assert_english_execution_prose(
        sections["overall_soundscape"], section="overall_soundscape"
    )
    _assert_english_execution_prose(
        sections["non_diegetic_music"], section="non_diegetic_music"
    )
    return prompt


def ensure_h3_visible_text_guard(prompt: str) -> str:
    """Compatibility shim: native H3 prompts are no longer mutated with custom guard blocks.

    Official H3 prompting uses natural shot descriptions, quoted visible text, ``<d>``
    vocal content, and speaker/shot semantics.  Injecting ArcReel-specific pseudo-fields
    into ``detailed_description`` breaks strict native compliance, so this function now
    intentionally returns the prompt unchanged.
    """
    return prompt.strip()


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
        _fail("H3 Ref2VA compilation requires at least one reference image")
    if reference_count > H3_MAX_REFERENCE_IMAGES:
        _fail(f"MiniMax H3 supports at most {H3_MAX_REFERENCE_IMAGES} reference images; got {reference_count}")

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
            _fail(
                "reference_source_names must match reference image count: "
                f"{len(source_names)} names for {reference_count} images"
            )
        if any(not name for name in source_names):
            _fail("reference_source_names must not contain blank names")

    labels = list(source_names) if reference_image_labels is None else [str(x).strip() for x in reference_image_labels]
    if len(labels) != reference_count:
        _fail(
            "reference_image_labels must match reference image count: "
            f"{len(labels)} labels for {reference_count} images"
        )
    if any(not label for label in labels):
        _fail("reference_image_labels must not contain blank labels")
    if options.strict_reference_labels and len(set(labels)) != len(labels):
        _fail(f"reference_image_labels must be unique; got {labels!r}")

    kinds = options.reference_kinds or {}
    descriptions = options.reference_descriptions or {}
    refs: list[H3Reference] = []
    subject_index_by_source: dict[str, int] = {}
    for index, (source_name, label) in enumerate(zip(source_names, labels, strict=True), start=1):
        kind = kinds.get(source_name, kinds.get(label, _infer_kind(source_name)))
        if kind not in {"character", "scene", "object", "style", "unknown"}:
            _fail(f"invalid reference kind for {source_name!r}: {kind!r}")
        description = str(descriptions.get(source_name, descriptions.get(label, ""))).strip()
        if description:
            _assert_english_execution_prose(description, section="reference_descriptions")
        logical_key = source_name.casefold()
        subject_index = subject_index_by_source.setdefault(logical_key, len(subject_index_by_source) + 1)
        refs.append(
            H3Reference(
                source_name=source_name,
                label=label,
                picture_index=index,
                subject_index=subject_index,
                kind=kind,
                description=description,
            )
        )
    return tuple(refs)


def _group_references_by_subject(
    references: Sequence[H3Reference],
) -> list[tuple[H3Reference, tuple[H3Reference, ...]]]:
    grouped: dict[int, list[H3Reference]] = {}
    for ref in references:
        grouped.setdefault(ref.subject_index, []).append(ref)
    return [(items[0], tuple(items)) for _, items in sorted(grouped.items())]


def _picture_source_phrase(group: Sequence[H3Reference]) -> str:
    pictures = [ref.picture_label for ref in group]
    if len(pictures) == 1:
        return pictures[0]
    if len(pictures) == 2:
        return f"{pictures[0]} and {pictures[1]}"
    return ", ".join(pictures[:-1]) + f", and {pictures[-1]}"


def _subject_definition(ref: H3Reference, group: Sequence[H3Reference]) -> str:
    # Provider-facing H3 text deliberately omits ArcReel's human asset name.  The
    # external reference mapping remains available in preview metadata, while the
    # H3 rewrite itself stays English as required by the official skill.
    source = _picture_source_phrase(group)
    descriptions = [item.description for item in group if item.description]
    if descriptions:
        merged = " ".join(dict.fromkeys(descriptions))
        return (
            f"{ref.subject_label} is the reusable visible subject defined by {source}. "
            f"{merged}"
        )
    if ref.kind == "scene":
        return (
            f"{ref.subject_label} is the environment defined by {source}; preserve its spatial layout, "
            "architecture, major props, lighting identity, and stable visual anchors."
        )
    if ref.kind == "character":
        return (
            f"{ref.subject_label} is the character defined by {source}; preserve facial identity, "
            "hairstyle, costume, body proportions, and stable visual traits."
        )
    if ref.kind == "object":
        return (
            f"{ref.subject_label} is the object defined by {source}; preserve its shape, material, "
            "proportions, and identifying visual details."
        )
    if ref.kind == "style":
        return (
            f"{ref.subject_label} is the visual style defined by {source}; preserve its palette, "
            "texture, lighting treatment, and rendering characteristics."
        )
    return (
        f"{ref.subject_label} is the reusable visible subject defined by {source}; preserve its stable "
        "identity and reference-defining visual attributes."
    )


def _reference_appearance_map(source_prompt: str, references: Sequence[H3Reference]) -> dict[int, list[int]]:
    matches = list(_SHOT_HEADER_RE.finditer(source_prompt))
    if not matches:
        return {ref.picture_index: [1] for ref in references}
    blocks: list[tuple[int, str]] = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(source_prompt)
        blocks.append((int(match.group("number")), source_prompt[match.start():end]))
    result: dict[int, list[int]] = {}
    for ref in references:
        marker = f"@[{ref.source_name}]"
        shots = [number for number, block in blocks if marker in block]
        if not shots:
            _fail(
                f"provider reference {ref.picture_label} is not used by any authored shot; remove the unused "
                "reference or bind it explicitly before H3 submission"
            )
        result[ref.picture_index] = shots
    return result


def _retention_line(ref: H3Reference, shots: Sequence[int]) -> str:
    shot_text = ", ".join(f"[Shot {number}]" for number in shots)
    if ref.kind == "scene":
        details = "the referenced environment, layout, architecture, and stable spatial anchors are retained."
    elif ref.kind == "character":
        details = "the referenced identity, face, hairstyle, costume, proportions, and stable appearance are retained."
    elif ref.kind == "object":
        details = "the referenced shape, material, proportions, and identifying visual details are retained."
    else:
        details = "the referenced subject identity and defining visual attributes are retained."
    return f"{ref.subject_label} (appears in {shot_text}): {ref.retention} - {details}"


def _source_to_subject(references: Sequence[H3Reference]) -> dict[str, str]:
    result: dict[str, str] = {}
    for ref in references:
        result.setdefault(ref.source_name, ref.subject_label)
    return result


def _render_inline_dialogues(
    text: str,
    references: Sequence[H3Reference],
    options: H3CompileOptions,
) -> str:
    source_to_subject = _source_to_subject(references)
    voice_styles = options.voice_styles or {}
    speaker_ids: dict[str, str] = {}

    def dialogue_repl(match: re.Match[str]) -> str:
        speaker = match.group("speaker").strip()
        sid = speaker_ids.setdefault(speaker, f"S{len(speaker_ids) + 1}")
        subject = source_to_subject.get(speaker)
        if subject:
            vocal_source = f"{subject} ({sid})"
            close = f" After the line, {subject} closes their lips and stops speaking."
        else:
            # A non-referenced vocal source is valid only if its authoring identifier is
            # already English.  The final native validator catches non-English names.
            vocal_source = f"The on-screen speaker {speaker} ({sid})"
            close = " After the line, the speaker closes their lips and stops speaking."
        voice_style = str(voice_styles.get(speaker, "")).strip()
        if voice_style:
            _assert_english_execution_prose(voice_style, section="voice_styles")
            delivery = f" in {voice_style}"
        else:
            delivery = " in a natural voice consistent with the speaker"
        dialogue = match.group("text").strip()
        return f"{vocal_source} says{delivery}: <d>[Chinese] {dialogue}</d>{close}"

    rendered = _ARCREEL_DIALOGUE_RE.sub(dialogue_repl, text)

    def mention_repl(match: re.Match[str]) -> str:
        name = match.group("name").strip()
        return source_to_subject.get(name, name)

    return _MENTION_RE.sub(mention_repl, rendered)


def _extract_english_sound_lines(text: str) -> tuple[str, str]:
    body_lines: list[str] = []
    sounds: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r"^(?:Sound|Audio):\s*(.+)$", stripped, flags=re.IGNORECASE)
        if match:
            sounds.append(match.group(1).strip())
        else:
            body_lines.append(line)
    return "\n".join(body_lines), " ".join(sounds).strip()


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


def _looks_like_native_ref2va(prompt: str) -> bool:
    names = [m.group(1) for m in _ANY_SECTION_RE.finditer(prompt)]
    return names == list(REF2VA_SECTIONS)


def compile_h3_ref2va_prompt(
    *,
    source_prompt: str,
    duration_seconds: int,
    reference_count: int,
    reference_source_names: Sequence[str] | None = None,
    reference_image_labels: Sequence[str] | None = None,
    options: H3CompileOptions | Mapping[str, Any] | None = None,
) -> str:
    """Compile or validate one ArcReel unit as a native H3 Ref2VA prompt.

    Already-native six-section prompts are validated and returned byte-for-byte
    (aside from outer whitespace).  Free-form authoring text is only formatted when
    its execution prose is already English.  Chinese story/director prose must first
    be rewritten by the authoring layer; silently forwarding it would violate the
    official H3 prompt-writing contract.
    """
    if not source_prompt or not source_prompt.strip():
        _fail("source_prompt must not be blank")
    duration = _assert_duration(duration_seconds)
    compile_options = options if isinstance(options, H3CompileOptions) else H3CompileOptions.from_mapping(options)

    if _looks_like_native_ref2va(source_prompt.strip()):
        native = validate_h3_native_ref2va_prompt(
            source_prompt.strip(),
            duration_seconds=duration,
            reference_count=reference_count,
        )
        if len(native) > compile_options.max_prompt_chars:
            _fail(f"compiled H3 prompt exceeds {compile_options.max_prompt_chars} characters")
        return native

    references = _build_references(
        source_prompt,
        reference_count=reference_count,
        reference_source_names=reference_source_names,
        reference_image_labels=reference_image_labels,
        options=compile_options,
    )
    appearance = _reference_appearance_map(source_prompt, references)
    rendered = _render_inline_dialogues(source_prompt, references, compile_options)
    rendered, extracted_soundscape = _extract_english_sound_lines(rendered)
    body = _clean_body(rendered)
    if not re.search(r"(?m)^\[Shot\s+1\]", body):
        body = f"[Shot 1] {body}"
    _assert_english_execution_prose(body, section="free-form Ref2VA body", allow_visible_text=True)

    style_opening = compile_options.style_opening.strip()
    if not style_opening:
        _fail("strict H3 Ref2VA compilation requires an English style_opening before [Shot 1]")
    _assert_english_execution_prose(style_opening, section="style_opening")

    soundscape = compile_options.overall_soundscape.strip() or extracted_soundscape
    if not soundscape:
        _fail(
            "strict H3 Ref2VA compilation requires an English overall_soundscape; use N/A only when the target "
            "video is explicitly silent"
        )
    _assert_english_execution_prose(soundscape, section="overall_soundscape")
    music = compile_options.non_diegetic_music.strip() or "N/A"
    _assert_english_execution_prose(music, section="non_diegetic_music")

    grouped_references = _group_references_by_subject(references)
    subject_definitions = "\n".join(
        _subject_definition(primary, group) for primary, group in grouped_references
    )
    subjects = ", ".join(primary.subject_label for primary, _group in grouped_references)
    summary = (
        f"[{compile_options.task_type}] The {duration}-second target video uses {subjects} as visual references "
        "and follows the authored shot order, actions, camera movement, sound, and vocal events."
    )
    retention_lines: list[str] = []
    for primary, group in grouped_references:
        shots = sorted({
            shot
            for item in group
            for shot in appearance[item.picture_index]
        })
        retention_lines.append(_retention_line(primary, shots))
    retention = "\n".join(retention_lines)
    detailed = style_opening + "\n" + body
    prompt = "\n".join(
        [
            "subject_definitions:",
            subject_definitions,
            "",
            "summary:",
            summary,
            "",
            "retention_analysis:",
            retention,
            "",
            "detailed_description:",
            detailed,
            "",
            "overall_soundscape:",
            soundscape,
            "",
            "non_diegetic_music:",
            music,
        ]
    ).strip()
    native = validate_h3_native_ref2va_prompt(
        prompt,
        duration_seconds=duration,
        reference_count=reference_count,
    )
    if len(native) > compile_options.max_prompt_chars:
        _fail(
            f"compiled H3 prompt is {len(native)} characters; limit is {compile_options.max_prompt_chars}. "
            "Shorten the native rewrite before provider submission."
        )
    return native