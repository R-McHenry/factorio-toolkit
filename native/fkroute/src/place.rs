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

// -- the sweep over seeds: fkcore.territory._place_seeds_py (PLAN-ORGANIC part T) -----------------
//
// The same loop over a coarse grid of territory cells (territory.rs: the power diagram), the walk
// between ports on their cells' boundaries, the Lagrangian price; `place` above stays the
// instance-level layout.

use crate::territory::{runs_of, Diagram, Grid, Rect};
use std::collections::BTreeMap;

/// One seed: name, declared size, need, min width, at, movable, ports (name, side, pos).
type SSeed = (String, (i64, i64), i64, i64, Option<At>, bool, Vec<(String, String, Option<i64>)>);
/// One world net: name, weight in belts, terms (seed or -1 for an edge, port or edge index, driver).
type WNet = (String, i64, Vec<(i64, i64, bool)>);
/// sweeps, alpha, decay, reach, steps, cells, final_cell, trespass, iters, tol, plateau.
type WParams = (i64, i64, i64, i64, Vec<i64>, Vec<i64>, i64, i64, i64, i64, i64);

fn side_idx(s: &str) -> usize {
    match s {
        "n" => 0,
        "e" => 1,
        "s" => 2,
        _ => 3,
    }
}

fn seed_point(at: At, size: (i64, i64)) -> (i64, i64) {
    let (w, h) = if at.2.rem_euclid(2) == 0 { size } else { (size.1, size.0) };
    (2 * at.0 + w, 2 * at.1 + h)
}

fn turned_box(at: At, size: (i64, i64)) -> Rect {
    let (w, h) = if at.2.rem_euclid(2) == 0 { size } else { (size.1, size.0) };
    (at.0, at.1, at.0 + w, at.1 + h)
}

fn turn_tile(px: i64, py: i64, rot: i64, size: (i64, i64)) -> (i64, i64) {
    let (w, h) = size;
    match rot.rem_euclid(4) {
        0 => (px, py),
        1 => (h - 1 - py, px),
        2 => (w - 1 - px, h - 1 - py),
        _ => (py, w - 1 - px),
    }
}

fn overlap(a: Rect, b: Rect) -> bool {
    a.0 < b.2 && b.0 < a.2 && a.1 < b.3 && b.1 < a.3
}

struct WSeed {
    size: (i64, i64),
    movable: bool,
    ports: Vec<(usize, Option<i64>)>,
}

/// A windowed walk field: distances and predecessors over the window's cells, -1 where unreached.
struct WField {
    i0: i64,
    j0: i64,
    ww: i64,
    wh: i64,
    gw: i64,
    dist: Vec<i64>,
    pred: Vec<i64>,
}

impl WField {
    #[inline]
    fn local(&self, k: usize) -> Option<usize> {
        let (x, y) = (k as i64 % self.gw - self.i0, k as i64 / self.gw - self.j0);
        if 0 <= x && x < self.ww && 0 <= y && y < self.wh {
            Some((y * self.ww + x) as usize)
        } else {
            None
        }
    }

    fn get(&self, k: usize) -> Option<i64> {
        match self.local(k) {
            Some(l) if self.dist[l] >= 0 => Some(self.dist[l]),
            _ => None,
        }
    }

    fn trace(&self, k: usize) -> Vec<usize> {
        let mut out = Vec::new();
        let mut k = k as i64;
        while k >= 0 {
            out.push(k as usize);
            k = match self.local(k as usize) {
                Some(l) => self.pred[l],
                None => -1,
            };
        }
        out
    }
}

struct WorldFull {
    costs: Vec<i64>,
    routes: Vec<Vec<Vec<usize>>>,
    u: Vec<i64>,
    lagr: i64,
    unreached: Vec<(usize, usize)>,
}

struct World<'a> {
    bbox: Rect,
    blocked: Vec<Rect>,
    seeds: Vec<WSeed>,
    nets: &'a [WNet],
    edges: Vec<(usize, Option<i64>)>,
    reach: i64,
    trespass: i64,
    lat: i64,
    edge_tiles: Vec<T>,
    penalty: i64,
    at: Vec<Option<At>>,
    weights: Vec<i64>,
    grid: Grid,
    dia: Diagram,
    price: Vec<i64>,
}

impl<'a> World<'a> {
    fn new(bbox: Rect, blocked: Vec<Rect>, sseeds: &[SSeed], nets: &'a [WNet], edges: &[(String, String, Option<i64>)], reach: i64, trespass: i64, lat: i64, c: i64) -> Self {
        let seeds: Vec<WSeed> = sseeds
            .iter()
            .map(|s| WSeed { size: s.1, movable: s.5, ports: s.6.iter().map(|p| (side_idx(&p.1), p.2)).collect() })
            .collect();
        let at: Vec<Option<At>> = sseeds.iter().map(|s| s.4).collect();
        let n = seeds.len();
        let grid = Grid::new(bbox, c);
        let dia = Diagram::new(&grid, &blocked, &vec![None; n], &vec![0; n]);
        let (bx0, by0, bx1, by1) = bbox;
        let mut edge_tiles: Vec<T> = Vec::new();
        for e in edges {
            if let Some(pos) = e.2 {
                let d = side_idx(&e.1);
                let t = if d == 0 || d == 2 {
                    (bx0 + pos, if d == 0 { by0 } else { by1 - 1 })
                } else {
                    (if d == 3 { bx0 } else { bx1 - 1 }, by0 + pos)
                };
                edge_tiles.push(t);
                edge_tiles.push((t.0 - DX[d], t.1 - DY[d]));
            }
        }
        let mut w = World {
            bbox,
            blocked,
            seeds,
            nets,
            edges: edges.iter().map(|e| (side_idx(&e.1), e.2)).collect(),
            reach,
            trespass,
            lat,
            edge_tiles,
            penalty: 2 * ((bx1 - bx0) + (by1 - by0)) * MILLI,
            at,
            weights: vec![0; n],
            grid,
            dia,
            price: Vec::new(),
        };
        w.set_cell(c, false);
        w
    }

    /// The grid at `c` tiles a cell; the price carried over by tile.
    fn set_cell(&mut self, c: i64, carry: bool) {
        let grid = Grid::new(self.bbox, c);
        let mut price = vec![0i64; grid.n];
        if carry {
            for (k, p) in price.iter_mut().enumerate() {
                let (x, y) = grid.tile(k);
                if let Some(ok) = self.grid.cell_of(x, y) {
                    *p = self.price[ok];
                }
            }
        }
        let fixed: Vec<Option<Rect>> = self
            .seeds
            .iter()
            .zip(&self.at)
            .map(|(sd, a)| match a {
                Some(a) if !sd.movable => Some(turned_box(*a, sd.size)),
                _ => None,
            })
            .collect();
        let mut dia = Diagram::new(&grid, &self.blocked, &fixed, &self.weights);
        dia.points = self.seeds.iter().zip(&self.at).map(|(sd, a)| a.map(|a| seed_point(a, sd.size))).collect();
        dia.frames = self
            .seeds
            .iter()
            .zip(&self.at)
            .map(|(sd, a)| match a {
                Some(a) if sd.movable => Some(turned_box(*a, sd.size)),
                _ => None,
            })
            .collect();
        dia.recompute(&grid, None);
        self.grid = grid;
        self.dia = dia;
        self.price = price;
    }

    fn fits(&self, i: usize, at: At) -> bool {
        let sd = &self.seeds[i];
        let b = turned_box(at, sd.size);
        let (bx0, by0, bx1, by1) = self.bbox;
        if b.0 < bx0 || b.1 < by0 || b.2 > bx1 || b.3 > by1 {
            return false;
        }
        if self.blocked.iter().any(|&r| overlap(b, r)) {
            return false;
        }
        let mut others: Vec<Rect> = Vec::new();
        for (j, a) in self.at.iter().enumerate() {
            if j == i {
                continue;
            }
            if let Some(a) = a {
                let o = turned_box(*a, self.seeds[j].size);
                if overlap(b, o) {
                    return false;
                }
                others.push(o);
            }
        }
        if self.edge_tiles.iter().any(|&(tx, ty)| b.0 <= tx && tx < b.2 && b.1 <= ty && ty < b.3) {
            return false;
        }
        let (w, h) = sd.size;
        let rot = at.2.rem_euclid(4);
        for &(side, pos) in &sd.ports {
            let pos = match pos {
                Some(p) => p,
                None => continue,
            };
            let (px, py) = match side {
                0 => (pos, 0),
                2 => (pos, h - 1),
                3 => (0, pos),
                _ => (w - 1, pos),
            };
            let (tx, ty) = turn_tile(px, py, rot, (w, h));
            let d = (side + rot as usize) % 4;
            let (ox, oy) = (at.0 + tx + DX[d], at.1 + ty + DY[d]);
            let (fx, fy) = (ox + DX[d], oy + DY[d]);
            if !(bx0 <= fx && fx < bx1 && by0 <= fy && fy < by1) {
                return false;
            }
            if self.blocked.iter().chain(others.iter()).any(|r| r.0 <= ox && ox < r.2 && r.1 <= oy && oy < r.3) {
                return false;
            }
        }
        true
    }

    /// The turned frames of the placed seeds: sealed, so no belt of the scope crosses them.
    fn claims(&self) -> Vec<Rect> {
        self.seeds.iter().zip(&self.at).filter_map(|(sd, a)| a.map(|a| turned_box(a, sd.size))).collect()
    }

    fn mv(&mut self, i: usize, at: Option<At>) {
        self.at[i] = at;
        let sd = &self.seeds[i];
        self.dia.points[i] = at.map(|a| seed_point(a, sd.size));
        self.dia.frames[i] = match at {
            Some(a) if sd.movable => Some(turned_box(a, sd.size)),
            _ => None,
        };
    }

    /// The cell of `ks` nearest `point` (half-tiles; None: the first), ties to the smaller index.
    fn nearest(&self, ks: &[usize], point: Option<(i64, i64)>) -> Option<usize> {
        if ks.is_empty() {
            return None;
        }
        match point {
            None => ks.iter().copied().min(),
            Some((px, py)) => {
                let mut best: Option<((i64, usize), usize)> = None;
                for &k in ks {
                    let (cx, cy) = self.grid.centre(k);
                    let key = ((cx - px) * (cx - px) + (cy - py) * (cy - py), k);
                    if best.map_or(true, |(bk, _)| key < bk) {
                        best = Some((key, k));
                    }
                }
                best.map(|(_k, k)| k)
            }
        }
    }

    fn owned(&self, who: i64) -> Vec<usize> {
        (0..self.grid.n).filter(|&k| self.dia.owner[k] == who).collect()
    }

    /// The grid cell of a terminal, and whether a pinned port fell off its cell.
    fn term_cell(&self, term: (i64, i64, bool), partner: Option<(i64, i64)>) -> (Option<usize>, bool) {
        let grid = &self.grid;
        let (who, idx, _drv) = term;
        if who < 0 {
            let (side, pos) = self.edges[idx as usize];
            let ks: Vec<usize> = if side == 0 || side == 2 {
                let y = if side == 0 { grid.y0 } else { grid.y1 - 1 };
                if let Some(pos) = pos {
                    return (grid.cell_of(grid.x0 + pos, y), false);
                }
                (0..grid.gw as usize).filter_map(|ii| grid.cell_of(grid.xa[ii], y)).collect()
            } else {
                let x = if side == 3 { grid.x0 } else { grid.x1 - 1 };
                if let Some(pos) = pos {
                    return (grid.cell_of(x, grid.y0 + pos), false);
                }
                (0..grid.gh as usize).filter_map(|jj| grid.cell_of(x, grid.ya[jj])).collect()
            };
            let ks: Vec<usize> = ks.into_iter().filter(|&k| !self.dia.wall[k]).collect();
            return (self.nearest(&ks, partner), false);
        }
        // 43-territory: the port stands where its belt leaves the frame (the tile outside a
        // pinned port; unpinned, outside the frame's side nearest the partner), as
        // fkcore.territory._World.term_cell
        let who_u = who as usize;
        let at = match self.at[who_u] {
            Some(a) => a,
            None => return (None, false),
        };
        let sd = &self.seeds[who_u];
        let (side, pos) = sd.ports[idx as usize];
        let rot = at.2.rem_euclid(4);
        let d = (side + rot as usize) % 4;
        let (w, h) = sd.size;
        if let Some(pos) = pos {
            let (px, py) = match side {
                0 => (pos, 0),
                2 => (pos, h - 1),
                3 => (0, pos),
                _ => (w - 1, pos),
            };
            let (tx, ty) = turn_tile(px, py, rot, (w, h));
            let k = grid.cell_of(at.0 + tx + DX[d], at.1 + ty + DY[d]);
            return (k, k.is_none());
        }
        let (x0, y0, x1, y1) = turned_box(at, sd.size);
        let tiles: Vec<T> = match d {
            0 => (x0..x1).map(|x| (x, y0 - 1)).collect(),
            2 => (x0..x1).map(|x| (x, y1)).collect(),
            3 => (y0..y1).map(|y| (x0 - 1, y)).collect(),
            _ => (y0..y1).map(|y| (x1, y)).collect(),
        };
        let mut ks: Vec<usize> = tiles.iter().filter_map(|&(x, y)| grid.cell_of(x, y)).collect();
        ks.sort();
        ks.dedup();
        (self.nearest(&ks, partner), false)
    }

    /// Where edge terminal `idx` stands for a seed at `point`: its pinned tile's centre, else the
    /// point of its side nearest `point` (the side's middle when None), in half-tiles.
    fn edge_point(&self, idx: usize, point: Option<(i64, i64)>) -> (i64, i64) {
        let (side, pos) = self.edges[idx];
        let (x0, y0, x1, y1) = self.bbox;
        if side == 0 || side == 2 {
            let y = if side == 0 { 2 * y0 + 1 } else { 2 * y1 - 1 };
            if let Some(pos) = pos {
                return (2 * (x0 + pos) + 1, y);
            }
            return (point.map_or(x0 + x1, |p| p.0.max(2 * x0 + 1).min(2 * x1 - 1)), y);
        }
        let x = if side == 3 { 2 * x0 + 1 } else { 2 * x1 - 1 };
        if let Some(pos) = pos {
            return (x, 2 * (y0 + pos) + 1);
        }
        (x, point.map_or(y0 + y1, |p| p.1.max(2 * y0 + 1).min(2 * y1 - 1)))
    }

    /// Where port `idx` of placed seed `who` stands, in half-tiles: its pinned tile's centre in
    /// the turned frame, else the seed's point.
    fn port_point(&self, who: usize, idx: usize) -> (i64, i64) {
        let at = self.at[who].unwrap();
        let sd = &self.seeds[who];
        let (side, pos) = sd.ports[idx];
        let pos = match pos {
            Some(p) => p,
            None => return seed_point(at, sd.size),
        };
        let (w, h) = sd.size;
        let (px, py) = match side {
            0 => (pos, 0),
            2 => (pos, h - 1),
            3 => (0, pos),
            _ => (w - 1, pos),
        };
        let (tx, ty) = turn_tile(px, py, at.2.rem_euclid(4), (w, h));
        (2 * (at.0 + tx) + 1, 2 * (at.1 + ty) + 1)
    }

    fn term_partner(&self, n: usize, ti: usize) -> Option<(i64, i64)> {
        let terms = &self.nets[n].2;
        let who_me = terms[ti].0;
        let me = if who_me >= 0 && self.at[who_me as usize].is_some() { Some(self.port_point(who_me as usize, terms[ti].1 as usize)) } else { None };
        let mut best: Option<((bool, usize), (i64, i64))> = None;
        for (tj, &(who, idx, drv)) in terms.iter().enumerate() {
            if tj == ti {
                continue;
            }
            let pt = if who >= 0 {
                match self.at[who as usize] {
                    Some(_) => self.port_point(who as usize, idx as usize),
                    None => continue,
                }
            } else {
                self.edge_point(idx as usize, me)
            };
            let key = (!drv, tj);
            if best.map_or(true, |(bk, _)| key < bk) {
                best = Some((key, pt));
            }
        }
        best.map(|(_k, p)| p)
    }

    fn terminals(&self, n: usize) -> Vec<(Option<usize>, bool)> {
        (0..self.nets[n].2.len()).map(|ti| self.term_cell(self.nets[n].2[ti], self.term_partner(n, ti))).collect()
    }

    /// The window round cells `ks`: their bounding box grown by a margin, (i0, j0, i1, j1).
    fn window(&self, ks: &[usize]) -> (i64, i64, i64, i64) {
        let grid = &self.grid;
        let margin = 6.max((grid.gw + grid.gh) / 12);
        let xs = ks.iter().map(|&k| k as i64 % grid.gw);
        let ys = ks.iter().map(|&k| k as i64 / grid.gw);
        let (xmin, xmax) = (xs.clone().min().unwrap(), xs.max().unwrap());
        let (ymin, ymax) = (ys.clone().min().unwrap(), ys.max().unwrap());
        (0.max(xmin - margin), 0.max(ymin - margin), (grid.gw - 1).min(xmax + margin), (grid.gh - 1).min(ymax + margin))
    }

    /// Dijkstra over the grid's cells inside `win`, as the Python heap orders (d, x, y); a cell
    /// inside a placed seed's frame is closed unless it is one of the `goals`; a cell a seed not
    /// in `own` holds costs `trespass`.
    fn field(&self, seeds: &[usize], win: (i64, i64, i64, i64), priced: bool, goals: &[usize], own: &[i64]) -> WField {
        let grid = &self.grid;
        let (i0, j0, i1, j1) = win;
        let gw = grid.gw;
        let reach = if grid.c <= self.reach { 1.max(self.reach / grid.c) } else { 1 };
        let step = grid.c * MILLI;
        let frames = self.claims();
        let open = |u: usize| -> bool {
            if self.dia.owner[u] == -2 {
                return false;
            }
            if goals.contains(&u) {
                return true;
            }
            let (cx, cy) = grid.centre(u);
            !frames.iter().any(|r| 2 * r.0 <= cx && cx < 2 * r.2 && 2 * r.1 <= cy && cy < 2 * r.3)
        };
        let mut f = WField { i0, j0, ww: i1 - i0 + 1, wh: j1 - j0 + 1, gw, dist: Vec::new(), pred: Vec::new() };
        f.dist = vec![-1; (f.ww * f.wh) as usize];
        f.pred = vec![-1; (f.ww * f.wh) as usize];
        let mut sorted: Vec<usize> = seeds.to_vec();
        sorted.sort();
        sorted.dedup();
        let mut heap: BinaryHeap<Reverse<(i64, i64, i64)>> = BinaryHeap::new();
        for &k in &sorted {
            if let Some(l) = f.local(k) {
                f.dist[l] = 0;
                f.pred[l] = -1;
                heap.push(Reverse((0, k as i64 % gw, k as i64 / gw)));
            }
        }
        while let Some(Reverse((d, x, y))) = heap.pop() {
            let k = (y * gw + x) as usize;
            let lk = f.local(k).unwrap();
            if d > f.dist[lk] {
                continue;
            }
            for hd in 0..4usize {
                for j in 1..=reach {
                    let (ux, uy) = (x + DX[hd] * j, y + DY[hd] * j);
                    if !(i0 <= ux && ux <= i1 && j0 <= uy && uy <= j1) {
                        break;
                    }
                    let u = (uy * gw + ux) as usize;
                    if open(u) {
                        let mut nd = d + j * step;
                        if priced {
                            let o = self.dia.owner[u];
                            nd += self.price[u] + if o >= 0 && !own.contains(&o) { self.trespass * grid.c } else { 0 };
                        }
                        let lu = f.local(u).unwrap();
                        if f.dist[lu] < 0 || nd < f.dist[lu] {
                            f.dist[lu] = nd;
                            f.pred[lu] = k as i64;
                            heap.push(Reverse((nd, ux, uy)));
                        }
                        break;
                    }
                }
            }
        }
        f
    }

    /// (cost, route cells, unreached term indexes, off-frame term indexes) of net `n`.
    fn eval_net(&self, n: usize, priced: bool) -> (i64, Vec<Vec<usize>>, Vec<usize>, Vec<usize>) {
        let terms = &self.nets[n].2;
        let cells = self.terminals(n);
        let mut drivers: Vec<(usize, usize)> = Vec::new();
        let mut consumers: Vec<(usize, usize)> = Vec::new();
        let mut off = Vec::new();
        let mut lost = Vec::new();
        for (ti, ((k, o), &(who, _idx, drv))) in cells.iter().zip(terms).enumerate() {
            if *o {
                off.push(ti);
            }
            match k {
                Some(k) => {
                    if drv {
                        drivers.push((ti, *k));
                    } else {
                        consumers.push((ti, *k));
                    }
                }
                None => {
                    if who < 0 || self.at[who as usize].is_some() {
                        lost.push(ti);
                    }
                }
            }
        }
        let mut cost = self.penalty * lost.len() as i64;
        if drivers.is_empty() || consumers.is_empty() {
            return (cost, Vec::new(), lost, off);
        }
        let all: Vec<usize> = drivers.iter().chain(consumers.iter()).map(|&(_ti, k)| k).collect();
        let win = self.window(&all);
        let mut routes = Vec::new();
        let mut unreached = lost;
        let seeds: Vec<usize> = drivers.iter().map(|&(_ti, k)| k).collect();
        let own: Vec<i64> = terms.iter().filter(|t| t.0 >= 0).map(|t| t.0).collect();
        let f = self.field(&seeds, win, priced, &all, &own);
        for &(ti, k) in &consumers {
            match f.get(k) {
                Some(d) => {
                    cost += d;
                    routes.push(f.trace(k));
                }
                None => {
                    unreached.push(ti);
                    cost += self.penalty;
                }
            }
        }
        if drivers.len() > 1 {
            let fields: Vec<WField> = drivers.iter().map(|&(_ti, k)| self.field(&[k], win, priced, &all, &own)).collect();
            let mut in_tree: Vec<usize> = vec![0];
            while in_tree.len() < drivers.len() {
                let mut best: Option<(i64, usize, usize)> = None;
                let mut sorted = in_tree.clone();
                sorted.sort();
                for &a in &sorted {
                    for b in 0..drivers.len() {
                        if in_tree.contains(&b) {
                            continue;
                        }
                        if let Some(d) = fields[a].get(drivers[b].1) {
                            let cand = (d, a, b);
                            if best.map_or(true, |bst| cand < bst) {
                                best = Some(cand);
                            }
                        }
                    }
                }
                match best {
                    None => {
                        for b in 0..drivers.len() {
                            if !in_tree.contains(&b) {
                                unreached.push(drivers[b].0);
                                cost += self.penalty;
                            }
                        }
                        break;
                    }
                    Some((d, a, b)) => {
                        in_tree.push(b);
                        cost += d;
                        routes.push(fields[a].trace(drivers[b].1));
                    }
                }
            }
        }
        (cost, routes, unreached, off)
    }

    /// Where an unplaced seed starts: the fitting corner and rotation on the first step's lattice
    /// nearest its nets' placed partners (weighted Manhattan, half-tiles; an unpinned edge port
    /// as the distance to its side), or nearest the box's centre; ties to the smaller (y, x, rot).
    fn start(&self, i: usize) -> Option<At> {
        let mut partners: Vec<(i64, Vec<(i64, i64)>, Vec<usize>)> = Vec::new();
        for (_name, weight, terms) in self.nets {
            if !terms.iter().any(|t| t.0 == i as i64) {
                continue;
            }
            let mut far = Vec::new();
            let mut sides = Vec::new();
            for &(who, idx, _drv) in terms {
                if who == i as i64 {
                    continue;
                }
                if who >= 0 {
                    if let Some(a) = self.at[who as usize] {
                        far.push(seed_point(a, self.seeds[who as usize].size));
                    }
                } else {
                    let (side, pos) = self.edges[idx as usize];
                    if pos.is_none() {
                        sides.push(side);
                    } else {
                        far.push(self.edge_point(idx as usize, None));
                    }
                }
            }
            if !far.is_empty() || !sides.is_empty() {
                partners.push((*weight, far, sides));
            }
        }
        let (bx0, by0, bx1, by1) = self.bbox;
        let (cx, cy) = (bx0 + bx1, by0 + by1);
        let mut lat = self.lat;
        loop {
            let best = self.start_on(i, lat, &partners, cx, cy);
            if best.is_some() || lat <= 1 {
                return best;
            }
            lat /= 2; // a lattice too coarse for the box: finer until something fits
        }
    }

    #[allow(clippy::type_complexity)]
    fn start_on(&self, i: usize, lat: i64, partners: &[(i64, Vec<(i64, i64)>, Vec<usize>)], cx: i64, cy: i64) -> Option<At> {
        let (bx0, by0, bx1, by1) = self.bbox;
        let mut best: Option<((i64, i64, i64, i64), At)> = None;
        for rot in 0..4i64 {
            let size = self.seeds[i].size;
            let (w, h) = if rot % 2 == 0 { size } else { (size.1, size.0) };
            let mut y = by0;
            while y <= by1 - h {
                let mut x = bx0;
                while x <= bx1 - w {
                    let (sx, sy) = (2 * x + w, 2 * y + h);
                    let score = if !partners.is_empty() {
                        let mut s = 0i64;
                        for (wgt, far, sides) in partners {
                            let mut m = i64::MAX;
                            for &(fx, fy) in far {
                                m = m.min((sx - fx).abs() + (sy - fy).abs());
                            }
                            for &sd in sides {
                                let d = match sd {
                                    0 => sy - 2 * by0,
                                    1 => 2 * bx1 - sx,
                                    2 => 2 * by1 - sy,
                                    _ => sx - 2 * bx0,
                                };
                                m = m.min(d);
                            }
                            s += wgt * m;
                        }
                        s
                    } else {
                        (sx - cx).abs() + (sy - cy).abs()
                    };
                    let key = (score, y, x, rot);
                    let skip = best.map_or(false, |(bk, _)| key >= bk);
                    if !skip && self.fits(i, (x, y, rot)) {
                        best = Some((key, (x, y, rot)));
                    }
                    x += lat;
                }
                y += lat;
            }
        }
        best.map(|(_k, at)| at)
    }

    fn full(&self, priced: bool) -> WorldFull {
        let nn = self.nets.len();
        let mut costs = Vec::with_capacity(nn);
        let mut routes = Vec::with_capacity(nn);
        let mut unreached = Vec::new();
        let mut u = vec![0i64; self.grid.n];
        for n in 0..nn {
            let (c, rs, un, _of) = self.eval_net(n, priced);
            costs.push(c);
            for ti in un {
                unreached.push((n, ti));
            }
            for r in &rs {
                for &k in r {
                    u[k] += self.nets[n].1;
                }
            }
            routes.push(rs);
        }
        let mut lagr: i64 = (0..nn).map(|n| self.nets[n].1 * costs[n]).sum();
        for k in 0..self.grid.n {
            if u[k] > 1 {
                lagr += self.price[k] * (u[k] - 1);
            }
        }
        WorldFull { costs, routes, u, lagr, unreached }
    }
}

/// fkcore.territory._place_seeds_py: -> (at, cells as row runs, areas, weights, ports, before,
/// after, hot, sweeps, unreached).
#[pyfunction]
#[allow(clippy::type_complexity)]
pub fn place_seeds(
    bbox: Rect,
    blocked: Vec<Rect>,
    seeds: Vec<SSeed>,
    nets: Vec<WNet>,
    edges: Vec<(String, String, Option<i64>)>,
    params: WParams,
) -> PyResult<(
    Vec<Option<At>>,
    Vec<Vec<(i64, i64, i64)>>,
    Vec<i64>,
    Vec<i64>,
    Vec<((i64, i64), (i64, i64))>,
    Vec<i64>,
    Vec<i64>,
    Vec<((i64, i64), i64)>,
    i64,
    Vec<(i64, i64)>,
)> {
    let (sweeps_cap, alpha, decay, reach, steps, cells, final_cell, trespass, iters, tol, plateau) = params;
    let steps = if steps.is_empty() { vec![1] } else { steps };
    let cells = if cells.is_empty() { vec![1] } else { cells };
    let needs: Vec<i64> = seeds.iter().map(|s| s.2).collect();
    let mut st = World::new(bbox, blocked, &seeds, &nets, &edges, reach, trespass, steps[0], cells[0]);
    for i in 0..seeds.len() {
        if st.at[i].is_none() {
            if let Some(at) = st.start(i) {
                st.mv(i, Some(at));
            }
        }
    }
    st.dia.adapt(&st.grid, &needs, iters, tol);
    st.weights = st.dia.weights.clone();
    let nn = nets.len();
    let f0 = st.full(false);
    let before: Vec<i64> = (0..nn).map(|n| if f0.unreached.iter().any(|&(k, _t)| k == n) { -1 } else { f0.costs[n] }).collect();
    let movable: Vec<usize> = (0..seeds.len()).filter(|&i| seeds[i].5 && st.at[i].is_some()).collect();
    let incident: Vec<Vec<usize>> = (0..seeds.len())
        .map(|i| {
            let mut v: Vec<usize> = (0..nn).filter(|&n| nets[n].2.iter().any(|&(w, _i, _d)| w == i as i64)).collect();
            v.sort();
            v
        })
        .collect();
    let mut cur = st.full(true);
    let mut sweeps = 0i64;
    let mut step_i = 0usize;
    // the plateau rule (43-territory): per step; on the finest step it ends the loop
    let mut best_lagr: Option<i64> = None;
    let mut stale = 0i64;
    let trace = std::env::var_os("FK_TRACE_SEEDS").is_some();
    while sweeps < sweeps_cap {
        let s = steps[step_i];
        let c = cells[step_i.min(cells.len() - 1)];
        if c != st.grid.c {
            st.set_cell(c, true);
            st.dia.adapt(&st.grid, &needs, iters, tol);
            st.weights = st.dia.weights.clone();
            cur = st.full(true);
        }
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
            let cur_at = st.at[i].unwrap();
            let mine = &incident[i];
            let mut u_base = cur.u.clone();
            for &n in mine {
                for r in &cur.routes[n] {
                    for &k in r {
                        u_base[k] -= nets[n].1;
                    }
                }
            }
            let mut base: i64 = (0..nn).filter(|n| !mine.contains(n)).map(|n| nets[n].1 * cur.costs[n]).sum();
            for k in 0..st.grid.n {
                if u_base[k] > 1 {
                    base += st.price[k] * (u_base[k] - 1);
                }
            }
            let mut best: Option<((i64, i64, i64, i64, i64), At)> = None;
            let owner0 = st.dia.owner.clone();
            let areas0 = st.dia.areas.clone();
            let own_cells: Vec<usize> = (0..st.grid.n).filter(|&k| owner0[k] == i as i64).collect();
            // 43-territory: the four rotations on the coarse steps (8 and up) only
            let rots: Vec<i64> = if s >= 8 { vec![0, 1, 2, 3] } else { vec![cur_at.2.rem_euclid(4)] };
            for &rot in &rots {
                for &(dx, dy) in &deltas {
                    let at = (cur_at.0 + dx, cur_at.1 + dy, rot);
                    if at == cur_at || !st.fits(i, at) {
                        continue;
                    }
                    st.mv(i, Some(at));
                    let mut ks = own_cells.clone();
                    ks.extend(st.grid.overlaps(turned_box(at, st.seeds[i].size)));
                    if ks.is_empty() {
                        st.dia.recompute(&st.grid, None);
                    } else {
                        let (i0, j0, i1, j1) = st.window(&ks);
                        let win: Vec<usize> = (j0..=j1).flat_map(|j| (i0..=i1).map(move |ii| (j * st.grid.gw + ii) as usize)).collect();
                        st.dia.recompute(&st.grid, Some(&win));
                    }
                    let mut lagr_c = base;
                    let mut touched: Vec<(usize, i64)> = Vec::new();
                    for &n in mine {
                        let wgt = nets[n].1;
                        let (cst, rs, _un, _of) = st.eval_net(n, true);
                        lagr_c += wgt * cst;
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
                    st.mv(i, Some(cur_at));
                    st.dia.owner.copy_from_slice(&owner0);
                    st.dia.areas.copy_from_slice(&areas0);
                    let key = (lagr_c, dx.abs() + dy.abs(), rot, dy, dx);
                    if best.map_or(true, |(bk, _)| key < bk) {
                        best = Some((key, at));
                    }
                }
            }
            if let Some((bk, at)) = best {
                if bk.0 < cur.lagr {
                    st.mv(i, Some(at));
                    st.dia.recompute(&st.grid, None);
                    // 43-territory: only the moved seed's nets are routed again, as the Python
                    let mut lagr = base;
                    for &n in mine {
                        let wgt = nets[n].1;
                        let (cst, rs, _un, _of) = st.eval_net(n, true);
                        cur.costs[n] = cst;
                        lagr += wgt * cst;
                        for r in &rs {
                            for &k in r {
                                let old = u_base[k];
                                u_base[k] = old + wgt;
                                lagr += st.price[k] * ((old + wgt - 1).max(0) - (old - 1).max(0));
                            }
                        }
                        cur.routes[n] = rs;
                    }
                    cur.u = u_base;
                    cur.lagr = lagr;
                    moved = true;
                }
            }
        }
        sweeps += 1;
        st.dia.adapt(&st.grid, &needs, iters, tol);
        st.weights = st.dia.weights.clone();
        for k in 0..st.grid.n {
            if cur.u[k] > 1 {
                st.price[k] += alpha * (cur.u[k] - 1);
            } else {
                st.price[k] = st.price[k] * decay / MILLI;
            }
        }
        cur = st.full(true);
        if trace {
            eprintln!("sweep {} step {} cell {} moved {} lagr {} unpriced {}", sweeps, s, st.grid.c, moved, cur.lagr, (0..nn).map(|n| nets[n].1 * cur.costs[n]).sum::<i64>());
        }
        if best_lagr.map_or(true, |b| cur.lagr < b) {
            best_lagr = Some(cur.lagr);
            stale = 0;
        } else {
            stale += 1;
        }
        if !moved || (plateau > 0 && stale >= plateau) {
            if step_i + 1 < steps.len() {
                step_i += 1;
                best_lagr = None;
                stale = 0;
            } else {
                break;
            }
        }
    }
    if st.grid.c != final_cell {
        st.set_cell(final_cell, true);
        st.dia.adapt(&st.grid, &needs, iters, tol);
        st.weights = st.dia.weights.clone();
    }
    let f1 = st.full(false);
    let after: Vec<i64> = (0..nn).map(|n| if f1.unreached.iter().any(|&(k, _t)| k == n) { -1 } else { f1.costs[n] }).collect();
    let mut hot: Vec<((i64, i64), i64)> = (0..st.grid.n).filter(|&k| f1.u[k] > 1).map(|k| (st.grid.tile(k), f1.u[k])).collect();
    hot.sort_by_key(|&((x, y), u)| (-u, y, x));
    let mut ports: BTreeMap<(i64, i64), (i64, i64)> = BTreeMap::new();
    for n in 0..nn {
        for (ti, (k, _off)) in st.terminals(n).iter().enumerate() {
            if let Some(k) = k {
                let (who, idx, _d) = nets[n].2[ti];
                ports.insert((who, idx), st.grid.tile(*k));
            }
        }
    }
    let cells_out: Vec<Vec<(i64, i64, i64)>> = (0..seeds.len()).map(|i| runs_of(&st.dia.owner, &st.grid, i as i64)).collect();
    let mut unreached: Vec<(i64, i64)> = f1.unreached.iter().map(|&(n, t)| (n as i64, t as i64)).collect();
    unreached.sort();
    unreached.dedup();
    Ok((
        st.at.clone(),
        cells_out,
        st.dia.areas.clone(),
        st.weights.clone(),
        ports.into_iter().collect(),
        before,
        after,
        hot,
        sweeps,
        unreached,
    ))
}
