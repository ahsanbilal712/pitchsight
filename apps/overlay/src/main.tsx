import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { installRecordMode } from "./record";
import Routes from "./routes";
import { StreamProvider } from "./stream/StreamProvider";
import "./styles/tokens.css";
import "./styles/stage.css";
import "./styles/broadcast.css";

installRecordMode();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <StreamProvider>
      <Routes />
    </StreamProvider>
  </StrictMode>,
);
