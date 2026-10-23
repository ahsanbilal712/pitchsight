# Arsenal v Chelsea · mo_00001

Re-reviewed 23 Oct: positions from tracking (track A's calib and tracks) moved the numbers.

Model why: Eberechi Eze shoots from 19.4 metres and sees his effort saved, an option that carries just a 2% goal chance. Returning the pass to Bukayo Saka lifts the goal chance to 12% and improves the win probability by +1 points.

Fact Checker on the model output: verified

```json
{
 "slug": "arsenal-chelsea-2526",
 "moment_id": "mo_00001",
 "why": "Eberechi Eze shoots from 21 metres and the shot is saved: a 3% goal chance. Bukayo Saka is still free on the right of the box; returning the pass lifts it to 20% and adds +2 points of win chance.",
 "claims": [
  {
   "text": "Eberechi Eze",
   "kind": "player",
   "value": "p_948",
   "unit": null,
   "evidence_ids": [
    "e_0046",
    "cf_000001"
   ]
  },
  {
   "text": "21 metres",
   "kind": "number",
   "value": 20.8,
   "unit": "metres",
   "evidence_ids": [
    "f_000001"
   ]
  },
  {
   "text": "3%",
   "kind": "number",
   "value": 0.0329,
   "unit": "p_goal",
   "evidence_ids": [
    "cf_000001"
   ]
  },
  {
   "text": "Bukayo Saka",
   "kind": "player",
   "value": "p_952",
   "unit": null,
   "evidence_ids": [
    "e_0045",
    "cf_000001"
   ]
  },
  {
   "text": "20%",
   "kind": "number",
   "value": 0.1955,
   "unit": "p_goal",
   "evidence_ids": [
    "cf_000001"
   ]
  },
  {
   "text": "+2 points",
   "kind": "number",
   "value": 0.0212,
   "unit": "win_prob_delta",
   "evidence_ids": [
    "cf_000001"
   ]
  }
 ],
 "line": {
  "headline": "Eze shoots, Saka was free",
  "body": "Saved from 21 metres: a 3% goal chance. Back to Saka makes it 20% and adds +2 points of win chance."
 }
}
```
