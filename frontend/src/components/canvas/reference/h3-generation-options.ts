export type ReferencePromptCompiler = "auto" | "h3_ref2va" | "raw";

export const DEFAULT_REFERENCE_PROMPT_COMPILER: ReferencePromptCompiler = "auto";

/**
 * One reference-image label per line.
 *
 * Keep commas inside labels intact. This matters for asset names such as
 * "客栈, 夜景". Empty lines are ignored.
 */
export function parseReferenceImageLabels(raw: string): string[] | undefined {
  const labels = raw
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  return labels.length > 0 ? labels : undefined;
}
