import { useState, type ReactNode } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis,
  Radar, RadarChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { AXES_FA, AXES_ORDER, DECISION_FA, mid, num, usd } from "../lib/fmt";
import type { Axes, OpportunityPoint, Results } from "../lib/types";

// Validated categorical slots (dataviz reference palette, light surface) + neutral inks.
export const C = {
  lead: "#eb6834", // slot 2 orange — leads, matches the brand thread
  watch: "#2a78d6", // slot 1 blue
  third: "#1baf7a", // slot 3 aqua (compare mode only, always labeled)
  rejected: "#898781",
  triage: "#c3c2b7",
  grid: "#e1e0d9",
  axis: "#898781",
  ink: "#0b0b0b",
  ink2: "#52514e",
};
const COMPARE = [C.watch, C.lead, C.third];

function TipBox({ children }: { children: ReactNode }) {
  return <div dir="rtl" className="rounded-lg border border-ink-100 bg-white px-3 py-2 text-xs leading-6 text-ink-800 shadow-lg">{children}</div>;
}

/** Toggle between a chart and its accessible table view. */
export function ChartFrame({ title, sub, table, children }: { title: string; sub?: string; table: ReactNode; children: ReactNode }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <figure className="m-0">
      <figcaption className="mb-2 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="font-extrabold text-ink-900">{title}</div>
          {sub && <div className="text-xs text-ink-500">{sub}</div>}
        </div>
        <button className="rounded-lg px-2 py-1 text-xs font-bold text-ink-500 hover:bg-ink-50" onClick={() => setAsTable(!asTable)}>
          {asTable ? "نمایش نمودار" : "نمایش جدول"}
        </button>
      </figcaption>
      {asTable ? <div className="overflow-x-auto">{table}</div> : children}
    </figure>
  );
}

const th = "border-b border-ink-100 px-2 py-1.5 text-start font-bold text-ink-600";
const td = "border-b border-ink-50 px-2 py-1.5 tabular-nums";

// --- Radar ------------------------------------------------------------------------------------

type RadarSeries = { name: string; scores: Axes };

export function LeadRadar({ series, ideal, height = 220, compact }: {
  series: RadarSeries[]; ideal?: Axes | null; height?: number; compact?: boolean;
}) {
  const rows = AXES_ORDER.map((k) => {
    const row: Record<string, string | number> = { axis: AXES_FA[k] };
    series.forEach((s, i) => (row[`s${i}`] = s.scores[k]));
    if (ideal) row.ideal = ideal[k];
    return row;
  });
  const single = series.length === 1;
  return (
    <div dir="ltr" style={{ height }} role="img"
      aria-label={series.map((s) => `${s.name}: ` + AXES_ORDER.map((k) => `${AXES_FA[k]} ${s.scores[k]}`).join("، ")).join(" | ")}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={rows} outerRadius={compact ? "66%" : "72%"} margin={{ top: 8, right: 24, bottom: 8, left: 24 }}>
          <PolarGrid stroke={C.grid} />
          <PolarAngleAxis dataKey="axis" tick={{ fontSize: compact ? 10 : 12, fill: C.ink2 }} />
          <PolarRadiusAxis domain={[0, 10]} tickCount={6} tick={false} axisLine={false} />
          {ideal && (
            <Radar name="مشتری ایده‌آل" dataKey="ideal" stroke={C.ink2} strokeDasharray="5 4" strokeWidth={1.5}
              fill="none" isAnimationActive={false} />
          )}
          {series.map((s, i) => {
            const color = single ? C.lead : COMPARE[i];
            return (
              <Radar key={s.name} name={s.name} dataKey={`s${i}`} stroke={color} strokeWidth={2} fill={color}
                fillOpacity={single ? 0.2 : 0.08} dot={{ r: 3, fill: color, strokeWidth: 0 }} isAnimationActive={false} />
            );
          })}
          <Tooltip content={({ active, payload, label }: any) =>
            active && payload?.length ? (
              <TipBox>
                <div className="font-bold">{label}</div>
                {payload.map((p: any) => <div key={p.name}>{p.name}: {num(p.value)} از ۱۰</div>)}
              </TipBox>
            ) : null} />
          {(!single || !compact) && (
            <Legend verticalAlign="bottom" height={24} iconType="plainline"
              formatter={(v: string) => <span className="text-xs text-ink-600">{v}</span>} />
          )}
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// --- Funnel -----------------------------------------------------------------------------------

export function FunnelChart({ funnel }: { funnel: Results["funnel"] }) {
  const data = funnel.map((f) => ({ ...f, name: f.label }));
  const height = 52 * data.length + 10;
  const table = (
    <table className="w-full text-sm">
      <thead><tr><th className={th}>مرحله</th><th className={th}>تعداد</th><th className={th}>هزینه این مرحله</th></tr></thead>
      <tbody>{data.map((d) => <tr key={d.stage}><td className={td}>{d.label}</td><td className={td}>{num(d.count)}</td><td className={td}>{usd(d.cost)}</td></tr>)}</tbody>
    </table>
  );
  return (
    <ChartFrame title="قیف عامل" sub="هر مرحله پیام‌های کمتری را با هزینه بیشتری بررسی می‌کند" table={table}>
      <div dir="ltr" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 4, bottom: 4, left: 56 }} barCategoryGap={10}>
            <XAxis type="number" hide reversed domain={[0, "dataMax"]} />
            <YAxis type="category" dataKey="name" orientation="right" width={150} axisLine={false} tickLine={false}
              tick={({ x, y, payload, index }: any) => (
                <g transform={`translate(${x},${y})`}>
                  <text x={8} y={-3} textAnchor="start" fontSize={13} fontWeight={700} fill={C.ink}>{payload.value}</text>
                  <text x={8} y={14} textAnchor="start" fontSize={11} fill={C.ink2}>
                    {data[index].cost ? usd(data[index].cost) : "بدون هزینه"}
                  </text>
                </g>
              )} />
            <Bar dataKey="count" radius={4} barSize={22} isAnimationActive={false}
              label={({ x, y, height: h, value }: any) => (
                <text x={x - 6} y={y + h / 2 + 4} textAnchor="end" fontSize={12} fontWeight={700} fill={C.ink}>{num(value)}</text>
              )}>
              {data.map((d) => <Cell key={d.stage} fill={d.stage === "leads" ? C.lead : "#7a72ab"} />)}
            </Bar>
            <Tooltip cursor={{ fill: "rgba(31,27,58,0.04)" }} content={({ active, payload }: any) =>
              active && payload?.length ? (
                <TipBox>
                  <div className="font-bold">{payload[0].payload.label}</div>
                  <div>{num(payload[0].payload.count)} پیام</div>
                  <div>هزینه: {usd(payload[0].payload.cost)}</div>
                </TipBox>
              ) : null} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

// --- Opportunity map --------------------------------------------------------------------------

const XShape = (props: any) => {
  const { cx, cy, size = 64 } = props;
  const r = Math.max(4, Math.sqrt(size) / 2);
  return <path d={`M${cx - r},${cy - r}L${cx + r},${cy + r}M${cx + r},${cy - r}L${cx - r},${cy + r}`} stroke={C.rejected} strokeWidth={2} strokeLinecap="round" />;
};
const Diamond = (props: any) => {
  const { cx, cy, size = 64 } = props;
  const r = Math.max(5, Math.sqrt(size) / 1.6);
  return <path d={`M${cx},${cy - r}L${cx + r},${cy}L${cx},${cy + r}L${cx - r},${cy}Z`} fill={C.watch} stroke="#fff" strokeWidth={2} />;
};
const Dot = (color: string, hollow = false) => (props: any) => {
  const { cx, cy, size = 64 } = props;
  const r = Math.max(3, Math.sqrt(size) / 2);
  return <circle cx={cx} cy={cy} r={r} fill={hollow ? "#fff" : color} stroke={hollow ? color : "#fff"} strokeWidth={hollow ? 1.5 : 2} />;
};

export function OpportunityMap({ points, onPick }: { points: OpportunityPoint[]; onPick?: (msgId: number) => void }) {
  const safe = points.map((p) => ({ ...p, cost: Math.max(p.cost, 0.000001) }));
  // log axis with clean power-of-ten ticks ($0.00001 … $0.1)
  const costs = safe.map((p) => p.cost);
  const lo = Math.floor(Math.log10(Math.min(...costs, 0.001)));
  const hi = Math.ceil(Math.log10(Math.max(...costs, 0.01)));
  const xTicks = Array.from({ length: hi - lo + 1 }, (_, i) => 10 ** (lo + i));
  const xDomain: [number, number] = [10 ** lo, 10 ** hi];
  const groups = [
    { key: "lead", name: "سرنخ واقعی", data: safe.filter((p) => p.decision === "lead"), shape: Dot(C.lead) },
    { key: "watch", name: "زیر نظر", data: safe.filter((p) => p.decision === "watch"), shape: Diamond },
    { key: "rejected", name: "بررسی و رد شد", data: safe.filter((p) => p.kind === "investigated" && !["lead", "watch"].includes(p.decision)), shape: XShape },
    { key: "triage", name: "فقط تریاژ", data: safe.filter((p) => p.kind === "triage"), shape: Dot(C.triage, true) },
  ].filter((g) => g.data.length);
  const table = (
    <table className="w-full text-sm">
      <thead><tr><th className={th}>پیام</th><th className={th}>فرد</th><th className={th}>نتیجه</th><th className={th}>هزینه</th><th className={th}>کیفیت</th></tr></thead>
      <tbody>{safe.filter((p) => p.kind === "investigated").map((p) => (
        <tr key={p.msg_id}><td className={td}>#{mid(p.msg_id)}</td><td className={td}>{p.author}</td><td className={td}>{DECISION_FA[p.decision] ?? p.decision}</td><td className={td}>{usd(p.cost)}</td><td className={td}>{num(p.quality, 1)}</td></tr>
      ))}</tbody>
    </table>
  );
  return (
    <ChartFrame title="نقشه فرصت‌ها" sub="محور افقی: هزینه صرف‌شده برای هر پیام (لگاریتمی) · محور عمودی: کیفیت فرصت · اندازه: گرمای خرید" table={table}>
      <div dir="ltr" style={{ height: 320 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 12, bottom: 24, left: 4 }}>
            <CartesianGrid stroke={C.grid} strokeDasharray="0" />
            <XAxis type="number" dataKey="cost" scale="log" domain={xDomain} ticks={xTicks} tickLine={false}
              tick={{ fontSize: 10, fill: C.axis }} stroke={C.grid} allowDataOverflow
              tickFormatter={(v: number) => `$${num(v, 6)}`}
              label={{ value: "هزینه صرف‌شده ←", position: "insideBottom", offset: -16, fontSize: 11, fill: C.ink2 }} />
            <YAxis type="number" dataKey="quality" domain={[0, 10]} ticks={[0, 2, 4, 6, 8, 10]} width={28}
              tick={{ fontSize: 11, fill: C.axis }} stroke={C.grid} tickLine={false}
              tickFormatter={(v: number) => num(v)} />
            <ZAxis type="number" dataKey="temperature" range={[50, 320]} domain={[1, 3]} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ active, payload }: any) => {
              if (!active || !payload?.length) return null;
              const p: OpportunityPoint = payload[0].payload;
              return (
                <TipBox>
                  <div className="font-bold">{p.author} · #{mid(p.msg_id)}</div>
                  <div>{DECISION_FA[p.decision] ?? p.decision}</div>
                  <div>هزینه: {usd(p.cost)} · کیفیت: {num(p.quality, 1)}</div>
                  {p.decision === "lead" && onPick && <div className="text-ink-400">برای جزئیات کلیک کنید</div>}
                </TipBox>
              );
            }} />
            <Legend verticalAlign="top" height={28} formatter={(v: string) => <span className="text-xs text-ink-700">{v}</span>} />
            {groups.map((g) => (
              <Scatter key={g.key} name={g.name} data={g.data} shape={g.shape} isAnimationActive={false}
                legendType={g.key === "lead" ? "circle" : g.key === "watch" ? "diamond" : g.key === "rejected" ? "cross" : "circle"}
                fill={g.key === "lead" ? C.lead : g.key === "watch" ? C.watch : g.key === "rejected" ? C.rejected : C.triage}
                onClick={(d: any) => onPick && d?.payload?.decision === "lead" && onPick(d.payload.msg_id)}
                style={{ cursor: g.key === "lead" && onPick ? "pointer" : "default" }} />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

// --- Budget burn ------------------------------------------------------------------------------

export function BurnLine({ burn, budget }: { burn: Results["burn"]; budget: number }) {
  const data = [{ n: 0, equiv_cost: 0, leads: 0, cost: 0 }, ...burn];
  const table = (
    <table className="w-full text-sm">
      <thead><tr><th className={th}>بررسی شماره</th><th className={th}>هزینه تجمعی</th><th className={th}>سرنخ‌ها</th></tr></thead>
      <tbody>{burn.map((b) => <tr key={b.n}><td className={td}>{num(b.n)}</td><td className={td}>{usd(b.equiv_cost)}</td><td className={td}>{num(b.leads)}</td></tr>)}</tbody>
    </table>
  );
  return (
    <ChartFrame title="خرج بودجه در برابر سرنخ‌ها" sub={`هزینه تجمعی بررسی‌های عمیق (بودجه: ${usd(budget)})`} table={table}>
      <div dir="ltr" style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 20, left: 0 }}>
            <CartesianGrid stroke={C.grid} vertical={false} />
            <XAxis type="number" dataKey="equiv_cost" domain={[0, "dataMax"]} tick={{ fontSize: 11, fill: C.axis }} stroke={C.grid}
              tickFormatter={(v: number) => `$${num(v, 2)}`}
              label={{ value: "هزینه تجمعی", position: "insideBottom", offset: -12, fontSize: 11, fill: C.ink2 }} />
            <YAxis allowDecimals={false} width={28} tick={{ fontSize: 11, fill: C.axis }} stroke={C.grid} tickFormatter={(v: number) => num(v)} />
            <Tooltip content={({ active, payload }: any) => active && payload?.length ? (
              <TipBox>
                <div>هزینه تا اینجا: {usd(payload[0].payload.equiv_cost)}</div>
                <div>سرنخ‌ها: {num(payload[0].payload.leads)}</div>
              </TipBox>) : null} />
            <Line type="stepAfter" dataKey="leads" name="سرنخ‌ها" stroke={C.lead} strokeWidth={2} dot={{ r: 3, fill: C.lead }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}
