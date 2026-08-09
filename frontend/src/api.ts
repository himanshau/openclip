const API = "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export type Project = { id: string; name: string; description?: string; created_at: string };
export type Video = {
  id: string;
  project_id: string;
  filename: string;
  status: string;
  duration?: number;
  width?: number;
  height?: number;
  thumbnail_path?: string;
};
export type Job = {
  id: string;
  type: string;
  status: string;
  progress: number;
  current_step?: string;
  error?: { message?: string };
};
export type Clip = {
  id: string;
  title?: string;
  start: number;
  end: number;
  score?: number;
  score_breakdown?: Record<string, unknown>;
  status: string;
  render_path?: string;
  edit_plan?: Record<string, unknown>;
  selection_reasons?: string[];
  short_form_potential_score?: number;
};
export type Transcript = {
  id: string;
  text: string;
  language?: string;
  segments: { start: number; end: number; text: string; words: { word: string; start: number; end: number }[] }[];
};

export const api = {
  health: () => req<{ status: string }>("/health"),
  system: () => req<Record<string, unknown>>("/api/system/status"),
  projects: () => req<Project[]>("/api/projects"),
  createProject: (name: string) =>
    req<Project>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  upload: async (projectId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<Video>(`/api/projects/${projectId}/videos`, { method: "POST", body: fd });
  },
  video: (id: string) => req<Video>(`/api/videos/${id}`),
  process: (id: string, top_n = 3) =>
    req<Job>(`/api/videos/${id}/process`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ top_n }),
    }),
  job: (id: string) => req<Job>(`/api/jobs/${id}`),
  transcript: (videoId: string) => req<Transcript>(`/api/videos/${videoId}/transcript`),
  clips: (videoId: string) => req<Clip[]>(`/api/videos/${videoId}/clips`),
  render: (clipId: string) => req<Job>(`/api/clips/${clipId}/render`, { method: "POST" }),
  presets: () => req<{ name: string }[]>("/api/caption-presets"),
  downloadUrl: (clipId: string) => `/api/renders/${clipId}`,
  mediaUrl: (videoId: string) => `/api/media/${videoId}/original`,
};
