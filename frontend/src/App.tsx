import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Empty, LinkButton, Loading } from "./components/ui";
import { AuthProvider, RequireAuth } from "./lib/auth";
import { Login, Signup } from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import DataStep from "./pages/DataStep";
import Landing from "./pages/Landing";
import NewSearch from "./pages/NewSearch";

// Chart-heavy pages (Recharts) load on demand so landing/sign-up stay light on slow connections.
const RunPage = lazy(() => import("./pages/RunPage"));
const LeadDetail = lazy(() => import("./pages/LeadDetail"));
const Evaluation = lazy(() => import("./pages/Evaluation"));
const ProductSetup = lazy(() => import("./pages/ProductSetup"));

function NotFound() {
  return (
    <Layout>
      <Empty icon="🪢" title="این رشته به جایی نمی‌رسد">صفحه‌ای که دنبالش بودید پیدا نشد.</Empty>
      <div className="mt-4 text-center"><LinkButton to="/">صفحه اصلی</LinkButton></div>
    </Layout>
  );
}

const guard = (el: React.ReactNode) => (
  <RequireAuth><Suspense fallback={<Loading />}>{el}</Suspense></RequireAuth>
);

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/app" element={guard(<Dashboard />)} />
          <Route path="/app/new" element={guard(<NewSearch />)} />
          <Route path="/app/products/:id" element={guard(<ProductSetup />)} />
          <Route path="/app/products/:id/data" element={guard(<DataStep />)} />
          <Route path="/app/runs/:id" element={guard(<RunPage />)} />
          <Route path="/app/runs/:id/leads/:msgId" element={guard(<LeadDetail />)} />
          <Route path="/app/eval" element={guard(<Evaluation />)} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
