import { useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { cx } from "./ui";

export function Logo({ className = "h-9 w-9" }: { className?: string }) {
  return <img src="/logo.svg" alt="" className={className} />;
}

export function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2" aria-label="سرنخ — صفحه اصلی">
      <Logo />
      <span className="text-xl font-extrabold tracking-tight text-ink-900">سرنخ</span>
    </Link>
  );
}

export function Layout({ children, wide }: { children: ReactNode; wide?: boolean }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const link = ({ isActive }: { isActive: boolean }) =>
    cx("rounded-lg px-3 py-2 text-sm font-bold", isActive ? "bg-ink-900 text-white" : "text-ink-600 hover:bg-ink-50");
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-ink-100 bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <Brand />
          {user ? (
            <>
              <nav className="hidden items-center gap-1 sm:flex">
                <NavLink to="/app" end className={link}>میز کار</NavLink>
                <NavLink to="/app/new" className={link}>جستجوی تازه</NavLink>
                <NavLink to="/app/eval" className={link}>ارزیابی</NavLink>
              </nav>
              <div className="hidden items-center gap-2 sm:flex">
                <span className="max-w-40 truncate text-sm text-ink-500" title={user.email}>{user.name}</span>
                <button className="rounded-lg px-2 py-1 text-sm text-ink-500 hover:bg-ink-50" onClick={async () => { await logout(); nav("/"); }}>خروج</button>
              </div>
              <button className="rounded-lg p-2 text-ink-700 hover:bg-ink-50 sm:hidden" aria-label="منو" aria-expanded={open} onClick={() => setOpen(!open)}>☰</button>
            </>
          ) : (
            <div className="flex items-center gap-2">
              <Link to="/login" className="rounded-lg px-3 py-2 text-sm font-bold text-ink-700 hover:bg-ink-50">ورود</Link>
              <Link to="/signup" className="rounded-xl bg-ink-900 px-4 py-2 text-sm font-bold text-white hover:bg-ink-700">ثبت‌نام رایگان</Link>
            </div>
          )}
        </div>
        {user && open && (
          <nav className="flex flex-col gap-1 border-t border-ink-100 px-4 py-2 sm:hidden" onClick={() => setOpen(false)}>
            <NavLink to="/app" end className={link}>میز کار</NavLink>
            <NavLink to="/app/new" className={link}>جستجوی تازه</NavLink>
            <NavLink to="/app/eval" className={link}>ارزیابی</NavLink>
            <button className="rounded-lg px-3 py-2 text-start text-sm text-ink-500 hover:bg-ink-50" onClick={async () => { await logout(); nav("/"); }}>خروج ({user.email})</button>
          </nav>
        )}
      </header>
      <main className={cx("mx-auto w-full flex-1 px-4 py-6 sm:py-8", wide ? "max-w-6xl" : "max-w-4xl")}>{children}</main>
      <footer className="border-t border-ink-100 py-5 text-center text-xs text-ink-400">
        سرنخ
      </footer>
    </div>
  );
}
