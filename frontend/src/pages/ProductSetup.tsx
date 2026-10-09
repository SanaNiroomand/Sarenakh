import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { LeadRadar } from "../components/charts";
import { Layout } from "../components/Layout";
import { Button, Card, ErrorBox, Field, LinkButton, Loading, SectionTitle, Spinner, Steps, TextArea, cx } from "../components/ui";
import { api, errorText } from "../lib/api";
import { AXES_FA, AXES_ORDER, num, usd } from "../lib/fmt";
import type { Axes, Product, Profile } from "../lib/types";

const LIST_FIELDS: { key: keyof Profile; label: string; hint: string }[] = [
  { key: "pain_points", label: "دردها و مشکلات", hint: "هر مورد در یک خط" },
  { key: "buying_signals", label: "نشانه‌های خرید", hint: "هر مورد در یک خط" },
  { key: "signal_examples", label: "نمونه پیام مشتری (برای پیش‌فیلتر معنایی)", hint: "فارسی، فینگلیش و انگلیسی‌قاطی؛ هر پیام در یک خط" },
  { key: "disqualifiers", label: "ردکننده‌ها", hint: "چه کسانی مشتری نیستند؛ هر مورد در یک خط" },
  { key: "facts", label: "واقعیت‌های محصول", hint: "تنها چیزهایی که پاسخ‌ها مجازند درباره محصول بگویند؛ هر مورد در یک خط" },
];

function AgentChat({ product, onUpdate }: { product: Product; onUpdate: (p: Product) => void }) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);
  const end = useRef<HTMLDivElement>(null);

  const turn = useCallback(async (message?: string) => {
    setBusy(true);
    setError(null);
    try {
      const p = await api.post<Product>(`/api/products/${product.id}/agent`, message ? { message } : undefined);
      onUpdate(p);
      setMsg("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }, [product.id, onUpdate]);

  useEffect(() => {
    const chat = product.setup_chat;
    if (!started.current && !product.profile && chat.length > 0 && chat[chat.length - 1].role === "user") {
      started.current = true;
      void turn();
    }
  }, [product, turn]);

  useEffect(() => end.current?.scrollIntoView({ block: "nearest" }), [product.setup_chat.length, busy]);

  const waitingForUser = !product.profile && product.setup_chat.at(-1)?.role === "assistant";
  return (
    <Card>
      <SectionTitle title="گفتگو با عامل پروفایل" sub="حداکثر دو سوال؛ هر وقت خواستید بگویید «بسه»." />
      <div className="max-h-96 space-y-3 overflow-y-auto">
        {product.setup_chat.map((t, i) => (
          <div key={i} className={cx("max-w-[90%] rounded-2xl px-4 py-2.5 text-sm leading-7",
            t.role === "user" ? "ms-auto bg-ink-900 text-white" : "bg-thread-50 text-ink-900 ring-1 ring-thread-200")}>
            {t.role === "assistant" && <div className="mb-0.5 text-xs font-bold text-thread-700">🧶 عامل پروفایل</div>}
            <div className="whitespace-pre-wrap">{t.content}</div>
          </div>
        ))}
        {busy && <div className="flex items-center gap-2 text-sm text-ink-500"><Spinner className="h-4 w-4" /> عامل در حال فکر کردن است…</div>}
        <div ref={end} />
      </div>
      {error && <div className="mt-3"><ErrorBox message={error} onRetry={() => turn()} /></div>}
      {waitingForUser && (
        <form className="mt-4 space-y-2" onSubmit={(e) => { e.preventDefault(); if (msg.trim()) void turn(msg.trim()); }}>
          <TextArea rows={3} value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="پاسخ شما…" aria-label="پاسخ به عامل" />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" loading={busy} disabled={!msg.trim()}>ارسال</Button>
            <Button type="button" variant="outline" disabled={busy} onClick={() => turn("بسه، با همین اطلاعات پروفایل رو بساز.")}>بسه، پروفایل را بساز</Button>
          </div>
        </form>
      )}
      {product.turn_cost_usd !== undefined && <div className="mt-2 text-xs text-ink-400">هزینه این نوبت: {usd(product.turn_cost_usd)}</div>}
    </Card>
  );
}

function ProfileEditor({ product, onSaved }: { product: Product; onSaved: (p: Product) => void }) {
  const [p, setP] = useState<Profile>(product.profile!);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setP(product.profile!), [product.profile]);

  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => { setP({ ...p, [k]: v }); setSaved(false); };
  const setAxis = (k: keyof Axes, v: number) => set("ideal_shape", { ...p.ideal_shape, [k]: v });
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.put<Product>(`/api/products/${product.id}/profile`, p));
      setSaved(true);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <SectionTitle title="پروفایل مشتری ایده‌آل" sub="هر چیزی را که لازم است ویرایش کنید؛ عامل‌ها دقیقا از همین استفاده می‌کنند." />
      <div className="space-y-4">
        <Field label="نام محصول" value={p.product_name} onChange={(e) => set("product_name", e.target.value)} />
        <Field label="یک جمله درباره محصول" value={p.one_liner} onChange={(e) => set("one_liner", e.target.value)} />
        <label className="block">
          <span className="mb-1.5 block text-sm font-bold">مشتری ایده‌آل</span>
          <TextArea rows={3} value={p.persona} onChange={(e) => set("persona", e.target.value)} />
        </label>
        {LIST_FIELDS.map(({ key, label, hint }) => (
          <label key={key} className="block">
            <span className="mb-1.5 block text-sm font-bold">{label}</span>
            <TextArea rows={Math.min(8, Math.max(3, (p[key] as string[]).length + 1))} value={(p[key] as string[]).join("\n")}
              onChange={(e) => set(key, e.target.value.split("\n") as never)}
              onBlur={(e) => set(key, e.target.value.split("\n").map((s) => s.trim()).filter(Boolean) as never)} />
            <span className="mt-1 block text-xs text-ink-400">{hint}</span>
          </label>
        ))}
        <label className="block">
          <span className="mb-1.5 block text-sm font-bold">لحن پاسخ‌ها</span>
          <TextArea rows={2} value={p.reply_tone} onChange={(e) => set("reply_tone", e.target.value)} />
        </label>
        <div>
          <div className="mb-1 text-sm font-bold">شکل مشتری ایده‌آل (خط‌چین روی نمودار سرنخ‌ها)</div>
          <div className="grid items-center gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              {AXES_ORDER.map((k) => (
                <label key={k} className="flex items-center gap-3 text-sm">
                  <span className="w-28 shrink-0">{AXES_FA[k]}</span>
                  <input type="range" min={0} max={10} value={p.ideal_shape[k]} onChange={(e) => setAxis(k, Number(e.target.value))}
                    className="flex-1 accent-thread-500" aria-label={AXES_FA[k]} />
                  <span className="w-6 text-center font-bold">{num(p.ideal_shape[k])}</span>
                </label>
              ))}
            </div>
            <LeadRadar series={[]} ideal={p.ideal_shape} height={220} compact />
          </div>
        </div>
      </div>
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Button onClick={save} loading={busy} variant="outline">ذخیره تغییرات</Button>
        {saved && <span className="text-sm text-emerald-700">✓ ذخیره شد</span>}
      </div>
    </Card>
  );
}

export default function ProductSetup() {
  const { id } = useParams();
  const nav = useNavigate();
  const [product, setProduct] = useState<Product | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setError(null);
    api.get<Product>(`/api/products/${id}`).then(setProduct).catch((e) => setError(errorText(e)));
  }, [id]);
  useEffect(load, [load]);

  return (
    <Layout>
      <Steps current={1} />
      {error && <ErrorBox message={error} onRetry={load} />}
      {!product && !error && <Loading />}
      {product && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-extrabold">{product.name}</h1>
              <p className="text-sm text-ink-500">{product.profile ? "پروفایل آماده است. بررسی کنید و ادامه دهید." : "عامل در حال ساختن پروفایل مشتری است."}</p>
              {product.source && (
                <p className="mt-1 text-xs text-ink-400">
                  محصول واقعی نمونه — واقعیت‌ها از <a href={product.source.url} target="_blank" rel="noopener noreferrer" className="underline" dir="ltr">صفحه محصول</a> (بررسی‌شده در {product.source.checked_at})؛ صرفا برای نمایش و بدون وابستگی.
                </p>
              )}
            </div>
            {product.profile && <Button variant="thread" onClick={() => nav(`/app/products/${product.id}/data`)}>ادامه: پیام‌های گروه ←</Button>}
          </div>
          {product.setup_chat.length > 0 && <AgentChat product={product} onUpdate={setProduct} />}
          {product.profile && <ProfileEditor product={product} onSaved={setProduct} />}
          {product.profile && (
            <div className="flex justify-end">
              <LinkButton to={`/app/products/${product.id}/data`} variant="thread" size="lg">ادامه: پیام‌های گروه ←</LinkButton>
            </div>
          )}
        </div>
      )}
    </Layout>
  );
}
