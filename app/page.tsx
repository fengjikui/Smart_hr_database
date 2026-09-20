// 工作台首页入口：页面只装配工作台，身份、聊天与表格状态在 components/workspace 中管理。
import HRWorkspace from '@/components/workspace/workspace';
export default function Page() {
  return <HRWorkspace />;
}
