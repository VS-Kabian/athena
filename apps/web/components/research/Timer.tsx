"use client";
import { useEffect, useRef, useState } from "react";

export function Timer({ running }: { running: boolean }) {
  const [ms, setMs] = useState(0);
  const ref = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  useEffect(() => {
    if (running) {
      const t0 = Date.now();          // start fresh each run (don't carry the previous run's elapsed)
      setMs(0);
      ref.current = setInterval(() => setMs(Date.now() - t0), 200);
    } else if (ref.current) {
      clearInterval(ref.current);
    }
    return () => { if (ref.current) clearInterval(ref.current); };
  }, [running]); // eslint-disable-line react-hooks/exhaustive-deps
  const s = Math.floor(ms / 1000);
  const fmt = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  return <span data-testid="timer" className="tabular-nums">{fmt}</span>;
}
