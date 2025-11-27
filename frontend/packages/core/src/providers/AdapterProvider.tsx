import React, { createContext, useContext } from 'react';
import type {
  StorageAdapter,
  ConfigProvider,
  ThemeEventListener,
} from '@chimera/platform';

interface AdapterContextValue {
  storageAdapter: StorageAdapter;
  configProvider: ConfigProvider;
  themeListener?: ThemeEventListener;
}

const AdapterContext = createContext<AdapterContextValue | null>(null);

/**
 * Provides adapter instances to descendant components via AdapterContext.
 *
 * @param children - React node(s) rendered inside the provider
 * @param storageAdapter - Storage adapter instance made available through context
 * @param configProvider - Configuration provider made available through context
 * @param themeListener - Optional theme event listener made available through context
 * @returns A React element that supplies the adapters and optional theme listener to its children
 */
export function AdapterProvider({
  children,
  storageAdapter,
  configProvider,
  themeListener,
}: {
  children: React.ReactNode;
  storageAdapter: StorageAdapter;
  configProvider: ConfigProvider;
  themeListener?: ThemeEventListener;
}) {
  return (
    <AdapterContext.Provider
      value={{ storageAdapter, configProvider, themeListener }}
    >
      {children}
    </AdapterContext.Provider>
  );
}

export function useAdapters() {
  const context = useContext(AdapterContext);
  if (!context) {
    throw new Error('useAdapters must be used within AdapterProvider');
  }
  return context;
}
