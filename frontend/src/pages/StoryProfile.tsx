import React, { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Sparkles,
  Users,
  Layers,
  Loader2,
  AlertCircle,
  Play,
  CheckCircle2,
  BookOpen,
  PenSquare,
  Settings,
  Plus,
  Lock,
  GitMerge,
  X,
  Check,
  Clock,
} from "lucide-react";
import {
  getStory,
  getAnalysisStatus,
  analyzeStory,
  fetchStoryCharacters,
  createCharacter,
  mergeCharacters,
  type CharacterBrief,
  type CharacterCreateInput,
} from "../api/client";
import { SidebarTabs } from "../components/SidebarTabs";
import { CharacterDrawer } from "../components/CharacterDrawer";
import { useToast } from "../context/ToastContext";

const STANDARD_ATTRIBUTES = [
  "eye_color",
  "hair_color",
  "hair_style",
  "clothing",
  "height",
  "age",
  "origin",
  "occupation",
  "relationship",
  "weapon",
  "scar",
  "mood",
];

export const StoryProfile: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const storyId = Number(id);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [selectedCharacterId, setSelectedCharacterId] = useState<number | null>(
    null,
  );

  // Multi-select for character merging
  const [selectedCharIds, setSelectedCharIds] = useState<number[]>([]);
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [mergeTargetId, setMergeTargetId] = useState<number | null>(null);

  // Add Character Modal state
  const [showAddCharModal, setShowAddCharModal] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newNotes, setNewNotes] = useState("");
  const [newStatus, setNewStatus] = useState<"active" | "planned">("active");
  const [newLocked, setNewLocked] = useState(false);
  const [newColor, setNewColor] = useState("#b45309");
  const [newAliases, setNewAliases] = useState<string[]>([]);
  const [newAliasInput, setNewAliasInput] = useState("");
  const [newTags, setNewTags] = useState<string[]>([]);
  const [newTagInput, setNewTagInput] = useState("");
  const [initialFacts, setInitialFacts] = useState<
    Array<{ attribute: string; value: string; locked: boolean }>
  >([]);
  const [newAttrKey, setNewAttrKey] = useState("");
  const [newAttrVal, setNewAttrVal] = useState("");

  // Fetch Story metadata
  const {
    data: story,
    isLoading: isStoryLoading,
    error: storyError,
  } = useQuery({
    queryKey: ["story", storyId],
    queryFn: () => getStory(storyId),
    enabled: !isNaN(storyId),
  });

  // Fetch Characters
  const { data: characters = [], isLoading: isCharsLoading } = useQuery({
    queryKey: ["characters", storyId],
    queryFn: () => fetchStoryCharacters(storyId),
    enabled: !isNaN(storyId),
  });

  // Fetch Analysis Status with conditional polling
  const { data: analysisStatus } = useQuery({
    queryKey: ["analysis-status", storyId],
    queryFn: () => getAnalysisStatus(storyId),
    enabled: !isNaN(storyId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" ||
        status === "waiting on rate limit" ||
        status === "waiting on provider"
        ? 1500
        : false;
    },
  });

  // Watch for completion of running analysis to invalidate story & characters
  React.useEffect(() => {
    if (analysisStatus?.status === "completed") {
      queryClient.invalidateQueries({ queryKey: ["story", storyId] });
      queryClient.invalidateQueries({ queryKey: ["characters", storyId] });
      queryClient.invalidateQueries({ queryKey: ["issues", storyId] });
    }
  }, [analysisStatus?.status, queryClient, storyId]);

  // Trigger analysis mutation
  const analyzeMutation = useMutation({
    mutationFn: () => analyzeStory(storyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analysis-status", storyId] });
      toast("Analysis started in background...", "info");
    },
    onError: (err) => {
      toast(`Failed to start analysis: ${(err as Error).message}`, "error");
    },
  });

  // Create character mutation
  const createCharMutation = useMutation({
    mutationFn: (data: CharacterCreateInput) => createCharacter(storyId, data),
    onSuccess: (newChar) => {
      setShowAddCharModal(false);
      resetAddCharForm();
      queryClient.invalidateQueries({ queryKey: ["characters", storyId] });
      toast(`Character "${newChar.canonical_name}" added to story bible.`, "success");
      setSelectedCharacterId(newChar.id);
    },
    onError: (err) => {
      toast(`Failed to create character: ${(err as Error).message}`, "error");
    },
  });

  // Merge characters mutation
  const mergeMutation = useMutation({
    mutationFn: ({
      sourceIds,
      targetId,
    }: {
      sourceIds: number[];
      targetId: number;
    }) => mergeCharacters(storyId, sourceIds, targetId),
    onSuccess: (target) => {
      setShowMergeModal(false);
      setSelectedCharIds([]);
      setMergeTargetId(null);
      queryClient.invalidateQueries({ queryKey: ["characters", storyId] });
      queryClient.invalidateQueries({ queryKey: ["issues", storyId] });
      toast(`Merged characters into "${target.canonical_name}".`, "success");
    },
    onError: (err) => {
      toast(`Merge failed: ${(err as Error).message}`, "error");
    },
  });

  const resetAddCharForm = () => {
    setNewName("");
    setNewDesc("");
    setNewNotes("");
    setNewStatus("active");
    setNewLocked(false);
    setNewColor("#b45309");
    setNewAliases([]);
    setNewAliasInput("");
    setNewTags([]);
    setNewTagInput("");
    setInitialFacts([]);
    setNewAttrKey("");
    setNewAttrVal("");
  };

  const handleAddAlias = () => {
    const a = newAliasInput.trim();
    if (!a || newAliases.includes(a)) return;
    setNewAliases([...newAliases, a]);
    setNewAliasInput("");
  };

  const handleAddTag = () => {
    const t = newTagInput.trim().toLowerCase();
    if (!t || newTags.includes(t)) return;
    setNewTags([...newTags, t]);
    setNewTagInput("");
  };

  const handleAddInitialFact = () => {
    if (!newAttrKey.trim() || !newAttrVal.trim()) return;
    setInitialFacts([
      ...initialFacts,
      {
        attribute: newAttrKey.trim().toLowerCase(),
        value: newAttrVal.trim(),
        locked: true,
      },
    ]);
    setNewAttrKey("");
    setNewAttrVal("");
  };

  const toggleSelectChar = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (selectedCharIds.includes(id)) {
      setSelectedCharIds(selectedCharIds.filter((x) => x !== id));
    } else {
      setSelectedCharIds([...selectedCharIds, id]);
    }
  };

  const isAnalyzing =
    analysisStatus?.status === "running" ||
    analysisStatus?.status === "waiting on rate limit" ||
    analysisStatus?.status === "waiting on provider" ||
    analyzeMutation.isPending;

  if (isNaN(storyId)) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center text-rose-600">
        Invalid story ID.
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col overflow-hidden">
      {/* Top Story Header */}
      <div className="border-b border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 px-6 py-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 z-10 shrink-0">
        <div className="flex items-center gap-4">
          <Link
            to="/"
            className="p-2 rounded-xl text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
            title="Back to Library"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="font-serif text-2xl font-bold text-stone-900 dark:text-stone-100 line-clamp-1">
              {isStoryLoading ? "Loading story..." : story?.title}
            </h1>
            <div className="flex items-center gap-3 text-xs text-stone-500 dark:text-stone-400 mt-0.5">
              <span className="flex items-center gap-1 font-medium">
                <Layers className="w-3.5 h-3.5" />
                {story?.chapter_count ?? 0} chapter
                {(story?.chapter_count ?? 0) === 1 ? "" : "s"}
              </span>
              <span>•</span>
              <span className="flex items-center gap-1 font-medium">
                <Users className="w-3.5 h-3.5" />
                {characters.length} character
                {characters.length === 1 ? "" : "s"}
              </span>
            </div>
          </div>
        </div>

        {/* Action / Status Controls */}
        <div className="flex items-center gap-3 w-full sm:w-auto justify-end flex-wrap">
          {/* Analysis progress indicator */}
          {analysisStatus && analysisStatus.status === "waiting on rate limit" && (
            <div className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-xl bg-amber-100 dark:bg-amber-950/80 border border-amber-300 dark:border-amber-800 text-amber-900 dark:text-amber-200 text-xs font-semibold animate-pulse">
              <Clock className="w-3.5 h-3.5 text-amber-700 animate-spin" />
              <span>Waiting on rate limit (cooling down)...</span>
            </div>
          )}

          {analysisStatus && analysisStatus.status === "waiting on provider" && (
            <div className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-xl bg-amber-100 dark:bg-amber-950/80 border border-amber-300 dark:border-amber-800 text-amber-900 dark:text-amber-200 text-xs font-semibold animate-pulse">
              <Clock className="w-3.5 h-3.5 text-amber-700 animate-spin" />
              <span>Waiting on provider (retrying)...</span>
            </div>
          )}

          {analysisStatus && analysisStatus.status === "running" && (
            <div className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-xl bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-900/60 text-amber-800 dark:text-amber-200 text-xs font-medium animate-pulse">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-600" />
              <span>
                Analyzing chapter {analysisStatus.current_chapter} of{" "}
                {analysisStatus.total_chapters}...
              </span>
            </div>
          )}

          {analysisStatus &&
            analysisStatus.status === "completed" &&
            !isAnalyzing && (
              <div className="hidden sm:flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400 font-medium px-2.5 py-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>Graph up to date</span>
              </div>
            )}

          <Link
            to={`/stories/${storyId}/settings`}
            className="px-3 py-2 rounded-xl border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 hover:bg-stone-100 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-200 text-sm font-medium shadow-xs flex items-center gap-1.5 transition-all"
            title="Story Settings & Bible Rules"
          >
            <Settings className="w-4 h-4 text-stone-500 dark:text-stone-400" />
            <span className="hidden md:inline">Settings</span>
          </Link>

          <Link
            to={`/stories/${storyId}/edit`}
            className="px-3.5 py-2 rounded-xl border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 hover:bg-stone-100 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-200 text-sm font-medium shadow-xs flex items-center gap-2 transition-all"
          >
            <PenSquare className="w-4 h-4 text-stone-500 dark:text-stone-400" />
            <span>Open in editor</span>
          </Link>

          <button
            onClick={() => analyzeMutation.mutate()}
            disabled={isAnalyzing}
            className="px-4 py-2 rounded-xl bg-amber-700 hover:bg-amber-800 text-white text-sm font-medium shadow-xs disabled:opacity-50 flex items-center gap-2 transition-all cursor-pointer"
          >
            {isAnalyzing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Analyzing...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-white" />
                <span>Analyze Story</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Main Workspace Layout (Main panel + Right sidebar) */}
      <div className="flex-1 flex overflow-hidden">
        {/* Main Center Panel */}
        <main className="flex-1 overflow-y-auto p-6 lg:p-8 space-y-8 bg-stone-50 dark:bg-stone-950">
          {isStoryLoading && (
            <div className="py-24 flex flex-col items-center justify-center text-stone-400 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-amber-700" />
              <p className="text-sm">Loading story profile...</p>
            </div>
          )}

          {storyError && (
            <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-900 text-rose-800 dark:text-rose-200 text-sm flex items-center gap-2">
              <AlertCircle className="w-4 h-4" />
              <span>Failed to load story: {(storyError as Error).message}</span>
            </div>
          )}

          {story && (
            <>
              {/* AI Narrative Summary Card */}
              <section className="bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800 p-6 shadow-xs relative overflow-hidden">
                <div className="absolute top-0 left-0 w-1.5 h-full bg-amber-600 dark:bg-amber-500" />
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-800 dark:text-amber-400 mb-2.5">
                  <BookOpen className="w-4 h-4" />
                  <span>Story Summary</span>
                </div>

                {story.summary ? (
                  <p className="font-serif text-base sm:text-lg text-stone-800 dark:text-stone-200 leading-relaxed">
                    {story.summary}
                  </p>
                ) : (
                  <div className="py-4 text-stone-400 dark:text-stone-500 text-sm italic flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-stone-300 dark:text-stone-600" />
                    <span>
                      No summary generated yet. Click{" "}
                      <strong>Analyze Story</strong> to build the world memory
                      and generate summaries.
                    </span>
                  </div>
                )}
              </section>

              {/* Characters Section */}
              <section>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                  <div>
                    <h2 className="font-serif text-xl font-bold text-stone-900 dark:text-stone-100">
                      Story Bible & Characters
                    </h2>
                    <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
                      Author-managed profiles, AI extracted facts, aliases, and notes.
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    {selectedCharIds.length >= 2 && (
                      <button
                        onClick={() => {
                          setMergeTargetId(selectedCharIds[0]);
                          setShowMergeModal(true);
                        }}
                        className="px-3.5 py-1.5 rounded-xl bg-purple-700 hover:bg-purple-800 text-white text-xs font-semibold shadow-xs flex items-center gap-1.5 cursor-pointer animate-in fade-in"
                      >
                        <GitMerge className="w-3.5 h-3.5" />
                        <span>Merge Selected ({selectedCharIds.length})</span>
                      </button>
                    )}

                    <button
                      onClick={() => setShowAddCharModal(true)}
                      className="px-3.5 py-1.5 rounded-xl bg-amber-700 hover:bg-amber-800 text-white text-xs font-semibold shadow-xs flex items-center gap-1.5 cursor-pointer transition-colors"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>Add Character</span>
                    </button>
                  </div>
                </div>

                {isCharsLoading && (
                  <div className="py-12 flex justify-center text-stone-400">
                    <Loader2 className="w-6 h-6 animate-spin text-amber-700" />
                  </div>
                )}

                {!isCharsLoading && characters.length === 0 && (
                  <div className="py-12 text-center rounded-2xl border border-dashed border-stone-200 dark:border-stone-800 p-8 bg-white/50 dark:bg-stone-900/40">
                    <Users className="w-10 h-10 mx-auto text-stone-300 dark:text-stone-700 mb-2 stroke-1" />
                    <p className="text-sm font-medium text-stone-700 dark:text-stone-300">
                      No characters in story bible
                    </p>
                    <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">
                      Add a manual character using the button above, or click "Analyze Story" to extract them from your text.
                    </p>
                  </div>
                )}

                {characters.length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {characters.map((char: CharacterBrief) => {
                      const isSelected = selectedCharIds.includes(char.id);
                      return (
                        <div
                          key={char.id}
                          onClick={() => setSelectedCharacterId(char.id)}
                          className={`p-5 rounded-2xl border bg-white dark:bg-stone-900 transition-all cursor-pointer flex flex-col justify-between group relative overflow-hidden ${
                            isSelected
                              ? "border-purple-600 ring-2 ring-purple-600/30 dark:border-purple-500 shadow-md"
                              : "border-stone-200 dark:border-stone-800 hover:border-amber-400/80 dark:hover:border-amber-600/80 hover:shadow-md"
                          }`}
                        >
                          <div>
                            {/* Card Top Row: Checkbox, Name, Badges */}
                            <div className="flex items-start justify-between gap-2 mb-2">
                              <div className="flex items-start gap-2.5">
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={() => {}}
                                  onClick={(e) => toggleSelectChar(char.id, e)}
                                  className="mt-1 accent-purple-600 rounded-sm cursor-pointer"
                                  title="Select to merge"
                                />

                                <div>
                                  <h3 className="font-serif text-lg font-bold text-stone-900 dark:text-stone-100 group-hover:text-amber-800 dark:group-hover:text-amber-400 transition-colors">
                                    {char.canonical_name}
                                  </h3>

                                  {/* Badges */}
                                  <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                                    <span
                                      className={`text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.2 rounded-sm ${
                                        char.source === "manual"
                                          ? "bg-amber-100 dark:bg-amber-950/80 text-amber-900 dark:text-amber-200 border border-amber-300 dark:border-amber-800"
                                          : "bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-300 border border-stone-200 dark:border-stone-700"
                                      }`}
                                    >
                                      {char.source === "manual" ? "Manual" : "AI"}
                                    </span>

                                    {char.status === "planned" && (
                                      <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.2 rounded-sm bg-purple-100 dark:bg-purple-950 text-purple-800 dark:text-purple-300 border border-purple-300 dark:border-purple-800">
                                        Planned
                                      </span>
                                    )}

                                    {char.locked && (
                                      <span
                                        title="Locked against overwrite"
                                        className="text-amber-700 dark:text-amber-400"
                                      >
                                        <Lock className="w-3 h-3" />
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>

                              <span className="text-[11px] font-semibold text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/60 px-2 py-0.5 rounded-md shrink-0">
                                {char.fact_count} fact
                                {char.fact_count === 1 ? "" : "s"}
                              </span>
                            </div>

                            {char.aliases && char.aliases.length > 0 && (
                              <div className="flex flex-wrap gap-1 mb-2.5">
                                {char.aliases.slice(0, 3).map((a, idx) => (
                                  <span
                                    key={idx}
                                    className="text-[10px] font-medium bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-400 px-2 py-0.5 rounded"
                                  >
                                    {a}
                                  </span>
                                ))}
                                {char.aliases.length > 3 && (
                                  <span className="text-[10px] text-stone-400">
                                    +{char.aliases.length - 3} more
                                  </span>
                                )}
                              </div>
                            )}

                            {char.description && (
                              <p className="text-xs text-stone-600 dark:text-stone-400 line-clamp-2 leading-relaxed italic mb-1">
                                "{char.description}"
                              </p>
                            )}

                            {char.notes && (
                              <p className="text-[11px] text-amber-900/80 dark:text-amber-300/80 line-clamp-1 italic">
                                Notes: {char.notes}
                              </p>
                            )}
                          </div>

                          <div className="pt-3 mt-3 border-t border-stone-100 dark:border-stone-800/80 flex items-center justify-between text-xs text-amber-700 dark:text-amber-400 font-medium">
                            <span>Open character drawer →</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            </>
          )}
        </main>

        {/* Right Sidebar: Contradictions & Grammar Tabs */}
        <SidebarTabs storyId={storyId} />
      </div>

      {/* Character Drawer */}
      <CharacterDrawer
        characterId={selectedCharacterId}
        onClose={() => setSelectedCharacterId(null)}
        onUpdated={() => {
          queryClient.invalidateQueries({ queryKey: ["characters", storyId] });
        }}
      />

      {/* Add Character Modal */}
      {showAddCharModal && (
        <div className="fixed inset-0 z-50 bg-stone-900/50 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in">
          <div className="bg-white dark:bg-stone-900 w-full max-w-lg rounded-2xl shadow-2xl border border-stone-200 dark:border-stone-800 p-6 space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-stone-100 dark:border-stone-800 pb-3">
              <h3 className="font-serif text-xl font-bold text-stone-900 dark:text-stone-100">
                Add Story Bible Character
              </h3>
              <button
                onClick={() => setShowAddCharModal(false)}
                className="p-1 rounded-lg text-stone-400 hover:text-stone-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                Canonical Name *
              </label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Maria Chen"
                className="w-full px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                Description
              </label>
              <textarea
                rows={2}
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Brief narrative role or background..."
                className="w-full px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                Author Notes (Bible)
              </label>
              <textarea
                rows={2}
                value={newNotes}
                onChange={(e) => setNewNotes(e.target.value)}
                placeholder="Private author notes, arcs, secrets..."
                className="w-full px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                  Status
                </label>
                <select
                  value={newStatus}
                  onChange={(e) =>
                    setNewStatus(e.target.value as "active" | "planned")
                  }
                  className="w-full px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
                >
                  <option value="active">Active</option>
                  <option value="planned">Planned (not yet in text)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                  Card Color
                </label>
                <input
                  type="color"
                  value={newColor}
                  onChange={(e) => setNewColor(e.target.value)}
                  className="w-full h-8 rounded-xl border border-stone-300 dark:border-stone-700 p-1 cursor-pointer bg-white dark:bg-stone-900"
                />
              </div>
            </div>

            {/* Aliases */}
            <div>
              <label className="block text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                Aliases & Titles
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={newAliasInput}
                  onChange={(e) => setNewAliasInput(e.target.value)}
                  placeholder="e.g. Dr. Chen"
                  className="flex-1 px-3 py-1 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
                />
                <button
                  type="button"
                  onClick={handleAddAlias}
                  className="px-3 py-1 rounded-xl bg-stone-200 dark:bg-stone-800 text-xs font-medium cursor-pointer"
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {newAliases.map((a) => (
                  <span
                    key={a}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] bg-stone-100 dark:bg-stone-800"
                  >
                    <span>{a}</span>
                    <button
                      onClick={() =>
                        setNewAliases(newAliases.filter((x) => x !== a))
                      }
                      className="text-stone-400 hover:text-rose-600"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>

            {/* Tags */}
            <div>
              <label className="block text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                Tags
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={newTagInput}
                  onChange={(e) => setNewTagInput(e.target.value)}
                  placeholder="e.g. protagonist, detective"
                  className="flex-1 px-3 py-1 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
                />
                <button
                  type="button"
                  onClick={handleAddTag}
                  className="px-3 py-1 rounded-xl bg-stone-200 dark:bg-stone-800 text-xs font-medium cursor-pointer"
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {newTags.map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] bg-stone-100 dark:bg-stone-800"
                  >
                    <span>#{t}</span>
                    <button
                      onClick={() => setNewTags(newTags.filter((x) => x !== t))}
                      className="text-stone-400 hover:text-rose-600"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>

            {/* Initial Facts */}
            <div>
              <label className="block text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                Initial Attributes & Facts
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  list="new-char-attr-vocab"
                  value={newAttrKey}
                  onChange={(e) => setNewAttrKey(e.target.value)}
                  placeholder="Attribute (e.g. eye_color)"
                  className="flex-1 px-2.5 py-1 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
                />
                <datalist id="new-char-attr-vocab">
                  {STANDARD_ATTRIBUTES.map((a) => (
                    <option key={a} value={a} />
                  ))}
                </datalist>

                <input
                  type="text"
                  value={newAttrVal}
                  onChange={(e) => setNewAttrVal(e.target.value)}
                  placeholder="Value (e.g. brown)"
                  className="flex-1 px-2.5 py-1 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
                />

                <button
                  type="button"
                  onClick={handleAddInitialFact}
                  className="px-3 py-1 rounded-xl bg-stone-200 dark:bg-stone-800 text-xs font-medium cursor-pointer"
                >
                  Add
                </button>
              </div>

              <div className="space-y-1">
                {initialFacts.map((f, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 rounded-lg bg-stone-50 dark:bg-stone-950 text-xs"
                  >
                    <span>
                      <strong>{f.attribute}</strong>: {f.value}
                    </span>
                    <button
                      onClick={() =>
                        setInitialFacts(initialFacts.filter((_, i) => i !== idx))
                      }
                      className="text-stone-400 hover:text-rose-600"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-3 border-t border-stone-100 dark:border-stone-800 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowAddCharModal(false)}
                className="px-3.5 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 text-xs font-medium cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  createCharMutation.mutate({
                    canonical_name: newName.trim(),
                    description: newDesc.trim() || null,
                    notes: newNotes.trim() || null,
                    status: newStatus,
                    locked: newLocked,
                    color: newColor,
                    aliases: newAliases,
                    tags: newTags,
                    initial_facts: initialFacts,
                  });
                }}
                disabled={!newName.trim() || createCharMutation.isPending}
                className="px-4 py-1.5 rounded-xl bg-amber-700 hover:bg-amber-800 disabled:opacity-50 text-white text-xs font-semibold shadow-xs flex items-center gap-1.5 cursor-pointer"
              >
                {createCharMutation.isPending ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Check className="w-3.5 h-3.5" />
                )}
                <span>Create Character</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Merge Characters Modal */}
      {showMergeModal && (
        <div className="fixed inset-0 z-50 bg-stone-900/50 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in">
          <div className="bg-white dark:bg-stone-900 w-full max-w-md rounded-2xl shadow-2xl border border-stone-200 dark:border-stone-800 p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-stone-100 dark:border-stone-800 pb-3">
              <h3 className="font-serif text-lg font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
                <GitMerge className="w-4 h-4 text-purple-600" />
                <span>Merge Characters</span>
              </h3>
              <button
                onClick={() => setShowMergeModal(false)}
                className="p-1 rounded-lg text-stone-400 hover:text-stone-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-stone-600 dark:text-stone-400 leading-relaxed">
              Merging combines all facts, relationships, and names. The merged names will be saved as aliases of the target, so future AI extractions resolve to the target character automatically.
            </p>

            <div>
              <label className="block text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                Choose Target Character (Canonical Identity)
              </label>
              <select
                value={mergeTargetId ?? ""}
                onChange={(e) => setMergeTargetId(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
              >
                {selectedCharIds.map((id) => {
                  const c = characters.find((x) => x.id === id);
                  return (
                    <option key={id} value={id}>
                      {c?.canonical_name || `Character #${id}`}
                    </option>
                  );
                })}
              </select>
            </div>

            <div className="p-3 rounded-xl bg-purple-50 dark:bg-purple-950/40 border border-purple-200/60 dark:border-purple-900/60 text-xs text-purple-900 dark:text-purple-200 space-y-1">
              <div className="font-semibold">Characters being merged into target:</div>
              <ul className="list-disc pl-4 space-y-0.5">
                {selectedCharIds
                  .filter((id) => id !== mergeTargetId)
                  .map((id) => {
                    const c = characters.find((x) => x.id === id);
                    return <li key={id}>{c?.canonical_name}</li>;
                  })}
              </ul>
            </div>

            <div className="pt-3 border-t border-stone-100 dark:border-stone-800 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowMergeModal(false)}
                className="px-3.5 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 text-xs font-medium cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  if (mergeTargetId) {
                    const sourceIds = selectedCharIds.filter(
                      (id) => id !== mergeTargetId,
                    );
                    mergeMutation.mutate({
                      sourceIds,
                      targetId: mergeTargetId,
                    });
                  }
                }}
                disabled={mergeMutation.isPending || !mergeTargetId}
                className="px-4 py-1.5 rounded-xl bg-purple-700 hover:bg-purple-800 disabled:opacity-50 text-white text-xs font-semibold shadow-xs flex items-center gap-1.5 cursor-pointer"
              >
                {mergeMutation.isPending ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <GitMerge className="w-3.5 h-3.5" />
                )}
                <span>Confirm Merge</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StoryProfile;
