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
  exclude_from_analysis?: boolean;
}

export interface CharacterBrief {
  id: number;
  story_id: number;
  canonical_name: string;
  description: string | null;
  aliases: string[];
  fact_count: number;
  source: "ai" | "manual";
  locked: boolean;
  status: "active" | "planned";
  notes: string | null;
  color: string | null;
  tags: string[];
}

export interface Fact {
  id: number;
  attribute: string;
  value: string;
  chapter_id: number | null;
  quote: string | null;
  confidence: number;
  source: "ai" | "manual";
  locked: boolean;
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
  source: "ai" | "manual";
  locked: boolean;
  status: "active" | "planned";
  notes: string | null;
  color: string | null;
  tags: string[];
  facts: Fact[];
  relationships: Relationship[];
}

export interface AttributeRule {
  id?: number;
  attribute: string;
  mode: "strict" | "can_change" | "ignore";
}

export interface StorySettings {
  confidence_threshold: number;
  grammar_language: string;
  disabled_grammar_rules: string[];
}

export interface CharacterCreateInput {
  canonical_name: string;
  description?: string | null;
  aliases?: string[];
  source?: "ai" | "manual";
  locked?: boolean;
  status?: "active" | "planned";
  notes?: string | null;
  color?: string | null;
  tags?: string[];
  initial_facts?: Array<{
    attribute: string;
    value: string;
    quote?: string | null;
    chapter_id?: number | null;
    confidence?: number;
    locked?: boolean;
  }>;
}

export interface CharacterUpdateInput {
  canonical_name?: string;
  description?: string | null;
  status?: "active" | "planned";
  notes?: string | null;
  color?: string | null;
  tags?: string[];
  locked?: boolean;
}

export interface FactCreateInput {
  attribute: string;
  value: string;
  quote?: string | null;
  chapter_id?: number | null;
  confidence?: number;
  locked?: boolean;
}

export interface FactUpdateInput {
  attribute?: string;
  value?: string;
  quote?: string | null;
  confidence?: number;
  locked?: boolean;
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

export interface GrammarIssue {
  message: string;
  rule_id: string;
  span_start: number;
  span_end: number;
  quote: string;
  suggestions: string[];
}

export interface AnalysisStatus {
  story_id: number;
  status:
    | "idle"
    | "running"
    | "waiting on rate limit"
    | "waiting on provider"
    | "completed"
    | "failed";
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

export async function createChapter(
  storyId: number,
  data?: { title?: string; text?: string; index?: number },
): Promise<Chapter> {
  return request<Chapter>(`/stories/${storyId}/chapters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
  });
}

export async function updateChapter(
  chapterId: number,
  data: {
    title?: string;
    text?: string;
    index?: number;
    exclude_from_analysis?: boolean;
  },
): Promise<Chapter> {
  return request<Chapter>(`/chapters/${chapterId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteChapter(
  chapterId: number,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/chapters/${chapterId}`, {
    method: "DELETE",
  });
}

export async function checkChapterGrammar(
  chapterId: number,
  text?: string,
): Promise<GrammarIssue[]> {
  return request<GrammarIssue[]>(`/chapters/${chapterId}/grammar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export async function createCharacter(
  storyId: number,
  data: CharacterCreateInput,
): Promise<CharacterDetail> {
  return request<CharacterDetail>(`/stories/${storyId}/characters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateCharacter(
  characterId: number,
  data: CharacterUpdateInput,
): Promise<CharacterDetail> {
  return request<CharacterDetail>(`/characters/${characterId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteCharacter(
  characterId: number,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/characters/${characterId}`, {
    method: "DELETE",
  });
}

export async function addAlias(
  characterId: number,
  name: string,
): Promise<{ id: number; character_id: number; name: string; source: string }> {
  return request<{ id: number; character_id: number; name: string; source: string }>(
    `/characters/${characterId}/aliases`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    },
  );
}

export async function deleteAlias(
  aliasId: number,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/aliases/${aliasId}`, {
    method: "DELETE",
  });
}

export async function addFact(
  characterId: number,
  data: FactCreateInput,
): Promise<Fact> {
  return request<Fact>(`/characters/${characterId}/facts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateFact(
  factId: number,
  data: FactUpdateInput,
): Promise<Fact> {
  return request<Fact>(`/facts/${factId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteFact(
  factId: number,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/facts/${factId}`, {
    method: "DELETE",
  });
}

export async function mergeCharacters(
  storyId: number,
  sourceIds: number[],
  targetId: number,
): Promise<CharacterDetail> {
  return request<CharacterDetail>(`/stories/${storyId}/characters/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_ids: sourceIds, target_id: targetId }),
  });
}

export async function ignoreCharacter(
  characterId: number,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/characters/${characterId}/ignore`, {
    method: "POST",
  });
}

export async function getAttributeRules(
  storyId: number,
): Promise<AttributeRule[]> {
  return request<AttributeRule[]>(`/stories/${storyId}/attribute-rules`);
}

export async function updateAttributeRules(
  storyId: number,
  rules: AttributeRule[],
): Promise<AttributeRule[]> {
  return request<AttributeRule[]>(`/stories/${storyId}/attribute-rules`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rules),
  });
}

export async function getStorySettings(
  storyId: number,
): Promise<StorySettings> {
  return request<StorySettings>(`/stories/${storyId}/settings`);
}

export async function updateStorySettings(
  storyId: number,
  data: Partial<StorySettings>,
): Promise<StorySettings> {
  return request<StorySettings>(`/stories/${storyId}/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function getExportUrl(storyId: number, format: "json" | "md"): string {
  return `${BASE_URL}/stories/${storyId}/export?format=${format}`;
}

export async function importStoryBible(
  storyId: number,
  data: unknown,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/stories/${storyId}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}
