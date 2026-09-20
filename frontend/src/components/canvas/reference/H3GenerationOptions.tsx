import { useTranslation } from "react-i18next";
import { Eye, Loader2 } from "lucide-react";
import type { ReferencePromptCompiler } from "./h3-generation-options";

export interface H3GenerationOptionsProps {
  referenceImageLabels: string;
  promptCompiler: ReferencePromptCompiler;
  disabled?: boolean;
  previewing?: boolean;
  onPreviewPrompt?: () => void;
  onReferenceImageLabelsChange: (value: string) => void;
  onPromptCompilerChange: (value: ReferencePromptCompiler) => void;
}

/**
 * Per-unit request overrides for reference-video generation.
 *
 * State deliberately lives in ReferenceVideoCanvas, not here: UnitPreviewPanel is
 * mounted in two responsive locations and may unmount when switching breakpoints.
 */
export function H3GenerationOptions({
  referenceImageLabels,
  promptCompiler,
  disabled = false,
  previewing = false,
  onPreviewPrompt,
  onReferenceImageLabelsChange,
  onPromptCompilerChange,
}: H3GenerationOptionsProps) {
  const { t } = useTranslation("dashboard");

  return (
    <div className="rounded-lg border border-[var(--color-hairline-soft)] bg-[oklch(0.18_0.010_265_/_0.45)] p-3">
      <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-4)]">
        {t("reference_h3_options_title", { defaultValue: "H3 / Advanced request options" })}
      </div>

      <label className="block">
        <span className="mb-1 block text-[11px] font-medium text-[var(--color-text-3)]">
          reference_image_labels
        </span>
        <textarea
          value={referenceImageLabels}
          disabled={disabled}
          rows={3}
          spellCheck={false}
          placeholder={"沈家新房\n姜采苓\n沈延/被附身"}
          onChange={(event) => onReferenceImageLabelsChange(event.target.value)}
          className="focus-ring w-full resize-y rounded-md border border-[var(--color-hairline)] bg-[oklch(0.15_0.008_265_/_0.75)] px-2.5 py-2 font-mono text-[11px] leading-relaxed text-[var(--color-text-2)] placeholder:text-[var(--color-text-4)] disabled:cursor-not-allowed disabled:opacity-60"
        />
        <span className="mt-1 block text-[10px] leading-relaxed text-[var(--color-text-4)]">
          {t("reference_h3_labels_help", {
            defaultValue:
              "One label per line. Leave blank to derive labels from the actual reference-image send order.",
          })}
        </span>
      </label>

      <label className="mt-2.5 block">
        <span className="mb-1 block text-[11px] font-medium text-[var(--color-text-3)]">
          prompt_compiler
        </span>
        <select
          value={promptCompiler}
          disabled={disabled}
          onChange={(event) =>
            onPromptCompilerChange(event.target.value as ReferencePromptCompiler)
          }
          className="focus-ring w-full rounded-md border border-[var(--color-hairline)] bg-[oklch(0.15_0.008_265_/_0.75)] px-2.5 py-2 font-mono text-[11px] text-[var(--color-text-2)] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <option value="auto">auto</option>
          <option value="h3_ref2va">h3_ref2va</option>
          <option value="raw">raw</option>
        </select>
        <span className="mt-1 block text-[10px] leading-relaxed text-[var(--color-text-4)]">
          {t("reference_h3_compiler_help", {
            defaultValue:
              "auto: detect MiniMax H3; h3_ref2va: force H3 six-section prompt; raw: bypass compilation.",
          })}
        </span>
      </label>
      {onPreviewPrompt && (
        <button
          type="button"
          disabled={disabled || previewing}
          onClick={onPreviewPrompt}
          className="focus-ring mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-[var(--color-accent)]/30 bg-[var(--color-accent-soft)] px-3 py-2 text-[11.5px] font-semibold text-[var(--color-accent-2)] hover:border-[var(--color-accent)]/50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {previewing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Eye className="h-3.5 w-3.5" />
          )}
          {previewing ? "正在转换…" : "一键预览最终 Prompt"}
        </button>
      )}
    </div>
  );
}
