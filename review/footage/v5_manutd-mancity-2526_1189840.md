# v5 line · manutd-mancity-2526 75:28 · finishing

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_608981 xG of the shot he took, at the reviewed strike (published PL reference model) = 0.48; f_608983 distance of the strike from goal = 4.5 m

```json
{
 "slug": "manutd-mancity-2526",
 "clip_ms": 1189840,
 "verdict": "finishing",
 "lower_third": "Dorgu scores from 4.5 m: 0.48 xG",
 "why": "Dorgu scores from 4.5 m, a chance worth 0.48 xG.",
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
   "text": "0.48",
   "kind": "number",
   "value": 0.48,
   "unit": "xg",
   "evidence_ids": [
    "f_608981"
   ]
  },
  {
   "text": "4.5 m",
   "kind": "number",
   "value": 4.5,
   "unit": "metres",
   "evidence_ids": [
    "f_608983"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.005264,
 "prompt_version": "insight_footage@7",
 "cache_key": "m_9002/match/insight@insight_footage@7.xg_1189840/gemini-4-argon/s9002",
 "decision_source": "cache/v5/xg_decision_1189840.json",
 "hand_reviewed": true,
 "review_note": "track B hand review, lead's v5 rules: every shot at its reviewed strike; a pass only at +0.04 xG and clearly onside"
}
```
