import { nanoid } from 'nanoid';

export function newId(): string {
  return nanoid(12);
}

export function newRequestId(): string {
  return nanoid(16);
}
