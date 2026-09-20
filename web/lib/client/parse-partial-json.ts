/**
 * Tolerant parser for the AI SDK streamObject text stream: the accumulated
 * text is partial JSON. Returns the deepest complete prefix value, or
 * undefined when nothing parseable exists yet. Never throws.
 */
export function parsePartialJson(text: string): unknown {
  if (!text.trim()) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    // continue with prefix completion
  }

  const stack: string[] = [];
  let inString = false;
  let escape = false;
  let lastGood = -1;
  let lastGoodStack: string[] = [];

  const n = text.length;
  for (let i = 0; i < n; i++) {
    const ch = text[i] as string;
    if (inString) {
      if (escape) {
        escape = false;
      } else if (ch === '\\') {
        escape = true;
      } else if (ch === '"') {
        inString = false;
        lastGood = i;
        lastGoodStack = [...stack];
      }
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === '{' || ch === '[') {
      stack.push(ch);
      continue;
    }
    if (ch === '}' || ch === ']') {
      stack.pop();
      lastGood = i;
      lastGoodStack = [...stack];
      continue;
    }
    if (ch === ',' || ch === ':') {
      lastGood = i;
      lastGoodStack = [...stack];
      continue;
    }
    if (/\s/.test(ch)) continue;
    const next = text[i + 1];
    if (next === undefined || /[\s,}\]]/.test(next)) {
      lastGood = i;
      lastGoodStack = [...stack];
    }
  }

  if (lastGood < 0) return undefined;

  /** Close any open containers of the last safe position and try to parse. */
  const closed = (rawPrefix: string): unknown => {
    let candidate = rawPrefix.replace(/[,:\s]+$/, '');
    if (candidate === '') {
      candidate = lastGoodStack.map((c) => (c === '{' ? '{' : '[')).join('');
    }
    for (let i = lastGoodStack.length - 1; i >= 0; i--) {
      candidate += lastGoodStack[i] === '{' ? '}' : ']';
    }
    try {
      return JSON.parse(candidate);
    } catch {
      return undefined;
    }
  };

  const prefix = text.slice(0, lastGood + 1).replace(/[,:\s]+$/, '');

  const parsed = closed(prefix);
  if (parsed !== undefined) return parsed;

  // The last token may be a key with no value yet (`, "key":` or a first key
  // like `{"key":`) — drop back to just before it and retry.
  const danglingKey = /(?:^[[{]|,)\s*"(?:[^"\\]|\\.)*"\s*$/.exec(prefix);
  if (danglingKey) {
    return closed(prefix.slice(0, danglingKey.index));
  }
  return undefined;
}
