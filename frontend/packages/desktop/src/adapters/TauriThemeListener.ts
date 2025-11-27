import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import type { ThemeEventListener } from '@chimera/platform';

/**
 * Tauri implementation of ThemeEventListener
 * Listens to OS theme changes via Tauri events
 */
export class TauriThemeListener implements ThemeEventListener {
  listen(callback: (theme: 'light' | 'dark') => void): () => void {
    let unlisten: UnlistenFn | null = null;
    let cancelled = false;

    // Start listening (async)
    listen<'light' | 'dark'>('theme-changed', (event) => {
      callback(event.payload);
    })
      .then((fn) => {
        if (cancelled) {
          // If we've already cleaned up, immediately unsubscribe
          fn();
        } else {
          unlisten = fn;
        }
      })
      .catch((error) => {
        console.error('[TauriThemeListener] Failed to register theme listener', error);
      });

    // Return cleanup function
    return () => {
      cancelled = true;
      if (unlisten) {
        unlisten();
        unlisten = null;
      }
    };
  }
}
