// V2 的 /demo 入口：页面只装配工作台，身份、聊天与表格状态在 components/demo 中管理。
import DemoWorkspace from '@/components/demo/workspace';
export default function Page() {
  return <DemoWorkspace />;
}
