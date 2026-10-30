"""Synthetic-validation kernels for the two preregistered intradraw v2 IDs.

No file/data loader or external scoring runner. Fixed-size set probabilities,
joint eight-ticket coverage, marginal balancing and projected optimization only.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from functools import lru_cache
import math
import os
from pathlib import Path
import sys

import numpy as np
from scipy.linalg import solve
from scipy.special import roots_hermitenorm

LD = np.longdouble
ROUND_BUDGET = 5e-12
QUAD_ORDER = 64
CHECK_ORDER = 80
NODE_BATCH = 32
INNER_TOL = 5e-12
MARGINAL_LIMIT = 1e-10


class NumericalFailure(RuntimeError):
    """A locked stop, never a request to change order, tolerance or start."""


def require(value, message):
    if not value:
        raise NumericalFailure(message)


def validate(U, log_weights, k, probe=False):
    U, a = np.asarray(U, LD), np.asarray(log_weights, LD)
    require(U.ndim == 2 and U.shape[1] == 2 and a.shape == (len(U),), "rank2 shape")
    require(0 < k < len(U) and k <= 6, "fixed selected count <=6")
    radius = LD('1.001') if probe else LD(1)
    require(np.isfinite(U).all() and np.isfinite(a).all(), "nonfinite parameter")
    require(np.all((U*U).sum(axis=1) <= radius*radius), "row L2 constraint")
    require(abs(a.sum()) <= LD('1e-12'), "log-weight gauge sum must be zero")
    require(np.max(np.abs(a)) <= 80, "numerical dynamic-range stop, no clipping")
    require(np.finfo(LD).eps <= LD('2e-19'), "requires >=63-bit longdouble mantissa")
    return U, a


def original_template(pool, permutation=None):
    if permutation is None:
        permutation = list(range(1, pool+1))
    require(sorted(permutation) == list(range(1, pool+1)), "not a number permutation")
    tickets = tuple(tuple(sorted(permutation[(6*r+j) % pool] for j in range(6)))
                    for r in range(8))
    require(len(set(tickets)) == 8 and all(len(set(t)) == 6 for t in tickets),
            "requires eight distinct six-number tickets")
    return tickets


def fixed_permutations(pool):
    generator = np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261030,64,pool])))
    return [generator.permutation(np.arange(1,pool+1)).tolist() for _ in range(64)]


@lru_cache(maxsize=16)
def geometry(pool, k, tickets):
    """Membership groups and all DP transitions, including an absorbing cap3.

    Losing states store each hit count0..2. A transition reaching cap3 moves to
    success=-1; subsequent hits cannot undo success, so their counts coalesce.
    This is exactly the selected-count<=6/capped-at3 union DP, not a sum of hits.
    """
    require(len(tickets)==8, "joint event requires eight tickets")
    ticket_sets=[set(t) for t in tickets]
    require(all(len(t)==len(set(t)) and set(t)<=set(range(1,pool+1)) for t in tickets),
            "invalid ticket members")
    groups=defaultdict(list)
    for ball in range(1,pool+1):
        mask=sum(1<<b for b,t in enumerate(ticket_sets) if ball in t)
        groups[mask].append(ball-1)
    states=[(0,0)]; stages=[]
    for mask, members in sorted(groups.items()):
        next_states={}; transitions=defaultdict(list)
        for index,(selected,code) in enumerate(states):
            for h in range(min(len(members),k-selected)+1):
                newcode=code
                if code>=0:
                    for b in range(8):
                        if mask & (1<<b):
                            digit=(code//3**b)%3
                            if digit+h>=3:
                                newcode=-1;break
                            newcode+=h*3**b
                state=(selected+h,newcode)
                target=next_states.setdefault(state,len(next_states))
                transitions[h].append((index,target))
        stages.append((tuple(members),len(next_states),
            tuple((h,np.array([x for x,_ in pairs],int),np.array([y for _,y in pairs],int))
                  for h,pairs in sorted(transitions.items()))))
        states=list(next_states)
    success=[i for i,(selected,code) in enumerate(states) if selected==k and code==-1]
    total=[i for i,(selected,_) in enumerate(states) if selected==k]
    return tuple(stages),tuple(success),tuple(total)


def moment_product(a,b):
    """[1,sum ux²,sum uy²,sum uxuy,sum pair cross²] under weighted sums."""
    a,b=np.asarray(a,LD),np.asarray(b,LD)
    out=np.empty(np.broadcast_shapes(a.shape,b.shape),dtype=LD)
    out[...,0]=a[...,0]*b[...,0]
    out[...,1]=a[...,1]*b[...,0]+a[...,0]*b[...,1]
    out[...,2]=a[...,2]*b[...,0]+a[...,0]*b[...,2]
    out[...,3]=a[...,3]*b[...,0]+a[...,0]*b[...,3]
    out[...,4]=(a[...,4]*b[...,0]+a[...,0]*b[...,4]+a[...,1]*b[...,2]
                +a[...,2]*b[...,1]-2*a[...,3]*b[...,3])
    return out


def determinant_mass(moment):
    return moment[...,0]+moment[...,1]+moment[...,2]+moment[...,4]


def atom(weight,u):
    x,y=u
    return np.array([weight,weight*x*x,weight*y*y,weight*x*y,LD(0)],LD)


def union_dp(weights,tickets,k,U=None):
    weights=np.atleast_2d(np.asarray(weights,LD))
    batch,pool=weights.shape
    stages,success,total=geometry(pool,k,tuple(tuple(t) for t in tickets))
    channels=1 if U is None else 5
    values=np.zeros((batch,1,channels),LD);values[:,0,0]=1
    for members,count,transitions in stages:
        coeff=np.zeros((batch,k+1,channels),LD);coeff[:,0,0]=1
        for i in members:
            if U is None:
                coeff[:,1:,0]+=coeff[:,:-1,0]*weights[:,i,None]
            else:
                u=np.asarray(U[i],LD)
                single=np.stack([atom(w,u) for w in weights[:,i]])
                coeff[:,1:]+=moment_product(coeff[:,:-1],single[:,None,:])
        updated=np.zeros((batch,count,channels),LD)
        for h,source,target in transitions:
            if U is None:
                addition=values[:,source,:]*coeff[:,h,None,:]
            else:
                addition=moment_product(values[:,source,:],coeff[:,h,None,:])
            np.add.at(updated,(np.arange(batch)[:,None],target[None,:]),addition)
        values=updated
    if U is None:
        mass=values[...,0]
    else:
        mass=determinant_mass(values)
    return mass[:,success].sum(axis=1),mass[:,total].sum(axis=1)


@lru_cache(maxsize=32)
def uniform_p8(pool,k,tickets):
    stages,success,total=geometry(pool,k,tickets)
    values=[1]
    for members,count,transitions in stages:
        updated=[0]*count
        for h,source,target in transitions:
            factor=math.comb(len(members),h)
            for s,t in zip(source,target):updated[int(t)]+=values[int(s)]*factor
        values=updated
    denominator=sum(values[i] for i in total)
    require(denominator==math.comb(pool,k),"integer DP lost subsets")
    return Fraction(sum(values[i] for i in success),denominator)


def dpp_polynomial(U,a,k):
    """Rank2 principal-minor expansion, every subset size retained up to k."""
    poly=np.zeros((k+1,5),LD);poly[0,0]=1
    for u,w in zip(U,np.exp(a)):
        poly[1:]+=moment_product(poly[:-1],atom(w,u))
    return poly


def exclusion_normalizer_marginals(U,a,k=6,probe=False):
    U,a=validate(U,a,k,probe)
    z=determinant_mass(dpp_polynomial(U,a,k)[k])
    nums=[]
    for i in range(len(U)):
        keep=np.arange(len(U))!=i
        rest=dpp_polynomial(U[keep],a[keep],k-1)[k-1]
        nums.append(determinant_mass(moment_product(rest,atom(np.exp(a[i]),U[i]))))
    pi=np.asarray(nums,LD)/z
    require(z>0 and np.isfinite(z) and np.isfinite(pi).all(),"invalid DPP mass")
    require(abs(pi.sum()-k)<=LD('1e-11'),"DPP fixed-size marginal sum")
    return z,pi


@lru_cache(maxsize=2)
def gaussian_nodes(order):
    """Probabilists' Hermite roots refined at Decimal precision80, then LD.

    Weights are (order-1)!/[order He_(order-1)(x)^2] for N(0,1), not
    unnormalized e^(-x²/2) weights. No sqrt(2) or missing normalization.
    """
    require(order in (QUAD_ORDER,CHECK_ORDER),"quadrature order is locked")
    initial=roots_hermitenorm(order)[0]
    roots=[];weights=[]
    with localcontext() as ctx:
        ctx.prec=80
        for guess in initial:
            x=Decimal(str(float(guess)))
            for _ in range(40):
                previous,current=Decimal(1),x
                for n in range(1,order):previous,current=current,x*current-n*previous
                delta=current/(order*previous)
                x-=delta
                if abs(delta)<Decimal('1e-65'):break
            else:raise NumericalFailure('Hermite node refinement')
            previous,current=Decimal(1),x
            for n in range(1,order):previous,current=current,x*current-n*previous
            weight=Decimal(math.factorial(order-1))/(order*previous*previous)
            roots.append(LD(str(x)));weights.append(LD(str(weight)))
    roots,weights=np.array(roots,LD),np.array(weights,LD)
    require(abs(weights.sum()-1)<=LD('5e-18'),"Gaussian weights do not sum to one")
    grid=np.array([(x,y) for x in roots for y in roots],LD)
    product=np.array([x*y for x in weights for y in weights],LD)
    return grid,product


def quadrature_bound(U,k,order=QUAD_ORDER):
    require(order in (QUAD_ORDER,CHECK_ORDER),"quadrature order is locked")
    # Fixed conservative radius includes central-difference probes. Do not let
    # very small nonzero U underflow a claimed error bound to zero.
    with localcontext() as ctx:
        ctx.prec=80
        lam=(Decimal(k)*Decimal('1.001'))**2/2
        first=(-lam).exp()*lam**order/Decimal(math.factorial(order))
        bound=2*first/(1-lam/Decimal(order+1))*(1+Decimal('1e-40'))
        epsilon=float(np.nextafter(float(bound),math.inf))
    # Positive exponential mixtures; low moments match and Gaussian even
    # moments above order dominate quadrature moments. Union bound in 2D.
    require(0<epsilon<1e-12,"analytic Gaussian truncation bound exceeds lock")
    return epsilon


def scalar_esp_marginals(weights,k):
    b,n=weights.shape
    prefix=np.zeros((n+1,b,k+1),LD);prefix[0,:,0]=1
    for i in range(n):
        prefix[i+1]=prefix[i]
        prefix[i+1,:,1:]+=prefix[i,:,:-1]*weights[:,i,None]
    suffix=np.zeros_like(prefix);suffix[n,:,0]=1
    for i in range(n-1,-1,-1):
        suffix[i]=suffix[i+1]
        suffix[i,:,1:]+=suffix[i+1,:,:-1]*weights[:,i,None]
    nums=np.zeros((b,n),LD)
    for i in range(n):
        nums[:,i]=weights[:,i]*sum(prefix[i,:,h]*suffix[i+1,:,k-1-h] for h in range(k))
    return prefix[n,:,k],nums


def attract_integrals(U,a,k=6,tickets=None,order=QUAD_ORDER,probe=False):
    U,a=validate(U,a,k,probe)
    grid,gh=gaussian_nodes(order)
    z=LD(0);nums=np.zeros(len(U),LD);event=LD(0)
    for start in range(0,len(grid),NODE_BATCH):
        q=grid[start:start+NODE_BATCH];g=gh[start:start+NODE_BATCH]
        weights=np.exp(a[None,:]+q@U.T-(U*U).sum(axis=1)[None,:]/2)
        denominator,numerator=scalar_esp_marginals(weights,k)
        z+=g@denominator;nums+=g@numerator
        if tickets is not None:
            positive,total=union_dp(weights,tickets,k)
            require(np.max(np.abs(total/denominator-1))<=LD('5e-12'),"event DP/Z mismatch")
            event+=g@positive
    require(z>0 and np.isfinite(z) and np.isfinite(nums).all(),"invalid HS integral")
    pi=nums/z
    require(abs(pi.sum()-k)<=LD('1e-11'),"HS fixed-size marginal sum")
    return z,pi,event


@dataclass(frozen=True)
class Estimate:
    value: float
    absolute_error: float
    quadrature_relative_bound: float
    exact_fraction: Fraction | None = None

    def __post_init__(self):
        require(math.isfinite(self.value) and 0<=self.value<=1 and
                math.isfinite(self.absolute_error) and self.absolute_error>=0,
                "invalid probability/error estimate")

    @property
    def lower(self):return max(0.,self.value-self.absolute_error)
    @property
    def upper(self):return min(1.,self.value+self.absolute_error)


def p8(family,U,a,tickets,k=6):
    U,a=validate(U,a,k)
    tickets=tuple(tuple(sorted(t)) for t in tickets)
    # With every U row identical and a=0, all k-subsets have equal mass.
    if np.all(U==U[0]) and np.all(a==0):
        fraction=uniform_p8(len(U),k,tickets)
        return Estimate(float(fraction),0.,0.,fraction)
    if family=='exclusion':
        numerator,total=union_dp(np.exp(a),tickets,k,U)
        z,pi=exclusion_normalizer_marginals(U,a,k)
        require(abs(total[0]/z-1)<=LD('5e-12'),"rank2 union/Z mismatch")
        return Estimate(float(numerator[0]/z),ROUND_BUDGET,0.)
    if family!='attract2':raise ValueError('unknown family')
    z,_,event=attract_integrals(U,a,k,tickets,QUAD_ORDER)
    zz,_,ee=attract_integrals(U,a,k,tickets,CHECK_ORDER)
    value,check=event/z,ee/zz
    require(abs(value-check)<=LD('5e-12'),"64/80 coverage certification failed")
    epsilon=quadrature_bound(U,k)
    return Estimate(float(value),ROUND_BUDGET+epsilon/(1-epsilon),epsilon)


def normalizer_marginals(family,U,a,k=6,probe=False,order=QUAD_ORDER):
    if family=='exclusion':return exclusion_normalizer_marginals(U,a,k,probe)
    if family=='attract2':return attract_integrals(U,a,k,order=order,probe=probe)[:2]
    raise ValueError('unknown family')


def balance(family,U,k=6,probe=False):
    """One zero-start gauge-fixed Newton solve, never free marginal d fitting."""
    U=np.asarray(U,LD);n=len(U);a=np.zeros(n,LD);target=LD(k)/n
    for step in range(101):
        z,pi=normalizer_marginals(family,U,a,k,probe)
        error=float(np.max(np.abs(pi-target)))
        if error<=INNER_TOL:
            epsilon=quadrature_bound(U,k) if family=='attract2' else 0.
            extra=epsilon/(1-epsilon)
            require(error+ROUND_BUDGET+extra<=MARGINAL_LIMIT,"marginal total budget")
            if family=='attract2':
                zz,pp=normalizer_marginals(family,U,a,k,probe,CHECK_ORDER)
                require(np.max(np.abs(pp-pi))<=LD('5e-12') and abs(zz/z-1)<=LD('5e-12'),
                        "64/80 balancing certification failed")
            return dict(log_weights=a,pi=pi,Z=z,iterations=step,max_error=error,
                        marginal_error_budget=ROUND_BUDGET+extra)
        require(step<100,"inner100-step limit")
        jac=np.zeros((n-1,n-1),float);h=LD('1e-4')
        for j in range(n-1):
            plus,minus=a.copy(),a.copy();plus[j]+=h;plus[-1]-=h;minus[j]-=h;minus[-1]+=h
            pp=normalizer_marginals(family,U,plus,k,probe)[1]
            pm=normalizer_marginals(family,U,minus,k,probe)[1]
            jac[:,j]=np.asarray((pp[:-1]-pm[:-1])/(2*h),float)
        require(np.linalg.cond(jac)<1e12,"inner gauge Jacobian ill-conditioned")
        delta=solve(jac,-np.asarray(pi[:-1]-target,float))
        for backtrack in range(32):
            proposal=a.copy();proposal[:-1]+=LD(2)**(-backtrack)*delta
            proposal[-1]=-proposal[:-1].sum()
            if np.max(np.abs(proposal))>80:continue
            newpi=normalizer_marginals(family,U,proposal,k,probe)[1]
            if np.max(np.abs(newpi-target))<error:
                a=proposal;break
        else:raise NumericalFailure('inner line search failed')
    raise NumericalFailure('unreachable')


def initial_U(pool):
    generator=np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261030,2,pool])))
    z=generator.normal(size=(pool,2))
    return .1*z/np.maximum(1,np.linalg.norm(z,axis=1))[:,None]


def project_rows(U):
    a=np.array(U,float,copy=True)
    require(np.isfinite(a).all(),"nonfinite disk projection")
    high=a.astype(LD);norms=np.sqrt((high*high).sum(axis=1))
    outside=norms>1
    a[outside]=np.asarray(high[outside]*(LD(np.nextafter(1.,0.))/norms[outside])[:,None],float)
    # A float64 norm can round to1 even when the represented vector is outside.
    # Check at higher precision, then move any remaining excess inward only.
    for _ in range(4):
        excess=(a.astype(LD)**2).sum(axis=1)>1
        if not np.any(excess):return a
        a[excess]=np.nextafter(a[excess],0.)
    raise NumericalFailure('disk projection rounding failed')


def projected_optimize(objective,initial):
    """The locked single-start outer solver; objective accepts synthetic arrays.

    Central difference probes can reach radius1.0001; only projected feasible
    candidates are accepted. Models use radius1.001 solely to validate probes.
    """
    U=project_rows(initial);previous=None
    for iteration in range(1001):
        value=float(objective(U,False));gradient=np.zeros_like(U);h=1e-4
        for i in range(len(U)):
            for j in range(2):
                p,m=U.copy(),U.copy();p[i,j]+=h;m[i,j]-=h
                gradient[i,j]=(objective(p,True)-objective(m,True))/(2*h)
        require(math.isfinite(value) and np.isfinite(gradient).all(),"nonfinite outer objective/gradient")
        mapping=project_rows(U-gradient)-U
        change=math.inf if previous is None else abs(value-previous)/max(1.,abs(value))
        if np.max(np.abs(mapping))<=1e-4 and change<=1e-8:
            return dict(U=U,objective=value,iterations=iteration,success=True,
                        projected_gradient_max=float(np.max(np.abs(mapping))))
        require(iteration<1000,"outer1000-step limit")
        for backtrack in range(40):
            proposal=project_rows(U-(2.**(-backtrack))*gradient)
            proposed=float(objective(proposal,False))
            require(math.isfinite(proposed),"nonfinite outer trial objective")
            if proposed<=value+1e-4*np.sum(gradient*(proposal-U)):
                previous,U=value,proposal;break
        else:raise NumericalFailure('outer line search failed')
    raise NumericalFailure('unreachable')


def profiled_objective(family,U,draws,k=6,probe=False):
    """Sum joint negative log probabilities plus ||U||F²/2; no data IO."""
    solved=balance(family,U,k,probe);a=solved['log_weights'];U=np.asarray(U,LD)
    result=LD(len(draws))*np.log(solved['Z'])+(U*U).sum()/2
    for draw in draws:
        indices=np.asarray(draw,int)-1
        require(len(indices)==k and len(set(indices.tolist()))==k and np.all((indices>=0)&(indices<len(U))),
                "invalid synthetic complete-k set")
        v=U[indices]
        if family=='exclusion':
            # det(I2+U_S^T U_S), retaining identity contributions.
            multiplier=(1+(v[:,0]**2).sum())*(1+(v[:,1]**2).sum())-(v[:,0]*v[:,1]).sum()**2
            result-=a[indices].sum()+np.log(multiplier)
        else:
            pair=((v.sum(axis=0)**2).sum()-(v*v).sum())/2
            result-=a[indices].sum()+pair
    return float(result)


def fit_once(family,draws,pool):
    """Future in-memory fit entry: exactly200 provided sets, no IO or scoring."""
    require(family in ('exclusion','attract2') and pool in (49,43),"locked models/pools only")
    require(len(draws)==200,"exactly200 warmup sets, no rolling window")
    objective=lambda U,probe:profiled_objective(family,U,draws,6,probe)
    fitted=projected_optimize(objective,initial_U(pool))
    solved=balance(family,fitted['U'],6)
    return dict(U=fitted['U'],log_weights=solved['log_weights'],outer=fitted,inner=solved,success=True)


def choose_estimates(estimates):
    """Exact ties choose first; overlapping uncertainty is failure, not a tie."""
    if all(e.exact_fraction is not None for e in estimates):
        return max(range(len(estimates)),key=lambda i:estimates[i].exact_fraction)
    best=max(range(len(estimates)),key=lambda i:estimates[i].value)
    for i,e in enumerate(estimates):
        if i==best:continue
        require(estimates[best].lower>e.upper,"template ordering unresolved at locked precision")
    return best


def select_template(family,U,a,permutations,k=6):
    require(len(permutations)==64,"exactly64 frozen permutations required")
    require(permutations==fixed_permutations(len(U)),"frozen candidate set changed")
    # Re-label parameters into canonical position order; geometry itself fixed.
    tickets=original_template(len(U));estimates=[]
    for permutation in permutations:
        require(sorted(permutation)==list(range(1,len(U)+1)),"invalid permutation")
        ix=np.array(permutation)-1
        estimates.append(p8(family,np.asarray(U)[ix],np.asarray(a)[ix],tickets,k))
    index=choose_estimates(estimates)
    return index,original_template(len(U),permutations[index]),estimates


def install_no_data_guard(root=None):
    """Opt-in synthetic process guard; no historical result files are inputs."""
    root=Path(root) if root is not None else Path(__file__).resolve().parents[1]
    paths=[(root/p).resolve() for p in ('data','marksix_data.csv','ev','audits','forward')]
    def audit(event,args):
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            path=Path(os.fsdecode(args[0])).resolve()
            if any(path==p or path.is_relative_to(p) for p in paths):
                raise PermissionError('intradraw synthetic-only process forbids historical inputs')
    sys.addaudithook(audit)
