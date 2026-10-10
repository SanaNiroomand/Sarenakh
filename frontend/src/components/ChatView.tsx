import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../lib/api";
import { mid, shortDate } from "../lib/fmt";
import type { ChatMsg } from "../lib/types";
import { ErrorBox, Loading, cx } from "./ui";

/** The chat around a message; the cited messages are highlighted. */
export function ChatDrawer({ datasetId, center, highlight, onClose }: {
  datasetId: number; center: number; highlight: number[]; onClose: () => void;
}) {
  const [msgs, setMsgs] = useState<ChatMsg[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    api.get<{ messages: ChatMsg[] }>(`/api/datasets/${datasetId}/messages?around=${center}&radius=18`)
      .then((r) => setMsgs(r.messages)).catch((e) => setError(errorText(e)));
  }, [datasetId, center]);

  useEffect(() => {
    if (msgs) refs.current[center]?.scrollIntoView({ block: "center" });
  }, [msgs, center]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const byId = new Map((msgs ?? []).map((m) => [m.msg_id, m]));
  const hl = new Set(highlight);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-ink-900/30" onClick={onClose} role="dialog" aria-modal="true" aria-label="گفتگوی گروه">
      <div className="flex h-full w-full max-w-lg flex-col bg-white" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
          <span className="font-bold">گفتگوی گروه</span>
          <button onClick={onClose} className="text-ink-500 hover:underline">بستن</button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-4 text-sm">
          {error && <ErrorBox message={error} />}
          {!msgs && !error && <Loading />}
          {msgs?.map((m) => {
            const parent = m.reply_to ? byId.get(m.reply_to) : undefined;
            return (
              <div key={m.msg_id} ref={(el) => { refs.current[m.msg_id] = el; }}
                className={cx("rounded-lg px-3 py-2", hl.has(m.msg_id) && "bg-thread-100")}>
                <div className="text-xs text-ink-500"><b className="text-ink-800">{m.author}</b> · #{mid(m.msg_id)} · {shortDate(m.date)}</div>
                {parent && <div title={parent.text} className="truncate text-xs text-ink-400">در پاسخ به {parent.author}: {parent.text}</div>}
                <div dir="auto" className="whitespace-pre-wrap leading-7">{m.text}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
