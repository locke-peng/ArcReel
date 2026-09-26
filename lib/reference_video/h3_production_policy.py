"""Production policy for turning H3 media QA failures into deterministic repair decisions.

Phase 3 promotes the six representative supplier-unit lessons into reusable ArcReel
policy.  The planner is deliberately pure and fail-closed: it classifies known failure
facts and returns the narrowest safe repair.  It never performs provider calls itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class H3FailureClass(StrEnum):
    LARGE_SEMANTIC_FAILURE = "large_semantic_failure"
    LOCAL_NONCANONICAL_SURFACE = "local_noncanonical_surface"
    EXACT_TEXT_REQUIRED = "exact_text_required"
    TIMELINE_ONLY_FAILURE = "timeline_only_failure"
    AUDIO_ONLY_FAILURE = "audio_only_failure"
    DIALOGUE_VISUALIZATION = "dialogue_visualization"
    IDENTITY_CONTINUITY_FAILURE = "identity_continuity_failure"
    UNKNOWN = "unknown"


class H3RepairAction(StrEnum):
    REGENERATE_SHOT = "regenerate_shot"
    DETERMINISTIC_SURFACE_REPAIR = "deterministic_surface_repair"
    DETERMINISTIC_TEXT_PLATE = "deterministic_text_plate"
    DETERMINISTIC_AV_RETIME = "deterministic_av_retime"
    AUDIO_REPAIR_REMUX = "audio_repair_remux"
    RECOMPILE_DIALOGUE_DETACHED = "recompile_dialogue_detached"
    REGENERATE_WITH_IDENTITY_BRIDGE = "regenerate_with_identity_bridge"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class H3MediaFailure:
    failure_class: H3FailureClass
    affected_fraction: float = 1.0
    provider_result_usable: bool = False
    audio_is_accepted: bool = False
    exact_visible_text: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.affected_fraction <= 1.0:
            raise ValueError("affected_fraction must be between 0 and 1")
        if self.failure_class == H3FailureClass.EXACT_TEXT_REQUIRED and not self.exact_visible_text:
            raise ValueError("exact_visible_text is required for exact-text repair")


@dataclass(frozen=True)
class H3RepairDecision:
    action: H3RepairAction
    provider_recall_required: bool
    preserve_audio_bitstream: bool
    reason: str


def plan_h3_media_repair(failure: H3MediaFailure) -> H3RepairDecision:
    """Return the narrowest safe repair for one already-inspected media failure."""

    kind = failure.failure_class

    if kind == H3FailureClass.LOCAL_NONCANONICAL_SURFACE:
        if failure.provider_result_usable and failure.affected_fraction <= 0.25:
            return H3RepairDecision(
                action=H3RepairAction.DETERMINISTIC_SURFACE_REPAIR,
                provider_recall_required=False,
                preserve_audio_bitstream=failure.audio_is_accepted,
                reason="repair only the local non-canonical pixels; keep accepted provider content",
            )
        return H3RepairDecision(
            action=H3RepairAction.REGENERATE_SHOT,
            provider_recall_required=True,
            preserve_audio_bitstream=False,
            reason="surface failure is too broad or the provider result is not otherwise reusable",
        )

    if kind == H3FailureClass.EXACT_TEXT_REQUIRED:
        return H3RepairDecision(
            action=H3RepairAction.DETERMINISTIC_TEXT_PLATE,
            provider_recall_required=False,
            preserve_audio_bitstream=failure.audio_is_accepted,
            reason="exact canonical text is deterministic presentation data, not generative content",
        )

    if kind == H3FailureClass.TIMELINE_ONLY_FAILURE:
        if failure.provider_result_usable:
            return H3RepairDecision(
                action=H3RepairAction.DETERMINISTIC_AV_RETIME,
                provider_recall_required=False,
                preserve_audio_bitstream=False,
                reason="retime accepted picture and matching audio together to canonical shot windows",
            )
        return H3RepairDecision(
            action=H3RepairAction.REGENERATE_SHOT,
            provider_recall_required=True,
            preserve_audio_bitstream=False,
            reason="timeline repair cannot preserve a provider result that already failed content",
        )

    if kind == H3FailureClass.AUDIO_ONLY_FAILURE:
        return H3RepairDecision(
            action=H3RepairAction.AUDIO_REPAIR_REMUX,
            provider_recall_required=False,
            preserve_audio_bitstream=False,
            reason="preserve accepted picture and repair only the failed audio layer",
        )

    if kind == H3FailureClass.DIALOGUE_VISUALIZATION:
        return H3RepairDecision(
            action=H3RepairAction.RECOMPILE_DIALOGUE_DETACHED,
            provider_recall_required=True,
            preserve_audio_bitstream=False,
            reason="dialogue leaked into pixels; regenerate from a dialogue-detached visual channel",
        )

    if kind == H3FailureClass.IDENTITY_CONTINUITY_FAILURE:
        return H3RepairDecision(
            action=H3RepairAction.REGENERATE_WITH_IDENTITY_BRIDGE,
            provider_recall_required=True,
            preserve_audio_bitstream=False,
            reason="identity continuity is semantic and must be regenerated with an explicit identity bridge",
        )

    if kind == H3FailureClass.LARGE_SEMANTIC_FAILURE:
        return H3RepairDecision(
            action=H3RepairAction.REGENERATE_SHOT,
            provider_recall_required=True,
            preserve_audio_bitstream=False,
            reason="character, action, scene, or composition semantics are wrong",
        )

    return H3RepairDecision(
        action=H3RepairAction.ESCALATE,
        provider_recall_required=False,
        preserve_audio_bitstream=False,
        reason="unknown failure class must fail closed for human review",
    )
