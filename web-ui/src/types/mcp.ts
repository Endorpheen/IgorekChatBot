export type McpTransport = 'websocket' | 'http-sse';
export type McpStatus = 'ok' | 'unreachable' | 'invalid_url' | 'timeout' | 'ssrf_blocked' | 'error';

export interface McpServer {
  id: string;
  name: string;
  transport: McpTransport;
  url: string;
  headers: string[];
  allow_tools: string[];
  timeout_s?: number;
  max_output_kb?: number;
  notes?: string;
  max_calls_per_minute_per_thread?: number;
  status?: McpStatus;
}

export interface HeaderEntry {
  key: string;
  value: string;
  isSecret?: boolean;
}

export interface McpServerForm {
  id: string;
  name: string;
  transport: McpTransport;
  url: string;
  headers: HeaderEntry[];
  timeout_s?: number;
  max_output_kb?: number;
  notes?: string;
  allow_tools: string[];
  max_calls_per_minute_per_thread?: number;
}

export interface McpTool {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown> | null;
}

export interface McpProbeResponse {
  status: McpStatus;
  tools: McpTool[];
  error?: string;
  cached: boolean;
}

export interface McpBinding {
  server_id: string;
  thread_id: string;
  enabled_tools: string[];
}

export type McpRunStatus = 'ok' | 'error' | 'timeout' | 'rate_limited' | 'forbidden';

export interface McpRunResult {
  trace_id: string;
  status: McpRunStatus;
  output?: unknown;
  error?: string;
  truncated?: boolean;
  duration_ms?: number;
}
