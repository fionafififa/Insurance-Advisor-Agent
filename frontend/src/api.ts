import type {
  AuthSession,
  ChatHistory,
  ChatThread,
  InsuranceCategory,
  PlanInterrupt,
  Product,
} from './types';

export const API_BASE = '/api/v1';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(
  path: string,
  { accessToken, headers: initialHeaders, ...init }: RequestInit & { accessToken?: string } = {},
): Promise<T> {
  const headers = new Headers(initialHeaders);
  headers.set('Content-Type', 'application/json');
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  });
  if (!response.ok) {
    throw await readApiError(response, '请求失败，请稍后重试');
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function readApiError(response: Response, fallback: string): Promise<ApiError> {
  const body = await response.json().catch(() => null);
  const message = typeof body?.detail === 'string' ? body.detail : body?.message;
  return new ApiError(typeof message === 'string' ? message : fallback, response.status);
}

interface LoginResponse {
  access_token: string;
  user: Omit<AuthSession['user'], 'displayName'> & {
    display_name?: string | null;
    displayName?: string | null;
  };
}

export async function login(username: string, password: string): Promise<AuthSession> {
  const result = await request<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  if (!result?.access_token || !result.user) {
    throw new ApiError('登录响应缺少会话信息，请稍后重试', 502);
  }
  const { user } = result;
  return {
    accessToken: result.access_token,
    user: {
      id: user.id,
      username: user.username,
      email: user.email,
      displayName: user.display_name ?? user.displayName ?? null,
    },
  };
}

export function listProducts(
  category: InsuranceCategory | 'all',
  signal?: AbortSignal,
): Promise<Product[]> {
  const params = new URLSearchParams();
  if (category !== 'all') {
    params.set('category', category);
  }
  const query = params.toString();
  return request<Product[]>(`/products${query ? `?${query}` : ''}`, { signal });
}

export function markPlanItemInsured(
  accessToken: string,
  planId: string,
  itemId: string,
): Promise<unknown> {
  return request<unknown>(
    `/insurance-plans/${encodeURIComponent(planId)}/items/${encodeURIComponent(itemId)}/insured`,
    { accessToken, method: 'PATCH' },
  );
}

export function getInsurancePlan(accessToken: string, planId: string): Promise<unknown> {
  return request<unknown>(
    `/insurance-plans/${encodeURIComponent(planId)}`,
    { accessToken },
  );
}

export function listChatThreads(accessToken: string): Promise<ChatThread[]> {
  return request<ChatThread[]>('/chat-threads', { accessToken });
}

export function createChatThread(accessToken: string, title = '保险咨询'): Promise<ChatThread> {
  return request<ChatThread>('/chat-threads', {
    accessToken,
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export function getChatHistory(accessToken: string, threadId: string): Promise<ChatHistory> {
  return request<ChatHistory>(`/chat-threads/${threadId}/messages`, { accessToken });
}

export function renameChatThread(
  accessToken: string,
  threadId: string,
  title: string,
): Promise<ChatThread> {
  return request<ChatThread>(`/chat-threads/${threadId}`, {
    accessToken,
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });
}

export async function deleteChatThread(accessToken: string, threadId: string): Promise<void> {
  await request<void>(`/chat-threads/${threadId}`, {
    accessToken,
    method: 'DELETE',
  });
}

export async function streamChat(
  accessToken: string,
  threadId: string,
  input: { message?: string; decision?: Record<string, unknown> },
  handlers: {
    onMessage: (chunk: string) => void;
    onAdditionalInfo?: (info: unknown) => void;
    onInterrupt?: (interrupt: PlanInterrupt) => void;
  },
): Promise<void> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ thread_id: threadId, ...input }),
  });
  if (!response.ok || !response.body) {
    throw await readApiError(response, '消息发送失败，请稍后重试');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() ?? '';
    parts.forEach((eventText) => handleSseEvent(eventText, handlers));
  }
  if (buffer.trim()) {
    handleSseEvent(buffer, handlers);
  }
}

function handleSseEvent(
  eventText: string,
  handlers: {
    onMessage: (chunk: string) => void;
    onAdditionalInfo?: (info: unknown) => void;
    onInterrupt?: (interrupt: PlanInterrupt) => void;
  },
) {
  const lines = eventText.split(/\r?\n/);
  const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim();
  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n');
  if (!data) return;
  if (event === 'message') {
    handlers.onMessage(parseSseMessage(data));
    return;
  }
  if (event === 'interrupt') {
    const interrupt = parseInterrupt(data);
    if (interrupt) handlers.onInterrupt?.(interrupt);
    return;
  }
  if (event === 'additional_info') {
    handlers.onAdditionalInfo?.(parseJsonLike(data) ?? data);
  }
}

function parseSseMessage(data: string): string {
  try {
    const value = JSON.parse(data) as unknown;
    return typeof value === 'string' ? value : JSON.stringify(value);
  } catch {
    return data;
  }
}

function parseInterrupt(data: string): PlanInterrupt | null {
  const parsed = parseJsonLike(data);
  const value = Array.isArray(parsed) ? parsed[0] : parsed;
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Partial<PlanInterrupt>;
  if (!('plan' in candidate) || typeof candidate.confirm_info !== 'string') return null;
  return {
    plan: candidate.plan,
    confirm_info: candidate.confirm_info,
    action: Array.isArray(candidate.action)
      ? candidate.action.filter((item): item is 'approve' | 'reject' =>
          item === 'approve' || item === 'reject',
        )
      : ['approve', 'reject'],
  };
}

function parseJsonLike(data: string): unknown {
  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
}
