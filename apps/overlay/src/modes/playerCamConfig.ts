// Player-Cam mode: the player trail and player tags, only cues involving the player. Kinds mirror
// config/budgets.yaml director.modes.player_cam (tests/apps/test_viewer_modes.py checks they match).
import type { ModeConfig } from "./config";

export const playerCam: ModeConfig = {
  name: "player_cam",
  heatmap: false,
  threatFront: false,
  ticker: true,
  playerTrail: true,
  onlyPlayerInvolved: true,
  kinds: ["player_tag", "milestone", "decision_index", "sliding_doors", "goal", "fourth_official"],
};
