//! fkroute: native kernels for fkcore's router.
//!
//! `astar` is fkcore.steiner._astar, step for step. The heap orders entries as Python's tuple
//! `(f, -g, state)` does, and costs are summed in the same order, so it pops the same states and
//! returns the same path.
use pyo3::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};
use std::cmp::Ordering;
use std::collections::BinaryHeap;

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
}

#[pymethods]
impl NativeGrid {
    #[new]
    #[pyo3(signature = (blocked, span0, span1, bbox=None))]
    fn new(blocked: Vec<T>, span0: Vec<T>, span1: Vec<T>, bbox: Option<(i64, i64, i64, i64)>) -> Self {
        NativeGrid {
            occ: blocked.into_iter().collect(),
            spans: [span0.into_iter().collect(), span1.into_iter().collect()],
            bbox,
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
    let grid = grid.get();
    let extra: FxHashSet<T> = extra.into_iter().collect();
    let tspans: [FxHashSet<T>; 2] = [tspan0.into_iter().collect(), tspan1.into_iter().collect()];
    let tapped: FxHashSet<T> = tapped.into_iter().collect();
    let sinks: Vec<Sink> = sinks
        .into_iter()
        .map(|(k, a, b, c, d)| {
            if k == 0 {
                Sink::Fixed { x: a, y: b, edir: c }
            } else {
                Sink::Tap { x0: a, y0: b, x1: c, y1: d }
            }
        })
        .collect();
    if targets.is_empty() || targets.iter().any(|&i| i >= sinks.len()) {
        return Err(pyo3::exceptions::PyValueError::new_err("targets: empty or out of range"));
    }
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
        if done.len() > limit {
            return Ok(None);
        }
        let mut path: Option<Vec<St>> = None;
        for &i in &targets {
            let hit = match sinks[i] {
                Sink::Fixed { x, y, edir } => {
                    (st.0, st.1) == (x, y) && st.2 != (edir + 2).rem_euclid(4) && (st.3 == 0 || st.2 == edir)
                }
                Sink::Tap { .. } => {
                    if sinks[i].h(st.0, st.1) > 0 {
                        false // too far for any tap: skip the path trace
                    } else {
                        let p = path.get_or_insert_with(|| trace(&parent, st));
                        tap_goal.call1((i, p.clone()))?.is_truthy()?
                    }
                }
            };
            if hit {
                let p = path.get_or_insert_with(|| trace(&parent, st));
                let tiles: FxHashSet<T> = p.iter().map(|s| (s.0, s.1)).collect();
                let crosses_spare = match start_spare.get(start_of[&p[0]]) {
                    Some(Some(sp)) => tiles.contains(sp),
                    _ => false,
                };
                if tiles.len() == p.len() && !crosses_spare {
                    return Ok(Some((p.clone(), i, gs)));
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
            let step = belt + if nd != d { turn } else { 0.0 };
            if !blocked((nx, ny)) {
                let ns = (nx, ny, nd, 0);
                let cost = gs + step;
                if cost < *g.get(&ns).unwrap_or(&f64::INFINITY) {
                    g.insert(ns, cost);
                    parent.insert(ns, Some(st));
                    heap.push(Entry { f: cost + hh(nx, ny), ng: -cost, st: ns });
                }
            }
            if ex != 0 || nd != d || tapped.contains(&(x, y)) {
                continue;
            }
            let mut seen_block = false;
            for j in 2..=max_ug {
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
                    grid.spans[ax].contains(&t) || tspans[ax].contains(&t)
                });
                if crosses {
                    break;
                }
                if seen_block && !blocked((tx, ty)) {
                    let ns = (tx, ty, d, 1);
                    let cost = gs + ug;
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

#[pymodule]
fn fkroute(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<NativeGrid>()?;
    m.add_function(wrap_pyfunction!(astar, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
