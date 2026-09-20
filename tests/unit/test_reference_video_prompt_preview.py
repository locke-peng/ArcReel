from lib.reference_video.prompt_preview import build_reference_prompt_preview_payload


def test_preview_payload_exposes_final_prompt_and_stable_mapping() -> None:
    payload = build_reference_prompt_preview_payload(
        provider_prompt="subject_definitions:\n<Subject 1>...",
        rendered_prompt="legacy",
        model_id="minimax_h3_zm_u24",
        prompt_compiler="auto",
        compiler_applied=True,
        duration_seconds=10,
        reference_labels=["沈家新房", "姜采苓", "沈延/被附身"],
        max_prompt_chars=7000,
    )

    assert payload["prompt_chars"] == len(payload["provider_prompt"])
    assert payload["reference_mapping"] == [
        {"index": 1, "picture": "<Picture 1>", "subject": "<Subject 1>", "label": "沈家新房"},
        {"index": 2, "picture": "<Picture 2>", "subject": "<Subject 2>", "label": "姜采苓"},
        {"index": 3, "picture": "<Picture 3>", "subject": "<Subject 3>", "label": "沈延/被附身"},
    ]
    assert payload["max_prompt_chars"] == 7000
    assert payload["compiler_applied"] is True
