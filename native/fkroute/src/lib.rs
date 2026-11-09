//! fkroute: native kernels for fkcore's router.
//!
//! `grid`: the ground (NativeGrid), `walk` and `hubs`; `search`: `astar`, fkcore.steiner._astar
//! step for step; `grow`: steiner.grow, the whole tree. The heap orders entries as Python's tuple
//! `(f, -g, state)` does, and costs are summed in the same order, so every kernel pops the same
//! states and returns the same tree as the Python search it mirrors.
use pyo3::prelude::*;

mod grid;
mod grow;
mod physics;
mod search;

pub(crate) type St = (i64, i64, i64, i64); // x, y, heading 0..3 = N E S W, just exited an underground
pub(crate) type T = (i64, i64);

pub(crate) const DX: [i64; 4] = [0, 1, 0, -1];
pub(crate) const DY: [i64; 4] = [-1, 0, 1, 0];

#[pymodule]
fn fkroute(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<grid::NativeGrid>()?;
    m.add_function(wrap_pyfunction!(search::astar, m)?)?;
    m.add_function(wrap_pyfunction!(grid::walk, m)?)?;
    m.add_function(wrap_pyfunction!(grid::hubs, m)?)?;
    m.add_function(wrap_pyfunction!(grow::grow, m)?)?;
    m.add_function(wrap_pyfunction!(physics::physics, m)?)?;
    m.add_function(wrap_pyfunction!(physics::physics_ready, m)?)?;
    m.add_function(wrap_pyfunction!(physics::physics_lookup, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
