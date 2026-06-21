"use client";
import { useEffect, useState } from "react";

type Theme = "dark" | "light";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const saved = localStorage.getItem("athena:theme");
    if (saved === "light" || saved === "dark") setTheme(saved);
  }, []);

  function apply(t: Theme) {
    setTheme(t);
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("athena:theme", t); } catch {}
  }

  return (
    <div className="theme-toggle" role="group" aria-label="Color theme">
      <button className={theme === "dark" ? "on" : ""} aria-pressed={theme === "dark"}
        aria-label="Dark theme" title="Dark" onClick={() => apply("dark")}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      </button>
      <button className={theme === "light" ? "on" : ""} aria-pressed={theme === "light"}
        aria-label="Light theme" title="Light" onClick={() => apply("light")}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.5 1.5M17.9 17.9l1.5 1.5M2.5 12h2M19.5 12h2M4.6 19.4l1.5-1.5M17.9 6.1l1.5-1.5" />
        </svg>
      </button>
    </div>
  );
}
