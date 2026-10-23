# v5 line · arsenal-chelsea-2526 79:10 · close_call

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_600051 shot xG (published PL reference model) from where he shot = 0.05; f_600052 xG after the pass (P(pass completes) x reference xG at the receiver) = 0.06; f_600054 chance the pass completes (pass model) = 58%; f_600055 reference xG of a shot from the receiver's spot = 0.11

```json
{
 "slug": "arsenal-chelsea-2526",
 "clip_ms": 1300500,
 "verdict": "close_call",
 "lower_third": "Eze: shot 0.05 xG, pass 0.06 xG, a close call",
 "why": "From where Eze stands a shot is worth 0.05 xG and the pass to the team-mate in the middle of the box 0.06, a close call; the shot is saved.",
 "claims": [
  {
   "text": "Eze",
   "kind": "player",
   "value": "p_948",
   "unit": null,
   "evidence_ids": [
    "f_600051"
   ]
  },
  {
   "text": "0.05",
   "kind": "number",
   "value": 0.0479,
   "unit": "xg",
   "evidence_ids": [
    "f_600051"
   ]
  },
  {
   "text": "0.06",
   "kind": "number",
   "value": 0.06,
   "unit": "xg",
   "evidence_ids": [
    "f_600052"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.005924,
 "prompt_version": "insight_footage@6",
 "cache_key": "m_9003/match/insight@insight_footage@6.xg_1300500/gemini-4-argon/s9003",
 "decision_source": "cache/v5/xg_decision_1300500.json",
 "hand_reviewed": true,
 "review_note": "track B hand review: shot xG 'from where he stands' (freeze) in comparisons; the scored shot's own xG (strike) in finishing lines"
}
```
