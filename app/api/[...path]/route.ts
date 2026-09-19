/**
 * V1 /api/* 与 V2 /api/v2/* 共用的同源代理。浏览器只访问前端域名，
 * 由服务端转发到 FastAPI；这里不解释查询计划，也不代替后端判断权限。
 * HR_BACKEND_URL 仅在服务端读取，数据库、模型和 Superset 凭据均不交给浏览器。
 */
const BACKEND = process.env.HR_BACKEND_URL || 'http://127.0.0.1:8000';
async function proxy(request: Request) {
  const url = new URL(request.url);
  const headers = new Headers();
  // 明确转发会话 Cookie、CSRF 和来源头，供后端校验请求；其余客户端头不透传。
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
    // 按 UTF-8 字节数限制请求大小，避免中文字符长度与实际负载大小混淆。
    if (body && new TextEncoder().encode(body).length > 8192)
      return Response.json({ detail: '请求内容过长。' }, { status: 413 });
    // 保留原始 API 路径和查询参数；超时覆盖本地模型推理，禁止上游重定向。
    const upstream = await fetch(`${BACKEND}${url.pathname}${url.search}`, {
      method: request.method,
      headers,
      body,
      signal: AbortSignal.timeout(195000),
      redirect: 'error',
    });
    // 会话建立、文件导出和失败调试所需的头单独放行，响应体不在代理层改写。
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
    // 查询结果与当前身份绑定，禁止共享缓存把某人的结果复用给其他人。
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
