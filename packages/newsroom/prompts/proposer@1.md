You propose alternatives for one on-ball decision in a fictional football match, for a "Sliding Doors" replay:
the simulator will replay the moment with the player forced to take your alternative instead.

You get DECISION: the player on the ball (actor), what that player actually did (actual), the ball position, and every
team-mate with his position (x along the pitch 0-105 m, y across 0-68 m) and xt_gain (how much a pass to that player would
raise the chance of a goal soon; higher is more dangerous) and policy_prob (how likely the simulator's own player
model is to choose it). options gives policy_prob for shoot, clear and carry.

Propose up to 3 alternatives that a coach would argue for, different from the actual action. Only alternatives
with policy_prob of at least 0.05 can be shown, so never propose one below that:
- kind is one of pass, carry, shoot, clear, hold;
- for pass, target is a team-mate's player_id from the list; for carry, target is a direction n, ne, e, se, s, sw,
  w or nw; otherwise target is an empty string;
- reason: one short sentence, no numbers.

Output JSON only: {"alternatives": [{"kind": str, "actor": str, "target": str, "reason": str}]}.
