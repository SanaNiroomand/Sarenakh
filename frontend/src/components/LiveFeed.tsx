import { useEffect, useMemo, useRef } from "react";
import { mid } from "../lib/fmt";
import type { AgentEvent } from "../lib/types";
import { Spinner, cx } from "./ui";

type Block =
  | { kind: "stage"; key: string; ev: AgentEvent }
  | { kind: "thread"; key: string; msgId: number; head: AgentEvent | null; steps: AgentEvent[]; verdict: AgentEvent | null };

/** Groups the flat event stream: stage lines, plus one block per person the agent follows. */
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

function Line({ text, className }: { text: string; className?: string }) {
  return <div title={text} className={cx("truncate", className)}>{text}</div>;
}

export function LiveFeed({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const blocks = useMemo(() => toBlocks(events), [events]);
  const end = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) end.current?.scrollIntoView({ block: "end" });
  }, [events.length]);

  return (
    <div ref={box} className="max-h-[70vh] space-y-3 overflow-y-auto text-sm" aria-live="polite" aria-label="گزارش کار عامل">
      {blocks.map((b) =>
        b.kind === "stage" ? (
          <Line key={b.key} text={b.ev.text} className={b.ev.type === "error" ? "text-red-700" : "text-ink-500"} />
        ) : (
          <div key={b.key}>
            <Line text={b.head?.text ?? `پیام #${mid(b.msgId)}`} />
            {b.steps.map((s) => <Line key={s.seq} text={s.text} className="ps-4 text-ink-500" />)}
            {b.verdict
              ? <Line text={b.verdict.text} className="ps-4 font-bold" />
              : running && <div className="ps-4 text-ink-400">…</div>}
          </div>
        ),
      )}
      {running && <div className="flex items-center gap-2 text-ink-400"><Spinner className="h-4 w-4" /> در حال کار…</div>}
      <div ref={end} />
    </div>
  );
}
