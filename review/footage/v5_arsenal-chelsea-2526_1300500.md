# v5 line · arsenal-chelsea-2526 79:10 · shot_only

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_600051 xG of the shot he took, at the reviewed strike (published PL reference model) = 0.08; f_600053 distance of the strike from goal = 16 m

```json
{
 "slug": "arsenal-chelsea-2526",
 "clip_ms": 1300500,
 "verdict": "shot_only",
 "lower_third": "Eze from 16 m: 0.08 xG, saved",
 "why": "Eze shoots from 16 m, a chance worth 0.08 xG, and it is saved.",
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
   "text": "0.08",
   "kind": "number",
   "value": 0.08,
   "unit": "xg",
   "evidence_ids": [
    "f_600051"
   ]
  },
  {
   "text": "16 m",
   "kind": "number",
   "value": 16.4,
   "unit": "metres",
   "evidence_ids": [
    "f_600053"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.005128,
 "prompt_version": "insight_footage@7",
 "cache_key": "m_9003/match/insight@insight_footage@7.xg_1300500/gemini-4-argon/s9003",
 "decision_source": "cache/v5/xg_decision_1300500.json",
 "hand_reviewed": true,
 "review_note": "track B hand review, lead's v5 rules: every shot at its reviewed strike; a pass only at +0.04 xG and clearly onside"
}
```
