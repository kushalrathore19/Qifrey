import React, { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Sliders,
  Shield,
  BookOpen,
  Download,
  Upload,
  Plus,
  Trash2,
  Save,
  Loader2,
  FileText,
} from "lucide-react";
import {
  getStory,
  fetchChapters,
  updateChapter,
  getAttributeRules,
  updateAttributeRules,
  getStorySettings,
  updateStorySettings,
  getExportUrl,
  importStoryBible,
  type AttributeRule,
  type Chapter,
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

const STANDARD_LANGUAGES = [
  { code: "en-US", label: "English (US)" },
  { code: "en-GB", label: "English (UK)" },
  { code: "en-CA", label: "English (Canada)" },
  { code: "en-AU", label: "English (Australia)" },
];

export const StorySettingsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const storyId = Number(id);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [confidence, setConfidence] = useState<number>(0.7);
  const [grammarLang, setGrammarLang] = useState<string>("en-US");
  const [disabledRules, setDisabledRules] = useState<string[]>([]);
  const [newRuleInput, setNewRuleInput] = useState<string>("");
  const [attributeRules, setAttributeRules] = useState<AttributeRule[]>([]);
  const [newAttributeName, setNewAttributeName] = useState<string>("");
  const [newAttributeMode, setNewAttributeMode] = useState<
    "strict" | "can_change" | "ignore"
  >("strict");

  // Fetch story
  const { data: story, isLoading: isStoryLoading } = useQuery({
    queryKey: ["story", storyId],
    queryFn: () => getStory(storyId),
    enabled: !isNaN(storyId),
  });

  // Fetch chapters
  const { data: chapters = [], isLoading: isChaptersLoading } = useQuery({
    queryKey: ["chapters", storyId],
    queryFn: () => fetchChapters(storyId),
    enabled: !isNaN(storyId),
  });

  // Fetch story settings
  const { data: settings } = useQuery({
    queryKey: ["story-settings", storyId],
    queryFn: () => getStorySettings(storyId),
    enabled: !isNaN(storyId),
  });

  // Fetch attribute rules
  const { data: rules } = useQuery({
    queryKey: ["attribute-rules", storyId],
    queryFn: () => getAttributeRules(storyId),
    enabled: !isNaN(storyId),
  });

  // Sync settings into local state
  useEffect(() => {
    if (settings) {
      setConfidence(settings.confidence_threshold ?? 0.7);
      setGrammarLang(settings.grammar_language ?? "en-US");
      setDisabledRules(settings.disabled_grammar_rules ?? []);
    }
  }, [settings]);

  // Sync rules into local state
  useEffect(() => {
    if (rules) {
      setAttributeRules(rules);
    }
  }, [rules]);

  // Save settings mutation
  const saveSettingsMutation = useMutation({
    mutationFn: () =>
      updateStorySettings(storyId, {
        confidence_threshold: confidence,
        grammar_language: grammarLang,
        disabled_grammar_rules: disabledRules,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["story-settings", storyId] });
      toast("Pipeline settings saved.", "success");
    },
    onError: (err) => {
      toast(`Failed to save settings: ${(err as Error).message}`, "error");
    },
  });

  // Save attribute rules mutation
  const saveRulesMutation = useMutation({
    mutationFn: (newRules: AttributeRule[]) =>
      updateAttributeRules(storyId, newRules),
    onSuccess: (saved) => {
      setAttributeRules(saved);
      queryClient.invalidateQueries({ queryKey: ["attribute-rules", storyId] });
      toast("Attribute rules updated.", "success");
    },
    onError: (err) => {
      toast(`Failed to save attribute rules: ${(err as Error).message}`, "error");
    },
  });

  // Chapter exclusion toggle mutation
  const toggleChapterExclusionMutation = useMutation({
    mutationFn: ({
      chapterId,
      excluded,
    }: {
      chapterId: number;
      excluded: boolean;
    }) => updateChapter(chapterId, { exclude_from_analysis: excluded }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapters", storyId] });
      toast("Chapter exclusion status updated.", "info");
    },
    onError: (err) => {
      toast(`Failed to update chapter: ${(err as Error).message}`, "error");
    },
  });

  // Import file handler
  const handleImportJson = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (event) => {
      try {
        const json = JSON.parse(event.target?.result as string);
        await importStoryBible(storyId, json);
        queryClient.invalidateQueries({ queryKey: ["story", storyId] });
        queryClient.invalidateQueries({ queryKey: ["characters", storyId] });
        queryClient.invalidateQueries({ queryKey: ["attribute-rules", storyId] });
        queryClient.invalidateQueries({ queryKey: ["story-settings", storyId] });
        toast("Story Bible imported successfully!", "success");
      } catch (err) {
        toast(`Import failed: ${(err as Error).message}`, "error");
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  const handleAddAttributeRule = () => {
    if (!newAttributeName.trim()) return;
    const cleanAttr = newAttributeName.trim().toLowerCase();
    const existingIdx = attributeRules.findIndex((r) => r.attribute === cleanAttr);
    let updated: AttributeRule[];
    if (existingIdx >= 0) {
      updated = [...attributeRules];
      updated[existingIdx] = { attribute: cleanAttr, mode: newAttributeMode };
    } else {
      updated = [
        ...attributeRules,
        { attribute: cleanAttr, mode: newAttributeMode },
      ];
    }
    setAttributeRules(updated);
    saveRulesMutation.mutate(updated);
    setNewAttributeName("");
  };

  const handleRemoveAttributeRule = (attr: string) => {
    const updated = attributeRules.filter((r) => r.attribute !== attr);
    setAttributeRules(updated);
    saveRulesMutation.mutate(updated);
  };

  const handleAddDisabledRule = () => {
    const rule = newRuleInput.trim().toUpperCase();
    if (!rule || disabledRules.includes(rule)) return;
    setDisabledRules([...disabledRules, rule]);
    setNewRuleInput("");
  };

  const handleRemoveDisabledRule = (rule: string) => {
    setDisabledRules(disabledRules.filter((r) => r !== rule));
  };

  if (isNaN(storyId)) {
    return <div className="p-8 text-center text-rose-600">Invalid story ID.</div>;
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-stone-200 dark:border-stone-800 pb-5">
        <div className="flex items-center gap-3">
          <Link
            to={`/stories/${storyId}`}
            className="p-2 rounded-xl text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
            title="Back to Story Profile"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="font-serif text-2xl sm:text-3xl font-bold text-stone-900 dark:text-stone-100">
              Story Bible & Analysis Settings
            </h1>
            <p className="text-xs sm:text-sm text-stone-500 dark:text-stone-400 mt-0.5">
              {isStoryLoading ? "Loading..." : story?.title}
            </p>
          </div>
        </div>

        {/* Export / Import Buttons */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <a
            href={getExportUrl(storyId, "md")}
            target="_blank"
            rel="noreferrer"
            className="px-3 py-1.5 rounded-xl border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 hover:bg-stone-100 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-200 text-xs font-medium shadow-xs flex items-center gap-1.5 transition-colors"
          >
            <FileText className="w-3.5 h-3.5 text-stone-500" />
            <span>Export Markdown</span>
          </a>

          <a
            href={getExportUrl(storyId, "json")}
            target="_blank"
            rel="noreferrer"
            className="px-3 py-1.5 rounded-xl border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 hover:bg-stone-100 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-200 text-xs font-medium shadow-xs flex items-center gap-1.5 transition-colors"
          >
            <Download className="w-3.5 h-3.5 text-stone-500" />
            <span>Export JSON</span>
          </a>

          <label className="px-3 py-1.5 rounded-xl border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 hover:bg-stone-100 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-200 text-xs font-medium shadow-xs flex items-center gap-1.5 cursor-pointer transition-colors">
            <Upload className="w-3.5 h-3.5 text-stone-500" />
            <span>Import JSON</span>
            <input
              type="file"
              accept=".json"
              onChange={handleImportJson}
              className="hidden"
            />
          </label>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Section 1: Attribute Rules */}
        <div className="bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800 p-6 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2 text-stone-900 dark:text-stone-100 font-serif font-bold text-lg">
              <Shield className="w-5 h-5 text-amber-700" />
              <h2>Attribute Contradiction Rules</h2>
            </div>
            <p className="text-xs text-stone-500 dark:text-stone-400 mb-4 leading-relaxed">
              Define how contradiction detection treats specific attributes:
              <br />
              • <strong>Strict:</strong> Flag changes across all chapters.
              <br />
              • <strong>Can Change:</strong> Allow changes between chapters (e.g. clothing, hairstyle); only flag conflicts within the same chapter.
              <br />
              • <strong>Ignore:</strong> Completely skip checking for this attribute.
            </p>

            {/* Rules list */}
            <div className="space-y-2 mb-4 max-h-60 overflow-y-auto pr-1">
              {attributeRules.length === 0 ? (
                <div className="p-3 text-xs text-stone-400 italic bg-stone-50 dark:bg-stone-950 rounded-xl">
                  No custom rules set. All attributes default to "Strict".
                </div>
              ) : (
                attributeRules.map((rule) => (
                  <div
                    key={rule.attribute}
                    className="flex items-center justify-between p-2.5 rounded-xl bg-stone-50 dark:bg-stone-950 border border-stone-200/80 dark:border-stone-800 text-xs"
                  >
                    <div>
                      <span className="font-semibold text-stone-800 dark:text-stone-200">
                        {rule.attribute}
                      </span>
                      <span className="ml-2 px-2 py-0.5 rounded-md text-[10px] uppercase font-bold tracking-wider bg-stone-200 dark:bg-stone-800 text-stone-600 dark:text-stone-400">
                        {rule.mode}
                      </span>
                    </div>
                    <button
                      onClick={() => handleRemoveAttributeRule(rule.attribute)}
                      className="p-1 rounded-lg text-stone-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors"
                      title="Remove rule"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Add Rule Form */}
          <div className="pt-4 border-t border-stone-100 dark:border-stone-800/80">
            <div className="text-xs font-semibold text-stone-600 dark:text-stone-400 mb-2">
              Add or update rule
            </div>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                list="attribute-suggestions"
                value={newAttributeName}
                onChange={(e) => setNewAttributeName(e.target.value)}
                placeholder="e.g. clothing, eye_color"
                className="flex-1 px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs focus:ring-2 focus:ring-amber-600/30 outline-hidden"
              />
              <datalist id="attribute-suggestions">
                {STANDARD_ATTRIBUTES.map((attr) => (
                  <option key={attr} value={attr} />
                ))}
              </datalist>

              <select
                value={newAttributeMode}
                onChange={(e) =>
                  setNewAttributeMode(
                    e.target.value as "strict" | "can_change" | "ignore",
                  )
                }
                className="px-2.5 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs focus:ring-2 focus:ring-amber-600/30 outline-hidden"
              >
                <option value="strict">Strict</option>
                <option value="can_change">Can Change</option>
                <option value="ignore">Ignore</option>
              </select>

              <button
                type="button"
                onClick={handleAddAttributeRule}
                disabled={!newAttributeName.trim() || saveRulesMutation.isPending}
                className="px-3 py-1.5 rounded-xl bg-amber-700 hover:bg-amber-800 disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1 cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Save</span>
              </button>
            </div>
          </div>
        </div>

        {/* Section 2: Pipeline & Grammar Settings */}
        <div className="bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800 p-6 shadow-xs flex flex-col justify-between">
          <div className="space-y-5">
            <div className="flex items-center gap-2 text-stone-900 dark:text-stone-100 font-serif font-bold text-lg">
              <Sliders className="w-5 h-5 text-amber-700" />
              <h2>Pipeline & Grammar Settings</h2>
            </div>

            {/* Confidence Slider */}
            <div>
              <div className="flex items-center justify-between text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                <span>Fact Extraction Confidence Threshold</span>
                <span className="font-mono text-amber-800 dark:text-amber-400">
                  {confidence.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min="0.4"
                max="0.95"
                step="0.05"
                value={confidence}
                onChange={(e) => setConfidence(parseFloat(e.target.value))}
                className="w-full accent-amber-700 cursor-pointer"
              />
              <p className="text-[11px] text-stone-400 mt-1">
                Extracted facts with model confidence below this score are automatically discarded.
              </p>
            </div>

            {/* Grammar Language */}
            <div>
              <label className="block text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                Grammar Check Language
              </label>
              <select
                value={grammarLang}
                onChange={(e) => setGrammarLang(e.target.value)}
                className="w-full px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs focus:ring-2 focus:ring-amber-600/30 outline-hidden"
              >
                {STANDARD_LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Disabled Grammar Rules */}
            <div>
              <label className="block text-xs font-semibold mb-1 text-stone-700 dark:text-stone-300">
                Disabled Grammar Rules
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  placeholder="e.g. UPPERCASE_SENTENCE_START"
                  value={newRuleInput}
                  onChange={(e) => setNewRuleInput(e.target.value)}
                  className="flex-1 px-3 py-1.5 rounded-xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-xs font-mono focus:ring-2 focus:ring-amber-600/30 outline-hidden"
                />
                <button
                  type="button"
                  onClick={handleAddDisabledRule}
                  className="px-3 py-1.5 rounded-xl bg-stone-200 dark:bg-stone-800 hover:bg-stone-300 dark:hover:bg-stone-700 text-stone-800 dark:text-stone-200 text-xs font-medium cursor-pointer"
                >
                  Add
                </button>
              </div>

              <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                {disabledRules.map((rule) => (
                  <span
                    key={rule}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-mono bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 border border-stone-200 dark:border-stone-700"
                  >
                    <span>{rule}</span>
                    <button
                      onClick={() => handleRemoveDisabledRule(rule)}
                      className="hover:text-rose-600 text-stone-400"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-stone-100 dark:border-stone-800/80 mt-6 flex justify-end">
            <button
              onClick={() => saveSettingsMutation.mutate()}
              disabled={saveSettingsMutation.isPending}
              className="px-4 py-2 rounded-xl bg-amber-700 hover:bg-amber-800 disabled:opacity-50 text-white text-xs font-semibold shadow-xs flex items-center gap-1.5 cursor-pointer transition-colors"
            >
              {saveSettingsMutation.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Save className="w-3.5 h-3.5" />
              )}
              <span>Save Pipeline Settings</span>
            </button>
          </div>
        </div>
      </div>

      {/* Section 3: Chapter Exclusions */}
      <div className="bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800 p-6 shadow-xs">
        <div className="flex items-center gap-2 text-stone-900 dark:text-stone-100 font-serif font-bold text-lg mb-2">
          <BookOpen className="w-5 h-5 text-amber-700" />
          <h2>Chapter Scope & Analysis Exclusion</h2>
        </div>
        <p className="text-xs text-stone-500 dark:text-stone-400 mb-5 leading-relaxed">
          Toggle chapters off to exclude them from character fact extraction, summary generation, and grammar checks (ideal for author notes, outlines, or non-canon drafts).
        </p>

        {isChaptersLoading ? (
          <div className="py-8 flex justify-center text-stone-400">
            <Loader2 className="w-6 h-6 animate-spin text-amber-700" />
          </div>
        ) : chapters.length === 0 ? (
          <p className="text-xs text-stone-400 italic">No chapters in this story.</p>
        ) : (
          <div className="divide-y divide-stone-100 dark:divide-stone-800/80">
            {chapters.map((chapter: Chapter) => {
              const isExcluded = Boolean(chapter.exclude_from_analysis);
              return (
                <div
                  key={chapter.id}
                  className="py-3 flex items-center justify-between gap-4"
                >
                  <div>
                    <span className="font-medium text-sm text-stone-900 dark:text-stone-100">
                      Chapter {chapter.index}: {chapter.title}
                    </span>
                    {isExcluded && (
                      <span className="ml-2 text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md bg-stone-200 dark:bg-stone-800 text-stone-500">
                        Excluded from AI
                      </span>
                    )}
                  </div>

                  <button
                    onClick={() =>
                      toggleChapterExclusionMutation.mutate({
                        chapterId: chapter.id,
                        excluded: !isExcluded,
                      })
                    }
                    className={`px-3 py-1 rounded-xl text-xs font-medium border transition-colors cursor-pointer ${
                      isExcluded
                        ? "bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-400 border-stone-300 dark:border-stone-700"
                        : "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border-emerald-300/60 dark:border-emerald-700/60"
                    }`}
                  >
                    {isExcluded ? "Excluded (Click to Include)" : "Included in Analysis"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default StorySettingsPage;
