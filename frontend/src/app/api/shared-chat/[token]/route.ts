import { NextRequest, NextResponse } from 'next/server';

const BACKEND_BASE =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8002';

function buildBackendUrl(token: string) {
  const base = BACKEND_BASE.replace(/\/$/, '');
  return `${base}/chat/shared/${token}`;
}

// Helper function to get CORS headers
function getCorsHeaders(origin: string | null) {
  const allowedOrigins = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'https://ai.cloudfuze.com',
  ];

  const originHeader = origin || '';
  const isAllowedOrigin = allowedOrigins.includes(originHeader);

  return {
    'Access-Control-Allow-Origin': isAllowedOrigin ? originHeader : allowedOrigins[0],
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Accept, Cookie, Authorization',
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Max-Age': '86400',
  };
}

async function proxySharedChatRequest(token: string, request: NextRequest) {
  const backendUrl = buildBackendUrl(token);
  const origin = request.headers.get('origin');

  const headers = new Headers();
  headers.set('Accept', 'application/json');
  headers.set('Content-Type', 'application/json');

  const cookieHeader = request.headers.get('cookie');
  if (cookieHeader) {
    headers.set('Cookie', cookieHeader);
  }

  // Forward authorization header if present
  const authHeader = request.headers.get('authorization');
  if (authHeader) {
    headers.set('Authorization', authHeader);
  }

  try {
    const backendResponse = await fetch(backendUrl, {
      method: 'GET',
      headers,
      credentials: 'include',
    });

    const responseText = await backendResponse.text();

    // Build response headers with CORS
    const responseHeaders = new Headers({
      'Content-Type': backendResponse.headers.get('content-type') || 'application/json',
      ...getCorsHeaders(origin),
    });

    // Forward CORS headers from backend if present
    const backendCorsOrigin = backendResponse.headers.get('access-control-allow-origin');
    if (backendCorsOrigin) {
      responseHeaders.set('Access-Control-Allow-Origin', backendCorsOrigin);
    }

    const response = new NextResponse(responseText, {
      status: backendResponse.status,
      headers: responseHeaders,
    });

    // Forward Set-Cookie header if present
    const setCookie = backendResponse.headers.get('set-cookie');
    if (setCookie) {
      response.headers.set('Set-Cookie', setCookie);
    }

    return response;
  } catch (error) {
    console.error('[API] Backend fetch error:', error);
    throw error;
  }
}

// Handle OPTIONS preflight requests
export async function OPTIONS(
  request: NextRequest,
  context: { params: Promise<{ token: string }> }
) {
  const origin = request.headers.get('origin');
  
  return new NextResponse(null, {
    status: 204,
    headers: getCorsHeaders(origin),
  });
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ token: string }> }
) {
  const params = await context.params;
  const token = params?.token;

  if (!token) {
    const origin = request.headers.get('origin');
    return NextResponse.json(
      { error: 'Missing share token' },
      { 
        status: 400,
        headers: getCorsHeaders(origin),
      }
    );
  }

  try {
    return await proxySharedChatRequest(token, request);
  } catch (error) {
    console.error('[API] Failed to proxy shared chat request:', error);
    const origin = request.headers.get('origin');
    return NextResponse.json(
      { error: 'Failed to proxy shared chat request' },
      { 
        status: 502,
        headers: getCorsHeaders(origin),
      }
    );
  }
}

