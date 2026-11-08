//! fkroute: native kernels for fkcore's router.
//!
//! `astar` is fkcore.steiner._astar, step for step. The heap orders entries as Python's tuple
//! `(f, -g, state)` does, and costs are summed in the same order, so it pops the same states and
//! returns the same path.
use pyo3::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};
use std::cmp::Ordering;
use std::cmp::Reverse;
use std::collections::BinaryHeap;
use std::sync::OnceLock;

type St = (i64, i64, i64, i64); // x, y, heading 0..3 = N E S W, just exited an underground
type T = (i64, i64);

const DX: [i64; 4] = [0, 1, 0, -1];
const DY: [i64; 4] = [-1, 0, 1, 0];

/// A steiner.Grid: blocked tiles (occ, plus fronts for a plain Grid), the hidden spans of the
/// foreign undergrounds per axis, and for a bounded grid the box outside which all is blocked.
/// Built once per Grid and cached on it.
#[pyclass(frozen, module = "fkroute")]
pub struct NativeGrid {
    occ: FxHashSet<T>,
    spans: [FxHashSet<T>; 2],
    bbox: Option<(i64, i64, i64, i64)>,
    dense: OnceLock<Vec<bool>>, // a bounded grid's blocked tiles as a bitmap over its box
    soft: FxHashMap<T, f64>,    // negotiated: the extra cost of a step onto a tile another net holds
}

#[pymethods]
impl NativeGrid {
    #[new]
    #[pyo3(signature = (blocked, span0, span1, bbox=None, soft=None))]
    fn new(blocked: Vec<T>, span0: Vec<T>, span1: Vec<T>, bbox: Option<(i64, i64, i64, i64)>,
           soft: Option<Vec<(T, f64)>>) -> Self {
        NativeGrid {
            occ: blocked.into_iter().collect(),
            spans: [span0.into_iter().collect(), span1.into_iter().collect()],
            bbox,
            dense: OnceLock::new(),
            soft: soft.unwrap_or_default().into_iter().collect(),
        }
    }
}

impl NativeGrid {
    #[inline]
    fn blocked(&self, t: T) -> bool {
        if let Some((x0, y0, x1, y1)) = self.bbox {
            if !(x0 <= t.0 && t.0 < x1 && y0 <= t.1 && t.1 < y1) {
                return true;
            }
        }
        self.occ.contains(&t)
    }

    fn dense(&self) -> &Vec<bool> {
        self.dense.get_or_init(|| {
            let (x0, y0, x1, y1) = self.bbox.unwrap();
            let (w, h) = ((x1 - x0).max(0), (y1 - y0).max(0));
            let mut out = vec![false; (w * h) as usize];
            for &(x, y) in &self.occ {
                if x0 <= x && x < x1 && y0 <= y && y < y1 {
                    out[((y - y0) * w + (x - x0)) as usize] = true;
                }
            }
            out
        })
    }
}

// -- the walk: route._walk ----------------------------------------------------------------------
/// Belt distances from a set of seeds over a bounded grid: dense over the box, plus the seeds
/// outside it; ``order`` is the order tiles were first reached (the Python dict's order).
struct Walk {
    x0: i64,
    y0: i64,
    x1: i64,
    y1: i64,
    dist: Vec<i64>,
    side: FxHashMap<T, i64>,
    order: Vec<T>,
}

impl Walk {
    #[inline]
    fn idx(&self, t: T) -> Option<usize> {
        if self.x0 <= t.0 && t.0 < self.x1 && self.y0 <= t.1 && t.1 < self.y1 {
            Some(((t.1 - self.y0) * (self.x1 - self.x0) + (t.0 - self.x0)) as usize)
        } else {
            None
        }
    }
    #[inline]
    fn get(&self, t: T) -> Option<i64> {
        match self.idx(t) {
            Some(i) => {
                let v = self.dist[i];
                if v >= 0 { Some(v) } else { None }
            }
            None => self.side.get(&t).copied(),
        }
    }
    #[inline]
    fn set(&mut self, t: T, v: i64) {
        match self.idx(t) {
            Some(i) => self.dist[i] = v,
            None => {
                self.side.insert(t, v);
            }
        }
    }
}

/// route._walk step for step: Dijkstra over (d, (x, y)) as Python's heap orders it; a step goes to
/// the first free tile within ``reach`` along a heading (a tunnel under what blocks), never out of
/// the box.
fn run_walk(grid: &NativeGrid, seeds: &[T], reach: i64) -> Walk {
    let (x0, y0, x1, y1) = grid.bbox.unwrap();
    let dense = grid.dense();
    let n = ((x1 - x0).max(0) * (y1 - y0).max(0)) as usize;
    let mut w = Walk { x0, y0, x1, y1, dist: vec![-1; n], side: FxHashMap::default(), order: Vec::new() };
    for &s in seeds {
        if w.get(s).is_none() {
            w.set(s, 0);
            w.order.push(s);
        }
    }
    let mut start = w.order.clone();
    start.sort();
    let mut heap: BinaryHeap<Reverse<(i64, i64, i64)>> = start.iter().map(|&(x, y)| Reverse((0, x, y))).collect();
    while let Some(Reverse((d, x, y))) = heap.pop() {
        if d > w.get((x, y)).unwrap_or(i64::MAX) {
            continue;
        }
        for h in 0..4usize {
            for j in 1..=reach {
                let u = (x + DX[h] * j, y + DY[h] * j);
                let i = w.idx(u);
                let free = match i {
                    Some(i) => !dense[i],
                    None => false,
                };
                if free {
                    let nd = d + j;
                    let cur = w.get(u);
                    if cur.map_or(true, |c| nd < c) {
                        if cur.is_none() {
                            w.order.push(u);
                        }
                        w.set(u, nd);
                        heap.push(Reverse((nd, u.0, u.1)));
                    }
                    break;
                }
                if i.is_none() {
                    break;
                }
            }
        }
    }
    w
}

fn need_box(grid: &NativeGrid) -> PyResult<()> {
    if grid.bbox.is_none() {
        return Err(pyo3::exceptions::PyValueError::new_err("walk needs a bounded grid"));
    }
    Ok(())
}

/// route._walk: [(tile, distance)] in the order the Python dict has them.
#[pyfunction]
#[pyo3(signature = (grid, seeds, reach=5))]
fn walk(grid: &Bound<'_, NativeGrid>, seeds: Vec<T>, reach: i64) -> PyResult<Vec<(T, i64)>> {
    let grid = grid.get();
    need_box(grid)?;
    let w = run_walk(grid, &seeds, reach);
    Ok(w.order.iter().map(|&t| (t, w.get(t).unwrap())).collect())
}

/// route._hubs after its seeds: [(H, f)] hub candidates, best first. ``near_d`` / ``near_c``: per
/// driver / consumer the tiles its walk starts from; ``ends``: tiles no hub may take.
#[pyfunction]
#[pyo3(signature = (grid, near_d, near_c, ends, most, reach=5))]
fn hubs(
    grid: &Bound<'_, NativeGrid>,
    near_d: Vec<Vec<T>>,
    near_c: Vec<Vec<T>>,
    ends: Vec<T>,
    most: usize,
    reach: i64,
) -> PyResult<Vec<(T, i64)>> {
    let grid = grid.get();
    need_box(grid)?;
    if near_d.is_empty() || near_c.is_empty() {
        return Ok(vec![]);
    }
    let dd: Vec<Walk> = near_d.iter().map(|s| run_walk(grid, s, reach)).collect();
    let dc: Vec<Walk> = near_c.iter().map(|s| run_walk(grid, s, reach)).collect();
    let ends: FxHashSet<T> = ends.into_iter().collect();
    let all = || dd.iter().chain(dc.iter());
    let in_common = |t: T| !ends.contains(&t) && all().all(|w| w.get(t).is_some());
    let mut rows: Vec<(bool, i64, i64, i64, i64)> = Vec::new();
    for &t in &dd[0].order {
        if !in_common(t) {
            continue;
        }
        let a: Vec<i64> = dd.iter().map(|w| w.get(t).unwrap()).collect();
        for f in 0..4usize {
            let u = (t.0 + DX[f], t.1 + DY[f]);
            if !in_common(u) {
                continue;
            }
            let b: Vec<i64> = dc.iter().map(|w| w.get(u).unwrap()).collect();
            let short = (a.len() > 1 && *a.iter().min().unwrap() < 3) || (b.len() > 1 && *b.iter().min().unwrap() < 3);
            rows.push((short, a.iter().sum::<i64>() + b.iter().sum::<i64>(), t.1, t.0, f as i64));
        }
    }
    rows.sort();
    let mut out: Vec<(T, i64)> = Vec::new();
    for (_short, _score, y, x, f) in rows {
        if out.iter().any(|(o, _)| (x - o.0).abs() + (y - o.1).abs() < 3) {
            continue;
        }
        out.push(((x, y), f));
        if out.len() >= most {
            break;
        }
    }
    Ok(out)
}

#[derive(Clone, Copy)]
enum Sink {
    Fixed { x: i64, y: i64, edir: i64 },
    Tap { x0: i64, y0: i64, x1: i64, y1: i64 },
}

impl Sink {
    #[inline]
    fn h(&self, x: i64, y: i64) -> i64 {
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

fn trace(parent: &FxHashMap<St, Option<St>>, st: St) -> Vec<St> {
    let mut out = vec![st];
    while let Some(Some(p)) = parent.get(out.last().unwrap()) {
        out.push(*p);
    }
    out.reverse();
    out
}

/// The search's fixed inputs: the ground (grid + the tree's own blocked tiles), the tree's tunnels,
/// the sinks and the costs.
struct Search<'a> {
    grid: &'a NativeGrid,
    extra: &'a FxHashSet<T>,
    tspans: &'a [FxHashSet<T>; 2],
    sinks: &'a [Sink],
    targets: &'a [usize],
    tapped: &'a FxHashSet<T>,
    belt: f64,
    turn: f64,
    ug: f64,
    max_ug: i64,
    limit: usize,
}

/// steiner._astar_py, step for step -> (path, sink index, cost, the start the path left from).
/// ``tap_goal(i, path, start)``: the goal test of tap sink i (Python's, or the native one).
fn search<F>(s: &Search, starts: &[(St, f64)], start_spare: &[Option<T>], mut tap_goal: F)
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
            if !blocked((nx, ny)) {
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
            if ex != 0 || nd != d || s.tapped.contains(&(x, y)) {
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

fn to_sinks(sinks: Vec<(u8, i64, i64, i64, i64)>) -> Vec<Sink> {
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
                    belt, turn, ug, max_ug, limit, tap_goal))]
#[allow(clippy::too_many_arguments)]
fn astar<'py>(
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
) -> PyResult<Option<(Vec<St>, usize, f64)>> {
    let sinks = to_sinks(sinks);
    if targets.is_empty() || targets.iter().any(|&i| i >= sinks.len()) {
        return Err(pyo3::exceptions::PyValueError::new_err("targets: empty or out of range"));
    }
    let extra: FxHashSet<T> = extra.into_iter().collect();
    let tspans: [FxHashSet<T>; 2] = [tspan0.into_iter().collect(), tspan1.into_iter().collect()];
    let tapped: FxHashSet<T> = tapped.into_iter().collect();
    let s = Search {
        grid: grid.get(), extra: &extra, tspans: &tspans, sinks: &sinks, targets: &targets,
        tapped: &tapped, belt, turn, ug, max_ug, limit,
    };
    let got = search(&s, &starts, &start_spare, |i, p, _from| tap_goal.call1((i, p.to_vec()))?.is_truthy())?;
    Ok(got.map(|(p, i, gs, _from)| (p, i, gs)))
}

// -- grow: steiner.grow, the whole tree in Rust ---------------------------------------------------
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Mv {
    Step(St),
    Jump(St),
    Split(i64, St, St), // side, straight child, side child
}

/// A dict with Python's order: a new key goes last, an existing key keeps its place, a removed key
/// leaves (``tree.succ`` and ``tree.sink_at`` are dicts, and their order reaches Python).
#[derive(Default)]
struct OrdMap<V: Copy> {
    slots: Vec<Option<(St, V)>>,
    idx: FxHashMap<St, usize>,
}

impl<V: Copy> Clone for OrdMap<V> {
    fn clone(&self) -> Self {
        let mut out = OrdMap { slots: Vec::with_capacity(self.idx.len()), idx: FxHashMap::default() };
        for (k, v) in self.iter() {
            out.insert(k, v);
        }
        out
    }
}

impl<V: Copy> OrdMap<V> {
    fn new() -> Self {
        OrdMap { slots: Vec::new(), idx: FxHashMap::default() }
    }
    fn get(&self, k: &St) -> Option<V> {
        self.idx.get(k).map(|&i| self.slots[i].unwrap().1)
    }
    fn contains(&self, k: &St) -> bool {
        self.idx.contains_key(k)
    }
    fn insert(&mut self, k: St, v: V) {
        match self.idx.get(&k) {
            Some(&i) => self.slots[i] = Some((k, v)),
            None => {
                self.idx.insert(k, self.slots.len());
                self.slots.push(Some((k, v)));
            }
        }
    }
    fn remove(&mut self, k: &St) -> Option<V> {
        self.idx.remove(k).map(|i| self.slots[i].take().unwrap().1)
    }
    fn iter(&self) -> impl Iterator<Item = (St, V)> + '_ {
        self.slots.iter().filter_map(|s| *s)
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
struct Tap {
    q: T,
    name: usize, // into Ctx.names
    dir: i64,
    sink: usize, // the sink's name, into Ctx.snames
}

/// A Tree: ``last_end`` is the one entry ``sink_terminal`` holds (Tree.copy() does not copy it, so
/// after _attach only the end just attached has it, and after _detach none).
#[derive(Clone)]
struct Tree {
    root: St,
    succ: OrdMap<Mv>,
    sink_at: OrdMap<usize>,
    taps: Vec<Tap>,
    reserved: FxHashSet<T>,
    last_end: Option<(St, bool)>,
}

struct Tiles {
    own: FxHashMap<T, u32>,
    spare: FxHashSet<T>,
}

struct TapSpec {
    rect: (i64, i64, i64, i64),
    k: usize,
    inserters: Vec<usize>,
}

struct Ctx<'a> {
    grid: &'a NativeGrid,
    keep_clear: FxHashSet<T>,
    drop_taps: bool,
    belt: f64,
    turn: f64,
    ug: f64,
    split: f64,
    tap: f64,
    long_tap: f64,
    max_ug: i64,
    limit: usize,
    names: Vec<String>,  // inserter names
    long: Option<usize>, // "long-handed-inserter" in names
    sinks: Vec<Sink>,
    taps: Vec<Option<TapSpec>>, // per sink: its tap spec (a TapSink) or None (a FixedSink)
    sname: Vec<usize>,          // per sink: the id of its name (equal names, one id)
}

#[inline]
fn split_tiles(s: St, side: i64) -> (T, T) {
    let d = s.2 as usize;
    let n = (s.0 + DX[d], s.1 + DY[d]);
    let sh = ((s.2 + side) % 4) as usize;
    (n, (n.0 + DX[sh], n.1 + DY[sh]))
}

#[inline]
fn spare_tile(s: St, side: i64) -> T {
    let sh = ((s.2 + side) % 4) as usize;
    (s.0 + DX[sh], s.1 + DY[sh])
}

impl Tree {
    fn new(root: St) -> Self {
        Tree { root, succ: OrdMap::new(), sink_at: OrdMap::new(), taps: Vec::new(), reserved: FxHashSet::default(), last_end: None }
    }

    fn states(&self) -> Vec<St> {
        let mut out = Vec::new();
        let mut stack = vec![self.root];
        while let Some(s) = stack.pop() {
            out.push(s);
            match self.succ.get(&s) {
                None => {}
                Some(Mv::Step(c)) | Some(Mv::Jump(c)) => stack.push(c),
                Some(Mv::Split(_, c1, c2)) => {
                    stack.push(c1);
                    stack.push(c2);
                }
            }
        }
        out
    }

    fn tiles(&self, cx: &Ctx) -> Tiles {
        let mut own: FxHashMap<T, u32> = FxHashMap::default();
        let mut spare = FxHashSet::default();
        for s in self.states() {
            *own.entry((s.0, s.1)).or_insert(0) += 1;
            if let Some(Mv::Split(side, _, _)) = self.succ.get(&s) {
                let (n, m) = split_tiles(s, side);
                *own.entry(n).or_insert(0) += 1;
                *own.entry(m).or_insert(0) += 1;
                if cx.drop_taps {
                    spare.insert(spare_tile(s, side));
                }
            }
        }
        for t in &self.taps {
            *own.entry(t.q).or_insert(0) += 1;
        }
        Tiles { own, spare }
    }

    #[inline]
    fn free(&self, cx: &Ctx, tl: &Tiles, t: T) -> bool {
        !cx.grid.blocked(t) && !tl.own.contains_key(&t) && !self.reserved.contains(&t) && !tl.spare.contains(&t)
            && !cx.grid.soft.contains_key(&t)
    }

    fn spans(&self) -> [FxHashSet<T>; 2] {
        let mut out = [FxHashSet::default(), FxHashSet::default()];
        for s in self.states() {
            if let Some(Mv::Jump(c)) = self.succ.get(&s) {
                let k = (c.0 - s.0).abs() + (c.1 - s.1).abs();
                let du = c.2 as usize;
                for j in 0..=k {
                    out[du % 2].insert((s.0 + DX[du] * j, s.1 + DY[du] * j));
                }
            }
        }
        out
    }

    fn terminal(&self, s: &St) -> bool {
        match self.last_end {
            Some((e, term)) if e == *s => term,
            _ => true,
        }
    }

    fn cost(&self, cx: &Ctx) -> f64 {
        let (mut belts, mut turns, mut ugs, mut splitters) = (0i64, 0i64, 0i64, 0i64);
        for s in self.states() {
            let mv = self.succ.get(&s);
            if s.3 != 0 {
                ugs += 1;
            }
            match mv {
                None => {
                    if s.3 == 0 {
                        belts += 1;
                    }
                }
                Some(Mv::Jump(_)) => ugs += 1,
                Some(m) => {
                    if s.3 == 0 {
                        belts += 1;
                    }
                    match m {
                        Mv::Split(..) => splitters += 1,
                        Mv::Step(c) => {
                            if c.2 != s.2 && s != self.root {
                                turns += 1;
                            }
                        }
                        Mv::Jump(_) => {}
                    }
                }
            }
        }
        let mut taps = 0.0f64;
        for t in &self.taps {
            taps += if Some(t.name) == cx.long { cx.long_tap } else { cx.tap };
        }
        let raw = belts as f64 * cx.belt + turns as f64 * cx.turn + ugs as f64 / 2.0 * cx.ug
            + splitters as f64 * cx.split + taps;
        py_round3(raw)
    }

    fn has_problems(&self, cx: &Ctx) -> bool {
        let tl = self.tiles(cx);
        for (t, &n) in &tl.own {
            if n > 1 || cx.grid.blocked(*t) {
                return true;
            }
        }
        if tl.spare.iter().any(|t| tl.own.contains_key(t)) {
            return true;
        }
        let reached: FxHashSet<usize> = self.sink_at.iter().map(|(_, i)| i).collect();
        for (i, spec) in cx.taps.iter().enumerate() {
            if !reached.contains(&i) {
                return true;
            }
            if let Some(sp) = spec {
                let got = self.taps.iter().filter(|t| t.sink == cx.sname[i]).count();
                if got < sp.k {
                    return true;
                }
            }
        }
        let mine = self.spans();
        for ax in 0..2 {
            if mine[ax].iter().any(|t| cx.grid.spans[ax].contains(t)) {
                return true;
            }
        }
        false
    }

    fn tapped(&self, cx: &Ctx) -> FxHashSet<T> {
        let mut out = FxHashSet::default();
        if cx.drop_taps {
            for t in &self.taps {
                let r = if Some(t.name) == cx.long { 2 } else { 1 };
                let g0 = (t.dir / 4) as usize;
                out.insert((t.q.0 + DX[g0] * r, t.q.1 + DY[g0] * r));
            }
        }
        out
    }
}

/// Python's round(x, 3): the nearest 3-decimal value of x's exact binary value.
fn py_round3(x: f64) -> f64 {
    format!("{:.3}", x).parse().unwrap()
}

/// TapSink.pick: taps off the last tiles of ``path`` (one per belt tile, newest first), up to k;
/// none on ``taken``.
fn pick(cx: &Ctx, tree: &Tree, tl: &Tiles, i: usize, path: &[St], taken: &[T]) -> Vec<Tap> {
    let sp = cx.taps[i].as_ref().unwrap();
    let on: FxHashSet<T> = path.iter().map(|s| (s.0, s.1)).collect();
    let mut tunnels: FxHashSet<St> = FxHashSet::default();
    if cx.drop_taps {
        for w in 0..path.len().saturating_sub(1) {
            if path[w + 1].3 != 0 {
                tunnels.insert(path[w]);
            }
        }
    }
    let (x0, y0, x1, y1) = sp.rect;
    let inside = |t: T| x0 <= t.0 && t.0 < x1 && y0 <= t.1 && t.1 < y1;
    let mut got: Vec<Tap> = Vec::new();
    let lo = path.len().saturating_sub(6);
    for s in path[lo..].iter().rev() {
        if tunnels.contains(s) {
            continue; // reversed this is an underground exit, which takes no drop
        }
        'found: for h in 0..4usize {
            for &nm in &sp.inserters {
                let r = if Some(nm) == cx.long { 2 } else { 1 };
                let q = (s.0 + DX[h] * r, s.1 + DY[h] * r);
                if tree.free(cx, tl, q) && !on.contains(&q) && !got.iter().any(|g| g.q == q)
                    && !taken.contains(&q) && inside((q.0 + DX[h] * r, q.1 + DY[h] * r))
                {
                    got.push(Tap { q, name: nm, dir: (((h + 2) % 4) * 4) as i64, sink: cx.sname[i] });
                    break 'found;
                }
            }
        }
        if got.len() >= sp.k {
            break;
        }
    }
    got
}

#[derive(Clone, Copy)]
enum How {
    Leaf,
    Split(St, i64, St), // s, side, c
}

/// _starts: (state, g0, how, taken) the next branch may leave the tree from.
fn starts_of(cx: &Ctx, tree: &Tree, tl: &Tiles) -> Vec<(St, f64, How, Vec<T>)> {
    let mut out = Vec::new();
    for s in tree.states() {
        let mv = tree.succ.get(&s);
        if mv.is_none() && !tree.sink_at.contains(&s) {
            out.push((s, 0.0, How::Leaf, vec![]));
        } else if mv.is_none() && tree.sink_at.contains(&s) && !tree.terminal(&s) {
            out.push((s, 0.0, How::Leaf, vec![]));
        }
        let c = match mv {
            Some(Mv::Step(c)) => c,
            _ => continue,
        };
        let d = c.2;
        let cm = tree.succ.get(&c);
        let straight_on = matches!(cm, Some(Mv::Step(cc)) if cc.2 == d);
        if c.3 != 0 || !straight_on || tree.sink_at.contains(&c) {
            continue;
        }
        if s.2 != d {
            continue; // s turns into c: c is a curve, a splitter needs a straight feed
        }
        let du = d as usize;
        for side in [1i64, 3] {
            let (n, m) = split_tiles(s, side);
            let o2 = (m.0 + DX[du], m.1 + DY[du], d, 0);
            let sp = spare_tile(s, side);
            if cx.keep_clear.contains(&sp) {
                continue;
            }
            if cx.drop_taps && tl.own.contains_key(&sp) {
                continue;
            }
            if tree.free(cx, tl, m) && tree.free(cx, tl, (o2.0, o2.1)) {
                out.push((o2, cx.split - cx.belt, How::Split(s, side, c), vec![n, m]));
            }
        }
    }
    out
}

/// grow()'s step: one A* from the tree's starts to the nearest of ``targets``.
fn step(cx: &Ctx, tree: &Tree, targets: &[usize]) -> PyResult<Option<(Vec<St>, How, usize, f64)>> {
    let tl = tree.tiles(cx);
    let st = starts_of(cx, tree, &tl);
    let mut extra: FxHashSet<T> = tl.own.keys().copied().collect();
    extra.extend(tree.reserved.iter().copied());
    extra.extend(tl.spare.iter().copied());
    let tspans = tree.spans();
    let tapped = tree.tapped(cx);
    let s = Search {
        grid: cx.grid, extra: &extra, tspans: &tspans, sinks: &cx.sinks, targets,
        tapped: &tapped, belt: cx.belt, turn: cx.turn, ug: cx.ug, max_ug: cx.max_ug, limit: cx.limit,
    };
    let starts: Vec<(St, f64)> = st.iter().map(|(s, g0, _, _)| (*s, *g0)).collect();
    let spare: Vec<Option<T>> = st
        .iter()
        .map(|(_, _, how, _)| match how {
            How::Split(s, side, _) if cx.drop_taps => Some(spare_tile(*s, *side)),
            _ => None,
        })
        .collect();
    let got = search(&s, &starts, &spare, |i, path, from| {
        // TapSink.goal: an exit can't turn (unless laid reversed), then enough taps
        let last = *path.last().unwrap();
        let du = last.2 as usize;
        if last.3 != 0 && !cx.drop_taps && cx.grid.blocked((last.0 + DX[du], last.1 + DY[du])) {
            return Ok(false);
        }
        Ok(pick(cx, tree, &tl, i, path, &st[from].3).len() >= cx.taps[i].as_ref().unwrap().k)
    })?;
    Ok(got.map(|(p, i, gs, from)| (p, st[from].2, i, gs)))
}

fn attach(cx: &Ctx, tree: &Tree, path: &[St], how: How, i: usize) -> Tree {
    let mut t = tree.clone();
    if let How::Split(s, side, c) = how {
        let nxt = t.succ.remove(&c).unwrap();
        let straight = match nxt {
            Mv::Step(x) | Mv::Jump(x) => x,
            Mv::Split(..) => unreachable!(),
        };
        t.succ.insert(s, Mv::Split(side, straight, path[0]));
    }
    for w in path.windows(2) {
        let (a, b) = (w[0], w[1]);
        t.succ.insert(a, if b.3 != 0 { Mv::Jump(b) } else { Mv::Step(b) });
    }
    let end = *path.last().unwrap();
    if cx.taps[i].is_some() {
        let tl = t.tiles(cx); // the same choice the goal test made (before the path lands)
        let got = pick(cx, &t, &tl, i, path, &[]);
        for g in &got {
            t.reserved.insert(g.q);
        }
        t.taps.extend(got);
    }
    t.sink_at.insert(end, i);
    t.last_end = Some((end, cx.taps[i].is_none()));
    t
}

fn detach(cx: &Ctx, tree: &Tree, i: usize) -> Option<Tree> {
    let mut t = tree.clone();
    t.last_end = None;
    let end = t.sink_at.iter().find(|&(_, v)| v == i).map(|(s, _)| s)?;
    if t.succ.get(&end).is_some() {
        return None; // a tap sink the tree runs on through: keep it
    }
    let mut parent: FxHashMap<St, St> = FxHashMap::default();
    for (s, mv) in t.succ.iter() {
        match mv {
            Mv::Step(c) | Mv::Jump(c) => {
                parent.insert(c, s);
            }
            Mv::Split(_, c1, c2) => {
                parent.insert(c1, s);
                parent.insert(c2, s);
            }
        }
    }
    let mut chain = vec![end];
    let mut s = end;
    while let Some(&p) = parent.get(&s) {
        let mv = t.succ.get(&p).unwrap();
        if matches!(mv, Mv::Split(..)) || t.sink_at.contains(&p) || p == t.root {
            break;
        }
        chain.push(p);
        s = p;
    }
    let p = parent.get(&s).copied();
    for c in &chain {
        t.succ.remove(c);
        t.sink_at.remove(c);
    }
    if let Some(p) = p {
        match t.succ.get(&p) {
            Some(Mv::Split(side, c1, c2)) => {
                let keep = if s == c1 { c2 } else { c1 };
                let (n, m) = split_tiles(p, side);
                let d = p.2;
                if keep == c1 {
                    let mid = (n.0, n.1, d, 0);
                    t.succ.insert(p, Mv::Step(mid));
                    t.succ.insert(mid, Mv::Step(c1));
                } else {
                    let sh = (d + side) % 4;
                    let (a, b) = ((n.0, n.1, d, 0), (m.0, m.1, sh, 0));
                    t.succ.insert(p, Mv::Step(a));
                    t.succ.insert(a, Mv::Step(b));
                    t.succ.insert(b, Mv::Step(c2));
                }
            }
            _ => {
                t.succ.remove(&p);
            }
        }
    }
    let name = cx.sname[i];
    t.taps.retain(|tp| tp.sink != name);
    t.reserved = t.taps.iter().map(|tp| tp.q).collect();
    Some(t)
}

type MvOut = (u8, i64, St, St);
type TapOut = (T, String, i64, usize);
type LogOut = (u8, Vec<usize>, usize, u8, f64, f64);

/// steiner.grow for FixedSink / TapSink sinks -> (succ, sink_at, taps, reserved, last_end, log).
/// succ: (state, (0 step | 1 jump | 2 split, side, child, side child)); taps: (tile, inserter,
/// direction, sink index of its name); log: (0 cannot | 1 added | 2 rerouted, targets, sink,
/// 0 leaf | 1 split, cost a, cost b).
#[pyfunction]
#[pyo3(signature = (grid, keep_clear, drop_taps, root, sinks, snames, ks, inserters, costs,
                    improve, order, limit))]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn grow(
    grid: &Bound<'_, NativeGrid>,
    keep_clear: Vec<T>,
    drop_taps: bool,
    root: St,
    sinks: Vec<(u8, i64, i64, i64, i64)>,
    snames: Vec<String>,
    ks: Vec<usize>,
    inserters: Vec<Vec<String>>,
    costs: (f64, f64, f64, f64, f64, f64, i64),
    improve: usize,
    order: Option<Vec<usize>>,
    limit: usize,
) -> PyResult<(Vec<(St, MvOut)>, Vec<(St, usize)>, Vec<TapOut>, Vec<T>, Option<(St, bool)>, Vec<LogOut>)> {
    let n = sinks.len();
    if snames.len() != n || ks.len() != n || inserters.len() != n {
        return Err(pyo3::exceptions::PyValueError::new_err("one name, k and inserter list per sink"));
    }
    let sinks = to_sinks(sinks);
    let mut names: Vec<String> = Vec::new();
    let mut taps: Vec<Option<TapSpec>> = Vec::new();
    for (i, s) in sinks.iter().enumerate() {
        taps.push(match *s {
            Sink::Fixed { .. } => None,
            Sink::Tap { x0, y0, x1, y1 } => {
                let ids = inserters[i]
                    .iter()
                    .map(|nm| match names.iter().position(|x| x == nm) {
                        Some(p) => p,
                        None => {
                            names.push(nm.clone());
                            names.len() - 1
                        }
                    })
                    .collect();
                Some(TapSpec { rect: (x0, y0, x1, y1), k: ks[i], inserters: ids })
            }
        });
    }
    let sname: Vec<usize> = snames.iter().map(|s| snames.iter().position(|x| x == s).unwrap()).collect();
    let long = names.iter().position(|x| x == "long-handed-inserter");
    let (belt, turn, ug, split, tap, long_tap, max_ug) = costs;
    let cx = Ctx {
        grid: grid.get(), keep_clear: keep_clear.into_iter().collect(), drop_taps,
        belt, turn, ug, split, tap, long_tap, max_ug, limit, names, long, sinks, taps, sname,
    };

    let mut tree = Tree::new(root);
    let ordered = order.is_some();
    let mut left: Vec<usize> = order.unwrap_or_else(|| (0..n).collect());
    let mut log: Vec<LogOut> = Vec::new();
    while !left.is_empty() {
        let targets: Vec<usize> = if ordered { left[..1].to_vec() } else { left.clone() };
        if targets.iter().any(|&i| i >= n) {
            return Err(pyo3::exceptions::PyValueError::new_err("order: a sink index out of range"));
        }
        match step(&cx, &tree, &targets)? {
            None => {
                log.push((0, targets, 0, 0, 0.0, 0.0));
                break;
            }
            Some((path, how, i, gcost)) => {
                tree = attach(&cx, &tree, &path, how, i);
                let at = left.iter().position(|&x| x == i).unwrap();
                left.remove(at);
                log.push((1, vec![], i, matches!(how, How::Split(..)) as u8, gcost, 0.0));
            }
        }
    }
    for _round in 0..improve {
        let mut better = false;
        for i in 0..n {
            let has = tree.sink_at.iter().any(|(_, v)| v == i);
            let cut = if has { detach(&cx, &tree, i) } else { None };
            let cut = match cut {
                Some(c) => c,
                None => continue,
            };
            let got = match step(&cx, &cut, &[i])? {
                Some(g) => g,
                None => continue,
            };
            let new = attach(&cx, &cut, &got.0, got.1, i);
            if !new.has_problems(&cx) {
                let (old_c, new_c) = (tree.cost(&cx), new.cost(&cx));
                if new_c < old_c - 1e-9 {
                    log.push((2, vec![], i, 0, old_c, new_c));
                    tree = new;
                    better = true;
                }
            }
        }
        if !better {
            break;
        }
    }

    let enc = |mv: Mv| -> MvOut {
        match mv {
            Mv::Step(c) => (0, 0, c, c),
            Mv::Jump(c) => (1, 0, c, c),
            Mv::Split(side, c1, c2) => (2, side, c1, c2),
        }
    };
    Ok((
        tree.succ.iter().map(|(s, mv)| (s, enc(mv))).collect(),
        tree.sink_at.iter().collect(),
        tree.taps.iter().map(|t| (t.q, cx.names[t.name].clone(), t.dir, t.sink)).collect(),
        tree.reserved.iter().copied().collect(),
        tree.last_end,
        log,
    ))
}

#[pymodule]
fn fkroute(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<NativeGrid>()?;
    m.add_function(wrap_pyfunction!(astar, m)?)?;
    m.add_function(wrap_pyfunction!(walk, m)?)?;
    m.add_function(wrap_pyfunction!(hubs, m)?)?;
    m.add_function(wrap_pyfunction!(grow, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
