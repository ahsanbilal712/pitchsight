# v3 caption · fourth_official · manutd-spurs-2425

Model draft (gemini-4-argon); Fact Checker on it: verified

Hand review: "15.3 km/h" -> "about 15 km/h" (other 0.5 s windows give 15-25 km/h; positions 0.5-1 m).

```json
{
 "slug": "manutd-spurs-2425",
 "beat_file": "data/footage/manutd-spurs-2425/cache/v3/fourth_official_772400.json",
 "headline": "Bruno Fernandes red card: closing in at about 15 km/h",
 "why": "Bruno Fernandes receives a red card for a foul on James Maddison. Tracking estimates his closing speed toward the fouled player at about 15 km/h; this is an assessment, not a ruling.",
 "claims": [
  {
   "text": "Bruno Fernandes",
   "kind": "player",
   "value": "p_966",
   "unit": null,
   "evidence_ids": [
    "f_800001"
   ]
  },
  {
   "text": "James Maddison",
   "kind": "player",
   "value": "p_965",
   "unit": null,
   "evidence_ids": [
    "f_800001"
   ]
  },
  {
   "text": "15 km/h",
   "kind": "number",
   "value": 15.3,
   "unit": "kmh",
   "evidence_ids": [
    "f_800001"
   ]
  }
 ],
 "model": "gemini-4-argon",
 "cost_usd": 0.004926,
 "prompt_version": "insight_footage@2"
}
```
