import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChatDrawer } from "../components/ChatView";
import { LeadCard } from "../components/LeadCard";
import { LiveFeed } from "../components/LiveFeed";
import { Layout } from "../components/Layout";
import { Button, ErrorBox, Loading } from "../components/ui";
import { api, errorText } from "../lib/api";
import { DECISION_FA, STATUS_FA, num, usd } from "../lib/fmt";
import type { AgentEvent, Results, RunSummary } from "../lib/types";

const shortName = (name?: string) => (name ?? "").split("—")[0].trim();
const COST_STEP: Record<string, string> = {
  prefiltered: "فیلتر اولیه", triaged: "بررسی سریع", investigated: "بررسی دقیق", leads: "نوشتن پاسخ",
};

function liveCounters(events: AgentEvent[]) {
  let leads = 0, spent = 0;
  for (const e of events) {
    spent += e.cost_usd || 0;
    if (e.type === "verdict" && e.data?.decision === "lead") leads += 1;
  }
  return { leads, spent };
}

function ResultsView({ res, onClues }: { res: Results; onClues: (ids: number[], center: number) => void }) {
  const k = res.kpi;
  const deepRejected = res.rejected.filter((r) => r.verdict);
  const earlyDropped = k.scanned - res.leads.length - res.watch.length - deepRejected.length;
  const isSample = res.run.dataset?.sample_key && res.run.product?.sample_key;
  return (
    <div className="space-y-10">
      {(() => {
        const summary = `${num(k.leads)} نفر از ${num(k.scanned)} پیام · هزینه ${usd(k.equivalent_cost_usd)}`
          + (k.cost_per_lead_usd != null ? ` · هر نفر ${usd(k.cost_per_lead_usd)}` : "")
          + (k.saved_usd > 0 ? (k.cost_usd > 0 ? ` · ${usd(k.saved_usd)} از حافظه` : " · این بار رایگان") : "");
        return <p className="truncate" title={summary}>{summary}</p>;
      })()}

      <section>
        <h2 className="font-bold">کسانی که پیدا شدند</h2>
        {res.leads.length === 0 ? (
          <p className="mt-3 text-sm text-ink-500">کسی پیدا نشد. دلیل‌ها را پایین‌تر ببینید.</p>
        ) : (
          <ul className="divide-y divide-ink-100">
            {res.leads.map((l) => <LeadCard key={l.msg_id} lead={l} runId={res.run.id} onClues={onClues} />)}
          </ul>
        )}
      </section>

      {res.watch.length > 0 && (
        <section>
          <h2 className="mb-2 font-bold">شاید بعدا</h2>
          <ul className="space-y-1 text-sm">
            {res.watch.map((w) => (
              <li key={w.msg_id} title={w.why_not ?? undefined} className="truncate">
                <Link to={`/app/runs/${res.run.id}/leads/${w.msg_id}`} className="font-bold hover:underline">{w.author}</Link>: {w.why_not}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="mb-2 font-bold">رد شدند</h2>
        <ul className="space-y-1 text-sm">
          {deepRejected.map((r) => (
            <li key={r.msg_id} title={r.why_not ?? undefined} className="truncate">
              <button onClick={() => onClues([r.msg_id], r.msg_id)} className="font-bold hover:underline">{r.author}</button>: {r.why_not ?? DECISION_FA[r.decision]}
            </li>
          ))}
        </ul>
        {earlyDropped > 0 && (
          <p className="mt-2 text-sm text-ink-500">{num(earlyDropped)} پیام دیگر در بررسی‌های اول کنار رفتند.</p>
        )}
      </section>

      <section>
        <h2 className="mb-2 font-bold">هزینه هر مرحله</h2>
        <table className="w-full max-w-md text-sm">
          <tbody>
            {res.funnel.slice(1).map((f) => (
              <tr key={f.stage} className="border-b border-ink-100">
                <td className="py-1.5">{COST_STEP[f.stage] ?? f.label}</td>
                <td className="py-1.5">{num(f.count)} پیام</td>
                <td className="py-1.5 text-ink-500">{usd(f.cost)}</td>
              </tr>
            ))}
            {res.stats.stage_cost?.x_user > 0 && (
              <tr className="border-b border-ink-100">
                <td className="py-1.5">نام کاربری در ایکس</td>
                <td className="py-1.5">{num(res.leads.length)} نفر</td>
                <td className="py-1.5 text-ink-500">{usd(res.stats.stage_cost.x_user)}</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {isSample && (
        <p className="text-sm">
          <Link to={`/app/eval?run=${res.run.id}`} className="text-thread-700 hover:underline">دقت این اجرا روی داده نمونه</Link>
        </p>
      )}
    </div>
  );
}

export default function RunPage() {
  const { id } = useParams();
  const [run, setRun] = useState<RunSummary | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [done, setDone] = useState(false);
  const [res, setRes] = useState<Results | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [clues, setClues] = useState<{ ids: number[]; center: number } | null>(null);
  const [showFeed, setShowFeed] = useState(false);

  useEffect(() => {
    api.get<RunSummary>(`/api/runs/${id}`).then(setRun).catch((e) => setError(errorText(e)));
    setEvents([]);
    setDone(false);
    setRes(null);
    const seen = new Set<number>();
    let failures = 0;
    const es = new EventSource(`/api/runs/${id}/stream`);
    es.onmessage = (m) => {
      failures = 0;
      const ev: AgentEvent = JSON.parse(m.data);
      if (seen.has(ev.seq)) return;
      seen.add(ev.seq);
      setEvents((prev) => [...prev, ev]);
      if (ev.type === "done") { es.close(); setDone(true); }
    };
    es.onerror = () => {
      failures += 1;
      if (failures > 4) { es.close(); setError("اتصال قطع شد. صفحه را تازه کنید."); }
    };
    return () => es.close();
  }, [id]);

  useEffect(() => {
    if (!done) return;
    api.get<RunSummary>(`/api/runs/${id}`).then(setRun).catch(() => undefined);
    api.get<Results>(`/api/runs/${id}/results`).then(setRes).catch((e) => setError(errorText(e)));
  }, [done, id]);

  const live = useMemo(() => liveCounters(events), [events]);

  return (
    <Layout>
      {run && (
        <div className="mb-6 flex items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold">{shortName(run.product?.name)}</h1>
            <p className="text-sm text-ink-500">
              {run.dataset?.name} · {done ? STATUS_FA[run.status] ?? "تمام شد" : "در حال اجرا"}
              {run.stop_reason === "budget" && " · بودجه تمام شد"}
            </p>
          </div>
          {!done && <Button variant="danger" size="sm" onClick={() => api.post(`/api/runs/${id}/stop`).catch(() => undefined)}>توقف</Button>}
        </div>
      )}
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}

      {!done ? (
        <>
          {run && (
            <p className="mb-4 text-sm text-ink-500">
              تا الان {num(live.leads)} نفر پیدا شده · خرج‌شده {usd(live.spent)} از {usd(run.budget_usd)}
            </p>
          )}
          {events.length === 0 ? <Loading text="در حال شروع…" /> : <LiveFeed events={events} running />}
        </>
      ) : !res ? (
        <Loading text="در حال آماده‌سازی نتایج…" />
      ) : (
        <>
          <ResultsView res={res} onClues={(ids, center) => setClues({ ids, center })} />
          <div className="mt-10">
            <button className="text-sm text-ink-500 hover:underline" onClick={() => setShowFeed(!showFeed)} aria-expanded={showFeed}>
              {showFeed ? "بستن گزارش کار عامل" : "دیدن گزارش کار عامل"}
            </button>
            {showFeed && <div className="mt-3"><LiveFeed events={events} running={false} /></div>}
          </div>
        </>
      )}

      {clues && res?.run.dataset && (
        <ChatDrawer datasetId={res.run.dataset.id} center={clues.center} highlight={clues.ids} onClose={() => setClues(null)} />
      )}
    </Layout>
  );
}
