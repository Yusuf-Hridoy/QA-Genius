import { dateStamp, downloadText } from './download';

/** Raw output object, pretty-printed — available for every kind. */
export function downloadJson(data: unknown, kind: string, slug: string) {
  downloadText(
    `${slug}-${kind}-${dateStamp()}.json`,
    JSON.stringify(data, null, 2),
    'application/json',
  );
}
