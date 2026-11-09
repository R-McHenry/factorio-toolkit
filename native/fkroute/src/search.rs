//! One A*: steiner._astar_py step for step (the heap orders entries as Python's tuple
//! `(f, -g, state)` does, and costs are summed in the same order), with 3.0's tap goal native:
//! TapSink.pick (the tail `6 + 4(k-1)`, arms as data, inserter reach by name) and the taps a
//! state's own path has counted in the search key where a target wants k > 1 (Python's fifth
//! state element). A TapSink subclass (m2m's) keeps its Python goal as a callback.
use pyo3::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};
use std::cmp::Ordering;
use std::collections::BinaryHeap;

use crate::grid::NativeGrid;
use crate::{St, DX, DY, T};

/// A search key: the state and, near a sink that wants k > 1 taps, how many taps the state's
/// own path has (0 elsewhere, and everywhere when no target wants more than one).
pub(crate) type Sk = (i64, i64, i64, i64, i64);

/// An inserter kind the call names: its reach (tiles to its pickup and drop) and what a tap by
/// it costs. Python's tables (fkcore.arms.REACH, steiner.COSTS); the kernel keeps no name.
#[derive(Clone, Debug)]
pub(crate) struct Ins {
    pub(crate) name: String,
    pub(crate) reach: i64,
    pub(crate) cost: f64,
}

/// One of the force's vector pairs (fkcore.arms.pairs): pick and drop offsets from the
/// inserter's tile and the heading the inserter faces (its pickup).
#[derive(Clone, Debug)]
pub(crate) struct ArmPair {
    pub(crate) pick: T,
    pub(crate) drop: T,
    pub(crate) heading: i64,
}

/// A plain TapSink: the machine's rectangle, how many taps it wants, its inserters (into the
/// call's table), those of reach 1 (``short``), and the force's arms (range, pairs) or None.
#[derive(Clone, Debug)]
pub(crate) struct TapSpec {
    pub(crate) rect: (i64, i64, i64, i64),
    pub(crate) k: usize,
    pub(crate) inserters: Vec<usize>,
    pub(crate) short: Vec<usize>,
    pub(crate) arms: Option<(i64, Vec<ArmPair>)>,
}

impl TapSpec {
    #[inline]
    fn inside(&self, t: T) -> bool {
        let (x0, y0, x1, y1) = self.rect;
        x0 <= t.0 && t.0 < x1 && y0 <= t.1 && t.1 < y1
    }

    fn range(&self) -> i64 {
        self.arms.as_ref().map_or(0, |a| a.0)
    }
}

#[derive(Clone, Debug)]
pub(crate) enum Sink {
    /// A belt must arrive on the tile and leave it flowing ``edir`` (a port's link tile).
    Fixed { x: i64, y: i64, edir: i64 },
    /// A machine fed by k inserters off the net's belt: the goal runs here.
    Tap(TapSpec),
    /// A TapSink subclass (m2m's LeftTap, _EndTap): the goal is Python's, called back; ``range``
    /// its arms' range for the heuristic (0: none).
    TapCb { rect: (i64, i64, i64, i64), k: usize, range: i64 },
    /// A drill's drop tile: a belt of the net stands on it, any heading, and may run on through.
    Drop { x: i64, y: i64 },
}

/// A sink as Python passes it: (kind, a, b, c, d, k, inserters, arms); kind 0 fixed (x, y, edir),
/// 1 tap (the rectangle), 2 tap with a Python goal (the rectangle), 3 drop (x, y); ``arms``: the
/// range and the pairs (pick dx, dy, drop dx, dy, heading).
#[derive(FromPyObject)]
pub(crate) struct SinkIn(
    pub u8,
    pub i64,
    pub i64,
    pub i64,
    pub i64,
    pub usize,
    pub Vec<usize>,
    pub Option<(i64, Vec<(i64, i64, i64, i64, i64)>)>,
);

pub(crate) fn to_ins(rows: Vec<(String, i64, f64)>) -> Vec<Ins> {
    rows.into_iter().map(|(name, reach, cost)| Ins { name, reach, cost }).collect()
}

pub(crate) fn to_sinks(sinks: Vec<SinkIn>, ins: &[Ins]) -> PyResult<Vec<Sink>> {
    let mut out = Vec::with_capacity(sinks.len());
    for SinkIn(kind, a, b, c, d, k, inserters, arms) in sinks {
        out.push(match kind {
            0 => Sink::Fixed { x: a, y: b, edir: c },
            1 => {
                if inserters.iter().any(|&i| i >= ins.len()) {
                    return Err(pyo3::exceptions::PyValueError::new_err("sinks: an inserter index out of range"));
                }
                let short: Vec<usize> = inserters.iter().copied().filter(|&i| ins[i].reach == 1).collect();
                let arms = arms.map(|(range, pairs)| {
                    (range, pairs.into_iter()
                        .map(|(px, py, dx, dy, h)| ArmPair { pick: (px, py), drop: (dx, dy), heading: h })
                        .collect())
                });
                Sink::Tap(TapSpec { rect: (a, b, c, d), k, inserters, short, arms })
            }
            2 => Sink::TapCb { rect: (a, b, c, d), k, range: arms.map_or(0, |a| a.0) },
            3 => Sink::Drop { x: a, y: b },
            _ => return Err(pyo3::exceptions::PyValueError::new_err("sinks: unknown kind")),
        });
    }
    Ok(out)
}

#[inline]
fn rect_h(rect: (i64, i64, i64, i64), range: i64, x: i64, y: i64) -> i64 {
    let (x0, y0, x1, y1) = rect;
    let dx = (x0 - x).max(0).max(x - (x1 - 1));
    let dy = (y0 - y).max(0).max(y - (y1 - 1));
    // a long-handed tap reaches 3 tiles from the footprint; with vectors any short hand reaches
    // its range twice over (TapSink.h)
    (dx + dy - 3.max(2 * range - 1)).max(0)
}

impl Sink {
    #[inline]
    pub(crate) fn h(&self, x: i64, y: i64) -> i64 {
        match self {
            Sink::Fixed { x: tx, y: ty, .. } | Sink::Drop { x: tx, y: ty } => (x - tx).abs() + (y - ty).abs(),
            Sink::Tap(sp) => rect_h(sp.rect, sp.range(), x, y),
            Sink::TapCb { rect, range, .. } => rect_h(*rect, *range, x, y),
        }
    }

    /// FixedSink.terminal: a branch ends there; a tap or drop sink's end may go on.
    pub(crate) fn terminal(&self) -> bool {
        matches!(self, Sink::Fixed { .. })
    }

    /// The taps the sink wants (1 for a sink without taps: Python's ``getattr(s, "k", 1)``).
    pub(crate) fn k(&self) -> usize {
        match self {
            Sink::Tap(sp) => sp.k,
            Sink::TapCb { k, .. } => *k,
            _ => 1,
        }
    }

    pub(crate) fn tap(&self) -> Option<&TapSpec> {
        match self {
            Sink::Tap(sp) => Some(sp),
            _ => None,
        }
    }
}

/// A tap laid: the inserter's tile, the belt tile it picks from, its kind (into the table), its
/// direction (0, 4, 8, 12), its own vectors (pick, drop) if any, and its sink's name id.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub(crate) struct Tap {
    pub(crate) q: T,
    pub(crate) tile: T,
    pub(crate) ins: usize,
    pub(crate) dir: i64,
    pub(crate) arm: Option<(T, T)>,
    pub(crate) sink: usize,
}

/// The search's ground: the grid plus the tree's own tiles (its states, its splitters' halves,
/// its taps), its reserved tiles and its spare tiles.
pub(crate) struct Ground<'a> {
    pub(crate) grid: &'a NativeGrid,
    pub(crate) extra: &'a FxHashSet<T>,
}

impl Ground<'_> {
    #[inline]
    pub(crate) fn blocked(&self, t: T) -> bool {
        self.grid.blocked(t) || self.extra.contains(&t)
    }

    /// Tree.free: nothing stands there, nothing is reserved or spare there, and no other net holds
    /// it (a negotiated soft tile takes a belt step, never an inserter or a splitter).
    #[inline]
    pub(crate) fn free(&self, t: T) -> bool {
        !self.blocked(t) && !self.grid.soft.contains_key(&t)
    }
}

/// TapSink.taps_at's first tap from a belt on ``tile``: the plain straight ones (every inserter
/// of the sink, or the short ones when the force has arms), then a short hand with the force's
/// vectors, then a long hand two out. ``ok(q)``: may the inserter stand on q.
fn first_tap_at(ins: &[Ins], sp: &TapSpec, tile: T, ok: impl Fn(T) -> bool) -> Option<(T, usize, i64, Option<(T, T)>)> {
    let names: &[usize] = if sp.arms.is_none() { &sp.inserters } else { &sp.short };
    for h in 0..4usize {
        for &nm in names {
            let r = ins[nm].reach;
            let q = (tile.0 + DX[h] * r, tile.1 + DY[h] * r);
            if ok(q) && sp.inside((q.0 + DX[h] * r, q.1 + DY[h] * r)) {
                return Some((q, nm, (((h + 2) % 4) * 4) as i64, None));
            }
        }
    }
    let (_range, pairs) = sp.arms.as_ref()?;
    if let Some(&s0) = sp.short.first() {
        for p in pairs {
            let q = (tile.0 - p.pick.0, tile.1 - p.pick.1);
            if ok(q) && sp.inside((q.0 + p.drop.0, q.1 + p.drop.1)) {
                return Some((q, s0, p.heading, Some((p.pick, p.drop))));
            }
        }
    }
    for &nm in &sp.inserters {
        if sp.short.contains(&nm) {
            continue;
        }
        for h in 0..4usize {
            let q = (tile.0 + DX[h] * 2, tile.1 + DY[h] * 2);
            if ok(q) && sp.inside((q.0 + DX[h] * 2, q.1 + DY[h] * 2)) {
                return Some((q, nm, (((h + 2) % 4) * 4) as i64, None));
            }
        }
    }
    None
}

/// TapSink.pick: taps off the last tiles of ``path`` (one per belt tile, newest first, a tail of
/// `6 + 4(k-1)` tiles), up to k; none on the path, on another tap of this pick, or on ``taken``.
pub(crate) fn pick(ins: &[Ins], g: &Ground, sp: &TapSpec, path: &[St], taken: &[T], sink: usize) -> Vec<Tap> {
    let on: FxHashSet<T> = path.iter().map(|s| (s.0, s.1)).collect();
    let tail = 6 + 4 * (sp.k as i64 - 1);
    let lo = path.len().saturating_sub(tail.max(0) as usize);
    let mut got: Vec<Tap> = Vec::new();
    for s in path[lo..].iter().rev() {
        let tile = (s.0, s.1);
        let ok = |q: T| g.free(q) && !on.contains(&q) && !got.iter().any(|t| t.q == q) && !taken.contains(&q);
        if let Some((q, nm, dir, arm)) = first_tap_at(ins, sp, tile, ok) {
            got.push(Tap { q, tile, ins: nm, dir, arm, sink });
        }
        if got.len() >= sp.k {
            break;
        }
    }
    got
}

struct Entry {
    f: f64,
    ng: f64,
    st: Sk,
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

pub(crate) fn trace(parent: &FxHashMap<Sk, Option<Sk>>, st: Sk) -> Vec<Sk> {
    let mut out = vec![st];
    while let Some(Some(p)) = parent.get(out.last().unwrap()) {
        out.push(*p);
    }
    out.reverse();
    out
}

#[inline]
fn st4(k: Sk) -> St {
    (k.0, k.1, k.2, k.3)
}

/// The search's fixed inputs: the ground, the tree's tunnels, the sinks and the costs.
pub(crate) struct Search<'a> {
    pub(crate) ground: Ground<'a>,
    pub(crate) tspans: &'a [FxHashSet<T>; 2],
    pub(crate) sinks: &'a [Sink],
    pub(crate) ins: &'a [Ins],
    pub(crate) targets: &'a [usize],
    pub(crate) tapped: &'a FxHashSet<T>,
    pub(crate) lane_ok: &'a FxHashMap<T, u16>, // PLAN-LANES: a fed tile's allowed carriers (lanephys.tile_mask)
    pub(crate) drop_taps: bool,
    pub(crate) belt: f64,
    pub(crate) turn: f64,
    pub(crate) ug: f64,
    pub(crate) max_ug: i64,
    pub(crate) limit: usize,
}

/// The search key of a state reached from ``prev`` (Python's ``key``): near a target that wants
/// k > 1 taps, the taps the state's own path would lay (up to k), else the count carried along.
fn key(s: &Search, multi: &[usize], parent: &FxHashMap<Sk, Option<Sk>>, prev: Option<Sk>, st: St) -> Sk {
    let (x, y, d, ex) = st;
    if multi.is_empty() {
        return (x, y, d, ex, 0);
    }
    if multi.iter().all(|&i| s.sinks[i].h(x, y) > 0) {
        return (x, y, d, ex, prev.map_or(0, |p| p.4));
    }
    let mut path: Vec<St> = match prev {
        Some(p) => trace(parent, p).into_iter().map(st4).collect(),
        None => Vec::new(),
    };
    path.push(st);
    let n = multi
        .iter()
        .map(|&i| {
            let sp = s.sinks[i].tap().unwrap();
            pick(s.ins, &s.ground, sp, &path, &[], i).len().min(sp.k)
        })
        .max()
        .unwrap();
    (x, y, d, ex, n as i64)
}

/// steiner._astar_py, step for step -> (path, sink index, cost, the start the path left from).
/// ``start_spare[i]``: the tile a path from start i may not cross; ``start_taken[i]``: the tiles
/// its move lays, where no tap goes. ``tap_cb(i, path, start)``: the Python goal of a TapCb sink.
pub(crate) fn search<F>(
    s: &Search,
    starts: &[(St, f64)],
    start_spare: &[Option<T>],
    start_taken: &[Vec<T>],
    mut tap_cb: F,
) -> PyResult<Option<(Vec<St>, usize, f64, usize)>>
where
    F: FnMut(usize, &[St], usize) -> PyResult<bool>,
{
    let (sinks, targets, g_) = (s.sinks, s.targets, &s.ground);
    let grid = g_.grid;
    let sink_tiles: FxHashSet<T> = sinks
        .iter()
        .filter_map(|s| match *s {
            Sink::Fixed { x, y, .. } => Some((x, y)),
            _ => None,
        })
        .collect();
    let hh = |x: i64, y: i64| -> f64 { targets.iter().map(|&i| sinks[i].h(x, y)).min().unwrap() as f64 };
    // 3.0: a target that wants k > 1 taps needs a path that passes k tap tiles, which costs more
    // than the straight path to the same state: near it a state carries how many taps its own
    // path has, so the costlier path isn't dropped
    let multi: Vec<usize> = targets.iter().copied().filter(|&i| sinks[i].k() > 1).collect();
    if multi.iter().any(|&i| sinks[i].tap().is_none()) {
        return Err(pyo3::exceptions::PyValueError::new_err("a sink with a Python goal wants k > 1 taps"));
    }
    let no_taken: Vec<T> = Vec::new();
    let taken_of = |from: usize| -> &[T] { start_taken.get(from).map_or(&no_taken[..], |v| &v[..]) };

    let mut heap: BinaryHeap<Entry> = BinaryHeap::new();
    let mut g: FxHashMap<Sk, f64> = FxHashMap::default();
    let mut parent: FxHashMap<Sk, Option<Sk>> = FxHashMap::default();
    let mut start_of: FxHashMap<Sk, usize> = FxHashMap::default();
    for (idx, &(st, g0)) in starts.iter().enumerate() {
        let k = key(s, &multi, &parent, None, st); // a start has no path behind it
        if g0 < *g.get(&k).unwrap_or(&f64::INFINITY) {
            g.insert(k, g0);
            parent.insert(k, None);
            start_of.insert(k, idx);
            heap.push(Entry { f: g0 + hh(st.0, st.1), ng: -g0, st: k });
        }
    }

    let mut done: FxHashSet<Sk> = FxHashSet::default();
    while let Some(Entry { ng, st, .. }) = heap.pop() {
        let gs = -ng;
        if done.contains(&st) || gs > *g.get(&st).unwrap_or(&f64::INFINITY) {
            continue;
        }
        done.insert(st);
        if done.len() > s.limit {
            return Ok(None);
        }
        let here = st4(st);
        let mut keys: Option<Vec<Sk>> = None;
        let mut path: Option<Vec<St>> = None;
        for &i in targets {
            let hit = match &sinks[i] {
                Sink::Fixed { x, y, edir } => {
                    (here.0, here.1) == (*x, *y) && here.2 != (edir + 2).rem_euclid(4) && (here.3 == 0 || here.2 == *edir)
                }
                Sink::Drop { x, y } => (here.0, here.1) == (*x, *y),
                Sink::Tap(_) | Sink::TapCb { .. } => {
                    if sinks[i].h(here.0, here.1) > 0 {
                        false // too far for any tap: skip the path trace
                    } else {
                        let ks = keys.get_or_insert_with(|| trace(&parent, st));
                        let p = path.get_or_insert_with(|| ks.iter().map(|k| st4(*k)).collect());
                        let from = start_of[&ks[0]];
                        match &sinks[i] {
                            Sink::Tap(sp) => {
                                // TapSink.goal: an exit can't turn (unless laid reversed), then
                                // enough taps
                                let du = here.2 as usize;
                                if here.3 != 0 && !s.drop_taps && grid.blocked((here.0 + DX[du], here.1 + DY[du])) {
                                    false
                                } else {
                                    pick(s.ins, g_, sp, p, taken_of(from), i).len() >= sp.k
                                }
                            }
                            _ => tap_cb(i, p, from)?,
                        }
                    }
                }
            };
            // the path's end: a belt or an exit its fed tile does not allow
            let hit = hit
                && s.lane_ok.get(&(here.0, here.1)).map_or(true, |m| m >> ((if here.3 != 0 { 8 } else { 0 }) + here.2) & 1 != 0);
            if hit {
                let ks = keys.get_or_insert_with(|| trace(&parent, st));
                let p = path.get_or_insert_with(|| ks.iter().map(|k| st4(*k)).collect());
                let tiles: FxHashSet<T> = p.iter().map(|s| (s.0, s.1)).collect();
                let from = start_of[&ks[0]];
                let crosses_spare = match start_spare.get(from) {
                    Some(Some(sp)) => tiles.contains(sp),
                    _ => false,
                };
                if tiles.len() == p.len() && !crosses_spare {
                    return Ok(Some((p.clone(), i, gs, from)));
                }
            }
        }
        let (x, y, d, ex) = here;
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
            if !g_.blocked((nx, ny)) && lok.map_or(true, |m| m >> bit & 1 != 0) {
                let ns = key(s, &multi, &parent, Some(st), (nx, ny, nd, 0));
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
                if g_.blocked((mx, my)) {
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
                if seen_block && !g_.blocked((tx, ty)) {
                    let ns = key(s, &multi, &parent, Some(st), (tx, ty, d, 1));
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

/// One A* from every start state to the nearest target sink -> (path, sink index, cost) or None.
///
/// `extra`: the tree's own tiles, its reserved tiles and its spare tiles (blocked on top of the
/// grid). `starts`: (state, g0) in the Python order; `start_spare[i]`: the tile a path from start i
/// may not cross (laid reversed, a split's own spare output), or None; `start_taken[i]`: the tiles
/// start i's move lays (a splitter's), where no tap goes. `sinks`: see `SinkIn`; `inserters`: the
/// table their inserter indices point into, (name, reach, tap cost). `tap_goal(i, path)`: the
/// Python goal test of a kind-2 sink.
#[pyfunction]
#[pyo3(signature = (grid, extra, tspan0, tspan1, starts, start_spare, start_taken, sinks, inserters,
                    targets, tapped, drop_taps, belt, turn, ug, max_ug, limit, tap_goal, lane_ok=None))]
#[allow(clippy::too_many_arguments)]
pub(crate) fn astar<'py>(
    grid: &Bound<'py, NativeGrid>,
    extra: Vec<T>,
    tspan0: Vec<T>,
    tspan1: Vec<T>,
    starts: Vec<(St, f64)>,
    start_spare: Vec<Option<T>>,
    start_taken: Vec<Vec<T>>,
    sinks: Vec<SinkIn>,
    inserters: Vec<(String, i64, f64)>,
    targets: Vec<usize>,
    tapped: Vec<T>,
    drop_taps: bool,
    belt: f64,
    turn: f64,
    ug: f64,
    max_ug: i64,
    limit: usize,
    tap_goal: &Bound<'py, PyAny>,
    lane_ok: Option<Vec<(T, u16)>>,
) -> PyResult<Option<(Vec<St>, usize, f64)>> {
    let ins = to_ins(inserters);
    let sinks = to_sinks(sinks, &ins)?;
    if targets.is_empty() || targets.iter().any(|&i| i >= sinks.len()) {
        return Err(pyo3::exceptions::PyValueError::new_err("targets: empty or out of range"));
    }
    let extra: FxHashSet<T> = extra.into_iter().collect();
    let tspans: [FxHashSet<T>; 2] = [tspan0.into_iter().collect(), tspan1.into_iter().collect()];
    let tapped: FxHashSet<T> = tapped.into_iter().collect();
    let lane_ok: FxHashMap<T, u16> = lane_ok.unwrap_or_default().into_iter().collect();
    let s = Search {
        ground: Ground { grid: grid.get(), extra: &extra }, tspans: &tspans, sinks: &sinks, ins: &ins,
        targets: &targets, tapped: &tapped, lane_ok: &lane_ok, drop_taps, belt, turn, ug, max_ug, limit,
    };
    let got = search(&s, &starts, &start_spare, &start_taken, |i, p, _from| {
        tap_goal.call1((i, p.to_vec()))?.is_truthy()
    })?;
    Ok(got.map(|(p, i, gs, _from)| (p, i, gs)))
}
