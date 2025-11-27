import type { ConfigProvider } from '@chimera/platform';

export class WebConfigProvider implements ConfigProvider {
  async getBackendUrl(): Promise<string> {
    return 'http://localhost:33003'; // Default Chimera backend port
  }

  getPlatform(): 'desktop' | 'web' {
    return 'web';
  }
}
