"""Real spawn points per TB4 map (clustered from demo positions, 2026-10-17) and the nearest-spawn labeller."""
SP = {
 'dm3': [('RL', 1520, 431, -88), ('YA', 1472, -928, -24), ('tele', -631, -679, -16), ('mega (SNG low)', -880, -232, -16), ('lifts', 513, 768, 216), ('RA tunnel', 192, -208, -176)],
 'dm2': [('quad button', 1712, -504, 24), ('low RL', 2576, -1328, 24), ('big stairs', 2048, -1352, 136), ('water', 2624, -487, 32), ('RA/MH', 2704, -2048, 128), ('tele low', 2248, -16, -136), ('low button', 2176, -2176, 84), ('tele YA side', 2543, -31, -64), ('NG', 2560, -192, 32)],
 'e1m2': [('start', 1496, 1328, 200), ('cross', 168, -480, 320), ('door', 792, -208, 320), ('GL-quad a', 936, -1216, 432), ('GL-quad b', 792, -992, 440), ('MH low', -415, -144, 320), ('quad', 408, -752, 432), ('RL', 784, 808, 200), ('YA', 1080, -720, 312), ('spikes', 1935, -135, 312)],
 'schloss': [('tower RL', -240, -2184, 440), ('cathedral SSG', 968, -3416, 408), ('cemetery tele', 1168, -1984, 312), ('cemetery low', 696, -3184, 184), ('tower entry', 136, -2471, 440), ('quad low', -249, -2361, 312), ('quad high', 424, -3240, 600), ('quad', 455, -3032, 440)],
}
def spawn_label(mp, x, y, z):
    best = min(SP[mp], key=lambda s: abs(s[1]-x)+abs(s[2]-y)+abs(s[3]-z))
    return best[0] if abs(best[1]-x) <= 160 and abs(best[2]-y) <= 160 and abs(best[3]-z) <= 96 else 'other'
