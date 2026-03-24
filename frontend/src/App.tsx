import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NavBar } from "./components/NavBar";
import { Dashboard } from "./pages/Dashboard";
import { NewJob } from "./pages/NewJob";
import { FilesBrowser } from "./pages/FilesBrowser";
import { FileDetailPage } from "./pages/FileDetailPage";
import { SecretsPage } from "./pages/SecretsPage";
import { SemanticSearchPage } from "./pages/SemanticSearchPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div style={{ minHeight: "100vh", background: "#1e1e2e", color: "#cdd6f4", fontFamily: "system-ui, sans-serif" }}>
          <NavBar />
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/jobs/new" element={<NewJob />} />
            <Route path="/files" element={<FilesBrowser />} />
            <Route path="/files/:id" element={<FileDetailPage />} />
            <Route path="/secrets" element={<SecretsPage />} />
            <Route path="/search" element={<SemanticSearchPage />} />
          </Routes>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
