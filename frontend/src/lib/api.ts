/**
 * Centralized API Fetch Helper
 * 
 * All backend API calls should use this helper to ensure:
 * - Same-origin requests (via Next.js proxy in development)
 * - Direct API calls in production (via reverse proxy/Nginx)
 * - Cookies are automatically included
 * - Consistent error handling
 * 
 * 🔒 SECURITY: Automatically switches between proxy (dev) and direct (prod)
 * based on NEXT_PUBLIC_USE_PROXY environment variable.
 */

/**
 * Get the API base URL for requests
 * - Development: Uses Next.js proxy (/api/proxy) if NEXT_PUBLIC_USE_PROXY=true
 * - Production: Uses direct backend URL from NEXT_PUBLIC_API_URL or NEXT_PUBLIC_BACKEND_URL
 * 
 * @returns The base URL for API requests (proxy path or direct backend URL)
 */
export function getApiBase(): string {
  // Check if proxy should be used (development only)
  const useProxy = process.env.NEXT_PUBLIC_USE_PROXY === 'true';
  
  if (useProxy) {
    // Development: Use Next.js proxy for same-origin cookie handling
    return '/api/proxy';
  }
  
  // Production: Use direct backend URL
  // Priority: NEXT_PUBLIC_BACKEND_URL > NEXT_PUBLIC_API_URL > default
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 
                     process.env.NEXT_PUBLIC_API_URL || 
                     '';
  
  // If no URL is set, default to empty (relative path - same origin)
  // This works when frontend and backend are on same domain via reverse proxy
  return backendUrl;
}

export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  // Ensure path starts with /
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  
  // Streaming endpoints: use text/event-stream so response is not buffered as JSON
  const isStreamPath = cleanPath.includes('/chat/stream') || cleanPath.includes('/retry/stream');
  const accept = isStreamPath ? 'text/event-stream' : 'application/json';
  
  // Get base URL (proxy path or direct backend URL)
  const base = getApiBase();
  const url = `${base}${cleanPath}`;
  
  return fetch(url, {
    ...options,
    credentials: 'include', // ⭐ CRITICAL: Always include cookies
    headers: {
      'Content-Type': 'application/json',
      'Accept': accept, // ⭐ text/event-stream for streaming to avoid buffering
      ...options.headers,
    },
  });
}

