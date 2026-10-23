# v4 line · manutd-mancity-2526 64:27 · close_call

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_607931 goal chance in the next 10 s, actual choice (shoot) = 3.8%; f_607932 goal chance in the next 10 s, alternative (carry the ball on) = 4.5%; f_607933 seconds after the choice that count = 10; f_607934 replays of the frozen frame per option = 2000

```json
{
 "slug": "manutd-mancity-2526",
 "clip_ms": 1079360,
 "verdict": "close_call",
 "lower_third": "Mbeumo: shot 3.8%, carry on 4.5%, a close call",
 "why": "Mbeumo scores; shooting gives a 3.8% chance of a goal in the next 10 seconds and carrying on 4.5%, a close call.",
 "claims": [
  {
   "text": "Mbeumo",
   "kind": "player",
   "value": "p_932",
   "unit": null,
   "evidence_ids": [
    "f_607931",
    "f_607932"
   ]
  },
  {
   "text": "3.8%",
   "kind": "number",
   "value": 0.0375,
   "unit": "p_goal",
   "evidence_ids": [
    "f_607931"
   ]
  },
  {
   "text": "4.5%",
   "kind": "number",
   "value": 0.0445,
   "unit": "p_goal",
   "evidence_ids": [
    "f_607932"
   ]
  },
  {
   "text": "10",
   "kind": "number",
   "value": 10.0,
   "unit": "seconds",
   "evidence_ids": [
    "f_607933"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.006204,
 "prompt_version": "insight_footage@4",
 "cache_key": "m_9002/match/insight@insight_footage@4.goal10_1079360.n2000s4242/gemini-4-argon/s9002",
 "decision_source": "cache/v4/goal10_decision_1079360.json n=2000 seed=4242",
 "hand_reviewed": true,
 "review_note": "track B hand review: one format for all six lines; keepers unnamed; displays as facts"
}
```
