import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { BurnLine, FunnelChart, LeadRadar, OpportunityMap } from "../components/charts";
import { ChatDrawer } from "../components/ChatView";
import { LeadCard } from "../components/LeadCard";
import { LiveFeed } from "../components/LiveFeed";
import { Layout } from "../components/Layout";
import { Badge, Button, Card, Empty, ErrorBox, LinkButton, Loading, SectionTitle, Steps, cx } from "../components/ui";
import { api, errorText } from "../lib/api";
import { DECISION_FA, STATUS_FA, mid, num, shortDate, usd } from "../lib/fmt";
import type { AgentEvent, LeadItem, Results, RunSummary } from "../lib/types";

function Kpi({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <Card className={cx("p-4", accent && "border-thread-200 bg-thread-50/60")}>
      <div className="text-xs font-bold text-ink-500">{label}</div>
      <div className="mt-1 text-2xl font-extrabold text-ink-900">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-400">{sub}</div>}
    </Card>
  );
}

function BudgetMeter({ spent, budget, replay }: { spent: number; budget: number; replay?: boolean }) {
  const pct = Math.min(100, (spent / budget) * 100);
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-ink-500">
        <span>خرج‌شده: <b className="text-ink-800">{usd(spent)}</b></span>
        <span>بودجه: {usd(budget)}</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-ink-100" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="مصرف بودجه">
        <div className={cx("h-full rounded-full transition-all", pct > 90 ? "bg-red-500" : "bg-thread-500")} style={{ width: `${Math.max(pct, spent > 0 ? 2 : 0)}%` }} />
      </div>
      {replay && <div className="mt-1 text-xs text-ink-400">♻️ بازپخش از حافظه — بدون هزینه واقعی</div>}
    </div>
  );
}

function liveCounters(events: AgentEvent[]) {
  let scanned = 0, prefiltered = 0, candidates = 0, investigated = 0, leads = 0, spent = 0;
  for (const e of events) {
    spent += e.cost_usd || 0;
    if (e.type === "stage" && e.data?.stage === "start") scanned = e.data.scanned ?? scanned;
    if (e.type === "stage" && e.data?.kept !== undefined) prefiltered = e.data.kept;
    if (e.type === "stage" && e.data?.candidates !== undefined) candidates = e.data.candidates;
    if (e.type === "verdict") { investigated += 1; if (e.data?.decision === "lead") leads += 1; }
  }
  return { scanned, prefiltered, candidates, investigated, leads, spent };
}

function WhyNot({ items, onOpen }: { items: LeadItem[]; onOpen: (id: number) => void }) {
  const [tab, setTab] = useState<"deep" | "triage">("deep");
  const deep = items.filter((i) => i.verdict);
  const tri = items.filter((i) => !i.verdict);
  const list = tab === "deep" ? deep : tri;
  return (
    <Card>
      <SectionTitle title="چرا نه؟" sub="پیام‌هایی که رد شدند، با دلیل یک‌خطی" />
      <div className="mb-3 flex gap-2 text-sm">
        <button onClick={() => setTab("deep")} className={cx("rounded-lg px-3 py-1.5 font-bold", tab === "deep" ? "bg-ink-900 text-white" : "bg-ink-50 text-ink-600")}>بعد از بررسی عمیق ({num(deep.length)})</button>
        <button onClick={() => setTab("triage")} className={cx("rounded-lg px-3 py-1.5 font-bold", tab === "triage" ? "bg-ink-900 text-white" : "bg-ink-50 text-ink-600")}>در تریاژ ({num(tri.length)})</button>
      </div>
      {list.length === 0 ? <div className="py-6 text-center text-sm text-ink-400">موردی نیست.</div> : (
        <ul className="max-h-96 divide-y divide-ink-50 overflow-y-auto">
          {list.map((i) => (
            <li key={i.msg_id}>
              <button onClick={() => onOpen(i.msg_id)} className="w-full py-2.5 text-start hover:bg-ink-50/60">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-bold text-ink-800">{i.author} <span className="font-normal text-ink-400">#{mid(i.msg_id)}</span></span>
                  <span className="text-ink-400">{i.fit != null ? `تناسب ${num(i.fit, 1)}` : i.triage ? `امتیاز تریاژ ${num(i.triage.relevance)}` : ""}</span>
                </div>
                <div dir="auto" className="mt-0.5 line-clamp-1 text-sm text-ink-500">{i.text}</div>
                <div className="mt-0.5 text-sm text-ink-800">✖️ {i.why_not ?? DECISION_FA[i.decision]}</div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ResultsView({ res, onClues }: { res: Results; onClues: (ids: number[], center: number) => void }) {
  const nav = useNavigate();
  const [compare, setCompare] = useState<number[]>([]);
  const k = res.kpi;
  const toggle = (id: number) => setCompare((c) => (c.includes(id) ? c.filter((x) => x !== id) : c.length >= 3 ? [...c.slice(1), id] : [...c, id]));
  const compared = res.leads.filter((l) => compare.includes(l.msg_id));
  const isSample = res.run.dataset?.sample_key && res.run.product?.sample_key;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="پیام‌های خوانده‌شده" value={num(k.scanned)} sub={`${num(res.funnel[1]?.count ?? 0)} از پیش‌فیلتر گذشتند`} />
        <Kpi label="سرنخ واقعی" value={num(k.leads)} sub={res.watch.length ? `${num(res.watch.length)} نفر زیر نظر` : "با شواهد و پاسخ آماده"} accent />
        <Kpi label="هزینه کل" value={usd(k.equivalent_cost_usd)} sub={k.saved_usd > 0 ? `پرداخت واقعی این بار: ${usd(k.cost_usd)}` : "هزینه واقعی API"} />
        <Kpi label="هزینه هر سرنخ" value={usd(k.cost_per_lead_usd)} sub="هزینه کل تقسیم بر سرنخ‌ها" />
      </div>

      {isSample && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-ink-900 px-5 py-3 text-sm text-white">
          <span>این اجرا روی داده نمونه است و پاسخ درست آن را می‌دانیم.</span>
          <LinkButton to={`/app/eval?run=${res.run.id}`} variant="thread" size="sm">دیدن ارزیابی دقت ←</LinkButton>
        </div>
      )}

      <section>
        <SectionTitle title={`سرنخ‌ها (${num(res.leads.length)})`} sub="خط‌چین: شکل مشتری ایده‌آل از پروفایل · روی شماره پیام‌ها بزنید تا در گفتگو ببینید" />
        {res.leads.length === 0 ? (
          <Empty title="سرنخ واقعی پیدا نشد">در این پیام‌ها کسی که واقعا به محصول نیاز داشته باشد دیده نشد. بخش «چرا نه؟» دلیل‌ها را نشان می‌دهد؛ با بودجه بیشتر یا گفتگوی دیگری امتحان کنید.</Empty>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {res.leads.map((l) => (
              <LeadCard key={l.msg_id} lead={l} ideal={res.ideal_shape} runId={res.run.id} onClues={onClues}
                compareOn={compare.includes(l.msg_id)} onCompare={() => toggle(l.msg_id)} />
            ))}
          </div>
        )}
      </section>

      {compared.length >= 2 && (
        <Card>
          <SectionTitle title="مقایسه سرنخ‌ها" sub="حداکثر سه نفر" action={<Button size="sm" variant="ghost" onClick={() => setCompare([])}>پاک کردن</Button>} />
          <LeadRadar series={compared.map((l) => ({ name: l.author, scores: l.scores! }))} ideal={res.ideal_shape} height={320} />
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card><FunnelChart funnel={res.funnel} /></Card>
        <Card><OpportunityMap points={res.opportunity} onPick={(id) => nav(`/app/runs/${res.run.id}/leads/${id}`)} /></Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <WhyNot items={res.rejected} onOpen={(id) => onClues([id], id)} />
        <div className="space-y-4">
          {res.burn.length > 1 && <Card><BurnLine burn={res.burn} budget={res.run.budget_usd} /></Card>}
          {res.watch.length > 0 && (
            <Card>
              <SectionTitle title="زیر نظر" sub="علاقه دارند ولی هنوز آماده نیستند" />
              <ul className="space-y-2 text-sm">
                {res.watch.map((w) => (
                  <li key={w.msg_id}><Link className="font-bold hover:underline" to={`/app/runs/${res.run.id}/leads/${w.msg_id}`}>{w.author}</Link> — {w.why_not}</li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
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
      if (failures > 4) { es.close(); setError("اتصال زنده قطع شد. صفحه را تازه کنید."); }
    };
    return () => es.close();
  }, [id]);

  useEffect(() => {
    if (!done) return;
    api.get<RunSummary>(`/api/runs/${id}`).then(setRun).catch(() => undefined);
    api.get<Results>(`/api/runs/${id}/results`).then(setRes).catch((e) => setError(errorText(e)));
  }, [done, id]);

  const live = useMemo(() => liveCounters(events), [events]);
  const running = !done;
  const replay = !!run?.replay || events.some((e) => e.data?.cached);
  const stop = async () => { await api.post(`/api/runs/${id}/stop`).catch(() => undefined); };

  return (
    <Layout wide>
      <Steps current={done ? 4 : 3} />
      {run && (
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold">{run.product?.name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-500">
              <span>{run.dataset?.name}</span>
              <Badge className={done ? "bg-emerald-50 text-emerald-800 ring-emerald-200" : "bg-amber-50 text-amber-900 ring-amber-200"}>
                {done ? (STATUS_FA[run.status] ?? "تمام شد") : "در حال اجرا"}
              </Badge>
              {run.finished_at && run.started_at && <span>· {num(Math.round(run.finished_at - run.started_at))} ثانیه</span>}
              {run.stop_reason === "budget" && <Badge className="bg-red-50 text-red-800 ring-red-200">💸 بودجه تمام شد</Badge>}
            </div>
          </div>
          <div className="flex gap-2">
            {running && <Button variant="danger" size="sm" onClick={stop}>توقف</Button>}
            {done && <LinkButton to="/app/new" variant="outline" size="sm">جستجوی تازه</LinkButton>}
          </div>
        </div>
      )}
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}
      {run?.status === "failed" && run.error && done && (
        <div className="mb-4"><ErrorBox message="اجرا کامل نشد؛ نتایجی که تا آن لحظه به دست آمده بود ذخیره شده است." /></div>
      )}

      {running ? (
        <div className="grid gap-5 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <SectionTitle title="عامل در حال دنبال کردن رشته‌ها" sub="هر کارت یک نفر است که عامل ردش را می‌گیرد" />
            {events.length === 0 ? <Loading text="در حال اتصال به عامل…" /> : <LiveFeed events={events} running />}
          </Card>
          <div className="space-y-3">
            <Card>{run && <BudgetMeter spent={live.spent} budget={run.budget_usd} replay={replay} />}</Card>
            <div className="grid grid-cols-2 gap-3">
              <Kpi label="پیام‌ها" value={num(live.scanned)} />
              <Kpi label="از پیش‌فیلتر" value={num(live.prefiltered)} />
              <Kpi label="بررسی عمیق" value={`${num(live.investigated)} / ${num(live.candidates)}`} />
              <Kpi label="سرنخ تا الان" value={num(live.leads)} accent />
            </div>
          </div>
        </div>
      ) : !res ? (
        <Loading text="در حال آماده‌سازی نتایج…" />
      ) : (
        <>
          {replay && (
            <div className="mb-4 rounded-2xl bg-thread-50 px-5 py-3 text-sm text-ink-800 ring-1 ring-thread-200">
              ♻️ نتیجه این اجرا از حافظه پخش شد (همان پیام‌ها و همان پروفایل قبلا بررسی شده بودند)، پس تقریبا هزینه‌ای نداشت.
              «هزینه کل» همان مبلغی است که بررسی اولیه خرج کرد.
            </div>
          )}
          <ResultsView res={res} onClues={(ids, center) => setClues({ ids, center })} />
          <Card className="mt-6">
            <button className="flex w-full items-center justify-between font-extrabold" onClick={() => setShowFeed(!showFeed)} aria-expanded={showFeed}>
              <span>گزارش کامل کار عامل ({num(events.length)} رویداد)</span><span>{showFeed ? "▲" : "▼"}</span>
            </button>
            {showFeed && <div className="mt-3"><LiveFeed events={events} running={false} /></div>}
          </Card>
          {run && <p className="mt-4 text-center text-xs text-ink-400">اجرای شماره {num(run.id)} · {shortDate(new Date(run.created_at * 1000).toISOString())}</p>}
        </>
      )}

      {clues && res?.run.dataset && (
        <ChatDrawer datasetId={res.run.dataset.id} center={clues.center} highlight={clues.ids} onClose={() => setClues(null)} />
      )}
    </Layout>
  );
}
