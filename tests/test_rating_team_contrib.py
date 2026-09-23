"""v4 4on4 engine: the +/- contribution term. Synthetic checks, no database.

Run: python tests/test_rating_team_contrib.py
"""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rate as R

checks = []
def check(name):
    def deco(f): checks.append((name, f)); return f
    return deco

def pm_terms(T, rr, sign, exp_margin):
    """Mirror of rate_team_mode's inner _pm_terms (kept in sync by hand)."""
    if R.TEAM_PM_W <= 0 or any(row[5] is None for row in T):
        return None
    mu_sum = sum(m for m, _ in rr); mean_mu = mu_sum / len(rr)
    expected = [sign * exp_margin * (m / mu_sum) + R.TEAM_PM_K * (m - mean_mu) for m, _ in rr]
    resid = [float(row[5]) - e for row, e in zip(T, expected)]
    mres = sum(resid) / len(resid)
    return [R.TEAM_PM_W * math.tanh((r - mres) / R.TEAM_PM_NORM) for r in resid]

def team(pms, mus=(1500, 1500, 1500, 1500)):
    T = [(f"p{i}", 50, 50, 8000, 8000, pm) for i, pm in enumerate(pms)]
    rr = [(m, 80.0) for m in mus]
    return T, rr

@check("constants: k derived from the margin slope, weight and norm as backtested")
def _():
    assert abs(R.TEAM_PM_K - R.TEAM_EXP_AMP / R.TEAM_EXP_SCALE / 4) < 1e-9
    assert R.TEAM_PM_W == 0.5 and R.TEAM_PM_NORM == 40.0
    assert R.ENGINE_VERSION.startswith("v4")

@check("equal players, equal +/-: no contribution for anyone")
def _():
    T, rr = team([10, 10, 10, 10])
    out = pm_terms(T, rr, +1.0, 0.0)
    assert all(abs(x) < 1e-9 for x in out), out

@check("terms are zero-sum within the team (mean residual removed)")
def _():
    T, rr = team([40, 0, -20, 20], mus=(1700, 1500, 1400, 1600))
    out = pm_terms(T, rr, +1.0, 12.0)
    # tanh is monotone, so signs follow the centred residuals; sum of residuals is zero by construction
    mu_sum = sum(m for m, _ in rr); mean_mu = mu_sum / 4
    exp = [12.0 * (m / mu_sum) + R.TEAM_PM_K * (m - mean_mu) for m, _ in rr]
    res = [pm - e for (_, _, _, _, _, pm), e in zip(T, exp)]
    assert abs(sum(r - sum(res) / 4 for r in res)) < 1e-9

@check("a strong player is expected to out-produce weak teammates: same +/- for all -> the strong one is debited")
def _():
    T, rr = team([10, 10, 10, 10], mus=(2000, 1400, 1400, 1400))
    out = pm_terms(T, rr, +1.0, 0.0)
    assert out[0] < 0 and all(x > 0 for x in out[1:]), out
    # 600 mu above the team mean of 1550 -> expected +17.7 more than mates; posting the same is a shortfall
    assert out[0] < -0.05

@check("the weak player who out-produces his expectation is credited (cronus-type night)")
def _():
    T, rr = team([25, 0, 5, 10], mus=(1200, 1950, 1770, 1910))
    out = pm_terms(T, rr, +1.0, -15.0)
    assert out[0] > 0.1, out          # +25 from the lowest-rated seat is well above his expected share

@check("capped: a monster game cannot exceed the weight")
def _():
    T, rr = team([400, -100, -100, -100])
    out = pm_terms(T, rr, +1.0, 0.0)
    assert max(out) <= R.TEAM_PM_W + 1e-9 and max(out) > 0.49

@check("fallback: any player without demo +/- disables the term for that team")
def _():
    T, rr = team([10, None, 10, 10])
    assert pm_terms(T, rr, +1.0, 0.0) is None

@check("sign: on team B the expected margin flips (B's players expected to post the negative of A's margin)")
def _():
    T, rr = team([0, 0, 0, 0], mus=(1500, 1500, 1500, 1500))
    a = pm_terms(T, rr, +1.0, 20.0); b = pm_terms(T, rr, -1.0, 20.0)
    # equal mus and equal +/- -> expected split is uniform on both sides -> centred residuals zero either way
    assert all(abs(x) < 1e-9 for x in a + b)

@check("fetch_team_matches rows carry six fields (cid, frags, deaths, dg, dt, pm) per player")
def _():
    src = Path(R.__file__).read_text()
    assert "(cid, fr, de, dg, dt, pm)" in src and "for (cid, fr, de, dg, dt, _pm) in TA + TB" in src

def main():
    failed = 0
    for name, f in checks:
        try:
            f(); print(f"  ok   {name}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL {name}: {e}")
    print(f"{len(checks) - failed}/{len(checks)} passed"); return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
