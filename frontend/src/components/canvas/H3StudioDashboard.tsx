import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  CheckCircle2,
  Clock3,
  Gauge,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  ShieldAlert,
  WalletCards,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { API } from "@/api";
import type {
  H3RepairBatchAction,
  H3StudioBatchPreview,
  H3StudioRepairTicketView,
  H3StudioSummary,
} from "@/types";
import { useAppStore } from "@/stores/app-store";
import { errMsg } from "@/utils/async";

interface H3StudioDashboardProps {
  projectName: string;
}

function Card({
  title,
  value,
  detail,
  icon: Icon,
}: {
  title: string;
  value: string | number;
  detail?: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "oklch(0.20 0.011 265 / 0.72)",
        border: "1px solid var(--color-hairline)",
      }}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: "var(--color-text-4)" }}>
          {title}
        </span>
        <Icon className="h-4 w-4" />
      </div>
      <div className="num mt-2 text-2xl font-semibold">{value}</div>
      {detail ? <div className="mt-1 text-xs" style={{ color: "var(--color-text-4)" }}>{detail}</div> : null}
    </div>
  );
}

function TicketList({
  title,
  items,
  selectable,
  selected,
  onToggle,
}: {
  title: string;
  items: H3StudioRepairTicketView[];
  selectable?: boolean;
  selected?: Set<string>;
  onToggle?: (ticketId: string) => void;
}) {
  return (
    <section
      className="rounded-xl"
      style={{
        background: "oklch(0.19 0.011 265 / 0.65)",
        border: "1px solid var(--color-hairline)",
      }}
    >
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--color-hairline-soft)" }}>
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="num text-xs" style={{ color: "var(--color-text-4)" }}>{items.length}</span>
      </div>
      <div className="max-h-64 overflow-y-auto p-2">
        {items.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs" style={{ color: "var(--color-text-4)" }}>—</div>
        ) : (
          items.map((item) => {
            const checked = selected?.has(item.ticket_id) ?? false;
            return (
              <label
                key={item.ticket_id}
                className="mb-1 flex items-start gap-2 rounded-lg px-3 py-2"
                style={{ background: checked ? "var(--color-accent-dim)" : "transparent" }}
              >
                {selectable ? (
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggle?.(item.ticket_id)}
                    className="mt-0.5"
                  />
                ) : null}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-semibold">{item.unit_id ?? item.ticket_id}</div>
                  <div className="mt-0.5 truncate text-[11px]" style={{ color: "var(--color-text-4)" }}>
                    {item.shot_id ?? "—"} · {item.failure_class ?? item.lifecycle.state}
                  </div>
                </div>
                <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px]" style={{ color: "var(--color-text-3)", background: "oklch(0.25 0.012 265 / .65)" }}>
                  {item.lifecycle.state}
                </span>
              </label>
            );
          })
        )}
      </div>
    </section>
  );
}

export function H3StudioDashboard({ projectName }: H3StudioDashboardProps) {
  const { t } = useTranslation("dashboard");
  const [summary, setSummary] = useState<H3StudioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingControl, setSavingControl] = useState(false);
  const [selectedApproval, setSelectedApproval] = useState<Set<string>>(new Set());
  const [selectedEnqueue, setSelectedEnqueue] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<H3StudioBatchPreview | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const [capDraft, setCapDraft] = useState("");

  const refresh = async () => {
    setLoading(true);
    try {
      const next = await API.getH3StudioSummary(projectName);
      setSummary(next);
      setCapDraft(next.control.max_running_tasks == null ? "" : String(next.control.max_running_tasks));
    } catch (err) {
      useAppStore.getState().pushToast(t("h3_studio_load_failed", { message: errMsg(err) }), "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, [projectName]);

  const costText = useMemo(() => {
    if (!summary) return "—";
    const entries = Object.entries(summary.budget.actual_cost_by_currency);
    return entries.length === 0
      ? "—"
      : entries.map(([currency, amount]) => `${currency} ${amount.toFixed(2)}`).join(" · ");
  }, [summary]);

  const toggle = (setter: React.Dispatch<React.SetStateAction<Set<string>>>, id: string) => {
    setter((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setPreview(null);
  };

  const applyPause = async () => {
    if (!summary) return;
    setSavingControl(true);
    try {
      await API.setH3StudioPaused(projectName, !summary.control.paused);
      await refresh();
    } catch (err) {
      useAppStore.getState().pushToast(t("h3_studio_control_failed", { message: errMsg(err) }), "error");
    } finally {
      setSavingControl(false);
    }
  };

  const applyCap = async () => {
    const trimmed = capDraft.trim();
    const value = trimmed === "" ? null : Number(trimmed);
    if (value !== null && (!Number.isInteger(value) || value < 1)) return;
    setSavingControl(true);
    try {
      await API.setH3StudioRunningCap(projectName, value);
      await refresh();
    } catch (err) {
      useAppStore.getState().pushToast(t("h3_studio_control_failed", { message: errMsg(err) }), "error");
    } finally {
      setSavingControl(false);
    }
  };

  const runBatch = async (
    action: H3RepairBatchAction,
    ids: string[],
    execute: boolean,
  ) => {
    if (ids.length === 0) return;
    setBatchBusy(true);
    try {
      if (!execute) {
        setPreview(await API.previewH3StudioBatch(projectName, action, ids));
      } else {
        await API.executeH3StudioBatch(projectName, action, ids);
        setPreview(null);
        setSelectedApproval(new Set());
        setSelectedEnqueue(new Set());
        await refresh();
      }
    } catch (err) {
      useAppStore.getState().pushToast(t("h3_studio_batch_failed", { message: errMsg(err) }), "error");
    } finally {
      setBatchBusy(false);
    }
  };

  if (loading && !summary) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm" style={{ color: "var(--color-text-3)" }}>
        <RefreshCw className="h-4 w-4 animate-spin" />
        {t("h3_studio_loading")}
      </div>
    );
  }

  if (!summary) return null;

  const { queues, budget, control } = summary;
  const approvalIds = [...selectedApproval];
  const enqueueIds = [...selectedEnqueue];

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="mx-auto max-w-[1500px]">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="display-serif text-xl font-semibold">{t("h3_studio_title")}</h1>
            <p className="mt-1 text-xs" style={{ color: "var(--color-text-4)" }}>{t("h3_studio_desc")}</p>
          </div>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs focus-ring"
            style={{ background: "oklch(0.25 0.012 265 / .7)", border: "1px solid var(--color-hairline)" }}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            {t("h3_studio_refresh")}
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Card title={t("h3_studio_pending")} value={queues.pending_approvals.length} icon={Clock3} />
          <Card title={t("h3_studio_approved_waiting")} value={queues.approved_waiting.length} icon={CheckCircle2} />
          <Card title={t("h3_studio_active")} value={queues.active_executions.length} icon={Activity} />
          <Card title={t("h3_studio_human_review")} value={queues.human_review_required.length} icon={ShieldAlert} />
          <Card
            title={t("h3_studio_budget")}
            value={budget.remaining_provider_calls ?? "∞"}
            detail={costText}
            icon={WalletCards}
          />
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[360px_1fr]">
          <section
            className="rounded-xl p-4"
            style={{ background: "oklch(0.19 0.011 265 / .65)", border: "1px solid var(--color-hairline)" }}
          >
            <h2 className="text-sm font-semibold">{t("h3_studio_control")}</h2>
            <div className="mt-4 flex items-center justify-between">
              <div>
                <div className="text-xs font-medium">{t("h3_studio_pause")}</div>
                <div className="mt-0.5 text-[11px]" style={{ color: "var(--color-text-4)" }}>
                  {control.paused ? t("h3_studio_paused") : t("h3_studio_running")}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void applyPause()}
                disabled={savingControl}
                className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs focus-ring"
                style={{ background: control.paused ? "var(--color-accent-dim)" : "oklch(0.25 0.012 265 / .7)" }}
              >
                {control.paused ? <PlayCircle className="h-3.5 w-3.5" /> : <PauseCircle className="h-3.5 w-3.5" />}
                {control.paused ? t("h3_studio_resume") : t("h3_studio_pause_action")}
              </button>
            </div>

            <div className="mt-4">
              <label className="text-xs font-medium" htmlFor="h3-studio-running-cap">{t("h3_studio_running_cap")}</label>
              <div className="mt-2 flex gap-2">
                <div className="relative flex-1">
                  <Gauge className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5" />
                  <input
                    id="h3-studio-running-cap"
                    inputMode="numeric"
                    value={capDraft}
                    onChange={(event) => setCapDraft(event.target.value)}
                    placeholder={t("h3_studio_unlimited")}
                    className="w-full rounded-md py-1.5 pl-8 pr-2 text-xs outline-none focus-ring"
                    style={{ background: "oklch(0.16 0.010 250 / .7)", border: "1px solid var(--color-hairline)" }}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => void applyCap()}
                  disabled={savingControl}
                  className="rounded-md px-3 py-1.5 text-xs focus-ring"
                  style={{ background: "var(--color-accent-dim)", color: "var(--color-accent-2)" }}
                >
                  {t("h3_studio_apply")}
                </button>
              </div>
            </div>

            <div className="mt-5 rounded-lg p-3 text-xs" style={{ background: "oklch(0.16 0.010 250 / .55)" }}>
              <div className="flex justify-between"><span>{t("h3_studio_reserved_calls")}</span><span className="num">{budget.reserved_provider_calls}</span></div>
              <div className="mt-2 flex justify-between"><span>{t("h3_studio_call_ceiling")}</span><span className="num">{budget.provider_call_ceiling ?? "∞"}</span></div>
              <div className="mt-2 flex justify-between"><span>{t("h3_studio_actual_cost")}</span><span className="num">{costText}</span></div>
            </div>
          </section>

          <div className="grid gap-4 md:grid-cols-2">
            <TicketList
              title={t("h3_studio_pending")}
              items={queues.pending_approvals}
              selectable
              selected={selectedApproval}
              onToggle={(id) => toggle(setSelectedApproval, id)}
            />
            <TicketList
              title={t("h3_studio_approved_waiting")}
              items={queues.approved_waiting}
              selectable
              selected={selectedEnqueue}
              onToggle={(id) => toggle(setSelectedEnqueue, id)}
            />
            <TicketList title={t("h3_studio_active")} items={queues.active_executions} />
            <TicketList title={t("h3_studio_human_review")} items={queues.human_review_required} />
          </div>
        </div>

        <section
          className="mt-4 rounded-xl p-4"
          style={{ background: "oklch(0.19 0.011 265 / .65)", border: "1px solid var(--color-hairline)" }}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">{t("h3_studio_batch")}</h2>
              <p className="mt-1 text-[11px]" style={{ color: "var(--color-text-4)" }}>{t("h3_studio_batch_desc")}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={batchBusy || approvalIds.length === 0}
                onClick={() => void runBatch("approve", approvalIds, false)}
                className="rounded-md px-3 py-1.5 text-xs focus-ring disabled:opacity-40"
                style={{ border: "1px solid var(--color-hairline)" }}
              >
                {t("h3_studio_preview_approve")} ({approvalIds.length})
              </button>
              <button
                type="button"
                disabled={batchBusy || enqueueIds.length === 0}
                onClick={() => void runBatch("enqueue", enqueueIds, false)}
                className="rounded-md px-3 py-1.5 text-xs focus-ring disabled:opacity-40"
                style={{ border: "1px solid var(--color-hairline)" }}
              >
                {t("h3_studio_preview_enqueue")} ({enqueueIds.length})
              </button>
            </div>
          </div>

          {preview ? (
            <div className="mt-4 rounded-lg p-3" style={{ background: "oklch(0.16 0.010 250 / .6)" }}>
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-semibold">
                  {t("h3_studio_preview_ready", { action: preview.action, count: preview.items.length })}
                </div>
                <button
                  type="button"
                  disabled={batchBusy || preview.items.every((item) => !item.eligible)}
                  onClick={() => void runBatch(
                    preview.action,
                    preview.items.filter((item) => item.eligible).map((item) => item.ticket_id),
                    true,
                  )}
                  className="rounded-md px-3 py-1.5 text-xs font-semibold focus-ring disabled:opacity-40"
                  style={{ background: "var(--color-accent)", color: "oklch(0.12 0 0)" }}
                >
                  {t("h3_studio_execute_eligible")}
                </button>
              </div>
              <div className="mt-3 grid gap-1">
                {preview.items.map((item) => (
                  <div key={item.ticket_id} className="flex items-center justify-between gap-3 rounded px-2 py-1.5 text-xs">
                    <span className="truncate">{item.ticket_id}</span>
                    <span style={{ color: item.eligible ? "var(--color-accent-2)" : "var(--color-text-4)" }}>
                      {item.eligible ? t("h3_studio_eligible") : item.reason}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
