import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { LeadRadar } from "../components/charts";
import { ChatDrawer } from "../components/ChatView";
import { ReplyBox, Vote } from "../components/LeadCard";
import { Layout } from "../components/Layout";
import { ErrorBox, Loading } from "../components/ui";
import { api, errorText } from "../lib/api";
import { AXES_FA, AXES_ORDER, DECISION_FA, TEMP, mid, num, shortDate, usd } from "../lib/fmt";
import type { Results } from "../lib/types";

const TOOL_FA: Record<string, string> = {
  get_thread: "رشته گفتگو را خواند",
  get_user_history: "پیام‌های قبلی این فرد را دید",
  get_nearby: "پیام‌های اطراف را دید",
  check_resolved: "بررسی کرد که نیازش قبلا برطرف نشده باشد",
  search_chat: "در گروه جستجو کرد",
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
  const evidenceIds = (lead?.evidence ?? []).map((e) => e.msg_id);

  return (
    <Layout>
      <Link to={`/app/runs/${id}`} className="text-sm text-ink-500 hover:underline">بازگشت به نتایج</Link>
      {error && <div className="mt-4"><ErrorBox message={error} /></div>}
      {!res && !error && <Loading />}
      {res && !lead && <p className="mt-6 text-ink-500">این پیام در نتایج نیست.</p>}
      {lead && (
        <div className="mt-6 space-y-8">
          <div>
            <h1 className="text-xl font-bold">{lead.author}</h1>
            <p className="text-sm text-ink-500">
              {DECISION_FA[lead.decision]}
              {lead.fit != null && <> · {num(lead.fit, 1)} از ۱۰</>}
              {lead.temperature && <> · {TEMP[lead.temperature].label}</>}
            </p>
            <p dir="auto" className="mt-4 whitespace-pre-wrap border-s-2 border-ink-200 ps-3 leading-8">{lead.text}</p>
            <p className="mt-1 text-xs text-ink-400">پیام #{mid(lead.msg_id)} · {shortDate(lead.date)}</p>
          </div>

          {v && (
            <section>
              <h2 className="mb-2 font-bold">چرا</h2>
              <p className="leading-8">{v.reasoning}</p>
              {v.disqualifiers_found.length > 0 && <p className="mt-2 text-sm">دلیل رد: {v.disqualifiers_found.join("، ")}</p>}
              {lead.why_not && lead.decision !== "lead" && <p className="mt-2 text-sm">{lead.why_not}</p>}
              {lead.critic && (
                <p className="mt-2 text-sm text-ink-500">
                  یک بار هم سعی شد این نتیجه رد شود: «{lead.critic.strongest_objection}» نتیجه: {lead.critic.survives ? "ماند" : "رد شد"}.
                </p>
              )}
            </section>
          )}

          {lead.scores && (
            <section>
              <h2 className="mb-2 font-bold">امتیازها</h2>
              <LeadRadar series={[{ name: "این فرد", scores: lead.scores }]} ideal={res!.ideal_shape} height={260} />
              <p className="mt-2 text-sm text-ink-500">
                {AXES_ORDER.map((k) => `${AXES_FA[k]} ${num(lead.scores![k])}`).join(" · ")}
              </p>
              <p className="text-xs text-ink-400">خط‌چین: مشتری ایده‌آل</p>
            </section>
          )}

          {evidenceIds.length > 0 && (
            <section>
              <h2 className="mb-2 font-bold">پیام‌هایی که به آن‌ها استناد شد</h2>
              <ul className="space-y-3">
                {lead.evidence!.map((e) => (
                  <li key={e.msg_id}>
                    <button className="text-start hover:underline" onClick={() => setClues({ ids: evidenceIds, center: e.msg_id })}>
                      <span className="text-sm text-ink-500">{e.author}: </span>
                      <span dir="auto" className="text-sm">{e.text}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {lead.trace && lead.trace.length > 0 && (
            <section>
              <h2 className="mb-2 font-bold">کارهایی که عامل کرد</h2>
              <ul className="list-inside list-disc space-y-1 text-sm">
                {lead.trace.map((t, i) => (
                  <li key={i}>{TOOL_FA[t.tool] ?? t.tool}{t.args?.why ? ` (${t.args.why})` : ""}</li>
                ))}
              </ul>
            </section>
          )}

          {lead.reply && (
            <section>
              <h2 className="mb-2 font-bold">پاسخ پیشنهادی</h2>
              <ReplyBox reply={lead.reply} />
            </section>
          )}

          <div className="flex items-center justify-between text-sm text-ink-500">
            <span className="flex items-center gap-2">درست بود؟ <Vote runId={Number(id)} msgId={lead.msg_id} initial={lead.vote ?? 0} /></span>
            <span>هزینه بررسی: {usd(lead.equiv_cost_usd)}</span>
          </div>
        </div>
      )}
      {clues && res?.run.dataset && (
        <ChatDrawer datasetId={res.run.dataset.id} center={clues.center} highlight={clues.ids} onClose={() => setClues(null)} />
      )}
    </Layout>
  );
}
