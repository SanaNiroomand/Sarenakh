import { Layout } from "../components/Layout";
import { Card, LinkButton } from "../components/ui";
import { useAuth } from "../lib/auth";

const FEED = [
  { t: "🧶 شروع: ۳۵۱ پیام از «پایتونیست‌های ایران»", c: "text-ink-700" },
  { t: "🪡 ۱۷۶ پیام به نشانه‌های خرید نزدیک بودند", c: "text-ink-700" },
  { t: "🔎 دنبال کردن سرنخ از Babak: «منم دنبال همینم…»", c: "font-bold text-ink-900" },
  { t: "🧵 خواندن رشته گفتگو — «همینم» به چی اشاره داره؟", c: "text-ink-600" },
  { t: "👤 مرور پیام‌های قبلی Babak — شاغله، وقتش کمه", c: "text-ink-600" },
  { t: "😈 وکیل مدافع شیطان تلاش کرد ردش کند… سرنخ ماند ✅", c: "text-purple-800" },
  { t: "🎯 Babak: دوره منظم با کلاس عصر → تناسب ۶٫۶ از ۱۰", c: "font-bold text-thread-700" },
];

export default function Landing() {
  const { user } = useAuth();
  return (
    <Layout wide>
      <section className="grid items-center gap-8 py-4 md:grid-cols-2 md:py-10">
        <div>
          <p className="mb-3 inline-block rounded-full bg-thread-50 px-3 py-1 text-xs font-bold text-thread-700 ring-1 ring-thread-200">
            عامل هوشمند پیدا کردن مشتری در گروه‌های تلگرامی
          </p>
          <h1 className="text-3xl font-extrabold leading-tight text-ink-900 sm:text-5xl sm:leading-tight">
            سرنخ مشتری‌ات را<br />در دل گفتگوها پیدا کن
          </h1>
          <p className="mt-4 text-base leading-8 text-ink-600 sm:text-lg">
            گفتگوهای گروه یک کلاف سردرگم است. سرنخ رشته‌ها را دنبال می‌کند، شواهد جمع می‌کند و فقط کسانی را که واقعا به محصول تو نیاز دارند تحویل می‌دهد —
            هر کدام با پیام‌های شاهد و یک پاسخ کمک‌محورِ آماده ارسال. هزینه بررسی هر پیام را هم دقیق می‌بینی.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            {user ? (
              <LinkButton to="/app" size="lg" variant="thread">رفتن به میز کار</LinkButton>
            ) : (
              <>
                <LinkButton to="/signup" size="lg" variant="thread">رایگان امتحان کن</LinkButton>
                <LinkButton to="/login" size="lg" variant="outline">ورود</LinkButton>
              </>
            )}
          </div>
          <p className="mt-3 text-xs text-ink-400">با داده نمونه، کل مسیر در کمتر از یک دقیقه — بدون نیاز به فایل.</p>
        </div>
        <Card className="bg-white/80">
          <div className="mb-3 flex items-center gap-2 text-xs font-bold text-ink-500">
            <span className="h-2 w-2 animate-pulse rounded-full bg-thread-500" /> گزارش زنده عامل
          </div>
          <ol className="ms-2 space-y-2 border-s-2 border-dashed border-thread-300 ps-4 text-sm leading-7">
            {FEED.map((f) => <li key={f.t} className={f.c}>{f.t}</li>)}
          </ol>
        </Card>
      </section>

      <section className="py-8">
        <h2 className="mb-5 text-center text-2xl font-extrabold">چطور کار می‌کند؟</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["۱", "محصولت را توصیف کن", "عامل یکی دو سوال می‌پرسد و پروفایل مشتری ایده‌آل را می‌سازد؛ قابل ویرایش."],
            ["۲", "پیام‌های گروه را بده", "خروجی JSON تلگرام دسکتاپ، متن کپی‌شده، یا داده نمونه."],
            ["۳", "عامل با بودجه تو کار می‌کند", "پیش‌فیلتر معنایی، تریاژ ارزان، بررسی عمیق با ابزار، منتقد و پیش‌نویس پاسخ."],
            ["۴", "سرنخ‌ها با شواهد", "نمودار شش‌محوری، پیام‌های شاهد، دلیل ردها و هزینه هر مرحله."],
          ].map(([n, t, d]) => (
            <Card key={n}>
              <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-ink-900 text-sm font-bold text-white">{n}</div>
              <div className="font-extrabold">{t}</div>
              <p className="mt-1 text-sm leading-7 text-ink-600">{d}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="grid gap-4 py-6 md:grid-cols-3">
        {[
          ["💸", "حواسش به بودجه هست", "اول ارزان‌ترین فیلترها، بعد مدل قوی‌تر فقط برای امیدوارترین‌ها. وقتی بودجه تمام شود می‌ایستد و می‌گوید چه چیزی بررسی نشد."],
          ["🧶", "بدون شاهد، سرنخی نیست", "هر سرنخ با شماره پیام‌های شاهد می‌آید؛ کلیک کنید و همان پیام را در گفتگو ببینید. ردها هم دلیل دارند."],
          ["🤝", "اول کمک، بعد معرفی", "پاسخ‌ها اول به سوال فرد جواب می‌دهند. محصول فقط وقتی واقعا مناسب است و فقط با واقعیت‌های خودِ شما معرفی می‌شود."],
        ].map(([i, t, d]) => (
          <Card key={t} className="bg-ink-900 text-white">
            <div className="text-2xl" aria-hidden>{i}</div>
            <div className="mt-2 text-lg font-extrabold">{t}</div>
            <p className="mt-1 text-sm leading-7 text-ink-200">{d}</p>
          </Card>
        ))}
      </section>

      <section className="py-8 text-center">
        <h2 className="text-2xl font-extrabold">سر رشته را پیدا کن</h2>
        <p className="mx-auto mt-2 max-w-xl text-ink-600">ثبت‌نام کنید و روی گفتگوی نمونه ببینید عامل چطور مشتری‌ها را پیدا می‌کند.</p>
        <div className="mt-5">
          <LinkButton to={user ? "/app" : "/signup"} size="lg" variant="thread">شروع کن</LinkButton>
        </div>
      </section>
    </Layout>
  );
}
