/**
 * Typed API client for the Qifrey backend.
 */
const BASE_URL = "/api";

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
  text?: string;
  summary?: string | null;
}

export interface CharacterBrief {
  id: number;
  story_id: number;
  canonical_name: string;
  description: string | null;
  aliases: string[];
  fact_count: number;
}

export interface Fact {
  id: number;
  attribute: string;
  value: string;
  chapter_id: number;
  quote: string | null;
  confidence: number;
}

export interface Relationship {
  id: number;
  type: string;
  source_character_id: number;
  target_character_id: number;
  chapter_id: number;
  quote: string | null;
}

export interface CharacterDetail {
  id: number;
  story_id: number;
  canonical_name: string;
  description: string | null;
  aliases: string[];
  facts: Fact[];
  relationships: Relationship[];
}

export type IssueType = "contradiction" | "grammar";
export type IssueStatus = "open" | "dismissed" | "accepted" | "intentional";

export interface Issue {
  id: number;
  story_id: number;
  type: IssueType;
  chapter_id: number | null;
  severity: string;
  message: string;
  quote: string | null;
  span_start: number | null;
  span_end: number | null;
  suggestions_json: string | null;
  related_fact_ids_json: string | null;
  status: IssueStatus;
  created_at: string;
}

export interface AnalysisStatus {
  story_id: number;
  status: "idle" | "running" | "completed" | "failed";
  current_chapter: number;
  total_chapters: number;
  error: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init);
  if (!res.ok) {
    const errorBody = await res
      .json()
      .catch(() => ({ detail: res.statusText }));
    throw new Error(errorBody.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export async function fetchStories(): Promise<Story[]> {
  return request<Story[]>("/stories");
}

export async function getStory(storyId: number): Promise<Story> {
  return request<Story>(`/stories/${storyId}`);
}

export async function createStory(title: string): Promise<Story> {
  return request<Story>("/stories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function uploadStory(file: File, title?: string): Promise<Story> {
  const form = new FormData();
  form.append("file", file);
  if (title) {
    form.append("title", title);
  }
  return request<Story>("/stories/upload", {
    method: "POST",
    body: form,
  });
}

export async function deleteStory(
  storyId: number,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/stories/${storyId}`, {
    method: "DELETE",
  });
}

export async function fetchChapters(storyId: number): Promise<Chapter[]> {
  return request<Chapter[]>(`/stories/${storyId}/chapters`);
}

export async function getChapter(chapterId: number): Promise<Chapter> {
  return request<Chapter>(`/chapters/${chapterId}`);
}

export async function analyzeStory(
  storyId: number,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/stories/${storyId}/analyze`, {
    method: "POST",
  });
}

export async function getAnalysisStatus(
  storyId: number,
): Promise<AnalysisStatus> {
  return request<AnalysisStatus>(`/stories/${storyId}/analysis-status`);
}

export async function fetchStoryCharacters(
  storyId: number,
): Promise<CharacterBrief[]> {
  return request<CharacterBrief[]>(`/stories/${storyId}/characters`);
}

export async function getCharacter(
  characterId: number,
): Promise<CharacterDetail> {
  return request<CharacterDetail>(`/characters/${characterId}`);
}

export async function fetchStoryIssues(
  storyId: number,
  params?: { type?: IssueType; status?: IssueStatus },
): Promise<Issue[]> {
  const query = new URLSearchParams();
  if (params?.type) query.append("type", params.type);
  if (params?.status) query.append("status", params.status);
  const qStr = query.toString();
  return request<Issue[]>(
    `/stories/${storyId}/issues${qStr ? `?${qStr}` : ""}`,
  );
}

export async function updateIssueStatus(
  issueId: number,
  status: IssueStatus,
): Promise<Issue> {
  return request<Issue>(`/issues/${issueId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}
