# Arsenal v Chelsea · mo_00001

Model why: Eberechi Eze shoots from 19.4 metres and sees his effort saved, an option that carries just a 2% goal chance. Returning the pass to Bukayo Saka lifts the goal chance to 12% and improves the win probability by +1 points.

Fact Checker on the model output: verified

```json
{
 "slug": "arsenal-chelsea-2526",
 "moment_id": "mo_00001",
 "why": "Eberechi Eze shoots from 19 metres and the shot is saved: a 2% goal chance. Bukayo Saka is still free on the right of the box; returning the pass lifts it to 12% and adds +1 point of win chance.",
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
   "text": "19 metres",
   "kind": "number",
   "value": 19.4,
   "unit": "metres",
   "evidence_ids": [
    "f_000001"
   ]
  },
  {
   "text": "2%",
   "kind": "number",
   "value": 0.0221,
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
   "text": "12%",
   "kind": "number",
   "value": 0.1219,
   "unit": "p_goal",
   "evidence_ids": [
    "cf_000001"
   ]
  },
  {
   "text": "+1 point",
   "kind": "number",
   "value": 0.013,
   "unit": "win_prob_delta",
   "evidence_ids": [
    "cf_000001"
   ]
  }
 ],
 "line": {
  "headline": "Eze shoots, Saka was free",
  "body": "Saved from 19 metres: a 2% goal chance. Back to Saka makes it 12% and adds +1 point of win chance."
 }
}
```
