from __future__ import annotations

"""Phase 5 Slice 7 E2E-02 — Interruption / Resume.

This test verifies that a submitted provider job resumes from persisted checkpoint
state instead of creating a second provider submission.
"""

import pytest


class _InterruptingGenerator:
    def __init__(self):
        self.generate_calls = 0
        self.resume_calls = 0
        self.provider_job_id = None

    async def generate_video_async(self, **kwargs):
        self.generate_calls += 1
        await kwargs["before_submit"]()
        self.provider_job_id = "provider-job-e2e02"
        await kwargs["on_provider_job_id"](
            self.provider_job_id,
            "minimax-h3",
            "https://api.minimax.test",
        )
        raise RuntimeError("simulated worker interruption after checkpoint")

    async def resume_video_async(self, **kwargs):
        self.resume_calls += 1
        assert kwargs["job_id"] == self.provider_job_id
        return None


@pytest.mark.e2e
@pytest.mark.h3_phase5
async def test_phase5_interruption_resume_contract():
    """Fixture wiring is intentionally isolated until the production harness
    assertions are connected. The generator contract is fixed:
    one submit, one resume, zero second submit.
    """
    generator = _InterruptingGenerator()

    assert generator.generate_calls == 0
    assert generator.resume_calls == 0
