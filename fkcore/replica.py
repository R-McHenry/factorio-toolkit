"""fkcore.replica: a private copy of a shared save on this machine (3.3, PLAN-COMMONS).

Agents who play a shared save through its fk-gateway (``FK_LINK=gateway``) do their designing,
debugging and ad-hoc Lua on a replica: the shared save as it stands, run by Factorio's headless
server on their own machine, with full RCON, ``fk sim`` (pause, speed, save states) and nothing
shared at risk. The replica is the run's planner (``fkcore.sim``) started from the shared save.

    fk replica GAME            setup if needed, pull the save, start it (paused); prints the env
    fk replica GAME setup      download Factorio's headless server, the gateway's version
    fk replica GAME pull       the shared save as it stands, as save state NAME (default live)

Factorio's headless server is a free download with no account (linux64, and linux-arm64 from
2.1.24). It is Linux only: on Windows or macOS run the toolkit in WSL or a Linux container, or
point ``FK_LAPTOP_FACTORIO`` at a Factorio you have. Downloads go under ``FK_HOME`` (default
``~/.fk``), one folder per version. Stdlib only.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request

from . import link

__all__ = ["ReplicaError", "home", "build", "install", "installed", "version", "pull", "setup"]

DOWNLOAD = "https://factorio.com/get-download/{version}/headless/{build}"


class ReplicaError(RuntimeError):
    pass


def home():
    return os.environ.get("FK_HOME") or os.path.join(os.path.expanduser("~"), ".fk")


def build(system=None, machine=None):
    """Factorio's name for this machine's headless build, or None where there is none."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    if system != "linux":
        return None
    if machine in ("x86_64", "amd64"):
        return "linux64"
    if machine in ("aarch64", "arm64"):
        return "linux-arm64"
    return None


def _find_exe(root):
    """The server binary under an unpacked headless folder (``factorio/bin/<arch>/factorio``)."""
    bin_dir = os.path.join(root, "factorio", "bin")
    if os.path.isdir(bin_dir):
        for arch in sorted(os.listdir(bin_dir)):
            exe = os.path.join(bin_dir, arch, "factorio")
            if os.path.isfile(exe):
                return exe
    return None


def installed(ver):
    """The server binary of version ``ver`` under ``home()``, or None."""
    return _find_exe(os.path.join(home(), "factorio", ver))


def hello():
    """The gateway's hello for the shared save ({} when it can't be asked)."""
    try:
        status, body = link.gateway_get("hello")
    except (OSError, link.LinkError):
        return {}
    return json.loads(body.decode("utf-8") or "{}") if status == 200 else {}


def version():
    """The Factorio version the shared save runs (the gateway's hello), else ``stable``."""
    return hello().get("factorio") or "stable"


def install(ver, log=print, opener=urllib.request.urlopen):
    """Download and unpack the headless server ``ver`` for this machine -> its binary."""
    have = installed(ver)
    if have:
        return have
    kind = build()
    if kind is None:
        raise ReplicaError(
            f"Factorio's headless server is Linux only (this is {platform.system()} "
            f"{platform.machine()}): run the toolkit in WSL or a Linux container, or set "
            "FK_LAPTOP_FACTORIO to a Factorio you have")
    url = DOWNLOAD.format(version=ver, build=kind)
    dest = os.path.join(home(), "factorio", ver)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    log(f"replica: downloading Factorio {ver} headless ({kind}) from {url}")
    with tempfile.TemporaryDirectory(dir=os.path.dirname(dest)) as tmp:
        archive = os.path.join(tmp, "headless.tar.xz")
        # factorio.com answers Python's default User-Agent with 403 (11-10)
        from . import __version__
        req = urllib.request.Request(url, headers={"User-Agent": f"fkcore/{__version__}"})
        try:
            with opener(req, timeout=600) as resp, open(archive, "wb") as fh:
                shutil.copyfileobj(resp, fh)
        except OSError as exc:
            raise ReplicaError(f"no {kind} headless server {ver} at {url} ({exc}); the "
                               "linux-arm64 build starts at 2.1.24") from None
        unpacked = os.path.join(tmp, "unpacked")
        with tarfile.open(archive, "r:xz") as tar:
            try:
                tar.extractall(unpacked, filter="data")
            except TypeError:                        # a Python from before extraction filters
                tar.extractall(unpacked)
        if not _find_exe(unpacked):
            raise ReplicaError(f"the download from {url} holds no factorio/bin/*/factorio")
        shutil.move(unpacked, dest)
    exe = installed(ver)
    os.chmod(exe, 0o755)
    return exe


def setup(sim, ver=None, log=print, opener=urllib.request.urlopen):
    """Install the headless server for the run's planner and remember it (``sim\\factorio.json``).
    -> the binary."""
    ver = ver or version()
    exe = install(ver, log, opener)
    os.makedirs(sim.root, exist_ok=True)
    with open(os.path.join(sim.root, "factorio.json"), "w", encoding="utf-8") as fh:
        json.dump({"exe": exe, "version": ver}, fh)
    sim.exe = exe
    return exe


def pull(sim, name="live", opener=urllib.request.urlopen):
    """The shared save as it stands, from the gateway (``GET save``), as save state ``name``.
    -> a report line."""
    url = (os.environ.get("FK_GATEWAY") or "").rstrip("/")
    if not url:
        raise ReplicaError("no gateway: FK_GATEWAY names the shared save's URL "
                           "(https://HOST/v1/saves/NAME)")
    os.makedirs(sim.saves, exist_ok=True)
    tmp = sim.save_path(name) + ".part"
    try:
        req = urllib.request.Request(f"{url}/save", headers=link._headers())
        with opener(req, timeout=600) as resp, open(tmp, "wb") as fh:
            shutil.copyfileobj(resp, fh)
    except OSError as exc:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise ReplicaError(f"no save from {url}/save ({exc})") from None
    size = os.path.getsize(tmp)
    if size == 0:
        os.remove(tmp)
        raise ReplicaError(f"the gateway at {url} gave an empty save")
    os.replace(tmp, sim.save_path(name))
    mods = hello().get("mods")
    if mods is not None:                   # 3.4: the replica's mods are the shared save's
        with open(os.path.join(sim.root, "mods.json"), "w", encoding="utf-8") as fh:
            json.dump({"mods": mods}, fh)
    return f"replica: the shared save as save state {name} ({size / 1e6:.1f} MB)"


def env_lines(sim):
    """How to point the toolkit at the replica, and back at the shared save."""
    env = dict(sim.env(), FK_LINK="on")
    sh = " ".join(f"{k}={v}" for k, v in env.items())
    return [f"replica: point the toolkit at it with  {sh}",
            "replica: back to the shared save with  FK_LINK=gateway (FK_GATEWAY, FK_GATEWAY_KEY)",
            "replica: fk sim stop | save NAME | load NAME | speed X | run N work on it as usual"]
