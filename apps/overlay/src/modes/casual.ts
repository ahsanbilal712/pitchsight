// Casual mode (TECH_PLAN 1.9): no heatmap, no threat front, no ticker, only its allowed kinds. Kinds mirror
// config/budgets.yaml director.modes.casual (tests/apps/test_viewer_modes.py checks they match).
import type { ModeConfig } from "./config";

export const casual: ModeConfig = {
  name: "casual",
  heatmap: false,
  threatFront: false,
  ticker: false,
  playerTrail: false,
  onlyPlayerInvolved: false,
  kinds: ["goal", "big_chance", "milestone", "fourth_official", "sliding_doors"],
};
