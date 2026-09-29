import type { ReferencePromptCompiler } from "@/types";

export const DEFAULT_REFERENCE_PROMPT_COMPILER: ReferencePromptCompiler = "auto";

/** One reference-image label per line. Commas inside labels remain intact. */
export function parseReferenceImageLabels(raw: string): string[] | undefined {
  const labels = raw
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  return labels.length > 0 ? labels : undefined;
}

export type { ReferencePromptCompiler };
