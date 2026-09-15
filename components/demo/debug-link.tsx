import { ExternalLink, Workflow } from 'lucide-react';

export function RunDebugLink({
  runId,
  navigation = false,
}: {
  runId?: string;
  navigation?: boolean;
}) {
  return (
    <a
      className={navigation ? 'd-debug-nav' : 'd-run-debug-link'}
      href={
        runId ? `/demo/debug?run=${encodeURIComponent(runId)}` : '/demo/debug'
      }
      target="_blank"
      rel="noopener noreferrer"
      title="在独立页面打开节点调试"
    >
      <Workflow size={navigation ? 18 : 16} aria-hidden="true" />
      {navigation ? '节点调试' : '查看节点调试'}
      {!navigation && <ExternalLink size={13} aria-hidden="true" />}
      <span className="d-sr-only">（新标签页）</span>
    </a>
  );
}
