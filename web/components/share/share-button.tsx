'use client';

import { useMemo, useState } from 'react';
import { Share2 } from 'lucide-react';
import type { Run } from '@/lib/pipeline/types';
import {
  MAX_BYTES,
  WARN_BYTES,
  encodeShare,
  formatKilobytes,
  fragmentBytes,
} from '@/lib/share/codec';
import { Dialog } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Pill } from '@/components/ui/pill';
import { copyWithToast } from '@/components/ui/copy-button';

/**
 * Share entry point: builds the read-only link (payload in the URL fragment,
 * never sent to the server) and shows it in a dialog with size guidance.
 */
export function ShareButton({
  run,
  project,
  disabled,
}: {
  run: Run;
  project: { name: string; stack: string };
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [origin, setOrigin] = useState('');

  const fragment = useMemo(() => {
    if (!open) return '';
    try {
      return encodeShare(run, project);
    } catch {
      return '';
    }
  }, [open, run, project]);

  const openDialog = () => {
    setOrigin(window.location.origin);
    setOpen(true);
  };

  const bytes = fragmentBytes(fragment);
  const tooLong = bytes > MAX_BYTES;
  const link = fragment && origin ? `${origin}/share#${fragment}` : '';

  return (
    <>
      <Button variant="secondary" onClick={openDialog} disabled={disabled}>
        <Share2 className="h-3.5 w-3.5" aria-hidden />
        Share
      </Button>
      <Dialog open={open} onOpenChange={setOpen} title="Share read-only result">
        <div className="flex flex-col gap-3">
          <p className="text-[13px] text-text-2">
            The result travels inside the link itself. No data is stored on the server, and no keys
            are included.
          </p>
          <label htmlFor="share-link" className="sr-only">
            Share link
          </label>
          <input
            id="share-link"
            readOnly
            value={link}
            onFocus={(e) => e.target.select()}
            className="w-full rounded-[var(--qg-radius)] border border-border bg-card-2 px-2.5 py-2 font-mono text-[12px] text-text"
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12px] text-muted">Link is {formatKilobytes(bytes)}</span>
            {bytes > WARN_BYTES && !tooLong ? (
              <Pill tone="warn">
                Very long links may not work in some messaging apps — export a file instead.
              </Pill>
            ) : null}
            {tooLong ? (
              <Pill tone="bad">Link is too long to share — export a file instead.</Pill>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              onClick={() => void copyWithToast(link, 'Link copied')}
              disabled={!link || tooLong}
            >
              Copy link
            </Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Close
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
