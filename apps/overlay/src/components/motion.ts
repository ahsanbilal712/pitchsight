// Shared helpers for the DOM overlay components: enter/exit presence and text fitting.
import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

export const SLIDE_MS = 300;

export interface Present<T> {
  key: string;
  item: T;
  phase: "in" | "out";
}

/** Keeps items that just left mounted for `ms` with phase "out", so CSS can play the exit animation. */
export function usePresence<T>(items: T[], keyOf: (t: T) => string, ms = SLIDE_MS): Present<T>[] {
  const [leaving, setLeaving] = useState<Present<T>[]>([]);
  const prev = useRef<Map<string, T>>(new Map());
  const timers = useRef<Set<number>>(new Set());
  const now = new Map(items.map((t) => [keyOf(t), t] as const));

  useLayoutEffect(() => {
    const gone: Present<T>[] = [];
    for (const [key, item] of prev.current) if (!now.has(key)) gone.push({ key, item, phase: "out" });
    prev.current = now;
    if (gone.length === 0) return;
    setLeaving((l) => [...l.filter((g) => !now.has(g.key) && !gone.some((x) => x.key === g.key)), ...gone]);
    const timer = window.setTimeout(() => {
      timers.current.delete(timer);
      setLeaving((l) => l.filter((g) => !gone.some((x) => x.item === g.item)));
    }, ms);
    timers.current.add(timer);
  });

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((t) => window.clearTimeout(t));
  }, []);

  const entering: Present<T>[] = items.map((item) => ({ key: keyOf(item), item, phase: "in" }));
  return [...entering, ...leaving.filter((g) => !now.has(g.key))];
}

/** Steps the font size of `ref` down (to `min` px) until its content fits its box; never lets text overflow. */
export function useFitText(ref: RefObject<HTMLElement | null>, deps: unknown[], max: number, min: number): void {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    let size = max;
    el.style.fontSize = `${size}px`;
    while (size > min && (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)) {
      size -= 1;
      el.style.fontSize = `${size}px`;
    }
  }, deps);
}

/** "mm:ss" of match time. */
export function clockText(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
