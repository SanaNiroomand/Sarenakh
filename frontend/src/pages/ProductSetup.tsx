import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Layout } from "../components/Layout";
import { Button, ErrorBox, Field, LinkButton, Loading, Spinner, TextArea, cx } from "../components/ui";
import { api, errorText } from "../lib/api";
import { AXES_FA, AXES_ORDER, num } from "../lib/fmt";
import type { Axes, Product, Profile } from "../lib/types";

const LIST_FIELDS: { key: keyof Profile; label: string }[] = [
  { key: "pain_points", label: "مشکل‌هایی که مشتری دارد" },
  { key: "buying_signals", label: "نشانه‌های اینکه کسی مشتری است" },
  { key: "signal_examples", label: "نمونه پیام‌هایی که مشتری ممکن است بنویسد" },
  { key: "disqualifiers", label: "چه کسانی مشتری نیستند" },
  { key: "facts", label: "اطلاعات محصول (پاسخ‌ها فقط از این‌ها استفاده می‌کنند)" },
];

function AgentChat({ product, onUpdate }: { product: Product; onUpdate: (p: Product) => void }) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  const turn = useCallback(async (message?: string) => {
    setBusy(true);
    setError(null);
    try {
      onUpdate(await api.post<Product>(`/api/products/${product.id}/agent`, message ? { message } : undefined));
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

  const waitingForUser = !product.profile && product.setup_chat.at(-1)?.role === "assistant";
  return (
    <section className="space-y-3">
      {product.setup_chat.map((t, i) => (
        <p key={i} className={cx("whitespace-pre-wrap rounded-xl px-4 py-2 text-sm leading-7",
          t.role === "user" ? "bg-ink-50" : "border border-ink-100")}>
          {t.content}
        </p>
      ))}
      {busy && <p className="flex items-center gap-2 text-sm text-ink-500"><Spinner className="h-4 w-4" /> چند لحظه…</p>}
      {error && <ErrorBox message={error} onRetry={() => turn()} />}
      {waitingForUser && (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (msg.trim()) void turn(msg.trim()); }}>
          <TextArea rows={3} value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="پاسخ شما" aria-label="پاسخ" />
          <div className="flex items-center gap-3">
            <Button type="submit" loading={busy} disabled={!msg.trim()}>ارسال</Button>
            <button type="button" className="text-sm text-ink-500 hover:underline" disabled={busy}
              onClick={() => turn("بسه، با همین اطلاعات پروفایل رو بساز.")}>بدون جواب ادامه بده</button>
          </div>
        </form>
      )}
    </section>
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
    <section className="space-y-4">
      <Field label="نام محصول" value={p.product_name} onChange={(e) => set("product_name", e.target.value)} />
      <label className="block">
        <span className="mb-1.5 block text-sm font-bold">مشتری ایده‌آل</span>
        <TextArea rows={3} value={p.persona} onChange={(e) => set("persona", e.target.value)} />
      </label>
      {LIST_FIELDS.map(({ key, label }) => (
        <label key={key} className="block">
          <span className="mb-1.5 block text-sm font-bold">{label}</span>
          <TextArea rows={Math.min(8, Math.max(3, (p[key] as string[]).length + 1))} value={(p[key] as string[]).join("\n")}
            onChange={(e) => set(key, e.target.value.split("\n") as never)}
            onBlur={(e) => set(key, e.target.value.split("\n").map((s) => s.trim()).filter(Boolean) as never)} />
        </label>
      ))}
      <label className="block">
        <span className="mb-1.5 block text-sm font-bold">لحن پاسخ‌ها</span>
        <TextArea rows={2} value={p.reply_tone} onChange={(e) => set("reply_tone", e.target.value)} />
      </label>
      <div>
        <span className="mb-1.5 block text-sm font-bold">مشتری ایده‌آل از ۰ تا ۱۰</span>
        <div className="space-y-1">
          {AXES_ORDER.map((k) => (
            <label key={k} className="flex items-center gap-3 text-sm">
              <span className="w-28 shrink-0">{AXES_FA[k]}</span>
              <input type="range" min={0} max={10} value={p.ideal_shape[k]} onChange={(e) => setAxis(k, Number(e.target.value))}
                className="flex-1 accent-ink-700" aria-label={AXES_FA[k]} />
              <span className="w-6 text-center">{num(p.ideal_shape[k])}</span>
            </label>
          ))}
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      <div className="flex items-center gap-3">
        <Button variant="outline" onClick={save} loading={busy}>ذخیره</Button>
        {saved && <span className="text-sm text-ink-500">ذخیره شد</span>}
      </div>
    </section>
  );
}

export default function ProductSetup() {
  const { id } = useParams();
  const [product, setProduct] = useState<Product | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const load = useCallback(() => {
    setError(null);
    api.get<Product>(`/api/products/${id}`).then(setProduct).catch((e) => setError(errorText(e)));
  }, [id]);
  useEffect(load, [load]);

  return (
    <Layout>
      {error && <ErrorBox message={error} onRetry={load} />}
      {!product && !error && <Loading />}
      {product && (
        <div className="space-y-8">
          <div>
            <h1 className="text-xl font-bold">{product.profile ? product.name : "معرفی محصول"}</h1>
            {product.source && (
              <p className="mt-1 text-xs text-ink-400">
                اطلاعات از <a href={product.source.url} target="_blank" rel="noopener noreferrer" className="underline">صفحه محصول</a> برداشته شده و فقط برای نمایش است.
              </p>
            )}
          </div>

          {product.setup_chat.length > 0 && <AgentChat product={product} onUpdate={setProduct} />}

          {product.profile && (
            <>
              <section>
                <h2 className="mb-1 font-bold">مشتری ایده‌آل شما</h2>
                <p className="leading-8">{product.profile.persona}</p>
                <button className="mt-2 text-sm text-ink-500 hover:underline" onClick={() => setEditing(!editing)}>
                  {editing ? "بستن" : "ویرایش جزئیات"}
                </button>
              </section>
              {editing && <ProfileEditor product={product} onSaved={setProduct} />}
              <LinkButton to={`/app/products/${product.id}/data`}>ادامه</LinkButton>
            </>
          )}
        </div>
      )}
    </Layout>
  );
}
