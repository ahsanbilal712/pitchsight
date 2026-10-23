# v4 line · manutd-spurs-2425 38:02 · close_call

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_608281 goal chance in the next 10 s, actual choice (shoot) = 1.4%; f_608282 goal chance in the next 10 s, alternative (carry the ball on) = 0.6%; f_608283 seconds after the choice that count = 10; f_608284 replays of the frozen frame per option = 2000

```json
{
 "slug": "manutd-spurs-2425",
 "clip_ms": 682800,
 "verdict": "close_call",
 "lower_third": "Werner: shot 1.4%, carry on 0.6%, a close call",
 "why": "Werner's shot is saved; shooting gives a 1.4% chance of a goal in the next 10 seconds and carrying on 0.6%, a close call.",
 "claims": [
  {
   "text": "Werner",
   "kind": "player",
   "value": "p_960",
   "unit": null,
   "evidence_ids": [
    "f_608281",
    "f_608282"
   ]
  },
  {
   "text": "1.4%",
   "kind": "number",
   "value": 0.014,
   "unit": "p_goal",
   "evidence_ids": [
    "f_608281"
   ]
  },
  {
   "text": "0.6%",
   "kind": "number",
   "value": 0.006,
   "unit": "p_goal",
   "evidence_ids": [
    "f_608282"
   ]
  },
  {
   "text": "10",
   "kind": "number",
   "value": 10.0,
   "unit": "seconds",
   "evidence_ids": [
    "f_608283"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.006176,
 "prompt_version": "insight_footage@4",
 "cache_key": "m_9004/match/insight@insight_footage@4.goal10_682800.n2000s4242/gemini-4-argon/s9004",
 "decision_source": "cache/v4/goal10_decision_682800.json n=2000 seed=4242",
 "hand_reviewed": true,
 "review_note": "track B hand review: one format for all six lines; keepers unnamed; displays as facts"
}
```
