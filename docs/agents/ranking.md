# Agent: Ranking

`wedding_v3/ranking.py` weight profiles:

| Profile | Focus |
|---------|-------|
| A_emotion | emotion 25% |
| B_story_music | story+music 25% each |
| C_peak_payoff | peak 20% + emotion |
| D_balanced | even mix |

Penalties: consecutive same video, exact shot reuse.
Boost: smile on music peak.
