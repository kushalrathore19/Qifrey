const BASE = "/api";

export interface Story {
  id: number;
  title: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
  chapter_count?: number;
}

export interface Chapter {
  id: number;
  story_id: number;
  index: number;
  title: string;
  content_hash: string;
  analyzed_hash: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

export function fetchStories(): Promise<Story[]> {
  return request<Story[]>("/stories");
}

export function createStory(title: string): Promise<Story> {
  return request<Story>("/stories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export function uploadStory(file: File, title?: string): Promise<Story> {
  const form = new FormData();
  form.append("file", file);
  if (title) form.append("title", title);
  return request<Story>("/stories/upload", { method: "POST", body: form });
}

export function deleteStory(id: number): Promise<void> {
  return request<void>(`/stories/${id}`, { method: "DELETE" });
}

export function fetchChapters(storyId: number): Promise<Chapter[]> {
  return request<Chapter[]>(`/stories/${storyId}/chapters`);
}
