import { useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchStories,
  createStory,
  uploadStory,
  deleteStory,
  type Story,
} from "../api";

export default function Library() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    data: stories = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: ["stories"],
    queryFn: fetchStories,
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadStory(file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["stories"] }),
  });

  const createMutation = useMutation({
    mutationFn: (title: string) => createStory(title),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["stories"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteStory(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["stories"] }),
  });

  const handleUpload = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
      e.target.value = "";
    }
  };

  const handleNewStory = () => {
    const title = prompt("Enter story title:");
    if (title?.trim()) {
      createMutation.mutate(title.trim());
    }
  };

  const handleDelete = (story: Story) => {
    if (confirm(`Delete "${story.title}"?`)) {
      deleteMutation.mutate(story.id);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Qifrey</h1>
            <p className="text-gray-500 mt-1">Master of ink and brush</p>
          </div>
          <div className="flex gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt"
              className="hidden"
              onChange={handleFileChange}
            />
            <button
              onClick={handleUpload}
              disabled={uploadMutation.isPending}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors cursor-pointer"
            >
              {uploadMutation.isPending ? "Uploading…" : "Upload .txt"}
            </button>
            <button
              onClick={handleNewStory}
              disabled={createMutation.isPending}
              className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors cursor-pointer"
            >
              New Story
            </button>
          </div>
        </div>

        {(uploadMutation.isError || createMutation.isError) && (
          <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg border border-red-200">
            {uploadMutation.error?.message || createMutation.error?.message}
          </div>
        )}

        {isLoading && (
          <div className="text-center py-12 text-gray-500">
            Loading stories…
          </div>
        )}

        {error && (
          <div className="text-center py-12 text-red-500">
            Failed to load stories: {(error as Error).message}
          </div>
        )}

        {!isLoading && !error && stories.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            <p className="text-lg">No stories yet</p>
            <p className="mt-2">
              Upload a .txt file or create a new story to get started.
            </p>
          </div>
        )}

        {stories.length > 0 && (
          <div className="space-y-3">
            {stories.map((story) => (
              <div
                key={story.id}
                className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-sm transition-shadow"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900">
                      {story.title}
                    </h2>
                    <div className="flex gap-4 mt-1 text-sm text-gray-500">
                      {story.chapter_count !== undefined && (
                        <span>
                          {story.chapter_count} chapter
                          {story.chapter_count !== 1 ? "s" : ""}
                        </span>
                      )}
                      <span>Created {formatDate(story.created_at)}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(story)}
                    disabled={deleteMutation.isPending}
                    className="text-gray-400 hover:text-red-500 transition-colors p-1 cursor-pointer"
                    title="Delete story"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-5 w-5"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
