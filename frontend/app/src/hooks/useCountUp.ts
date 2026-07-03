import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";

const DURATION_MS = 600;

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3;
}

/** 0 -> value за ~600ms (requestAnimationFrame). Instant у тестах
 * (import.meta.env.MODE === "test" — jsdom стабить matchMedia на
 * matches:false, тож prefers-reduced-motion саме по собі тут не поможе)
 * і за prefers-reduced-motion: reduce. */
export function useCountUp(value: number): number {
  const prefersReducedMotion = useReducedMotion();
  const isTestEnv = import.meta.env.MODE === "test";
  const instant = prefersReducedMotion || isTestEnv;
  const [display, setDisplay] = useState(0);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    if (instant) return; // display не рендериться в цьому режимі (див. return нижче)

    const start = performance.now();

    function tick(now: number) {
      const t = Math.min((now - start) / DURATION_MS, 1);
      setDisplay(Math.round(value * easeOutCubic(t)));
      if (t < 1) {
        frameRef.current = requestAnimationFrame(tick);
      }
    }

    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [value, instant]);

  return instant ? value : display;
}
