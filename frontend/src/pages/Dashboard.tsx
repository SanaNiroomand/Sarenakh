import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Layout } from "../components/Layout";
import { SampleSource } from "../components/SampleSource";
import { Badge, Button, Card, Empty, ErrorBox, LinkButton, Loading, SectionTitle } from "../components/ui";
import { ApiError, api, errorText } from "../lib/api";
import { useAuth } from "../lib/auth";
import { STATUS_FA, ago, num, usd } from "../lib/fmt";
import { startSampleRun } from "../lib/flow";
import type { RunSummary, SampleProduct } from "../lib/types";

export function SampleButtons({ compact }: { compact?: boolean }) {
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
    <div className="space-y-3">
      <div className={compact ? "flex flex-wrap gap-2" : "grid gap-3 sm:grid-cols-2"}>
        {samples.map((s) => (
          <button key={s.key} onClick={() => go(s.key)} disabled={!!busy}
            className="group flex items-start gap-3 rounded-2xl border border-thread-200 bg-white p-4 text-start transition hover:border-thread-400 hover:bg-thread-50 disabled:opacity-60">
            <span className="text-2xl" aria-hidden>{s.emoji}</span>
            <span className="flex-1">
              <span className="block font-extrabold text-ink-900">⚡ {s.name}</span>
              <span className="mt-0.5 block text-sm text-ink-500">{s.pitch}</span>
              <span className="mt-2 block text-xs font-bold text-thread-700">{busy === s.key ? "در حال شروع…" : "اجرا روی گفتگوی نمونه ←"}</span>
            </span>
          </button>
        ))}
      </div>
      {error && <ErrorBox message={error} />}
      {!compact && <SampleSource samples={samples} />}
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => { setError(null); api.get<RunSummary[]>("/api/runs").then(setRuns).catch((e) => setError(errorText(e))); };
  useEffect(load, []);

  return (
    <Layout>
      {params.get("welcome") && (
        <div className="mb-5 rounded-2xl bg-ink-900 px-5 py-4 text-white">
          <div className="font-extrabold">خوش آمدید{user?.name ? `، ${user.name}` : ""}! 👋</div>
          <div className="mt-1 text-sm text-ink-200">سریع‌ترین راه: یکی از محصولات نمونه را بزنید تا عامل را روی یک گروه برنامه‌نویسی واقعی‌نما ببینید.</div>
        </div>
      )}

      <Card className="mb-6 border-thread-200 bg-gradient-to-l from-thread-50 to-white">
        <SectionTitle title="امتحان سریع با داده نمونه" sub="دو محصول واقعی ایرانی روی گروه «پایتونیست‌های ایران» (۳۹۱ پیام فارسی، فینگلیش و انگلیسی‌قاطی) — یک کلیک، کمتر از یک دقیقه." />
        <SampleButtons />
      </Card>

      <div className="mb-8 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-ink-100 bg-white p-5">
        <div>
          <div className="font-extrabold">محصول خودتان را دارید؟</div>
          <div className="text-sm text-ink-500">محصول را توصیف کنید، پیام‌های گروه را بدهید و بودجه تعیین کنید.</div>
        </div>
        <LinkButton to="/app/new" variant="primary">🧶 جستجوی تازه</LinkButton>
      </div>

      <SectionTitle title="اجراهای شما" action={<Button size="sm" variant="ghost" onClick={load}>↻ تازه‌سازی</Button>} />
      {error && <ErrorBox message={error} onRetry={load} />}
      {!runs && !error && <Loading />}
      {runs && runs.length === 0 && (
        <Empty title="هنوز اجرایی ندارید">با یکی از دکمه‌های نمونه بالا شروع کنید؛ نتیجه اینجا ذخیره می‌شود.</Empty>
      )}
      {runs && runs.length > 0 && (
        <div className="space-y-2">
          {runs.map((r) => (
            <Link key={r.id} to={`/app/runs/${r.id}`}
              className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-ink-100 bg-white px-4 py-3 transition hover:border-ink-300">
              <div className="min-w-0">
                <div className="truncate font-bold text-ink-900">{r.product?.name}</div>
                <div className="truncate text-xs text-ink-500">{r.dataset?.name} · {ago(r.created_at)}</div>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <Badge className={r.status === "done" ? "bg-emerald-50 text-emerald-800 ring-emerald-200" : r.status === "failed" ? "bg-red-50 text-red-800 ring-red-200" : "bg-amber-50 text-amber-900 ring-amber-200"}>
                  {STATUS_FA[r.status]}
                </Badge>
                <span className="font-bold">{num(r.leads ?? 0)} سرنخ</span>
                <span className="text-ink-500">{usd(r.cost_usd)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </Layout>
  );
}
