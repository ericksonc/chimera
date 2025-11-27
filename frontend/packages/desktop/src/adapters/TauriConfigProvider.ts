import { invoke } from "@tauri-apps/api/core";
import type { ConfigProvider } from "@chimera/platform";

/**
 * Tauri implementation of ConfigProvider
 * Gets configuration from Rust backend
 */
export class TauriConfigProvider implements ConfigProvider {
  async getBackendUrl(): Promise<string> {
    return invoke<string>("get_backend_url");
  }

  getPlatform(): "desktop" | "web" {
    return "desktop";
  }
}
