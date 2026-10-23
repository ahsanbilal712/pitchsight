# v4 line · manutd-mancity-2526 56:41 · alternative_better

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_607701 goal chance in the next 10 s, actual choice (shoot) = 2.5%; f_607702 goal chance in the next 10 s, alternative (pass to the team-mate in the box, central) = 4.5%; f_607703 seconds after the choice that count = 10; f_607704 replays of the frozen frame per option = 2000

```json
{
 "slug": "manutd-mancity-2526",
 "clip_ms": 877000,
 "verdict": "alternative_better",
 "lower_third": "Amad: shot 2.5%, pass 4.5% (goal in 10 s)",
 "why": "Amad's shot is saved; a pass to the team-mate in the middle of the box gives a 4.5% chance of a goal in the next 10 seconds, against 2.5%.",
 "claims": [
  {
   "text": "Amad",
   "kind": "player",
   "value": "p_928",
   "unit": null,
   "evidence_ids": [
    "f_607701",
    "f_607702"
   ]
  },
  {
   "text": "2.5%",
   "kind": "number",
   "value": 0.0245,
   "unit": "p_goal",
   "evidence_ids": [
    "f_607701"
   ]
  },
  {
   "text": "4.5%",
   "kind": "number",
   "value": 0.045,
   "unit": "p_goal",
   "evidence_ids": [
    "f_607702"
   ]
  },
  {
   "text": "10",
   "kind": "number",
   "value": 10.0,
   "unit": "seconds",
   "evidence_ids": [
    "f_607703"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.006266,
 "prompt_version": "insight_footage@4",
 "cache_key": "m_9002/match/insight@insight_footage@4.goal10_877000.n2000s4242/gemini-4-argon/s9002",
 "decision_source": "cache/v4/goal10_decision_877000.json n=2000 seed=4242",
 "hand_reviewed": true,
 "review_note": "track B hand review: one format for all six lines; keepers unnamed; displays as facts"
}
```
