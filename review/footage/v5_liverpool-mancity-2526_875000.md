# v5 line · liverpool-mancity-2526 86:23 · shot_only

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_607501 xG of the shot he took, at the reviewed strike (published PL reference model) = 0.02; f_607503 distance of the strike from goal = 29 m

```json
{
 "slug": "liverpool-mancity-2526",
 "clip_ms": 875000,
 "verdict": "shot_only",
 "lower_third": "Szoboszlai from 29 m: 0.02 xG, blocked",
 "why": "Szoboszlai shoots from 29 m, a chance worth 0.02 xG, and it is blocked.",
 "claims": [
  {
   "text": "Szoboszlai",
   "kind": "player",
   "value": "p_912",
   "unit": null,
   "evidence_ids": [
    "f_607501"
   ]
  },
  {
   "text": "0.02",
   "kind": "number",
   "value": 0.02,
   "unit": "xg",
   "evidence_ids": [
    "f_607501"
   ]
  },
  {
   "text": "29 m",
   "kind": "number",
   "value": 28.8,
   "unit": "metres",
   "evidence_ids": [
    "f_607503"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.0052,
 "prompt_version": "insight_footage@7",
 "cache_key": "m_9001/match/insight@insight_footage@7.xg_875000/gemini-4-argon/s9001",
 "decision_source": "cache/v5/xg_decision_875000.json",
 "hand_reviewed": true,
 "review_note": "track B hand review, lead's v5 rules: every shot at its reviewed strike; a pass only at +0.04 xG and clearly onside"
}
```
