// Overlay routes: the broadcast overlay, or the 3D Sliding Doors replay at /replay3d?cf=<id>.
// Static hosting without SPA fallback can use ?view=replay3d instead of the path.
import { lazy, Suspense } from "react";
import App from "./App";

const Replay3D = lazy(() => import("./replay3d/Replay3D"));

export function isReplay3D(): boolean {
  return window.location.pathname.endsWith("/replay3d") || new URLSearchParams(window.location.search).get("view") === "replay3d";
}

export default function Routes() {
  return isReplay3D() ? (
    <Suspense fallback={null}>
      <Replay3D />
    </Suspense>
  ) : (
    <App />
  );
}
