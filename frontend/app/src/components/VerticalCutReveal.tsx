/**
 * VerticalCutReveal — адаптовано з пасти (danielpetho/vertical-cut-reveal):
 * прибрано "use client", framer-motion -> motion/react (стандартизація,
 * щоб не тягти ще один пакет окрім motion), @/lib/utils -> локальний cn().
 *
 * Типізація переписана охайніше за оригінал: замість динамічної форми
 * `elements` (string[] чи WordObject[] залежно від splitBy, з кастами
 * при рендері) тут одразу будуємо нормалізований WordObject[] для всіх
 * режимів splitBy — поведінка та сама, типи строгі без `as`.
 */
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { motion } from "motion/react";
import type { Transition } from "motion/react";
import { cn } from "../lib/cn";

interface VerticalCutRevealProps {
  children: ReactNode;
  reverse?: boolean;
  transition?: Transition;
  splitBy?: "words" | "characters" | "lines" | string;
  staggerDuration?: number;
  staggerFrom?: "first" | "last" | "center" | "random" | number;
  containerClassName?: string;
  wordLevelClassName?: string;
  elementLevelClassName?: string;
  onClick?: () => void;
  onStart?: () => void;
  onComplete?: () => void;
  autoStart?: boolean;
}

export interface VerticalCutRevealRef {
  startAnimation: () => void;
  reset: () => void;
}

interface WordObject {
  characters: string[];
  needsSpace: boolean;
}

function splitIntoCharacters(text: string): string[] {
  if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
    const segmenter = new Intl.Segmenter("en", { granularity: "grapheme" });
    return Array.from(segmenter.segment(text), ({ segment }) => segment);
  }
  return Array.from(text);
}

export const VerticalCutReveal = forwardRef<VerticalCutRevealRef, VerticalCutRevealProps>(
  (
    {
      children,
      reverse = false,
      transition = { type: "spring", stiffness: 190, damping: 22 },
      splitBy = "words",
      staggerDuration = 0.2,
      staggerFrom = "first",
      containerClassName,
      wordLevelClassName,
      elementLevelClassName,
      onClick,
      onStart,
      onComplete,
      autoStart = true,
    },
    ref,
  ) => {
    const containerRef = useRef<HTMLSpanElement>(null);
    const text = typeof children === "string" ? children : (children?.toString() ?? "");
    const [isAnimating, setIsAnimating] = useState(false);

    const wordObjects = useMemo<WordObject[]>(() => {
      const words = text.split(" ");
      if (splitBy === "characters") {
        return words.map((word, i) => ({
          characters: splitIntoCharacters(word),
          needsSpace: i !== words.length - 1,
        }));
      }
      const units =
        splitBy === "words" ? words : splitBy === "lines" ? text.split("\n") : text.split(splitBy);
      return units.map((unit, i) => ({ characters: [unit], needsSpace: i !== units.length - 1 }));
    }, [text, splitBy]);

    const getStaggerDelay = useCallback(
      (index: number) => {
        const total =
          splitBy === "characters"
            ? wordObjects.reduce(
                (acc, word) => acc + word.characters.length + (word.needsSpace ? 1 : 0),
                0,
              )
            : wordObjects.length;
        if (staggerFrom === "first") return index * staggerDuration;
        if (staggerFrom === "last") return (total - 1 - index) * staggerDuration;
        if (staggerFrom === "center") {
          const center = Math.floor(total / 2);
          return Math.abs(center - index) * staggerDuration;
        }
        if (staggerFrom === "random") {
          const randomIndex = Math.floor(Math.random() * total);
          return Math.abs(randomIndex - index) * staggerDuration;
        }
        return Math.abs(staggerFrom - index) * staggerDuration;
      },
      [wordObjects, splitBy, staggerFrom, staggerDuration],
    );

    const startAnimation = useCallback(() => {
      setIsAnimating(true);
      onStart?.();
    }, [onStart]);

    useImperativeHandle(ref, () => ({
      startAnimation,
      reset: () => setIsAnimating(false),
    }));

    useEffect(() => {
      if (autoStart) startAnimation();
    }, [autoStart, startAnimation]);

    const variants = {
      hidden: { y: reverse ? "-100%" : "100%" },
      visible: (i: number) => ({
        y: 0,
        transition: {
          ...transition,
          delay: ((transition?.delay as number) || 0) + getStaggerDelay(i),
        },
      }),
    };

    return (
      <span
        className={cn("flex flex-wrap whitespace-pre-wrap", splitBy === "lines" && "flex-col", containerClassName)}
        onClick={onClick}
        ref={containerRef}
      >
        <span className="sr-only">{text}</span>

        {wordObjects.map((wordObj, wordIndex, array) => {
          const previousCharsCount = array
            .slice(0, wordIndex)
            .reduce((sum, word) => sum + word.characters.length, 0);

          return (
            <span
              key={wordIndex}
              aria-hidden="true"
              className={cn("inline-flex overflow-hidden", wordLevelClassName)}
            >
              {wordObj.characters.map((char, charIndex) => (
                <span className={cn("relative whitespace-pre-wrap", elementLevelClassName)} key={charIndex}>
                  <motion.span
                    custom={previousCharsCount + charIndex}
                    initial="hidden"
                    animate={isAnimating ? "visible" : "hidden"}
                    variants={variants}
                    onAnimationComplete={
                      wordIndex === wordObjects.length - 1 && charIndex === wordObj.characters.length - 1
                        ? onComplete
                        : undefined
                    }
                    className="inline-block"
                  >
                    {char}
                  </motion.span>
                </span>
              ))}
              {wordObj.needsSpace && <span> </span>}
            </span>
          );
        })}
      </span>
    );
  },
);

VerticalCutReveal.displayName = "VerticalCutReveal";
