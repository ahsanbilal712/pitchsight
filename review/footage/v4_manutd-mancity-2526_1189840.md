# v4 line · manutd-mancity-2526 75:28 · finishing

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_608981 goal chance in the next 10 s, actual choice (shoot) = 17%; f_608983 seconds after the choice that count = 10; f_608984 replays of the frozen frame per option = 2,000; f_608985 95% interval low, actual choice = 15%; f_608986 95% interval high, actual choice = 19%; f_608989 random seed of the replays = 4242

```json
{
 "slug": "manutd-mancity-2526",
 "clip_ms": 1189840,
 "verdict": "finishing",
 "lower_third": "Dorgu scores from a 17% chance (goal in 10 s)",
 "why": "From here the replays give a 17% chance of a goal in the next 10 seconds, and Dorgu scores.",
 "claims": [
  {
   "text": "Dorgu",
   "kind": "player",
   "value": "p_935",
   "unit": null,
   "evidence_ids": [
    "f_608981"
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
 "cost_usd": 0.005772,
 "prompt_version": "insight_footage@5",
 "cache_key": "m_9002/match/insight@insight_footage@5.goal10_1189840.n2000s4242/gemini-4-argon/s9002",
 "decision_source": "cache/v4/goal10_decision_1189840.json n=2000 seed=4242",
 "hand_reviewed": true,
 "review_note": "track B hand review: finishing line (lead: a goal never implies a better option)"
}
```
