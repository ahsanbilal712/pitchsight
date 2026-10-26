// Fan app: phone-shaped. ProfilePicker -> MiniPitch -> CueFeed -> PlayerCamCard -> MomentCards. The profile is validated, stored client-side and drives the server-side filtered stream.
import { useEffect, useState } from "react";
import CueFeed from "./components/CueFeed";
import MiniPitch from "./components/MiniPitch";
import MomentCards from "./components/MomentCards";
import PlayerCamCard from "./components/PlayerCamCard";
import ProfilePicker from "./components/ProfilePicker";
import { useLeague } from "./league";
import { loadProfile, saveProfile, validateProfile, type ViewerProfile } from "./profile";
import { StreamProvider, useStream } from "./stream/StreamProvider";

function clockText(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function Scoreline() {
  const state = useStream();
  const lg = useLeague();
  const clubs = state.hello?.clubs ?? lg?.golden;
  const name = (id?: string) => (id && lg?.clubs[id]?.short_name) || "–";
  return (
    <div className="scoreline" data-testid="fan-score">
      <span>{name(clubs?.home)}</span>
      <b>
        {state.score[0]}–{state.score[1]}
      </b>
      <span>{name(clubs?.away)}</span>
      <span className="clock">{clockText(state.clock)}</span>
    </div>
  );
}

export default function App() {
  const [profile, setProfile] = useState<ViewerProfile>(loadProfile);
  const [stored, setStored] = useState(true);

  useEffect(() => {
    setStored(saveProfile(profile));
    document.documentElement.dataset.contrast = profile.high_contrast ? "high" : "normal";
  }, [profile]);

  const change = (p: ViewerProfile) => {
    if (validateProfile(p).length === 0) setProfile(p);
  };

  return (
    <StreamProvider profile={profile}>
      <div className="phone" data-mode={profile.mode} data-stored={stored}>
        <header className="top">
          <div className="brand">
            PITCHSIGHT <span>fan</span>
          </div>
          <Scoreline />
        </header>
        <ProfilePicker profile={profile} onChange={change} />
        <MiniPitch highlight={profile.mode === "player_cam" ? profile.player : null} />
        {profile.mode === "player_cam" && profile.player && <PlayerCamCard player={profile.player} />}
        <MomentCards />
        <CueFeed profile={profile} />
      </div>
    </StreamProvider>
  );
}
