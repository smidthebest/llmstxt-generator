import { BrowserRouter, Routes, Route, Link, useLocation, useParams } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import HomePage from "./pages/HomePage";
import SitePage from "./pages/SitePage";
import HistoryPage from "./pages/HistoryPage";

/** Wrapper that keys SitePage by :id so React fully remounts on site navigation */
function SitePageKeyed() {
  const { id } = useParams<{ id: string }>();
  return <SitePage key={id} />;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1 },
  },
});

function Layout() {
  const location = useLocation();
  const isHome = location.pathname === "/";

  return (
    <div className="min-h-screen">
      {!isHome && (
        <nav className="fixed top-0 left-0 right-0 z-50 bg-black/80 backdrop-blur-md border-b border-[#383838]">
          <div className="max-w-3xl mx-auto px-6 h-12 flex items-center justify-between">
            <Link to="/" className="font-display text-lg font-bold text-[#f0f0f0]">
              llms.txt
            </Link>
            <Link
              to="/history"
              className="text-xs tracking-widest uppercase text-[#ddd] hover:text-[#f0f0f0] transition-colors"
            >
              Sites
            </Link>
          </div>
        </nav>
      )}
      <main className={!isHome ? "pt-12" : ""}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/sites/:id" element={<SitePageKeyed />} />
          <Route path="/history" element={<HistoryPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
