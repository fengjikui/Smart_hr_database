// 全站共享的文档外壳与基础样式。所有页面复用同一业务协议和身份状态。
import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {
  title: '澄观 · HR 智能数据工作台',
  description: '在授权范围内探索组织、人员、教育背景与入离职信息，演示数据均为合成数据。',
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
