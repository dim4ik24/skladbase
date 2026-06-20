/**
 * Sparkles — частинки на tsparticles. Адаптовано з пасти (lepikhinb/sparkles),
 * але та пасть писана під @tsparticles/react v3 (`initParticlesEngine`) —
 * у встановленій v4 цього експорту вже нема, рушій ініціалізується через
 * `<ParticlesProvider init>` (рендерить children лише коли він `loaded`,
 * тож власний `isReady`-стан з оригіналу тут не потрібен).
 *
 * Прибрано "use client", типізовано пропси під TS. Важкий ефект (slim
 * тягне купу плагінів) — монтується лише лінькво й вибірково з боку
 * викликача (SubscriptionPaywall); сюди жодної lazy/reduced-motion логіки
 * не закладаємо, цей файл лишається простим переносимим примітивом.
 */
import { useId } from "react";
import { Particles, ParticlesProvider } from "@tsparticles/react";
import { loadSlim } from "@tsparticles/slim";
import type { Engine, ISourceOptions } from "@tsparticles/engine";

interface SparklesProps {
  className?: string;
  size?: number;
  minSize?: number | null;
  density?: number;
  speed?: number;
  minSpeed?: number | null;
  opacity?: number;
  opacitySpeed?: number;
  minOpacity?: number | null;
  color?: string;
  background?: string;
  options?: ISourceOptions;
}

// Модульний рівень: один стабільний референс на весь час життя апки —
// ParticlesProvider кидає помилку, якщо `init` змінюється між рендерами.
async function initEngine(engine: Engine): Promise<void> {
  await loadSlim(engine);
}

function SparklesParticles({
  className,
  size = 1,
  minSize = null,
  density = 800,
  speed = 1,
  minSpeed = null,
  opacity = 1,
  opacitySpeed = 3,
  minOpacity = null,
  color = "#FFFFFF",
  background = "transparent",
  options = {},
}: SparklesProps) {
  const id = useId();

  const defaultOptions: ISourceOptions = {
    background: {
      color: { value: background },
    },
    fullScreen: {
      enable: false,
      zIndex: 1,
    },
    fpsLimit: 120,
    particles: {
      color: { value: color },
      move: {
        enable: true,
        direction: "none",
        speed: {
          min: minSpeed || speed / 10,
          max: speed,
        },
        straight: false,
      },
      number: { value: density },
      opacity: {
        value: {
          min: minOpacity || opacity / 10,
          max: opacity,
        },
        animation: {
          enable: true,
          sync: false,
          speed: opacitySpeed,
        },
      },
      size: {
        value: {
          min: minSize || size / 2.5,
          max: size,
        },
      },
    },
    detectRetina: true,
  };

  return <Particles id={id} options={{ ...defaultOptions, ...options }} className={className} />;
}

export function Sparkles(props: SparklesProps) {
  return (
    <ParticlesProvider init={initEngine}>
      <SparklesParticles {...props} />
    </ParticlesProvider>
  );
}
