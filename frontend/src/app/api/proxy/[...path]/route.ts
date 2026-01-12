/**
 * Next.js API Proxy Route
 * 
 * ✅ This proxy route is used for backend API calls in DEVELOPMENT ONLY:
 * - Same-origin requests (no CORS issues)
 * - Cookies are automatically forwarded
 * - Helps with localhost cookie handling
 * 
 * 🔒 SECURITY: This proxy is HARD-DISABLED in production for security.
 * In production, use direct API calls with proper CORS/reverse proxy setup.
 * 
 * All frontend API calls should use the `apiFetch()` helper which handles
 * proxy vs direct routing automatically.
 */

import { NextRequest, NextResponse } from 'next/server';
// ⚠️ CRITICAL: Use axios with proper configuration to access Set-Cookie headers
import axios from 'axios';

// 🔒 SECURITY: Hard-disable proxy in production
// This prevents any proxy access even if route is accidentally called
const isProduction = process.env.NODE_ENV === 'production';

// Helper function to return production block response
function productionBlockResponse() {
  return NextResponse.json(
    { 
      error: 'Proxy disabled in production',
      message: 'This proxy route is only available in development. Use direct API calls in production.'
    },
    { status: 403 }
  );
}

// Get backend URL from environment or default to localhost
// ⚠️ CRITICAL: Must use 'localhost' (not 127.0.0.1) for cookie domain matching
const BACKEND_BASE = (() => {
  const envUrl = process.env.NEXT_PUBLIC_BACKEND_URL || process.env.NEXT_PUBLIC_API_URL;
  if (envUrl) {
    // Replace 127.0.0.1 with localhost to ensure cookie domain consistency
    return envUrl.replace('127.0.0.1', 'localhost');
  }
  return 'http://localhost:8002';
})();

async function proxyRequest(
  request: NextRequest,
  pathSegments: string[],
  method: string
) {
  try {
    const path = pathSegments.join('/');
    // ⚠️ CRITICAL: Ensure we use localhost (not 127.0.0.1) for cookie domain matching
    let backendUrl = BACKEND_BASE;
    if (backendUrl.includes('127.0.0.1')) {
      backendUrl = backendUrl.replace('127.0.0.1', 'localhost');
      console.log(`[PROXY] ⚠️ Replaced 127.0.0.1 with localhost for cookie compatibility`);
    }
    const url = `${backendUrl}/${path}${request.nextUrl.search}`;
    
    console.log(`[PROXY] ${method} ${url}`);
    
    // ✅ STREAMING DETECTION: Check if this is a streaming endpoint
    const isStreamingEndpoint = path.includes('/chat/stream') || path.includes('/stream');
    
    // Get request body if present
    let body: string | undefined;
    if (method !== 'GET' && method !== 'HEAD') {
      try {
        body = await request.text();
      } catch {
        // No body, that's fine
      }
    }
    
    // ✅ STREAMING MODE: Use Node.js fetch for real-time streaming (axios buffers everything)
    if (isStreamingEndpoint) {
      try {
        const browserCookies = request.headers.get('cookie') || '';
        
        console.log('[PROXY] 🌊 Using streaming mode (Node.js fetch)');
        
        const backendResponse = await fetch(url, {
          method: method as any,
          headers: {
            'Content-Type': request.headers.get('content-type') || 'application/json',
            'Cookie': browserCookies,
          },
          body: body,
        });
        
        // Create a ReadableStream to forward chunks in real-time
        const stream = new ReadableStream({
          async start(controller) {
            const reader = backendResponse.body?.getReader();
            
            if (!reader) {
              controller.close();
              return;
            }
            
            try {
              while (true) {
                const { done, value } = await reader.read();
                if (done) {
                  controller.close();
                  break;
                }
                // Forward chunk immediately (no buffering)
                controller.enqueue(value);
              }
            } catch (error) {
              console.error('[PROXY] ❌ Streaming error:', error);
              controller.error(error);
            }
          }
        });
        
        // Create response with streaming body
        const proxiedResponse = new NextResponse(stream, {
          status: backendResponse.status,
          statusText: backendResponse.statusText || '',
          headers: {
            'Content-Type': backendResponse.headers.get('content-type') || 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
          },
        });
        
        // Forward Set-Cookie header if present (though streaming endpoints typically don't set cookies)
        const setCookieHeader = backendResponse.headers.get('set-cookie');
        if (setCookieHeader) {
          proxiedResponse.headers.set('Set-Cookie', setCookieHeader);
          console.log('[PROXY] ✅ Forwarded Set-Cookie header in streaming response');
        }
        
        return proxiedResponse;
      } catch (fetchError) {
        console.error('[PROXY] ❌ Streaming fetch error:', fetchError);
        const errorMessage = fetchError instanceof Error ? fetchError.message : 'Unknown error';
        const isConnectionRefused = errorMessage.includes('ECONNREFUSED') || errorMessage.includes('connect');
        
        return NextResponse.json(
          { 
            error: 'Backend connection failed', 
            message: errorMessage,
            hint: isConnectionRefused 
              ? 'Backend server is not running. Please start it with: python server.py' 
              : undefined
          },
          { status: 502 }
        );
      }
    }
    
    // ✅ NON-STREAMING MODE: Use axios for Set-Cookie header access
    // ⚠️ CRITICAL: Use axios instead of fetch to access Set-Cookie headers
    // Node.js fetch() strips Set-Cookie headers, but axios exposes them
    let axiosResponse;
    try {
      // ⭐ CRITICAL: Get cookies from browser request
      const browserCookies = request.headers.get('cookie') || '';
      
      // Use axios to make the request (exposes Set-Cookie headers)
      // ⚠️ CRITICAL: Configure axios to preserve all headers including Set-Cookie
      axiosResponse = await axios({
        method: method as 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH' | 'HEAD' | 'OPTIONS',
        url,
        headers: {
          'Content-Type': request.headers.get('content-type') || 'application/json',
          // ⭐ CRITICAL: Forward cookies from browser to backend
          cookie: browserCookies,
        },
        data: body,
        maxRedirects: 5,
        timeout: 35000, // 35 seconds (slightly longer than backend's 30s timeout)
        validateStatus: () => true, // Don't throw on any status code
        // ⚠️ CRITICAL: Don't use arraybuffer - use default to let axios parse headers correctly
        // Axios automatically exposes Set-Cookie in response.headers['set-cookie']
      });
    } catch (fetchError) {
      console.error('[PROXY] ❌ Axios error:', fetchError);
      const errorMessage = fetchError instanceof Error ? fetchError.message : 'Unknown error';
      const errorCode = (fetchError as any)?.code || '';
      const isConnectionRefused = errorMessage.includes('ECONNREFUSED') || 
                                  errorMessage.includes('connect') || 
                                  errorCode === 'ECONNREFUSED';
      const isConnectionReset = errorCode === 'ECONNRESET' || 
                                errorMessage.includes('ECONNRESET');
      const isTimeout = errorCode === 'ECONNABORTED' || 
                       errorMessage.includes('timeout') ||
                       errorMessage.includes('ETIMEDOUT');
      
      return NextResponse.json(
        { 
          error: 'Backend connection failed', 
          message: errorMessage,
          code: errorCode,
          hint: isConnectionRefused 
            ? 'Backend server is not running. Please start it with: python server.py'
            : isConnectionReset
            ? 'Backend server closed the connection. It may be overloaded, crashed, or taking too long to respond.'
            : isTimeout
            ? 'Request timed out. The backend server may be slow or unresponsive.'
            : undefined
        },
        { status: 502 }
      );
    }
    
    // 🔍 Check for Set-Cookie header (only log when found - missing is expected for most endpoints)
    const setCookieHeaders = axiosResponse.headers['set-cookie'] || 
                             axiosResponse.headers['Set-Cookie'] ||
                             axiosResponse.headers['SET-COOKIE'];
    
    // Get response body and content type
    let responseBody: string;
    if (typeof axiosResponse.data === 'string') {
      responseBody = axiosResponse.data;
    } else if (axiosResponse.data instanceof Buffer) {
      responseBody = axiosResponse.data.toString('utf-8');
    } else {
      // For JSON or other types, stringify
      responseBody = JSON.stringify(axiosResponse.data);
    }
    const contentType = axiosResponse.headers['content-type'] || 'application/json';
    
    // Create response with same status and content type
    const proxiedResponse = new NextResponse(responseBody, {
      status: axiosResponse.status,
      statusText: axiosResponse.statusText || '',
      headers: {
        'Content-Type': contentType,
      },
    });
    
    // 🔥 CRITICAL FIX: Forward Set-Cookie headers from backend to browser
    // Axios exposes Set-Cookie headers as an array in response.headers['set-cookie']
    try {
      let setCookieFound = false;
      
      // Axios stores Set-Cookie headers as an array
      if (setCookieHeaders) {
        const setCookies = Array.isArray(setCookieHeaders) ? setCookieHeaders : [setCookieHeaders];
        if (setCookies.length > 0) {
          console.log(`[PROXY] ✅ Found ${setCookies.length} Set-Cookie header(s) via axios - forwarding to browser`);
          setCookies.forEach((cookie, index) => {
            const cookiePreview = cookie.length > 60 ? cookie.substring(0, 60) + '...' : cookie;
            console.log(`[PROXY]   Set-Cookie ${index + 1}: ${cookiePreview}`);
            proxiedResponse.headers.append('Set-Cookie', cookie);
          });
          setCookieFound = true;
        }
      }
      
      // Only log when Set-Cookie is missing for endpoints that SHOULD set it (login/logout)
      // Most endpoints don't set cookies, so missing is expected and normal
      if (!setCookieFound && (path.includes('/auth/microsoft/callback') || path.includes('/auth/logout'))) {
        console.warn('[PROXY] ⚠️ Expected Set-Cookie header missing for auth endpoint:', path);
      }
    } catch (e) {
      console.error('[PROXY] ❌ Error handling Set-Cookie headers:', e);
      // Don't crash - just log the error and continue
    }
    
    // Forward other important headers (except content-type, set-cookie, and content-length which we handled above)
    // 🔒 CRITICAL FIX: Remove content-length to prevent ERR_CONTENT_LENGTH_MISMATCH
    // Next.js will calculate the correct content-length automatically
    try {
      Object.entries(axiosResponse.headers).forEach(([key, value]) => {
        const lowerKey = key.toLowerCase();
        // Skip headers that Next.js handles automatically or we've already handled
        if (lowerKey !== 'set-cookie' && 
            lowerKey !== 'content-type' && 
            lowerKey !== 'content-length' &&  // 🔒 CRITICAL: Remove to prevent mismatch
            lowerKey !== 'transfer-encoding') {  // Also skip transfer-encoding
          const headerValue = Array.isArray(value) ? value.join(', ') : String(value);
          proxiedResponse.headers.set(key, headerValue);
        }
      });
    } catch (headerError) {
      console.warn('[PROXY] ⚠️ Error forwarding headers (non-critical):', headerError);
      // Continue anyway - headers are not critical
    }
    
    return proxiedResponse;
  } catch (error) {
    console.error('[PROXY] ❌ Fatal error proxying request:', error);
    console.error('[PROXY] Error stack:', error instanceof Error ? error.stack : 'No stack trace');
    return NextResponse.json(
      { 
        error: 'Proxy error', 
        message: error instanceof Error ? error.message : 'Unknown error',
        details: process.env.NODE_ENV === 'development' ? (error instanceof Error ? error.stack : undefined) : undefined
      },
      { status: 500 }
    );
  }
}

// ✅ Next.js App Router: params might be a Promise, handle both cases
export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> | { path: string[] } }
) {
  // 🔒 SECURITY: Block proxy in production
  if (isProduction) {
    return productionBlockResponse();
  }
  const params = await Promise.resolve(context.params);
  return proxyRequest(request, params.path, 'GET');
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> | { path: string[] } }
) {
  // 🔒 SECURITY: Block proxy in production
  if (isProduction) {
    return productionBlockResponse();
  }
  const params = await Promise.resolve(context.params);
  return proxyRequest(request, params.path, 'POST');
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> | { path: string[] } }
) {
  // 🔒 SECURITY: Block proxy in production
  if (isProduction) {
    return productionBlockResponse();
  }
  const params = await Promise.resolve(context.params);
  return proxyRequest(request, params.path, 'PUT');
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> | { path: string[] } }
) {
  // 🔒 SECURITY: Block proxy in production
  if (isProduction) {
    return productionBlockResponse();
  }
  const params = await Promise.resolve(context.params);
  return proxyRequest(request, params.path, 'DELETE');
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> | { path: string[] } }
) {
  // 🔒 SECURITY: Block proxy in production
  if (isProduction) {
    return productionBlockResponse();
  }
  const params = await Promise.resolve(context.params);
  return proxyRequest(request, params.path, 'PATCH');
}

