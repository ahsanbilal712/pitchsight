# v5 line · manutd-mancity-2526 56:41 · alternative_better

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_607701 xG of the shot he took, at the reviewed strike (published PL reference model) = 0.07; f_607703 distance of the strike from goal = 18 m; f_607702 xG after the pass (P(pass completes) x reference xG at the receiver) = 0.11; f_607704 chance the pass completes (pass model) = 84%; f_607705 reference xG of a shot from the receiver's spot = 0.13

```json
{
 "slug": "manutd-mancity-2526",
 "clip_ms": 877000,
 "verdict": "alternative_better",
 "lower_third": "Amad: shot 0.07 xG, pass 0.11 xG",
 "why": "Amad's shot from 18 m is worth 0.07 xG and is saved; the pass to the team-mate in the middle of the box is worth 0.11 (it arrives 84% of the time).",
 "claims": [
  {
   "text": "Amad",
   "kind": "player",
   "value": "p_928",
   "unit": null,
   "evidence_ids": [
    "f_607701"
   ]
  },
  {
   "text": "0.07",
   "kind": "number",
   "value": 0.07,
   "unit": "xg",
   "evidence_ids": [
    "f_607701"
   ]
  },
  {
   "text": "18 m",
   "kind": "number",
   "value": 17.6,
   "unit": "metres",
   "evidence_ids": [
    "f_607703"
   ]
  },
  {
   "text": "0.11",
   "kind": "number",
   "value": 0.11,
   "unit": "xg",
   "evidence_ids": [
    "f_607702"
   ]
  },
  {
   "text": "84%",
   "kind": "number",
   "value": 0.84,
   "unit": "percent",
   "evidence_ids": [
    "f_607704"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.0064,
 "prompt_version": "insight_footage@7",
 "cache_key": "m_9002/match/insight@insight_footage@7.xg_877000/gemini-4-argon/s9002",
 "decision_source": "cache/v5/xg_decision_877000.json",
 "hand_reviewed": true,
 "review_note": "track B hand review, lead's v5 rules: every shot at its reviewed strike; a pass only at +0.04 xG and clearly onside"
}
```
