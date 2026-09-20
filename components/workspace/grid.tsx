'use client';
/**
 * 表格：QueryGrid 把筛选/排序/页码转换成 Plan，向后端重新查询。
 * 使用 AG Grid Community 的 infinite 行模型，不使用 Enterprise 的 serverSide 模型；
 * “服务端筛选”指本组件主动请求 /query，并非在浏览器已下载的数据上裁剪权限。
 */
import { useMemo, useRef, useEffect } from 'react';
import { AgGridReact } from 'ag-grid-react';
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type IDatasource,
  type IGetRowsParams,
} from 'ag-grid-community';
import {
  request,
  type Plan,
  type Result,
  type Filter,
  type Row,
  type Column,
} from './types';
ModuleRegistry.registerModules([AllCommunityModule]);
const theme = themeQuartz.withParams({
  accentColor: '#a32b36',
  fontFamily: 'PingFang SC, Microsoft YaHei, system-ui, sans-serif',
  fontSize: 13,
  headerFontSize: 12,
  backgroundColor: '#ffffff',
  foregroundColor: '#29313a',
  headerBackgroundColor: '#f5f6f8',
  borderColor: '#e1e4e8',
  rowHeight: 40,
  headerHeight: 42,
  wrapperBorderRadius: 4,
});
const localeText = {
  page: '页',
  more: '更多',
  to: '至',
  of: '共',
  nextPage: '下一页',
  lastPage: '末页',
  firstPage: '首页',
  previousPage: '上一页',
  pageSizeSelectorLabel: '每页',
  loadingOoo: '正在读取授权数据…',
  noRowsToShow: '没有符合条件的记录',
  filterOoo: '输入筛选值…',
  equals: '等于',
  contains: '包含',
  greaterThanOrEqual: '大于或等于',
  lessThanOrEqual: '小于或等于',
  andCondition: '并且',
  orCondition: '或者',
  applyFilter: '应用',
  resetFilter: '重置',
  clearFilter: '清空',
  ariaColumnFilter: '列筛选',
  ariaColumnSelectAll: '选择所有列',
};

type GridFilter = {
  type?: string;
  filter?: string | number;
  conditions?: GridFilter[];
  operator?: string;
};
function gridPlan(base: Plan, params: IGetRowsParams): Plan {
  // 保留条件编辑器的基础筛选，再叠加列头筛选；更窄的条件不会扩大后端授权范围。
  const filters: Filter[] = [...base.filters];
  for (const [field, f] of Object.entries(
    params.filterModel as Record<string, GridFilter>,
  )) {
    // 只翻译后端明确支持的操作，遇到未知组合就报错，不能悄悄丢掉用户条件。
    if (f.operator && f.operator !== 'AND')
      throw new Error('列头暂仅支持“并且”，多值“或者”请在条件区使用“属于”。');
    for (const item of f.conditions || [f]) {
      const op = (
        {
          equals: 'eq',
          contains: 'contains',
          greaterThanOrEqual: 'gte',
          lessThanOrEqual: 'lte',
        } as const
      )[item.type as 'equals'];
      if (!op || item.filter === undefined)
        throw new Error('该列筛选尚未支持，请在条件区设置。');
      filters.push({ field, op, values: [String(item.filter)] });
    }
  }
  return {
    ...base,
    filters,
    order_by: params.sortModel.length
      ? params.sortModel.map((s) => ({ field: s.colId, direction: s.sort }))
      : base.order_by.filter((o) => !base.columns.includes(o.field)),
    // 表格块大小与接口 page_size 统一为 50；后端返回完整匹配总数用于页数计算。
    page: Math.floor(params.startRow / 50) + 1,
    page_size: 50,
  };
}

export function QueryGrid({
  plan,
  columns,
  csrf,
  onResult,
  onError,
  onDrill,
}: {
  plan: Plan;
  columns: Column[];
  csrf: string;
  onResult: (result: Result) => void;
  onError: (message: string) => void;
  onDrill?: (row: Row, metric: string) => void;
}) {
  // 用 ref 保持最新回调，避免仅因父组件回调引用变化就销毁数据源和重新拉取页面。
  const handlers = useRef({ onResult, onError, onDrill });
  useEffect(() => {
    handlers.current = { onResult, onError, onDrill };
  }, [onResult, onError, onDrill]);
  // 切换条件、身份或卸载表格时取消旧请求，防止旧结果落进新状态。
  const controllers = useRef(new Set<AbortController>());
  useEffect(
    () => () => {
      controllers.current.forEach((c) => c.abort());
    },
    [],
  );
  const datasource = useMemo<IDatasource>(
    () => ({
      getRows(params) {
        const controller = new AbortController();
        controllers.current.add(controller);
        let effective: Plan;
        try {
          effective = gridPlan(plan, params);
        } catch (error) {
          handlers.current.onError((error as Error).message);
          params.failCallback();
          return;
        }
        // 每次都由后端按当前会话重新鉴权并计算 totals；缓存块只用于前端浏览体验。
        request<Result>('/query', csrf, effective, controller.signal)
          .then((result) => {
            if (controller.signal.aborted) return;
            params.successCallback(result.rows, result.total_rows);
            handlers.current.onResult(result);
          })
          .catch((error) => {
            if (!controller.signal.aborted) {
              params.failCallback();
              handlers.current.onError(error.message);
            }
          })
          .finally(() => controllers.current.delete(controller));
      },
      destroy() {
        controllers.current.forEach((c) => c.abort());
        controllers.current.clear();
      },
    }),
    [plan, csrf],
  );
  const canDrill = !!onDrill;
  // 指标列与辅助分子/分母列只按允许的方式交互，避免把聚合值当成员工字段筛选。
  const defs = useMemo<ColDef<Row>[]>(
    () =>
      columns.map((c) => {
        const metric = plan.metrics.includes(c.key);
        const numeric =
          c.key === 'age' ||
          metric ||
          c.key.endsWith('_numerator') ||
          c.key.endsWith('_denominator') ||
          c.key.endsWith('_sample_size');
        const filterable =
          plan.kind === 'people' ||
          (plan.group_by.includes(c.key) &&
            !c.key.endsWith('_month') &&
            c.key !== 'relation');
        return {
          field: c.key,
          headerName: c.label,
          minWidth: numeric ? 140 : 150,
          flex: 1,
          resizable: true,
          sortable:
            plan.kind === 'people' || metric || plan.group_by.includes(c.key),
          filter: filterable
            ? numeric
              ? 'agNumberColumnFilter'
              : 'agTextColumnFilter'
            : false,
          floatingFilter: filterable,
          filterParams: {
            filterOptions: numeric
              ? ['equals', 'greaterThanOrEqual', 'lessThanOrEqual']
              : ['contains', 'equals'],
            maxNumConditions: 1,
            debounceMs: 450,
          },
          type: numeric ? 'numericColumn' : undefined,
          cellDataType: false,
          valueFormatter: (p) =>
            p.value === null || p.value === undefined ? '—' : String(p.value),
          cellClass: metric && canDrill ? 'd-drill-cell' : undefined,
          onCellDoubleClicked: (e) => {
            if (metric && e.data) handlers.current.onDrill?.(e.data, c.key);
          },
        };
      }),
    [columns, plan.kind, plan.group_by, plan.metrics, canDrill],
  );
  return (
    <div className="d-grid" aria-label="授权查询结果表">
      <AgGridReact<Row>
        theme={theme}
        rowModelType="infinite"
        datasource={datasource}
        columnDefs={defs}
        cacheBlockSize={50}
        maxBlocksInCache={3}
        maxConcurrentDatasourceRequests={1}
        pagination
        paginationPageSize={50}
        paginationPageSizeSelector={false}
        suppressMultiSort
        enableCellTextSelection
        ensureDomOrder
        localeText={localeText}
        initialState={{
          sort: {
            sortModel: plan.order_by.map((o) => ({
              colId: o.field,
              sort: o.direction,
            })),
          },
        }}
      />
    </div>
  );
}

export function StaticGrid({
  columns,
  rows,
}: {
  columns: Column[];
  rows: Row[];
}) {
  // 静态关系解释表只展示后端已经授权返回的 rows；这里的筛选/分页在浏览器完成。
  const defs = useMemo<ColDef<Row>[]>(
    () =>
      columns.map((c) => ({
        field: c.key,
        headerName: c.label,
        flex: 1,
        minWidth: c.key === 'reason' ? 430 : 130,
        wrapText: c.key === 'reason',
        autoHeight: c.key === 'reason',
        tooltipField: c.key,
        sortable: true,
        resizable: true,
        filter: 'agTextColumnFilter',
        floatingFilter: true,
        valueFormatter: (p) => (p.value == null ? '—' : String(p.value)),
      })),
    [columns],
  );
  return (
    <div className="d-grid">
      <AgGridReact<Row>
        theme={theme}
        rowData={rows}
        columnDefs={defs}
        pagination
        paginationPageSize={50}
        paginationPageSizeSelector={false}
        localeText={localeText}
        enableCellTextSelection
      />
    </div>
  );
}
