//! The hub composite: route._hub_search and route._hub_trees in one call. The candidates from
//! `hubs`, then per candidate the reversed tree from the hub to every driver (taps drop onto
//! their belt, the merges' spare outputs stay clear of what stands) and the forward tree from the
//! tile ahead of it to every consumer on what is left, until `wins` candidates route; the
//! cheapest wins. Each side tries its sink lists (route._grow's passes) in order and keeps the
//! first that routes, else the last.
use pyo3::prelude::*;
use rustc_hash::FxHashSet;

use crate::grid::{run_hubs, NativeGrid};
use crate::grow::{run_grow, tree_out, Costs, Ctx, Mv, Tree, TreeOut};
use crate::search::{to_ins, to_sinks, Ins, Sink, SinkIn};
use crate::{St, DX, DY, T};

/// One side's attempts: per attempt its sinks and their name ids.
type Attempts = Vec<(Vec<Sink>, Vec<String>)>;

fn attempts_of(lists: Vec<Vec<SinkIn>>, names: Vec<Vec<String>>, ins: &[Ins]) -> PyResult<Attempts> {
    if lists.len() != names.len() || lists.is_empty() {
        return Err(pyo3::exceptions::PyValueError::new_err("hub_search: one name list per attempt, one attempt at least"));
    }
    let mut out = Vec::with_capacity(lists.len());
    for (l, n) in lists.into_iter().zip(names) {
        let sinks = to_sinks(l, ins)?;
        if sinks.iter().any(|s| matches!(s, Sink::TapCb { .. })) {
            return Err(pyo3::exceptions::PyValueError::new_err("hub_search: a sink with a Python goal"));
        }
        out.push((sinks, n));
    }
    Ok(out)
}

/// route._grow's loop over its passes: the first sink list whose tree has no problems, else the
/// last. -> (attempt index, tree, log, routed).
fn try_attempts<'a>(
    grid: &'a NativeGrid,
    keep_clear: &[T],
    drop_taps: bool,
    root: St,
    attempts: &Attempts,
    ins: &'a [Ins],
    costs: Costs,
    improve: usize,
    limit: usize,
) -> PyResult<(usize, Tree, Ctx<'a>, Vec<crate::grow::LogOut>, bool)> {
    let mut last = None;
    for (ai, (sinks, names)) in attempts.iter().enumerate() {
        let cx = Ctx::new(grid, keep_clear, drop_taps, sinks.clone(), names, ins, costs, limit, &[])?;
        let (tree, log) = run_grow(&cx, root, improve, None)?;
        let ok = !tree.has_problems(&cx);
        if ok {
            return Ok((ai, tree, cx, log, true));
        }
        last = Some((ai, tree, cx, log));
    }
    let (ai, tree, cx, log) = last.unwrap();
    Ok((ai, tree, cx, log, false))
}

/// The tiles the reversed tree's carriers point into (route._belt_fronts of its plan): every
/// belt and underground exit of the reversed view points back at the tile its state was reached
/// from, a splitter's two tiles likewise; an underground entrance (a state that just exited, read
/// backwards) points nowhere.
fn reversed_fronts(tree: &Tree) -> FxHashSet<T> {
    let mut out = FxHashSet::default();
    for s in tree.states() {
        let back = ((s.2 + 2) % 4) as usize;
        let mv = tree.succ.get(&s);
        if let Some(Mv::Jump(_)) = mv {
            out.insert((s.0 + DX[back], s.1 + DY[back]));
            continue;
        }
        if let Some(Mv::Split(side, _, _)) = mv {
            let d = s.2 as usize;
            let n = (s.0 + DX[d], s.1 + DY[d]);
            let sh = ((s.2 + side) % 4) as usize;
            let m = (n.0 + DX[sh], n.1 + DY[sh]);
            out.insert((n.0 + DX[back], n.1 + DY[back]));
            out.insert((m.0 + DX[back], m.1 + DY[back]));
        }
        if s.3 == 0 {
            out.insert((s.0 + DX[back], s.1 + DY[back]));
        }
    }
    out
}

type Best = (T, i64, usize, TreeOut, usize, TreeOut);
type Fail = (T, i64, u8, usize, TreeOut, Option<(usize, TreeOut)>);

/// route._hub_search over route._hub_trees -> (the best candidate, the first that failed, how
/// many candidates there were). The best: (hub, f, the drivers' attempt, its tree, the consumers'
/// attempt, its tree); the first failure: (hub, f, 0 drivers | 1 consumers, attempt, its tree,
/// and for a consumers' failure the drivers' (attempt, tree) that stood). ``grid``: the hub's
/// bounded ground (blocked, box, spans, the negotiated soft tiles); ``near_d`` / ``near_c`` /
/// ``ends``: as `hubs`; ``keep_clear``: the standing belts, for the reversed tree; the attempts
/// as `grow`'s sinks, with their names; ``inserters`` and ``costs`` as `grow`'s.
#[pyfunction]
#[pyo3(signature = (grid, near_d, near_c, ends, most, keep_clear, r_attempts, r_names, f_attempts,
                    f_names, inserters, costs, improve, limit, wins, reach=5))]
#[allow(clippy::too_many_arguments)]
pub(crate) fn hub_search(
    grid: &Bound<'_, NativeGrid>,
    near_d: Vec<Vec<T>>,
    near_c: Vec<Vec<T>>,
    ends: Vec<T>,
    most: usize,
    keep_clear: Vec<T>,
    r_attempts: Vec<Vec<SinkIn>>,
    r_names: Vec<Vec<String>>,
    f_attempts: Vec<Vec<SinkIn>>,
    f_names: Vec<Vec<String>>,
    inserters: Vec<(String, i64, f64)>,
    costs: Costs,
    improve: usize,
    limit: usize,
    wins: usize,
    reach: i64,
) -> PyResult<(Option<Best>, Option<Fail>, usize)> {
    let base = grid.get();
    if base.bbox.is_none() {
        return Err(pyo3::exceptions::PyValueError::new_err("hub_search needs a bounded grid"));
    }
    let ins = to_ins(inserters);
    let ra = attempts_of(r_attempts, r_names, &ins)?;
    let fa = attempts_of(f_attempts, f_names, &ins)?;
    let ends_set: FxHashSet<T> = ends.into_iter().collect();
    let cands = run_hubs(base, &near_d, &near_c, &ends_set, most, reach);
    let n = cands.len();
    let mut best: Option<(f64, Best)> = None;
    let mut first_fail: Option<Fail> = None;
    let mut won = 0usize;
    for (hub, f) in cands {
        let fu = f as usize;
        let front = (hub.0 + DX[fu], hub.1 + DY[fu]);
        // the reversed tree: from the hub, heading away from F, to every driver; F is taken
        let mut rocc = base.occ.clone();
        rocc.insert(front);
        let rgrid = base.derived(rocc, base.spans.clone());
        let rroot = (hub.0, hub.1, (f + 2) % 4, 0);
        let (ri, rtree, rcx, rlog, rok) = try_attempts(&rgrid, &keep_clear, true, rroot, &ra, &ins, costs, improve, limit)?;
        if !rok {
            if first_fail.is_none() {
                first_fail = Some((hub, f, 0, ri, tree_out(&rtree, &ins, rlog), None));
            }
            continue;
        }
        // the forward tree: from F, on what the reversed tree left, to every consumer
        let mut focc = base.occ.clone();
        let rtiles = rtree.tiles(&rcx);
        focc.extend(rtiles.own.keys().copied());
        for t in reversed_fronts(&rtree) {
            if t != front {
                focc.insert(t);
            }
        }
        let rs = rtree.spans();
        let mut fspans = base.spans.clone();
        for ax in 0..2 {
            fspans[ax].extend(rs[ax].iter().copied());
        }
        let fgrid = base.derived(focc, fspans);
        let froot = (front.0, front.1, f, 0);
        let (fi, ftree, fcx, flog, fok) = try_attempts(&fgrid, &[], false, froot, &fa, &ins, costs, improve, limit)?;
        if !fok {
            if first_fail.is_none() {
                first_fail = Some((hub, f, 1, fi, tree_out(&ftree, &ins, flog), Some((ri, tree_out(&rtree, &ins, rlog)))));
            }
            continue;
        }
        let cost = rtree.cost(&rcx) + ftree.cost(&fcx);
        if best.as_ref().map_or(true, |(c, _)| cost < c - 1e-9) {
            best = Some((cost, (hub, f, ri, tree_out(&rtree, &ins, rlog), fi, tree_out(&ftree, &ins, flog))));
        }
        won += 1;
        if won >= wins {
            break;
        }
    }
    Ok((best.map(|(_, b)| b), first_fail, n))
}
