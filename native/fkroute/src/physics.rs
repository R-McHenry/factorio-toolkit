//! The lane physics as data: `fkcore.lanephys` enumerated by Python and handed over once at
//! import (`physics(table)`), kept in a OnceLock. Nothing here states a lane rule: every entry is
//! a lookup of what the table said. `physics_lookup` reads it back for the parity test.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use rustc_hash::FxHashMap;
use std::sync::OnceLock;

/// A lane: 0 L, 1 R (lanephys.LANES order).
pub(crate) type Lane = u8;

/// One move's lane effect: its edges (source lane, target lane, rank) and the source lane it
/// blocks, if any.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Move {
    pub(crate) edges: Vec<(Lane, Lane, u8)>,
    pub(crate) blocked: Option<Lane>,
}

/// Directions are the router's 0 N, 1 E, 2 S, 3 W (lanephys's 0, 4, 8, 12 over four).
pub(crate) struct Physics {
    vias: Vec<String>,
    /// (via, source heading, target heading, underground end 0 "in" / 1 "out") -> the move
    moves: FxHashMap<(usize, u8, u8, u8), Move>,
    /// [drop heading][belt heading]
    drop: [[Lane; 4]; 4],
    /// [come][go][side]
    turn_drop: [[[Lane; 4]; 4]; 4],
    /// [drill heading][belt heading]
    mine: [[Lane; 4]; 4],
}

static PHYSICS: OnceLock<Physics> = OnceLock::new();

/// The table, once `physics` has been called.
#[allow(dead_code)]
pub(crate) fn table() -> Option<&'static Physics> {
    PHYSICS.get()
}

impl Physics {
    pub(crate) fn via(&self, name: &str) -> Option<usize> {
        self.vias.iter().position(|v| v == name)
    }

    pub(crate) fn moves(&self, via: usize, src: u8, dst: u8, ug_out: bool) -> Option<&Move> {
        self.moves.get(&(via, src, dst, ug_out as u8))
    }

    pub(crate) fn drop_lane(&self, drop: u8, belt: u8) -> Lane {
        self.drop[drop as usize][belt as usize]
    }

    pub(crate) fn turn_drop_lane(&self, come: u8, go: u8, side: u8) -> Lane {
        self.turn_drop[come as usize][go as usize][side as usize]
    }

    pub(crate) fn mine_lane(&self, drill: u8, belt: u8) -> Lane {
        self.mine[drill as usize][belt as usize]
    }
}

fn lane_of(s: &str) -> PyResult<Lane> {
    match s {
        "L" => Ok(0),
        "R" => Ok(1),
        _ => Err(PyValueError::new_err(format!("physics: lane {s:?} is not L or R"))),
    }
}

fn lane_name(l: Lane) -> &'static str {
    if l == 0 { "L" } else { "R" }
}

fn d4(d: i64) -> PyResult<u8> {
    if d % 4 != 0 || !(0..16).contains(&d) {
        return Err(PyValueError::new_err(format!("physics: direction {d} is not 0, 4, 8 or 12")));
    }
    Ok((d / 4) as u8)
}

fn ug_of(s: &str) -> PyResult<u8> {
    match s {
        "in" => Ok(0),
        "out" => Ok(1),
        _ => Err(PyValueError::new_err(format!("physics: underground end {s:?} is not in or out"))),
    }
}

type MoveRow = (String, i64, i64, String, Vec<(String, String, u8)>, Option<String>);

/// `fkroute.physics(lanephys.table())`: take the lane physics as data. True when the table was
/// taken now, False when one was already set (the first import wins; the table is one).
#[pyfunction]
pub(crate) fn physics(table: &Bound<'_, PyDict>) -> PyResult<bool> {
    let get = |k: &str| -> PyResult<Bound<'_, PyAny>> {
        table.get_item(k)?.ok_or_else(|| PyValueError::new_err(format!("physics: no {k:?} in the table")))
    };
    let vias: Vec<String> = get("vias")?.extract()?;
    let mut moves = FxHashMap::default();
    for (via, src, dst, ug, edges, blocked) in get("moves")?.extract::<Vec<MoveRow>>()? {
        let vi = vias.iter().position(|v| *v == via)
            .ok_or_else(|| PyValueError::new_err(format!("physics: via {via:?} is not in vias")))?;
        let mut es = Vec::with_capacity(edges.len());
        for (a, b, rank) in &edges {
            es.push((lane_of(a)?, lane_of(b)?, *rank));
        }
        let blocked = match &blocked {
            Some(l) => Some(lane_of(l)?),
            None => None,
        };
        moves.insert((vi, d4(src)?, d4(dst)?, ug_of(&ug)?), Move { edges: es, blocked });
    }
    let mut drop = [[0u8; 4]; 4];
    for (a, b, lane) in get("drop_lane")?.extract::<Vec<(i64, i64, String)>>()? {
        drop[d4(a)? as usize][d4(b)? as usize] = lane_of(&lane)?;
    }
    let mut turn_drop = [[[0u8; 4]; 4]; 4];
    for (c, g, s, lane) in get("turn_drop_lane")?.extract::<Vec<(i64, i64, i64, String)>>()? {
        turn_drop[d4(c)? as usize][d4(g)? as usize][d4(s)? as usize] = lane_of(&lane)?;
    }
    let mut mine = [[0u8; 4]; 4];
    for (a, b, lane) in get("mine_lane")?.extract::<Vec<(i64, i64, String)>>()? {
        mine[d4(a)? as usize][d4(b)? as usize] = lane_of(&lane)?;
    }
    Ok(PHYSICS.set(Physics { vias, moves, drop, turn_drop, mine }).is_ok())
}

/// True once `physics` has taken a table.
#[pyfunction]
pub(crate) fn physics_ready() -> bool {
    PHYSICS.get().is_some()
}

/// What the kernel holds, in lanephys's own shape: `physics_lookup("moves", via, src_dir,
/// dst_dir, ug)` -> `(((src, dst, rank), ...), blocked)`; `("drop_lane", drop_dir, belt_dir)`,
/// `("turn_drop_lane", come, go, side)` and `("mine_lane", drill_dir, belt_dir)` -> "L" or "R".
#[pyfunction]
#[pyo3(signature = (kind, *args))]
pub(crate) fn physics_lookup<'py>(py: Python<'py>, kind: &str, args: &Bound<'py, PyTuple>) -> PyResult<PyObject> {
    let p = PHYSICS.get().ok_or_else(|| PyValueError::new_err("physics: no table set"))?;
    let int = |i: usize| -> PyResult<i64> { args.get_item(i)?.extract() };
    match kind {
        "moves" => {
            let via: String = args.get_item(0)?.extract()?;
            let vi = p.via(&via).ok_or_else(|| PyValueError::new_err(format!("no lane rule for {via:?}")))?;
            let ug: String = args.get_item(3)?.extract()?;
            let mv = p.moves(vi, d4(int(1)?)?, d4(int(2)?)?, ug_of(&ug)? == 1)
                .ok_or_else(|| PyValueError::new_err("physics: no such move"))?;
            let edges: Vec<PyObject> = mv.edges.iter()
                .map(|&(a, b, r)| (lane_name(a), lane_name(b), r).into_pyobject(py).map(|t| t.into_any().unbind()))
                .collect::<PyResult<_>>()?;
            let edges = PyTuple::new(py, edges)?;
            Ok((edges, mv.blocked.map(lane_name)).into_pyobject(py)?.into_any().unbind())
        }
        "drop_lane" => Ok(lane_name(p.drop_lane(d4(int(0)?)?, d4(int(1)?)?)).into_pyobject(py)?.into_any().unbind()),
        "turn_drop_lane" => Ok(lane_name(p.turn_drop_lane(d4(int(0)?)?, d4(int(1)?)?, d4(int(2)?)?))
            .into_pyobject(py)?.into_any().unbind()),
        "mine_lane" => Ok(lane_name(p.mine_lane(d4(int(0)?)?, d4(int(1)?)?)).into_pyobject(py)?.into_any().unbind()),
        _ => Err(PyValueError::new_err(format!("physics_lookup: unknown kind {kind:?}"))),
    }
}
