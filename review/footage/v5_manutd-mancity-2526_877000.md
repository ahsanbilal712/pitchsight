# v5 line · manutd-mancity-2526 56:41 · alternative_better

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_607701 shot xG (published PL reference model) from where he shot = 0.06; f_607702 xG after the pass (P(pass completes) x reference xG at the receiver) = 0.11; f_607704 chance the pass completes (pass model) = 84%; f_607705 reference xG of a shot from the receiver's spot = 0.13

```json
{
 "slug": "manutd-mancity-2526",
 "clip_ms": 877000,
 "verdict": "alternative_better",
 "lower_third": "Amad: shot 0.06 xG, pass 0.11 xG",
 "why": "From where Amad stands a shot is worth 0.06 xG, the pass to the team-mate in the middle of the box 0.11 (it arrives 84% of the time); the shot is saved.",
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
   "text": "0.06",
   "kind": "number",
   "value": 0.0635,
   "unit": "xg",
   "evidence_ids": [
    "f_607701"
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
 "cost_usd": 0.006726,
 "prompt_version": "insight_footage@6",
 "cache_key": "m_9002/match/insight@insight_footage@6.xg_877000/gemini-4-argon/s9002",
 "decision_source": "cache/v5/xg_decision_877000.json",
 "hand_reviewed": true,
 "review_note": "track B hand review: shot xG 'from where he stands' (freeze) in comparisons; the scored shot's own xG (strike) in finishing lines"
}
```
