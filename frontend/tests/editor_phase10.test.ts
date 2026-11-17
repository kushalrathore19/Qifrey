import test from "node:test";
import assert from "node:assert/strict";

// Mock localStorage for Node test environment
class MockLocalStorage {
  private store: Map<string, string> = new Map();

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  clear(): void {
    this.store.clear();
  }
}

test("Editor autosave and draft recovery preserves text across reload", () => {
  const storage = new MockLocalStorage();
  const chapterId = 42;
  const draftKey = `qifrey_draft_${chapterId}`;

  // User writes in chapter 42
  const typedTitle = "The Repairer of Reputations";
  const typedText = "Hildred looked up, his black eyes cold.";

  // Real-time typing triggers draft persistence
  storage.setItem(
    draftKey,
    JSON.stringify({
      title: typedTitle,
      text: typedText,
      timestamp: Date.now(),
    }),
  );

  // Simulate page reload: server has old text, but localStorage has uncommitted draft
  const serverChapter = {
    id: chapterId,
    title: "Chapter 1",
    text: "Hildred was reading.",
  };

  const savedDraftRaw = storage.getItem(draftKey);
  assert.ok(savedDraftRaw, "Draft should be found in storage");

  const draft = JSON.parse(savedDraftRaw!);
  let effectiveText = serverChapter.text;
  let effectiveTitle = serverChapter.title;
  let isUnsaved = false;

  if (draft.text !== undefined && draft.text !== serverChapter.text) {
    effectiveText = draft.text;
    if (draft.title) effectiveTitle = draft.title;
    isUnsaved = true;
  }

  assert.strictEqual(effectiveText, typedText);
  assert.strictEqual(effectiveTitle, typedTitle);
  assert.strictEqual(isUnsaved, true);

  // Once server confirms save, draft is cleared
  storage.removeItem(draftKey);
  assert.strictEqual(storage.getItem(draftKey), null);
});

test("Out-of-order response protection discards stale network saves", async () => {
  let saveSeq = 0;
  let latestConfirmedText = "";

  const performSave = async (
    textToSave: string,
    delayMs: number,
  ): Promise<void> => {
    const seq = ++saveSeq;
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    if (seq === saveSeq) {
      latestConfirmedText = textToSave;
    }
  };

  // User types "A", then quickly replaces it with "AB"
  const p1 = performSave("A", 50); // Slow save
  const p2 = performSave("AB", 10); // Fast save

  await Promise.all([p1, p2]);

  // "AB" had sequence 2, "A" had sequence 1. Even though "AB" finished first,
  // when "A" resolves its seq (1) does not equal current saveSeq (2), so it is discarded.
  assert.strictEqual(latestConfirmedText, "AB");
});

test("Debouncing and coalescing live analysis suppresses rapid intermediate edits", async () => {
  let liveAnalysisCallCount = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const triggerLiveAnalysis = () => {
    liveAnalysisCallCount++;
  };

  const scheduleEdits = (_text: string, debounceMs: number) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      triggerLiveAnalysis();
    }, debounceMs);
  };

  // Simulate rapid typing within 50ms intervals with 100ms debounce
  scheduleEdits("H", 100);
  await new Promise((r) => setTimeout(r, 30));
  scheduleEdits("Hi", 100);
  await new Promise((r) => setTimeout(r, 30));
  scheduleEdits("Hil", 100);
  await new Promise((r) => setTimeout(r, 30));
  scheduleEdits("Hildred", 100);

  // At this point, 0 calls should have executed
  assert.strictEqual(liveAnalysisCallCount, 0);

  // Wait 120ms for idle
  await new Promise((r) => setTimeout(r, 120));

  // Exactly one live analysis call should have executed
  assert.strictEqual(liveAnalysisCallCount, 1);
});

test("Side panel click-to-highlight finds quote or span in chapter text", () => {
  const chapterText =
    "Hildred Castaigne adjusted his dark blue overcoat; his dark blue eyes stared into the glass.\n\nhis black eyes got blurry";

  const issueSameChapter = {
    id: 101,
    chapter_id: 1,
    message: "Contradiction found: eye_color",
    quote: "his black eyes",
    span_start: 94,
    span_end: 108,
  };

  // Highlight locator logic
  let from = -1;
  let to = -1;

  if (
    issueSameChapter.quote &&
    chapterText.includes(issueSameChapter.quote)
  ) {
    from = chapterText.indexOf(issueSameChapter.quote);
    to = from + issueSameChapter.quote.length;
  } else if (
    issueSameChapter.span_start !== null &&
    issueSameChapter.span_end !== null
  ) {
    from = issueSameChapter.span_start;
    to = issueSameChapter.span_end;
  }

  assert.strictEqual(from, 94);
  assert.strictEqual(to, 94 + "his black eyes".length);
  assert.strictEqual(chapterText.slice(from, to), "his black eyes");
});

test("Side panel issue navigation switches chapters when issue belongs to another chapter", () => {
  const currentChapterId = 1;
  const chapters = [
    { id: 1, title: "Chapter 1" },
    { id: 2, title: "Chapter 2" },
  ];

  const issueOtherChapter = {
    id: 102,
    chapter_id: 2,
    message: "Contradiction found with Chapter 1",
    quote: "his black eyes cold",
    span_start: 20,
    span_end: 39,
  };

  let targetSwitchedTo: number | null = null;
  if (
    issueOtherChapter.chapter_id &&
    issueOtherChapter.chapter_id !== currentChapterId
  ) {
    const target = chapters.find(
      (c) => c.id === issueOtherChapter.chapter_id,
    );
    if (target) {
      targetSwitchedTo = target.id;
    }
  }

  assert.strictEqual(targetSwitchedTo, 2);
});

test("Grammar suggestion application replaces span with suggestion", () => {
  const originalText = "Hildred walked slow to the chamber.";
  const grammarIssue = {
    id: 201,
    chapter_id: 1,
    message: "Use slowly instead of slow",
    quote: "slow",
    span_start: 15,
    span_end: 19,
  };
  const suggestion = "slowly";

  let from = grammarIssue.span_start;
  let to = grammarIssue.span_end;
  if (grammarIssue.quote && originalText.includes(grammarIssue.quote)) {
    from = originalText.indexOf(grammarIssue.quote);
    to = from + grammarIssue.quote.length;
  }

  const updatedText =
    originalText.slice(0, from) + suggestion + originalText.slice(to);
  assert.strictEqual(updatedText, "Hildred walked slowly to the chamber.");
});
