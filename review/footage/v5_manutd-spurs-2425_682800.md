# v5 line · manutd-spurs-2425 38:02 · shot_only

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_608281 xG of the shot he took, at the strike (reviewed frame) (published PL reference model) = 0.08

```json
{
 "slug": "manutd-spurs-2425",
 "clip_ms": 682800,
 "verdict": "shot_only",
 "lower_third": "Werner's shot: 0.08 xG, saved",
 "why": "Werner's shot is worth 0.08 xG, and it is saved.",
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
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.004466,
 "prompt_version": "insight_footage@6",
 "cache_key": "m_9004/match/insight@insight_footage@6.xg_682800/gemini-4-argon/s9004",
 "decision_source": "cache/v5/xg_decision_682800.json",
 "hand_reviewed": true,
 "review_note": "track B hand review: the reviewed strike's xG (0.08); no other option was in view"
}
```
