# Fourth Official · Man Utd v Spurs 40:57 · Bruno Fernandes on James Maddison

Hand-written in review (no model draft: gcloud ADC expired). An assessment from tracking, never a ruling: the
referee's decision (straight red, 41:04) is reported as what happened, not judged. Closing speed is the 0.5 s window
ending at contact (frame 23172, tracks/90.json); other windows give 3.5-7 m/s, all above the 3 m/s "at speed" line,
so the text says "about". Placeholders: `<foul>` is the tagged foul event, `<fact>` the closing-speed fact; player
values are roster label keys.

```json
{
 "headline": "Fourth Official: Fernandes on Maddison",
 "body": "Assessment, not a ruling: contact in midfield, outside the penalty area. Fernandes closes in at about 15 km/h. The referee shows a red card.",
 "why": "An assessment from tracking, not a ruling: Fernandes closes on Maddison at about 15 km/h and the contact is in midfield, outside the penalty area.",
 "claims": [
  {"text": "Fernandes", "kind": "player", "value": "home:#8", "unit": null, "evidence_ids": ["<foul>"]},
  {"text": "Maddison", "kind": "player", "value": "away:#10", "unit": null, "evidence_ids": ["<foul>"]},
  {"text": "15 km/h", "kind": "number", "value": 15.3, "unit": "kmh", "evidence_ids": ["<fact>"]}
 ]
}
```
