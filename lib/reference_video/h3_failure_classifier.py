"""Deterministic mapping from structured media-QA facts to the Phase 3 failure taxonomy."""

from __future__ import annotations

from lib.reference_video.h3_production_policy import H3FailureClass, H3MediaFailure
from lib.reference_video.media_qa_schema import MediaQAFinding

_TAG_CLASS_MAP: dict[str, H3FailureClass] = {
    "large_semantic_failure": H3FailureClass.LARGE_SEMANTIC_FAILURE,
    "invented_content": H3FailureClass.LARGE_SEMANTIC_FAILURE,
    "topology_failure": H3FailureClass.LARGE_SEMANTIC_FAILURE,
    "local_noncanonical_surface": H3FailureClass.LOCAL_NONCANONICAL_SURFACE,
    "noncanonical_text": H3FailureClass.LOCAL_NONCANONICAL_SURFACE,
    "surface_pollution": H3FailureClass.LOCAL_NONCANONICAL_SURFACE,
    "exact_text_required": H3FailureClass.EXACT_TEXT_REQUIRED,
    "exact_text_mismatch": H3FailureClass.EXACT_TEXT_REQUIRED,
    "timeline_only_failure": H3FailureClass.TIMELINE_ONLY_FAILURE,
    "cut_timing": H3FailureClass.TIMELINE_ONLY_FAILURE,
    "audio_only_failure": H3FailureClass.AUDIO_ONLY_FAILURE,
    "dialogue_visualization": H3FailureClass.DIALOGUE_VISUALIZATION,
    "dialogue_leakage": H3FailureClass.DIALOGUE_VISUALIZATION,
    "identity_continuity_failure": H3FailureClass.IDENTITY_CONTINUITY_FAILURE,
    "identity_drift": H3FailureClass.IDENTITY_CONTINUITY_FAILURE,
}


def classify_h3_media_finding(finding: MediaQAFinding) -> H3MediaFailure:
    """Translate one QA finding into the existing Phase 3 repair-planner input.

    The classifier never chooses a repair action. That remains exclusively owned by
    plan_h3_media_repair().
    """

    failure_class = finding.failure_class
    if failure_class is None:
        matches = {_TAG_CLASS_MAP[tag] for tag in finding.tags if tag in _TAG_CLASS_MAP}
        failure_class = matches.pop() if len(matches) == 1 else H3FailureClass.UNKNOWN

    return H3MediaFailure(
        failure_class=failure_class,
        affected_fraction=finding.affected_fraction,
        provider_result_usable=finding.provider_result_usable,
        audio_is_accepted=finding.audio_is_accepted,
        exact_visible_text=finding.exact_visible_text,
    )
