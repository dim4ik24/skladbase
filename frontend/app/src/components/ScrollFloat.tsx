/**
 * ScrollFloat — заголовок, що «випливає» по літерах під час скролу
 * (gsap ScrollTrigger, scrub). Збудовано з нуля (немає референсного
 * вихідника, на відміну від Beams/карусель/редактор) за патерном
 * заголовків react-bits.
 *
 * У TMA скрол-контейнер — внутрішній `.app` div, не `window`, тож
 * `scrollContainerRef` обов'язково передається з App.tsx.
 *
 * Якщо середовище не підтримує ResizeObserver (старий WebView, тестове
 * jsdom-середовище) — рендериться звичайний статичний текст без анімації,
 * без падіння.
 */
import { useEffect, useId, useMemo, useRef } from "react";
import type { RefObject } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

type ScrollFloatTag = "h1" | "h2";

interface ScrollFloatProps {
  children: string;
  as: ScrollFloatTag;
  className?: string;
  scrollContainerRef?: RefObject<HTMLElement | null>;
}

let pluginRegistered = false;

function ensurePlugin(): boolean {
  if (typeof window === "undefined" || typeof ResizeObserver === "undefined") return false;
  if (!pluginRegistered) {
    gsap.registerPlugin(ScrollTrigger);
    pluginRegistered = true;
  }
  return true;
}

export function ScrollFloat({ children, as: Tag, className, scrollContainerRef }: ScrollFloatProps) {
  const containerRef = useRef<HTMLHeadingElement | null>(null);
  const chars = useMemo(() => Array.from(children), [children]);
  const reactId = useId();

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !ensurePlugin()) return;

    const charNodes = el.querySelectorAll<HTMLElement>("[data-sf-char]");
    const tween = gsap.fromTo(
      charNodes,
      { opacity: 0, yPercent: 40, scale: 0.85 },
      {
        opacity: 1,
        yPercent: 0,
        scale: 1,
        ease: "none",
        stagger: 0.02,
        scrollTrigger: {
          trigger: el,
          scroller: scrollContainerRef?.current ?? undefined,
          start: "top 90%",
          end: "top 45%",
          scrub: true,
        },
      },
    );

    return () => {
      tween.scrollTrigger?.kill();
      tween.kill();
    };
  }, [chars, scrollContainerRef]);

  return (
    <Tag ref={containerRef} className={className}>
      {/* Повний текст — для скрінрідерів і пошуку в DOM; розбиті по
          літерах <span> нижче лише анімують, по-літерне озвучення
          скрінрідером не потрібне. */}
      <span className="sr-only">{children}</span>
      <span aria-hidden="true">
        {chars.map((char, index) => (
          <span key={`${reactId}-${index}`} data-sf-char style={{ display: "inline-block" }}>
            {char === " " ? " " : char}
          </span>
        ))}
      </span>
    </Tag>
  );
}
