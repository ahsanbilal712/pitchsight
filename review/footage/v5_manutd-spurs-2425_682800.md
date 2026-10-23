# v5 line · manutd-spurs-2425 38:02 · shot_only

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_608281 xG of the shot he took, at the reviewed strike (published PL reference model) = 0.08; f_608283 distance of the strike from goal = 16 m

```json
{
 "slug": "manutd-spurs-2425",
 "clip_ms": 682800,
 "verdict": "shot_only",
 "lower_third": "Werner from 16 m: 0.08 xG, saved",
 "why": "Werner shoots from 16 m, a chance worth 0.08 xG, and it is saved.",
 "claims": [
  {
   "text": "Werner",
   "kind": "player",
   "value": "p_960",
   "unit": null,
   "evidence_ids": [
    "f_608281"
   ]
  },
  {
   "text": "0.08",
   "kind": "number",
   "value": 0.08,
   "unit": "xg",
   "evidence_ids": [
    "f_608281"
   ]
  },
  {
   "text": "16 m",
   "kind": "number",
   "value": 16.4,
   "unit": "metres",
   "evidence_ids": [
    "f_608283"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.005522,
 "prompt_version": "insight_footage@7",
 "cache_key": "m_9004/match/insight@insight_footage@7.xg_682800/gemini-4-argon/s9004",
 "decision_source": "cache/v5/xg_decision_682800.json",
 "hand_reviewed": true,
 "review_note": "track B hand review, lead's v5 rules: every shot at its reviewed strike; a pass only at +0.04 xG and clearly onside"
}
```
