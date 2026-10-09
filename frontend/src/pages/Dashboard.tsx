import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Layout } from "../components/Layout";
import { Button, ErrorBox, LinkButton, Loading } from "../components/ui";
import { ApiError, api, errorText } from "../lib/api";
import { STATUS_FA, ago, num } from "../lib/fmt";
import { startSampleRun } from "../lib/flow";
import type { RunSummary, SampleProduct } from "../lib/types";

const shortName = (name: string) => name.split("—")[0].trim();

export function SampleButtons() {
  const nav = useNavigate();
  const [samples, setSamples] = useState<SampleProduct[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.get<SampleProduct[]>("/api/products/samples").then(setSamples).catch(() => undefined); }, []);
  const go = async (key: string) => {
    setBusy(key);
    setError(null);
    try {
      nav(`/app/runs/${await startSampleRun(key)}`);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 409 ? `${e.message} (از فهرست اجراها آن را باز کنید)` : errorText(e));
      setBusy(null);
    }
  };
  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {samples.map((s) => (
          <Button key={s.key} variant="outline" onClick={() => go(s.key)} loading={busy === s.key} disabled={!!busy}>
            {s.emoji} {shortName(s.name)}
          </Button>
        ))}
      </div>
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
    </div>
  );
}

export default function Dashboard() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => { setError(null); api.get<RunSummary[]>("/api/runs").then(setRuns).catch((e) => setError(errorText(e))); };
  useEffect(load, []);

  return (
    <Layout>
      <div className="mb-8">
        <LinkButton to="/app/new">جستجوی تازه</LinkButton>
      </div>

      <section className="mb-10">
        <h2 className="mb-1 font-bold">امتحان با داده نمونه</h2>
        <p className="mb-3 text-sm text-ink-500">یک گروه تلگرام نمونه درباره برنامه‌نویسی. یکی از محصول‌ها را انتخاب کنید.</p>
        <SampleButtons />
        <p className="mt-3 text-xs text-ink-400">اطلاعات این دو محصول از سایت کوئرا و باسلام است و فقط برای نمایش استفاده شده.</p>
      </section>

      <section>
        <h2 className="mb-3 font-bold">اجراهای قبلی</h2>
        {error && <ErrorBox message={error} onRetry={load} />}
        {!runs && !error && <Loading />}
        {runs && runs.length === 0 && <p className="text-sm text-ink-500">هنوز اجرایی ندارید.</p>}
        {runs && runs.length > 0 && (
          <ul className="divide-y divide-ink-100 border-y border-ink-100">
            {runs.map((r) => (
              <li key={r.id}>
                <Link to={`/app/runs/${r.id}`} className="flex items-center justify-between gap-3 py-3 hover:bg-ink-50">
                  <span className="truncate">{shortName(r.product?.name ?? "")}</span>
                  <span className="shrink-0 text-sm text-ink-500">
                    {r.status === "done" ? `${num(r.leads ?? 0)} سرنخ` : STATUS_FA[r.status]} · {ago(r.created_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Layout>
  );
}
