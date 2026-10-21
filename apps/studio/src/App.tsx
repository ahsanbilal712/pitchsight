// Studio console (TECH_PLAN 1.9): App -> StreamProvider -> Header -> MomentQueue -> AgentTrace -> CueList
// (Why? drawer) -> ProducerPanel and DemoControls (T-035) -> Blackboard.
import { useState } from "react";
import AgentTrace from "./components/AgentTrace";
import Blackboard from "./components/Blackboard";
import CueList from "./components/CueList";
import Header from "./components/Header";
import MomentQueue from "./components/MomentQueue";
import WhyDrawer from "./components/WhyDrawer";

export default function App() {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div className="studio">
      <Header />
      <main className="grid">
        <MomentQueue />
        <div className="center">
          <AgentTrace />
          <CueList selected={selected} onSelect={setSelected} />
        </div>
        <div className="side">
          <Blackboard />
        </div>
      </main>
      {selected && <WhyDrawer cueId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
