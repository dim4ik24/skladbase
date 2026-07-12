import "@testing-library/jest-dom/vitest";

// jsdom does not implement IntersectionObserver (TeamSection: scroll-collapse
// of an expanded panel) — safe no-op default so any test that happens to
// render an expanded panel doesn't crash. Tests that need to actually FIRE
// the callback replace window.IntersectionObserver locally (see
// App.test.tsx "collapses on scroll-out" tests) and restore it afterwards.
class NoopIntersectionObserver implements IntersectionObserver {
  readonly root: Element | Document | null = null;
  readonly rootMargin: string = "";
  readonly scrollMargin: string = "";
  readonly thresholds: ReadonlyArray<number> = [];
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}
window.IntersectionObserver = NoopIntersectionObserver;

// jsdom does not implement matchMedia — stub it so components that call it
// (e.g. AtmosphereBackground: prefers-reduced-motion check) don't throw.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
