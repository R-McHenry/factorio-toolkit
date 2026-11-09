//! The lane-state search: fkcore.lanesearch._leg_py, step for step (PLAN-4.0 N1).
//!
//! A state is (x, y, h, ex, L, R): steiner's belt state and what the belt's two lanes hold, as
//! small ids. No lane rule lives here: the moves are `physics::table()`'s (the lane physics
//! taken once at import), and every entry into a tree's or a host's belt comes precomputed from
//! Python with the move kind the table gives it. The heap orders entries as Python's `(f, -g, state)`
//! tuple does and costs are summed in the same order, so the kernel returns the same path.
use pyo3::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};
use std::cmp::Ordering;
use std::collections::BinaryHeap;

use crate::grid::NativeGrid;
use crate::physics::{self, Physics};
use crate::{DX, DY};

type T = (i64, i64);
type St = (i64, i64, i64, i64, i64, i64); // x, y, heading, exited an underground, L, R

const EMPTY: i64 = 0;
// the move codes (lanesearch.STEP ..)
const STEP: i64 = 0;
const JUMP: i64 = 1;
const STUB: i64 = 2;
const ENTER: i64 = 3;
const RIDE: i64 = 4;
const LEAVE: i64 = 5;
const ATTACH: i64 = 6;
const VIA_SIDE: i64 = 4; // lanephys.VIAS.index("side")
const VIA_STRAIGHT: i64 = 0;

struct Entry {
    hn: i64,
    ex: i64,
    via: i64,
    ug: i64,
    content: (i64, i64),
    ok: i64,
    kind: i64, // 0 the tree (an attachment), 1 a host (a ride begins)
}

struct Hop {
    next: T,
    via: i64,
    hn: i64,
    ug: i64,
    ex: i64,
    content: (i64, i64),
}

enum Goal {
    Fixed { x: i64, y: i64, edir: i64, need: (i64, i64) },
    Tap { x0: i64, y0: i64, x1: i64, y1: i64 },
}

impl Goal {
    #[inline]
    fn h(&self, x: i64, y: i64) -> i64 {
        match *self {
            Goal::Fixed { x: tx, y: ty, .. } => (x - tx).abs() + (y - ty).abs(),
            Goal::Tap { x0, y0, x1, y1 } => {
                let dx = (x0 - x).max(0).max(x - (x1 - 1));
                let dy = (y0 - y).max(0).max(y - (y1 - 1));
                (dx + dy - 3).max(0)
            }
        }
    }
}

struct HeapEntry {
    f: f64,
    ng: f64,
    st: St,
}

impl PartialEq for HeapEntry {
    fn eq(&self, o: &Self) -> bool {
        self.cmp(o) == Ordering::Equal
    }
}
impl Eq for HeapEntry {}
impl PartialOrd for HeapEntry {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for HeapEntry {
    // BinaryHeap pops the largest: reverse Python's min-heap order on (f, -g, state).
    fn cmp(&self, o: &Self) -> Ordering {
        o.f.partial_cmp(&self.f)
            .unwrap_or(Ordering::Equal)
            .then_with(|| o.ng.partial_cmp(&self.ng).unwrap_or(Ordering::Equal))
            .then_with(|| o.st.cmp(&self.st))
    }
}

/// lanesearch.lanes_ok: does a belt holding (L, R) meet `need` for net `me` (-1 ANY, -2
/// PENDING: the net itself or nothing yet).
#[inline]
fn lanes_ok(need: (i64, i64), l: i64, r: i64, me: i64) -> bool {
    for (n, have) in [(need.0, l), (need.1, r)] {
        if n == -1 {
            continue;
        }
        if n == EMPTY {
            if have != EMPTY {
                return false;
            }
        } else if n == me {
            if have != me {
                return false;
            }
        } else if n == -2 {
            if have != EMPTY && have != me {
                return false;
            }
        } else if have != EMPTY && have != n {
            return false;
        }
    }
    true
}

struct Lane<'a> {
    grid: &'a NativeGrid,
    extra: FxHashSet<T>,
    tspans: [FxHashSet<T>; 2],
    entries: FxHashMap<(T, i64), Entry>,
    hops: FxHashMap<T, Vec<Hop>>, // every host tile, a chain's end with no hop
    leaves: FxHashMap<T, T>,
    goals: Vec<Goal>,
    attach: FxHashSet<T>,
    no_turn: FxHashSet<St>,
    taken: FxHashSet<T>, // tiles the net rides already: a forward leg does not ride into them
    me: i64,
    phys: &'static Physics,
    belt: f64,
    turn: f64,
    ug: f64,
    ride: f64,
    max_ug: i64,
    hscale: f64,
}

impl Lane<'_> {
    /// _Spec.merge: (L, R) after a feed holding `lanes` enters a carrier holding `content` by
    /// move `via`; None where a lane would hold two ids or the net's own items land nowhere.
    fn merge(&self, via: i64, src: i64, dst: i64, ug: i64, lanes: (i64, i64), content: (i64, i64)) -> Option<(i64, i64)> {
        let mv = self.phys.moves(via as usize, src as u8, dst as u8, ug == 1)?;
        let mut out = [content.0, content.1];
        let mut mine = false;
        for &(a, b, _rank) in &mv.edges {
            let v = if a == 0 { lanes.0 } else { lanes.1 };
            if v == EMPTY {
                continue;
            }
            let slot = out[b as usize];
            if slot != EMPTY && slot != v {
                return None;
            }
            out[b as usize] = v;
            if v == self.me {
                mine = true;
            }
        }
        if mine { Some((out[0], out[1])) } else { None }
    }

    #[inline]
    fn blocked(&self, t: T) -> bool {
        self.grid.blocked(t) || self.extra.contains(&t)
    }
}

fn trace(parent: &FxHashMap<St, Option<(St, i64)>>, mut st: St) -> Vec<(St, i64)> {
    let mut out = Vec::new();
    loop {
        match parent.get(&st) {
            Some(Some((p, how))) => {
                out.push((st, *how));
                st = *p;
            }
            _ => {
                out.push((st, -1));
                break;
            }
        }
    }
    out.reverse();
    out
}

#[inline]
fn push(
    heap: &mut BinaryHeap<HeapEntry>,
    g: &mut FxHashMap<St, f64>,
    parent: &mut FxHashMap<St, Option<(St, i64)>>,
    st: St,
    prev: St,
    how: i64,
    cost: f64,
    h: f64,
) {
    if cost < *g.get(&st).unwrap_or(&f64::INFINITY) {
        g.insert(st, cost);
        parent.insert(st, Some((prev, how)));
        heap.push(HeapEntry { f: cost + h, ng: -cost, st });
    }
}

/// One A* of the lane-state search (lanesearch._leg_py) -> ([(state, move)], goal index or -1
/// for an attachment, cost) or None.
///
/// `entries`: (tile, src heading, hn, ex, via, ug, L, R, down_ok bits, kind); `host_tiles`:
/// every host's tile (a state there rides); `hops`: (tile, next, via, hn, ug, ex, L, R); `leaves`: (the free tile a host chain ends into, the chain's
/// end); `goals`: (0, x, y, edir, needL, needR) fixed or (1, x0, y0, x1, y1, 0) tap;
/// `no_turn`: start states that may not turn on their first step (a drop root: its lane
/// depends on its heading); `taken`: tiles no hop may ride into; `costs`: (belt, turn, ug,
/// ride, max_ug, the heuristic's price of a tile); `tap_goal(i, path)`: the Python tap goal
/// test. The moves are `physics::table()`'s: `fkroute.physics` must have run.
#[pyfunction]
#[pyo3(signature = (grid, extra, tspan0, tspan1, starts, entries, host_tiles, hops, leaves, goals,
                    targets, attach, no_turn, taken, me, costs, limit, tap_goal))]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn lane_astar<'py>(
    grid: &Bound<'py, NativeGrid>,
    extra: Vec<T>,
    tspan0: Vec<T>,
    tspan1: Vec<T>,
    starts: Vec<(St, f64)>,
    entries: Vec<(T, i64, i64, i64, i64, i64, i64, i64, i64, i64)>,
    host_tiles: Vec<T>,
    hops: Vec<(T, T, i64, i64, i64, i64, i64, i64)>,
    leaves: Vec<(T, T)>,
    goals: Vec<(u8, i64, i64, i64, i64, i64)>,
    targets: Vec<usize>,
    attach: Vec<T>,
    no_turn: Vec<St>,
    taken: Vec<T>,
    me: i64,
    costs: (f64, f64, f64, f64, i64, f64),
    limit: usize,
    tap_goal: &Bound<'py, PyAny>,
) -> PyResult<Option<(Vec<(St, i64)>, i64, f64)>> {
    let goals: Vec<Goal> = goals
        .into_iter()
        .map(|(k, a, b, c, d, e)| {
            if k == 0 {
                Goal::Fixed { x: a, y: b, edir: c, need: (d, e) }
            } else {
                Goal::Tap { x0: a, y0: b, x1: c, y1: d }
            }
        })
        .collect();
    if targets.iter().any(|&i| i >= goals.len()) {
        return Err(pyo3::exceptions::PyValueError::new_err("targets: out of range"));
    }
    let phys = physics::table()
        .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("lane_astar: fkroute.physics has not taken the table"))?;
    let mut hop_map: FxHashMap<T, Vec<Hop>> = FxHashMap::default();
    for t in host_tiles {
        hop_map.entry(t).or_default();
    }
    for (t, next, via, hn, ug, ex, l, r) in hops {
        hop_map.entry(t).or_default().push(Hop { next, via, hn, ug, ex, content: (l, r) });
    }
    let (belt, turn, ug, ride, max_ug, hscale) = costs;
    let s = Lane {
        grid: grid.get(),
        extra: extra.into_iter().collect(),
        tspans: [tspan0.into_iter().collect(), tspan1.into_iter().collect()],
        entries: entries
            .into_iter()
            .map(|(t, src, hn, ex, via, ug, l, r, ok, kind)| ((t, src), Entry { hn, ex, via, ug, content: (l, r), ok, kind }))
            .collect(),
        hops: hop_map,
        leaves: leaves.into_iter().collect(),
        goals,
        attach: attach.into_iter().collect(),
        no_turn: no_turn.into_iter().collect(),
        taken: taken.into_iter().collect(),
        me,
        phys,
        belt,
        turn,
        ug,
        ride,
        max_ug,
        hscale,
    };
    let mut entry_tiles: Vec<T> = s.entries.iter().filter(|(_, e)| e.kind == 0).map(|((t, _), _)| *t).collect();
    entry_tiles.sort();
    entry_tiles.dedup();
    let fixed_tiles: FxHashSet<T> = s
        .goals
        .iter()
        .filter_map(|g| match *g {
            Goal::Fixed { x, y, .. } => Some((x, y)),
            _ => None,
        })
        .collect();
    let hh = |x: i64, y: i64| -> f64 {
        let mut best = i64::MAX;
        for &i in &targets {
            best = best.min(s.goals[i].h(x, y));
        }
        for t in &entry_tiles {
            best = best.min((x - t.0).abs() + (y - t.1).abs());
        }
        if best == i64::MAX { 0.0 } else { best as f64 * s.hscale }
    };
    let soft = !s.grid.soft.is_empty();
    let soft_at = |t: T| -> f64 { if soft { s.grid.soft.get(&t).copied().unwrap_or(0.0) } else { 0.0 } };

    let mut heap: BinaryHeap<HeapEntry> = BinaryHeap::new();
    let mut g: FxHashMap<St, f64> = FxHashMap::default();
    let mut parent: FxHashMap<St, Option<(St, i64)>> = FxHashMap::default();
    for &(st, g0) in &starts {
        if g0 < *g.get(&st).unwrap_or(&f64::INFINITY) {
            g.insert(st, g0);
            parent.insert(st, None);
            heap.push(HeapEntry { f: g0 + hh(st.0, st.1), ng: -g0, st });
        }
    }
    let mut done: FxHashSet<St> = FxHashSet::default();
    while let Some(HeapEntry { ng, st, .. }) = heap.pop() {
        let gs = -ng;
        if done.contains(&st) || gs > *g.get(&st).unwrap_or(&f64::INFINITY) {
            continue;
        }
        done.insert(st);
        if done.len() > limit {
            return Ok(None);
        }
        let (x, y, d, ex, l, r) = st;
        if s.attach.contains(&(x, y)) {
            return Ok(Some((trace(&parent, st), -1, gs)));
        }
        let came = match parent.get(&st) {
            Some(Some((_, how))) => *how,
            _ => -1,
        };
        let mut path: Option<Vec<(St, i64)>> = None;
        for &i in &targets {
            let hit = match s.goals[i] {
                Goal::Fixed { x: tx, y: ty, edir, need } => {
                    (x, y) == (tx, ty)
                        && d != (edir + 2).rem_euclid(4)
                        && (ex == 0 || d == edir)
                        && (came != STUB || d == edir)
                        && lanes_ok(need, l, r, me)
                }
                Goal::Tap { .. } => {
                    if s.goals[i].h(x, y) > 0 {
                        false
                    } else {
                        let p = path.get_or_insert_with(|| trace(&parent, st));
                        let states: Vec<St> = p.iter().map(|(q, _)| *q).collect();
                        tap_goal.call1((i, states))?.is_truthy()?
                    }
                }
            };
            if hit {
                let p = path.get_or_insert_with(|| trace(&parent, st));
                // no two pieces on one tile: the states' tiles and the stubs' behind them
                let mut tiles: Vec<T> = p.iter().map(|(q, _)| (q.0, q.1)).collect();
                for (q, how) in p.iter() {
                    if *how == STUB {
                        let hu = q.2 as usize;
                        tiles.push((q.0 - DX[hu], q.1 - DY[hu]));
                    }
                }
                let n = tiles.len();
                let set: FxHashSet<T> = tiles.into_iter().collect();
                if set.len() == n {
                    return Ok(Some((p.clone(), i as i64, gs)));
                }
            }
        }
        let riding = s.hops.contains_key(&(x, y));
        if riding && !s.hops[&(x, y)].is_empty() {
            for hop in &s.hops[&(x, y)] {
                if s.taken.contains(&hop.next) {
                    continue;
                }
                if let Some(lanes) = s.merge(hop.via, d, hop.hn, hop.ug, (l, r), hop.content) {
                    let ns = (hop.next.0, hop.next.1, hop.hn, hop.ex, lanes.0, lanes.1);
                    let h = hh(ns.0, ns.1);
                    push(&mut heap, &mut g, &mut parent, ns, st, RIDE, gs + s.ride, h);
                }
            }
            continue;
        }
        if riding {
            if (l != EMPTY && l != me) || (r != EMPTY && r != me) {
                continue; // passengers aboard: the ride ends here
            }
            let du = d as usize;
            let n = (x + DX[du], y + DY[du]);
            if s.leaves.get(&n) == Some(&(x, y)) {
                let cost = gs + s.belt + soft_at(n);
                let ns = (n.0, n.1, d, 0, l, r);
                let h = hh(ns.0, ns.1);
                push(&mut heap, &mut g, &mut parent, ns, st, LEAVE, cost, h);
            }
            continue;
        }
        if fixed_tiles.contains(&(x, y)) && matches!(parent.get(&st), Some(Some(_))) {
            continue; // nothing continues through a port's link tile
        }
        let du = d as usize;
        // an exit runs straight on; so does a drop root and a belt a stub side-loads
        let fixed_heading = ex != 0 || came == STUB || s.no_turn.contains(&st);
        for nd in 0..4i64 {
            if fixed_heading && nd != d {
                continue;
            }
            if nd == (d + 2) % 4 {
                continue;
            }
            let ndu = nd as usize;
            let n = (x + DX[ndu], y + DY[ndu]);
            if let Some(e) = s.entries.get(&(n, nd)) {
                if let Some(lanes) = s.merge(e.via, nd, e.hn, e.ug, (l, r), e.content) {
                    let arr = [lanes.0, lanes.1];
                    let had = [e.content.0, e.content.1];
                    let ok = (0..2).all(|ln| !(arr[ln] == me && had[ln] != me) || (e.ok >> ln) & 1 != 0);
                    if ok {
                        let cost = gs + if e.kind == 0 { 0.0 } else { s.ride };
                        let ns = (n.0, n.1, e.hn, e.ex, lanes.0, lanes.1);
                        let h = hh(ns.0, ns.1);
                        push(&mut heap, &mut g, &mut parent, ns, st, if e.kind == 0 { ATTACH } else { ENTER }, cost, h);
                    }
                }
            } else if !s.blocked(n) {
                let step = s.belt + if nd != d { s.turn } else { 0.0 };
                let cost = gs + step + soft_at(n);
                let ns = (n.0, n.1, nd, 0, l, r);
                let h = hh(ns.0, ns.1);
                push(&mut heap, &mut g, &mut parent, ns, st, STEP, cost, h);
                for hn in [(nd + 1) % 4, (nd + 3) % 4] {
                    let hu = hn as usize;
                    let b = (n.0 - DX[hu], n.1 - DY[hu]);
                    if s.blocked(b) || fixed_tiles.contains(&b) {
                        continue;
                    }
                    if let Some(lanes) = s.merge(VIA_SIDE, nd, hn, 1, (l, r), (EMPTY, EMPTY)) {
                        let mut cost = gs + 2.0 * s.belt;
                        if soft {
                            cost += soft_at(n);
                            cost += soft_at(b);
                        }
                        let ns = (n.0, n.1, hn, 0, lanes.0, lanes.1);
                        let h = hh(ns.0, ns.1);
                        push(&mut heap, &mut g, &mut parent, ns, st, STUB, cost, h);
                    }
                }
            }
            if ex != 0 || nd != d {
                continue;
            }
            let ax = (d % 2) as usize;
            let mut seen_block = false;
            for j in 2..=s.max_ug {
                let m = (x + DX[du] * (j - 1), y + DY[du] * (j - 1));
                if fixed_tiles.contains(&m) {
                    break;
                }
                if s.blocked(m) {
                    seen_block = true;
                }
                let t = (x + DX[du] * j, y + DY[du] * j);
                let crosses = (0..=j).any(|q| {
                    let u = (x + DX[du] * q, y + DY[du] * q);
                    s.grid.spans[ax].contains(&u) || s.tspans[ax].contains(&u)
                });
                if crosses {
                    break;
                }
                if seen_block && !s.blocked(t) {
                    let cost = gs + s.ug + soft_at(t);
                    let ns = (t.0, t.1, d, 1, l, r);
                    let h = hh(ns.0, ns.1);
                    push(&mut heap, &mut g, &mut parent, ns, st, JUMP, cost, h);
                }
            }
        }
    }
    let _ = VIA_STRAIGHT;
    Ok(None)
}
