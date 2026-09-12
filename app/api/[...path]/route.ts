const BACKEND = process.env.HR_BACKEND_URL || 'http://127.0.0.1:8000';
async function proxy(request: Request) {
  const url = new URL(request.url);
  const headers = new Headers();
  for (const key of [
    'content-type',
    'cookie',
    'x-csrf-token',
    'origin',
    'sec-fetch-site',
  ]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  try {
    const body = ['GET', 'HEAD'].includes(request.method)
      ? undefined
      : await request.text();
    if (body && new TextEncoder().encode(body).length > 8192)
      return Response.json({ detail: '请求内容过长。' }, { status: 413 });
    const upstream = await fetch(`${BACKEND}${url.pathname}${url.search}`, {
      method: request.method,
      headers,
      body,
      signal: AbortSignal.timeout(195000),
      redirect: 'error',
    });
    const responseHeaders = new Headers();
    for (const key of [
      'content-type',
      'set-cookie',
      'content-disposition',
      'retry-after',
      'x-debug-run-id',
    ]) {
      const value = upstream.headers.get(key);
      if (value) responseHeaders.set(key, value);
    }
    responseHeaders.set('Cache-Control', 'no-store, private');
    responseHeaders.set('X-Content-Type-Options', 'nosniff');
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { detail: '数据服务暂时未连接，请启动本地后端后重试。' },
      { status: 503 },
    );
  }
}
export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
