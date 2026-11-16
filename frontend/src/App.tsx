import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "./context/ThemeContext";
import { ToastProvider } from "./context/ToastContext";
import { Navbar } from "./components/Navbar";
import { Library } from "./pages/Library";
import { StoryProfile } from "./pages/StoryProfile";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5_000,
      refetchOnWindowFocus: false,
    },
  },
});

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <BrowserRouter>
            <div className="min-h-screen flex flex-col bg-stone-50 text-stone-800 dark:bg-stone-950 dark:text-stone-100 transition-colors font-sans">
              <Navbar />
              <div className="flex-1">
                <Routes>
                  <Route path="/" element={<Library />} />
                  <Route path="/stories/:id" element={<StoryProfile />} />
                </Routes>
              </div>
            </div>
          </BrowserRouter>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
};

export default App;
