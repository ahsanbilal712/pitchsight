# Manchester United v Manchester City · mo_00001

Re-reviewed 23 Oct: positions from tracking (track A's calib and tracks) moved the numbers.

Model why: Amad shoots from 18 metres out, seeing his effort saved by Gianluigi Donnarumma. Taking the shot carries a 2% goal chance, whereas passing to the number 19 at 11.9 metres drops that chance to 2%.

Fact Checker on the model output: [{"where": "why", "token": "19", "reject_reason": "unbound_number"}]

```json
{
 "slug": "manutd-mancity-2526",
 "moment_id": "mo_00001",
 "why": "Amad shoots from 18 metres and Gianluigi Donnarumma saves: a 3% goal chance. The pass to the unmarked team-mate in the middle of the box is no better, so the shot is the right call.",
 "claims": [
  {
   "text": "Amad",
   "kind": "player",
   "value": "p_928",
   "unit": null,
   "evidence_ids": [
    "e_0036",
    "cf_000001"
   ]
  },
  {
   "text": "18 metres",
   "kind": "number",
   "value": 18.0,
   "unit": "metres",
   "evidence_ids": [
    "f_000001"
   ]
  },
  {
   "text": "Gianluigi Donnarumma",
   "kind": "player",
   "value": "p_926",
   "unit": null,
   "evidence_ids": [
    "e_0037"
   ]
  },
  {
   "text": "3%",
   "kind": "number",
   "value": 0.0278,
   "unit": "p_goal",
   "evidence_ids": [
    "cf_000001"
   ]
  }
 ],
 "line": {
  "headline": "Amad's shot was the right call",
  "body": "Donnarumma saves from 18 metres: a 3% goal chance. The pass into the middle of the box was no better."
 }
}
```
