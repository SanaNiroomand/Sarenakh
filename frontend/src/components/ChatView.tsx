import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../lib/api";
import { mid, num, shortDate } from "../lib/fmt";
import type { ChatMsg } from "../lib/types";
import { Button, ErrorBox, Loading, cx } from "./ui";

/** The chat around a message, with evidence messages highlighted ("clues"). Rendered as a drawer. */
export function ChatDrawer({ datasetId, center, highlight, onClose }: {
  datasetId: number; center: number; highlight: number[]; onClose: () => void;
}) {
  const [msgs, setMsgs] = useState<ChatMsg[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState(center);
  const refs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    setMsgs(null);
    setError(null);
    api.get<{ messages: ChatMsg[] }>(`/api/datasets/${datasetId}/messages?around=${focus}&radius=18`)
      .then((r) => setMsgs(r.messages)).catch((e) => setError(errorText(e)));
  }, [datasetId, focus]);

  useEffect(() => {
    if (msgs) refs.current[focus]?.scrollIntoView({ block: "center" });
  }, [msgs, focus]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const byId = new Map((msgs ?? []).map((m) => [m.msg_id, m]));
  const hl = new Set(highlight);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-ink-900/40" onClick={onClose} role="dialog" aria-modal="true" aria-label="گفتگوی گروه">
      <div className="flex h-full w-full max-w-lg flex-col bg-paper shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-ink-100 bg-white px-4 py-3">
          <div>
            <div className="font-extrabold">گفتگوی گروه</div>
            <div className="text-xs text-ink-500">پیام‌های نارنجی سرنخ‌هایی هستند که عامل به آن‌ها استناد کرده</div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="بستن">✕</Button>
        </div>
        {highlight.length > 1 && (
          <div className="flex flex-wrap gap-1.5 border-b border-ink-100 bg-white px-4 py-2">
            {highlight.map((id) => (
              <button key={id} onClick={() => setFocus(id)}
                className={cx("rounded-full px-2 py-0.5 text-xs font-bold ring-1", id === focus ? "bg-thread-500 text-white ring-thread-500" : "bg-thread-50 text-thread-700 ring-thread-200")}>
                #{mid(id)}
              </button>
            ))}
          </div>
        )}
        <div className="flex-1 space-y-2 overflow-y-auto p-4">
          {error && <ErrorBox message={error} />}
          {!msgs && !error && <Loading />}
          {msgs?.map((m) => {
            const parent = m.reply_to ? byId.get(m.reply_to) : undefined;
            const isClue = hl.has(m.msg_id);
            return (
              <div key={m.msg_id} ref={(el) => { refs.current[m.msg_id] = el; }}
                className={cx("rounded-2xl border px-3 py-2 text-sm", isClue ? "border-thread-300 bg-thread-50 ring-2 ring-thread-200" : "border-ink-100 bg-white",
                  m.msg_id === focus && "ring-thread-400")}>
                <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                  <span className="font-bold text-ink-800">{m.author}</span>
                  <span className="text-ink-400">#{mid(m.msg_id)} · {shortDate(m.date)}</span>
                </div>
                {m.reply_to && (
                  <div className="mb-1 border-s-2 border-ink-200 ps-2 text-xs text-ink-500">
                    ↩ {parent ? <><b>{parent.author}:</b> {parent.text.slice(0, 90)}{parent.text.length > 90 ? "…" : ""}</> : `پاسخ به #${num(m.reply_to)}`}
                  </div>
                )}
                {m.forwarded_from && <div className="mb-1 text-xs text-ink-400">بازارسال از {m.forwarded_from}</div>}
                <div dir="auto" className="whitespace-pre-wrap leading-7 text-ink-900">{m.text}</div>
                {isClue && <div className="mt-1 text-xs font-bold text-thread-700">🧶 سرنخ</div>}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
