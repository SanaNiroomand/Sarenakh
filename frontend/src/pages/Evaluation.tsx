import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Layout } from "../components/Layout";
import { Card, Empty, ErrorBox, Loading, SectionTitle, cx } from "../components/ui";
import { api, errorText } from "../lib/api";
import { DECISION_FA, mid, num, pct, usd } from "../lib/fmt";
import type { Evaluation as Ev, RunSummary } from "../lib/types";
import { SampleButtons } from "./Dashboard";

const STAGE_FA: Record<string, string> = {
  prefilter_dropped: "پیش‌فیلتر کنار گذاشت",
  prefilter: "پیش‌فیلتر",
  triage: "تریاژ",
  investigate: "بررسی عمیق",
  critic: "منتقد",
  draft: "سرنخ + پاسخ",
};
const PRODUCT_FA: Record<string, string> = { pystart: "دوره پایتون (پای‌استارت)", cheshmaram: "عینک چشم‌آرام" };

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-ink-100 bg-white px-4 py-3">
      <div className="text-xs font-bold text-ink-500">{label}</div>
      <div className="text-xl font-extrabold">{value}</div>
      {sub && <div className="text-xs text-ink-400">{sub}</div>}
    </div>
  );
}

function EvalView({ runId }: { runId: number }) {
  const [ev, setEv] = useState<Ev | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setEv(null);
    api.get<Ev>(`/api/runs/${runId}/evaluation`).then(setEv).catch((e) => setError(errorText(e)));
  }, [runId]);
  if (error) return <ErrorBox message={error} />;
  if (!ev) return <Loading />;
  const th = "border-b border-ink-100 px-2 py-2 text-start text-xs font-bold text-ink-500";
  const td = "border-b border-ink-50 px-2 py-2 align-top";
  return (
    <div className="space-y-5">
      <Card className="bg-ink-900 text-white">
        <div className="text-sm text-ink-200">{PRODUCT_FA[ev.product] ?? ev.product} · اجرای شماره {num(ev.run_id)}</div>
        <div className="mt-1 text-2xl font-extrabold sm:text-3xl">
          {num(ev.found)} از {num(ev.real_leads)} سرنخ واقعی پیدا شد، {num(ev.false_positives)} مثبت کاذب
        </div>
        <Link to={`/app/runs/${ev.run_id}`} className="mt-2 inline-block text-sm text-thread-200 underline-offset-4 hover:underline">دیدن نتایج این اجرا ←</Link>
      </Card>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="دقت (Precision)" value={pct(ev.precision)} sub="از سرنخ‌های اعلام‌شده چندتا درست بودند" />
        <Metric label="بازیابی (Recall)" value={pct(ev.recall)} sub="از مشتری‌های واقعی چندتا پیدا شدند" />
        <Metric label="هزینه کل" value={usd(ev.equivalent_cost_usd)} sub={`هزینه هر سرنخ: ${usd(ev.cost_per_lead_usd)}`} />
        <Metric label="بازیابی پیش‌فیلتر" value={pct(ev.prefilter_recall)} sub="مشتری‌هایی که از فیلتر ارزان رد شدند" />
      </div>

      <Card>
        <SectionTitle title="مشتری‌های واقعی کاشته‌شده" sub="هر نفر یک بار شمرده می‌شود" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr><th className={th}></th><th className={th}>نفر</th><th className={th}>چرا مشتری است</th><th className={th}>کجا رسید</th><th className={th}>تناسب</th></tr></thead>
            <tbody>
              {ev.leads.map((l) => (
                <tr key={l.label}>
                  <td className={td}>{l.found ? "✅" : "❌"}</td>
                  <td className={cx(td, "font-bold")}>{l.author}<div className="text-xs font-normal text-ink-400">#{mid(l.msg_id)}</div></td>
                  <td className={cx(td, "text-ink-600")} dir="ltr" style={{ textAlign: "left" }}>{l.note}</td>
                  <td className={td}>{STAGE_FA[l.stage] ?? l.stage} · {DECISION_FA[l.decision] ?? l.decision}</td>
                  <td className={td}>{l.fit != null ? num(l.fit, 1) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <SectionTitle title="تله‌ها (پیام‌های گمراه‌کننده)" sub="سینیورها، کسانی که قبلا خریده‌اند، طعنه، تبلیغ رقیب، فقط-رایگان…" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr><th className={th}></th><th className={th}>نفر</th><th className={th}>تله</th><th className={th}>کجا متوقف شد</th></tr></thead>
            <tbody>
              {ev.decoys.map((d) => (
                <tr key={d.label}>
                  <td className={td}>{d.fooled ? "❌ فریب خورد" : "✅"}</td>
                  <td className={cx(td, "font-bold")}>{d.author}<div className="text-xs font-normal text-ink-400">#{mid(d.msg_id)}</div></td>
                  <td className={cx(td, "text-ink-600")} dir="ltr" style={{ textAlign: "left" }}>{d.note}</td>
                  <td className={td}>{STAGE_FA[d.stage] ?? d.stage}{d.relevance != null ? ` (تریاژ ${num(d.relevance)})` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

export default function Evaluation() {
  const [params, setParams] = useSearchParams();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.get<RunSummary[]>("/api/runs").then(setRuns).catch((e) => setError(errorText(e))); }, []);

  const sampleRuns = (runs ?? []).filter((r) => r.status === "done" && r.dataset?.sample_key && r.product?.sample_key);
  const selected = Number(params.get("run")) || sampleRuns[0]?.id;

  return (
    <Layout>
      <h1 className="text-2xl font-extrabold">ارزیابی دقت</h1>
      <p className="mb-6 mt-1 text-ink-500">
        در گفتگوی نمونه ۱۴ مشتری واقعی (۹ برای دوره پایتون، ۵ برای عینک) و ۱۶ تله کاشته‌ایم و پاسخ درست را می‌دانیم.
        اینجا می‌بینید عامل چندتا را درست پیدا کرد، چندتا را اشتباه گرفت و با چه هزینه‌ای.
      </p>
      {error && <ErrorBox message={error} />}
      {!runs && !error && <Loading />}
      {runs && sampleRuns.length === 0 && (
        <div className="space-y-4">
          <Empty icon="📏" title="هنوز اجرایی روی داده نمونه ندارید">یکی از محصولات نمونه را اجرا کنید؛ ارزیابی خودکار اینجا ظاهر می‌شود.</Empty>
          <SampleButtons />
        </div>
      )}
      {sampleRuns.length > 0 && (
        <>
          <div className="mb-5 flex flex-wrap gap-2">
            {sampleRuns.slice(0, 8).map((r) => (
              <button key={r.id} onClick={() => setParams({ run: String(r.id) })}
                className={cx("rounded-xl px-3 py-2 text-sm font-bold ring-1", r.id === selected ? "bg-ink-900 text-white ring-ink-900" : "bg-white text-ink-700 ring-ink-200")}>
                {PRODUCT_FA[r.product?.sample_key ?? ""] ?? r.product?.name} · #{mid(r.id)}
              </button>
            ))}
          </div>
          {selected && <EvalView runId={selected} />}
          <div className="mt-8">
            <SectionTitle title="اجرای دوباره روی داده نمونه" />
            <SampleButtons />
          </div>
        </>
      )}
    </Layout>
  );
}
