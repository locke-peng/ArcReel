import { describe, expect, it } from "vitest";

interface Preview {
  provider_prompt: string;
  rendered_prompt: string;
  model_id: string | null;
  prompt_compiler: "auto" | "h3_ref2va" | "raw";
  compiler_applied: boolean;
  duration_seconds: number;
  prompt_chars: number;
  max_prompt_chars: number | null;
  reference_mapping: Array<{
    index: number;
    picture: string;
    subject: string;
    label: string;
    source_name?: string;
  }>;
}

describe("reference prompt preview response contract", () => {
  it("represents a final H3 provider prompt and mapping", () => {
    const preview: Preview = {
      provider_prompt: "subject_definitions:",
      rendered_prompt: "legacy",
      model_id: "minimax_h3_zm_u24",
      prompt_compiler: "auto",
      compiler_applied: true,
      duration_seconds: 10,
      prompt_chars: 20,
      max_prompt_chars: 500000,
      reference_mapping: [
        { index: 1, picture: "<Picture 1>", subject: "<Subject 1>", label: "沈家新房" },
      ],
    };
    expect(preview.reference_mapping[0]?.subject).toBe("<Subject 1>");
    expect(preview.compiler_applied).toBe(true);
  });
});
