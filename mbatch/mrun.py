import os, sys, shlex, argparse
import mbatch

def _env_int(*names):
    for n in names:
        v = os.environ.get(n)
        if v:
            try: return int(v)
            except ValueError: pass
    return None

def main():
    parser = argparse.ArgumentParser(
        description='Launch a hybrid MPI+OpenMP command with the site-aware launcher '
                    'from the site configuration (the same one used in sbatch scripts). '
                    'Use inside an interactive allocation (salloc, debugjob) or on a login node.',
        epilog='Example: mrun -n 4 -t 24 -- python myscript.py --lmax 4000')
    parser.add_argument("-n", "--nproc", type=int, default=None,
                        help="Number of MPI processes (default: $SLURM_NTASKS, else 1)")
    parser.add_argument("-t", "--threads", type=int, default=None,
                        help="OpenMP threads per process (default: $SLURM_CPUS_PER_TASK, "
                             "else $OMP_NUM_THREADS, else 1)")
    parser.add_argument("-s", "--site", type=str, default=None,
                        help="Site name (optional; will auto-detect if not provided)")
    parser.add_argument("-p", "--partition", type=str, default=None,
                        help="Partition name (only used to look up threads per core)")
    parser.add_argument("-c", "--constraint", type=str, default=None,
                        help="Constraint name (only used to look up threads per core)")
    parser.add_argument("-e", "--extra", type=str, default='',
                        help="Extra shell commands to run after the site env block and before "
                             "launching, e.g. to activate a virtual environment.")
    parser.add_argument("--no-env", action='store_true',
                        help="Skip the site `env` block (module loads etc.), e.g. if your "
                             "environment is already set up.")
    parser.add_argument("--dry-run", action='store_true',
                        help="Print the launch script without running it.")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="Command to launch (put it after --)")
    args = parser.parse_args()

    cmd = args.command
    if cmd and cmd[0] == '--': cmd = cmd[1:]
    if not cmd: parser.error("No command given.")
    cmd = shlex.join(cmd)

    nproc = args.nproc or _env_int('SLURM_NTASKS') or 1
    threads = args.threads or _env_int('SLURM_CPUS_PER_TASK', 'OMP_NUM_THREADS') or 1

    site = mbatch.detect_site() if args.site is None else args.site
    config = mbatch.load_template(site)
    launcher = config.get('launcher') or ''
    if '!CPTFLAG' in launcher or '!HYPERTHREADS' in launcher:
        constraint = mbatch.get_default(config, 'constraint', args.constraint)
        partition = mbatch.get_default(config, 'part', args.partition)
        tpc = mbatch.get_tpc(config, constraint, partition)
    else:
        tpc = 1

    script = mbatch.render_launcher(config, cmd, nproc, threads, threads_per_core=tpc,
                                    extra=args.extra, with_env=not args.no_env)

    if args.dry_run:
        print(script)
        return
    sys.stdout.flush()
    os.execvp('bash', ['bash', '-c', script])  # replace this process; exit code passes through

if __name__ == '__main__':
    main()
