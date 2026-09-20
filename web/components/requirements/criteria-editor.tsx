'use client';

import { useEffect, useRef, type MutableRefObject } from 'react';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, ListChecks, Plus, Trash2 } from 'lucide-react';
import { useRunStore } from '@/lib/store/run';
import type { AcceptanceCriterion } from '@/lib/pipeline/types';
import { Pill } from '@/components/ui/pill';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';

function AutoGrowTextarea({
  value,
  onChange,
  ariaLabel,
}: {
  value: string;
  onChange: (text: string) => void;
  ariaLabel: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  return (
    <textarea
      ref={ref}
      value={value}
      aria-label={ariaLabel}
      rows={1}
      onChange={(e) => onChange(e.target.value)}
      className="w-full resize-none overflow-hidden rounded-[var(--qg-radius)] border border-border bg-card px-2.5 py-2 text-[13px] text-text focus-visible:outline-none"
      style={{ boxShadow: 'none' }}
    />
  );
}

function SortableRow({
  criterion,
  index,
  highlight,
  rowRef,
}: {
  criterion: AcceptanceCriterion;
  index: number;
  highlight: boolean;
  rowRef?: (el: HTMLLIElement | null) => void;
}) {
  const updateCriterion = useRunStore((s) => s.updateCriterion);
  const removeCriterion = useRunStore((s) => s.removeCriterion);
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: criterion.id });

  const style = {
    transform: CSS.Translate.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : undefined,
  };

  return (
    <li
      ref={(el) => {
        setNodeRef(el);
        rowRef?.(el);
      }}
      style={style}
      data-testid="criterion-row"
      data-criterion-id={criterion.id}
      className={
        highlight
          ? 'flex items-start gap-2 rounded-[var(--qg-radius-card)] border border-accent bg-accent-soft/40 p-2.5'
          : 'flex items-start gap-2 rounded-[var(--qg-radius-card)] border border-border bg-card p-2.5'
      }
    >
      <button
        type="button"
        ref={setActivatorNodeRef}
        aria-label={`Reorder ${criterion.id}`}
        className="mt-2 cursor-grab touch-none rounded p-1 text-muted hover:bg-card-2 active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4" aria-hidden />
      </button>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <Pill tone="neutral" className="w-fit font-mono">
          {criterion.id}
        </Pill>
        <AutoGrowTextarea
          value={criterion.text}
          onChange={(text) => updateCriterion(index, text)}
          ariaLabel={`${criterion.id} text`}
        />
      </div>
      <button
        type="button"
        aria-label={`Delete ${criterion.id}`}
        onClick={() => removeCriterion(index)}
        className="mt-2 rounded p-1 text-muted hover:bg-card-2 hover:text-text"
      >
        <Trash2 className="h-4 w-4" aria-hidden />
      </button>
    </li>
  );
}

/**
 * Step 2 — editable acceptance criteria list. Ids are recomputed AC-1..n
 * from order on every change (in the run store).
 */
export function CriteriaEditor({
  highlightId,
  rowRefs,
}: {
  highlightId?: string | null;
  rowRefs?: MutableRefObject<Map<string, HTMLLIElement>>;
}) {
  const criteria = useRunStore((s) => s.run.criteria);
  const addCriterion = useRunStore((s) => s.addCriterion);
  const reorderCriteria = useRunStore((s) => s.reorderCriteria);
  const items = criteria?.items ?? [];

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = items.findIndex((c) => c.id === active.id);
    const to = items.findIndex((c) => c.id === over.id);
    if (from === -1 || to === -1) return;
    reorderCriteria(from, to);
  };

  if (items.length === 0) {
    return (
      <EmptyState
        icon={ListChecks}
        headline="No acceptance criteria yet"
        description="Generate them from your story in step 1, or start from scratch below."
        action={{ label: 'Add criterion', onClick: () => addCriterion('') }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={items.map((c) => c.id)} strategy={verticalListSortingStrategy}>
          <ul className="flex flex-col gap-2" aria-label="Acceptance criteria">
            {items.map((criterion, i) => (
              <SortableRow
                key={criterion.id}
                criterion={criterion}
                index={i}
                highlight={highlightId === criterion.id}
                rowRef={
                  rowRefs
                    ? (el) => {
                        if (el) rowRefs.current.set(criterion.id, el);
                        else rowRefs.current.delete(criterion.id);
                      }
                    : undefined
                }
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
      <div>
        <Button variant="ghost" onClick={() => addCriterion('')}>
          <Plus className="h-3.5 w-3.5" aria-hidden />
          Add criterion
        </Button>
      </div>
    </div>
  );
}
