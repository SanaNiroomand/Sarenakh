import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Layout } from "../components/Layout";
import { Button, ErrorBox, TextArea } from "../components/ui";
import { api, errorText } from "../lib/api";
import type { Product, SampleProduct } from "../lib/types";

const shortName = (name: string) => name.split("—")[0].trim();

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

  const open = async (key: string, call: () => Promise<Product>) => {
    setBusy(key);
    setError(null);
    try {
      nav(`/app/products/${(await call()).id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(null);
    }
  };

  return (
    <Layout>
      <h1 className="text-xl font-bold">چه چیزی می‌فروشید؟</h1>
      <p className="mb-3 mt-1 text-sm text-ink-500">با زبان ساده بنویسید: چه چیزی، برای چه کسی، و قیمتش.</p>
      <TextArea rows={5} value={desc} onChange={(e) => setDesc(e.target.value)} aria-label="توضیح محصول"
        placeholder="مثلا: دوره آنلاین طراحی UI برای تازه‌کارها، ۳ میلیون تومان" />
      <div className="mt-3">
        <Button onClick={() => open("own", () => api.post<Product>("/api/products", { description: desc.trim() }))}
          loading={busy === "own"} disabled={desc.trim().length < 20 || !!busy}>ادامه</Button>
      </div>
      {error && <div className="mt-4"><ErrorBox message={error} /></div>}

      <section className="mt-10">
        <h2 className="mb-3 text-sm text-ink-500">یا یکی از محصولات نمونه:</h2>
        <div className="flex flex-wrap gap-2">
          {samples.map((s) => (
            <Button key={s.key} variant="outline" loading={busy === s.key} disabled={!!busy}
              onClick={() => open(s.key, () => api.post<Product>(`/api/products/sample/${s.key}`))}>
              {s.emoji} {shortName(s.name)}
            </Button>
          ))}
        </div>
      </section>

      {mine.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-2 text-sm text-ink-500">محصولات قبلی شما:</h2>
          <ul className="divide-y divide-ink-100 border-y border-ink-100">
            {mine.map((p) => (
              <li key={p.id}>
                <Link to={p.profile ? `/app/products/${p.id}/data` : `/app/products/${p.id}`}
                  className="block truncate py-2.5 hover:bg-ink-50">{p.profile ? shortName(p.name) : "محصول ناتمام"}</Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Layout>
  );
}
