import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Layout } from "../components/Layout";
import { Button, ErrorBox, Loading, TextArea, cx } from "../components/ui";
import { api, errorText } from "../lib/api";
import { num, usd } from "../lib/fmt";
import { BUDGET_OPTIONS, getConfig, type PublicConfig } from "../lib/flow";
import type { Dataset, Product, RunSummary } from "../lib/types";

type Source = "sample" | "x" | "upload" | "paste";
const SOURCES: [Source, string][] = [
  ["sample", "داده نمونه"], ["x", "ایکس (توییتر)"], ["upload", "فایل خروجی تلگرام"], ["paste", "متن کپی‌شده"],
];
const POST_OPTIONS = [50, 100, 200, 300];

export default function DataStep() {
  const { id } = useParams();
  const nav = useNavigate();
  const [product, setProduct] = useState<Product | null>(null);
  const [source, setSource] = useState<Source>("sample");
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [pasted, setPasted] = useState("");
  const [budget, setBudget] = useState(0.25);
  const [maxBudget, setMaxBudget] = useState(1);
  const [xcfg, setXcfg] = useState<PublicConfig["x"] | null>(null);
  const [posts, setPosts] = useState(100);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<Product>(`/api/products/${id}`).then(setProduct).catch((e) => setError(errorText(e)));
    getConfig().then((c) => {
      setBudget(c.default_run_budget_usd);
      setMaxBudget(c.max_run_budget_usd);
      setXcfg(c.x);
    }).catch(() => undefined);
  }, [id]);

  const load = async (key: string, call: () => Promise<Dataset>) => {
    setBusy(key);
    setError(null);
    try { setDataset(await call()); } catch (e) { setError(errorText(e)); } finally { setBusy(null); }
  };

  useEffect(() => {
    setDataset(null);
    setError(null);
    if (source === "sample") void load("sample", () => api.get<Dataset>("/api/datasets/sample"));
  }, [source]);

  const upload = (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    void load("upload", () => api.post<Dataset>("/api/datasets/upload", fd));
  };

  const start = async () => {
    if (!dataset || !product) return;
    setBusy("run");
    setError(null);
    try {
      const run = await api.post<RunSummary>("/api/runs", { product_id: product.id, dataset_id: dataset.id, budget_usd: budget });
      nav(`/app/runs/${run.id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(null);
    }
  };

  if (!product && !error) return <Layout><Loading /></Layout>;
  return (
    <Layout>
      <h1 className="text-xl font-bold">پیام‌ها از کجا بیاید؟</h1>

      <div className="mt-4 flex flex-wrap gap-2" role="tablist">
        {SOURCES.filter(([s]) => s !== "x" || xcfg?.enabled).map(([s, label]) => (
          <button key={s} role="tab" aria-selected={source === s} onClick={() => setSource(s)}
            className={cx("rounded-lg px-3 py-1.5 text-sm", source === s ? "bg-ink-900 text-white" : "bg-ink-50 text-ink-700 hover:bg-ink-100")}>
            {label}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {source === "sample" && <p className="text-sm text-ink-500">یک گروه تلگرام نمونه درباره برنامه‌نویسی.</p>}

        {source === "x" && xcfg && (
          <div className="space-y-2">
            <p className="text-sm text-ink-500">پست‌های فارسی هفت روز اخیر که به نیاز مشتری‌های شما می‌خورند.</p>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <select value={posts} onChange={(e) => setPosts(Number(e.target.value))} aria-label="تعداد پست"
                className="rounded-lg border border-ink-200 bg-white px-2 py-1.5">
                {POST_OPTIONS.filter((n) => n <= xcfg.max_posts).map((n) => <option key={n} value={n}>{num(n)} پست</option>)}
              </select>
              <Button variant="outline" loading={busy === "x"} disabled={!!busy}
                onClick={() => load("x", () => api.post<Dataset>("/api/datasets/twitter", { product_id: product?.id, max_posts: posts }))}>
                جستجو در ایکس
              </Button>
            </div>
            <p className="text-xs text-ink-400">
              {xcfg.price_per_post_usd > 0
                ? <>حداکثر {usd(posts * xcfg.price_per_post_usd)} · جستجوی تکراری تا یک روز رایگان است</>
                : <>رایگان، با حساب ایکس خودتان · ممکن است یک دقیقه طول بکشد</>}
            </p>
          </div>
        )}

        {source === "upload" && (
          <div className="space-y-2">
            <p className="text-sm text-ink-500">تلگرام دسکتاپ ← منوی گروه ← Export chat history ← فرمت JSON</p>
            <input type="file" accept=".json,application/json" disabled={busy === "upload"} aria-label="فایل JSON"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} className="text-sm" />
          </div>
        )}

        {source === "paste" && (
          <div className="space-y-2">
            <TextArea rows={7} value={pasted} onChange={(e) => setPasted(e.target.value)} dir="auto" aria-label="متن پیام‌ها"
              placeholder={"سارا: کسی دوره پایتون خوب سراغ داره؟"} />
            <Button variant="outline" onClick={() => load("paste", () => api.post<Dataset>("/api/datasets/paste", { text: pasted }))}
              loading={busy === "paste"} disabled={pasted.trim().length < 10}>خواندن</Button>
          </div>
        )}

        {(busy === "sample" || busy === "upload") && <Loading text="در حال خواندن…" />}
        {busy === "x" && <Loading text="در حال جستجو در ایکس…" />}
        {dataset && (
          <p className="mt-3 text-sm">
            {num(dataset.stats.messages)} {dataset.source === "twitter" ? "پست" : "پیام"} از {num(dataset.stats.authors)} نفر خوانده شد.
            {dataset.stats.x && <> هزینه ایکس: {usd(dataset.stats.x.cost_usd)}</>}
            {dataset.warnings.map((w) => <span key={w} title={w} className="block truncate text-amber-800">{w}</span>)}
          </p>
        )}
      </div>

      <div className="mt-8">
        <label className="flex items-center gap-3 text-sm">
          <span className="font-bold">بودجه</span>
          <select value={budget} onChange={(e) => setBudget(Number(e.target.value))}
            className="rounded-lg border border-ink-200 bg-white px-2 py-1.5">
            {BUDGET_OPTIONS.filter((b) => b <= maxBudget).map((b) => <option key={b} value={b}>{usd(b)}</option>)}
          </select>
        </label>
        <p className="mt-1 text-xs text-ink-400">وقتی بودجه تمام شود، بررسی متوقف می‌شود.</p>
      </div>

      {error && <div className="mt-4"><ErrorBox message={error} /></div>}
      <div className="mt-6">
        <Button onClick={start} loading={busy === "run"} disabled={!dataset || !!busy}>شروع</Button>
      </div>
    </Layout>
  );
}
