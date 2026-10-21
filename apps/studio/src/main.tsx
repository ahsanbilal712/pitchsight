import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { StreamProvider } from "./stream/StreamProvider";
import "./styles/tokens.css";
import "./styles/studio.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <StreamProvider>
      <App />
    </StreamProvider>
  </StrictMode>,
);
