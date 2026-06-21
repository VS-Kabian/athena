"use client";

type Props = { canStart: boolean; running: boolean; onStart: () => void; onCancel: () => void };

export function StartCancel({ canStart, running, onStart, onCancel }: Props) {
  return (
    <div className="flex gap-3">
      <button className="btn-primary disabled:opacity-40" disabled={!canStart || running} onClick={onStart}>
        Start Research
      </button>
      <button className="btn-ghost disabled:opacity-40" disabled={!running} onClick={onCancel}>
        Cancel Research
      </button>
    </div>
  );
}
