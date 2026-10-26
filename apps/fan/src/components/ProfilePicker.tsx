// Profile picker: mode, club, player, metric, high contrast. Every change is a new
// validated ViewerProfile; the stream reconnects with it.
import { surname, useLeague } from "../league";
import { MODES, METRICS, type ViewerMode, type ViewerProfile } from "../profile";
import { useStream } from "../stream/StreamProvider";

const MODE_LABEL: Record<ViewerMode, string> = { casual: "Casual", analyst: "Analyst", player_cam: "Player-Cam" };

export default function ProfilePicker({ profile, onChange }: { profile: ViewerProfile; onChange: (p: ViewerProfile) => void }) {
  const state = useStream();
  const lg = useLeague();
  const clubs = state.hello?.clubs ?? lg?.golden;
  const ids = state.playerIds;
  const set = (patch: Partial<ViewerProfile>) => onChange({ ...profile, ...patch });
  const pickMode = (mode: ViewerMode) =>
    set({
      mode,
      player: mode === "player_cam" ? (profile.player ?? ids[10] ?? ids[0] ?? null) : profile.player,
      show_heatmap: mode === "analyst",
    });
  return (
    <section className="picker" data-testid="profile-picker">
      <div className="seg" role="radiogroup" aria-label="Mode">
        {MODES.map((m) => (
          <button
            key={m}
            type="button"
            role="radio"
            aria-checked={profile.mode === m}
            data-testid={`mode-${m}`}
            onClick={() => pickMode(m)}
          >
            {MODE_LABEL[m]}
          </button>
        ))}
      </div>
      <div className="row">
        <label>
          Club
          <select
            data-testid="club"
            value={profile.club ?? ""}
            onChange={(e) => set({ club: (e.target.value || null) as ViewerProfile["club"] })}
          >
            <option value="">Neutral</option>
            <option value="home">{(clubs && lg?.clubs[clubs.home]?.short_name) ?? "Home"}</option>
            <option value="away">{(clubs && lg?.clubs[clubs.away]?.short_name) ?? "Away"}</option>
          </select>
        </label>
        <label>
          Metric
          <select
            data-testid="metric"
            value={profile.metric ?? ""}
            onChange={(e) => set({ metric: (e.target.value || null) as ViewerProfile["metric"] })}
          >
            <option value="">None</option>
            {METRICS.map((m) => (
              <option key={m} value={m}>
                {m.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
      </div>
      {profile.mode === "player_cam" && (
        <label className="row">
          Player
          <select data-testid="player" value={profile.player ?? ""} onChange={(e) => set({ player: e.target.value })}>
            {ids.map((id, row) => (
              <option key={id} value={id}>
                {row < 11 ? "H" : "A"} {lg?.players[id]?.shirt ?? ""} {surname(lg, id)}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="toggle">
        <input
          type="checkbox"
          data-testid="high-contrast"
          checked={profile.high_contrast}
          onChange={(e) => set({ high_contrast: e.target.checked })}
        />
        High contrast
      </label>
    </section>
  );
}
