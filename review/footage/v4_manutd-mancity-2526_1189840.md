# v4 line · manutd-mancity-2526 75:28 · alternative_better

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_608981 goal chance in the next 10 s, actual choice (shoot) = 17.1%; f_608982 goal chance in the next 10 s, alternative (carry the ball on) = 31.6%; f_608983 seconds after the choice that count = 10; f_608984 replays of the frozen frame per option = 2000

```json
{
 "slug": "manutd-mancity-2526",
 "clip_ms": 1189840,
 "verdict": "alternative_better",
 "lower_third": "Dorgu: shot 17%, carry on 32% (goal in 10 s)",
 "why": "Dorgu scores; in the replays, carrying the ball on gives a 32% chance of a goal in the next 10 seconds, higher than 17% for the shot.",
 "claims": [
  {
   "text": "Dorgu",
   "kind": "player",
   "value": "p_935",
   "unit": null,
   "evidence_ids": [
    "f_608981",
    "f_608982"
   ]
  },
  {
   "text": "17%",
   "kind": "number",
   "value": 0.1705,
   "unit": "p_goal",
   "evidence_ids": [
    "f_608981"
   ]
  },
  {
   "text": "32%",
   "kind": "number",
   "value": 0.3155,
   "unit": "p_goal",
   "evidence_ids": [
    "f_608982"
   ]
  },
  {
   "text": "10",
   "kind": "number",
   "value": 10.0,
   "unit": "seconds",
   "evidence_ids": [
    "f_608983"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.006182,
 "prompt_version": "insight_footage@4",
 "cache_key": "m_9002/match/insight@insight_footage@4.goal10_1189840.n2000s4242/gemini-4-argon/s9002",
 "decision_source": "cache/v4/goal10_decision_1189840.json n=2000 seed=4242",
 "hand_reviewed": true,
 "review_note": "track B hand review: one format for all six lines; keepers unnamed; displays as facts; Dorgu's displays follow the overlay (whole percent from 10%)"
}
```
