import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Upload,
  BookPlus,
  BookOpen,
  Trash2,
  Clock,
  Layers,
  Sparkles,
  Loader2,
} from "lucide-react";
import { fetchStories, deleteStory, type Story } from "../api/client";
import { UploadModal } from "../components/UploadModal";
import { NewStoryModal } from "../components/NewStoryModal";
import { useToast } from "../context/ToastContext";

export const Library: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isNewStoryOpen, setIsNewStoryOpen] = useState(false);

  const {
    data: stories = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: ["stories"],
    queryFn: fetchStories,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteStory(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stories"] });
      toast("Story deleted", "info");
    },
    onError: (err) => {
      toast(`Failed to delete: ${(err as Error).message}`, "error");
    },
  });

  const handleDelete = (e: React.MouseEvent, story: Story) => {
    e.stopPropagation();
    if (
      confirm(
        `Are you sure you want to delete "${story.title}"? This cannot be undone.`,
      )
    ) {
      deleteMutation.mutate(story.id);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-10 pb-6 border-b border-stone-200 dark:border-stone-800">
        <div>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold tracking-tight text-stone-900 dark:text-stone-100">
            Manuscript Library
          </h1>
          <p className="text-stone-500 dark:text-stone-400 mt-1.5 text-sm max-w-xl">
            Upload fiction manuscripts to build an intelligent living map of
            characters, facts, and world consistency.
          </p>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto">
          <button
            onClick={() => setIsUploadOpen(true)}
            className="flex-1 sm:flex-none px-4 py-2.5 rounded-xl bg-amber-700 hover:bg-amber-800 text-white text-sm font-medium shadow-sm flex items-center justify-center gap-2 transition-all cursor-pointer"
          >
            <Upload className="w-4 h-4" />
            <span>Upload .txt</span>
          </button>

          <button
            onClick={() => setIsNewStoryOpen(true)}
            className="flex-1 sm:flex-none px-4 py-2.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 hover:bg-stone-100 dark:hover:bg-stone-800 text-stone-700 dark:text-stone-200 text-sm font-medium transition-colors flex items-center justify-center gap-2 cursor-pointer"
          >
            <BookPlus className="w-4 h-4" />
            <span>New Story</span>
          </button>
        </div>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="py-24 flex flex-col items-center justify-center text-stone-400 gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-amber-700" />
          <p className="text-sm font-medium">Loading your library...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="p-6 rounded-2xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-800 dark:text-rose-200 text-sm text-center">
          Failed to load stories: {(error as Error).message}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && stories.length === 0 && (
        <div className="py-20 text-center rounded-3xl border-2 border-dashed border-stone-300 dark:border-stone-800 p-8 max-w-lg mx-auto bg-stone-50/50 dark:bg-stone-950/30">
          <div className="w-14 h-14 rounded-2xl bg-amber-100 dark:bg-amber-950/60 border border-amber-300/60 dark:border-amber-700/50 flex items-center justify-center text-amber-800 dark:text-amber-300 mx-auto mb-4">
            <BookOpen className="w-7 h-7" />
          </div>
          <h3 className="font-serif text-xl font-bold text-stone-900 dark:text-stone-100 mb-1">
            Your library is empty
          </h3>
          <p className="text-stone-500 dark:text-stone-400 text-sm mb-6">
            Upload your first .txt manuscript or create a blank story to start
            mapping characters and contradictions.
          </p>
          <div className="flex justify-center gap-3">
            <button
              onClick={() => setIsUploadOpen(true)}
              className="px-4 py-2 rounded-xl bg-amber-700 hover:bg-amber-800 text-white text-sm font-medium flex items-center gap-2 cursor-pointer shadow-sm"
            >
              <Upload className="w-4 h-4" />
              Upload .txt
            </button>
          </div>
        </div>
      )}

      {/* Story Cards Grid */}
      {!isLoading && stories.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {stories.map((story) => (
            <div
              key={story.id}
              onClick={() => navigate(`/stories/${story.id}`)}
              className="group p-6 rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 hover:border-amber-400/80 dark:hover:border-amber-600/80 hover:shadow-md transition-all cursor-pointer flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-3 mb-3">
                  <h2 className="font-serif text-xl font-bold text-stone-900 dark:text-stone-100 group-hover:text-amber-800 dark:group-hover:text-amber-400 transition-colors line-clamp-2">
                    {story.title}
                  </h2>
                  <button
                    onClick={(e) => handleDelete(e, story)}
                    className="p-1.5 rounded-lg text-stone-400 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/50 transition-colors opacity-0 group-hover:opacity-100"
                    title="Delete story"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>

                {story.summary ? (
                  <p className="text-xs text-stone-600 dark:text-stone-400 line-clamp-3 leading-relaxed mb-4 italic">
                    "{story.summary}"
                  </p>
                ) : (
                  <p className="text-xs text-stone-600 dark:text-stone-400 italic mb-4 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-stone-300 dark:text-stone-600" />
                    Not analyzed yet — click to analyze
                  </p>
                )}
              </div>

              <div className="pt-4 border-t border-stone-100 dark:border-stone-800/80 flex items-center justify-between text-xs text-stone-600 dark:text-stone-400">
                <span className="flex items-center gap-1.5 font-medium">
                  <Layers className="w-3.5 h-3.5" />
                  {story.chapter_count || 0} chapter
                  {(story.chapter_count ?? 0) === 1 ? "" : "s"}
                </span>
                <span className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5" />
                  {formatDate(story.updated_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modals */}
      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onSuccess={(created) => navigate(`/stories/${created.id}`)}
      />

      <NewStoryModal
        isOpen={isNewStoryOpen}
        onClose={() => setIsNewStoryOpen(false)}
        onSuccess={(created) => navigate(`/stories/${created.id}`)}
      />
    </div>
  );
};

export default Library;
