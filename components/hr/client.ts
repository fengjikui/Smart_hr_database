/**
 * V1 HTTP 与资源读取工具，只处理 /api 下原版协议；V2 使用 components/demo/types.ts。
 * 会话由同源 Cookie 承载，读请求禁缓存，写请求通过 mutation 附加 CSRF。
 */
import { useCallback, useEffect, useState } from 'react';

export class ApiError extends Error {
  // 后端失败时保留调试记录定位符，使 UI 能跳到实际失败节点，而不是丢失执行证据。
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
  // identity 必须参与请求 key；同一路径在不同身份下可能返回完全不同的数据。
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
  // 新身份或新参数加载期间绝不展示旧结果；取消旧网络请求之外还要约束已保存状态。
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
