import type { Metadata } from 'next';
import { Suspense } from 'react';
import DemoWorkspace from '@/components/demo/workspace';

export const metadata: Metadata = { title: '节点调试 · 澄观 HR' };

export default function Page() {
  return (
    <Suspense fallback={<p>正在加载节点调试…</p>}>
      <DemoWorkspace debug />
    </Suspense>
  );
}
