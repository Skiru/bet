import math
import bet.sofa.player_model as pm
import fit_player_model as fp
prm = pm.load_params()['basketball']
def dist(rec, f, scale):
    own = fp.family_sample(rec, f, prm.max_sample); pool = rec.pools[prm.pool][f]
    # copy of pm.count_distribution with a mean scale on every mu
    n = len(own); seconds = sum(s for s,_ in own); total = sum(v for _,v in own); mean_s = seconds/n
    pool_rate = pool.sum_v/pool.sum_s if pool.sum_s > 0 else total/seconds
    k = prm.prior_games*mean_s; rate = (total+k*pool_rate)/(seconds+k)
    w = [0.5**(i/prm.hl_minutes) for i in range(n)]; wt = sum(w)
    es = sum(a*s for a,(s,_) in zip(w, own))/wt; sp = sum(a*(s-es)**2 for a,(s,_) in zip(w, own))/wt
    cv = math.sqrt(sp)/max(es,1.0); sigma = math.sqrt(prm.sig_a**2+cv**2)
    po = pm.pearson_dispersion(own); parts = [(float(n), po)] if po is not None else []
    if pool.phi is not None: parts.append((float(prm.k_phi), pool.phi))
    ww = sum(a for a,_ in parts); phi = max(sum(a*b for a,b in parts)/ww if ww > 0 else 1.0, 1.0)
    norm = sum(pm._GH_WEIGHTS)
    mus = [scale*rate*es*math.exp(sigma*math.sqrt(2.0)*x-0.5*sigma*sigma) for x in pm._GH_NODES]
    kmax = int(max(mus)+12.0*math.sqrt(max(phi*max(mus),1.0))+12); pmf = [0.0]*(kmax+1)
    for a, mu in zip(pm._GH_WEIGHTS, mus):
        for i, v in enumerate(pm.nb_pmf(mu, phi*mu, kmax)): pmf[i] += a/norm*v
    return pmf, sum(a/norm*mu for a, mu in zip(pm._GH_WEIGHTS, mus))
def p_side(pmf, line, side, scale_b=prm.calibration_b):
    over = min(max(sum(m for k, m in enumerate(pmf) if k > line), 1e-6), 1-1e-6)
    over_c = pm.calibrate_side(over, scale_b)
    return over_c if side == "OVER" else 1.0 - over_c, over
