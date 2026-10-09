// All numbers render with Persian digits via the "Vazirmatn UI FD" font; Intl adds Persian separators.

const nf = (min: number, max: number) =>
  new Intl.NumberFormat("fa-IR", { minimumFractionDigits: min, maximumFractionDigits: max });

export const num = (n: number | null | undefined, digits = 0) =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : nf(0, digits).format(n);

const idFmt = new Intl.NumberFormat("fa-IR", { useGrouping: false });
/** Message ids: Persian digits, never thousands separators. */
export const mid = (n: number) => idFmt.format(n);

export function usd(n: number | null | undefined, opts: { digits?: number } = {}): string {
  if (n === null || n === undefined) return "—";
  if (n === 0) return "۰ دلار";
  if (n < 0.0001) return "کمتر از ۰٫۰۰۰۱ دلار";
  const digits = opts.digits ?? (n < 0.01 ? 4 : n < 1 ? 3 : 2);
  return `${nf(0, digits).format(n)} دلار`;
}

export const pct = (x: number) => `${nf(0, 0).format(Math.round(x * 100))}٪`;

export const fit10 = (x: number | null | undefined) => (x === null || x === undefined ? "—" : `${nf(0, 1).format(x)} از ۱۰`);

export function shortDate(iso: string): string {
  // "2026-10-02T10:20:31" -> "۱۰ مهر، ۱۰:۲۰" (Persian calendar)
  const d = new Date(iso.length === 19 ? iso + "+03:30" : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("fa-IR", {
    month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tehran",
  }).format(d);
}

export function ago(unixSeconds: number): string {
  const s = Math.max(1, Math.round(Date.now() / 1000 - unixSeconds));
  if (s < 60) return "لحظاتی پیش";
  if (s < 3600) return `${num(Math.floor(s / 60))} دقیقه پیش`;
  if (s < 86400) return `${num(Math.floor(s / 3600))} ساعت پیش`;
  return `${num(Math.floor(s / 86400))} روز پیش`;
}

export const TEMP = {
  hot: { label: "داغ", icon: "🔥", cls: "bg-red-50 text-red-800 ring-red-200" },
  warm: { label: "گرم", icon: "☀️", cls: "bg-amber-50 text-amber-900 ring-amber-200" },
  cold: { label: "سرد", icon: "❄️", cls: "bg-sky-50 text-sky-900 ring-sky-200" },
} as const;

export const AXES_FA: Record<string, string> = {
  need: "نیاز",
  product_fit: "تناسب محصول",
  urgency: "فوریت",
  buying_intent: "قصد خرید",
  reachability: "دسترس‌پذیری",
  confidence: "اطمینان",
};

export const AXES_ORDER = ["need", "product_fit", "buying_intent", "urgency", "reachability", "confidence"] as const;

export const TIMING_FA = { browsing: "در حال گشتن", considering: "در حال سنجیدن", ready: "آماده خرید" } as const;
export const ACTION_FA = { reply: "پاسخ عمومی", dm: "پیام خصوصی", watch: "زیر نظر", skip: "رد" } as const;
export const SIGNAL_FA: Record<string, string> = {
  question: "سوال", complaint: "شکایت", purchase_intent: "قصد خرید", noise: "بی‌ربط",
};
export const DECISION_FA: Record<string, string> = {
  lead: "سرنخ واقعی", watch: "زیر نظر", rejected: "رد شد", skipped: "کنار رفت", pending: "بررسی نشد",
};
export const STATUS_FA: Record<string, string> = {
  queued: "در صف", running: "در حال اجرا", done: "تمام شد", failed: "خطا", stopped: "متوقف شد",
};
