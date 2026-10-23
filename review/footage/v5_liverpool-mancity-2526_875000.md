# v5 line · liverpool-mancity-2526 86:23 · close_call

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
Facts: f_607501 shot xG (published PL reference model) from where he shot = 0.02; f_607502 xG after the pass (P(pass completes) x reference xG at the receiver) = 0.03; f_607504 chance the pass completes (pass model) = 56%; f_607505 reference xG of a shot from the receiver's spot = 0.06

```json
{
 "slug": "liverpool-mancity-2526",
 "clip_ms": 875000,
 "verdict": "close_call",
 "lower_third": "Szoboszlai: shot 0.02 xG, pass 0.03 xG, a close call",
 "why": "From where Szoboszlai stands a shot is worth 0.02 xG and the pass to the team-mate at the edge of the box 0.03, a close call; his shot is blocked.",
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
   "value": 0.0199,
   "unit": "xg",
   "evidence_ids": [
    "f_607501"
   ]
  },
  {
   "text": "0.03",
   "kind": "number",
   "value": 0.03,
   "unit": "xg",
   "evidence_ids": [
    "f_607502"
   ]
  }
 ],
 "confidence": 0.95,
 "model": "gemini-4-argon",
 "cost_usd": 0.00595,
 "prompt_version": "insight_footage@6",
 "cache_key": "m_9001/match/insight@insight_footage@6.xg_875000/gemini-4-argon/s9001",
 "decision_source": "cache/v5/xg_decision_875000.json",
 "hand_reviewed": true,
 "review_note": "track B hand review: shot xG 'from where he stands' (freeze) in comparisons; the scored shot's own xG (strike) in finishing lines"
}
```
