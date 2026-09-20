'use client';

import { useState } from 'react';
import { Pencil } from 'lucide-react';
import { useProjectStore } from '@/lib/store/project';
import { Dialog } from '@/components/ui/dialog';
import { FormField } from '@/components/ui/form-field';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

export function ProjectCard() {
  const project = useProjectStore((s) => s.project);
  const setProject = useProjectStore((s) => s.setProject);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(project.name);
  const [stack, setStack] = useState(project.stack);

  const openDialog = () => {
    setName(project.name);
    setStack(project.stack);
    setOpen(true);
  };

  const save = () => {
    if (name.trim()) {
      setProject({ name: name.trim(), stack: stack.trim() });
    }
    setOpen(false);
  };

  return (
    <>
      <button
        onClick={openDialog}
        className="w-full rounded-[10px] border border-border bg-card p-3 text-left transition-colors duration-[var(--dur)] hover:bg-card-2"
        aria-label="Edit project"
      >
        <div className="flex items-center justify-between">
          <span className="text-[11px] tracking-[0.6px] text-muted">PROJECT</span>
          <Pencil className="h-3.5 w-3.5 text-muted" aria-hidden />
        </div>
        <div className="mt-1 truncate text-[14px] font-semibold">{project.name}</div>
        <div className="mt-0.5 truncate text-[12px] text-muted">{project.stack}</div>
      </button>

      <Dialog open={open} onOpenChange={setOpen} title="Edit project">
        <div className="flex flex-col gap-3">
          <FormField label="Project name">
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
          </FormField>
          <FormField label="Tech stack">
            <Input
              value={stack}
              onChange={(e) => setStack(e.target.value)}
              maxLength={120}
              placeholder="Next.js, Node API, Postgres"
            />
          </FormField>
          <div className="mt-1 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={save}>
              Save
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
