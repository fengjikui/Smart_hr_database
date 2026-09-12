'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Bug,
  Check,
  ChevronRight,
  CircleHelp,
  Database,
  GitBranch,
  LayoutDashboard,
  MessageSquare,
  PanelTop,
  ShieldCheck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from '@/components/ui/sidebar';
import { TooltipProvider } from '@/components/ui/tooltip';
import { api, mutation } from './client';
import { Failure, LoadingBlock } from './results';
import { DebugPanel } from './debug-panel';
import { DataDictionary } from './data-dictionary';
import {
  Boards,
  Catalog,
  Chat,
  Governance,
  Organization,
  Overview,
} from './views';
import type { Answer, Bootstrap, View } from './types';

const NAV = [
  { id: 'overview' as View, label: '数据总览', icon: PanelTop },
  { id: 'chat' as View, label: '智能问数', icon: MessageSquare },
  { id: 'boards' as View, label: '我的看板', icon: LayoutDashboard },
  { id: 'organization' as View, label: '组织与权限', icon: GitBranch },
  { id: 'catalog' as View, label: '指标字典', icon: BookOpen },
  { id: 'governance' as View, label: '数据治理', icon: Database },
  { id: 'dictionary' as View, label: '数据库与口径', icon: BookOpen },
  { id: 'debug' as View, label: '节点调试', icon: Bug },
];
function Navigation({
  view,
  onView,
}: {
  view: View;
  onView: (v: View) => void;
}) {
  const { setOpenMobile } = useSidebar();
  return (
    <SidebarMenu>
      {NAV.map(({ id, label, icon: Icon }, i) => (
        <SidebarMenuItem
          key={id}
          className={i === 3 ? 'nav-section-break' : ''}
        >
          <SidebarMenuButton
            className="hr-nav-item"
            isActive={view === id}
            onClick={() => {
              onView(id);
              setOpenMobile(false);
            }}
          >
            <Icon size={18} />
            <span>{label}</span>
            {id === 'chat' ? <span className="nav-new">AI</span> : null}
          </SidebarMenuButton>
        </SidebarMenuItem>
      ))}
    </SidebarMenu>
  );
}
export default function Workspace() {
  const [boot, setBoot] = useState<Bootstrap | null>(null);
  const [view, setView] = useState<View>('overview');
  const [error, setError] = useState('');
  const [switching, setSwitching] = useState(false);
  const [initial, setInitial] = useState('');
  const [toast, setToast] = useState('');
  const [chatKey, setChatKey] = useState(0);
  const [debugRunId, setDebugRunId] = useState<string | undefined>();
  const epoch = useRef(0);
  const initialize = useCallback(async (persona?: string) => {
    const version = ++epoch.current;
    setSwitching(true);
    setError('');
    setBoot(null);
    try {
      if (persona)
        await api('/demo/session', {
          method: 'POST',
          body: JSON.stringify({ persona_id: persona }),
        });
      let data: Bootstrap;
      try {
        data = await api<Bootstrap>('/bootstrap');
      } catch (e) {
        if (persona) throw e;
        await api('/demo/session', {
          method: 'POST',
          body: JSON.stringify({ persona_id: 'ceo' }),
        });
        data = await api<Bootstrap>('/bootstrap');
      }
      if (version !== epoch.current) return;
      setBoot(data);
      setInitial('');
      setDebugRunId(undefined);
      setChatKey((v) => v + 1);
    } catch (e) {
      if (version === epoch.current) setError((e as Error).message);
    } finally {
      if (version === epoch.current) setSwitching(false);
    }
  }, []);
  // Initial session bootstrap intentionally starts a network operation once on mount.
  useEffect(() => {
    // oxlint-disable-next-line react/react-compiler
    void initialize();
  }, [initialize]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(''), 3500);
    return () => clearTimeout(t);
  }, [toast]);
  function ask(q: string) {
    setInitial(q);
    setChatKey((v) => v + 1);
    setView('chat');
  }
  function openDebug(id?: string) {
    setDebugRunId(id);
    setView('debug');
  }
  async function save(answer: Answer) {
    if (!boot) return;
    await api(
      '/dashboards',
      mutation(boot.principal.csrf, {
        title: `${answer.metric.name}${answer.plan.dimension === 'none' ? '' : ` · ${answer.columns[0].label}`}`,
        plan: answer.plan,
      }),
    );
    setToast('已保存到“我的看板”，每次打开按当前权限刷新。');
  }
  async function download(answer: Answer) {
    if (!boot) return;
    const response = await fetch('/api/export', {
      ...mutation(boot.principal.csrf, answer.plan),
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': boot.principal.csrf,
      },
    });
    if (!response.ok) {
      const body = (await response.json()) as { detail?: string };
      throw new Error(body.detail ?? '导出失败');
    }
    const url = URL.createObjectURL(await response.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = `澄观-${answer.metric.name}-${answer.as_of}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <TooltipProvider>
      <SidebarProvider
        style={{ '--sidebar-width': '228px' } as React.CSSProperties}
      >
        <a className="skip-link" href="#main-content">
          跳到主要内容
        </a>
        <Sidebar className="hr-sidebar">
          <SidebarHeader className="brand-header">
            <div className="brand-symbol">
              <Activity size={25} />
            </div>
            <div>
              <strong>澄观</strong>
              <span>HR INTELLIGENCE</span>
            </div>
          </SidebarHeader>
          <SidebarContent>
            <p className="nav-label">工作空间</p>
            <Navigation view={view} onView={setView} />
            <div className="sidebar-note">
              <ShieldCheck size={18} />
              <p>
                数据有边界
                <br />
                洞察有依据
              </p>
            </div>
          </SidebarContent>
          <SidebarFooter className="hr-sidebar-footer">
            <div>
              <i
                className={boot?.model.connected ? 'online-dot' : 'offline-dot'}
              />
              <span>
                {boot?.model.connected ? '本地模型已连接' : '检查本地模型连接'}
              </span>
            </div>
            <small>LM Studio · Qwen3.8 27B</small>
            <p>澄川科技 · 模拟企业</p>
          </SidebarFooter>
        </Sidebar>
        <SidebarInset className="hr-inset">
          <header className="topbar">
            <div className="breadcrumbs">
              <SidebarTrigger className="mobile-nav-trigger" />
              <span>工作空间</span>
              <ChevronRight size={14} />
              <strong>{NAV.find((v) => v.id === view)?.label}</strong>
            </div>
            <div className="topbar-actions">
              <span className="demo-badge">
                <i />
                模拟数据
              </span>
              {boot ? (
                <Select
                  value={boot.principal.id}
                  onValueChange={(value) => {
                    if (value) void initialize(value);
                  }}
                  disabled={switching}
                >
                  <SelectTrigger
                    className="persona-select"
                    aria-label="切换演示身份"
                  >
                    <span className="persona-avatar">
                      {boot.principal.label.slice(0, 1)}
                    </span>
                    <SelectValue>{boot.principal.label}</SelectValue>
                  </SelectTrigger>
                  <SelectContent align="end">
                    {boot.personas.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
            </div>
          </header>
          <main id="main-content" className="hr-main">
            {error ? (
              <Failure message={error} retry={() => initialize()} />
            ) : !boot || switching ? (
              <LoadingBlock />
            ) : (
              <div key={boot.principal.id}>
                {view === 'overview' ? (
                  <Overview boot={boot} onAsk={ask} />
                ) : null}
                {view === 'chat' ? (
                  <Chat
                    key={chatKey}
                    boot={boot}
                    initialQuestion={initial}
                    onSave={save}
                    onExport={download}
                    onDebug={openDebug}
                  />
                ) : null}
                {view === 'boards' ? (
                  <Boards boot={boot} onAsk={ask} onExport={download} />
                ) : null}
                {view === 'organization' ? <Organization boot={boot} /> : null}
                {view === 'catalog' ? (
                  <Catalog boot={boot} onAsk={ask} />
                ) : null}
                {view === 'governance' ? <Governance boot={boot} /> : null}
                {view === 'dictionary' ? <DataDictionary boot={boot} /> : null}
                {view === 'debug' ? (
                  <DebugPanel
                    key={`${boot.principal.id}:${debugRunId ?? 'latest'}`}
                    boot={boot}
                    initialRunId={debugRunId}
                  />
                ) : null}
              </div>
            )}
          </main>
          <footer className="workspace-footer">
            <span>
              <ShieldCheck size={13} />
              所有结果在当前身份授权范围内计算
            </span>
            <button onClick={() => setView('catalog')}>
              <CircleHelp size={14} />
              了解统计口径
              <ArrowUpRight size={13} />
            </button>
          </footer>
        </SidebarInset>
        {toast ? (
          <output className="toast-message">
            <Check size={18} />
            {toast}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setToast('');
                setView('boards');
              }}
            >
              查看
            </Button>
          </output>
        ) : null}
      </SidebarProvider>
    </TooltipProvider>
  );
}
