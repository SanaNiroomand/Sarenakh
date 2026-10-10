import { useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";
import { Link } from "react-router-dom";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
export { cx };

/** Shows text on a single line with "…"; click to see the whole text. */
export function OneLine({ text, className }: { text: string; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span title={open ? undefined : text} onClick={() => setOpen(!open)}
      className={cx("block cursor-pointer", !open && "truncate", className)}>{text}</span>
  );
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "thread" | "ghost" | "outline" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
};

const BTN_BASE =
  "inline-flex items-center justify-center gap-2 rounded-xl font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-thread-500";
const BTN_VARIANT = {
  primary: "bg-ink-900 text-white hover:bg-ink-700",
  thread: "bg-thread-500 text-white hover:bg-thread-600",
  ghost: "text-ink-700 hover:bg-ink-50",
  outline: "border border-ink-200 bg-white text-ink-800 hover:bg-ink-50",
  danger: "border border-red-200 bg-white text-red-700 hover:bg-red-50",
};
const BTN_SIZE = { sm: "px-3 py-1.5 text-sm", md: "px-4 py-2.5 text-sm", lg: "px-6 py-3.5 text-base" };

export function Button({ variant = "primary", size = "md", loading, className, children, disabled, ...rest }: BtnProps) {
  return (
    <button className={cx(BTN_BASE, BTN_VARIANT[variant], BTN_SIZE[size], className)} disabled={disabled || loading} {...rest}>
      {loading && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function LinkButton({ to, variant = "primary", size = "md", className, children }:
  { to: string; variant?: BtnProps["variant"]; size?: BtnProps["size"]; className?: string; children: ReactNode }) {
  return <Link to={to} className={cx(BTN_BASE, BTN_VARIANT[variant], BTN_SIZE[size], className)}>{children}</Link>;
}

export function Card({ className, children, ...rest }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("rounded-2xl border border-ink-100 bg-white p-4 shadow-[0_1px_2px_rgba(31,27,58,0.04)] sm:p-5", className)} {...rest}>{children}</div>;
}

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={cx("animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Loading({ text = "در حال بارگذاری…" }: { text?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-ink-500" role="status">
      <Spinner /> <span>{text}</span>
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <p className="text-sm text-red-700" role="alert">
      {message}
      {onRetry && <button className="ms-2 underline" onClick={onRetry}>دوباره</button>}
    </p>
  );
}

export function Empty({ icon = "🧶", title, children }: { icon?: string; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-ink-200 px-6 py-10 text-center">
      <div className="text-3xl" aria-hidden>{icon}</div>
      <div className="font-bold text-ink-800">{title}</div>
      {children && <div className="max-w-md text-sm text-ink-500">{children}</div>}
    </div>
  );
}

export function Badge({ className, children }: { className?: string; children: ReactNode }) {
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ring-inset", className)}>{children}</span>;
}

export function Field({ label, hint, error, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-bold text-ink-800">{label}</span>
      <input
        className={cx("w-full rounded-xl border bg-white px-3.5 py-2.5 text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-thread-400 focus:ring-4 focus:ring-thread-100",
          error ? "border-red-300" : "border-ink-200")}
        {...rest}
      />
      {hint && !error && <span className="mt-1 block text-xs text-ink-400">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-red-700">{error}</span>}
    </label>
  );
}

export function TextArea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cx("w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 leading-7 text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-thread-400 focus:ring-4 focus:ring-thread-100", className)}
      {...rest}
    />
  );
}

export function SectionTitle({ title, sub, action }: { title: string; sub?: string; action?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
      <div>
        <h2 className="text-lg font-extrabold text-ink-900">{title}</h2>
        {sub && <p className="text-sm text-ink-500">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

export function Steps({ current }: { current: 1 | 2 | 3 | 4 }) {
  const steps = ["معرفی محصول", "پیام‌های گروه", "کار عامل", "نتایج"];
  return (
    <ol className="mb-6 flex items-center gap-1 overflow-x-auto text-xs sm:gap-2 sm:text-sm" aria-label="مراحل">
      {steps.map((s, i) => {
        const n = i + 1;
        const state = n < current ? "done" : n === current ? "now" : "next";
        return (
          <li key={s} className="flex shrink-0 items-center gap-1 sm:gap-2">
            <span className={cx("flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold",
              state === "done" && "bg-thread-500 text-white", state === "now" && "bg-ink-900 text-white",
              state === "next" && "bg-ink-100 text-ink-400")}>{n}</span>
            <span className={cx(state === "next" ? "text-ink-400" : "font-bold text-ink-800")} aria-current={state === "now" ? "step" : undefined}>{s}</span>
            {n < steps.length && <span className="mx-1 h-px w-4 bg-ink-200 sm:w-8" aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}
