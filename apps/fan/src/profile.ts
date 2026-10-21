// Viewer profile (schemas/viewer_profile.schema.json): built by the ProfilePicker, validated here with the
// schema's own rules (no validator dependency), kept in localStorage. Storage can throw (private windows,
// blocked site data), so every access is guarded and the app works without it.
export type ViewerMode = "analyst" | "casual" | "player_cam";
export const MODES: ViewerMode[] = ["casual", "analyst", "player_cam"];
export const METRICS = ["pressure", "pitch_control", "ball_speed", "passing", "decision_index"] as const;

export interface ViewerProfile {
  schema_version: "1.0.0";
  viewer_id: string;
  mode: ViewerMode | "studio";
  club: "home" | "away" | null;
  player: string | null;
  metric: (typeof METRICS)[number] | null;
  high_contrast: boolean;
  show_heatmap: boolean;
}

const KEY = "whyline.fan.profile";
const KEYS = ["schema_version", "viewer_id", "mode", "club", "player", "metric", "high_contrast", "show_heatmap"];

/** Problems with a profile against viewer_profile.schema.json (empty list = valid). */
export function validateProfile(p: unknown): string[] {
  const errors: string[] = [];
  if (typeof p !== "object" || p === null) return ["not an object"];
  const o = p as Record<string, unknown>;
  for (const k of Object.keys(o)) if (!KEYS.includes(k)) errors.push(`unknown field ${k}`);
  if (o.schema_version !== "1.0.0") errors.push("schema_version must be 1.0.0");
  if (typeof o.viewer_id !== "string" || !o.viewer_id) errors.push("viewer_id must be a string");
  if (!["analyst", "casual", "player_cam", "studio"].includes(o.mode as string)) errors.push("bad mode");
  if (!(o.club === undefined || o.club === null || o.club === "home" || o.club === "away")) errors.push("bad club");
  if (!(o.player === undefined || o.player === null || (typeof o.player === "string" && /^p_[0-9]{3}$/.test(o.player))))
    errors.push("bad player");
  if (o.mode === "player_cam" && !o.player) errors.push("player is required in player_cam mode");
  if (!(o.metric === undefined || o.metric === null || (METRICS as readonly string[]).includes(o.metric as string)))
    errors.push("bad metric");
  for (const k of ["high_contrast", "show_heatmap"])
    if (o[k] !== undefined && typeof o[k] !== "boolean") errors.push(`${k} must be boolean`);
  return errors;
}

function newViewerId(): string {
  return `v_fan_${Math.random().toString(36).slice(2, 10)}`;
}

export function defaultProfile(): ViewerProfile {
  return {
    schema_version: "1.0.0",
    viewer_id: newViewerId(),
    mode: "casual",
    club: null,
    player: null,
    metric: null,
    high_contrast: false,
    show_heatmap: false,
  };
}

/** Stored profile, overridden by ?mode=&club=&player= (recording and tests), else the default. */
export function loadProfile(): ViewerProfile {
  let stored: ViewerProfile | null = null;
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (parsed && validateProfile(parsed).length === 0) stored = parsed as ViewerProfile;
  } catch {
    stored = null;
  }
  const p = { ...(stored ?? defaultProfile()) };
  const q = new URLSearchParams(window.location.search);
  const mode = q.get("mode");
  if (mode && (MODES as string[]).includes(mode)) p.mode = mode as ViewerMode;
  const club = q.get("club");
  if (club === "home" || club === "away") p.club = club;
  const player = q.get("player");
  if (player && /^p_[0-9]{3}$/.test(player)) p.player = player;
  if (q.get("contrast") === "high") p.high_contrast = true;
  return validateProfile(p).length === 0 ? p : { ...p, mode: "casual" };
}

/** Saves the profile; returns false when storage is unavailable (the app keeps working in memory). */
export function saveProfile(p: ViewerProfile): boolean {
  if (validateProfile(p).length) return false;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(p));
    return true;
  } catch {
    return false;
  }
}
