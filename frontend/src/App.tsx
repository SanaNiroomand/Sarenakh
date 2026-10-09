import { useEffect, useState } from "react";

type Health = {
  status: "ok" | "degraded";
  version: string;
  model_check: string;
  models: { model: string; kind: string; ok: boolean; error: string | null }[];
};

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setError(true));
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center gap-6 px-4 text-center">
      <img src="/logo.svg" alt="" className="h-20 w-20" />
      <h1 className="text-4xl font-extrabold text-ink-900">سرنخ</h1>
      <p className="text-lg text-ink-600">سرنخ مشتری‌ات را در دل گفتگوها پیدا کن</p>

      <section className="w-full rounded-2xl border border-ink-100 bg-white p-4 text-start shadow-sm">
        <h2 className="mb-2 font-bold">وضعیت سرویس</h2>
        {error && <p className="text-red-700">سرور در دسترس نیست.</p>}
        {!health && !error && <p className="text-ink-400">در حال بررسی…</p>}
        {health && (
          <>
            <p className={health.status === "ok" ? "text-emerald-700" : "text-thread-700"}>
              {health.status === "ok" ? "همه‌چیز آماده است" : "حالت محدود: " + health.model_check}
            </p>
            <ul className="mt-2 space-y-1 text-sm" dir="ltr">
              {health.models.map((m) => (
                <li key={m.model} className="flex justify-between gap-2">
                  <span className="font-mono">{m.model}</span>
                  <span className={m.ok ? "text-emerald-700" : "text-red-700"}>{m.ok ? "OK" : m.error}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-ink-400">نسخه {health.version}</p>
          </>
        )}
      </section>
    </main>
  );
}
