"""Real spawn points per TB4 map and what the 60-game one-second study (2026-10-17) says about each under a lock.

SPAWNS[map] = [(label, x, y, z), ...] clustered from demo positions 50 ms after spawning.
CHAINED_LOCKED[map][spawn] = [share of locked spawns that died inside 14 s, n].
ROOM_SURVIVAL[map][spawn][first room entered] = [share surviving to 14 s among players who left the spawn area, n>=25].
LOCK_THR[map] = per-second lock margin (enemy alive stack - own, +100 per RL) at the map's 85th percentile.
Source: docs/research_top_na_fours_2026-10.md finding 7; script spawn_points.py (session scratchpad)."""
SPAWNS = {
 "dm3": [
  [
   "RL",
   1520,
   431,
   -88
  ],
  [
   "YA",
   1472,
   -928,
   -24
  ],
  [
   "tele",
   -631,
   -679,
   -16
  ],
  [
   "mega (SNG low)",
   -880,
   -232,
   -16
  ],
  [
   "lifts",
   513,
   768,
   216
  ],
  [
   "RA tunnel",
   192,
   -208,
   -176
  ]
 ],
 "dm2": [
  [
   "quad/big",
   1712,
   -504,
   24
  ],
  [
   "low RL",
   2576,
   -1328,
   24
  ],
  [
   "big stairs",
   2048,
   -1352,
   136
  ],
  [
   "water",
   2624,
   -487,
   32
  ],
  [
   "RA/MH",
   2704,
   -2048,
   128
  ],
  [
   "tele button",
   2248,
   -16,
   -136
  ],
  [
   "low button",
   2176,
   -2176,
   84
  ],
  [
   "tele/ya",
   2543,
   -31,
   -64
  ],
  [
   "NG",
   2560,
   -192,
   32
  ]
 ],
 "e1m2": [
  [
   "start",
   1496,
   1328,
   200
  ],
  [
   "crossing",
   168,
   -480,
   320
  ],
  [
   "door",
   792,
   -208,
   320
  ],
  [
   "GL",
   936,
   -1216,
   432
  ],
  [
   "quad/GL",
   792,
   -992,
   440
  ],
  [
   "MH low",
   -415,
   -144,
   320
  ],
  [
   "quad healthpaks",
   408,
   -752,
   432
  ],
  [
   "RL",
   784,
   808,
   200
  ],
  [
   "YA",
   1080,
   -720,
   312
  ],
  [
   "spikes",
   1935,
   -135,
   312
  ]
 ],
 "schloss": [
  [
   "tower RL",
   -240,
   -2184,
   440
  ],
  [
   "Cat SSG",
   968,
   -3416,
   408
  ],
  [
   "cemetery tele",
   1168,
   -1984,
   312
  ],
  [
   "RA/cemetery",
   696,
   -3184,
   184
  ],
  [
   "tower entry",
   136,
   -2471,
   440
  ],
  [
   "mid",
   -249,
   -2361,
   312
  ],
  [
   "quad/Cat high",
   424,
   -3240,
   600
  ],
  [
   "quad/Cat low",
   455,
   -3032,
   440
  ]
 ]
}
LOCK_THR = {"dm3": 386, "dm2": 400, "e1m2": 234, "schloss": 375}
CHAINED_LOCKED = {
 "dm3": {
  "tele": [
   0.755,
   277
  ],
  "RA tunnel": [
   0.672,
   287
  ],
  "lifts": [
   0.719,
   310
  ],
  "YA": [
   0.695,
   308
  ],
  "mega (SNG low)": [
   0.751,
   301
  ],
  "RL": [
   0.554,
   294
  ]
 },
 "dm2": {
  "tele/ya": [
   0.724,
   301
  ],
  "quad/big": [
   0.752,
   302
  ],
  "tele button": [
   0.829,
   293
  ],
  "RA/MH": [
   0.636,
   319
  ],
  "low RL": [
   0.779,
   294
  ],
  "big stairs": [
   0.643,
   300
  ],
  "water": [
   0.885,
   287
  ],
  "NG": [
   0.854,
   281
  ],
  "low button": [
   0.738,
   290
  ]
 },
 "e1m2": {
  "door": [
   0.653,
   216
  ],
  "GL": [
   0.863,
   227
  ],
  "quad healthpaks": [
   0.851,
   202
  ],
  "start": [
   0.485,
   196
  ],
  "RL": [
   0.596,
   228
  ],
  "YA": [
   0.784,
   204
  ],
  "spikes": [
   0.714,
   203
  ],
  "quad/GL": [
   0.84,
   225
  ],
  "crossing": [
   0.776,
   237
  ],
  "MH low": [
   0.659,
   226
  ]
 },
 "schloss": {
  "Cat SSG": [
   0.753,
   320
  ],
  "RA/cemetery": [
   0.75,
   296
  ],
  "mid": [
   0.763,
   283
  ],
  "tower RL": [
   0.802,
   333
  ],
  "tower entry": [
   0.737,
   308
  ],
  "quad/Cat high": [
   0.807,
   290
  ],
  "quad/Cat low": [
   0.806,
   294
  ],
  "cemetery tele": [
   0.728,
   302
  ]
 }
}
ROOM_SURVIVAL = {
 "dm3": {
  "tele": {
   "Ring": [
    0.255,
    192
   ],
   "RA.rox": [
    0.241,
    29
   ]
  },
  "RA tunnel": {
   "hill": [
    0.391,
    192
   ],
   "RA.low": [
    0.25,
    44
   ]
  },
  "lifts": {
   "lifts.below": [
    0.26,
    246
   ]
  },
  "mega (SNG low)": {
   "Ring": [
    0.237,
    190
   ],
   "SNG.MH": [
    0.513,
    39
   ]
  },
  "YA": {
   "YA": [
    0.329,
    161
   ],
   "window": [
    0.412,
    85
   ]
  },
  "RL": {
   "water": [
    0.679,
    56
   ],
   "bridge.low": [
    0.661,
    118
   ]
  }
 },
 "dm2": {
  "tele/ya": {
   "tele.YA": [
    0.513,
    156
   ]
  },
  "quad/big": {
   "NG": [
    0.205,
    39
   ],
   "Quad.low": [
    0.135,
    74
   ],
   "big": [
    0.44,
    75
   ],
   "Quad.button": [
    0.3,
    80
   ]
  },
  "tele button": {
   "tele.YA": [
    0.329,
    143
   ]
  },
  "RA/MH": {
   "big.stairs": [
    0.46,
    50
   ],
   "RA.MH/rox": [
    0.667,
    45
   ],
   "low.button": [
    0.588,
    68
   ],
   "low.stairs": [
    0.459,
    37
   ]
  },
  "big stairs": {
   "big": [
    0.377,
    281
   ]
  },
  "NG": {
   "Quad.low": [
    0.162,
    37
   ],
   "tele.entry": [
    0.229,
    96
   ],
   "path": [
    0.25,
    48
   ]
  },
  "low button": {
   "low.RL": [
    0.295,
    258
   ]
  },
  "water": {
   "NG": [
    0.119,
    236
   ]
  },
  "low RL": {
   "low.stairs": [
    0.356,
    87
   ],
   "low.lift": [
    0.328,
    67
   ]
  }
 },
 "e1m2": {
  "door": {
   "bridge": [
    0.5,
    100
   ],
   "cross": [
    0.168,
    95
   ]
  },
  "GL": {
   "Quad": [
    0.131,
    84
   ],
   "GL": [
    0.204,
    98
   ]
  },
  "start": {
   "start.stairs": [
    0.504,
    115
   ],
   "start.water": [
    0.537,
    80
   ]
  },
  "RL": {
   "cross.water": [
    0.367,
    109
   ],
   "water.RL": [
    0.635,
    63
   ]
  },
  "YA": {
   "GL.stairs": [
    0.309,
    68
   ],
   "YA.water": [
    0.512,
    41
   ]
  },
  "spikes": {
   "YA.spikes": [
    0.225,
    120
   ],
   "SSG.spikes": [
    0.408,
    76
   ]
  },
  "quad healthpaks": {
   "Quad.stairs": [
    0.239,
    46
   ],
   "GL.Quad": [
    0.189,
    95
   ]
  },
  "MH low": {
   "MH": [
    0.345,
    29
   ],
   "MH.entry": [
    0.333,
    93
   ],
   "MH.SNG": [
    0.491,
    55
   ]
  },
  "quad/GL": {
   "GL": [
    0.178,
    180
   ]
  },
  "crossing": {
   "Quad.stairs": [
    0.218,
    119
   ],
   "MH.entry": [
    0.377,
    53
   ]
  }
 },
 "schloss": {
  "Cat SSG": {
   "cathedral": [
    0.263,
    278
   ]
  },
  "RA/cemetery": {
   "RA.low": [
    0.289,
    235
   ]
  },
  "mid": {
   "tower.entry": [
    0.346,
    136
   ],
   "Quad.ledge": [
    0.135,
    52
   ],
   "yard.tunnel": [
    0.232,
    56
   ]
  },
  "tower RL": {
   "tower": [
    0.383,
    120
   ],
   "cemetary.tele": [
    0.28,
    50
   ],
   "tower.entry": [
    0.2,
    25
   ]
  },
  "tower entry": {
   "Quad.ledge": [
    0.274,
    117
   ],
   "tower.RL": [
    0.324,
    139
   ]
  },
  "quad/Cat low": {
   "cathedral": [
    0.231,
    199
   ],
   "Quad.ledge": [
    0.177,
    62
   ]
  },
  "cemetery tele": {
   "tower.RL": [
    0.287,
    244
   ],
   "RA.window": [
    0.205,
    39
   ]
  },
  "quad/Cat high": {
   "cathedral.YA": [
    0.231,
    108
   ],
   "Quad": [
    0.149,
    47
   ],
   "Quad.ledge": [
    0.321,
    56
   ]
  }
 }
}


def spawn_label(mp, x, y, z):
    """Nearest listed spawn point within 160 u (xy) / 96 u (z), else 'other'."""
    pts = SPAWNS.get(mp) or []
    if not pts:
        return 'other'
    best = min(pts, key=lambda s: abs(s[1] - x) + abs(s[2] - y) + abs(s[3] - z))
    return best[0] if abs(best[1] - x) <= 160 and abs(best[2] - y) <= 160 and abs(best[3] - z) <= 96 else 'other'


def room_name(loc):
    """A .loc room name as players say it in coaching text (Peter: 'Cat' for cathedral)."""
    return (loc or "").replace("cathedral", "Cat").replace("cemetary", "cemetery")
