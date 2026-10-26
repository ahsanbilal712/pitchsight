// Overlay root: a fixed 1920x1080 transparent stage. Component tree:
// Pitch2D -> ScoreBug -> ChaosMeter -> SwingBar -> LowerThird -> PlayerTags -> Ticker.
import ChaosMeter from "./components/ChaosMeter";
import LowerThird from "./components/LowerThird";
import PlayerTags from "./components/PlayerTags";
import ScoreBug from "./components/ScoreBug";
import SwingBar from "./components/SwingBar";
import Ticker from "./components/Ticker";
import Pitch2D from "./pitch/Pitch2D";
import { useStream } from "./stream/StreamProvider";

export default function App() {
  const { state } = useStream();
  return (
    <div className="stage" data-mode={state.profile?.mode ?? "analyst"}>
      <Pitch2D />
      <PlayerTags />
      <div className="safe-area">
        <ScoreBug />
        <ChaosMeter />
        <SwingBar />
        <LowerThird />
        <Ticker />
      </div>
    </div>
  );
}
