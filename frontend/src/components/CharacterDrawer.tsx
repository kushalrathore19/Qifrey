import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  X,
  User,
  Tag,
  Sparkles,
  BookOpen,
  Quote,
  Network,
  Loader2,
  Lock,
  Unlock,
  Edit2,
  Check,
  Plus,
  Trash2,
  UserX,
} from "lucide-react";
import {
  getCharacter,
  updateCharacter,
  deleteCharacter,
  addAlias,
  addFact,
  updateFact,
  deleteFact,
  ignoreCharacter,
  type Fact,
} from "../api/client";
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

interface CharacterDrawerProps {
  characterId: number | null;
  onClose: () => void;
  onUpdated?: () => void;
}

export const CharacterDrawer: React.FC<CharacterDrawerProps> = ({
  characterId,
  onClose,
  onUpdated,
}) => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState<"active" | "planned">("active");
  const [color, setColor] = useState("#4a90e2");
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");

  // Alias state
  const [newAlias, setNewAlias] = useState("");

  // New fact form state
  const [showAddFact, setShowAddFact] = useState(false);
  const [newFactAttr, setNewFactAttr] = useState("");
  const [newFactVal, setNewFactVal] = useState("");
  const [newFactQuote, setNewFactQuote] = useState("");
  const [newFactLocked, setNewFactLocked] = useState(true);

  // Edit fact form state
  const [editingFactId, setEditingFactId] = useState<number | null>(null);
  const [editFactVal, setEditFactVal] = useState("");
  const [editFactQuote, setEditFactQuote] = useState("");

  const {
    data: character,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["character", characterId],
    queryFn: () => (characterId ? getCharacter(characterId) : null),
    enabled: !!characterId,
  });

  // Populate local form when character data loads
  useEffect(() => {
    if (character) {
      setName(character.canonical_name || "");
      setDescription(character.description || "");
      setNotes(character.notes || "");
      setStatus(character.status || "active");
      setColor(character.color || "#4a90e2");
      setTags(character.tags || []);
    }
  }, [character]);

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ["character", characterId] });
    queryClient.invalidateQueries({ queryKey: ["characters"] });
    queryClient.invalidateQueries({ queryKey: ["issues"] });
    if (onUpdated) onUpdated();
  };

  // Update character mutation
  const updateMutation = useMutation({
    mutationFn: () =>
      updateCharacter(characterId!, {
        canonical_name: name.trim(),
        description: description.trim() || null,
        notes: notes.trim() || null,
        status,
        color,
        tags,
      }),
    onSuccess: () => {
      setIsEditing(false);
      refreshAll();
      toast("Character details saved.", "success");
    },
    onError: (err) => {
      toast(`Update failed: ${(err as Error).message}`, "error");
    },
  });

  // Toggle character lock
  const toggleCharLockMutation = useMutation({
    mutationFn: (locked: boolean) =>
      updateCharacter(characterId!, { locked }),
    onSuccess: () => {
      refreshAll();
      toast("Character lock status updated.", "info");
    },
  });

  // Add alias mutation
  const addAliasMutation = useMutation({
    mutationFn: (aliasName: string) => addAlias(characterId!, aliasName),
    onSuccess: () => {
      setNewAlias("");
      refreshAll();
      toast("Alias added.", "success");
    },
  });

  // Add fact mutation
  const addFactMutation = useMutation({
    mutationFn: () =>
      addFact(characterId!, {
        attribute: newFactAttr.trim().toLowerCase(),
        value: newFactVal.trim(),
        quote: newFactQuote.trim() || null,
        locked: newFactLocked,
      }),
    onSuccess: () => {
      setShowAddFact(false);
      setNewFactAttr("");
      setNewFactVal("");
      setNewFactQuote("");
      refreshAll();
      toast("Fact added.", "success");
    },
    onError: (err) => {
      toast(`Failed to add fact: ${(err as Error).message}`, "error");
    },
  });

  // Update fact lock mutation
  const toggleFactLockMutation = useMutation({
    mutationFn: ({ factId, locked }: { factId: number; locked: boolean }) =>
      updateFact(factId, { locked }),
    onSuccess: () => {
      refreshAll();
    },
  });

  // Update fact value/quote mutation
  const saveFactEditMutation = useMutation({
    mutationFn: ({ factId }: { factId: number }) =>
      updateFact(factId, {
        value: editFactVal.trim(),
        quote: editFactQuote.trim() || null,
      }),
    onSuccess: () => {
      setEditingFactId(null);
      refreshAll();
      toast("Fact updated.", "success");
    },
  });

  // Delete fact mutation
  const deleteFactMutation = useMutation({
    mutationFn: (factId: number) => deleteFact(factId),
    onSuccess: () => {
      refreshAll();
      toast("Fact deleted.", "info");
    },
  });

  // Delete character mutation
  const deleteCharMutation = useMutation({
    mutationFn: () => deleteCharacter(characterId!),
    onSuccess: () => {
      refreshAll();
      toast("Character deleted.", "info");
      onClose();
    },
    onError: (err) => {
      toast(`Failed to delete character: ${(err as Error).message}`, "error");
    },
  });

  // Ignore character ("Not a character")
  const ignoreMutation = useMutation({
    mutationFn: () => ignoreCharacter(characterId!),
    onSuccess: () => {
      refreshAll();
      toast("Marked as 'not a character' and removed.", "info");
      onClose();
    },
    onError: (err) => {
      toast(`Failed to ignore character: ${(err as Error).message}`, "error");
    },
  });

  if (!characterId) return null;

  // Compute first appearance
  let firstChapter: number | null = null;
  if (character?.facts && character.facts.length > 0) {
    const validChapters = character.facts
      .map((f) => f.chapter_id)
      .filter((id): id is number => id !== null && id !== undefined);
    if (validChapters.length > 0) {
      firstChapter = Math.min(...validChapters);
    }
  }

  // Group facts by attribute name
  const groupedFacts: Record<string, Fact[]> = {};
  if (character?.facts) {
    for (const fact of character.facts) {
      if (!groupedFacts[fact.attribute]) {
        groupedFacts[fact.attribute] = [];
      }
      groupedFacts[fact.attribute].push(fact);
    }
  }

  const formatAttributeName = (attr: string) => {
    return attr
      .replace(/^other:/, "")
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  };

  const handleAddTag = () => {
    const clean = tagInput.trim().toLowerCase();
    if (!clean || tags.includes(clean)) return;
    setTags([...tags, clean]);
    setTagInput("");
  };

  const handleRemoveTag = (t: string) => {
    setTags(tags.filter((item) => item !== t));
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-stone-900/40 backdrop-blur-xs flex justify-end animate-in fade-in duration-200">
      <div className="w-full max-w-lg bg-white dark:bg-stone-900 h-full shadow-2xl border-l border-stone-200 dark:border-stone-800 flex flex-col transform animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-6 border-b border-stone-200 dark:border-stone-800 flex items-start justify-between bg-stone-50/50 dark:bg-stone-950/40">
          <div className="flex items-start gap-3">
            <div
              className="w-12 h-12 rounded-2xl flex items-center justify-center text-white shrink-0 shadow-xs"
              style={{ backgroundColor: character?.color || "#b45309" }}
            >
              <User className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="font-serif text-2xl font-bold text-stone-900 dark:text-stone-100">
                  {isLoading ? "Loading..." : character?.canonical_name}
                </h2>

                {character && (
                  <>
                    <span
                      className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md ${
                        character.source === "manual"
                          ? "bg-amber-100 dark:bg-amber-950/80 text-amber-900 dark:text-amber-200 border border-amber-300 dark:border-amber-800"
                          : "bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-300 border border-stone-200 dark:border-stone-700"
                      }`}
                    >
                      {character.source === "manual" ? "Manual" : "AI"}
                    </span>

                    {character.status === "planned" && (
                      <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md bg-purple-100 dark:bg-purple-950 text-purple-800 dark:text-purple-300 border border-purple-300 dark:border-purple-800">
                        Planned
                      </span>
                    )}

                    <button
                      onClick={() =>
                        toggleCharLockMutation.mutate(!character.locked)
                      }
                      title={character.locked ? "Locked against AI overwrite" : "Click to lock"}
                      className={`p-1 rounded-md transition-colors ${
                        character.locked
                          ? "text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/60"
                          : "text-stone-400 hover:text-stone-600 dark:hover:text-stone-300"
                      }`}
                    >
                      {character.locked ? (
                        <Lock className="w-3.5 h-3.5" />
                      ) : (
                        <Unlock className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </>
                )}
              </div>

              {firstChapter !== null && (
                <div className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400 font-medium mt-1">
                  <BookOpen className="w-3.5 h-3.5" />
                  <span>First appeared in Chapter {firstChapter}</span>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-1">
            {character && (
              <button
                onClick={() => setIsEditing(!isEditing)}
                className={`p-2 rounded-xl transition-colors ${
                  isEditing
                    ? "bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300"
                    : "text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-800"
                }`}
                title="Edit character details"
              >
                <Edit2 className="w-4 h-4" />
              </button>
            )}

            <button
              onClick={onClose}
              className="p-2 rounded-xl text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isLoading && (
            <div className="py-20 flex flex-col items-center justify-center text-stone-400 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-amber-600" />
              <p className="text-sm">Fetching character memory graph...</p>
            </div>
          )}

          {error && (
            <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-900 text-rose-800 dark:text-rose-200 text-sm">
              Failed to load character: {(error as Error).message}
            </div>
          )}

          {character && isEditing && (
            <div className="p-4 rounded-2xl bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200/80 dark:border-amber-900/60 space-y-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-amber-800 dark:text-amber-400">
                Edit Character Details
              </h3>

              <div>
                <label className="block text-xs font-semibold text-stone-700 dark:text-stone-300 mb-1">
                  Canonical Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs focus:ring-2 focus:ring-amber-600/30 outline-hidden"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-stone-700 dark:text-stone-300 mb-1">
                  Description
                </label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs focus:ring-2 focus:ring-amber-600/30 outline-hidden"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-stone-700 dark:text-stone-300 mb-1">
                  Author Notes (Story Bible)
                </label>
                <textarea
                  rows={2}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Private author notes, backstory, secret motivations..."
                  className="w-full px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs focus:ring-2 focus:ring-amber-600/30 outline-hidden"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-stone-700 dark:text-stone-300 mb-1">
                    Status
                  </label>
                  <select
                    value={status}
                    onChange={(e) =>
                      setStatus(e.target.value as "active" | "planned")
                    }
                    className="w-full px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
                  >
                    <option value="active">Active</option>
                    <option value="planned">Planned</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-stone-700 dark:text-stone-300 mb-1">
                    Badge Color
                  </label>
                  <input
                    type="color"
                    value={color}
                    onChange={(e) => setColor(e.target.value)}
                    className="w-full h-8 rounded-xl border border-stone-300 dark:border-stone-700 p-1 cursor-pointer bg-white dark:bg-stone-900"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-stone-700 dark:text-stone-300 mb-1">
                  Tags
                </label>
                <div className="flex gap-2 mb-2">
                  <input
                    type="text"
                    value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                    placeholder="e.g. antagonist, mage"
                    className="flex-1 px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
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
                  {tags.map((t) => (
                    <span
                      key={t}
                      className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[10px] bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300"
                    >
                      <span>{t}</span>
                      <button
                        onClick={() => handleRemoveTag(t)}
                        className="hover:text-rose-600 text-stone-400"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  className="px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 text-xs font-medium cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => updateMutation.mutate()}
                  disabled={updateMutation.isPending || !name.trim()}
                  className="px-4 py-1.5 rounded-xl bg-amber-700 hover:bg-amber-800 disabled:opacity-50 text-white text-xs font-semibold shadow-xs flex items-center gap-1 cursor-pointer"
                >
                  {updateMutation.isPending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Check className="w-3.5 h-3.5" />
                  )}
                  <span>Save Changes</span>
                </button>
              </div>
            </div>
          )}

          {character && !isEditing && (
            <>
              {/* Description */}
              {character.description && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-2">
                    Description
                  </h3>
                  <p className="text-stone-700 dark:text-stone-300 text-sm leading-relaxed bg-stone-50 dark:bg-stone-950/50 p-3.5 rounded-xl border border-stone-200/70 dark:border-stone-800/70 italic">
                    "{character.description}"
                  </p>
                </div>
              )}

              {/* Notes */}
              {character.notes && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-amber-800 dark:text-amber-400 mb-2">
                    Author Notes (Story Bible)
                  </h3>
                  <p className="text-stone-800 dark:text-stone-200 text-xs leading-relaxed bg-amber-50/50 dark:bg-amber-950/20 p-3.5 rounded-xl border border-amber-200/60 dark:border-amber-900/40">
                    {character.notes}
                  </p>
                </div>
              )}

              {/* Tags */}
              {character.tags && character.tags.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-2">
                    Tags
                  </h3>
                  <div className="flex flex-wrap gap-1.5">
                    {character.tags.map((t, idx) => (
                      <span
                        key={idx}
                        className="px-2.5 py-0.5 rounded-md text-[11px] font-medium bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 border border-stone-200 dark:border-stone-700"
                      >
                        #{t}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Aliases */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500 flex items-center gap-1.5">
                    <Tag className="w-3.5 h-3.5" />
                    Known Aliases & Titles
                  </h3>
                </div>

                <div className="flex flex-wrap gap-1.5 mb-2.5">
                  {character.aliases && character.aliases.length > 0 ? (
                    character.aliases.map((alias, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 border border-stone-200 dark:border-stone-700"
                      >
                        <span>{alias}</span>
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-stone-400 italic">No aliases recorded yet.</span>
                  )}
                </div>

                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newAlias}
                    onChange={(e) => setNewAlias(e.target.value)}
                    placeholder="Add an alias..."
                    className="flex-1 px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      if (newAlias.trim()) addAliasMutation.mutate(newAlias.trim());
                    }}
                    disabled={!newAlias.trim() || addAliasMutation.isPending}
                    className="px-3 py-1.5 rounded-xl bg-stone-200 dark:bg-stone-800 hover:bg-stone-300 dark:hover:bg-stone-700 disabled:opacity-50 text-xs font-medium cursor-pointer"
                  >
                    Add
                  </button>
                </div>
              </div>

              {/* Attributes / Facts */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" />
                    Facts & Attributes
                  </h3>

                  <button
                    onClick={() => setShowAddFact(!showAddFact)}
                    className="text-xs font-medium text-amber-700 dark:text-amber-400 hover:underline flex items-center gap-1 cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add Fact</span>
                  </button>
                </div>

                {/* Add Fact Form */}
                {showAddFact && (
                  <div className="p-3.5 rounded-xl border border-amber-300 dark:border-amber-800 bg-amber-50/40 dark:bg-amber-950/20 mb-4 space-y-3">
                    <div className="text-xs font-bold text-amber-900 dark:text-amber-200">
                      New Manual Fact (Author Bible)
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[11px] font-medium text-stone-600 dark:text-stone-400 mb-1">
                          Attribute
                        </label>
                        <input
                          type="text"
                          list="char-attr-vocab"
                          value={newFactAttr}
                          onChange={(e) => setNewFactAttr(e.target.value)}
                          placeholder="e.g. eye_color"
                          className="w-full px-2.5 py-1 rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
                        />
                        <datalist id="char-attr-vocab">
                          {STANDARD_ATTRIBUTES.map((a) => (
                            <option key={a} value={a} />
                          ))}
                        </datalist>
                      </div>

                      <div>
                        <label className="block text-[11px] font-medium text-stone-600 dark:text-stone-400 mb-1">
                          Value
                        </label>
                        <input
                          type="text"
                          value={newFactVal}
                          onChange={(e) => setNewFactVal(e.target.value)}
                          placeholder="e.g. emerald green"
                          className="w-full px-2.5 py-1 rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-[11px] font-medium text-stone-600 dark:text-stone-400 mb-1">
                        Optional Evidence Quote / Notes
                      </label>
                      <input
                        type="text"
                        value={newFactQuote}
                        onChange={(e) => setNewFactQuote(e.target.value)}
                        placeholder="Quote from manuscript or notes..."
                        className="w-full px-2.5 py-1 rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs outline-hidden"
                      />
                    </div>

                    <div className="flex items-center justify-between pt-1">
                      <label className="flex items-center gap-1.5 text-xs text-stone-700 dark:text-stone-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={newFactLocked}
                          onChange={(e) => setNewFactLocked(e.target.checked)}
                          className="accent-amber-700 rounded-sm"
                        />
                        <span>Lock fact against AI deletion</span>
                      </label>

                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => setShowAddFact(false)}
                          className="px-2.5 py-1 text-xs text-stone-500 hover:text-stone-800 cursor-pointer"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => addFactMutation.mutate()}
                          disabled={
                            !newFactAttr.trim() ||
                            !newFactVal.trim() ||
                            addFactMutation.isPending
                          }
                          className="px-3 py-1 bg-amber-700 hover:bg-amber-800 disabled:opacity-50 text-white rounded-lg text-xs font-semibold cursor-pointer"
                        >
                          Save Fact
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {Object.keys(groupedFacts).length === 0 ? (
                  <p className="text-xs text-stone-600 dark:text-stone-400 italic">
                    No verified facts extracted yet for this character.
                  </p>
                ) : (
                  <div className="space-y-4">
                    {Object.entries(groupedFacts).map(([attr, facts]) => (
                      <div
                        key={attr}
                        className="rounded-xl border border-stone-200 dark:border-stone-800 bg-stone-50/40 dark:bg-stone-950/30 p-3.5"
                      >
                        <h4 className="text-xs font-bold uppercase tracking-wider text-amber-800 dark:text-amber-400 mb-2">
                          {formatAttributeName(attr)}
                        </h4>
                        <div className="space-y-2.5">
                          {facts.map((f) => (
                            <div
                              key={f.id}
                              className="text-xs bg-white dark:bg-stone-900 p-2.5 rounded-lg border border-stone-200/80 dark:border-stone-800"
                            >
                              {editingFactId === f.id ? (
                                <div className="space-y-2">
                                  <input
                                    type="text"
                                    value={editFactVal}
                                    onChange={(e) => setEditFactVal(e.target.value)}
                                    className="w-full px-2 py-1 border rounded-md text-xs dark:bg-stone-800"
                                  />
                                  <input
                                    type="text"
                                    value={editFactQuote}
                                    onChange={(e) => setEditFactQuote(e.target.value)}
                                    placeholder="Evidence quote"
                                    className="w-full px-2 py-1 border rounded-md text-xs dark:bg-stone-800"
                                  />
                                  <div className="flex justify-end gap-2">
                                    <button
                                      onClick={() => setEditingFactId(null)}
                                      className="px-2 py-0.5 text-xs text-stone-500"
                                    >
                                      Cancel
                                    </button>
                                    <button
                                      onClick={() =>
                                        saveFactEditMutation.mutate({ factId: f.id })
                                      }
                                      className="px-2.5 py-0.5 text-xs bg-amber-700 text-white rounded-md"
                                    >
                                      Save
                                    </button>
                                  </div>
                                </div>
                              ) : (
                                <>
                                  <div className="flex items-center justify-between mb-1">
                                    <div className="flex items-center gap-2">
                                      <span className="font-semibold text-stone-900 dark:text-stone-100 text-sm">
                                        {f.value}
                                      </span>
                                      {f.source === "manual" && (
                                        <span className="text-[10px] px-1.5 py-0.2 rounded-sm bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300 font-medium">
                                          manual
                                        </span>
                                      )}
                                    </div>

                                    <div className="flex items-center gap-1.5">
                                      <span className="text-[11px] font-medium text-stone-600 dark:text-stone-400 bg-stone-100 dark:bg-stone-800 px-2 py-0.5 rounded-md">
                                        {f.chapter_id ? `Ch. ${f.chapter_id}` : "Notes"}
                                      </span>

                                      <button
                                        onClick={() =>
                                          toggleFactLockMutation.mutate({
                                            factId: f.id,
                                            locked: !f.locked,
                                          })
                                        }
                                        title={f.locked ? "Locked" : "Unlocked"}
                                        className={`p-1 rounded-md ${
                                          f.locked
                                            ? "text-amber-700 dark:text-amber-400"
                                            : "text-stone-400 hover:text-stone-600"
                                        }`}
                                      >
                                        {f.locked ? (
                                          <Lock className="w-3.5 h-3.5" />
                                        ) : (
                                          <Unlock className="w-3.5 h-3.5" />
                                        )}
                                      </button>

                                      <button
                                        onClick={() => {
                                          setEditingFactId(f.id);
                                          setEditFactVal(f.value);
                                          setEditFactQuote(f.quote || "");
                                        }}
                                        className="p-1 text-stone-400 hover:text-stone-600 rounded-md"
                                        title="Edit fact"
                                      >
                                        <Edit2 className="w-3 h-3" />
                                      </button>

                                      <button
                                        onClick={() => deleteFactMutation.mutate(f.id)}
                                        className="p-1 text-stone-400 hover:text-rose-600 rounded-md"
                                        title="Delete fact"
                                      >
                                        <Trash2 className="w-3 h-3" />
                                      </button>
                                    </div>
                                  </div>

                                  {f.quote && (
                                    <p className="text-stone-500 dark:text-stone-400 italic flex items-start gap-1 mt-1.5">
                                      <Quote className="w-3 h-3 shrink-0 text-stone-400 mt-0.5" />
                                      <span>"{f.quote}"</span>
                                    </p>
                                  )}
                                </>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Relationships */}
              {character.relationships &&
                character.relationships.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-2.5 flex items-center gap-1.5">
                      <Network className="w-3.5 h-3.5" />
                      Relationships
                    </h3>
                    <div className="space-y-2">
                      {character.relationships.map((rel) => (
                        <div
                          key={rel.id}
                          className="text-xs bg-stone-50 dark:bg-stone-950/40 p-2.5 rounded-xl border border-stone-200 dark:border-stone-800 flex items-center justify-between"
                        >
                          <div>
                            <span className="font-semibold text-stone-900 dark:text-stone-100">
                              {rel.type}
                            </span>
                            {rel.quote && (
                              <p className="text-stone-500 dark:text-stone-400 italic mt-0.5">
                                "{rel.quote}"
                              </p>
                            )}
                          </div>
                          <span className="text-[11px] text-stone-600 dark:text-stone-400">
                            {rel.chapter_id ? `Ch. ${rel.chapter_id}` : ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

              {/* Danger Actions: "Not a character" & Delete Character */}
              <div className="pt-6 border-t border-stone-200 dark:border-stone-800 space-y-3">
                <div className="text-xs font-bold uppercase tracking-wider text-stone-400 dark:text-stone-500">
                  Author Bible Actions
                </div>

                <div className="flex flex-col sm:flex-row gap-2">
                  <button
                    onClick={() => {
                      if (
                        window.confirm(
                          `Mark "${character.canonical_name}" as "Not a character"? This will delete it and permanently add its name to the ignored names list so AI will never extract it again.`
                        )
                      ) {
                        ignoreMutation.mutate();
                      }
                    }}
                    disabled={ignoreMutation.isPending}
                    className="flex-1 px-3 py-2 rounded-xl border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 hover:bg-amber-100 dark:hover:bg-amber-900/40 text-amber-900 dark:text-amber-200 text-xs font-medium flex items-center justify-center gap-1.5 cursor-pointer transition-colors"
                  >
                    <UserX className="w-3.5 h-3.5" />
                    <span>Not a character (Ignore)</span>
                  </button>

                  <button
                    onClick={() => {
                      if (
                        window.confirm(
                          `Delete "${character.canonical_name}" from story? This action cannot be undone.`
                        )
                      ) {
                        deleteCharMutation.mutate();
                      }
                    }}
                    disabled={deleteCharMutation.isPending}
                    className="px-3 py-2 rounded-xl border border-rose-300 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 hover:bg-rose-100 dark:hover:bg-rose-900/40 text-rose-800 dark:text-rose-200 text-xs font-medium flex items-center justify-center gap-1.5 cursor-pointer transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Delete Character</span>
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default CharacterDrawer;
