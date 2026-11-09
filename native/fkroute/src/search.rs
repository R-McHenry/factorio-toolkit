//! One A*: steiner._astar_py step for step (the heap orders entries as Python's tuple
//! `(f, -g, state)` does, and costs are summed in the same order).
use pyo3::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};
use std::cmp::Ordering;
use std::collections::BinaryHeap;

use crate::grid::NativeGrid;
use crate::{St, DX, DY, T};

#[derive(Clone, Copy)]
pub(crate) enum Sink {
    Fixed { x: i64, y: i64, edir: i64 },
    Tap { x0: i64, y0: i64, x1: i64, y1: i64 },
}

impl Sink {
    #[inline]
    pub(crate) fn h(&self, x: i64, y: i64) -> i64 {
        match *self {
            Sink::Fixed { x: tx, y: ty, .. } => (x - tx).abs() + (y - ty).abs(),
            Sink::Tap { x0, y0, x1, y1 } => {
                let dx = (x0 - x).max(0).max(x - (x1 - 1));
                let dy = (y0 - y).max(0).max(y - (y1 - 1));
                (dx + dy - 3).max(0)
            }
        }
    }
}

struct Entry {
    f: f64,
    ng: f64,
    st: St,
}

impl PartialEq for Entry {
    fn eq(&self, o: &Self) -> bool {
        self.cmp(o) == Ordering::Equal
    }
}
impl Eq for Entry {}
impl PartialOrd for Entry {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for Entry {
    // BinaryHeap pops the largest: reverse Python's min-heap order on (f, -g, state).
    // partial_cmp, not total_cmp: Python treats -0.0 and 0.0 as equal.
    fn cmp(&self, o: &Self) -> Ordering {
        o.f.partial_cmp(&self.f)
            .unwrap_or(Ordering::Equal)
            .then_with(|| o.ng.partial_cmp(&self.ng).unwrap_or(Ordering::Equal))
            .then_with(|| o.st.cmp(&self.st))
    }
}

pub(crate) fn trace(parent: &FxHashMap<St, Option<St>>, st: St) -> Vec<St> {
    let mut out = vec![st];
    while let Some(Some(p)) = parent.get(out.last().unwrap()) {
        out.push(*p);
    }
    out.reverse();
    out
}

/// The search's fixed inputs: the ground (grid + the tree's own blocked tiles), the tree's tunnels,
/// the sinks and the costs.
pub(crate) struct Search<'a> {
    pub(crate) grid: &'a NativeGrid,
    pub(crate) extra: &'a FxHashSet<T>,
    pub(crate) tspans: &'a [FxHashSet<T>; 2],
    pub(crate) sinks: &'a [Sink],
    pub(crate) targets: &'a [usize],
    pub(crate) tapped: &'a FxHashSet<T>,
    pub(crate) lane_ok: &'a FxHashMap<T, u16>, // PLAN-LANES: a fed tile's allowed carriers (lanephys.tile_mask)
    pub(crate) belt: f64,
    pub(crate) turn: f64,
    pub(crate) ug: f64,
    pub(crate) max_ug: i64,
    pub(crate) limit: usize,
}

/// steiner._astar_py, step for step -> (path, sink index, cost, the start the path left from).
/// ``tap_goal(i, path, start)``: the goal test of tap sink i (Python's, or the native one).
pub(crate) fn search<F>(s: &Search, starts: &[(St, f64)], start_spare: &[Option<T>], mut tap_goal: F)
    -> PyResult<Option<(Vec<St>, usize, f64, usize)>>
where
    F: FnMut(usize, &[St], usize) -> PyResult<bool>,
{
    let (grid, extra, sinks, targets) = (s.grid, s.extra, s.sinks, s.targets);
    let sink_tiles: FxHashSet<T> = sinks
        .iter()
        .filter_map(|s| match *s {
            Sink::Fixed { x, y, .. } => Some((x, y)),
            _ => None,
        })
        .collect();
    let blocked = |t: T| grid.blocked(t) || extra.contains(&t);
    let hh = |x: i64, y: i64| -> f64 { targets.iter().map(|&i| sinks[i].h(x, y)).min().unwrap() as f64 };

    let mut heap: BinaryHeap<Entry> = BinaryHeap::new();
    let mut g: FxHashMap<St, f64> = FxHashMap::default();
    let mut parent: FxHashMap<St, Option<St>> = FxHashMap::default();
    let mut start_of: FxHashMap<St, usize> = FxHashMap::default();
    for (idx, &(st, g0)) in starts.iter().enumerate() {
        if g0 < *g.get(&st).unwrap_or(&f64::INFINITY) {
            g.insert(st, g0);
            parent.insert(st, None);
            start_of.insert(st, idx);
            heap.push(Entry { f: g0 + hh(st.0, st.1), ng: -g0, st });
        }
    }

    let mut done: FxHashSet<St> = FxHashSet::default();
    while let Some(Entry { ng, st, .. }) = heap.pop() {
        let gs = -ng;
        if done.contains(&st) || gs > *g.get(&st).unwrap_or(&f64::INFINITY) {
            continue;
        }
        done.insert(st);
        if done.len() > s.limit {
            return Ok(None);
        }
        let mut path: Option<Vec<St>> = None;
        for &i in targets {
            let hit = match sinks[i] {
                Sink::Fixed { x, y, edir } => {
                    (st.0, st.1) == (x, y) && st.2 != (edir + 2).rem_euclid(4) && (st.3 == 0 || st.2 == edir)
                }
                Sink::Tap { .. } => {
                    if sinks[i].h(st.0, st.1) > 0 {
                        false // too far for any tap: skip the path trace
                    } else {
                        let p = path.get_or_insert_with(|| trace(&parent, st));
                        let from = start_of[&p[0]];
                        tap_goal(i, p, from)?
                    }
                }
            };
            // the path's end: a belt or an exit its fed tile does not allow
            let hit = hit
                && s.lane_ok.get(&(st.0, st.1)).map_or(true, |m| m >> ((if st.3 != 0 { 8 } else { 0 }) + st.2) & 1 != 0);
            if hit {
                let p = path.get_or_insert_with(|| trace(&parent, st));
                let tiles: FxHashSet<T> = p.iter().map(|s| (s.0, s.1)).collect();
                let from = start_of[&p[0]];
                let crosses_spare = match start_spare.get(from) {
                    Some(Some(sp)) => tiles.contains(sp),
                    _ => false,
                };
                if tiles.len() == p.len() && !crosses_spare {
                    return Ok(Some((p.clone(), i, gs, from)));
                }
            }
        }
        let (x, y, d, ex) = st;
        if sink_tiles.contains(&(x, y)) && matches!(parent.get(&st), Some(Some(_))) {
            continue; // nothing continues through a port's link tile
        }
        let du = d as usize;
        let ax = (d % 2) as usize;
        let lok: Option<u16> = if s.lane_ok.is_empty() { None } else { s.lane_ok.get(&(x, y)).copied() };
        for nd in 0..4i64 {
            if ex != 0 && nd != d {
                continue;
            }
            if nd == (d + 2) % 4 {
                continue;
            }
            let ndu = nd as usize;
            let (nx, ny) = (x + DX[ndu], y + DY[ndu]);
            let step = s.belt + if nd != d { s.turn } else { 0.0 };
            let bit = if ex != 0 { 8 + d } else { nd };
            if !blocked((nx, ny)) && lok.map_or(true, |m| m >> bit & 1 != 0) {
                let ns = (nx, ny, nd, 0);
                let mut cost = gs + step;
                if !grid.soft.is_empty() {
                    cost += grid.soft.get(&(nx, ny)).copied().unwrap_or(0.0);
                }
                if cost < *g.get(&ns).unwrap_or(&f64::INFINITY) {
                    g.insert(ns, cost);
                    parent.insert(ns, Some(st));
                    heap.push(Entry { f: cost + hh(nx, ny), ng: -cost, st: ns });
                }
            }
            if ex != 0 || nd != d || s.tapped.contains(&(x, y)) || lok.map_or(false, |m| m >> (4 + d) & 1 == 0) {
                continue;
            }
            let mut seen_block = false;
            for j in 2..=s.max_ug {
                let (mx, my) = (x + DX[du] * (j - 1), y + DY[du] * (j - 1));
                if sink_tiles.contains(&(mx, my)) {
                    break;
                }
                if blocked((mx, my)) {
                    seen_block = true;
                }
                let (tx, ty) = (x + DX[du] * j, y + DY[du] * j);
                let crosses = (0..=j).any(|q| {
                    let t = (x + DX[du] * q, y + DY[du] * q);
                    grid.spans[ax].contains(&t) || s.tspans[ax].contains(&t)
                });
                if crosses {
                    break;
                }
                if seen_block && !blocked((tx, ty)) {
                    let ns = (tx, ty, d, 1);
                    let mut cost = gs + s.ug;
                    if !grid.soft.is_empty() {
                        cost += grid.soft.get(&(tx, ty)).copied().unwrap_or(0.0);
                    }
                    if cost < *g.get(&ns).unwrap_or(&f64::INFINITY) {
                        g.insert(ns, cost);
                        parent.insert(ns, Some(st));
                        heap.push(Entry { f: cost + hh(tx, ty), ng: -cost, st: ns });
                    }
                }
            }
        }
    }
    Ok(None)
}

pub(crate) fn to_sinks(sinks: Vec<(u8, i64, i64, i64, i64)>) -> Vec<Sink> {
    sinks
        .into_iter()
        .map(|(k, a, b, c, d)| {
            if k == 0 {
                Sink::Fixed { x: a, y: b, edir: c }
            } else {
                Sink::Tap { x0: a, y0: b, x1: c, y1: d }
            }
        })
        .collect()
}

/// One A* from every start state to the nearest target sink -> (path, sink index, cost) or None.
///
/// `extra`: the tree's own tiles, its reserved tiles and its spare tiles (blocked on top of the
/// grid). `starts`: (state, g0) in the Python order; `start_spare[i]`: the tile a path from start i
/// may not cross (laid reversed, a split's own spare output), or None. `sinks`: (0, x, y, edir, 0)
/// fixed or (1, x0, y0, x1, y1) tap. `tap_goal(i, path)`: the Python goal test of tap sink i.
#[pyfunction]
#[pyo3(signature = (grid, extra, tspan0, tspan1, starts, start_spare, sinks, targets, tapped,
                    belt, turn, ug, max_ug, limit, tap_goal, lane_ok=None))]
#[allow(clippy::too_many_arguments)]
pub(crate) fn astar<'py>(
    grid: &Bound<'py, NativeGrid>,
    extra: Vec<T>,
    tspan0: Vec<T>,
    tspan1: Vec<T>,
    starts: Vec<(St, f64)>,
    start_spare: Vec<Option<T>>,
    sinks: Vec<(u8, i64, i64, i64, i64)>,
    targets: Vec<usize>,
    tapped: Vec<T>,
    belt: f64,
    turn: f64,
    ug: f64,
    max_ug: i64,
    limit: usize,
    tap_goal: &Bound<'py, PyAny>,
    lane_ok: Option<Vec<(T, u16)>>,
) -> PyResult<Option<(Vec<St>, usize, f64)>> {
    let sinks = to_sinks(sinks);
    if targets.is_empty() || targets.iter().any(|&i| i >= sinks.len()) {
        return Err(pyo3::exceptions::PyValueError::new_err("targets: empty or out of range"));
    }
    let extra: FxHashSet<T> = extra.into_iter().collect();
    let tspans: [FxHashSet<T>; 2] = [tspan0.into_iter().collect(), tspan1.into_iter().collect()];
    let tapped: FxHashSet<T> = tapped.into_iter().collect();
    let lane_ok: FxHashMap<T, u16> = lane_ok.unwrap_or_default().into_iter().collect();
    let s = Search {
        grid: grid.get(), extra: &extra, tspans: &tspans, sinks: &sinks, targets: &targets,
        tapped: &tapped, lane_ok: &lane_ok, belt, turn, ug, max_ug, limit,
    };
    let got = search(&s, &starts, &start_spare, |i, p, _from| tap_goal.call1((i, p.to_vec()))?.is_truthy())?;
    Ok(got.map(|(p, i, gs, _from)| (p, i, gs)))
}
