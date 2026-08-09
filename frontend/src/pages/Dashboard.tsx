import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Project } from "../api";

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [health, setHealth] = useState("…");
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [h, p] = await Promise.all([api.health(), api.projects()]);
      setHealth(h.status);
      setProjects(p);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await api.createProject(name.trim());
    setName("");
    await refresh();
  };

  return (
    <div className="space-y-8">
      <section>
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-accent">Local-first Shorts</p>
        <h1 className="font-display mt-2 text-4xl font-bold text-ink md:text-5xl">OpenClip</h1>
        <p className="mt-3 max-w-2xl text-lg text-sea/80">
          Upload long-form video. Generate ranked vertical Shorts on your machine — no paid AI APIs required.
        </p>
        <p className="mt-2 text-sm text-sea">API health: <strong>{health}</strong></p>
        {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      </section>

      <form onSubmit={onCreate} className="flex flex-wrap gap-3">
        <input
          className="min-w-[240px] flex-1 rounded-md border border-sea/20 bg-white px-3 py-2"
          placeholder="New project name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button className="rounded-md bg-ink px-4 py-2 font-semibold text-white" type="submit">
          Create project
        </button>
      </form>

      <section className="grid gap-4 md:grid-cols-2">
        {projects.map((p) => (
          <Link
            key={p.id}
            to={`/projects/${p.id}`}
            className="rounded-xl border border-sea/10 bg-white/80 p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
          >
            <h2 className="font-display text-xl font-semibold">{p.name}</h2>
            <p className="mt-1 text-sm text-sea/70">{new Date(p.created_at).toLocaleString()}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}
