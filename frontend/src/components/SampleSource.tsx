import type { SampleProduct } from "../lib/types";

const host = (u: string) => {
  try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; }
};

/** Where the demo products' facts come from — real Iranian products, used only as examples. */
export function SampleSource({ samples }: { samples: SampleProduct[] }) {
  if (!samples.length) return null;
  return (
    <p className="text-xs leading-6 text-ink-500">
      محصولات نمونه واقعی‌اند و اطلاعاتشان از صفحه عمومی خود محصول برداشته شده
      ({samples.map((s, i) => (
        <span key={s.key}>
          {i > 0 && "، "}
          <a href={s.source_url} target="_blank" rel="noopener noreferrer" className="font-bold text-ink-700 underline underline-offset-2" dir="ltr">{host(s.source_url)}</a>
        </span>
      ))}، بررسی‌شده در {samples[0].checked_at}). صرفا برای نمایش؛ سرنخ وابستگی یا همکاری با این برندها ندارد و قیمت‌ها ممکن است تغییر کرده باشند.
    </p>
  );
}
