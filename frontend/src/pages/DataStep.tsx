import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Layout } from "../components/Layout";
import { Button, Card, ErrorBox, Loading, SectionTitle, Steps, TextArea, cx } from "../components/ui";
import { ApiError, api, errorText } from "../lib/api";
import { num, usd } from "../lib/fmt";
import { BUDGET_OPTIONS, getConfig, type PublicConfig } from "../lib/flow";
import type { Dataset, Product, RunSummary } from "../lib/types";

type Tab = "sample" | "upload" | "paste";

function DatasetSummary({ ds }: { ds: Dataset }) {
  const s = ds.stats;
  return (
    <div className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-900 ring-1 ring-emerald-200">
      <div className="font-bold">✓ {ds.name}</div>
      <div className="mt-1">{num(s.messages)} پیام · {num(s.analyzable)} پیام متنی قابل بررسی · {num(s.authors)} نفر · {num(s.replies)} پاسخ</div>
      {ds.warnings.map((w) => <div key={w} className="mt-1 text-amber-800">⚠️ {w}</div>)}
    </div>
  );
}

export default function DataStep() {
  const { id } = useParams();
  const nav = useNavigate();
  const [product, setProduct] = useState<Product | null>(null);
  const [cfg, setCfg] = useState<PublicConfig | null>(null);
  const [tab, setTab] = useState<Tab>("sample");
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [pasted, setPasted] = useState("");
  const [budget, setBudget] = useState(0.25);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<Product>(`/api/products/${id}`).then(setProduct).catch((e) => setError(errorText(e)));
    getConfig().then((c) => { setCfg(c); setBudget(c.default_run_budget_usd); }).catch(() => undefined);
  }, [id]);

  const pickSample = async () => {
    setBusy("sample");
    setError(null);
    try { setDataset(await api.get<Dataset>("/api/datasets/sample")); } catch (e) { setError(errorText(e)); } finally { setBusy(null); }
  };
  useEffect(() => { if (tab === "sample" && !dataset) void pickSample(); }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (file: File) => {
    setBusy("upload");
    setError(null);
    const fd = new FormData();
    fd.append("file", file);
    try { setDataset(await api.post<Dataset>("/api/datasets/upload", fd)); } catch (e) { setError(errorText(e)); } finally { setBusy(null); }
  };
  const paste = async () => {
    setBusy("paste");
    setError(null);
    try { setDataset(await api.post<Dataset>("/api/datasets/paste", { text: pasted })); } catch (e) { setError(errorText(e)); } finally { setBusy(null); }
  };
  const start = async () => {
    if (!dataset || !product) return;
    setBusy("run");
    setError(null);
    try {
      const run = await api.post<RunSummary>("/api/runs", { product_id: product.id, dataset_id: dataset.id, budget_usd: budget });
      nav(`/app/runs/${run.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : errorText(e));
      setBusy(null);
    }
  };

  const options = BUDGET_OPTIONS.filter((b) => !cfg || b <= cfg.max_run_budget_usd);
  const switchTab = (t: Tab) => { setTab(t); setDataset(null); setError(null); };

  if (!product && !error) return <Layout><Loading /></Layout>;
  return (
    <Layout>
      <Steps current={2} />
      <h1 className="mb-1 text-2xl font-extrabold">پیام‌های کدام گروه را بگردیم؟</h1>
      <p className="mb-6 text-ink-500">برای «{product?.name}»</p>

      <Card className="mb-5">
        <div className="mb-4 flex flex-wrap gap-2" role="tablist">
          {([["sample", "⚡ داده نمونه"], ["upload", "📁 آپلود خروجی تلگرام"], ["paste", "📋 چسباندن متن"]] as [Tab, string][]).map(([t, label]) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => switchTab(t)}
              className={cx("rounded-xl px-4 py-2 text-sm font-bold", tab === t ? "bg-ink-900 text-white" : "bg-ink-50 text-ink-600 hover:bg-ink-100")}>{label}</button>
          ))}
        </div>

        {tab === "sample" && (
          <div className="space-y-3 text-sm text-ink-600">
            <p>گروه «پایتونیست‌های ایران»: یک هفته گفتگوی واقعی‌نما با پیام‌های فارسی، فینگلیش و فارسیِ پر از اصطلاح انگلیسی؛ چند مشتری واقعی و کلی پیام گمراه‌کننده (طعنه، تبلیغ رقیب، کسانی که قبلا خریده‌اند).</p>
            {busy === "sample" && <Loading text="در حال آماده‌سازی…" />}
          </div>
        )}

        {tab === "upload" && (
          <div className="space-y-3">
            <ol className="list-inside list-decimal space-y-1 text-sm leading-7 text-ink-600">
              <li>در تلگرام دسکتاپ گروه را باز کنید و از منوی ⋮ گزینه <b>Export chat history</b> را بزنید.</li>
              <li>تیک عکس و فایل‌ها را بردارید و فرمت را <b>JSON</b> (Machine-readable) انتخاب کنید.</li>
              <li>فایل <b dir="ltr">result.json</b> را اینجا بدهید (حداکثر ۱۵ مگابایت).</li>
            </ol>
            <label className={cx("flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-ink-200 px-4 py-8 text-center hover:border-thread-300",
              busy === "upload" && "opacity-60")}>
              <span className="text-2xl" aria-hidden>📁</span>
              <span className="font-bold">{busy === "upload" ? "در حال خواندن فایل…" : "انتخاب فایل JSON"}</span>
              <input type="file" accept=".json,application/json" className="sr-only" disabled={busy === "upload"}
                onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            </label>
          </div>
        )}

        {tab === "paste" && (
          <div className="space-y-3">
            <p className="text-sm text-ink-600">پیام‌ها را از تلگرام کپی کنید (یا هر خط به شکل «نام: پیام»).</p>
            <TextArea rows={8} value={pasted} onChange={(e) => setPasted(e.target.value)} dir="auto"
              placeholder={"سارا: سلام کسی دوره پایتون خوب سراغ داره؟\nعلی: من مکتب‌خونه رو دیدم…"} />
            <Button onClick={paste} loading={busy === "paste"} disabled={pasted.trim().length < 10}>خواندن پیام‌ها</Button>
          </div>
        )}

        {dataset && <div className="mt-4"><DatasetSummary ds={dataset} /></div>}
      </Card>

      <Card className="mb-5">
        <SectionTitle title="بودجه این اجرا" sub="عامل از امیدوارترین پیام‌ها شروع می‌کند و وقتی بودجه تمام شود می‌ایستد." />
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="بودجه">
          {options.map((b) => (
            <button key={b} role="radio" aria-checked={budget === b} onClick={() => setBudget(b)}
              className={cx("rounded-xl px-4 py-2.5 text-sm font-bold ring-1", budget === b ? "bg-thread-500 text-white ring-thread-500" : "bg-white text-ink-700 ring-ink-200 hover:bg-ink-50")}>
              {usd(b)}
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs leading-6 text-ink-500">
          حدودا هر بررسی عمیق ۰٫۰۱ تا ۰٫۰۲ دلار و هر سرنخ با پیش‌نویس پاسخ حدود ۰٫۰۲ دلار هزینه دارد. اجرای داده نمونه با محصول نمونه از حافظه پخش می‌شود و تقریبا رایگان است.
          {cfg && <> مدل‌ها: تریاژ <span dir="ltr">{cfg.models.triage}</span>، بررسی و پاسخ <span dir="ltr">{cfg.models.agent}</span>.</>}
        </p>
      </Card>

      {error && <div className="mb-4"><ErrorBox message={error} /></div>}
      <div className="flex justify-end">
        <Button size="lg" variant="thread" onClick={start} loading={busy === "run"} disabled={!dataset || !!busy}>🧶 شروع جستجو</Button>
      </div>
    </Layout>
  );
}
