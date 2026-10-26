"""Offside geometry (Law 11) from the frame in which the ball is played.

The line is the second-last opponent (the keeper counts) or the ball, whichever is nearer the goal, and never in the
attacker's own half. Level is onside. Margin = how far the receiver is beyond that line (positive = offside).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from physics.window import Frame

from .rules import PITCH_L, PITCH_W, attack_dir, rules


@dataclass
class OffsideRuling:
    offside: bool
    margin_m: float                    # receiver beyond the line (+) or behind it (-)
    offside_player: str
    last_defender: str                 # the second-last opponent who sets the line
    line: list[list[float]]            # [[x, 0], [x, 68]] absolute metres
    pass_event_id: str
    t_ms: int
    team: str                          # attacking team
    reason: str                        # offside | onside | level | own_half | behind_ball | restart

    @property
    def kind(self) -> str:
        return "offside"


def check_offside(frame: Frame, pass_event: dict, restart_kind: str | None = None) -> OffsideRuling | None:
    """Ruling for the receiver of `pass_event` judged on `frame` (the tick before the kick). None when the event is not
    a pass or its receiver is not on the pitch; otherwise a ruling whose `offside` flag is the decision."""
    if pass_event.get("type") != "pass":
        return None
    receiver = pass_event.get("attrs", {}).get("recipient")
    row = frame.row_of(receiver) if receiver else -1
    if row < 0:
        return None
    team = 0 if row < 11 else 1
    d = attack_dir(team, frame.period)
    S = np.asarray(frame.S, dtype=np.float64)
    u = S[:23, 0] if d > 0 else PITCH_L - S[:23, 0]
    opp = np.arange(11, 22) if team == 0 else np.arange(0, 11)
    order = opp[np.argsort(u[opp], kind="stable")]
    second_last = int(order[-2])
    passer_row = frame.row_of(pass_event.get("player", "")) if pass_event.get("player") else -1
    ball_u = u[passer_row] if passer_row >= 0 else u[22]
    line_u = max(float(u[second_last]), float(ball_u), PITCH_L / 2)
    margin = float(u[row]) - line_u
    rule = rules()["offside"]
    if restart_kind in rule["restart_exempt"]:
        reason = "restart"
    elif u[row] <= PITCH_L / 2:
        reason = "own_half"
    elif u[row] <= ball_u:
        reason = "behind_ball"
    elif abs(margin) < 1e-9 and rule["level_is_onside"]:
        reason = "level"
    else:
        reason = "offside" if margin > 0 else "onside"
    x = line_u if d > 0 else PITCH_L - line_u
    ids = [str(p) for p in frame.player_ids] if frame.player_ids is not None else []
    defender = ids[second_last] if second_last < len(ids) else f"row_{second_last}"
    if frame.subs is not None:
        for st, sr, on in zip(*frame.subs, strict=True):
            if int(st) <= frame.t_ms and int(sr) == second_last:
                defender = str(on)
    return OffsideRuling(offside=reason == "offside", margin_m=round(margin, 2), offside_player=receiver,
                         last_defender=defender, line=[[round(x, 2), 0.0], [round(x, 2), PITCH_W]],
                         pass_event_id=pass_event.get("id", ""), t_ms=int(pass_event["t_ms"]),
                         team=pass_event.get("team", "home" if team == 0 else "away"), reason=reason)
