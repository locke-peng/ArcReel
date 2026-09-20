import { Check, Clipboard, Code2, Loader2 } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { GlassModal } from "@/components/ui/GlassModal";
import { SecondaryButton } from "@/components/ui/SecondaryButton";
import type { ReferencePromptPreview } from "@/types";

export interface PromptPreviewDialogProps {
  open: boolean;
  loading: boolean;
  preview: ReferencePromptPreview | null;
  error?: string | null;
  onClose: () => void;
}

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the legacy fallback.
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    return document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
}

export function PromptPreviewDialog({
  open,
  loading,
  preview,
  error,
  onClose,
}: PromptPreviewDialogProps) {
  const titleId = useId();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) setCopied(false);
  }, [open]);

  const prompt = preview?.provider_prompt ?? "";
  const maxChars = preview?.max_prompt_chars;
  const nearLimit = Boolean(maxChars && preview && preview.prompt_chars > maxChars * 0.9);

  return (
    <GlassModal
      open={open}
      onClose={loading ? () => {} : onClose}
      labelledBy={titleId}
      hairlineTone="accent"
      closeOnBackdrop={!loading}
      closeOnEscape={!loading}
      widthClassName="w-[min(94vw,980px)]"
    >
      <div className="flex max-h-[86vh] flex-col">
        <div className="flex items-start gap-3 border-b border-[var(--color-hairline-soft)] px-5 py-4">
          <span aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-[var(--color-accent)]/25 bg-[var(--color-accent-soft)] text-[var(--color-accent-2)]">
            <Code2 className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-[16px] font-semibold text-[var(--color-text)]">
              最终执行 Prompt 预览
            </h2>
            <p className="mt-0.5 text-[11.5px] leading-relaxed text-[var(--color-text-4)]">
              只编译，不生成视频、不调用供应商、不产生生成费用。
            </p>
          </div>
          <SecondaryButton size="sm" onClick={onClose} disabled={loading}>
            关闭
          </SecondaryButton>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex min-h-[280px] items-center justify-center gap-2 text-sm text-[var(--color-text-3)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在转换 Prompt…
            </div>
          ) : error ? (
            <div className="rounded-lg border border-red-400/25 bg-red-400/5 p-3 text-[12px] leading-relaxed text-red-200">
              {error}
            </div>
          ) : preview ? (
            <div className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                <Meta label="模型" value={preview.model_id || "—"} />
                <Meta label="编译器" value={`${preview.prompt_compiler}${preview.compiler_applied ? " · applied" : ""}`} />
                <Meta label="目标时长" value={`${preview.duration_seconds}s`} />
                <Meta
                  label="字符数"
                  value={maxChars ? `${preview.prompt_chars.toLocaleString()} / ${maxChars.toLocaleString()}` : preview.prompt_chars.toLocaleString()}
                  warn={nearLimit}
                />
              </div>

              {preview.reference_mapping.length > 0 && (
                <div className="rounded-lg border border-[var(--color-hairline-soft)] bg-[oklch(0.17_0.008_265_/_0.6)] p-3">
                  <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-4)]">Reference mapping</div>
                  <div className="grid gap-1.5">
                    {preview.reference_mapping.map((item) => (
                      <div key={`${item.index}:${item.label}`} className="grid grid-cols-[72px_88px_1fr] items-center gap-2 rounded-md border border-[var(--color-hairline-soft)] px-2.5 py-1.5 text-[11px]">
                        <code className="text-[var(--color-text-4)]">{item.picture}</code>
                        <code className="text-[var(--color-accent-2)]">{item.subject}</code>
                        <span className="truncate text-[var(--color-text-2)]" title={item.label}>{item.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="overflow-hidden rounded-lg border border-[var(--color-hairline)] bg-[oklch(0.13_0.006_265)]">
                <div className="flex items-center justify-between border-b border-[var(--color-hairline-soft)] px-3 py-2">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-4)]">Final provider prompt</div>
                  <button
                    type="button"
                    onClick={() => {
                      void copyText(prompt).then((ok) => {
                        if (!ok) return;
                        setCopied(true);
                        window.setTimeout(() => setCopied(false), 1600);
                      });
                    }}
                    className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-[var(--color-hairline)] px-2 py-1 text-[10.5px] text-[var(--color-text-3)] hover:text-[var(--color-text)]"
                  >
                    {copied ? <Check className="h-3 w-3" /> : <Clipboard className="h-3 w-3" />}
                    {copied ? "已复制" : "复制"}
                  </button>
                </div>
                <pre className="max-h-[48vh] overflow-auto whitespace-pre-wrap break-words p-3 font-mono text-[11px] leading-[1.65] text-[var(--color-text-2)]">{prompt}</pre>
              </div>

              {preview.rendered_prompt !== preview.provider_prompt && (
                <details className="rounded-lg border border-[var(--color-hairline-soft)] bg-[oklch(0.17_0.008_265_/_0.45)]">
                  <summary className="cursor-pointer px-3 py-2 text-[11px] font-medium text-[var(--color-text-3)]">查看 H3 编译前的 ArcReel provider prompt</summary>
                  <pre className="max-h-[28vh] overflow-auto whitespace-pre-wrap break-words border-t border-[var(--color-hairline-soft)] p-3 font-mono text-[10.5px] leading-relaxed text-[var(--color-text-3)]">{preview.rendered_prompt}</pre>
                </details>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </GlassModal>
  );
}

function Meta({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="rounded-lg border border-[var(--color-hairline-soft)] bg-[oklch(0.18_0.010_265_/_0.5)] px-3 py-2">
      <div className="text-[9.5px] font-bold uppercase tracking-wider text-[var(--color-text-4)]">{label}</div>
      <div className={`mt-1 truncate font-mono text-[11px] ${warn ? "text-amber-300" : "text-[var(--color-text-2)]"}`}>{value}</div>
    </div>
  );
}
