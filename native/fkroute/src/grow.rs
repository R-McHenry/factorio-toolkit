//! steiner.grow: the whole tree search (starts, A*, attach, the reroute rounds).
use pyo3::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};

use crate::grid::NativeGrid;
use crate::search::{search, to_sinks, Search, Sink};
use crate::{St, DX, DY, T};

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
    lane_ok: FxHashMap<T, u16>,
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

/// _lanes_allow: may tile ``t`` hold the carrier of ``bit``? Always, unless something feeds it.
#[inline]
fn lanes_allow(cx: &Ctx, t: T, bit: i64) -> bool {
    cx.lane_ok.get(&t).map_or(true, |m| m >> bit & 1 != 0)
}

/// _lanes_hold: every one of ``states`` on a fed tile holds a carrier its lanes allow.
fn lanes_hold(cx: &Ctx, t: &Tree, states: &[St]) -> bool {
    if cx.lane_ok.is_empty() {
        return true;
    }
    states.iter().all(|s| {
        if !cx.lane_ok.contains_key(&(s.0, s.1)) {
            return true;
        }
        let bit = if s.3 != 0 {
            8 + s.2
        } else {
            match t.succ.get(s) {
                Some(Mv::Jump(_)) => 4 + s.2,
                Some(Mv::Step(c)) => c.2,
                _ => s.2,
            }
        };
        lanes_allow(cx, (s.0, s.1), bit)
    })
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
            if tree.free(cx, tl, m) && tree.free(cx, tl, (o2.0, o2.1)) && lanes_allow(cx, n, 12 + d)
                && lanes_allow(cx, m, 12 + d)
            {
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
        tapped: &tapped, lane_ok: &cx.lane_ok, belt: cx.belt, turn: cx.turn, ug: cx.ug,
        max_ug: cx.max_ug, limit: cx.limit,
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
                let laid: Vec<St> = if keep == c1 {
                    let mid = (n.0, n.1, d, 0);
                    t.succ.insert(p, Mv::Step(mid));
                    t.succ.insert(mid, Mv::Step(c1));
                    vec![p, mid]
                } else {
                    let sh = (d + side) % 4;
                    let (a, b) = ((n.0, n.1, d, 0), (m.0, m.1, sh, 0));
                    t.succ.insert(p, Mv::Step(a));
                    t.succ.insert(a, Mv::Step(b));
                    t.succ.insert(b, Mv::Step(c2));
                    vec![p, a, b]
                };
                if !lanes_hold(cx, &t, &laid) {
                    return None; // the belts in the splitter's place break a fed tile
                }
            }
            _ => {
                t.succ.remove(&p);
                if !lanes_hold(cx, &t, &[p]) {
                    return None; // ... or a belt left heading its own way as a leaf
                }
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
                    improve, order, limit, lane_ok=None))]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub(crate) fn grow(
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
    lane_ok: Option<Vec<(T, u16)>>,
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
        belt, turn, ug, split, tap, long_tap, max_ug, limit,
        lane_ok: lane_ok.unwrap_or_default().into_iter().collect(), names, long, sinks, taps, sname,
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
