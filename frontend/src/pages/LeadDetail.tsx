import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { LeadRadar } from "../components/charts";
import { ChatDrawer } from "../components/ChatView";
import { FitScore, ReplyBox, TempBadge, Vote } from "../components/LeadCard";
import { Layout } from "../components/Layout";
import { Badge, Card, Empty, ErrorBox, Loading, SectionTitle } from "../components/ui";
import { api, errorText } from "../lib/api";
import { ACTION_FA, AXES_FA, AXES_ORDER, DECISION_FA, SIGNAL_FA, TIMING_FA, mid, num, shortDate, usd } from "../lib/fmt";
import type { Results } from "../lib/types";

const TOOL_FA: Record<string, string> = {
  get_thread: "🧵 خواندن رشته گفتگو",
  get_user_history: "👤 مرور سابقه پیام‌های فرد",
  get_nearby: "↕️ پیام‌های اطراف",
  check_resolved: "✅ بررسی حل‌شدن نیاز",
  search_chat: "🔍 جستجو در گروه",
};

export default function LeadDetail() {
  const { id, msgId } = useParams();
  const [res, setRes] = useState<Results | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [clues, setClues] = useState<{ ids: number[]; center: number } | null>(null);
  useEffect(() => {
    api.get<Results>(`/api/runs/${id}/results`).then(setRes).catch((e) => setError(errorText(e)));
  }, [id]);

  const lead = res && [...res.leads, ...res.watch, ...res.rejected].find((l) => String(l.msg_id) === msgId);
  const v = lead?.verdict;

  return (
    <Layout>
      <Link to={`/app/runs/${id}`} className="mb-4 inline-block text-sm font-bold text-ink-600 hover:underline">→ بازگشت به نتایج</Link>
      {error && <ErrorBox message={error} />}
      {!res && !error && <Loading />}
      {res && !lead && <Empty title="این پیام در نتایج نیست" />}
      {lead && (
        <div className="space-y-5">
          <Card>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-2xl font-extrabold">{lead.author}</h1>
                  <TempBadge t={lead.temperature} />
                  <Badge className="bg-ink-50 text-ink-700 ring-ink-200">{DECISION_FA[lead.decision]}</Badge>
                </div>
                <div className="mt-1 text-sm text-ink-500">پیام #{mid(lead.msg_id)} · {shortDate(lead.date)}</div>
              </div>
              <FitScore fit={lead.fit} />
            </div>
            <blockquote dir="auto" className="mt-4 whitespace-pre-wrap rounded-xl border-s-4 border-thread-400 bg-thread-50/60 px-4 py-3 leading-8 text-ink-900">{lead.text}</blockquote>
            {lead.triage && (
              <p className="mt-3 text-xs text-ink-500">تریاژ ({SIGNAL_FA[lead.triage.signal]}، {num(lead.triage.relevance)} از ۱۰): {lead.triage.reason}</p>
            )}
          </Card>

          {v && lead.scores && (
            <div className="grid gap-5 md:grid-cols-2">
              <Card>
                <SectionTitle title="شش محور" sub="خط‌چین: مشتری ایده‌آل" />
                <LeadRadar series={[{ name: "این فرد", scores: lead.scores }]} ideal={res!.ideal_shape} height={280} />
                <ul className="mt-2 space-y-1.5 text-sm">
                  {AXES_ORDER.map((k) => (
                    <li key={k} className="flex items-center gap-2">
                      <span className="w-28 shrink-0 text-ink-600">{AXES_FA[k]}</span>
                      <span className="h-2 flex-1 overflow-hidden rounded-full bg-ink-100">
                        <span className="block h-full rounded-full bg-thread-500" style={{ width: `${lead.scores![k] * 10}%` }} />
                      </span>
                      <span className="w-6 text-center font-bold">{num(lead.scores![k])}</span>
                    </li>
                  ))}
                </ul>
              </Card>
              <Card className="space-y-3 text-sm leading-7">
                <SectionTitle title="قضاوت عامل" />
                <p><b>نیاز: </b>{v.stated_need || "—"}</p>
                <p><b>استدلال: </b>{v.reasoning}</p>
                <p><b>زمان‌بندی: </b>{TIMING_FA[v.timing]} · <b>اقدام پیشنهادی: </b>{ACTION_FA[v.action]}</p>
                {lead.weak && <p><b>نقطه ضعف: </b>{lead.weak.label} ({num(lead.weak.score)} از ۱۰)</p>}
                {v.disqualifiers_found.length > 0 && <p className="text-red-800"><b>ردکننده‌ها: </b>{v.disqualifiers_found.join(" · ")}</p>}
                {lead.why_not && <p className="text-ink-600"><b>چرا نه: </b>{lead.why_not}</p>}
                {lead.critic && (
                  <div className="rounded-xl bg-purple-50 px-3 py-2 text-purple-900 ring-1 ring-purple-200">
                    <b>😈 وکیل مدافع شیطان: </b>{lead.critic.strongest_objection}
                    <div className="mt-1 font-bold">{lead.critic.survives ? "✅ سرنخ ماند" : "❌ سرنخ رد شد"} — {lead.critic.reason}</div>
                  </div>
                )}
                <p className="text-xs text-ink-400">هزینه بررسی این پیام: {usd(lead.equiv_cost_usd)}{lead.cached ? " (این بار از حافظه)" : ""}</p>
              </Card>
            </div>
          )}

          {lead.evidence && lead.evidence.length > 0 && (
            <Card>
              <SectionTitle title="سرنخ‌ها (پیام‌های شاهد)" sub="روی هر پیام بزنید تا در دل گفتگو ببینید" />
              <ul className="space-y-2">
                {lead.evidence.map((e) => (
                  <li key={e.msg_id}>
                    <button className="w-full rounded-xl border border-ink-100 px-3 py-2 text-start hover:border-thread-300"
                      onClick={() => setClues({ ids: lead.evidence!.map((x) => x.msg_id), center: e.msg_id })}>
                      <div className="text-xs text-ink-400"><b className="text-thread-700">#{mid(e.msg_id)}</b> · {e.author} · {shortDate(e.date)}</div>
                      <div dir="auto" className="text-sm leading-7 text-ink-800">{e.text}</div>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {lead.trace && lead.trace.length > 0 && (
            <Card>
              <SectionTitle title="مسیر بررسی عامل" sub="ابزارهایی که عامل خودش انتخاب کرد" />
              <ol className="ms-2 space-y-2 border-s-2 border-dashed border-thread-300 ps-4 text-sm">
                {lead.trace.map((t, i) => (
                  <li key={i}>
                    <span className="font-bold">{TOOL_FA[t.tool] ?? t.tool}</span>
                    <span className="text-xs text-ink-400"> · مرحله {num(t.step)}</span>
                    {t.args?.why && <div className="text-ink-600">«{t.args.why}»</div>}
                    {t.args?.query && <div className="text-xs text-ink-500">جستجو: {t.args.query}</div>}
                  </li>
                ))}
              </ol>
            </Card>
          )}

          {lead.reply && (
            <Card>
              <SectionTitle title="پیش‌نویس پاسخ" />
              <ReplyBox reply={lead.reply} />
            </Card>
          )}

          <Card><Vote runId={Number(id)} msgId={lead.msg_id} initial={lead.vote ?? 0} /></Card>
        </div>
      )}
      {clues && res?.run.dataset && (
        <ChatDrawer datasetId={res.run.dataset.id} center={clues.center} highlight={clues.ids} onClose={() => setClues(null)} />
      )}
    </Layout>
  );
}
