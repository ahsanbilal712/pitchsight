# Manchester United v Manchester City · mo_00001

Model why: Amad shoots from 18 metres out and Donnarumma saves the effort. Taking the shot gives a 3% goal chance, whereas passing to the number 19 at 12.5 metres lowers the goal chance to 2%.

Fact Checker on the model output: [{"where": "why", "token": "19", "reject_reason": "unbound_number"}]

```json
{
 "slug": "manutd-mancity-2526",
 "moment_id": "mo_00001",
 "why": "Amad shoots from 18 metres out and Donnarumma saves the effort. Taking the shot gives a 3% goal chance, whereas passing to the unmarked team-mate in the middle of the box lowers it to 2%.",
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
   "text": "Donnarumma",
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
  },
  {
   "text": "2%",
   "kind": "number",
   "value": 0.0173,
   "unit": "p_goal",
   "evidence_ids": [
    "cf_000001"
   ]
  }
 ],
 "line": {
  "headline": "Amad's shot was the right call",
  "body": "Donnarumma saves from 18 metres: a 3% goal chance. The pass into the middle of the box: 2%."
 }
}
```
