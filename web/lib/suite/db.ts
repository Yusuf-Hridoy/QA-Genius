'use client';

import { openDB, type DBSchema } from 'idb';
import type { SuiteRow } from './parse';

export type StoredSuite = {
  suiteId: string;
  fileName: string;
  importedAt: string;
  rows: SuiteRow[];
};

type SuiteDb = DBSchema & {
  suiteRows: {
    key: string;
    value: StoredSuite;
  };
};

const DB_NAME = 'qag';
const STORE = 'suiteRows';

async function db() {
  return openDB<SuiteDb>(DB_NAME, 1, {
    upgrade(database) {
      if (!database.objectStoreNames.contains(STORE)) {
        database.createObjectStore(STORE, { keyPath: 'suiteId' });
      }
    },
  });
}

/** One suite per suiteId; re-import replaces the previous rows. */
export async function putSuite(suite: StoredSuite): Promise<void> {
  const database = await db();
  await database.put(STORE, suite);
}

export async function getSuite(suiteId: string): Promise<StoredSuite | undefined> {
  const database = await db();
  return database.get(STORE, suiteId);
}
