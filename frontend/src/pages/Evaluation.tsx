import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Layout } from "../components/Layout";
import { ErrorBox, Loading } from "../components/ui";
import { api, errorText } from "../lib/api";
import { DECISION_FA, mid, num, usd } from "../lib/fmt";
import type { Evaluation as Ev, RunSummary } from "../lib/types";
import { SampleButtons } from "./Dashboard";

const shortName = (name?: string) => (name ?? "").split("—")[0].trim();

function EvalView({ runId }: { runId: number }) {
  const [ev, setEv] = useState<Ev | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setEv(null);
    api.get<Ev>(`/api/runs/${runId}/evaluation`).then(setEv).catch((e) => setError(errorText(e)));
  }, [runId]);
  if (error) return <ErrorBox message={error} />;
  if (!ev) return <Loading />;
  return (
    <div className="space-y-8">
      <p className="truncate">
        {num(ev.found)} از {num(ev.real_leads)} مشتری پیدا شد · {num(ev.false_positives)} انتخاب اشتباه
        {ev.cost_per_lead_usd != null && <> · هر نفر {usd(ev.cost_per_lead_usd)}</>}
      </p>

      <section>
        <h2 className="mb-2 font-bold">مشتری‌های واقعی</h2>
        <ul className="space-y-1 text-sm">
          {ev.leads.map((l) => (
            <li key={l.label} className="truncate" title={l.note}>
              {l.found ? "✓" : "✗"} <b>{l.author}</b>
              {!l.found && <span className="text-ink-500"> ({DECISION_FA[l.decision] ?? l.decision})</span>}: {l.note}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-2 font-bold">پیام‌های گمراه‌کننده</h2>
        <ul className="space-y-1 text-sm">
          {ev.decoys.map((d) => (
            <li key={d.label} className="truncate" title={d.note}>
              {d.fooled ? "✗" : "✓"} <b>{d.author}</b>{d.fooled && <span className="text-red-700"> (اشتباه انتخاب شد)</span>}: {d.note}
            </li>
          ))}
        </ul>
      </section>

      <Link to={`/app/runs/${ev.run_id}`} className="text-sm text-ink-500 hover:underline">دیدن نتایج این اجرا</Link>
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
      <h1 className="text-xl font-bold">دقت</h1>
      <p className="mb-6 mt-1 text-sm text-ink-500">روی داده نمونه، جواب درست را می‌دانیم.</p>
      {error && <ErrorBox message={error} />}
      {!runs && !error && <Loading />}
      {runs && sampleRuns.length === 0 && (
        <div className="space-y-3">
          <p className="text-sm">هنوز اجرایی روی داده نمونه ندارید. یکی را اجرا کنید:</p>
          <SampleButtons />
        </div>
      )}
      {sampleRuns.length > 0 && (
        <>
          <label className="mb-6 flex items-center gap-2 text-sm">
            <span>اجرا:</span>
            <select value={selected} onChange={(e) => setParams({ run: e.target.value })}
              className="rounded-lg border border-ink-200 bg-white px-2 py-1.5">
              {sampleRuns.map((r) => (
                <option key={r.id} value={r.id}>{shortName(r.product?.name)} · #{mid(r.id)}</option>
              ))}
            </select>
          </label>
          {selected && <EvalView runId={selected} />}
        </>
      )}
    </Layout>
  );
}
