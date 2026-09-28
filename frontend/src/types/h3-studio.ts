export type H3RepairBatchAction = "approve" | "reject" | "cancel" | "enqueue";

export interface H3StudioControl {
  project_name: string;
  paused: boolean;
  max_running_tasks: number | null;
  explicit: boolean;
}

export interface H3StudioProjectProjection {
  project_name: string;
  state_counts?: Record<string, number>;
  episode_summaries?: unknown[];
  [key: string]: unknown;
}

export interface H3StudioActualCall {
  call_id: number;
  task_id: string;
  provider: string;
  model: string;
  status: string;
  cost_amount: number;
  currency: string;
}

export interface H3StudioTicketLedger {
  ticket_id: string;
  unit_id: string;
  shot_id: string | null;
  execution_task_id: string | null;
  max_provider_calls: number | null;
  reserved_provider_calls: number;
  actual_calls: H3StudioActualCall[];
  actual_cost_by_currency: Record<string, number>;
  pricing_state: string;
}

export interface H3StudioBudgetLedger {
  project_name: string;
  provider_call_ceiling: number | null;
  reserved_provider_calls: number;
  remaining_provider_calls: number | null;
  budget_counter_reconciled: boolean | null;
  tickets: H3StudioTicketLedger[];
  actual_cost_by_currency: Record<string, number>;
  unpriced_call_count: number;
}

export interface H3StudioRepairTicketView {
  ticket_id: string;
  unit_id?: string;
  shot_id?: string | null;
  failure_class?: string;
  repair_action?: string;
  lifecycle: { state: string; [key: string]: unknown };
  execution?: Record<string, unknown> | null;
  provider_call_allowance?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface H3StudioSummary {
  project: H3StudioProjectProjection;
  control: H3StudioControl;
  budget: H3StudioBudgetLedger;
  queues: {
    pending_approvals: H3StudioRepairTicketView[];
    approved_waiting: H3StudioRepairTicketView[];
    active_executions: H3StudioRepairTicketView[];
    human_review_required: H3StudioRepairTicketView[];
  };
}

export interface H3StudioBatchPreviewItem {
  ticket_id: string;
  unit_id?: string;
  shot_id?: string | null;
  lifecycle_state?: string;
  action: H3RepairBatchAction;
  eligible: boolean;
  reason: string;
  execution_task_id?: string | null;
}

export interface H3StudioBatchPreview {
  project_name: string;
  action: H3RepairBatchAction;
  items: H3StudioBatchPreviewItem[];
}

export interface H3StudioBatchExecutionItem {
  ticket_id: string;
  action: H3RepairBatchAction;
  success: boolean;
  result: Record<string, unknown> | null;
  error_type: string | null;
  error_message: string | null;
}

export interface H3StudioBatchExecution {
  project_name: string;
  action: H3RepairBatchAction;
  items: H3StudioBatchExecutionItem[];
}
