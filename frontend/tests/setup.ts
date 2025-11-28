/**
 * Vitest setup file - runs before all tests.
 *
 * Sets up:
 * - @testing-library/jest-dom matchers
 * - Global mocks for browser APIs not available in jsdom
 */

import "@testing-library/jest-dom/vitest";

// Mock window.matchMedia (not implemented in jsdom)
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

// Mock ResizeObserver (not implemented in jsdom)
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

window.ResizeObserver = ResizeObserverMock;
