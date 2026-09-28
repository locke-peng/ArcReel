import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import type { H3StudioSummary } from "@/types";
import { H3StudioDashboard } from "./H3StudioDashboard";

function makeSummary(): H3StudioSummary {
  return {
    project: { project_name: "demo", state_counts: { complete: 3 } },
    control: {
      project_name: "demo",
      paused: false,
      max_running_tasks: 2,
      explicit: true,
    },
    budget: {
      project_name: "demo",
      provider_call_ceiling: 5,
      reserved_provider_calls: 2,
      remaining_provider_calls: 3,
      budget_counter_reconciled: true,
      tickets: [],
      actual_cost_by_currency: { CNY: 4.5 },
      unpriced_call_count: 0,
    },
    queues: {
      pending_approvals: [
        {
          ticket_id: "h3rt_pending",
          unit_id: "E12U06",
          shot_id: "E12U06-S02",
          failure_class: "large_semantic_failure",
          lifecycle: { state: "awaiting_approval" },
        },
      ],
      approved_waiting: [
        {
          ticket_id: "h3rt_approved",
          unit_id: "E13U03",
          shot_id: "E13U03-S01",
          failure_class: "identity_continuity_failure",
          lifecycle: { state: "approved" },
        },
      ],
      active_executions: [],
      human_review_required: [],
    },
  };
}

describe("H3StudioDashboard", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.restoreAllMocks();
    vi.spyOn(API, "getH3StudioSummary").mockResolvedValue(makeSummary());
  });

  it("loads authoritative summary and renders queue and budget facts", async () => {
    render(<H3StudioDashboard projectName="demo" />);

    expect(await screen.findByText("H3 生产控制台")).toBeInTheDocument();
    expect(screen.getByText("E12U06")).toBeInTheDocument();
    expect(screen.getByText("E13U03")).toBeInTheDocument();
    expect(screen.getByText("CNY 4.50")).toBeInTheDocument();
    expect(API.getH3StudioSummary).toHaveBeenCalledWith("demo");
  });

  it("pauses fresh admission and refreshes from server truth", async () => {
    const pause = vi.spyOn(API, "setH3StudioPaused").mockResolvedValue({
      project_name: "demo",
      paused: true,
      max_running_tasks: 2,
      explicit: true,
    });

    render(<H3StudioDashboard projectName="demo" />);
    await screen.findByText("H3 生产控制台");

    fireEvent.click(screen.getByRole("button", { name: "暂停" }));

    await waitFor(() => {
      expect(pause).toHaveBeenCalledWith("demo", true);
      expect(API.getH3StudioSummary).toHaveBeenCalledTimes(2);
    });
  });

  it("updates the project running cap through the accepted control endpoint", async () => {
    const cap = vi.spyOn(API, "setH3StudioRunningCap").mockResolvedValue({
      project_name: "demo",
      paused: false,
      max_running_tasks: 3,
      explicit: true,
    });

    render(<H3StudioDashboard projectName="demo" />);
    await screen.findByText("H3 生产控制台");

    const input = screen.getByLabelText("并发修复上限");
    fireEvent.change(input, { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "应用" }));

    await waitFor(() => {
      expect(cap).toHaveBeenCalledWith("demo", 3);
    });
  });

  it("previews approval before executing eligible tickets", async () => {
    const preview = vi.spyOn(API, "previewH3StudioBatch").mockResolvedValue({
      project_name: "demo",
      action: "approve",
      items: [
        {
          ticket_id: "h3rt_pending",
          action: "approve",
          eligible: true,
          reason: "approval_pending",
        },
      ],
    });
    const execute = vi.spyOn(API, "executeH3StudioBatch").mockResolvedValue({
      project_name: "demo",
      action: "approve",
      items: [
        {
          ticket_id: "h3rt_pending",
          action: "approve",
          success: true,
          result: {},
          error_type: null,
          error_message: null,
        },
      ],
    });

    render(<H3StudioDashboard projectName="demo" />);
    await screen.findByText("H3 生产控制台");

    fireEvent.click(screen.getByRole("checkbox", { name: /E12U06/ }));
    fireEvent.click(screen.getByRole("button", { name: /预览审批/ }));

    await waitFor(() => {
      expect(preview).toHaveBeenCalledWith("demo", "approve", ["h3rt_pending"], undefined);
    });

    fireEvent.click(await screen.findByRole("button", { name: "执行符合条件项" }));

    await waitFor(() => {
      expect(execute).toHaveBeenCalledWith("demo", "approve", ["h3rt_pending"], undefined);
    });
  });

  it("keeps enqueue as a separate preview and execute path", async () => {
    const preview = vi.spyOn(API, "previewH3StudioBatch").mockResolvedValue({
      project_name: "demo",
      action: "enqueue",
      items: [
        {
          ticket_id: "h3rt_approved",
          action: "enqueue",
          eligible: true,
          reason: "approved",
        },
      ],
    });

    render(<H3StudioDashboard projectName="demo" />);
    await screen.findByText("H3 生产控制台");

    fireEvent.click(screen.getByRole("checkbox", { name: /E13U03/ }));
    fireEvent.click(screen.getByRole("button", { name: /预览入队/ }));

    await waitFor(() => {
      expect(preview).toHaveBeenCalledWith("demo", "enqueue", ["h3rt_approved"], undefined);
    });
  });
});
