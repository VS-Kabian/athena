"use client";
import { useState } from "react";

export function RoundsSlider({ onChange, disabled }: { onChange: (n: number) => void; disabled?: boolean }) {
  const [rounds, setRounds] = useState(2);
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm" style={{ color: "var(--muted)" }} htmlFor="rounds">
        Research rounds: <span style={{ color: "var(--accent)" }}>{rounds}</span>
      </label>
      <input id="rounds" type="range" min={1} max={5} value={rounds} disabled={disabled}
             onChange={(e) => { const n = Number(e.target.value); setRounds(n); onChange(n); }} />
    </div>
  );
}
