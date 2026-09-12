'use client';
import { useState } from 'react';
import { ArrowUpRight, ChartNoAxesCombined, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
export default function Workspace() {
  const [question, setQuestion] = useState('');
  return <main className="initial-workspace">
    <header><strong>澄观 <small>HR Intelligence</small></strong><span>模拟数据 · 本地演示</span></header>
    <section><p className="eyebrow">人力数据工作台</p><h1>从一个问题，看清你的团队。</h1><p>人员、组织与考勤，在你的授权范围内查询。</p>
      <form onSubmit={e => e.preventDefault()}><Textarea aria-label="输入人力数据问题" value={question} onChange={e => setQuestion(e.target.value)} placeholder="例如：我的直属和间接下属分别有多少人？" /><Button disabled>正在连接数据服务 <ArrowUpRight /></Button></form>
      <div className="initial-notes"><span><ShieldCheck size={18} /> 按管理关系限制数据范围</span><span><ChartNoAxesCombined size={18} /> 查询结果可保存为看板</span></div>
    </section>
  </main>;
}
