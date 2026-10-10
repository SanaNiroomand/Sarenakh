import { useEffect, useMemo, useRef } from "react";
import { mid, usd } from "../lib/fmt";
import type { AgentEvent } from "../lib/types";
import { Spinner, cx } from "./ui";

type Block =
  | { kind: "stage"; key: string; ev: AgentEvent }
  | { kind: "thread"; key: string; msgId: number; head: AgentEvent | null; steps: AgentEvent[]; verdict: AgentEvent | null };

/** Groups the flat event stream: stage lines, plus one "thread" card per followed candidate. */
function toBlocks(events: AgentEvent[]): Block[] {
  const blocks: Block[] = [];
  const threads = new Map<number, Extract<Block, { kind: "thread" }>>();
  for (const ev of events) {
    if (ev.msg_id == null || ev.type === "stage") {
      blocks.push({ kind: "stage", key: `s${ev.seq}`, ev });
      continue;
    }
    let t = threads.get(ev.msg_id);
    if (!t) {
      t = { kind: "thread", key: `t${ev.msg_id}`, msgId: ev.msg_id, head: null, steps: [], verdict: null };
      threads.set(ev.msg_id, t);
      blocks.push(t);
    }
    if (ev.type === "investigate") t.head = ev;
    else if (ev.type === "verdict") t.verdict = ev;
    else t.steps.push(ev);
  }
  return blocks;
}

const STEP_TONE: Record<string, string> = {
  tool: "text-ink-600",
  critic: "text-purple-800",
  draft: "text-thread-700",
  memory: "text-sky-800",
  error: "text-red-700",
};

export function LiveFeed({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const blocks = useMemo(() => toBlocks(events), [events]);
  const end = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
    if (nearBottom) end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [events.length]);

  return (
    <div ref={box} className="max-h-[70vh] overflow-y-auto pe-1" aria-live="polite" aria-label="گزارش زنده عامل">
      <ol className="relative ms-3 border-s-2 border-dashed border-thread-300 ps-5">
        {blocks.map((b) =>
          b.kind === "stage" ? (
            <li key={b.key} className="relative py-1.5">
              <span className="absolute -start-[27px] top-3 h-3 w-3 rounded-full border-2 border-white bg-thread-400" aria-hidden />
              <div title={b.ev.text} className={cx("truncate text-sm leading-7", b.ev.type === "done" ? "font-extrabold text-ink-900" : "text-ink-700",
                b.ev.type === "error" && "text-red-700")}>
                {b.ev.text}
                {b.ev.cost_usd > 0 && <span className="ms-2 text-xs text-ink-400">({usd(b.ev.cost_usd)})</span>}
              </div>
            </li>
          ) : (
            <ThreadCard key={b.key} b={b} running={running} />
          ),
        )}
        {running && (
          <li className="relative py-2 text-sm text-ink-500">
            <span className="absolute -start-[29px] top-2.5 rounded-full bg-paper p-0.5 text-thread-500"><Spinner className="h-4 w-4" /></span>
            عامل در حال دنبال کردن رشته‌ها…
          </li>
        )}
      </ol>
      <div ref={end} />
    </div>
  );
}

function ThreadCard({ b, running }: { b: Extract<Block, { kind: "thread" }>; running: boolean }) {
  const d = b.verdict?.data ?? {};
  const decision = d.decision as string | undefined;
  const tone = decision === "lead" ? "border-thread-300 bg-thread-50/70" : decision === "watch" ? "border-sky-200 bg-sky-50/50"
    : decision ? "border-ink-100 bg-white" : "border-ink-200 bg-white";
  return (
    <li className="relative py-1.5">
      <span className={cx("absolute -start-[29px] top-4 flex h-4 w-4 items-center justify-center rounded-full border-2 border-white text-[9px]",
        decision === "lead" ? "bg-thread-500" : decision ? "bg-ink-300" : "bg-ink-900")} aria-hidden />
      <div className={cx("min-w-0 rounded-xl border px-3 py-2", tone)}>
        <div title={b.head?.text} className="truncate text-sm font-bold text-ink-900">{b.head?.text ?? `پیام #${mid(b.msgId)}`}</div>
        {b.steps.length > 0 && (
          <ul className="mt-1 space-y-0.5 border-s border-ink-100 ps-3">
            {b.steps.map((s) => (
              <li key={s.seq} title={s.text} className={cx("truncate text-[13px] leading-6", STEP_TONE[s.type] ?? "text-ink-600")}>
                {s.text}{s.data?.cached && <span className="ms-1 text-xs text-ink-400">(از حافظه)</span>}
              </li>
            ))}
          </ul>
        )}
        {b.verdict ? (
          <div title={b.verdict.text} className={cx("mt-1.5 truncate text-sm font-bold", decision === "lead" ? "text-thread-700" : "text-ink-600")}>
            {b.verdict.text}
            {(d.equiv_cost ?? 0) > 0 && <span className="ms-2 text-xs font-normal text-ink-400">هزینه این رشته: {usd(d.equiv_cost)}</span>}
          </div>
        ) : running ? (
          <div className="mt-1 flex items-center gap-2 text-xs text-ink-400"><Spinner className="h-3 w-3" /> در حال بررسی…</div>
        ) : null}
      </div>
    </li>
  );
}
