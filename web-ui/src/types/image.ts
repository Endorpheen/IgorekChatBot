export type ImageJobStatus = 'queued' | 'running' | 'done' | 'error';

export interface ImageJobCreateResponse {
  job_id: string;
  status: 'queued';
}

export interface ImageJobStatusResponse {
  job_id: string;
  status: ImageJobStatus;
  provider: string;
  prompt: string;
  width: number;
  height: number;
  steps: number;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  result_url?: string | null;
}

export interface ImageModelCapabilities {
  model: string;
  steps_allowed: number[];
  default_steps: number;
  sizes_allowed: number[];
  default_size: number;
}
