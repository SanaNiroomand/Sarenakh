import { useState } from "react";
import { Link } from "react-router-dom";
import { api, errorText } from "../lib/api";
import { TEMP, mid, num, usd } from "../lib/fmt";
import type { LeadItem } from "../lib/types";
import { Button, OneLine, cx } from "./ui";

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}

export function TempBadge({ t }: { t: LeadItem["temperature"] }) {
  if (!t) return null;
  return <span className="text-sm text-ink-500">{TEMP[t].label}</span>;
}

export function FitScore({ fit }: { fit: number | null; size?: "lg" | "sm" }) {
  return <span className="shrink-0 font-bold" title="امتیاز تناسب">{num(fit, 1)} از ۱۰</span>;
}

export function ReplyBox({ reply }: { reply: NonNullable<LeadItem["reply"]> }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="rounded-xl bg-ink-50 p-3">
      <p dir="auto" className="whitespace-pre-wrap text-sm leading-7">{reply.reply}</p>
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-xs text-ink-400">{reply.mode === "help_soft_mention" ? "کمک + معرفی محصول" : "فقط کمک"}</span>
        <Button size="sm" variant="outline" onClick={async () => { setCopied(await copyText(reply.reply)); setTimeout(() => setCopied(false), 1800); }}>
          {copied ? "کپی شد" : "کپی پاسخ"}
        </Button>
      </div>
    </div>
  );
}

export function Vote({ runId, msgId, initial }: { runId: number; msgId: number; initial: number }) {
  const [vote, setVote] = useState(initial);
  const [err, setErr] = useState<string | null>(null);
  const send = async (v: number) => {
    const next = vote === v ? 0 : v;
    const prev = vote;
    setVote(next);
    setErr(null);
    try {
      await api.post(`/api/runs/${runId}/feedback`, { msg_id: msgId, vote: next });
    } catch (e) {
      setVote(prev);
      setErr(errorText(e));
    }
  };
  return (
    <span className="flex items-center gap-1">
      <button onClick={() => send(1)} aria-pressed={vote === 1} title="درست بود"
        className={cx("rounded-lg px-2 py-0.5", vote === 1 ? "bg-emerald-100" : "hover:bg-ink-50")}>👍</button>
      <button onClick={() => send(-1)} aria-pressed={vote === -1} title="درست نبود"
        className={cx("rounded-lg px-2 py-0.5", vote === -1 ? "bg-red-100" : "hover:bg-ink-50")}>👎</button>
      {err && <span className="text-xs text-red-700">{err}</span>}
    </span>
  );
}

export function LeadCard({ lead, runId, onClues }: {
  lead: LeadItem; runId: number; onClues: (ids: number[], center: number) => void;
}) {
  const clueIds = (lead.evidence ?? []).map((e) => e.msg_id);
  return (
    <li className="space-y-3 py-5">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <span className="font-bold">{lead.author}</span>{" "}
          <TempBadge t={lead.temperature} />
          {lead.url && (
            <a href={lead.url} target="_blank" rel="noopener noreferrer" className="ms-2 text-sm text-thread-700 hover:underline">دیدن در ایکس</a>
          )}
        </div>
        <FitScore fit={lead.fit} />
      </div>
      {lead.verdict?.stated_need && <OneLine text={lead.verdict.stated_need} className="text-sm" />}
      <div className="text-sm text-ink-500">
        پیام‌ها:{" "}
        {clueIds.map((id) => (
          <button key={id} onClick={() => onClues(clueIds, id)} className="me-2 text-thread-700 hover:underline">#{mid(id)}</button>
        ))}
      </div>
      {lead.reply && <ReplyBox reply={lead.reply} />}
      <div className="flex items-center justify-between gap-3 text-sm text-ink-500">
        <Vote runId={runId} msgId={lead.msg_id} initial={lead.vote ?? 0} />
        <span>هزینه بررسی: {usd(lead.equiv_cost_usd)}</span>
        <Link to={`/app/runs/${runId}/leads/${lead.msg_id}`} className="text-ink-700 hover:underline">جزئیات</Link>
      </div>
    </li>
  );
}
