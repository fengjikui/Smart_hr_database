import { useCallback, useEffect, useState } from 'react';

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public debugRunId?: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api${path}`, {
    ...init,
    credentials: 'same-origin',
    cache: 'no-store',
    headers,
  });
  const body = (await response.json()) as { detail?: unknown };
  if (!response.ok)
    throw new ApiError(
      typeof body.detail === 'string'
        ? body.detail
        : '请求未通过校验，请检查输入后重试。',
      response.status,
      response.headers.get('x-debug-run-id') ?? undefined,
    );
  return body as T;
}
export function mutation(
  csrf: string,
  data?: unknown,
  method = 'POST',
): RequestInit {
  return {
    method,
    headers: { 'X-CSRF-Token': csrf },
    body: data === undefined ? undefined : JSON.stringify(data),
  };
}
export function useResource<T>(path: string, identity: string) {
  const [state, setState] = useState<{
    key: string;
    data: T | null;
    error: string;
  }>({ key: '', data: null, error: '' });
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((v) => v + 1), []);
  const requestKey = `${identity}:${path}:${revision}`;
  useEffect(() => {
    const controller = new AbortController();
    api<T>(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ key: requestKey, data, error: '' });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({
            key: requestKey,
            data: null,
            error: String(error.message),
          });
      });
    return () => controller.abort();
  }, [path, requestKey]);
  // Old identity or parameter results are never rendered while a new request loads.
  const current = state.key === requestKey;
  return {
    data: current ? state.data : null,
    error: current ? state.error : '',
    loading: !current,
    reload,
  };
}
export function number(value: unknown, maxDigits = 1) {
  return typeof value === 'number'
    ? value.toLocaleString('zh-CN', { maximumFractionDigits: maxDigits })
    : '—';
}
