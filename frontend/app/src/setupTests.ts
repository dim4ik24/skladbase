import "@testing-library/jest-dom/vitest";

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
