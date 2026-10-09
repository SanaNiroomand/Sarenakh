import { Layout } from "../components/Layout";
import { LinkButton } from "../components/ui";
import { useAuth } from "../lib/auth";

// Placeholder landing page; the final design will replace this file.
export default function Landing() {
  const { user } = useAuth();
  return (
    <Layout>
      <section className="py-16 text-center">
        <h1 className="text-4xl font-extrabold">سرنخ</h1>
        <p className="mx-auto mt-4 max-w-xl leading-8 text-ink-600">
          سرنخ پیام‌های گروه‌های تلگرام را می‌خواند و کسانی را که به محصول شما نیاز دارند پیدا می‌کند.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          {user ? (
            <LinkButton to="/app">ورود به برنامه</LinkButton>
          ) : (
            <>
              <LinkButton to="/signup">ثبت‌نام</LinkButton>
              <LinkButton to="/login" variant="outline">ورود</LinkButton>
            </>
          )}
        </div>
      </section>
    </Layout>
  );
}
