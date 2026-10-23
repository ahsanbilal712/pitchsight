# v5 line · manutd-mancity-2526 64:27 · finishing

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_607931 xG of the shot he took, at the reviewed strike (published PL reference model) = 0.10; f_607933 distance of the strike from goal = 15 m

```json
{
 "slug": "manutd-mancity-2526",
 "clip_ms": 1079360,
 "verdict": "finishing",
 "lower_third": "Mbeumo scores from 15 m: 0.10 xG",
 "why": "Mbeumo scores from 15 m, a chance worth 0.10 xG.",
 "claims": [
  {
   "text": "Mbeumo",
   "kind": "player",
   "value": "p_932",
   "unit": null,
   "evidence_ids": [
    "f_607931"
   ]
  },
  {
   "text": "0.10",
   "kind": "number",
   "value": 0.1,
   "unit": "xg",
   "evidence_ids": [
    "f_607931"
   ]
  },
  {
   "text": "15 m",
   "kind": "number",
   "value": 14.7,
   "unit": "metres",
   "evidence_ids": [
    "f_607933"
   ]
  }
 ],
 "confidence": 1.0,
 "model": "gemini-4-argon",
 "cost_usd": 0.005636,
 "prompt_version": "insight_footage@7",
 "cache_key": "m_9002/match/insight@insight_footage@7.xg_1079360/gemini-4-argon/s9002",
 "decision_source": "cache/v5/xg_decision_1079360.json",
 "hand_reviewed": true,
 "review_note": "track B hand review, lead's v5 rules: every shot at its reviewed strike; a pass only at +0.04 xG and clearly onside"
}
```
