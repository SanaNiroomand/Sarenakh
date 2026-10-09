import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Layout } from "../components/Layout";
import { SampleSource } from "../components/SampleSource";
import { Button, Card, ErrorBox, SectionTitle, Steps, TextArea } from "../components/ui";
import { api, errorText } from "../lib/api";
import type { Product, SampleProduct } from "../lib/types";

export default function NewSearch() {
  const nav = useNavigate();
  const [samples, setSamples] = useState<SampleProduct[]>([]);
  const [mine, setMine] = useState<Product[]>([]);
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<SampleProduct[]>("/api/products/samples").then(setSamples).catch(() => undefined);
    api.get<Product[]>("/api/products").then(setMine).catch(() => undefined);
  }, []);

  const fromSample = async (key: string) => {
    setBusy(key);
    setError(null);
    try {
      const p = await api.post<Product>(`/api/products/sample/${key}`);
      nav(`/app/products/${p.id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(null);
    }
  };

  const create = async () => {
    setBusy("own");
    setError(null);
    try {
      const p = await api.post<Product>("/api/products", { description: desc.trim() });
      nav(`/app/products/${p.id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(null);
    }
  };

  return (
    <Layout>
      <Steps current={1} />
      <h1 className="mb-1 text-2xl font-extrabold">چه چیزی می‌فروشید؟</h1>
      <p className="mb-6 text-ink-500">با زبان ساده توضیح دهید. عامل پروفایل یکی دو سوال کوتاه می‌پرسد و مشتری ایده‌آل را تعریف می‌کند.</p>

      <Card className="mb-6">
        <label htmlFor="desc" className="mb-2 block font-bold">توضیح محصول</label>
        <TextArea id="desc" rows={5} value={desc} onChange={(e) => setDesc(e.target.value)}
          placeholder="مثلا: یه دوره آنلاین طراحی UI داریم برای کسایی که از گرافیک می‌خوان وارد طراحی محصول بشن. ۸ هفته‌ست، منتور داره و قیمتش ۳ میلیون تومنه…" />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-ink-400">قیمت، مخاطب و ویژگی‌های اصلی را بنویسید؛ پاسخ‌ها فقط از همین واقعیت‌ها استفاده می‌کنند.</span>
          <Button onClick={create} loading={busy === "own"} disabled={desc.trim().length < 20 || !!busy}>ادامه با عامل پروفایل ←</Button>
        </div>
      </Card>

      {error && <div className="mb-4"><ErrorBox message={error} /></div>}

      <SectionTitle title="یا با یک محصول واقعی نمونه شروع کنید" sub="پروفایل آماده دارند؛ می‌توانید ویرایششان کنید." />
      <div className="mb-3"><SampleSource samples={samples} /></div>
      <div className="mb-8 grid gap-3 sm:grid-cols-2">
        {samples.map((s) => (
          <button key={s.key} onClick={() => fromSample(s.key)} disabled={!!busy}
            className="flex items-start gap-3 rounded-2xl border border-ink-100 bg-white p-4 text-start transition hover:border-thread-300 disabled:opacity-60">
            <span className="text-2xl" aria-hidden>{s.emoji}</span>
            <span>
              <span className="block font-extrabold">{s.name}</span>
              <span className="mt-1 block text-sm leading-6 text-ink-500">{s.description.slice(0, 140)}…</span>
              {busy === s.key && <span className="mt-1 block text-xs text-thread-700">در حال آماده‌سازی…</span>}
            </span>
          </button>
        ))}
      </div>

      {mine.length > 0 && (
        <>
          <SectionTitle title="محصولات قبلی شما" />
          <div className="space-y-2">
            {mine.map((p) => (
              <Link key={p.id} to={p.profile ? `/app/products/${p.id}/data` : `/app/products/${p.id}`}
                className="flex items-center justify-between rounded-xl border border-ink-100 bg-white px-4 py-3 hover:border-ink-300">
                <span className="truncate font-bold">{p.name}</span>
                <span className="text-xs text-ink-500">{p.profile ? "پروفایل آماده ←" : "پروفایل ناتمام ←"}</span>
              </Link>
            ))}
          </div>
        </>
      )}
    </Layout>
  );
}
