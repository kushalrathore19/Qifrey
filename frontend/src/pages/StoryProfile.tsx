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
} from "lucide-react";
import {
  getStory,
  getAnalysisStatus,
  analyzeStory,
  fetchStoryCharacters,
  type CharacterBrief,
} from "../api/client";
import { SidebarTabs } from "../components/SidebarTabs";
import { CharacterDrawer } from "../components/CharacterDrawer";
import { useToast } from "../context/ToastContext";

export const StoryProfile: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const storyId = Number(id);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [selectedCharacterId, setSelectedCharacterId] = useState<number | null>(
    null,
  );

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
      return status === "running" ? 1500 : false;
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

  const isAnalyzing =
    analysisStatus?.status === "running" || analyzeMutation.isPending;

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
        <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
          {/* Analysis progress indicator */}
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
            to={`/stories/${storyId}/edit`}
            className="px-3.5 py-2 rounded-xl border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 hover:bg-stone-100 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-200 text-sm font-medium shadow-sm flex items-center gap-2 transition-all"
          >
            <PenSquare className="w-4 h-4 text-stone-500 dark:text-stone-400" />
            <span>Open in editor</span>
          </Link>

          <button
            onClick={() => analyzeMutation.mutate()}
            disabled={isAnalyzing}
            className="px-4 py-2 rounded-xl bg-amber-700 hover:bg-amber-800 text-white text-sm font-medium shadow-sm disabled:opacity-50 flex items-center gap-2 transition-all cursor-pointer"
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
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="font-serif text-xl font-bold text-stone-900 dark:text-stone-100">
                      Character Memory
                    </h2>
                    <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
                      Living profiles, aliases, and extracted facts across all
                      chapters.
                    </p>
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
                      No characters extracted yet
                    </p>
                    <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">
                      Click the "Analyze Story" button above to extract
                      characters and build the memory graph.
                    </p>
                  </div>
                )}

                {characters.length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {characters.map((char: CharacterBrief) => (
                      <div
                        key={char.id}
                        onClick={() => setSelectedCharacterId(char.id)}
                        className="p-5 rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 hover:border-amber-400/80 dark:hover:border-amber-600/80 hover:shadow-md transition-all cursor-pointer flex flex-col justify-between group"
                      >
                        <div>
                          <div className="flex items-start justify-between gap-2 mb-2">
                            <h3 className="font-serif text-lg font-bold text-stone-900 dark:text-stone-100 group-hover:text-amber-800 dark:group-hover:text-amber-400 transition-colors">
                              {char.canonical_name}
                            </h3>
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
                            <p className="text-xs text-stone-600 dark:text-stone-400 line-clamp-2 leading-relaxed italic">
                              "{char.description}"
                            </p>
                          )}
                        </div>

                        <div className="pt-3 mt-3 border-t border-stone-100 dark:border-stone-800/80 flex items-center justify-between text-xs text-amber-700 dark:text-amber-400 font-medium">
                          <span>View attributes & quotes →</span>
                        </div>
                      </div>
                    ))}
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
      />
    </div>
  );
};

export default StoryProfile;
