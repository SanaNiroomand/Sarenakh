import { useState } from "react";
import { Link } from "react-router-dom";
import { api, errorText } from "../lib/api";
import { ACTION_FA, TEMP, TIMING_FA, mid, num, shortDate, usd } from "../lib/fmt";
import type { Axes, LeadItem } from "../lib/types";
import { LeadRadar } from "./charts";
import { Badge, Button, Card, cx } from "./ui";

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
  const x = TEMP[t];
  return <Badge className={x.cls}>{x.icon} {x.label}</Badge>;
}

export function FitScore({ fit, size = "lg" }: { fit: number | null; size?: "lg" | "sm" }) {
  return (
    <div className="text-end leading-none" title="امتیاز کلی تناسب (محاسبه در کد از شش محور)">
      <span className={cx("font-extrabold text-ink-900", size === "lg" ? "text-3xl" : "text-xl")}>{num(fit, 1)}</span>
      <span className="text-xs text-ink-400"> /۱۰</span>
    </div>
  );
}

export function ReplyBox({ reply }: { reply: NonNullable<LeadItem["reply"]> }) {
  const [copied, setCopied] = useState(false);
  const soft = reply.mode === "help_soft_mention";
  return (
    <div className="rounded-xl border border-ink-100 bg-ink-50/60 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <Badge className={soft ? "bg-thread-50 text-thread-700 ring-thread-200" : "bg-emerald-50 text-emerald-800 ring-emerald-200"}>
          {soft ? "✍️ کمک + معرفی ملایم" : "🤝 فقط کمک"}
        </Badge>
        <Button size="sm" variant="outline" onClick={async () => { setCopied(await copyText(reply.reply)); setTimeout(() => setCopied(false), 1800); }}>
          {copied ? "✓ کپی شد" : "کپی پاسخ"}
        </Button>
      </div>
      <p dir="auto" className="whitespace-pre-wrap text-sm leading-7 text-ink-900">{reply.reply}</p>
      {reply.facts_used.length > 0 && (
        <div className="mt-2 text-xs text-ink-500">
          <span className="font-bold">واقعیت‌های استفاده‌شده از پروفایل محصول: </span>{reply.facts_used.join(" · ")}
        </div>
      )}
      {reply.revised && <div className="mt-1 text-xs text-ink-400">پس از بازبینی منتقد یک بار اصلاح شد.</div>}
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
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-ink-500">درست بود؟</span>
      <button onClick={() => send(1)} aria-pressed={vote === 1} title="سرنخ درستی بود"
        className={cx("rounded-lg px-2 py-1 text-base ring-1", vote === 1 ? "bg-emerald-50 ring-emerald-300" : "ring-ink-100 hover:bg-ink-50")}>👍</button>
      <button onClick={() => send(-1)} aria-pressed={vote === -1} title="سرنخ درستی نبود"
        className={cx("rounded-lg px-2 py-1 text-base ring-1", vote === -1 ? "bg-red-50 ring-red-300" : "ring-ink-100 hover:bg-ink-50")}>👎</button>
      {vote !== 0 && <span className="text-xs text-ink-400">ثبت شد — در اجرای بعدی از آن یاد می‌گیرد</span>}
      {err && <span className="text-xs text-red-700">{err}</span>}
    </div>
  );
}

export function LeadCard({ lead, ideal, runId, onClues, compareOn, onCompare }: {
  lead: LeadItem; ideal: Axes | null; runId: number;
  onClues: (ids: number[], center: number) => void;
  compareOn?: boolean; onCompare?: () => void;
}) {
  const v = lead.verdict!;
  const clueIds = (lead.evidence ?? []).map((e) => e.msg_id);
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-base font-extrabold text-ink-900">{lead.author}</span>
            <TempBadge t={lead.temperature} />
            {lead.cached && <Badge className="bg-ink-50 text-ink-500 ring-ink-100" >♻️ از حافظه</Badge>}
          </div>
          <div className="mt-0.5 text-xs text-ink-400">{shortDate(lead.date)} · {TIMING_FA[v.timing]} · پیشنهاد: {ACTION_FA[v.action]}</div>
        </div>
        <FitScore fit={lead.fit} />
      </div>

      <p className="text-sm leading-7 text-ink-800"><span className="font-bold">نیاز: </span>{v.stated_need}</p>

      {lead.scores && <LeadRadar series={[{ name: "این فرد", scores: lead.scores }]} ideal={ideal} height={210} compact />}

      <div className="flex flex-wrap items-center gap-2 text-xs">
        {lead.weak && (
          <span className="rounded-full bg-amber-50 px-2 py-0.5 font-bold text-amber-900 ring-1 ring-amber-200">
            نقطه ضعف: {lead.weak.label} ({num(lead.weak.score)})
          </span>
        )}
        <span className="text-ink-500">سرنخ‌ها:</span>
        {clueIds.map((id) => (
          <button key={id} onClick={() => onClues(clueIds, id)}
            className="rounded-full bg-thread-50 px-2 py-0.5 font-bold text-thread-700 ring-1 ring-thread-200 hover:bg-thread-100">
            #{mid(id)}
          </button>
        ))}
      </div>

      {lead.reply ? <ReplyBox reply={lead.reply} /> : <div className="text-xs text-ink-400">پیش‌نویس پاسخ ساخته نشد.</div>}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ink-50 pt-3">
        <Vote runId={runId} msgId={lead.msg_id} initial={lead.vote ?? 0} />
        <div className="flex items-center gap-3 text-xs">
          <span className="text-ink-400" title="هزینه بررسی این پیام">{usd(lead.equiv_cost_usd)}</span>
          {onCompare && (
            <label className="flex cursor-pointer items-center gap-1 text-ink-600">
              <input type="checkbox" checked={!!compareOn} onChange={onCompare} className="accent-thread-500" /> مقایسه
            </label>
          )}
          <Link to={`/app/runs/${runId}/leads/${lead.msg_id}`} className="font-bold text-ink-700 underline-offset-4 hover:underline">جزئیات ←</Link>
        </div>
      </div>
    </Card>
  );
}
