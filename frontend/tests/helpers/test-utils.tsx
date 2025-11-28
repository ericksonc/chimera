/**
 * React Testing Library utilities for Chimera components.
 *
 * Provides a custom render function that wraps components with
 * required providers (if any).
 */

import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

/**
 * Custom render function that can wrap components with providers.
 * Currently passes through to RTL render, but structured for future
 * provider additions (theme, auth, etc).
 */
interface CustomRenderOptions extends Omit<RenderOptions, "wrapper"> {
  // Add provider-specific options here as needed
}

function AllProviders({ children }: { children: ReactNode }) {
  // Add providers here as needed
  return <>{children}</>;
}

function customRender(
  ui: ReactElement,
  options?: CustomRenderOptions
): ReturnType<typeof render> {
  return render(ui, { wrapper: AllProviders, ...options });
}

// Re-export everything from RTL
export * from "@testing-library/react";

// Override render with our custom version
export { customRender as render };
