// API client. Base URL and token live in storage (Settings tab); every call
// goes through `api()` so auth and errors are handled in one place.
import { Platform } from 'react-native';

import { getItem, setItem } from './storage';

const DEFAULT_BASE = Platform.OS === 'web' ? 'http://localhost:8000' : 'http://localhost:8000';

let cached: { baseUrl: string; token: string } | null = null;

export async function getConfig() {
  if (!cached) {
    cached = {
      baseUrl: (await getItem('health.baseUrl')) || DEFAULT_BASE,
      token: (await getItem('health.token')) || '',
    };
  }
  return cached;
}

export async function saveConfig(baseUrl: string, token: string) {
  cached = { baseUrl: baseUrl.replace(/\/+$/, ''), token };
  await setItem('health.baseUrl', cached.baseUrl);
  await setItem('health.token', token);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function headers(extra: Record<string, string> = {}) {
  const { token } = await getConfig();
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra };
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { baseUrl } = await getConfig();
  const { json, ...rest } = init;
  const res = await fetch(baseUrl + path, {
    ...rest,
    headers: await headers({
      ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...((rest.headers as Record<string, string>) ?? {}),
    }),
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function upload<T>(path: string, file: { uri: string; name: string; type: string } | File): Promise<T> {
  const { baseUrl } = await getConfig();
  const form = new FormData();
  if (file instanceof File) form.append('file', file, file.name);
  else form.append('file', file as unknown as Blob);
  const res = await fetch(baseUrl + path, { method: 'POST', headers: await headers(), body: form });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return (await res.json()) as T;
}

// ---- chat streaming (SSE over fetch) -------------------------------------

export type ChatEvent =
  | { type: 'thread'; thread_id: number }
  | { type: 'text'; text: string }
  | { type: 'tool'; name: string }
  | { type: 'done'; stop_reason: string | null }
  | { type: 'error'; message: string };

export async function streamChat(
  message: string,
  threadId: number | null,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
) {
  const { baseUrl } = await getConfig();
  // expo/fetch streams response bodies on iOS/Android; the browser's fetch does on web.
  const doFetch: typeof fetch =
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    Platform.OS === 'web' ? fetch : (require('expo/fetch').fetch as typeof fetch);
  const res = await doFetch(baseUrl + '/api/chat', {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  });
  if (!res.ok || !res.body) {
    onEvent({ type: 'error', message: `HTTP ${res.status}: ${await res.text()}` });
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of frame.split('\n')) {
        if (line.startsWith('data:')) {
          try {
            onEvent(JSON.parse(line.slice(5).trim()) as ChatEvent);
          } catch {
            /* ignore malformed frame */
          }
        }
      }
    }
  }
}

// ---- types the screens use --------------------------------------------------

export type Insight = {
  id: number;
  kind: string;
  severity: 'info' | 'attention' | 'urgent';
  title: string;
  body: string;
  due_at: string | null;
  created_at: string;
  acknowledged_at: string | null;
};

export type Observation = {
  id: number;
  kind: string;
  value: string | null;
  unit: string | null;
  value_text: string | null;
  observed_at: string;
  source: string;
};

export type Medication = {
  id: number;
  name: string;
  dose: string | null;
  frequency: string | null;
  reason: string | null;
  active: boolean;
  last_taken_at: string | null;
};

export type Doc = {
  id: number;
  filename: string;
  kind: string | null;
  document_date: string | null;
  provider_name: string | null;
  status: 'pending' | 'processing' | 'processed' | 'failed';
  summary: string | null;
  error: string | null;
  uploaded_at: string;
};

export type Meal = { id: number; eaten_at: string; description: string; calories: string | null; protein_g: string | null };
export type Workout = { id: number; started_at: string; kind: string; duration_min: string | null; distance_km: string | null };
export type Thread = { id: number; title: string | null; updated_at: string };
export type ThreadMessage = { id: number; role: 'user' | 'assistant'; text: string };

export function fmtNum(v: string | number | null | undefined, digits = 1) {
  if (v === null || v === undefined) return '–';
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return Number.isFinite(n) ? n.toFixed(Number.isInteger(n) ? 0 : digits) : '–';
}

export function fmtWhen(iso: string | null | undefined) {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}
