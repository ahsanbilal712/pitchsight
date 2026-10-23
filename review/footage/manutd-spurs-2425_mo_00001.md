# Manchester United v Tottenham Hotspur · mo_00001

Re-reviewed 23 Oct: positions from tracking (track A's calib and tracks) moved the numbers.

Model why: From 21.1 metres out, Werner takes the shot that Onana saves, and the simulation shows shooting is the better option here. The strike carries a 3% goal chance, whereas carrying the ball instead drops that chance to 1%.

Fact Checker on the model output: verified

```json
{
 "slug": "manutd-spurs-2425",
 "moment_id": "mo_00001",
 "why": "Werner is through and shoots from 22 metres; Onana saves. The shot is a 3% goal chance, and taking the ball round the keeper instead drops it to 2%, so shooting is the better choice.",
 "claims": [
  {
   "text": "22 metres",
   "kind": "number",
   "value": 21.6,
   "unit": "metres",
   "evidence_ids": [
    "f_000001"
   ]
  },
  {
   "text": "Werner",
   "kind": "player",
   "value": "p_960",
   "unit": null,
   "evidence_ids": [
    "e_0030",
    "cf_000001"
   ]
  },
  {
   "text": "Onana",
   "kind": "player",
   "value": "p_962",
   "unit": null,
   "evidence_ids": [
    "e_0031"
   ]
  },
  {
   "text": "3%",
   "kind": "number",
   "value": 0.0266,
   "unit": "p_goal",
   "evidence_ids": [
    "cf_000001"
   ]
  },
  {
   "text": "2%",
   "kind": "number",
   "value": 0.0174,
   "unit": "p_goal",
   "evidence_ids": [
    "cf_000001"
   ]
  }
 ],
 "line": {
  "headline": "Werner was right to shoot",
  "body": "Onana saves from 22 metres: a 3% goal chance. Taking it round the keeper: 2%."
 }
}
```
