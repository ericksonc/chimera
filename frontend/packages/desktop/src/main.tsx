import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ThemeProvider } from "@chimera/core/providers/ThemeProvider";
import {
  AdapterProvider,
  initThreadStore,
  initBlueprintStore,
} from "@chimera/core";
import { TauriStorageAdapter, TauriConfigProvider } from "./adapters";
import { TauriThemeListener } from "./adapters/TauriThemeListener";
import "@chimera/core/index.css";

// Initialize adapters
const storageAdapter = new TauriStorageAdapter();
const configProvider = new TauriConfigProvider();
const themeListener = new TauriThemeListener();

// Initialize stores with adapters
initThreadStore(storageAdapter);
initBlueprintStore(storageAdapter);

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AdapterProvider
      storageAdapter={storageAdapter}
      configProvider={configProvider}
      themeListener={themeListener}
    >
      <ThemeProvider themeListener={themeListener}>
        <App />
      </ThemeProvider>
    </AdapterProvider>
  </React.StrictMode>
);
