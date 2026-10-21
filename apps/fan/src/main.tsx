import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Skeleton from T-001; the real shell arrives with its own ticket.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <div>WHYLINE fan</div>
  </StrictMode>,
);
