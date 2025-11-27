import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AdapterProvider,
  initThreadStore,
  initBlueprintStore,
} from '@chimera/core';
import { ThemeProvider } from '@chimera/core/providers/ThemeProvider';
import '@chimera/core/index.css';
import './index.css';
import App from './App.tsx';
import { WebStorageAdapter } from './adapters/WebStorageAdapter';
import { WebConfigProvider } from './adapters/WebConfigProvider';

// Initialize adapters
const storageAdapter = new WebStorageAdapter();
const configProvider = new WebConfigProvider();

// Initialize stores with adapters
initThreadStore(storageAdapter);
initBlueprintStore(storageAdapter);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AdapterProvider
      storageAdapter={storageAdapter}
      configProvider={configProvider}
    >
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </AdapterProvider>
  </StrictMode>
);
