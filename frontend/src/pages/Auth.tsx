import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Layout } from "../components/Layout";
import { Button, ErrorBox, Field } from "../components/ui";
import { api, errorText } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { User } from "../lib/types";

function AuthForm({ title, onSubmit, children, footer }: {
  title: string; onSubmit: (e: FormEvent) => void; children: ReactNode; footer: ReactNode;
}) {
  return (
    <Layout>
      <div className="mx-auto max-w-sm">
        <h1 className="mb-6 text-xl font-bold">{title}</h1>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>{children}</form>
        <p className="mt-4 text-sm text-ink-500">{footer}</p>
      </div>
    </Layout>
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
    <AuthForm title="ورود" onSubmit={submit}
      footer={<>حساب ندارید؟ <Link to="/signup" className="text-ink-900 hover:underline">ثبت‌نام</Link></>}>
      <Field label="ایمیل" type="email" dir="ltr" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <Field label="رمز عبور" type="password" dir="ltr" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <ErrorBox message={error} />}
      <Button type="submit" loading={busy}>ورود</Button>
    </AuthForm>
  );
}

export function Signup() {
  const { user, setUser } = useAuth();
  const nav = useNavigate();
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
      setUser(await api.post<User>("/api/auth/signup", { email, password }));
      nav("/app", { replace: true });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthForm title="ثبت‌نام" onSubmit={submit}
      footer={<>حساب دارید؟ <Link to="/login" className="text-ink-900 hover:underline">ورود</Link></>}>
      <Field label="ایمیل" type="email" dir="ltr" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <Field label="رمز عبور" type="password" dir="ltr" autoComplete="new-password" required hint="حداقل ۸ کاراکتر" error={pwError}
        value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <ErrorBox message={error} />}
      <Button type="submit" loading={busy}>ثبت‌نام</Button>
    </AuthForm>
  );
}
