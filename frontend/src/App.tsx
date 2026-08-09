import { Link, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import ProjectPage from "./pages/ProjectPage";
import VideoPage from "./pages/VideoPage";
import ModelsPage from "./pages/ModelsPage";

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-sea/10 bg-white/70 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link to="/" className="font-display text-2xl font-bold tracking-tight text-ink">
            OpenClip
          </Link>
          <nav className="flex gap-5 text-sm font-semibold text-sea">
            <Link to="/">Dashboard</Link>
            <Link to="/models">Models</Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8 animate-rise">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="/videos/:id" element={<VideoPage />} />
          <Route path="/models" element={<ModelsPage />} />
        </Routes>
      </main>
    </div>
  );
}
