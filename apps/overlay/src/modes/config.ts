// Viewer-mode configuration (TECH_PLAN 1.9 viewer modes, config/budgets.yaml director.modes). The api already
// filters cues per viewer (T-033); the overlay applies the same rules so fixture playback and recordings match.
import type { OverlayState } from "../stream/reducer";
import type { Cue } from "../stream/types";
import { analyst } from "./analyst";
import { casual } from "./casual";
import { playerCam } from "./playerCamConfig";

export interface ModeConfig {
  name: string;
  heatmap: boolean;
  threatFront: boolean;
  ticker: boolean;
  playerTrail: boolean;
  onlyPlayerInvolved: boolean;
  kinds: string[] | null; // null = every kind
}

const studio: ModeConfig = { ...analyst, name: "studio", kinds: null };
const MODES: Record<string, ModeConfig> = { analyst, casual, player_cam: playerCam, studio };

export function modeConfig(state: OverlayState): ModeConfig {
  return MODES[state.profile?.mode ?? "analyst"] ?? analyst;
}

/** Whether a cue may be on this overlay in its mode. */
export function modeAllows(state: OverlayState, cue: Cue): boolean {
  const cfg = modeConfig(state);
  if (cfg.kinds && !cfg.kinds.includes(cue.kind)) return false;
  if (cfg.onlyPlayerInvolved) {
    const players = (cue.targets as { players?: string[] } | undefined)?.players ?? [];
    return Boolean(state.profile?.player && players.includes(state.profile.player));
  }
  return true;
}
