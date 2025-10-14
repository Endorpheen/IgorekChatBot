export type ImageJobStatus = 'queued' | 'running' | 'done' | 'error';

export interface ImageJobCreateResponse {
  job_id: string;
  status: 'queued';
}

export interface ImageJobStatusResponse {
  job_id: string;
  status: ImageJobStatus;
  provider: string;
  model: string;
  prompt: string;
  width: number;
  height: number;
  steps: number;
  cfg?: number | null;
  seed?: number | null;
  mode?: string | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  result_url?: string | null;
}

export interface ProviderSummary {
  id: string;
  label: string;
  enabled: boolean;
  description?: string | null;
  recommended_models: string[];
}

export interface ProviderModelCapabilities {
  supports_steps?: boolean;
  supports_cfg?: boolean;
  supports_seed?: boolean;
  supports_mode?: boolean;
  modes?: { id: string; label?: string; description?: string }[];
}

export interface ProviderModelLimits {
  min_steps?: number;
  max_steps?: number;
  min_cfg?: number;
  max_cfg?: number;
  min_width?: number;
  max_width?: number;
  min_height?: number;
  max_height?: number;
  width_values?: number[];
  height_values?: number[];
  presets?: [number, number][] | number[][];
}

export interface ProviderModelDefaults {
  width?: number;
  height?: number;
  steps?: number;
  cfg?: number;
  seed?: number;
  mode?: string;
}

export interface ProviderModelSpec {
  id: string;
  display_name: string;
  recommended: boolean;
  capabilities: ProviderModelCapabilities;
  limits: ProviderModelLimits;
  defaults: ProviderModelDefaults;
  metadata?: Record<string, unknown>;
}

export interface ProviderModelsResponse {
  provider: string;
  models: ProviderModelSpec[];
}

export interface ProviderListResponse {
  providers: ProviderSummary[];
}
