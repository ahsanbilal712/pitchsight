# v7 caption · dangerous space in view

Model draft (gemini-4-argon). Fact Checker: verified. Gates: pass.
- f_700001 zone: cells from which a shot is worth at least this xG = 0.05
- f_700003 Manchester United (attacking) share of the dangerous space in view at 56:41 = 28%

```json
{
 "caption": "Dangerous space in view: spots in front of goal worth 0.05 xG or more, weighted by xG; the share the attacking team would reach first.",
 "claims": [
  {
   "text": "0.05",
   "kind": "number",
   "value_number": 0.05,
   "unit": "xg",
   "evidence_ids": [
    "f_700001"
   ]
  }
 ],
 "model": "gemini-4-argon",
 "cost_usd": 0.004188,
 "latency_ms": 7933,
 "prompt_version": "insight_footage@9",
 "version": "insight_footage@9.danger.76540932",
 "hand_reviewed": true,
 "draft": "This shows Man Utd's 28% share of the zone in view where a shot is worth at least 0.05 xG, weighted by xG and who reaches each spot first.",
 "review_note": "track B hand review: definitional (the overlay prints the live share, so no single frame's 28% in the caption); 'in view' and 'the attacking team' as in track A's final definition (ee20aa4)"
}
```
