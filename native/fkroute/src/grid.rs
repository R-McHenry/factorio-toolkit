//! The ground: a steiner.Grid as the kernel sees it, route._walk and route._hubs.
use pyo3::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};
use std::cmp::Reverse;
use std::collections::BinaryHeap;
use std::sync::OnceLock;

use crate::{DX, DY, T};

/// A steiner.Grid: blocked tiles (occ, plus fronts for a plain Grid), the hidden spans of the
/// foreign undergrounds per axis, and for a bounded grid the box outside which all is blocked.
/// Built once per Grid and cached on it.
#[pyclass(frozen, module = "fkroute")]
pub struct NativeGrid {
    pub(crate) occ: FxHashSet<T>,
    pub(crate) spans: [FxHashSet<T>; 2],
    pub(crate) bbox: Option<(i64, i64, i64, i64)>,
    dense: OnceLock<Vec<bool>>, // a bounded grid's blocked tiles as a bitmap over its box
    pub(crate) soft: FxHashMap<T, f64>,    // negotiated: the extra cost of a step onto a tile another net holds
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
    /// The same box and soft tiles over other blocked tiles and spans (the hub's per-candidate
    /// grounds).
    pub(crate) fn derived(&self, occ: FxHashSet<T>, spans: [FxHashSet<T>; 2]) -> NativeGrid {
        NativeGrid { occ, spans, bbox: self.bbox, dense: OnceLock::new(), soft: self.soft.clone() }
    }

    #[inline]
    pub(crate) fn blocked(&self, t: T) -> bool {
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
pub(crate) fn walk(grid: &Bound<'_, NativeGrid>, seeds: Vec<T>, reach: i64) -> PyResult<Vec<(T, i64)>> {
    let grid = grid.get();
    need_box(grid)?;
    let w = run_walk(grid, &seeds, reach);
    Ok(w.order.iter().map(|&t| (t, w.get(t).unwrap())).collect())
}

/// route._hubs after its seeds: [(H, f)] hub candidates, best first. ``near_d`` / ``near_c``: per
/// driver / consumer the tiles its walk starts from; ``ends``: tiles no hub may take.
#[pyfunction]
#[pyo3(signature = (grid, near_d, near_c, ends, most, reach=5))]
pub(crate) fn hubs(
    grid: &Bound<'_, NativeGrid>,
    near_d: Vec<Vec<T>>,
    near_c: Vec<Vec<T>>,
    ends: Vec<T>,
    most: usize,
    reach: i64,
) -> PyResult<Vec<(T, i64)>> {
    let grid = grid.get();
    need_box(grid)?;
    let ends: FxHashSet<T> = ends.into_iter().collect();
    Ok(run_hubs(grid, &near_d, &near_c, &ends, most, reach))
}

/// route._hubs_py: the candidates, best first.
pub(crate) fn run_hubs(grid: &NativeGrid, near_d: &[Vec<T>], near_c: &[Vec<T>], ends: &FxHashSet<T>, most: usize, reach: i64) -> Vec<(T, i64)> {
    if near_d.is_empty() || near_c.is_empty() {
        return vec![];
    }
    let dd: Vec<Walk> = near_d.iter().map(|s| run_walk(grid, s, reach)).collect();
    let dc: Vec<Walk> = near_c.iter().map(|s| run_walk(grid, s, reach)).collect();
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
    out
}
