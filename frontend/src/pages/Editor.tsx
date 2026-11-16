import React, {
  useState,
  useEffect,
  useRef,
  useMemo,
  useCallback,
} from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView, Decoration, hoverTooltip } from "@codemirror/view";
import { RangeSetBuilder } from "@codemirror/state";
import {
  ArrowLeft,
  Plus,
  Trash2,
  ChevronUp,
  ChevronDown,
  Check,
  Loader2,
  Play,
  FileText,
} from "lucide-react";
import {
  getStory,
  fetchChapters,
  getChapter,
  createChapter,
  updateChapter,
  deleteChapter,
  checkChapterGrammar,
  analyzeStory,
  getAnalysisStatus,
  type Chapter,
  type GrammarIssue,
} from "../api/client";
import { useToast } from "../context/ToastContext";
import { useTheme } from "../context/ThemeContext";

function countWords(str: string): number {
  if (!str) return 0;
  const match = str.trim().match(/\S+/g);
  return match ? match.length : 0;
}

export const Editor: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const storyId = Number(id);
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { theme } = useTheme();

  // Selected chapter state
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(
    null,
  );
  const [activeTitle, setActiveTitle] = useState<string>("");
  const [activeText, setActiveText] = useState<string>("");
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "unsaved">(
    "saved",
  );
  const [grammarIssues, setGrammarIssues] = useState<GrammarIssue[]>([]);
  const [draggedChapterIndex, setDraggedChapterIndex] = useState<number | null>(
    null,
  );

  // Auto-save debounce timer ref
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const grammarTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadedChapterIdRef = useRef<number | null>(null);

  // Fetch Story metadata
  const { data: story } = useQuery({
    queryKey: ["story", storyId],
    queryFn: () => getStory(storyId),
    enabled: !isNaN(storyId),
  });

  // Fetch Chapters list
  const { data: chapters = [], isLoading: isChaptersLoading } = useQuery({
    queryKey: ["chapters", storyId],
    queryFn: () => fetchChapters(storyId),
    enabled: !isNaN(storyId),
  });

  const activeChapterId =
    selectedChapterId ?? (chapters.length > 0 ? chapters[0].id : null);

  // Track latest edits for immediate save before analyze
  const activeChapterRef = useRef({
    id: activeChapterId,
    title: activeTitle,
    text: activeText,
  });
  useEffect(() => {
    activeChapterRef.current = {
      id: activeChapterId,
      title: activeTitle,
      text: activeText,
    };
  }, [activeChapterId, activeTitle, activeText]);

  // Fetch active chapter detail (with text)
  const { data: currentChapterDetail } = useQuery({
    queryKey: ["chapter", activeChapterId],
    queryFn: () => (activeChapterId ? getChapter(activeChapterId) : null),
    enabled: !!activeChapterId,
  });

  // Perform backend save
  const performSave = useCallback(
    async (chapId: number, titleToSave: string, textToSave: string) => {
      setSaveStatus("saving");
      try {
        await updateChapter(chapId, {
          title: titleToSave,
          text: textToSave,
        });
        setSaveStatus("saved");
        queryClient.invalidateQueries({ queryKey: ["chapters", storyId] });
      } catch (err) {
        setSaveStatus("unsaved");
        toast(`Auto-save failed: ${(err as Error).message}`, "error");
      }
    },
    [queryClient, storyId, toast],
  );

  // Trigger grammar check
  const triggerGrammarCheck = useCallback(
    async (chapId: number, text: string) => {
      try {
        const issues = await checkChapterGrammar(chapId, text);
        setGrammarIssues(issues);
      } catch {
        // Silently degrade if grammar service unavailable
        setGrammarIssues([]);
      }
    },
    [],
  );

  // When active chapter detail loads, sync local editor state
  useEffect(() => {
    if (
      currentChapterDetail &&
      loadedChapterIdRef.current !== currentChapterDetail.id
    ) {
      loadedChapterIdRef.current = currentChapterDetail.id;
      setActiveTitle(currentChapterDetail.title);
      setActiveText(currentChapterDetail.text || "");
      setSaveStatus("saved");
      triggerGrammarCheck(
        currentChapterDetail.id,
        currentChapterDetail.text || "",
      );
    }
  }, [currentChapterDetail, triggerGrammarCheck]);

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

  // Invalidate queries on analysis completion
  useEffect(() => {
    if (analysisStatus?.status === "completed") {
      queryClient.invalidateQueries({ queryKey: ["story", storyId] });
      queryClient.invalidateQueries({ queryKey: ["chapters", storyId] });
    }
  }, [analysisStatus?.status, queryClient, storyId]);

  // Schedule auto-save (1.5s debounce)
  const scheduleAutoSave = useCallback(
    (chapId: number, nextTitle: string, nextText: string) => {
      setSaveStatus("unsaved");
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        performSave(chapId, nextTitle, nextText);
      }, 1500);

      // Debounce grammar check (1000ms)
      if (grammarTimerRef.current) clearTimeout(grammarTimerRef.current);
      grammarTimerRef.current = setTimeout(() => {
        triggerGrammarCheck(chapId, nextText);
      }, 1000);
    },
    [performSave, triggerGrammarCheck],
  );

  // Switch active chapter (ensures current changes saved first)
  const handleSelectChapter = async (targetChapter: Chapter) => {
    if (targetChapter.id === activeChapterId) return;

    if (saveStatus === "unsaved" && activeChapterId) {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      await performSave(activeChapterId, activeTitle, activeText);
    }

    setSelectedChapterId(targetChapter.id);
    setActiveTitle(targetChapter.title);
    setActiveText(targetChapter.text || "");
    setGrammarIssues([]);
  };

  // Add chapter mutation
  const addChapterMutation = useMutation({
    mutationFn: async () => {
      const nextIdx = chapters.length + 1;
      return createChapter(storyId, {
        title: `Chapter ${nextIdx}`,
        text: "",
        index: nextIdx,
      });
    },
    onSuccess: (newChap) => {
      queryClient.invalidateQueries({ queryKey: ["chapters", storyId] });
      setSelectedChapterId(newChap.id);
      setActiveTitle(newChap.title);
      setActiveText("");
      setSaveStatus("saved");
      toast("Added new chapter", "success");
    },
    onError: (err) => {
      toast(`Failed to add chapter: ${(err as Error).message}`, "error");
    },
  });

  // Delete chapter mutation
  const deleteChapterMutation = useMutation({
    mutationFn: async (chapId: number) => {
      return deleteChapter(chapId);
    },
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ["chapters", storyId] });
      toast("Chapter deleted", "info");
      if (activeChapterId === deletedId) {
        const remaining = chapters.filter((c) => c.id !== deletedId);
        if (remaining.length > 0) {
          setSelectedChapterId(remaining[0].id);
        } else {
          setSelectedChapterId(null);
          setActiveTitle("");
          setActiveText("");
        }
      }
    },
    onError: (err) => {
      toast(`Failed to delete chapter: ${(err as Error).message}`, "error");
    },
  });

  // Reorder chapters helper
  const handleMoveChapter = async (
    currentIndex: number,
    direction: "up" | "down",
  ) => {
    const targetIndex =
      direction === "up" ? currentIndex - 1 : currentIndex + 1;
    if (targetIndex < 0 || targetIndex >= chapters.length) return;

    const currentChap = chapters[currentIndex];
    const targetChap = chapters[targetIndex];

    try {
      // Swap their index values
      await updateChapter(currentChap.id, { index: targetChap.index });
      await updateChapter(targetChap.id, { index: currentChap.index });
      queryClient.invalidateQueries({ queryKey: ["chapters", storyId] });
    } catch (err) {
      toast(`Failed to reorder: ${(err as Error).message}`, "error");
    }
  };

  // Drag and drop reordering
  const handleDragStart = (idx: number) => {
    setDraggedChapterIndex(idx);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = async (targetIdx: number) => {
    if (draggedChapterIndex === null || draggedChapterIndex === targetIdx) {
      setDraggedChapterIndex(null);
      return;
    }

    const reordered = [...chapters];
    const [moved] = reordered.splice(draggedChapterIndex, 1);
    reordered.splice(targetIdx, 0, moved);

    setDraggedChapterIndex(null);

    try {
      // Update indices sequentially
      await Promise.all(
        reordered.map((chap, idx) =>
          updateChapter(chap.id, { index: idx + 1 }),
        ),
      );
      queryClient.invalidateQueries({ queryKey: ["chapters", storyId] });
    } catch (err) {
      toast(`Failed to reorder: ${(err as Error).message}`, "error");
    }
  };

  // Analyze mutation
  const analyzeMutation = useMutation({
    mutationFn: async () => {
      // Ensure current changes are flushed first
      const current = activeChapterRef.current;
      if (current.id && saveStatus === "unsaved") {
        if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        await performSave(current.id, current.title, current.text);
      }
      return analyzeStory(storyId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analysis-status", storyId] });
      toast("Analysis started...", "info");
    },
    onError: (err) => {
      toast(`Analysis error: ${(err as Error).message}`, "error");
    },
  });

  const isAnalyzing =
    analysisStatus?.status === "running" || analyzeMutation.isPending;

  // CodeMirror Theme styling
  const editorTheme = useMemo(() => {
    return EditorView.theme({
      "&": {
        fontSize: "1.0625rem",
        fontFamily:
          "ui-serif, Georgia, Cambria, 'Times New Roman', Times, serif",
        height: "100%",
      },
      ".cm-content": {
        lineHeight: "1.8",
        padding: "2rem 2.5rem",
        maxWidth: "850px",
        margin: "0 auto",
      },
      ".cm-line": {
        padding: "0.15rem 0",
      },
      "&.cm-focused .cm-cursor": {
        borderLeftColor: "#b45309",
        borderLeftWidth: "2px",
      },
      ".cm-scroller": {
        overflow: "auto",
      },
    });
  }, []);

  // CodeMirror Grammar Underline Decorations
  const grammarDecorations = useMemo(() => {
    const docLen = activeText.length;
    const builder = new RangeSetBuilder<Decoration>();
    const mark = Decoration.mark({
      class:
        "underline decoration-wavy decoration-amber-500 underline-offset-4 cursor-pointer hover:bg-amber-100/40 dark:hover:bg-amber-950/40",
    });

    const valid = grammarIssues
      .filter(
        (iss) =>
          iss.span_start >= 0 &&
          iss.span_end <= docLen &&
          iss.span_start < iss.span_end,
      )
      .sort((a, b) => a.span_start - b.span_start || a.span_end - b.span_end);

    let lastTo = -1;
    for (const iss of valid) {
      if (iss.span_start >= lastTo) {
        builder.add(iss.span_start, iss.span_end, mark);
        lastTo = iss.span_end;
      }
    }

    return EditorView.decorations.of(builder.finish());
  }, [grammarIssues, activeText.length]);

  // CodeMirror Tooltip with click-to-apply suggestions
  const grammarTooltipExtension = useMemo(() => {
    return hoverTooltip((view, pos) => {
      const issue = grammarIssues.find(
        (iss) => pos >= iss.span_start && pos <= iss.span_end,
      );
      if (!issue) return null;

      return {
        pos: issue.span_start,
        end: issue.span_end,
        above: true,
        create() {
          const dom = document.createElement("div");
          dom.className =
            "p-3 rounded-xl shadow-xl border bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-700 text-stone-800 dark:text-stone-100 text-xs max-w-xs space-y-2 select-none z-50";

          const msg = document.createElement("div");
          msg.className = "font-medium text-amber-700 dark:text-amber-400";
          msg.textContent = issue.message;
          dom.appendChild(msg);

          if (issue.quote) {
            const q = document.createElement("div");
            q.className =
              "text-[11px] italic text-stone-500 dark:text-stone-400 border-l-2 border-stone-300 dark:border-stone-600 pl-2";
            q.textContent = `"${issue.quote}"`;
            dom.appendChild(q);
          }

          if (issue.suggestions && issue.suggestions.length > 0) {
            const sugHeader = document.createElement("div");
            sugHeader.className =
              "text-[11px] text-stone-500 dark:text-stone-400 font-semibold pt-1";
            sugHeader.textContent = "Suggestions (click to apply):";
            dom.appendChild(sugHeader);

            const sugList = document.createElement("div");
            sugList.className = "flex flex-wrap gap-1.5 pt-0.5";
            issue.suggestions.slice(0, 4).forEach((sug) => {
              const btn = document.createElement("button");
              btn.type = "button";
              btn.className =
                "px-2 py-0.5 rounded-md bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/80 dark:hover:bg-amber-900 text-amber-800 dark:text-amber-200 border border-amber-200 dark:border-amber-800 font-medium cursor-pointer transition-colors";
              btn.textContent = sug;
              btn.onmousedown = (e) => {
                e.preventDefault();
                e.stopPropagation();
                view.dispatch({
                  changes: {
                    from: issue.span_start,
                    to: issue.span_end,
                    insert: sug,
                  },
                });
              };
              sugList.appendChild(btn);
            });
            dom.appendChild(sugList);
          }

          return { dom };
        },
      };
    });
  }, [grammarIssues]);

  // CodeMirror combined extensions
  const extensions = useMemo(() => {
    return [
      EditorView.lineWrapping,
      editorTheme,
      grammarDecorations,
      grammarTooltipExtension,
    ];
  }, [editorTheme, grammarDecorations, grammarTooltipExtension]);

  const activeWordCount = useMemo(() => countWords(activeText), [activeText]);

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col overflow-hidden bg-stone-50 dark:bg-stone-950">
      {/* Top Bar */}
      <header className="border-b border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 px-6 py-3 flex items-center justify-between gap-4 shrink-0 z-10">
        <div className="flex items-center gap-4">
          <Link
            to={`/stories/${storyId}`}
            className="p-2 rounded-xl text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
            title="Back to Story Profile"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="font-serif text-lg font-bold text-stone-900 dark:text-stone-100 line-clamp-1">
              {story?.title || "Story Editor"}
            </h1>
            <p className="text-xs text-stone-500 dark:text-stone-400">
              Write Mode • {chapters.length} chapter
              {chapters.length === 1 ? "" : "s"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Save Status indicator */}
          <div className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg">
            {saveStatus === "saving" && (
              <span className="flex items-center gap-1 text-amber-700 dark:text-amber-400">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Saving...</span>
              </span>
            )}
            {saveStatus === "saved" && (
              <span className="flex items-center gap-1 text-stone-400 dark:text-stone-500">
                <Check className="w-3.5 h-3.5" />
                <span>Saved</span>
              </span>
            )}
            {saveStatus === "unsaved" && (
              <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                <span>Unsaved</span>
              </span>
            )}
          </div>

          {/* Analysis status badge */}
          {analysisStatus && analysisStatus.status === "running" && (
            <div className="flex items-center gap-2 px-3 py-1 rounded-xl bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-900/60 text-amber-800 dark:text-amber-200 text-xs font-medium">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-600" />
              <span>Analyzing chapter {analysisStatus.current_chapter}...</span>
            </div>
          )}

          {/* Analyze Button */}
          <button
            onClick={() => analyzeMutation.mutate()}
            disabled={isAnalyzing}
            className="px-3.5 py-1.5 rounded-xl bg-amber-700 hover:bg-amber-800 text-white text-xs font-medium shadow-sm disabled:opacity-50 flex items-center gap-1.5 transition-all cursor-pointer"
          >
            {isAnalyzing ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Analyzing...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-white" />
                <span>Analyze</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* Main Split Layout: Left Chapter List + Center CodeMirror Editor */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Chapter Sidebar */}
        <aside className="w-64 sm:w-72 border-r border-stone-200 dark:border-stone-800 bg-stone-100/70 dark:bg-stone-900/40 flex flex-col shrink-0">
          <div className="p-4 border-b border-stone-200 dark:border-stone-800 flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wider text-stone-500 dark:text-stone-400">
              Chapters
            </h2>
            <button
              onClick={() => addChapterMutation.mutate()}
              disabled={addChapterMutation.isPending}
              className="p-1 rounded-lg hover:bg-stone-200 dark:hover:bg-stone-800 text-stone-600 dark:text-stone-300 transition-colors cursor-pointer"
              title="Add Chapter"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>

          {/* Chapter list */}
          <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
            {isChaptersLoading && (
              <div className="p-4 text-center text-xs text-stone-400 flex items-center justify-center gap-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Loading chapters...</span>
              </div>
            )}

            {!isChaptersLoading && chapters.length === 0 && (
              <div className="p-6 text-center text-xs text-stone-400">
                No chapters yet. Click + to add one.
              </div>
            )}

            {chapters.map((chap, idx) => {
              const isSelected = chap.id === activeChapterId;
              return (
                <div
                  key={chap.id}
                  draggable
                  onDragStart={() => handleDragStart(idx)}
                  onDragOver={handleDragOver}
                  onDrop={() => handleDrop(idx)}
                  onClick={() => handleSelectChapter(chap)}
                  className={`group relative p-2.5 rounded-xl border transition-all cursor-pointer select-none flex items-center justify-between gap-2 ${
                    isSelected
                      ? "bg-white dark:bg-stone-800 border-amber-600/40 shadow-sm"
                      : "bg-transparent border-transparent hover:bg-stone-200/60 dark:hover:bg-stone-800/60 text-stone-600 dark:text-stone-300"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <p
                      className={`text-sm font-medium truncate ${
                        isSelected
                          ? "text-stone-900 dark:text-stone-100 font-semibold"
                          : ""
                      }`}
                    >
                      {chap.title}
                    </p>
                    <p className="text-[11px] text-stone-400 dark:text-stone-500">
                      Chapter {chap.index}
                    </p>
                  </div>

                  {/* Actions on hover or selection */}
                  <div className="flex items-center gap-0.5 opacity-60 group-hover:opacity-100 transition-opacity">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleMoveChapter(idx, "up");
                      }}
                      disabled={idx === 0}
                      className="p-1 rounded hover:bg-stone-200 dark:hover:bg-stone-700 disabled:opacity-20 text-stone-500"
                      title="Move up"
                    >
                      <ChevronUp className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleMoveChapter(idx, "down");
                      }}
                      disabled={idx === chapters.length - 1}
                      className="p-1 rounded hover:bg-stone-200 dark:hover:bg-stone-700 disabled:opacity-20 text-stone-500"
                      title="Move down"
                    >
                      <ChevronDown className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (
                          window.confirm(
                            `Delete "${chap.title}"? This cannot be undone.`,
                          )
                        ) {
                          deleteChapterMutation.mutate(chap.id);
                        }
                      }}
                      className="p-1 rounded hover:bg-rose-100 dark:hover:bg-rose-950/60 text-stone-400 hover:text-rose-600 transition-colors"
                      title="Delete chapter"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </aside>

        {/* Center Editor Panel */}
        <main className="flex-1 flex flex-col overflow-hidden bg-white dark:bg-stone-950">
          {activeChapterId ? (
            <>
              {/* Editable Title Header + Word Count */}
              <div className="border-b border-stone-200 dark:border-stone-800 px-8 py-3.5 flex items-center justify-between gap-4 bg-white dark:bg-stone-900/60">
                <input
                  type="text"
                  value={activeTitle}
                  onChange={(e) => {
                    const nextTitle = e.target.value;
                    setActiveTitle(nextTitle);
                    if (activeChapterId) {
                      scheduleAutoSave(activeChapterId, nextTitle, activeText);
                    }
                  }}
                  className="font-serif text-xl font-bold bg-transparent border-b border-transparent hover:border-stone-300 dark:hover:border-stone-700 focus:border-amber-600 focus:outline-none text-stone-900 dark:text-stone-100 px-1 py-0.5 w-full max-w-lg transition-colors"
                  placeholder="Chapter Title..."
                />
                <div className="text-xs text-stone-400 dark:text-stone-500 font-medium whitespace-nowrap">
                  {activeWordCount} words
                </div>
              </div>

              {/* CodeMirror Workspace */}
              <div className="flex-1 overflow-hidden relative">
                <CodeMirror
                  value={activeText}
                  height="100%"
                  theme={theme === "dark" ? "dark" : "light"}
                  extensions={extensions}
                  onChange={(val) => {
                    setActiveText(val);
                    if (activeChapterId) {
                      scheduleAutoSave(activeChapterId, activeTitle, val);
                    }
                  }}
                  className="h-full"
                />
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-stone-400 space-y-3">
              <FileText className="w-10 h-10 stroke-[1.5]" />
              <p className="text-sm">
                Select or create a chapter to begin writing.
              </p>
              <button
                onClick={() => addChapterMutation.mutate()}
                className="px-4 py-2 rounded-xl bg-amber-700 text-white text-xs font-medium hover:bg-amber-800 transition-colors"
              >
                Create Chapter
              </button>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
