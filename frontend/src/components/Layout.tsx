import type { ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { cx } from "./ui";

export function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2 text-lg font-bold">
      <img src="/logo.svg" alt="" className="h-7 w-7" />
      سرنخ
    </Link>
  );
}

export function Layout({ children }: { children: ReactNode; wide?: boolean }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const link = ({ isActive }: { isActive: boolean }) => cx("hover:underline", isActive ? "font-bold" : "text-ink-500");
  return (
    <div className="min-h-screen">
      <header className="border-b border-ink-100">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-3 text-sm">
          <Brand />
          {user ? (
            <nav className="flex items-center gap-4">
              <NavLink to="/app" end className={link}>خانه</NavLink>
              <NavLink to="/app/new" className={link}>جستجوی تازه</NavLink>
              <NavLink to="/app/eval" className={link}>دقت</NavLink>
              <button className="text-ink-500 hover:underline" onClick={async () => { await logout(); nav("/"); }}>خروج</button>
            </nav>
          ) : (
            <nav className="flex items-center gap-4">
              <Link to="/login" className="text-ink-500 hover:underline">ورود</Link>
              <Link to="/signup" className="hover:underline">ثبت‌نام</Link>
            </nav>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-3xl px-4 py-8">{children}</main>
    </div>
  );
}
