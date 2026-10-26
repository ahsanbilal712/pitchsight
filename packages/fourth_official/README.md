# fourth_official

Deterministic offside and foul re-derivation from tracking.

Tests live in `tests/fourth_official/`.

```python
def check_offside(frame: Frame, pass_event: Event) -> OffsideRuling | None     # margin_m, last_defender, line [[x,y1],[x,y2]]
def check_foul(events: list[Event], frames: TrackingWindow) -> FoulRuling | None  # contact point, closing speed, in_box
def ruling_to_cue(r: Ruling, t_ms: int) -> Cue                                  # layer referee_line, kind fourth_official, verified by construction
```

Rules library in `packages/fourth_official/rules.yaml` (offside, penalty area, handball zones, back-pass). Performance: < 5 ms per check. Tests: geometric unit tests with hand-built frames.
