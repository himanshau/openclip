import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Video } from "../api";

export default function ProjectPage() {
  const { id } = useParams();
  const [videos, setVideos] = useState<Video[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!id) return;
    void api
      .projects()
      .then(async () => {
        const res = await fetch(`/api/projects/${id}/videos`);
        if (res.ok) setVideos(await res.json());
      })
      .catch(() => undefined);
  }, [id]);

  const onUpload = async (file: File | null) => {
    if (!file || !id) return;
    setBusy(true);
    setMsg("Uploading…");
    try {
      const video = await api.upload(id, file);
      setVideos((v) => [video, ...v]);
      setMsg(`Uploaded ${video.filename} (${video.status}). Media job queued.`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-sm text-accent">← Dashboard</Link>
        <h1 className="font-display mt-2 text-3xl font-bold">Project</h1>
        <p className="text-sea/70 text-sm">{id}</p>
      </div>

      <label className="inline-flex cursor-pointer items-center gap-3 rounded-md bg-ink px-4 py-2 font-semibold text-white">
        {busy ? "Working…" : "Upload video"}
        <input
          type="file"
          accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
          className="hidden"
          disabled={busy}
          onChange={(e) => void onUpload(e.target.files?.[0] || null)}
        />
      </label>
      {msg && <p className="text-sm text-sea">{msg}</p>}

      <ul className="space-y-3">
        {videos.map((v) => (
          <li key={v.id} className="rounded-lg border border-sea/10 bg-white/80 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="font-semibold">{v.filename}</p>
                <p className="text-sm text-sea/70">{v.status}</p>
              </div>
              <Link className="text-accent font-semibold" to={`/videos/${v.id}`}>
                Open
              </Link>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
