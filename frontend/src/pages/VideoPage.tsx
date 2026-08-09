import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Clip, Job, Transcript, Video } from "../api";

export default function VideoPage() {
  const { id } = useParams();
  const [video, setVideo] = useState<Video | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [preset, setPreset] = useState("bold");
  const [smartCut, setSmartCut] = useState(true);

  const refreshMeta = async () => {
    if (!id) return;
    const v = await api.video(id);
    setVideo(v);
    try {
      setTranscript(await api.transcript(id));
    } catch {
      setTranscript(null);
    }
    try {
      setClips(await api.clips(id));
    } catch {
      setClips([]);
    }
  };

  useEffect(() => {
    void refreshMeta().catch((e) => setError(String(e)));
  }, [id]);

  useEffect(() => {
    if (!job || job.status === "COMPLETED" || job.status === "FAILED" || job.status === "CANCELLED") return;
    const t = setInterval(() => {
      void api.job(job.id).then(async (j) => {
        setJob(j);
        if (j.status === "COMPLETED") await refreshMeta();
      });
    }, 1500);
    return () => clearInterval(t);
  }, [job?.id, job?.status]);

  const progressLabel = useMemo(() => {
    if (!job) return null;
    return `${job.current_step || job.type} — ${job.progress}% (${job.status})`;
  }, [job]);

  const startPipeline = async () => {
    if (!id) return;
    setError(null);
    const j = await api.process(id, 3);
    setJob(j);
  };

  return (
    <div className="space-y-8">
      <div>
        <Link to="/" className="text-sm text-accent">← Dashboard</Link>
        <h1 className="font-display mt-2 text-3xl font-bold">{video?.filename || "Video"}</h1>
        <p className="text-sm text-sea/70">
          {video?.status} · {video?.width}x{video?.height} · {video?.duration?.toFixed?.(1)}s
        </p>
      </div>

      {id && (
        <video className="w-full max-w-3xl rounded-lg bg-black" controls src={api.mediaUrl(id)} />
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button className="rounded-md bg-ink px-4 py-2 font-semibold text-white" onClick={() => void startPipeline()}>
          Process → Shorts
        </button>
        <label className="text-sm">
          Caption preset
          <select className="ml-2 rounded border px-2 py-1" value={preset} onChange={(e) => setPreset(e.target.value)}>
            {["classic", "minimal", "bold", "karaoke", "neon", "box", "clean"].map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="text-sm flex items-center gap-2">
          <input type="checkbox" checked={smartCut} onChange={(e) => setSmartCut(e.target.checked)} />
          Smart cut (applied in edit plan)
        </label>
      </div>

      {progressLabel && (
        <div className="rounded-lg border border-accent/30 bg-white/80 p-4">
          <div className="mb-2 text-sm font-semibold">{progressLabel}</div>
          <div className="h-2 overflow-hidden rounded bg-sea/10">
            <div className="h-full bg-accent transition-all" style={{ width: `${job?.progress || 0}%` }} />
          </div>
          {job?.error?.message && <p className="mt-2 text-sm text-red-700">{job.error.message}</p>}
        </div>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}

      <section>
        <h2 className="font-display text-2xl font-semibold">Transcript</h2>
        {!transcript && <p className="text-sm text-sea/70 mt-2">Not ready yet.</p>}
        {transcript && (
          <div className="mt-3 max-h-72 overflow-auto rounded-lg bg-white/80 p-4 text-sm leading-relaxed">
            {transcript.segments.map((s, i) => (
              <p key={i} className="mb-2">
                <span className="text-sea/50 mr-2">{s.start.toFixed(1)}s</span>
                {s.words.map((w, j) => (
                  <span key={j} title={`${w.start}-${w.end}`} className="hover:bg-ember/30">
                    {w.word}{" "}
                  </span>
                ))}
              </p>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="font-display text-2xl font-semibold">Generated clips</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {clips.map((c) => (
            <article key={c.id} className="rounded-xl border border-sea/10 bg-white/90 p-4">
              <h3 className="font-semibold">{c.title || c.id}</h3>
              <p className="text-sm text-sea/70">
                {c.start.toFixed(1)}s → {c.end.toFixed(1)}s · Short-form Potential{" "}
                {(c.short_form_potential_score ?? c.score)?.toFixed?.(1) ?? "—"} · {c.status}
              </p>
              {typeof (c.score_breakdown as any)?.feature_scores === "object" && (
                <p className="mt-1 text-xs text-sea/60">
                  hook {String((c.score_breakdown as any).feature_scores.hook ?? "—")} · emotion{" "}
                  {String((c.score_breakdown as any).feature_scores.emotion ?? "—")} · curiosity{" "}
                  {String((c.score_breakdown as any).feature_scores.curiosity ?? "—")} · payoff{" "}
                  {String((c.score_breakdown as any).feature_scores.payoff ?? "—")}
                </p>
              )}
              {(c.selection_reasons?.length || (c.score_breakdown as any)?.selection_reasons) && (
                <ul className="mt-2 list-disc pl-5 text-xs text-sea/80">
                  {(c.selection_reasons || (c.score_breakdown as any).selection_reasons || []).map(
                    (r: string, i: number) => (
                      <li key={i}>{r}</li>
                    )
                  )}
                </ul>
              )}
              <div className="mt-3 flex gap-3 text-sm font-semibold">
                {c.render_path ? (
                  <a className="text-accent" href={api.downloadUrl(c.id)} target="_blank" rel="noreferrer">
                    Download
                  </a>
                ) : (
                  <button
                    className="text-accent"
                    onClick={() => void api.render(c.id).then(setJob)}
                  >
                    Render
                  </button>
                )}
              </div>
              {c.render_path && (
                <video className="mt-3 w-full rounded bg-black" controls src={api.downloadUrl(c.id)} />
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
