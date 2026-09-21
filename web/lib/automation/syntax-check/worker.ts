import { checkFiles } from './check';
import type { FileReport, InputFile } from './types';

export type CheckRequestMessage = {
  id: number;
  files: InputFile[];
  framework?: string;
};

export type CheckResponseMessage = {
  id: number;
  reports: FileReport[];
};

/** Pure request → response mapping; unit-tested without spawning a Worker. */
export async function handleCheckRequest(msg: CheckRequestMessage): Promise<CheckResponseMessage> {
  const reports = await checkFiles(msg.files, { framework: msg.framework });
  return { id: msg.id, reports };
}

type WorkerScope = {
  onmessage: ((e: MessageEvent<CheckRequestMessage>) => void) | null;
  postMessage: (msg: CheckResponseMessage) => void;
};

declare const self: WorkerScope | undefined;

// Worker entry: only wired when running inside a Worker.
if (typeof self !== 'undefined' && self !== null) {
  self.onmessage = (e: MessageEvent<CheckRequestMessage>) => {
    void handleCheckRequest(e.data).then((response) => self.postMessage(response));
  };
}
