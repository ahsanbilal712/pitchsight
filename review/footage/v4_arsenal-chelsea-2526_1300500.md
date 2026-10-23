# v4 line · arsenal-chelsea-2526 79:10 · alternative_better

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_600051 goal chance in the next 10 s, actual choice (shoot) = 2.6%; f_600052 goal chance in the next 10 s, alternative (pass to the team-mate in the box, central) = 5.7%; f_600053 seconds after the choice that count = 10; f_600054 replays of the frozen frame per option = 2000

```json
{
 "slug": "arsenal-chelsea-2526",
 "clip_ms": 1300500,
 "verdict": "alternative_better",
 "lower_third": "Eze: shot 2.6%, pass 5.7% (goal in 10 s)",
 "why": "Eze's shot is saved; a pass to the team-mate in the middle of the box gives a 5.7% chance of a goal in the next 10 seconds, against 2.6%.",
 "claims": [
  {
   "text": "Eze",
   "kind": "player",
   "value": "p_948",
   "unit": null,
   "evidence_ids": [
    "f_600051",
    "f_600052"
   ]
  },
  {
   "text": "2.6%",
   "kind": "number",
   "value": 0.026,
   "unit": "p_goal",
   "evidence_ids": [
    "f_600051"
   ]
  },
  {
   "text": "5.7%",
   "kind": "number",
   "value": 0.057,
   "unit": "p_goal",
   "evidence_ids": [
    "f_600052"
   ]
  },
  {
   "text": "10",
   "kind": "number",
   "value": 10.0,
   "unit": "seconds",
   "evidence_ids": [
    "f_600053"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.006304,
 "prompt_version": "insight_footage@4",
 "cache_key": "m_9003/match/insight@insight_footage@4.goal10_1300500.n2000s4242/gemini-4-argon/s9003",
 "decision_source": "cache/v4/goal10_decision_1300500.json n=2000 seed=4242",
 "hand_reviewed": true,
 "review_note": "track B hand review: one format for all six lines; keepers unnamed; displays as facts"
}
```
