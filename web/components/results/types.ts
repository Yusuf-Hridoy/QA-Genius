export type ResultProps = {
  /** Partially-streamed output object; undefined until the first chunk arrives. */
  data: Record<string, unknown> | undefined;
  isLoading: boolean;
  /** Last submitted request values (evidence attachments, coverage inputs). */
  input?: Record<string, unknown>;
};

export type ExportsProps = {
  data: Record<string, unknown>;
  /** Last submitted request values (used, e.g., for the .feature title). */
  input: Record<string, unknown>;
};
