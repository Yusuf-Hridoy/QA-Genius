/**
 * Character-for-character port of v1 prompts.py lines 35–83 (GLOBAL_RULES,
 * JSON_OUTPUT_RULES, ANTI_QUOTE_TRAP, LIMITATIONS_INSTRUCTION,
 * CONFIDENCE_INSTRUCTION, _apply_global_rules). Snapshot-tested; change only
 * with a deliberate prompt change and a snapshot update in the same commit.
 */

export const GLOBAL_RULES = `
GLOBAL RULES — apply to every output you generate:
1. CLASSIFY EVERY VALUE you produce as one of:
   - DERIVED: lifted directly from the user's input
   - COMPUTED: derivable through stated math or logic from the input
   - UNKNOWN: cannot be determined from the input
2. NEVER present an UNKNOWN value as a fact. For UNKNOWN values you must:
   - Mark them with [VERIFY], [NOT PROVIDED], or [PLEASE CONFIRM], OR
   - Omit them entirely from the output
3. NEVER ship code or content with self-incriminating comments such as
   "placeholder, should be X", "TODO: replace this", "using displayed value
   for some reason", or any phrase admitting the value is wrong/guessed.
   If you cannot generate working content, list it under a "Limitations"
   section and explain what the user needs to provide.
4. NEVER hallucinate values that look plausible but aren't grounded in input
   (specific prices, version numbers, percentages, ID counts, dates, country
   codes, ISO codes, etc.). If a specific value is needed and not provided,
   use a partial assertion or placeholder.
5. BEFORE flagging any finding as a violation, explicitly verify:
   (a) the constraint, (b) the actual value, (c) whether the value
   satisfies the constraint. Only flag if the answer to (c) is "no". False
   positives are worse than missed findings  --  they erode trust in the
   entire report.
6. FOR EVERY NUMERICAL SCORE you produce, include a brief breakdown showing
   the components and weights used. Unexplained scores are forbidden.
7. READ THE INPUT TWICE before generating output. On the first read,
   identify every specific entity, technology, role, constraint, and
   context clue. On the second read, ensure your output references those
   specifics. Do not produce generic content that would apply to any
   project.
8. NEVER reference content from other tabs. Each tab is a self-contained
   analysis. Placeholder text shown in the UI is not user input  --  only
   treat the actual user input as data to analyze.
`;

export const JSON_OUTPUT_RULES = `
CRITICAL JSON FORMATTING RULES — failure to follow these will break the application:

1. Respond with ONLY a valid JSON object. No prose before or after. No markdown code fences (no \`\`\`json blocks).

2. ALL double quotes inside string values MUST be escaped with backslash. Examples:
   ❌ WRONG: "description": "He said "hello" today"
   ✅ RIGHT: "description": "He said \\"hello\\" today"

3. If a string value contains a quoted phrase, escape EVERY inner quote.
   ❌ WRONG: "issue": "Phrase "maybe later" is vague"
   ✅ RIGHT: "issue": "Phrase \\"maybe later\\" is vague"

4. Use \\n for newlines inside string values, not actual line breaks.

5. Do not use single quotes for JSON strings — only double quotes.

6. Do not include trailing commas after the last item in objects or arrays.

7. All keys must be strings in double quotes.

8. Verify your output is valid JSON before responding. If you're unsure, simplify the content.
`;

export const ANTI_QUOTE_TRAP = `
When referencing phrases from the user's input in your analysis:
- Paraphrase rather than quote verbatim when possible
- If you must quote, use single quotes ('like this') instead of double quotes inside JSON string values
- Never use double quotes around inline phrases within a JSON string value
- Example: write "the phrase 'maybe later' is vague" NOT "the phrase \\"maybe later\\" is vague"
`;

export const LIMITATIONS_INSTRUCTION =
  'If any part of the output cannot be reliably generated from the input, ' +
  "list it under a final 'Limitations' section explaining what's missing and what the user should provide.";

export const CONFIDENCE_INSTRUCTION =
  'For every finding, classify confidence as HIGH (directly stated in input), ' +
  'MEDIUM (inferred from input), or LOW (general best practice not specific to this input). ' +
  'Display the confidence label on each finding.';

/** Prepend global rules and append limitations / confidence instructions (v1 _apply_global_rules). */
export function applyGlobalRules(baseSystemPrompt: string, includeAntiQuoteTrap = false): string {
  const parts = [GLOBAL_RULES, JSON_OUTPUT_RULES];
  if (includeAntiQuoteTrap) {
    parts.push(ANTI_QUOTE_TRAP);
  }
  parts.push(baseSystemPrompt, LIMITATIONS_INSTRUCTION, CONFIDENCE_INSTRUCTION);
  return parts.join('\n\n');
}
