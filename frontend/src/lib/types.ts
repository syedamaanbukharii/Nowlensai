// Types mirroring the NowLens API schemas (see docs/API.md).

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  csrf_token?: string | null;
}

export interface UserOut {
  id: string;
  email: string;
  role: "viewer" | "user" | "operator" | "admin";
  is_active: boolean;
}

export interface Citation {
  index: number;
  chunk_id: string;
  document_id: string;
  title: string;
  source_url: string;
  snippet: string;
}

export interface QaVerdict {
  grounded?: boolean;
  citations_valid?: boolean;
  answers_question?: boolean;
  issues?: string[];
  verdict?: "pass" | "revise";
  [key: string]: unknown;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  intent: string;
  domains: string[];
  citations: Citation[];
  analysis: Record<string, unknown> | null;
  qa: QaVerdict;
  grounded: boolean;
  metrics: Record<string, unknown>;
}

export interface SearchHit {
  chunk_id: string;
  score: number;
  title: string;
  source_url: string;
  domains: string[];
  snippet: string;
  retriever: string;
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
  citations: Citation[];
  metrics: Record<string, unknown>;
}

export interface DomainOut {
  key: string;
  name: string;
  category: string;
  description: string;
  aliases: string[];
  related: string[];
}

export interface JobOut {
  id: string;
  url: string;
  status: "pending" | "running" | "succeeded" | "failed" | "skipped";
  detail: string;
  chunks_indexed: number;
  duplicates_removed: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentOut {
  id: string;
  url: string;
  title: string;
  domains: string[];
  chunk_count: number;
  last_ingested_at: string | null;
}

export interface IngestReport {
  url: string;
  document_id: string | null;
  success: boolean;
  chunks_indexed: number;
  duplicates_removed: number;
  skipped: boolean;
  error: string | null;
  stages: { name: string; ok: boolean; detail: string; items: number }[];
}

export interface ApiErrorBody {
  code: string;
  message: string;
  trace_id: string | null;
}
