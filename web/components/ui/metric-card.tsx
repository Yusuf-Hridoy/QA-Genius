import { cn } from '@/lib/utils/cn';

export function MetricCard({
  label,
  value,
  sub,
  className,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  className?: string;
}) {
  return (
    <div className={cn('rounded-[var(--radius)] bg-card-2 px-3.5 py-3', className)}>
      <div className="text-[11px] text-muted">{label}</div>
      <div className="font-display text-[22px] font-semibold leading-7">{value}</div>
      {sub ? <div className="mt-0.5 text-[12px] text-muted">{sub}</div> : null}
    </div>
  );
}
