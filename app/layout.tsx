import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {
  title: '澄观 · HR 智能数据工作台',
  description: '在授权范围内探索组织、人员与考勤，演示数据均为合成数据。',
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
