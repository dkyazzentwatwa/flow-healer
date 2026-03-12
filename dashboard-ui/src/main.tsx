import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";
import "./styles.css";

declare global {
  interface Window {
    __FLOW_HEALER_BOOTSTRAP__?: {
      notice?: string;
      authMode?: string;
      authTokenEnv?: string;
      refreshMs?: number;
      generatedAt?: string;
    };
  }
}

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Dashboard root element not found.");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App bootstrap={window.__FLOW_HEALER_BOOTSTRAP__ ?? {}} />
  </React.StrictMode>,
);
