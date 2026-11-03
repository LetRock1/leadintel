import { cn, useChartColors } from "@xedu/shared/lib";
import { Segmented } from "@xedu/shared/ui";
import { useId, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

export interface Series<K extends string = string> {
  key: K;
  label: string;
  /** A dashed line (for an estimate next to what happened), so lines differ by more than their colour. */
  dashed?: boolean;
}

interface ChartProps<T extends object> {
  title: string;
  description?: ReactNode;
  data: readonly T[];
  /** The key of the x value of each row (a date or a category). */
  x: keyof T & string;
  series: Series<keyof T & string>[];
  kind?: "line" | "bar";
  height?: number;
  /** Formats values (axis, tooltip and table). */
  format: (v: number) => string;
  /** A shorter format for the y axis (defaults to format). */
  axisFormat?: (v: number) => string;
  xFormat?: (v: string) => string;
  className?: string;
  footer?: ReactNode;
  /** A marker on every point of a line (when each point is an event, such as a learning run). */
  dots?: boolean;
  /** Shown instead of an empty chart when every value is zero or missing (a new business has no data yet). */
  empty?: string;
}

function Legend({ series, colors, kind }: { series: Series[]; colors: readonly string[]; kind: "line" | "bar" }) {
  if (series.length < 2) return null;
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 px-4 pt-2 text-[12.5px] text-ink-2">
      {series.map((s, i) => (
        <li key={s.key} className="flex items-center gap-1.5">
          {kind === "line" && s.dashed ? (
            <svg aria-hidden width="16" height="4" viewBox="0 0 16 4">
              <line
                x1="0"
                y1="2"
                x2="16"
                y2="2"
                stroke={colors[i % colors.length]}
                strokeWidth="2"
                strokeDasharray="5 3"
              />
            </svg>
          ) : (
            <span
              aria-hidden
              className={kind === "line" ? "h-0.5 w-3.5 rounded-full" : "size-2.5 rounded-[2px]"}
              style={{ background: colors[i % colors.length] }}
            />
          )}
          {s.label}
        </li>
      ))}
    </ul>
  );
}

function TooltipBox({
  active,
  payload,
  label,
  format,
  xFormat,
}: Partial<TooltipContentProps<number, string>> & { format: (v: number) => string; xFormat?: (v: string) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-40 rounded-sm border border-line bg-raised px-3 py-2 text-[12.5px] shadow-overlay">
      <p className="mb-1 font-medium text-ink">{xFormat ? xFormat(String(label)) : String(label)}</p>
      {payload.map((p) => (
        <p key={String(p.dataKey)} className="flex items-center gap-2 text-ink-2">
          <span aria-hidden className="size-2 rounded-full" style={{ background: p.color }} />
          {p.name}
          <span className="num ml-auto pl-4 font-medium text-ink">
            {typeof p.value === "number" ? format(p.value) : "None"}
          </span>
        </p>
      ))}
    </div>
  );
}

function cell<T extends object>(row: T, key: keyof T & string): unknown {
  return (row as Record<string, unknown>)[key];
}

function DataTable<T extends object>({
  data,
  x,
  series,
  format,
  xFormat,
  title,
}: Pick<ChartProps<T>, "data" | "x" | "series" | "format" | "xFormat" | "title">) {
  return (
    <div className="max-h-72 overflow-auto">
      <table className="w-full border-collapse text-[13px]" aria-label={title}>
        <thead>
          <tr>
            <th
              scope="col"
              className="sticky top-0 border-b border-line bg-surface py-1.5 pr-3 text-left font-medium text-muted"
            >
              {x === "date" ? "Date" : ""}
            </th>
            {series.map((s) => (
              <th
                key={s.key}
                scope="col"
                className="sticky top-0 border-b border-line bg-surface py-1.5 pl-3 text-right font-medium text-muted"
              >
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((r, i) => (
            <tr key={i}>
              <th scope="row" className="border-b border-line py-1.5 pr-3 text-left font-normal text-ink-2">
                {xFormat ? xFormat(String(cell(r, x))) : String(cell(r, x))}
              </th>
              {series.map((s) => {
                const v = cell(r, s.key);
                return (
                  <td key={s.key} className="num border-b border-line py-1.5 pl-3 text-right text-ink">
                    {typeof v === "number" ? format(v) : "None"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * A line or bar chart on one y axis, with a hover tooltip, a legend for two or more series, and a table view of the
 * same numbers (for screen readers, print, and anyone who prefers the figures).
 */
export function TrendChart<T extends object>({
  title,
  description,
  data,
  x,
  series,
  kind = "line",
  height = 220,
  format,
  axisFormat,
  xFormat,
  className,
  footer,
  dots = false,
  empty,
}: ChartProps<T>) {
  const c = useChartColors();
  const [view, setView] = useState<"chart" | "table">("chart");
  const titleId = useId();
  const tick = { fill: c.text, fontSize: 12 };
  const axis = axisFormat ?? format;
  // whole-number ticks only for counts: shares (0 to 1) and money need decimals between the integers
  const counts = data.every((r) =>
    series.every((s) => {
      const v = cell(r, s.key);
      return typeof v !== "number" || Number.isInteger(v);
    }),
  );
  const nothing =
    Boolean(empty) &&
    data.every((r) =>
      series.every((s) => {
        const v = cell(r, s.key);
        return v === null || v === undefined || v === 0;
      }),
    );
  const common = (
    <>
      <CartesianGrid vertical={false} stroke={c.grid} />
      <XAxis
        dataKey={x as string}
        tick={tick}
        tickLine={false}
        axisLine={{ stroke: c.axis }}
        tickFormatter={xFormat ? (v: string) => xFormat(String(v)) : undefined}
        minTickGap={18}
        interval="preserveStartEnd"
      />
      <YAxis
        tick={tick}
        tickLine={false}
        axisLine={false}
        width={56}
        tickFormatter={(v: number) => axis(v)}
        allowDecimals={!counts}
      />
      <Tooltip
        cursor={kind === "line" ? { stroke: c.axis, strokeWidth: 1 } : { fill: c.grid, opacity: 0.6 }}
        content={(p) => (
          <TooltipBox {...(p as Partial<TooltipContentProps<number, string>>)} format={format} xFormat={xFormat} />
        )}
      />
    </>
  );
  return (
    <figure aria-labelledby={titleId} className={cn("rounded-md border border-line bg-surface", className)}>
      <figcaption className="flex flex-wrap items-start gap-3 px-4 pt-3">
        <div className="min-w-0 flex-1">
          <p id={titleId} className="text-[14px] font-semibold text-ink">
            {title}
          </p>
          {description && <p className="mt-0.5 text-[12.5px] text-muted">{description}</p>}
        </div>
        <Segmented
          size="sm"
          label={`${title}: show as`}
          value={view}
          onChange={setView}
          options={[
            { value: "chart", label: "Chart" },
            { value: "table", label: "Table" },
          ]}
        />
      </figcaption>
      {view === "chart" && nothing ? (
        <p className="px-4 pb-4 pt-3 text-[13.5px] text-muted" style={{ minHeight: height / 2 }}>
          {empty}
        </p>
      ) : view === "chart" ? (
        <>
          <Legend series={series} colors={c.series} kind={kind} />
          <div className="px-2 pb-3 pt-2" style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
              {kind === "line" ? (
                <LineChart data={data as T[]} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                  {common}
                  {series.map((s, i) => (
                    <Line
                      key={s.key}
                      type="monotone"
                      dataKey={s.key as string}
                      name={s.label}
                      stroke={c.series[i % c.series.length]}
                      strokeWidth={2}
                      strokeDasharray={s.dashed ? "5 4" : undefined}
                      dot={
                        dots
                          ? {
                              r: 4,
                              fill: c.series[i % c.series.length],
                              stroke: c.surface,
                              strokeWidth: 2,
                              strokeDasharray: "none",
                            }
                          : false
                      }
                      activeDot={{ r: 5, stroke: c.surface, strokeWidth: 2, strokeDasharray: "none" }}
                      isAnimationActive={false}
                      connectNulls
                    />
                  ))}
                </LineChart>
              ) : (
                <BarChart
                  data={data as T[]}
                  margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
                  barGap={2}
                  barCategoryGap="24%"
                >
                  {common}
                  {series.map((s, i) => (
                    <Bar
                      key={s.key}
                      dataKey={s.key as string}
                      name={s.label}
                      fill={c.series[i % c.series.length]}
                      maxBarSize={24}
                      radius={[4, 4, 0, 0]}
                      isAnimationActive={false}
                    />
                  ))}
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <div className="px-4 pb-3 pt-2">
          <DataTable data={data} x={x} series={series} format={format} xFormat={xFormat} title={title} />
        </div>
      )}
      {footer && <div className="border-t border-line px-4 py-2.5 text-[12.5px] text-muted">{footer}</div>}
    </figure>
  );
}

export interface IntervalRow {
  label: ReactNode;
  value: number | null;
  low?: number | null;
  high?: number | null;
  note?: ReactNode;
  emphasis?: boolean;
}

/** Two ends of an interval, naming a shared unit once: "+10.3 points", "+24.8 points" -> "+10.3 to +24.8 points". */
function range(low: string, high: string): string {
  const unit = / [a-z]+$/i.exec(low)?.[0];
  return unit && high.endsWith(unit) ? `${low.slice(0, -unit.length)} to ${high}` : `${low} to ${high}`;
}

/**
 * Estimates with their 95% interval on one shared scale (a dot and a whisker per row), for policy values and A/B
 * test lifts. A zero line is drawn when the scale crosses zero.
 */
export function IntervalPlot({
  rows,
  format,
  label,
  className,
}: {
  rows: IntervalRow[];
  format: (v: number) => string;
  label: string;
  className?: string;
}) {
  const c = useChartColors();
  const values = rows.flatMap((r) => [r.value, r.low, r.high]).filter((v): v is number => typeof v === "number");
  if (!values.length) return null;
  let lo = Math.min(0, ...values);
  let hi = Math.max(0, ...values);
  const pad = (hi - lo || 1) * 0.06;
  lo -= pad;
  hi += pad;
  const at = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  const zero = lo < 0 && hi > 0;
  return (
    <div role="table" aria-label={label} className={cn("text-[13.5px]", className)}>
      {rows.map((r, i) => (
        <div
          key={i}
          role="row"
          className="grid grid-cols-[minmax(0,13rem)_minmax(0,1fr)_8.5rem] items-center gap-x-4 border-b border-line py-2.5 last:border-b-0"
        >
          <div role="cell" className="min-w-0">
            <p className={cn("truncate", r.emphasis ? "font-medium text-ink" : "text-ink-2")}>{r.label}</p>
            {r.note && <p className="truncate text-[12px] text-muted">{r.note}</p>}
          </div>
          <div role="cell" aria-hidden className="relative h-5">
            <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2" style={{ background: c.grid }} />
            {zero && <span className="absolute inset-y-0 w-px" style={{ left: at(0), background: c.axis }} />}
            {typeof r.low === "number" && typeof r.high === "number" && (
              <span
                className="absolute top-1/2 h-0.5 -translate-y-1/2 rounded-full"
                style={{ left: at(r.low), width: `calc(${at(r.high)} - ${at(r.low)})`, background: c.series[0] }}
              />
            )}
            {typeof r.value === "number" && (
              <span
                className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
                style={{ left: at(r.value), background: c.series[0], boxShadow: `0 0 0 2px ${c.surface}` }}
              />
            )}
          </div>
          <div role="cell" className="text-right">
            <p className="num font-medium text-ink">
              {typeof r.value === "number" ? format(r.value) : "Not enough data"}
            </p>
            {typeof r.low === "number" && typeof r.high === "number" && (
              <p className="num text-[12px] text-muted">{range(format(r.low), format(r.high))}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
