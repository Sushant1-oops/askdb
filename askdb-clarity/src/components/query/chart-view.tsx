import type { ReactElement } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell as SliceCell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartSpec, Row } from "@/lib/api";
import { formatCompact } from "@/lib/format";

const COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];
const MAX_POINTS = 50;

const axisProps = { tick: { fontSize: 11, fill: "var(--muted-foreground)" }, tickLine: false, axisLine: { stroke: "var(--border)" } } as const;
const tooltipProps = {
  contentStyle: { background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 },
  cursor: { fill: "var(--muted)", opacity: 0.5 },
} as const;

export function ChartView({ spec, rows }: { spec: ChartSpec; rows: Row[] }) {
  const data = rows.slice(0, MAX_POINTS).map((r) => {
    const point: Record<string, string | number | null> = {};
    for (const [key, value] of Object.entries(r)) {
      point[key] = typeof value === "number" || typeof value === "string" || value === null ? value : String(value);
    }
    return point;
  });
  const first = spec.yKeys[0];
  if (!first || data.length === 0) return null;

  const common = { data, margin: { top: 8, right: 12, bottom: 4, left: 0 } };
  const grid = <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />;
  const xAxis = <XAxis dataKey={spec.xKey} {...axisProps} interval="preserveStartEnd" />;
  const yAxis = <YAxis {...axisProps} width={48} tickFormatter={(v: number) => formatCompact(v)} />;
  const legend = spec.yKeys.length > 1 ? <Legend wrapperStyle={{ fontSize: 12 }} /> : null;

  let chart: ReactElement;
  switch (spec.type) {
    case "line":
      chart = (
        <LineChart {...common}>
          {grid}{xAxis}{yAxis}<Tooltip {...tooltipProps} />{legend}
          {spec.yKeys.map((k, i) => (
            <Line key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={data.length < 25} />
          ))}
        </LineChart>
      );
      break;
    case "area":
      chart = (
        <AreaChart {...common}>
          {grid}{xAxis}{yAxis}<Tooltip {...tooltipProps} />{legend}
          {spec.yKeys.map((k, i) => (
            <Area key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]} fill={COLORS[i % COLORS.length]} fillOpacity={0.15} strokeWidth={2} />
          ))}
        </AreaChart>
      );
      break;
    case "pie":
      chart = (
        <PieChart>
          <Tooltip {...tooltipProps} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Pie data={data} dataKey={first} nameKey={spec.xKey} innerRadius="45%" outerRadius="80%" paddingAngle={2} stroke="var(--card)">
            {data.map((_, i) => (
              <SliceCell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
        </PieChart>
      );
      break;
    case "scatter":
      chart = (
        <ScatterChart {...common}>
          {grid}
          <XAxis dataKey={spec.xKey} type="number" name={spec.xKey} {...axisProps} />
          <YAxis dataKey={first} type="number" name={first} {...axisProps} width={48} />
          <Tooltip {...tooltipProps} cursor={{ strokeDasharray: "3 3" }} />
          <Scatter data={data} fill={COLORS[0]} />
        </ScatterChart>
      );
      break;
    default:
      chart = (
        <BarChart {...common}>
          {grid}{xAxis}{yAxis}<Tooltip {...tooltipProps} />{legend}
          {spec.yKeys.map((k, i) => (
            <Bar key={k} dataKey={k} fill={COLORS[i % COLORS.length]} radius={[3, 3, 0, 0]} maxBarSize={48} />
          ))}
        </BarChart>
      );
  }

  return (
    <figure className="rounded-md border border-border bg-card p-3">
      {spec.title && <figcaption className="mb-2 px-1 font-display text-[13px] font-bold">{spec.title}</figcaption>}
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {chart}
        </ResponsiveContainer>
      </div>
      {rows.length > MAX_POINTS && <p className="mt-1 px-1 text-[11px] text-muted-foreground">Showing the first {MAX_POINTS} rows.</p>}
    </figure>
  );
}
