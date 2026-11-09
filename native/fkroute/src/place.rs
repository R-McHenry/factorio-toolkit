//! place: fkcore.layout's routability Lagrangian (PLAN-4.0 part P), step for step.
//!
//! `field` is the walk with a price per tile entered, returning the dense distance field and the
//! predecessors; `place` is `fkcore.layout._place_py`: the same integer arithmetic (milli-tiles),
//! the same instance order and tie-breaks, so both return the same positions.
use pyo3::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};
use std::cmp::Reverse;
use std::collections::BinaryHeap;

use crate::grid::NativeGrid;

type T = (i64, i64);
type At = (i64, i64, i64);

const DX: [i64; 4] = [0, 1, 0, -1];
const DY: [i64; 4] = [-1, 0, 1, 0];
const MILLI: i64 = 1000;

/// One spec instance: per rotation (footprint tiles, attach groups), its position, movable.
type SInst = (String, Vec<(Vec<T>, Vec<Vec<T>>)>, Option<At>, bool);
/// One spec net: name, weight in belts, terms (instance, group, driver).
type SNet = (String, i64, Vec<(usize, usize, bool)>);

/// The priced walk over a dense board: Dijkstra over (d, x, y) as Python's heap orders it; a step
/// enters the first free tile within `reach` along a heading (a tunnel under what blocks) at
/// `MILLI` per tile plus the price of the tile entered; never out of the box.
fn run_field(
    x0: i64,
    y0: i64,
    w: i64,
    h: i64,
    free: &dyn Fn(usize) -> bool,
    price: Option<&[i64]>,
    seeds: &[T],
    reach: i64,
) -> (Vec<i64>, Vec<i64>) {
    let n = (w * h) as usize;
    let mut dist = vec![-1i64; n];
    let mut pred = vec![-1i64; n];
    let mut sorted: Vec<T> = seeds.to_vec();
    sorted.sort();
    sorted.dedup();
    let mut heap: BinaryHeap<Reverse<(i64, i64, i64)>> = BinaryHeap::new();
    for &(sx, sy) in &sorted {
        let (lx, ly) = (sx - x0, sy - y0);
        if 0 <= lx && lx < w && 0 <= ly && ly < h {
            let k = (ly * w + lx) as usize;
            if dist[k] != 0 {
                dist[k] = 0;
                heap.push(Reverse((0, sx, sy)));
            }
        }
    }
    while let Some(Reverse((d, x, y))) = heap.pop() {
        let k = ((y - y0) * w + (x - x0)) as usize;
        if d > dist[k] {
            continue;
        }
        for hd in 0..4usize {
            for j in 1..=reach {
                let (ux, uy) = (x + DX[hd] * j, y + DY[hd] * j);
                let (lx, ly) = (ux - x0, uy - y0);
                if !(0 <= lx && lx < w && 0 <= ly && ly < h) {
                    break;
                }
                let u = (ly * w + lx) as usize;
                if free(u) {
                    let nd = d + j * MILLI + price.map_or(0, |p| p[u]);
                    if dist[u] < 0 || nd < dist[u] {
                        dist[u] = nd;
                        pred[u] = k as i64;
                        heap.push(Reverse((nd, ux, uy)));
                    }
                    break;
                }
            }
        }
    }
    (dist, pred)
}

/// fkcore.layout: the walk with a price field over a bounded grid. `soft` is [(tile, price)] in
/// milli-tiles. -> (x0, y0, x1, y1, dist, pred): dense over the box, -1 where unreached; `pred`
/// is the index of the tile a route came from.
#[pyfunction]
#[pyo3(signature = (grid, seeds, reach=5, soft=None))]
pub fn field(
    grid: &Bound<'_, NativeGrid>,
    seeds: Vec<T>,
    reach: i64,
    soft: Option<Vec<(T, i64)>>,
) -> PyResult<(i64, i64, i64, i64, Vec<i64>, Vec<i64>)> {
    let grid = grid.get();
    let (x0, y0, x1, y1) = match grid.bbox {
        Some(b) => b,
        None => return Err(pyo3::exceptions::PyValueError::new_err("field needs a bounded grid")),
    };
    let (w, h) = ((x1 - x0).max(0), (y1 - y0).max(0));
    let dense = grid.dense();
    let mut price = vec![0i64; (w * h) as usize];
    for ((x, y), p) in soft.unwrap_or_default() {
        if x0 <= x && x < x1 && y0 <= y && y < y1 {
            price[((y - y0) * w + (x - x0)) as usize] = p;
        }
    }
    let free = |u: usize| !dense[u];
    let (dist, pred) = run_field(x0, y0, w, h, &free, Some(&price), &seeds, reach);
    Ok((x0, y0, x1, y1, dist, pred))
}

// -- the board: layout._State ----------------------------------------------------------------------
struct State<'a> {
    insts: &'a [SInst],
    nets: &'a [SNet],
    reach: i64,
    x0: i64,
    y0: i64,
    w: i64,
    h: i64,
    owner: Vec<i64>,
    price: Vec<i64>,
    at: Vec<Option<At>>,
    pinned: FxHashMap<T, usize>, // tile -> the instance whose one-tile attach it is
    /// layout._State.stem_of: (instance, group) -> the straight run of free tiles its belt end
    /// demands beyond itself (rule 5: the longest stem of the nets it consumes)
    stem_of: FxHashMap<(usize, usize), i64>,
}

impl<'a> State<'a> {
    fn new(
        bbox: (i64, i64, i64, i64),
        blocked: &[T],
        insts: &'a [SInst],
        nets: &'a [SNet],
        reach: i64,
        stems: &[i64],
        price: &[(T, i64)],
    ) -> Self {
        let (x0, y0, x1, y1) = bbox;
        let (w, h) = ((x1 - x0).max(0), (y1 - y0).max(0));
        let n = (w * h) as usize;
        let mut st = State {
            insts,
            nets,
            reach,
            x0,
            y0,
            w,
            h,
            owner: vec![-1; n],
            price: vec![0; n],
            at: vec![None; insts.len()],
            pinned: FxHashMap::default(),
            stem_of: FxHashMap::default(),
        };
        for &t in blocked {
            if let Some(k) = st.idx(t) {
                st.owner[k] = -2;
            }
        }
        // layout.Spec.price: where lambda starts above zero (the last build's fought-over tiles)
        for &(t, p) in price {
            if let Some(k) = st.idx(t) {
                if p > st.price[k] {
                    st.price[k] = p;
                }
            }
        }
        for (n, net) in nets.iter().enumerate() {
            let stem = stems.get(n).copied().unwrap_or(0);
            if stem <= 0 {
                continue;
            }
            for &(i, g, drv) in &net.2 {
                if !drv {
                    let e = st.stem_of.entry((i, g)).or_insert(0);
                    *e = (*e).max(stem);
                }
            }
        }
        st
    }

    #[inline]
    fn idx(&self, t: T) -> Option<usize> {
        let (x, y) = (t.0 - self.x0, t.1 - self.y0);
        if 0 <= x && x < self.w && 0 <= y && y < self.h {
            Some((y * self.w + x) as usize)
        } else {
            None
        }
    }

    fn tiles(&self, i: usize, at: At) -> Vec<T> {
        self.insts[i].1[at.2 as usize].0.iter().map(|&(dx, dy)| (at.0 + dx, at.1 + dy)).collect()
    }

    fn groups(&self, i: usize, at: At) -> Vec<Vec<T>> {
        self.insts[i].1[at.2 as usize]
            .1
            .iter()
            .map(|g| g.iter().map(|&(dx, dy)| (at.0 + dx, at.1 + dy)).collect())
            .collect()
    }

    /// layout._State.inward: the tile one step nearer instance `i`'s footprint box than ring
    /// tile `t` (the belt's tile): where its inserter stands. None when `t` is not beside the box.
    fn inward(&self, i: usize, at: At, t: T, step: i64) -> Option<T> {
        let tiles = &self.insts[i].1[at.2 as usize].0;
        if tiles.is_empty() {
            return None;
        }
        let x0 = at.0 + tiles.iter().map(|p| p.0).min().unwrap();
        let x1 = at.0 + tiles.iter().map(|p| p.0).max().unwrap() + 1;
        let y0 = at.1 + tiles.iter().map(|p| p.1).min().unwrap();
        let y1 = at.1 + tiles.iter().map(|p| p.1).max().unwrap() + 1;
        let (tx, ty) = t;
        if tx < x0 {
            Some((tx + step, ty))
        } else if tx >= x1 {
            Some((tx - step, ty))
        } else if ty < y0 {
            Some((tx, ty + step))
        } else if ty >= y1 {
            Some((tx, ty - step))
        } else {
            None
        }
    }

    /// layout._State.usable: free, and (a ring) its inward neighbour free too; `moving` counts
    /// the instance's own tiles as free. `gi` is the group's index.
    fn usable(&self, i: usize, at: At, gi: usize, t: T, moving: bool) -> bool {
        let ok = |v: i64| v == -1 || (moving && v == i as i64);
        match self.idx(t) {
            Some(k) if ok(self.owner[k]) => {}
            _ => return false,
        }
        let glen = self.insts[i].1[at.2 as usize].1[gi].len();
        let o = if glen == 1 {
            // a belt end on another's belt end or a port's tile: a zero-length belt; and the
            // tile beyond it, where its belt arrives or goes on, free and inside the box
            if !self.pinned.get(&t).map_or(true, |&o| o == i) {
                return false;
            }
            // rule 5: a pair's consumer belt end has `stem` free tiles straight beyond it, none
            // another's belt end: the trunk's root, its back and the belt ahead of it
            let stem = self.stem_of.get(&(i, gi)).copied().unwrap_or(0);
            for step in 1..=stem {
                let s = match self.inward(i, at, t, -step) {
                    Some(s) => s,
                    None => break,
                };
                match self.idx(s) {
                    Some(ks) if ok(self.owner[ks]) && self.pinned.get(&s).map_or(true, |&o| o == i) => {}
                    _ => return false,
                }
            }
            self.inward(i, at, t, -1)
        } else {
            self.inward(i, at, t, 1)
        };
        if let Some(o) = o {
            match self.idx(o) {
                Some(ko) if ok(self.owner[ko]) => {}
                _ => return false,
            }
        }
        true
    }

    fn fits(&self, i: usize, at: At) -> bool {
        let tiles = self.tiles(i, at);
        for &t in &tiles {
            match self.idx(t) {
                Some(k)
                    if (self.owner[k] == -1 || self.owner[k] == i as i64)
                        && self.pinned.get(&t).map_or(true, |&o| o == i) => {}
                _ => return false,
            }
        }
        let own: FxHashSet<T> = tiles.iter().copied().collect();
        for (gi, g) in self.groups(i, at).iter().enumerate() {
            if !g.iter().any(|&t| !own.contains(&t) && self.usable(i, at, gi, t, true)) {
                return false;
            }
        }
        true
    }

    fn put(&mut self, i: usize, at: Option<At>) {
        if let Some(old) = self.at[i] {
            for t in self.tiles(i, old) {
                if let Some(k) = self.idx(t) {
                    self.owner[k] = -1;
                }
            }
            for g in self.groups(i, old) {
                if g.len() == 1 && self.pinned.get(&g[0]) == Some(&i) {
                    self.pinned.remove(&g[0]);
                }
            }
        }
        self.at[i] = at;
        if let Some(at) = at {
            for t in self.tiles(i, at) {
                if let Some(k) = self.idx(t) {
                    self.owner[k] = i as i64;
                }
            }
            for g in self.groups(i, at) {
                if g.len() == 1 {
                    self.pinned.insert(g[0], i);
                }
            }
        }
    }

    fn free_tiles(&self, i: usize, g: usize) -> Vec<T> {
        let at = match self.at[i] {
            Some(a) => a,
            None => return Vec::new(),
        };
        let group = &self.groups(i, at)[g];
        let mut out: Vec<T> = group.iter().copied().filter(|&t| self.usable(i, at, g, t, false)).collect();
        out.sort();
        out
    }

    fn field(&self, seeds: &[T], priced: bool) -> (Vec<i64>, Vec<i64>) {
        let owner = &self.owner;
        let free = |u: usize| owner[u] == -1;
        let price = if priced { Some(self.price.as_slice()) } else { None };
        run_field(self.x0, self.y0, self.w, self.h, &free, price, seeds, self.reach)
    }

    fn trace(pred: &[i64], mut k: i64) -> Vec<usize> {
        let mut out = Vec::new();
        while k >= 0 {
            out.push(k as usize);
            k = pred[k as usize];
        }
        out
    }

    /// (cost, routes, unreached term indexes) of net `n`: the nearest driver per consumer and the
    /// MST over the drivers, traced back.
    fn eval_net(&self, n: usize, priced: bool) -> (i64, Vec<Vec<usize>>, Vec<usize>) {
        let terms = &self.nets[n].2;
        let mut drivers: Vec<(usize, Vec<T>)> = Vec::new();
        let mut consumers: Vec<(usize, Vec<T>)> = Vec::new();
        for (ti, &(i, g, drv)) in terms.iter().enumerate() {
            if self.at[i].is_none() {
                continue;
            }
            let ts = self.free_tiles(i, g);
            if ts.is_empty() {
                continue;
            }
            if drv {
                drivers.push((ti, ts));
            } else {
                consumers.push((ti, ts));
            }
        }
        if drivers.is_empty() || consumers.is_empty() {
            return (0, Vec::new(), Vec::new());
        }
        let mut cost = 0i64;
        let mut routes = Vec::new();
        let mut unreached = Vec::new();
        let seeds: Vec<T> = drivers.iter().flat_map(|(_ti, ts)| ts.iter().copied()).collect();
        let (dist, pred) = self.field(&seeds, priced);
        for (ti, ts) in &consumers {
            let mut best: Option<(i64, usize)> = None;
            for &t in ts {
                let k = self.idx(t).unwrap();
                if dist[k] >= 0 && best.map_or(true, |b| dist[k] < b.0) {
                    best = Some((dist[k], k));
                }
            }
            match best {
                None => unreached.push(*ti),
                Some((d, k)) => {
                    cost += d;
                    routes.push(Self::trace(&pred, k as i64));
                }
            }
        }
        if drivers.len() > 1 {
            let fields: Vec<(Vec<i64>, Vec<i64>)> = drivers.iter().map(|(_ti, ts)| self.field(ts, priced)).collect();
            let mut in_tree: Vec<usize> = vec![0];
            while in_tree.len() < drivers.len() {
                let mut best: Option<(i64, usize, usize, usize)> = None;
                let mut sorted = in_tree.clone();
                sorted.sort();
                for &a in &sorted {
                    let da = &fields[a].0;
                    for b in 0..drivers.len() {
                        if in_tree.contains(&b) {
                            continue;
                        }
                        for &t in &drivers[b].1 {
                            let k = self.idx(t).unwrap();
                            if da[k] >= 0 {
                                let cand = (da[k], a, b, k);
                                if best.map_or(true, |bst| cand < bst) {
                                    best = Some(cand);
                                }
                            }
                        }
                    }
                }
                match best {
                    None => {
                        for b in 0..drivers.len() {
                            if !in_tree.contains(&b) {
                                unreached.push(drivers[b].0);
                            }
                        }
                        break;
                    }
                    Some((d, a, b, k)) => {
                        in_tree.push(b);
                        cost += d;
                        routes.push(Self::trace(&fields[a].1, k as i64));
                    }
                }
            }
        }
        (cost, routes, unreached)
    }

    /// Where an unplaced instance starts: the fitting (x, y, rot) nearest (weighted Manhattan) to
    /// its nets' placed partners, or nearest the box's centre; ties to the smaller (y, x, rot).
    fn manhattan_start(&self, i: usize) -> Option<At> {
        let mut partners: Vec<(i64, Vec<usize>, Vec<T>)> = Vec::new();
        for (_name, weight, terms) in self.nets {
            let mine: Vec<usize> = terms.iter().filter(|(ii, _g, _d)| *ii == i).map(|(_ii, g, _d)| *g).collect();
            if mine.is_empty() {
                continue;
            }
            let mut tiles: Vec<T> = Vec::new();
            for &(ii, g, _d) in terms {
                if ii != i {
                    if let Some(at) = self.at[ii] {
                        tiles.extend(self.groups(ii, at)[g].iter().copied());
                    }
                }
            }
            if !tiles.is_empty() {
                partners.push((*weight, mine, tiles));
            }
        }
        let (cx, cy) = (self.x0 * 2 + self.w, self.y0 * 2 + self.h);
        let mut best: Option<((i64, i64, i64, i64), At)> = None;
        for rot in 0..4i64 {
            let (tiles, groups) = &self.insts[i].1[rot as usize];
            if tiles.is_empty() {
                continue;
            }
            let fw = tiles.iter().map(|t| t.0).max().unwrap() + 1;
            let fh = tiles.iter().map(|t| t.1).max().unwrap() + 1;
            for y in self.y0..=(self.y0 + self.h - fh) {
                for x in self.x0..=(self.x0 + self.w - fw) {
                    let at = (x, y, rot);
                    let score = if !partners.is_empty() {
                        let mut s = 0i64;
                        for (wgt, mine, far) in &partners {
                            let mut near = i64::MAX;
                            for &g in mine {
                                for &(dx, dy) in &groups[g] {
                                    for &(fx, fy) in far {
                                        let d = (x + dx - fx).abs() + (y + dy - fy).abs();
                                        if d < near {
                                            near = d;
                                        }
                                    }
                                }
                            }
                            s += wgt * near;
                        }
                        s
                    } else {
                        (2 * x + fw - cx).abs() + (2 * y + fh - cy).abs()
                    };
                    let key = (score, y, x, rot);
                    if let Some((bk, _)) = best {
                        if key >= bk {
                            continue;
                        }
                    }
                    if self.fits(i, at) {
                        best = Some((key, at));
                    }
                }
            }
        }
        best.map(|(_k, at)| at)
    }
}

struct Full {
    costs: Vec<i64>,
    routes: Vec<Vec<Vec<usize>>>,
    u: Vec<i64>,
    lagr: i64,
    unreached: Vec<(usize, usize)>,
}

fn full(st: &State, priced: bool) -> Full {
    let nn = st.nets.len();
    let n_tiles = (st.w * st.h) as usize;
    let mut costs = Vec::with_capacity(nn);
    let mut routes = Vec::with_capacity(nn);
    let mut unreached = Vec::new();
    let mut u = vec![0i64; n_tiles];
    for n in 0..nn {
        let (c, rs, un) = st.eval_net(n, priced);
        costs.push(c);
        for ti in un {
            unreached.push((n, ti));
        }
        for r in &rs {
            for &k in r {
                u[k] += st.nets[n].1;
            }
        }
        routes.push(rs);
    }
    let mut lagr: i64 = (0..nn).map(|n| st.nets[n].1 * costs[n]).sum();
    for k in 0..n_tiles {
        if u[k] > 1 {
            lagr += st.price[k] * (u[k] - 1);
        }
    }
    Full { costs, routes, u, lagr, unreached }
}

/// fkcore.layout._place_py: -> (positions, before, after, hot tiles, sweeps, unreached).
/// `stems` (optional, per net) is the straight run of free tiles a net's consumer belt ends
/// demand beyond themselves (layout rule 5; the number is lanephys's, read through the spec).
/// `price` (optional, [(tile, milli-tiles)]) is where the price field starts above zero
/// (layout.Spec.price: the last build's fought-over tiles, `fk layout --from`).
#[pyfunction]
#[pyo3(signature = (bbox, blocked, insts, nets, params, stems=None, price=None))]
#[allow(clippy::type_complexity)]
pub fn place(
    bbox: (i64, i64, i64, i64),
    blocked: Vec<T>,
    insts: Vec<SInst>,
    nets: Vec<SNet>,
    params: (i64, i64, i64, i64, Vec<i64>),
    stems: Option<Vec<i64>>,
    price: Option<Vec<(T, i64)>>,
) -> PyResult<(Vec<Option<At>>, Vec<i64>, Vec<i64>, Vec<(T, i64)>, i64, Vec<(usize, usize)>)> {
    let (sweeps_cap, alpha, decay, reach, steps) = params;
    let steps = if steps.is_empty() { vec![1] } else { steps };
    let stems = stems.unwrap_or_default();
    let price = price.unwrap_or_default();
    let mut st = State::new(bbox, &blocked, &insts, &nets, reach, &stems, &price);
    for (i, inst) in insts.iter().enumerate() {
        if let Some(at) = inst.2 {
            st.put(i, Some(at));
        }
    }
    for (i, inst) in insts.iter().enumerate() {
        if inst.2.is_none() {
            if let Some(at) = st.manhattan_start(i) {
                st.put(i, Some(at));
            }
        }
    }
    let nn = nets.len();
    let n_tiles = (st.w * st.h) as usize;
    let f0 = full(&st, false);
    let before: Vec<i64> = (0..nn)
        .map(|n| if f0.unreached.iter().any(|&(k, _t)| k == n) { -1 } else { f0.costs[n] })
        .collect();
    let movable: Vec<usize> = (0..insts.len()).filter(|&i| insts[i].3 && st.at[i].is_some()).collect();
    let incident: Vec<Vec<usize>> = (0..insts.len())
        .map(|i| {
            let mut v: Vec<usize> = (0..nn).filter(|&n| nets[n].2.iter().any(|&(ii, _g, _d)| ii == i)).collect();
            v.sort();
            v
        })
        .collect();
    let mut cur_full = full(&st, true);
    let mut sweeps = 0i64;
    let mut step_i = 0usize;
    while sweeps < sweeps_cap {
        let s = steps[step_i];
        let mut deltas: Vec<T> = vec![(0, 0)];
        for k in [s, 2 * s] {
            for sx in [-1i64, 1] {
                deltas.push((sx * k, 0));
            }
        }
        for k in [s, 2 * s] {
            for sy in [-1i64, 1] {
                deltas.push((0, sy * k));
            }
        }
        let mut moved = false;
        for &i in &movable {
            let cur = st.at[i].unwrap();
            let mine = &incident[i];
            let mut u_base = cur_full.u.clone();
            for &n in mine {
                for r in &cur_full.routes[n] {
                    for &k in r {
                        u_base[k] -= nets[n].1;
                    }
                }
            }
            let mut base: i64 = (0..nn).filter(|n| !mine.contains(n)).map(|n| nets[n].1 * cur_full.costs[n]).sum();
            for k in 0..n_tiles {
                if u_base[k] > 1 {
                    base += st.price[k] * (u_base[k] - 1);
                }
            }
            let mut best: Option<((i64, i64, i64, i64, i64), At)> = None;
            for rot in 0..4i64 {
                for &(dx, dy) in &deltas {
                    let at = (cur.0 + dx, cur.1 + dy, rot);
                    if at == cur || !st.fits(i, at) {
                        continue;
                    }
                    st.put(i, Some(at));
                    let mut lagr_c = base;
                    let mut touched: Vec<(usize, i64)> = Vec::new();
                    for &n in mine {
                        let wgt = nets[n].1;
                        let (c, rs, _un) = st.eval_net(n, true);
                        lagr_c += wgt * c;
                        for r in &rs {
                            for &k in r {
                                let old = u_base[k];
                                u_base[k] = old + wgt;
                                touched.push((k, wgt));
                                lagr_c += st.price[k] * ((old + wgt - 1).max(0) - (old - 1).max(0));
                            }
                        }
                    }
                    for &(k, wgt) in &touched {
                        u_base[k] -= wgt;
                    }
                    st.put(i, Some(cur));
                    let key = (lagr_c, dx.abs() + dy.abs(), rot, dy, dx);
                    if best.map_or(true, |(bk, _)| key < bk) {
                        best = Some((key, at));
                    }
                }
            }
            if let Some((bk, at)) = best {
                if bk.0 < cur_full.lagr {
                    st.put(i, Some(at));
                    cur_full = full(&st, true);
                    moved = true;
                }
            }
        }
        sweeps += 1;
        for k in 0..n_tiles {
            if cur_full.u[k] > 1 {
                st.price[k] += alpha * (cur_full.u[k] - 1);
            } else {
                st.price[k] = st.price[k] * decay / MILLI;
            }
        }
        cur_full = full(&st, true);
        if !moved {
            if step_i + 1 < steps.len() {
                step_i += 1;
            } else {
                break;
            }
        }
    }
    let f1 = full(&st, false);
    let after: Vec<i64> = (0..nn)
        .map(|n| if f1.unreached.iter().any(|&(k, _t)| k == n) { -1 } else { f1.costs[n] })
        .collect();
    let mut hot: Vec<(T, i64)> = (0..n_tiles)
        .filter(|&k| f1.u[k] > 1)
        .map(|k| ((k as i64 % st.w + st.x0, k as i64 / st.w + st.y0), f1.u[k]))
        .collect();
    hot.sort_by_key(|&((x, y), u)| (-u, y, x));
    let mut unreached = f1.unreached.clone();
    unreached.sort();
    Ok((st.at.clone(), before, after, hot, sweeps, unreached))
}
