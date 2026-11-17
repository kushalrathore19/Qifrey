import React, { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  SpellCheck,
  Check,
  EyeOff,
  Sparkles,
  Quote,
  Loader2,
  CheckCircle,
  ChevronRight,
  ChevronLeft,
} from "lucide-react";
import {
  fetchStoryIssues,
  updateIssueStatus,
  getGrammarStatus,
  type Issue,
  type IssueStatus,
  type IssueType,
} from "../api/client";
import { useToast } from "../context/ToastContext";

interface SidebarTabsProps {
  storyId: number;
  currentChapterId?: number | null;
  onSelectIssue?: (issue: Issue) => void;
  onApplySuggestion?: (issue: Issue, suggestion: string) => void;
  isCollapsible?: boolean;
}

export const SidebarTabs: React.FC<SidebarTabsProps> = ({
  storyId,
  currentChapterId,
  onSelectIssue,
  onApplySuggestion,
  isCollapsible = false,
}) => {
  const [activeTab, setActiveTab] = useState<IssueType>("contradiction");
  const [statusFilter, setStatusFilter] = useState<IssueStatus>("open");
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    if (!isCollapsible) return false;
    return localStorage.getItem("qifrey_sidebar_collapsed") === "true";
  });

  const queryClient = useQueryClient();
  const { toast } = useToast();

  const toggleCollapse = () => {
    setIsCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("qifrey_sidebar_collapsed", String(next));
      return next;
    });
  };

  // Check grammar checker availability (LanguageTool/Java)
  const { data: grammarStatus } = useQuery({
    queryKey: ["grammar-status"],
    queryFn: getGrammarStatus,
  });

  // Fetch open issues for count badges
  const { data: openContradictions = [] } = useQuery({
    queryKey: ["issues", storyId, "contradiction", "open"],
    queryFn: () =>
      fetchStoryIssues(storyId, { type: "contradiction", status: "open" }),
  });

  const { data: openGrammar = [] } = useQuery({
    queryKey: ["issues", storyId, "grammar", "open"],
    queryFn: () =>
      fetchStoryIssues(storyId, { type: "grammar", status: "open" }),
  });

  // Fetch currently filtered list
  const { data: issues = [], isLoading } = useQuery({
    queryKey: ["issues", storyId, activeTab, statusFilter],
    queryFn: () =>
      fetchStoryIssues(storyId, { type: activeTab, status: statusFilter }),
  });

  // Sort issues so that current chapter issues appear first
  const sortedIssues = useMemo(() => {
    if (!currentChapterId) return issues;
    return [...issues].sort((a, b) => {
      const aIsCurrent = a.chapter_id === currentChapterId;
      const bIsCurrent = b.chapter_id === currentChapterId;
      if (aIsCurrent && !bIsCurrent) return -1;
      if (!aIsCurrent && bIsCurrent) return 1;
      return 0;
    });
  }, [issues, currentChapterId]);

  const statusMutation = useMutation({
    mutationFn: ({
      issueId,
      status,
    }: {
      issueId: number;
      status: IssueStatus;
    }) => updateIssueStatus(issueId, status),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["issues", storyId] });
      toast(`Issue marked as ${updated.status}`, "info");
    },
    onError: (err) => {
      toast(`Failed to update issue: ${(err as Error).message}`, "error");
    },
  });

  const handleAction = (e: React.MouseEvent, issueId: number, status: IssueStatus) => {
    e.stopPropagation();
    statusMutation.mutate({ issueId, status });
  };

  const parseSuggestions = (jsonStr: string | null): string[] => {
    if (!jsonStr) return [];
    try {
      return JSON.parse(jsonStr);
    } catch {
      return [];
    }
  };

  if (isCollapsed) {
    return (
      <aside className="w-12 shrink-0 bg-white dark:bg-stone-900 border-l border-stone-200 dark:border-stone-800 flex flex-col items-center py-4 justify-between h-full transition-all">
        <div className="flex flex-col items-center gap-4">
          <button
            onClick={toggleCollapse}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800 text-stone-600 dark:text-stone-300 transition-colors cursor-pointer"
            title="Expand Insights Panel"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <button
            onClick={() => {
              setActiveTab("contradiction");
              toggleCollapse();
            }}
            className="relative p-2 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800 text-amber-600 cursor-pointer"
            title="Contradictions"
          >
            <AlertTriangle className="w-4 h-4" />
            {openContradictions.length > 0 && (
              <span className="absolute -top-1 -right-1 px-1 py-0.2 text-[9px] font-bold rounded-full bg-amber-500 text-white">
                {openContradictions.length}
              </span>
            )}
          </button>

          <button
            onClick={() => {
              setActiveTab("grammar");
              toggleCollapse();
            }}
            className="relative p-2 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800 text-indigo-600 cursor-pointer"
            title="Grammar"
          >
            <SpellCheck className="w-4 h-4" />
            {openGrammar.length > 0 && (
              <span className="absolute -top-1 -right-1 px-1 py-0.2 text-[9px] font-bold rounded-full bg-indigo-500 text-white">
                {openGrammar.length}
              </span>
            )}
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside className="w-full lg:w-96 shrink-0 bg-white dark:bg-stone-900 border-l border-stone-200 dark:border-stone-800 flex flex-col h-full">
      {/* Tab Navigation */}
      <div className="p-3 border-b border-stone-200 dark:border-stone-800 bg-stone-50/60 dark:bg-stone-950/40">
        <div className="flex items-center gap-2">
          <div className="flex-1 flex rounded-xl bg-stone-200/70 dark:bg-stone-800/70 p-1">
            <button
              onClick={() => setActiveTab("contradiction")}
              className={`flex-1 py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer ${
                activeTab === "contradiction"
                  ? "bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 shadow-xs"
                  : "text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-200"
              }`}
            >
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
              <span>Contradictions</span>
              {openContradictions.length > 0 && (
                <span className="px-1.5 py-0.5 text-[10px] rounded-full bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300 font-bold">
                  {openContradictions.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("grammar")}
              className={`flex-1 py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer ${
                activeTab === "grammar"
                  ? "bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 shadow-xs"
                  : "text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-200"
              }`}
            >
              <SpellCheck className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
              <span>Grammar</span>
              {openGrammar.length > 0 && (
                <span className="px-1.5 py-0.5 text-[10px] rounded-full bg-indigo-100 dark:bg-indigo-950 text-indigo-800 dark:text-indigo-300 font-bold">
                  {openGrammar.length}
                </span>
              )}
            </button>
          </div>

          {isCollapsible && (
            <button
              onClick={toggleCollapse}
              className="p-1.5 rounded-lg hover:bg-stone-200 dark:hover:bg-stone-800 text-stone-500 dark:text-stone-400 transition-colors cursor-pointer"
              title="Collapse sidebar"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Filter bar */}
        <div className="flex items-center justify-between mt-3 px-1">
          <span className="text-xs font-medium text-stone-600 dark:text-stone-400">
            Filter Status:
          </span>
          <div className="flex gap-1.5">
            <button
              onClick={() => setStatusFilter("open")}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                statusFilter === "open"
                  ? "bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-900"
                  : "text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800"
              }`}
            >
              Open
            </button>
            <button
              onClick={() => setStatusFilter("dismissed")}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                statusFilter === "dismissed"
                  ? "bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-900"
                  : "text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800"
              }`}
            >
              Dismissed
            </button>
          </div>
        </div>
      </div>

      {/* Grammar checker unavailable status warning banner */}
      {activeTab === "grammar" && grammarStatus && !grammarStatus.available && (
        <div className="p-3 bg-amber-50 dark:bg-amber-950/60 border-b border-amber-200 dark:border-amber-900 text-amber-900 dark:text-amber-200 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span className="font-medium">
            Grammar checker unavailable (Java not found). Install Java runtime for live grammar checks.
          </span>
        </div>
      )}

      {/* Issues list container */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
        {isLoading && (
          <div className="py-12 flex flex-col items-center justify-center text-stone-400 gap-2">
            <Loader2 className="w-6 h-6 animate-spin text-amber-600" />
            <p className="text-xs">Loading insights...</p>
          </div>
        )}

        {!isLoading && sortedIssues.length === 0 && (
          <div className="py-16 text-center text-stone-400 dark:text-stone-500 px-4">
            <CheckCircle className="w-10 h-10 mx-auto mb-2 text-stone-300 dark:text-stone-700 stroke-1" />
            <p className="text-sm font-medium">
              No {statusFilter} {activeTab}s
            </p>
            <p className="text-xs mt-1 text-stone-400">
              {statusFilter === "open"
                ? `Everything looks consistent and clean for ${activeTab}.`
                : `No ${activeTab} issues marked as dismissed.`}
            </p>
          </div>
        )}

        {sortedIssues.map((item: Issue) => {
          const suggestions = parseSuggestions(item.suggestions_json);
          const isCurrentChapter = currentChapterId && item.chapter_id === currentChapterId;

          return (
            <div
              key={item.id}
              onClick={() => onSelectIssue?.(item)}
              className={`p-3.5 rounded-xl border bg-white dark:bg-stone-900 hover:shadow-md transition-all text-xs space-y-2.5 cursor-pointer ${
                isCurrentChapter
                  ? "border-amber-400 dark:border-amber-600/70 shadow-xs"
                  : "border-stone-200 dark:border-stone-800"
              }`}
            >
              {/* Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold px-2 py-0.5 rounded-md bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300">
                    {item.chapter_id ? `Chapter ${item.chapter_id}` : "Manuscript"}
                  </span>
                  {isCurrentChapter && (
                    <span className="px-1.5 py-0.5 text-[9px] font-bold rounded-full bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300">
                      Current
                    </span>
                  )}
                </div>
                <span
                  className={`capitalize px-2 py-0.5 rounded-md text-[10px] font-bold ${
                    item.status === "open"
                      ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
                      : item.status === "dismissed"
                        ? "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-400"
                        : "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                  }`}
                >
                  {item.status}
                </span>
              </div>

              {/* Message */}
              <p className="font-medium text-stone-800 dark:text-stone-200 leading-snug">
                {item.message}
              </p>

              {/* Quote */}
              {item.quote && (
                <div className="bg-stone-50 dark:bg-stone-950/60 p-2.5 rounded-lg border border-stone-200/70 dark:border-stone-800/70 text-stone-600 dark:text-stone-400 text-[11px] italic flex items-start gap-1.5 whitespace-pre-line">
                  <Quote className="w-3 h-3 shrink-0 text-stone-400 mt-0.5" />
                  <span>{item.quote}</span>
                </div>
              )}

              {/* Suggestions (Grammar) */}
              {suggestions.length > 0 && (
                <div className="bg-indigo-50/70 dark:bg-indigo-950/40 border border-indigo-200/60 dark:border-indigo-900/60 p-2 rounded-lg">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-700 dark:text-indigo-300 flex items-center gap-1 mb-1">
                    <Sparkles className="w-2.5 h-2.5" />
                    Suggested Replacements (click to apply):
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {suggestions.map((s, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onApplySuggestion?.(item, s);
                        }}
                        className="px-2 py-0.5 bg-white dark:bg-stone-900 hover:bg-indigo-100 dark:hover:bg-indigo-900 text-indigo-900 dark:text-indigo-200 rounded font-semibold text-[11px] border border-indigo-200 dark:border-indigo-800 cursor-pointer transition-colors shadow-2xs"
                        title="Apply suggestion to editor text"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex items-center gap-1.5 pt-1 border-t border-stone-100 dark:border-stone-800/80">
                {item.status === "open" ? (
                  <>
                    <button
                      onClick={(e) => handleAction(e, item.id, "dismissed")}
                      disabled={statusMutation.isPending}
                      className="flex-1 py-1 px-2 rounded-lg border border-stone-300 dark:border-stone-700 hover:bg-stone-100 dark:hover:bg-stone-800 text-stone-700 dark:text-stone-300 text-[11px] font-medium flex items-center justify-center gap-1 transition-colors cursor-pointer"
                      title="Dismiss this issue"
                    >
                      <EyeOff className="w-3 h-3 text-stone-400" />
                      Dismiss
                    </button>

                    <button
                      onClick={(e) => handleAction(e, item.id, "accepted")}
                      disabled={statusMutation.isPending}
                      className="flex-1 py-1 px-2 rounded-lg border border-emerald-300 dark:border-emerald-800 hover:bg-emerald-50 dark:hover:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 text-[11px] font-medium flex items-center justify-center gap-1 transition-colors cursor-pointer"
                      title="Accept suggested correction"
                    >
                      <Check className="w-3 h-3 text-emerald-500" />
                      Accept
                    </button>

                    {item.type === "contradiction" && (
                      <button
                        onClick={(e) => handleAction(e, item.id, "intentional")}
                        disabled={statusMutation.isPending}
                        className="py-1 px-2 rounded-lg border border-amber-300 dark:border-amber-800 hover:bg-amber-50 dark:hover:bg-amber-950/50 text-amber-800 dark:text-amber-300 text-[11px] font-medium transition-colors cursor-pointer"
                        title="Mark as intentional author decision"
                      >
                        Intentional
                      </button>
                    )}
                  </>
                ) : (
                  <button
                    onClick={(e) => handleAction(e, item.id, "open")}
                    disabled={statusMutation.isPending}
                    className="py-1 px-2.5 rounded-lg border border-stone-300 dark:border-stone-700 hover:bg-stone-100 dark:hover:bg-stone-800 text-stone-600 dark:text-stone-400 text-[11px] font-medium transition-colors cursor-pointer"
                  >
                    Restore to Open
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
};
