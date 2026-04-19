export type Health = {
  status: string;
  environment: string;
  database: string;
  cache: string;
  worker: string;
  provider: string;
  model_fast: string;
  model_power: string;
};

export type TicketInput = {
  ticket_id: string;
  customer_email: string;
  subject: string;
  body: string;
  source?: string;
  tier?: number;
  created_at?: string;
  expected_action?: string;
};

export type ToolCallEntry = {
  tool_name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  error?: string | null;
  why?: string;
  timestamp?: string;
};

export type TicketResult = {
  ticket_id: string;
  status: string;
  response?: string;
  category?: string;
  priority?: string;
  confidence?: number;
  tool_calls_count?: number;
  tool_calls?: ToolCallEntry[];
  model_used?: string;
  model_tier?: string;
  reasoning_steps?: string[];
  escalation_summary?: string;
};

export type AsyncQueued = {
  mode: string;
  task_id: string;
  ticket_id: string;
  status: string;
  poll_url?: string;
};

export type TaskStatus = {
  task_id: string;
  status: string;
  detail?: string;
  result?: unknown;
  error?: string;
};

export type AuditEntry = {
  ticket_id: string;
  status: string;
  category?: string;
  priority?: string;
  confidence?: number;
  tool_calls?: ToolCallEntry[];
  reasoning?: string[];
  started_at?: string;
  final_response?: string;
  retries?: number;
};

export type CostsResponse = {
  total_tickets: number;
  total_cost_usd: number;
  total_tokens: number;
  avg_cost_per_ticket?: number;
  per_ticket: {
    ticket_id: string;
    model_used: string;
    model_tier: string;
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: number;
  }[];
};
