/**
 * AtmosphereBackground — статичний green-field фон (editorial sport-poster).
 * Beams/WebGL прибрані: тепер фон = body background (#2E7D46) + ця компонента
 * рендерить нульовий overhead. Пропс `suspended` лишається в сигнатурі
 * щоб не зламати виклики в App.tsx без змін.
 */

interface AtmosphereBackgroundProps {
  suspended?: boolean;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function AtmosphereBackground(_props: AtmosphereBackgroundProps) {
  return null;
}
