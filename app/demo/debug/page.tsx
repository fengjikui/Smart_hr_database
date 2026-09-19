// V2 的独立调试入口。仍复用同一身份壳；?run= 只定位记录，不代表获得记录访问权。
import type { Metadata } from 'next';
import { Suspense } from 'react';
import DemoWorkspace from '@/components/demo/workspace';

export const metadata: Metadata = { title: '节点调试 · 澄观 HR' };

export default function Page() {
  // 内部调试组件读取 URL 查询参数，Suspense 为这段客户端状态提供加载边界。
  return (
    <Suspense fallback={<p>正在加载节点调试…</p>}>
      <DemoWorkspace debug />
    </Suspense>
  );
}
