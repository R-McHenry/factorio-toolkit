//! steiner.grow: the whole tree search (starts, A*, attach, the reroute rounds), forward or laid
//! reversed (drop_taps, keep_clear, the merges' spare tiles), for FixedSink, TapSink (3.0's taps:
//! k > 1, arms; m2m's LeftTap and _EndTap) and DropSink sinks.
use pyo3::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};

use crate::grid::NativeGrid;
use crate::search::{pick, search, to_ins, to_sinks, Ground, Ins, Search, Sink, SinkIn, Tap};
use crate::{St, DX, DY, T};

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub(crate) enum Mv {
    Step(St),
    Jump(St),
    Split(i64, St, St), // side, straight child, side child
}

/// A dict with Python's order: a new key goes last, an existing key keeps its place, a removed key
/// leaves (``tree.succ`` and ``tree.sink_at`` are dicts, and their order reaches Python).
#[derive(Default)]
pub(crate) struct OrdMap<V: Copy> {
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
    pub(crate) fn get(&self, k: &St) -> Option<V> {
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
    pub(crate) fn iter(&self) -> impl Iterator<Item = (St, V)> + '_ {
        self.slots.iter().filter_map(|s| *s)
    }
}

/// A Tree: ``last_end`` is the one entry ``sink_terminal`` holds (Tree.copy() does not copy it, so
/// after _attach only the end just attached has it, and after _detach none).
#[derive(Clone)]
pub(crate) struct Tree {
    pub(crate) root: St,
    pub(crate) succ: OrdMap<Mv>,
    pub(crate) sink_at: OrdMap<usize>,
    pub(crate) taps: Vec<Tap>,
    pub(crate) reserved: FxHashSet<T>,
    pub(crate) last_end: Option<(St, bool)>,
}

pub(crate) struct Tiles {
    pub(crate) own: FxHashMap<T, u32>,
    spare: FxHashSet<T>,
}

/// One grow's fixed inputs: the ground, the sinks and the costs.
pub(crate) struct Ctx<'a> {
    pub(crate) grid: &'a NativeGrid,
    pub(crate) keep_clear: FxHashSet<T>,
    pub(crate) drop_taps: bool,
    pub(crate) belt: f64,
    pub(crate) turn: f64,
    pub(crate) ug: f64,
    pub(crate) split: f64,
    pub(crate) max_ug: i64,
    pub(crate) limit: usize,
    pub(crate) lane_ok: FxHashMap<T, u16>,
    pub(crate) ins: &'a [Ins],
    pub(crate) sinks: Vec<Sink>,
    pub(crate) sname: Vec<usize>, // per sink: the id of its name (equal names, one id)
}

/// (belt, turn, ug, split, max_ug): steiner.COSTS less the tap costs, which ride on the inserters.
pub(crate) type Costs = (f64, f64, f64, f64, i64);

impl<'a> Ctx<'a> {
    pub(crate) fn new(
        grid: &'a NativeGrid,
        keep_clear: &[T],
        drop_taps: bool,
        sinks: Vec<Sink>,
        snames: &[String],
        ins: &'a [Ins],
        costs: Costs,
        limit: usize,
        lane_ok: &[(T, u16)],
    ) -> PyResult<Self> {
        if snames.len() != sinks.len() {
            return Err(pyo3::exceptions::PyValueError::new_err("one name per sink"));
        }
        let sname: Vec<usize> = snames.iter().map(|s| snames.iter().position(|x| x == s).unwrap()).collect();
        let (belt, turn, ug, split, max_ug) = costs;
        Ok(Ctx {
            grid, keep_clear: keep_clear.iter().copied().collect(), drop_taps, belt, turn, ug, split, max_ug,
            limit, lane_ok: lane_ok.iter().copied().collect(), ins, sinks, sname,
        })
    }
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
    pub(crate) fn new(root: St) -> Self {
        Tree { root, succ: OrdMap::new(), sink_at: OrdMap::new(), taps: Vec::new(), reserved: FxHashSet::default(), last_end: None }
    }

    pub(crate) fn states(&self) -> Vec<St> {
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

    pub(crate) fn tiles(&self, cx: &Ctx) -> Tiles {
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

    /// The search's extra ground: the tree's tiles, its reserved tiles and its spare tiles.
    fn extra(&self, tl: &Tiles) -> FxHashSet<T> {
        let mut extra: FxHashSet<T> = tl.own.keys().copied().collect();
        extra.extend(self.reserved.iter().copied());
        extra.extend(tl.spare.iter().copied());
        extra
    }

    #[inline]
    fn free(&self, cx: &Ctx, tl: &Tiles, t: T) -> bool {
        !cx.grid.blocked(t) && !tl.own.contains_key(&t) && !self.reserved.contains(&t) && !tl.spare.contains(&t)
            && !cx.grid.soft.contains_key(&t)
    }

    pub(crate) fn spans(&self) -> [FxHashSet<T>; 2] {
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

    pub(crate) fn cost(&self, cx: &Ctx) -> f64 {
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
            taps += cx.ins[t.ins].cost;
        }
        let raw = belts as f64 * cx.belt + turns as f64 * cx.turn + ugs as f64 / 2.0 * cx.ug
            + splitters as f64 * cx.split + taps;
        py_round3(raw)
    }

    pub(crate) fn has_problems(&self, cx: &Ctx) -> bool {
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
        for (i, sink) in cx.sinks.iter().enumerate() {
            if !reached.contains(&i) {
                return true;
            }
            if let Some(sp) = sink.tap() {
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

    /// Laid reversed, the belt tiles the taps drop onto: they start no tunnel.
    fn tapped(&self, cx: &Ctx) -> FxHashSet<T> {
        let mut out = FxHashSet::default();
        if cx.drop_taps {
            for t in &self.taps {
                out.insert(t.tile);
            }
        }
        out
    }
}

/// Python's round(x, 3): the nearest 3-decimal value of x's exact binary value.
fn py_round3(x: f64) -> f64 {
    format!("{:.3}", x).parse().unwrap()
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
    let extra = tree.extra(&tl);
    let tspans = tree.spans();
    let tapped = tree.tapped(cx);
    let s = Search {
        ground: Ground { grid: cx.grid, extra: &extra }, tspans: &tspans, sinks: &cx.sinks, ins: cx.ins,
        targets, tapped: &tapped, lane_ok: &cx.lane_ok, drop_taps: cx.drop_taps, belt: cx.belt,
        turn: cx.turn, ug: cx.ug, max_ug: cx.max_ug, limit: cx.limit,
    };
    let starts: Vec<(St, f64)> = st.iter().map(|(s, g0, _, _)| (*s, *g0)).collect();
    let spare: Vec<Option<T>> = st
        .iter()
        .map(|(_, _, how, _)| match how {
            How::Split(s, side, _) if cx.drop_taps => Some(spare_tile(*s, *side)),
            _ => None,
        })
        .collect();
    let taken: Vec<Vec<T>> = st.iter().map(|(_, _, _, t)| t.clone()).collect();
    let got = search(&s, &starts, &spare, &taken, |_i, _path, _from| {
        Err(pyo3::exceptions::PyValueError::new_err("grow: a sink with a Python goal"))
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
    if let Some(sp) = cx.sinks[i].tap() {
        let tl = t.tiles(cx); // the same choice the goal test made (before the path lands)
        let extra = t.extra(&tl);
        let got = pick(cx.ins, &Ground { grid: cx.grid, extra: &extra }, sp, path, &[], cx.sname[i], cx.drop_taps);
        for g in &got {
            t.reserved.insert(g.q);
        }
        t.taps.extend(got);
    }
    t.sink_at.insert(end, i);
    t.last_end = Some((end, cx.sinks[i].terminal()));
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

pub(crate) type MvOut = (u8, i64, St, St);
pub(crate) type TapOut = (T, String, i64, usize, Option<(T, T)>);
pub(crate) type LogOut = (u8, Vec<usize>, usize, u8, f64, f64);
/// A tree as Python rebuilds it: (succ, sink_at, taps, reserved, last_end, log).
pub(crate) type TreeOut = (Vec<(St, MvOut)>, Vec<(St, usize)>, Vec<TapOut>, Vec<T>, Option<(St, bool)>, Vec<LogOut>);

/// steiner.grow's loop: the sinks in ``order`` one by one (or all at once, nearest first), then
/// ``improve`` rounds of rip-up and re-route. -> the tree and its log.
pub(crate) fn run_grow(cx: &Ctx, root: St, improve: usize, order: Option<Vec<usize>>) -> PyResult<(Tree, Vec<LogOut>)> {
    let n = cx.sinks.len();
    let mut tree = Tree::new(root);
    let ordered = order.is_some();
    let mut left: Vec<usize> = order.unwrap_or_else(|| (0..n).collect());
    let mut log: Vec<LogOut> = Vec::new();
    while !left.is_empty() {
        let targets: Vec<usize> = if ordered { left[..1].to_vec() } else { left.clone() };
        if targets.iter().any(|&i| i >= n) {
            return Err(pyo3::exceptions::PyValueError::new_err("order: a sink index out of range"));
        }
        match step(cx, &tree, &targets)? {
            None => {
                log.push((0, targets, 0, 0, 0.0, 0.0));
                break;
            }
            Some((path, how, i, gcost)) => {
                tree = attach(cx, &tree, &path, how, i);
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
            let cut = if has { detach(cx, &tree, i) } else { None };
            let cut = match cut {
                Some(c) => c,
                None => continue,
            };
            let got = match step(cx, &cut, &[i])? {
                Some(g) => g,
                None => continue,
            };
            let new = attach(cx, &cut, &got.0, got.1, i);
            if !new.has_problems(cx) {
                let (old_c, new_c) = (tree.cost(cx), new.cost(cx));
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
    Ok((tree, log))
}

/// The tree for Python: succ (state, (0 step | 1 jump | 2 split, side, child, side child)), sink_at,
/// taps (tile, inserter, direction, sink index of its name, (pick, drop) or None), reserved,
/// last_end, and the log (0 cannot | 1 added | 2 rerouted, targets, sink, 0 leaf | 1 split, cost a,
/// cost b).
pub(crate) fn tree_out(tree: &Tree, ins: &[Ins], log: Vec<LogOut>) -> TreeOut {
    let enc = |mv: Mv| -> MvOut {
        match mv {
            Mv::Step(c) => (0, 0, c, c),
            Mv::Jump(c) => (1, 0, c, c),
            Mv::Split(side, c1, c2) => (2, side, c1, c2),
        }
    };
    (
        tree.succ.iter().map(|(s, mv)| (s, enc(mv))).collect(),
        tree.sink_at.iter().collect(),
        tree.taps.iter().map(|t| (t.q, ins[t.ins].name.clone(), t.dir, t.sink, t.arm)).collect(),
        tree.reserved.iter().copied().collect(),
        tree.last_end,
        log,
    )
}

/// steiner.grow for FixedSink / TapSink / DropSink sinks -> a `TreeOut`. ``sinks``: see
/// `search::SinkIn` (no kind 2: the goal runs here); ``inserters``: (name, reach, tap cost);
/// ``costs``: (belt, turn, ug, split, max_ug).
#[pyfunction]
#[pyo3(signature = (grid, keep_clear, drop_taps, root, sinks, snames, inserters, costs, improve, order,
                    limit, lane_ok=None))]
#[allow(clippy::too_many_arguments)]
pub(crate) fn grow(
    grid: &Bound<'_, NativeGrid>,
    keep_clear: Vec<T>,
    drop_taps: bool,
    root: St,
    sinks: Vec<SinkIn>,
    snames: Vec<String>,
    inserters: Vec<(String, i64, f64)>,
    costs: Costs,
    improve: usize,
    order: Option<Vec<usize>>,
    limit: usize,
    lane_ok: Option<Vec<(T, u16)>>,
) -> PyResult<TreeOut> {
    let ins = to_ins(inserters);
    let sinks = to_sinks(sinks, &ins)?;
    if sinks.iter().any(|s| matches!(s, Sink::TapCb { .. })) {
        return Err(pyo3::exceptions::PyValueError::new_err("grow: a sink with a Python goal"));
    }
    let cx = Ctx::new(grid.get(), &keep_clear, drop_taps, sinks, &snames, &ins, costs, limit,
                      &lane_ok.unwrap_or_default())?;
    let (tree, log) = run_grow(&cx, root, improve, order)?;
    Ok(tree_out(&tree, &ins, log))
}
