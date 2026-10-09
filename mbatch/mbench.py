"""mbench: benchmarks meant to be launched through mrun.

``mrun`` sets up MPI processes, threads and CPU binding from the site files, and
``mbench`` provides workloads to see how well that setup performs. Each process
runs its own copy of the benchmark. Thread counts are not changed here, so the
results reflect the environment the site files and the user provide. Usage::

    mbench sht --res 30 --lmax 300 --nrep 2
    mrun -n 1 -t 8 -- mbench sht --res 2 --op map2alm alm2map
    mrun -n 1 -t 8 -- mbench sht --pix healpix --nside 2048 --pol

``mbench sht`` times pixell.curvedsky spherical harmonic transforms of random
alms with a flat spectrum, on a CAR map (a declination band or the full sky) or
a full-sky HEALPix map. Each operation is run once untimed as a warm-up and
then ``--nrep`` times. Requires pixell.
"""

import argparse
import os
import time

import numpy as np

RANK = next(
    (
        os.environ[k]
        for k in ["OMPI_COMM_WORLD_RANK", "PMI_RANK", "SLURM_PROCID"]
        if k in os.environ
    ),
    "0",
)


def log(msg):
    print(f"[rank {RANK}] {msg}", flush=True)


def get_args(argv=None):
    p = argparse.ArgumentParser(
        prog="mbench",
        description="Benchmarks meant to be launched through mrun.",
        epilog="Example: mrun -n 1 -t 8 -- mbench sht --res 2",
    )
    sub = p.add_subparsers(dest="bench", metavar="BENCH", required=True)
    s = sub.add_parser("sht", help="Spherical harmonic transforms with pixell")
    s.set_defaults(func=run_sht)
    s.add_argument("--pix", choices=["car", "healpix"], default="car")
    s.add_argument("--res", type=float, default=2.0, help="CAR pixel size in arcmin")
    s.add_argument("--nside", type=int, default=2048, help="HEALPix nside")
    s.add_argument("--lmax", type=int, default=4000, help="Default: 4000")
    s.add_argument(
        "--op", nargs="+", choices=["map2alm", "alm2map"], default=["map2alm"]
    )
    s.add_argument(
        "--dec", type=float, nargs=2, default=[-63, 23], help="CAR band (deg)"
    )
    s.add_argument(
        "--full-sky", action="store_true", help="Full-sky CAR map instead of a band"
    )
    s.add_argument("--pol", action="store_true", help="T,Q,U instead of one map")
    s.add_argument("--double", action="store_true", help="Double precision")
    s.add_argument("--nrep", type=int, default=5, help="Timed repetitions")
    return p.parse_args(argv)


def make_map(args, dtype):
    """Return an empty CAR or HEALPix map."""
    from pixell import enmap, utils

    pre = (3,) if args.pol else ()
    if args.pix == "healpix":
        return np.zeros(pre + (12 * args.nside**2,), dtype)
    res = args.res * utils.arcmin
    if args.full_sky:
        shape, wcs = enmap.fullsky_geometry(res=res, dims=pre)
    else:
        shape, wcs = enmap.band_geometry(np.deg2rad(args.dec), res=res, dims=pre)
    return enmap.zeros(shape, wcs, dtype)


def run_sht(args):
    """Time map2alm and/or alm2map for the parsed ``mbench sht`` arguments."""
    from pixell import curvedsky

    dtype = np.float64 if args.double else np.float32
    omap, lmax = make_map(args, dtype), args.lmax
    ps = np.ones(lmax + 1)
    if args.pol:
        ps = np.eye(3)[:, :, None] * ps
    alm = curvedsky.rand_alm(ps, lmax=lmax, seed=1, dtype=np.result_type(dtype, 1j))
    if args.pix == "car":
        m2a, a2m = curvedsky.map2alm, curvedsky.alm2map
        method = curvedsky.get_method(omap.shape, omap.wcs)
        log(f"CAR geometry {omap.wcs}, transform method {method}")
    else:
        m2a, a2m = curvedsky.map2alm_healpix, curvedsky.alm2map_healpix
    a2m(alm, omap)
    log(
        f"{args.pix}: map {omap.shape} {omap.dtype}, alm {alm.shape} {alm.dtype}, "
        f"lmax {lmax}, OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')}"
    )
    ops = {"map2alm": lambda: m2a(omap, lmax=lmax), "alm2map": lambda: a2m(alm, omap)}
    for op in args.op:
        ops[op]()  # warm-up
        times = []
        for _ in range(args.nrep):
            t = time.perf_counter()
            ops[op]()
            times.append(time.perf_counter() - t)
        reps = ", ".join(f"{t:.3f}" for t in times)
        log(
            f"shape {omap.shape}: {np.mean(times):.3f} s per {op} "
            f"(best {min(times):.3f} s; {reps})"
        )


def main(argv=None):
    """Command-line entry point: ``mbench <benchmark> [options]``."""
    args = get_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
