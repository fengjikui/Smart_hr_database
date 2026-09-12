'use client';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { Answer } from './types';

export function TrendChart({
  answer,
  compact = false,
}: {
  answer: Answer;
  compact?: boolean;
}) {
  return (
    <figure
      className={compact ? 'trend-chart compact' : 'trend-chart'}
      aria-label={`${answer.metric.name}趋势：${answer.rows.map((r) => `${r.label} ${r.value ?? '无数据'}`).join('，')}`}
    >
      <ResponsiveContainer
        width="100%"
        height="100%"
        minWidth={0}
        minHeight={0}
        initialDimension={{ width: 600, height: compact ? 180 : 230 }}
      >
        <LineChart
          data={answer.rows}
          margin={{ top: 12, right: 18, bottom: 4, left: -14 }}
        >
          <CartesianGrid
            vertical={false}
            stroke="var(--border)"
            strokeDasharray="3 5"
          />
          <XAxis
            dataKey="label"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 12, fill: 'var(--muted-foreground)' }}
            tickMargin={13}
            minTickGap={22}
            tickFormatter={(v: string) =>
              answer.plan.dimension === 'day' ? v.slice(5) : `${v.slice(5)}月`
            }
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 12, fill: 'var(--muted-foreground)' }}
            tickMargin={8}
            width={52}
            domain={[0, 'auto']}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--card)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              fontSize: 14,
            }}
            formatter={(v) => [v ?? '—', answer.metric.name]}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="var(--chart-1)"
            strokeWidth={2.5}
            dot={{ r: 3.5, fill: 'var(--card)', strokeWidth: 2 }}
            activeDot={{ r: 5 }}
            isAnimationActive={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </figure>
  );
}
