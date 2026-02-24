/**
 * Centralized API URL and Fetch Helper
 *
 * Supports all modes without breaking current or deployment setup:
 * - Direct: NEXT_PUBLIC_API_BASE_URL
 * - Dev proxy: NEXT_PUBLIC_USE_PROXY=true → /api/proxy
 * - Legacy: NEXT_PUBLIC_BACKEND_URL or NEXT_PUBLIC_API_URL
 * - Same-origin: no vars → ""
 *
 * credentials: "include" is ALWAYS set in apiFetch so login works in direct mode.
 */

const DIRECT = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
const USE_PROXY = process.env.NEXT_PUBLIC_USE_PROXY === 'true';
const LEGACY =
  process.env.NEXT_PUBLIC_BACKEND_URL?.trim() ||
  process.env.NEXT_PUBLIC_API_URL?.trim();

export function getApiBase(): string {
  if (DIRECT) return DIRECT;
  if (USE_PROXY) return '/api/proxy';
  if (LEGACY) return LEGACY;
  return '';
}

export function apiUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${getApiBase()}${cleanPath}`;
}

export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  return fetch(apiUrl(path), {
    ...options,
    // CRITICAL: Always last so callers cannot override — required for session cookie in direct mode
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...options.headers,
    },
  });
}
