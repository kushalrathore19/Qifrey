# Gold Standard Evaluation Dataset

This directory contains human-annotated gold standard data used to measure Qifrey's extraction and contradiction detection accuracy.

> [!IMPORTANT]
> **Gold labels must NEVER be generated with an LLM.** To avoid circular bias, benchmark contamination, and hallucinated ground truths, all files in this directory must be hand-labeled by human annotators.

## File Format

Each gold dataset is stored as a JSON file adhering to `template.json`:

```json
{
  "title": "Story Title",
  "chapters": [
    {
      "index": 1,
      "title": "Chapter title",
      "text": "Verbatim text of the chapter...",
      "characters": [
        {
          "canonical_name": "Primary canonical name (e.g. Qifrey)",
          "aliases": ["Alternative names, titles, or nicknames"]
        }
      ],
      "locations": [
        {
          "name": "Location or setting mentioned in chapter"
        }
      ],
      "facts": [
        {
          "character": "Canonical character name",
          "attribute": "Controlled attribute (e.g. eye_color, hair_color, occupation) or custom snake_case",
          "value": "Ground truth attribute value",
          "quote": "Verbatim quote from chapter text demonstrating the fact"
        }
      ]
    }
  ],
  "contradictions": [
    {
      "character": "Canonical character name",
      "attribute": "Attribute in conflict",
      "chapter_a": 1,
      "chapter_b": 2,
      "value_a": "First stated value",
      "value_b": "Conflicting stated value",
      "description": "Explanation of the conflict"
    }
  ]
}
```

## Annotation Guidelines

1. **Explicit facts only**: Only record facts explicitly stated in the chapter text. Do not infer unstated worldbuilding details.
2. **Canonical names**: Always use a consistent canonical name for each character across all chapters, even if the chapter text uses only an alias.
3. **Aliases**: Include all aliases used in that chapter (e.g., titles, nicknames, code names).
4. **Attribute Vocabulary**: Prefer standard attributes (`eye_color`, `hair_color`, `age`, `height`, `occupation`, `vehicle_color`, `home_location`, `wand_color`, etc.) or snake_case descriptors.
5. **Planted Contradictions**: Note any deliberate inconsistencies across chapters so contradiction precision and recall can be evaluated.
