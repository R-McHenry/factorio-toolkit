//! territory: fkcore.territory's power diagram (PLAN-ORGANIC part T), step for step.
//!
//! `Grid` is the coarse grid of `c`-tile cells over the box, `wall_dist2` Meijster's exact squared
//! distance transform to the walls (the blocked cells and the ring outside the box), `Diagram` the
//! additively weighted Voronoi assignment with each placed seed's declared frame its own outright,
//! a cell pruned to the piece holding its seed, and `adapt` the capacity-constrained weights. The
//! same integers as the Python (half-tiles for points, quarter-tile^2 for weights), the same ties.
use pyo3::prelude::*;

pub(crate) type Rect = (i64, i64, i64, i64);

const DX: [i64; 4] = [0, 1, 0, -1];
const DY: [i64; 4] = [-1, 0, 1, 0];

pub(crate) struct Grid {
    pub x0: i64,
    pub y0: i64,
    pub x1: i64,
    pub y1: i64,
    pub c: i64,
    pub gw: i64,
    pub gh: i64,
    pub n: usize,
    pub xa: Vec<i64>,
    pub xb: Vec<i64>,
    pub ya: Vec<i64>,
    pub yb: Vec<i64>,
    pub tiles: Vec<i64>,
}

impl Grid {
    pub fn new(bbox: Rect, c: i64) -> Self {
        let (x0, y0, x1, y1) = bbox;
        let gw = ((x1 - x0 + c - 1).div_euclid(c)).max(0);
        let gh = ((y1 - y0 + c - 1).div_euclid(c)).max(0);
        let xa: Vec<i64> = (0..gw).map(|i| x0 + i * c).collect();
        let xb: Vec<i64> = (0..gw).map(|i| (x0 + (i + 1) * c).min(x1)).collect();
        let ya: Vec<i64> = (0..gh).map(|j| y0 + j * c).collect();
        let yb: Vec<i64> = (0..gh).map(|j| (y0 + (j + 1) * c).min(y1)).collect();
        let n = (gw * gh) as usize;
        let tiles: Vec<i64> = (0..n)
            .map(|k| {
                let (i, j) = ((k as i64 % gw) as usize, (k as i64 / gw) as usize);
                (xb[i] - xa[i]) * (yb[j] - ya[j])
            })
            .collect();
        Grid { x0, y0, x1, y1, c, gw, gh, n, xa, xb, ya, yb, tiles }
    }

    #[inline]
    pub fn cell_of(&self, x: i64, y: i64) -> Option<usize> {
        if !(self.x0 <= x && x < self.x1 && self.y0 <= y && y < self.y1) {
            return None;
        }
        Some((((y - self.y0).div_euclid(self.c)) * self.gw + (x - self.x0).div_euclid(self.c)) as usize)
    }

    #[inline]
    pub fn centre(&self, k: usize) -> (i64, i64) {
        let (i, j) = ((k as i64 % self.gw) as usize, (k as i64 / self.gw) as usize);
        (self.xa[i] + self.xb[i], self.ya[j] + self.yb[j])
    }

    #[inline]
    pub fn tile(&self, k: usize) -> (i64, i64) {
        let (i, j) = ((k as i64 % self.gw) as usize, (k as i64 / self.gw) as usize);
        (self.xa[i], self.ya[j])
    }

    pub fn overlaps(&self, rect: Rect) -> Vec<usize> {
        let (rx0, ry0) = (rect.0.max(self.x0), rect.1.max(self.y0));
        let (rx1, ry1) = (rect.2.min(self.x1), rect.3.min(self.y1));
        if rx0 >= rx1 || ry0 >= ry1 {
            return Vec::new();
        }
        let (i0, i1) = ((rx0 - self.x0).div_euclid(self.c), (rx1 - 1 - self.x0).div_euclid(self.c));
        let (j0, j1) = ((ry0 - self.y0).div_euclid(self.c), (ry1 - 1 - self.y0).div_euclid(self.c));
        let mut out = Vec::new();
        for j in j0..=j1 {
            for i in i0..=i1 {
                out.push((j * self.gw + i) as usize);
            }
        }
        out
    }

    #[inline]
    pub fn inside(&self, k: usize, rect: Rect) -> bool {
        let (cx, cy) = self.centre(k);
        2 * rect.0 <= cx && cx < 2 * rect.2 && 2 * rect.1 <= cy && cy < 2 * rect.3
    }
}

/// Per cell, the squared distance in half-tiles from its centre to the nearest wall cell's centre
/// or to the ring outside the grid: Meijster's exact EDT on the padded grid, times (2c)^2.
pub(crate) fn wall_dist2(grid: &Grid, wall: &[bool]) -> Vec<i64> {
    let (gw, gh) = (grid.gw + 2, grid.gh + 2);
    let inf = gw + gh;
    let mut g = vec![0i64; (gw * gh) as usize];
    for i in 0..gw {
        let mut prev = inf;
        for j in 0..gh {
            let k = (j * gw + i) as usize;
            let is_wall = i == 0
                || j == 0
                || i == gw - 1
                || j == gh - 1
                || wall[((j - 1) * grid.gw + (i - 1)) as usize];
            prev = if is_wall { 0 } else if prev < inf { prev + 1 } else { inf };
            g[k] = prev;
        }
        prev = inf;
        for j in (0..gh).rev() {
            let k = (j * gw + i) as usize;
            if g[k] == 0 {
                prev = 0;
            } else {
                prev = if prev < inf { prev + 1 } else { inf };
                if prev < g[k] {
                    g[k] = prev;
                }
            }
        }
    }
    let mut out = vec![0i64; grid.n];
    let mut s = vec![0i64; gw as usize];
    let mut t = vec![0i64; gw as usize];
    let scale = (2 * grid.c) * (2 * grid.c);
    for j in 1..gh - 1 {
        let row = (j * gw) as usize;
        let gj = &g[row..row + gw as usize];
        let f = |x: i64, i: i64| (x - i) * (x - i) + gj[i as usize] * gj[i as usize];
        let mut q: i64 = 0;
        s[0] = 0;
        t[0] = 0;
        for u in 1..gw {
            while q >= 0 && f(t[q as usize], s[q as usize]) > f(t[q as usize], u) {
                q -= 1;
            }
            if q < 0 {
                q = 0;
                s[0] = u;
            } else {
                let i = s[q as usize];
                let w = 1 + (u * u - i * i + gj[u as usize] * gj[u as usize] - gj[i as usize] * gj[i as usize])
                    .div_euclid(2 * (u - i));
                if w < gw {
                    q += 1;
                    s[q as usize] = u;
                    t[q as usize] = w;
                }
            }
        }
        for u in (0..gw).rev() {
            if 1 <= u && u <= gw - 2 {
                out[((j - 1) * grid.gw + (u - 1)) as usize] = f(u, s[q as usize]) * scale;
            }
            if u == t[q as usize] {
                q -= 1;
            }
        }
    }
    out
}

pub(crate) struct Diagram {
    pub n_seeds: usize,
    pub fixed: Vec<Option<Rect>>,
    pub points: Vec<Option<(i64, i64)>>,
    pub frames: Vec<Option<Rect>>,
    pub weights: Vec<i64>,
    pub wall: Vec<bool>,
    pub fixed_owner: Vec<i64>,
    pub areas: Vec<i64>,
    pub wd2: Vec<i64>,
    pub owner: Vec<i64>,
}

impl Diagram {
    pub fn new(grid: &Grid, blocked: &[Rect], fixed: &[Option<Rect>], weights: &[i64]) -> Self {
        let n_seeds = fixed.len();
        let mut wall = vec![false; grid.n];
        for &rect in blocked {
            for k in grid.overlaps(rect) {
                wall[k] = true;
            }
        }
        let mut fixed_owner = vec![-1i64; grid.n];
        let mut areas = vec![0i64; n_seeds];
        for (i, rect) in fixed.iter().enumerate() {
            if let Some(rect) = rect {
                for k in grid.overlaps(*rect) {
                    if grid.inside(k, *rect) {
                        fixed_owner[k] = i as i64;
                        areas[i] += grid.tiles[k];
                    } else {
                        wall[k] = true;
                    }
                }
            }
        }
        let wd2 = wall_dist2(grid, &wall);
        let owner: Vec<i64> = (0..grid.n).map(|k| if wall[k] { -2 } else { fixed_owner[k] }).collect();
        Diagram {
            n_seeds,
            fixed: fixed.to_vec(),
            points: vec![None; n_seeds],
            frames: vec![None; n_seeds],
            weights: weights.to_vec(),
            wall,
            fixed_owner,
            areas,
            wd2,
            owner,
        }
    }

    fn assign(&mut self, grid: &Grid, ks: &[usize]) {
        for &k in ks {
            if self.wall[k] || self.fixed_owner[k] >= 0 {
                continue;
            }
            let (cx, cy) = grid.centre(k);
            let mut who: i64 = -1;
            for (i, rect) in self.frames.iter().enumerate() {
                if let Some(r) = rect {
                    if 2 * r.0 <= cx && cx < 2 * r.2 && 2 * r.1 <= cy && cy < 2 * r.3 {
                        who = i as i64;
                        break;
                    }
                }
            }
            if who < 0 {
                let mut best = self.wd2[k];
                for (i, p) in self.points.iter().enumerate() {
                    if let Some((sx, sy)) = p {
                        let d = (cx - sx) * (cx - sx) + (cy - sy) * (cy - sy) - self.weights[i];
                        if d < best {
                            best = d;
                            who = i as i64;
                        }
                    }
                }
            }
            self.owner[k] = who;
        }
    }

    /// Keep of seed `i`'s cells the 4-connected piece holding `home`; the rest is nobody's.
    fn prune(&mut self, grid: &Grid, i: usize, home: Option<usize>) -> i64 {
        let ii = i as i64;
        let home = match home {
            Some(h) if self.owner[h] == ii => h,
            _ => {
                for k in 0..grid.n {
                    if self.owner[k] == ii {
                        self.owner[k] = -1;
                    }
                }
                return 0;
            }
        };
        let mut seen = vec![false; grid.n];
        seen[home] = true;
        let mut todo = vec![home];
        let mut area = grid.tiles[home];
        let gw = grid.gw;
        while let Some(k) = todo.pop() {
            let (x, y) = (k as i64 % gw, k as i64 / gw);
            for d in 0..4 {
                let (nx, ny) = (x + DX[d], y + DY[d]);
                if 0 <= nx && nx < gw && 0 <= ny && ny < grid.gh {
                    let nk = (ny * gw + nx) as usize;
                    if !seen[nk] && self.owner[nk] == ii {
                        seen[nk] = true;
                        area += grid.tiles[nk];
                        todo.push(nk);
                    }
                }
            }
        }
        for k in 0..grid.n {
            if self.owner[k] == ii && !seen[k] {
                self.owner[k] = -1;
            }
        }
        area
    }

    /// Assign the cells in `ks` (all when None), prune every movable seed to its piece.
    pub fn recompute(&mut self, grid: &Grid, ks: Option<&[usize]>) {
        match ks {
            Some(ks) => self.assign(grid, ks),
            None => {
                let all: Vec<usize> = (0..grid.n).collect();
                self.assign(grid, &all);
            }
        }
        for i in 0..self.n_seeds {
            if self.fixed[i].is_some() {
                continue;
            }
            match self.points[i] {
                None => self.areas[i] = 0,
                Some((sx, sy)) => {
                    let home = grid.cell_of(sx.div_euclid(2), sy.div_euclid(2));
                    self.areas[i] = self.prune(grid, i, home);
                }
            }
        }
    }

    /// Capacity-constrained weights: rounds of recompute and step until every movable cell is
    /// within `tol` per cent of its need or the cap. -> the rounds run.
    pub fn adapt(&mut self, grid: &Grid, needs: &[i64], iters: i64, tol: i64) -> i64 {
        let n = self.n_seeds;
        let mut gain = vec![16i64; n];
        let mut last = vec![0i64; n];
        let side = (grid.x1 - grid.x0).max(grid.y1 - grid.y0);
        let cap = (2 * side) * (2 * side);
        let mut rounds = 0i64;
        loop {
            self.recompute(grid, None);
            rounds += 1;
            let off: Vec<usize> = (0..n)
                .filter(|&i| {
                    self.fixed[i].is_none()
                        && self.points[i].is_some()
                        && (self.areas[i] - needs[i]).abs() * 100 > tol * needs[i]
                })
                .collect();
            if off.is_empty() || rounds > iters {
                return rounds;
            }
            for i in off {
                let diff = needs[i] - self.areas[i];
                if last[i] != 0 && (diff > 0) != (last[i] > 0) {
                    gain[i] = (gain[i] / 2).max(1);
                }
                last[i] = diff;
                let w = self.weights[i] + (diff * gain[i]).div_euclid(16);
                self.weights[i] = w.max(-cap).min(cap);
            }
        }
    }

    /// The cells of seed `i` whose neighbour in direction `side` (0..3 = n e s w) is not its own.
    pub fn boundary(&self, grid: &Grid, i: usize, d: usize) -> Vec<usize> {
        let ii = i as i64;
        let mut out = Vec::new();
        for k in 0..grid.n {
            if self.owner[k] != ii {
                continue;
            }
            let (x, y) = (k as i64 % grid.gw + DX[d], k as i64 / grid.gw + DY[d]);
            if !(0 <= x && x < grid.gw && 0 <= y && y < grid.gh) || self.owner[(y * grid.gw + x) as usize] != ii {
                out.push(k);
            }
        }
        out
    }
}

/// fkcore.territory.voronoi_py: the power diagram with adapted weights on a coarse grid.
/// -> (owner per cell, areas, weights, (gw, gh)).
#[pyfunction]
#[pyo3(signature = (seeds, needs, bbox, blocked, cell, weights=None, fixed=None, iters=40, tol=5, frames=None))]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn voronoi(
    seeds: Vec<Option<(i64, i64)>>,
    needs: Vec<i64>,
    bbox: Rect,
    blocked: Vec<Rect>,
    cell: i64,
    weights: Option<Vec<i64>>,
    fixed: Option<Vec<Option<Rect>>>,
    iters: i64,
    tol: i64,
    frames: Option<Vec<Option<Rect>>>,
) -> PyResult<(Vec<i64>, Vec<i64>, Vec<i64>, (i64, i64))> {
    let n = seeds.len();
    let grid = Grid::new(bbox, cell.max(1));
    let fixed = fixed.unwrap_or_else(|| vec![None; n]);
    let weights = weights.unwrap_or_else(|| vec![0; n]);
    let mut dia = Diagram::new(&grid, &blocked, &fixed, &weights);
    dia.points = seeds;
    if let Some(fr) = frames {
        dia.frames = fr;
    }
    dia.adapt(&grid, &needs, iters, tol);
    Ok((dia.owner, dia.areas, dia.weights, (grid.gw, grid.gh)))
}
