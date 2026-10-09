import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Brand } from "../components/Layout";
import { Button, Card, ErrorBox, Field } from "../components/ui";
import { api, errorText } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { User } from "../lib/types";

function AuthShell({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="mb-6"><Brand /></div>
      <Card className="w-full max-w-sm">
        <h1 className="text-xl font-extrabold">{title}</h1>
        <p className="mb-5 mt-1 text-sm text-ink-500">{sub}</p>
        {children}
      </Card>
    </div>
  );
}

export function Login() {
  const { user, setUser } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/app";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (user) return <Navigate to={next} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setUser(await api.post<User>("/api/auth/login", { email, password }));
      nav(next, { replace: true });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="ورود" sub="خوش برگشتید؛ سرنخ‌ها منتظرند.">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="ایمیل" type="email" dir="ltr" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field label="رمز عبور" type="password" dir="ltr" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <ErrorBox message={error} />}
        <Button type="submit" className="w-full" size="lg" loading={busy}>ورود</Button>
      </form>
      <p className="mt-4 text-center text-sm text-ink-500">حساب ندارید؟ <Link to="/signup" className="font-bold text-ink-900 underline-offset-4 hover:underline">ثبت‌نام</Link></p>
    </AuthShell>
  );
}

export function Signup() {
  const { user, setUser } = useAuth();
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (user && !busy) return <Navigate to="/app" replace />;

  const pwError = password && password.length < 8 ? "حداقل ۸ کاراکتر" : undefined;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (pwError) return;
    setBusy(true);
    setError(null);
    try {
      setUser(await api.post<User>("/api/auth/signup", { email, password, name }));
      nav("/app?welcome=1", { replace: true });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="ثبت‌نام رایگان" sub="کمتر از یک دقیقه؛ بعدش با یک کلیک داده نمونه را امتحان کنید.">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="نام (اختیاری)" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        <Field label="ایمیل" type="email" dir="ltr" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field label="رمز عبور" type="password" dir="ltr" autoComplete="new-password" required hint="حداقل ۸ کاراکتر" error={pwError}
          value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <ErrorBox message={error} />}
        <Button type="submit" className="w-full" size="lg" variant="thread" loading={busy}>ساخت حساب</Button>
      </form>
      <p className="mt-4 text-center text-sm text-ink-500">حساب دارید؟ <Link to="/login" className="font-bold text-ink-900 underline-offset-4 hover:underline">ورود</Link></p>
    </AuthShell>
  );
}
