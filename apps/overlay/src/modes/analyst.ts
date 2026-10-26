// Analyst mode: heatmap, threat front and every layer. Kinds mirror config/budgets.yaml
// director.modes.analyst (tests/apps/test_viewer_modes.py checks they match).
import type { ModeConfig } from "./config";

export const analyst: ModeConfig = {
  name: "analyst",
  heatmap: true,
  threatFront: true,
  ticker: true,
  playerTrail: false,
  onlyPlayerInvolved: false,
  kinds: [
    "sliding_doors",
    "state_change",
    "big_chance",
    "goal",
    "tempo_shift",
    "pressing_trap",
    "fourth_official",
    "oracle",
    "dugout",
    "decision_index",
    "milestone",
    "recap",
  ],
};
