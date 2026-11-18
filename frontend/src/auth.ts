import type { AuthSession } from './types';

const STORAGE_KEY = 'insurance-mall-auth-v3';

export function readSession(): AuthSession | null {
  try {
    const value = window.sessionStorage.getItem(STORAGE_KEY);
    const session = value ? (JSON.parse(value) as AuthSession | null) : null;
    if (typeof session?.accessToken === 'string' && session.accessToken && session.user) {
      return session;
    }
  } catch {
    // A malformed stored session is treated as signed out.
  }
  return null;
}

export function saveSession(session: AuthSession): void {
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  window.sessionStorage.removeItem(STORAGE_KEY);
}
