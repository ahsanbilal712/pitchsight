# Liverpool v Manchester City · mo_00001

Re-reviewed 23 Oct: positions from tracking (tracks/62.json through calib/62_refined.json) moved the numbers.

Model why: Szoboszlai takes a shot from 31 metres that gets blocked, carrying a 3% goal chance. Passing to Salah raises the goal chance to 8% and adds +4 points to the win probability.

Fact Checker on the model output: verified

```json
{
 "slug": "liverpool-mancity-2526",
 "moment_id": "mo_00001",
 "why": "Szoboszlai shoots from 32 metres and the shot is blocked: a 3% goal chance. Salah is free on the right, and the pass to him makes it 5% and adds 2 points to the win chance.",
 "claims": [
  {
   "text": "Szoboszlai",
   "kind": "player",
   "value": "p_912",
   "unit": null,
   "evidence_ids": [
    "e_0033",
    "cf_000001",
    "f_000001"
   ]
  },
  {
   "text": "32 metres",
   "kind": "number",
   "value": 31.7,
   "unit": "metres",
   "evidence_ids": [
    "f_000001"
   ]
  },
  {
   "text": "3%",
   "kind": "number",
   "value": 0.0311,
   "unit": "p_goal",
   "evidence_ids": [
    "cf_000001"
   ]
  },
  {
   "text": "Salah",
   "kind": "player",
   "value": "p_911",
   "unit": null,
   "evidence_ids": [
    "cf_000001",
    "f_000002"
   ]
  },
  {
   "text": "5%",
   "kind": "number",
   "value": 0.0533,
   "unit": "p_goal",
   "evidence_ids": [
    "cf_000001"
   ]
  },
  {
   "text": "2 points",
   "kind": "number",
   "value": 0.0198,
   "unit": "win_prob_delta",
   "evidence_ids": [
    "cf_000001"
   ]
  }
 ],
 "line": {
  "headline": "Szoboszlai shoots, Salah was free",
  "body": "Blocked from 32 metres: a 3% goal chance. The pass to Salah makes it 5% and adds 2 points of win chance."
 }
}
```
