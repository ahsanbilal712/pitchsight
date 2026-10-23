# v3 caption · ghost_defender · manutd-mancity-2526

Model draft (gemini-4-argon); Fact Checker on it: verified

Hand review: headline leads with the finding (no defender could reach the lane) instead of the engine's goal chance; "7.0" -> "7".

```json
{
 "slug": "manutd-mancity-2526",
 "beat_file": "data/footage/manutd-mancity-2526/cache/v3/ghost_defender_1078360.json",
 "headline": "No City defender could get into Mbeumo's shooting lane",
 "why": "To trim the goal chance in the engine's replay from 5% to 4% on Bryan Mbeumo's shot, the defender needs 10.7 metres, beyond the 7 metres he can cover at top speed in the time available.",
 "claims": [
  {
   "text": "5%",
   "kind": "number",
   "value": 0.0532,
   "unit": "p_goal",
   "evidence_ids": [
    "f_800001"
   ]
  },
  {
   "text": "4%",
   "kind": "number",
   "value": 0.0378,
   "unit": "p_goal",
   "evidence_ids": [
    "f_800002"
   ]
  },
  {
   "text": "Bryan Mbeumo",
   "kind": "player",
   "value": "p_932",
   "unit": null,
   "evidence_ids": [
    "f_800001",
    "f_800002",
    "f_800003"
   ]
  },
  {
   "text": "10.7 metres",
   "kind": "number",
   "value": 10.7,
   "unit": "metres",
   "evidence_ids": [
    "f_800003"
   ]
  },
  {
   "text": "7 metres",
   "kind": "number",
   "value": 7.0,
   "unit": "metres",
   "evidence_ids": [
    "f_800004"
   ]
  }
 ],
 "model": "gemini-4-argon",
 "cost_usd": 0.007644,
 "prompt_version": "insight_footage@2"
}
```
