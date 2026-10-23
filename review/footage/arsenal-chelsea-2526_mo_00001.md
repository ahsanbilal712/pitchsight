# Arsenal v Chelsea · mo_00001

Model why: Eze shoots from 20.8 metres out and sees his effort saved by Sánchez, an option that carries just a 3% goal chance. Passing back to Saka instead raises the goal probability to 20% and improves the win chance by +2 points.

Fact Checker on the model output: [{"where": "claims[2]", "text": "S\u00e1nchez", "reject_reason": "player_not_in_evidence"}]

```json
{
 "slug": "arsenal-chelsea-2526",
 "moment_id": "mo_00001",
 "why": "Eze shoots from 21 metres out and sees his effort saved, an option that carries just a 3% goal chance. Passing back to Saka instead raises the goal chance to 20% and improves the win chance by +2 points.",
 "claims": [
  {
   "text": "Eze",
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
   "text": "Saka",
   "kind": "player",
   "value": "p_952",
   "unit": null,
   "evidence_ids": [
    "cf_000001",
    "f_000002"
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
  "body": "Saved from 21 metres: a 3% goal chance. Back to Saka makes it 20%, +2 points of win chance."
 }
}
```
