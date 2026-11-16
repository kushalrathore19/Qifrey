import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  X,
  User,
  Tag,
  Sparkles,
  BookOpen,
  Quote,
  Network,
  Loader2,
} from "lucide-react";
import { getCharacter, type Fact } from "../api/client";

interface CharacterDrawerProps {
  characterId: number | null;
  onClose: () => void;
}

export const CharacterDrawer: React.FC<CharacterDrawerProps> = ({
  characterId,
  onClose,
}) => {
  const {
    data: character,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["character", characterId],
    queryFn: () => (characterId ? getCharacter(characterId) : null),
    enabled: !!characterId,
  });

  if (!characterId) return null;

  // Compute first appearance
  let firstChapter: number | null = null;
  if (character?.facts && character.facts.length > 0) {
    firstChapter = Math.min(...character.facts.map((f) => f.chapter_id));
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

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-stone-900/40 backdrop-blur-xs flex justify-end animate-in fade-in duration-200">
      <div className="w-full max-w-lg bg-white dark:bg-stone-900 h-full shadow-2xl border-l border-stone-200 dark:border-stone-800 flex flex-col transform animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-6 border-b border-stone-200 dark:border-stone-800 flex items-start justify-between bg-stone-50/50 dark:bg-stone-950/40">
          <div className="flex items-start gap-3">
            <div className="w-12 h-12 rounded-2xl bg-amber-100 dark:bg-amber-950/70 border border-amber-300/60 dark:border-amber-700/50 flex items-center justify-center text-amber-800 dark:text-amber-300 shrink-0">
              <User className="w-6 h-6" />
            </div>
            <div>
              <h2 className="font-serif text-2xl font-bold text-stone-900 dark:text-stone-100">
                {isLoading ? "Loading character..." : character?.canonical_name}
              </h2>
              {firstChapter && (
                <div className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400 font-medium mt-1">
                  <BookOpen className="w-3.5 h-3.5" />
                  <span>First appeared in Chapter {firstChapter}</span>
                </div>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
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

          {character && (
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

              {/* Aliases */}
              {character.aliases && character.aliases.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-2 flex items-center gap-1.5">
                    <Tag className="w-3.5 h-3.5" />
                    Known Aliases & Titles
                  </h3>
                  <div className="flex flex-wrap gap-1.5">
                    {character.aliases.map((alias, idx) => (
                      <span
                        key={idx}
                        className="px-2.5 py-1 rounded-lg text-xs font-medium bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 border border-stone-200 dark:border-stone-700"
                      >
                        {alias}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Attributes / Facts */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-3 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5" />
                  Facts & Attributes
                </h3>

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
                              <div className="flex items-center justify-between mb-1">
                                <span className="font-semibold text-stone-900 dark:text-stone-100 text-sm">
                                  {f.value}
                                </span>
                                <span className="text-[11px] font-medium text-stone-600 dark:text-stone-400 bg-stone-100 dark:bg-stone-800 px-2 py-0.5 rounded-md">
                                  Ch. {f.chapter_id}
                                </span>
                              </div>
                              {f.quote && (
                                <p className="text-stone-500 dark:text-stone-400 italic flex items-start gap-1 mt-1.5">
                                  <Quote className="w-3 h-3 shrink-0 text-stone-400 mt-0.5" />
                                  <span>"{f.quote}"</span>
                                </p>
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
                            Ch. {rel.chapter_id}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
