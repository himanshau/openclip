import { useEffect, useState } from "react";
import { api } from "../api";

export default function ModelsPage() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api
      .system()
      .then(setStatus)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="text-red-700">{error}</p>;
  if (!status) return <p>Loading system status…</p>;

  const models = (status.models as { name: string; installed: boolean; detail?: string }[]) || [];
  const gpu = status.gpu as { available: boolean; vram_used_mb?: number; vram_total_mb?: number };
  const ffmpeg = status.ffmpeg as { ffmpeg_installed: boolean; version?: string };
  const workers = status.workers as { reachable: boolean; detail?: string };

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl font-bold">Model & system status</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl bg-white/80 p-4 border border-sea/10">
          <h2 className="font-semibold">GPU</h2>
          <p>available: {String(gpu?.available)}</p>
          <p>
            VRAM: {gpu?.vram_used_mb ?? "—"} / {gpu?.vram_total_mb ?? "—"} MB
          </p>
          <p>CPU: {String(status.cpu_percent)}%</p>
          <p>
            RAM: {String(status.ram_used_mb)} / {String(status.ram_total_mb)} MB
          </p>
        </div>
        <div className="rounded-xl bg-white/80 p-4 border border-sea/10">
          <h2 className="font-semibold">Runtime</h2>
          <p>FFmpeg: {ffmpeg?.ffmpeg_installed ? ffmpeg.version || "yes" : "missing"}</p>
          <p>Workers: {workers?.reachable ? "reachable" : workers?.detail || "down"}</p>
        </div>
      </div>
      <ul className="space-y-2">
        {models.map((m) => (
          <li key={m.name} className="rounded-lg bg-white/80 px-4 py-3 border border-sea/10">
            <strong>{m.name}</strong>: {m.installed ? "installed" : "not installed"}
            {m.detail ? <span className="text-sea/60 text-sm"> — {m.detail}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
