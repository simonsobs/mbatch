======
mbatch
======

``mbatch`` is a parallelized pipeline script plumbing tool. It aims to be
simple; it does *not* aim to be powerful, flexible or automagical e.g. like
``parsl``. It is intended to be of specialized use for SLURM-based hybrid
MPI+OpenMP pipelines and emphasizes versioning, reproducibility and controlled
caching.  ``mbatch`` aims to provide a quick way to stitch together existing
pipeline scripts without requiring significant code changes. A pipeline can be
put together using a YAML file that stitches together various stages, where each
stage has its own script that outputs products to disk. Unlike more generic
pipeline tools (e.g. ``ceci``, ``BBpipe``), dependencies between stages have to
be specified manually, and are only used to specify dependencies between SLURM
submissions; however, this also means far less boilerplate code is needed to make
your pipeline compatible with this tool. ``mbatch`` also does checks
of the git cleanliness of specified modules, and logs this to aid future
reproducibility and automatically decide whether to re-use previously run stages.

* Free software: BSD license
* OS support: Unix-like (e.g. Linux, Mac OS X, but not Windows)
* Requires Python >= 3.8

Features
--------

* Separates projects and stages within projects by automatically creating
  directory structures
* Detects cluster computing site, composes appropriate SLURM ``sbatch`` scripts, assigns
  dependencies and submits them
* Logs all information on a per-stage basis, including arguments used for the
  run, git and package version information, SLURM output and job completion status
* Based on the logged information, automatically decides whether to re-use
  certain stages (and not submit them to the queue)
* Shows a summary of what stages will be re-used and what will be submitted, and
  prompts user to confirm before proceeding


Installing
----------

First, you should pip install ``mbatch``, either off PyPI (currently not implemented, use git clone below):

.. code-block:: console
		
   $ pip install mbatch --user

or by git cloning and then doing a local install:

.. code-block:: console
		
   $ git clone git@github.com:simonsobs/mbatch.git
   $ cd mbatch
   $ python setup.py install --user

You will likely need to do a small amount of configuration, as described below.

Configuration
-------------
   
Next, you should make sure that there are appropriate configurations
for the sites you frequently use. You can find out the location
of the default site configuration files by running:

.. code-block:: console
		
   $ mbatch --show-site-path

This will typically show a location like

```
~/.local/lib/python3.8/site-packages/mbatch/data/sites/
```

You can edit the site files here e.g. ``niagara.yml`` for the ``niagara`` Scinet
supercomputing site, though note that the default provided
ones may end up overwritten when ``mbatch`` is updated. To guard against that,
you can copy the contents of ``~/.local/lib/python3.8/site-packages/mbatch/data/sites/``
(or whatever was the result of the above command) to ``~/.mbatch/``, which is the
first location that ``mbatch`` looks for site files.

You can also create a custom SLURM template `~/.mbatch/mysite.yml`. For example a site with 8 cores per node and 8GB memory per node would look like:

.. code-block:: yaml

  default_constraint: None
  default_part: None
  default_qos: None
  default_account: None
  architecture:
    None:      # constraint name
      None:    # partition name
        cores_per_node: 8
        threads_per_core: 2
        memory_per_node_gb: 8

  template: |
    #!/bin/bash!CONSTRAINT!QOS!PARTITION!ACCOUNT
    #SBATCH --nodes=!NODES
    #SBATCH --time=!WALL
    #SBATCH --ntasks-per-node=!TASKSPERNODE
    #SBATCH --cpus-per-task=!THREADS
    #SBATCH --job-name=!JOBNAME
    #SBATCH --output=!OUT_%j.txt
    #SBATCH --mail-type=FAIL
    #SBATCH --mail-user=

    cd $SLURM_SUBMIT_DIR

    !ENV

    !EXTRA

    !LAUNCH

  # Environment setup; inserted at !ENV and also used by mrun
  env: |
    export DISABLE_MPI=false
    module load python

  # Thread settings, binding and launch line; inserted at !LAUNCH and also used by mrun
  launcher: |
    export OMP_NUM_THREADS=!THREADS
    export NUMEXPR_MAX_THREADS=!THREADS

    mpirun !NPFLAG !CMD

Use ``--site mysite`` to specify this template.
To enable hyper-threading, change ``!THREADS`` to ``!HYPERTHREADS``.

The ``env`` and ``launcher`` blocks are optional: a template that does not
contain ``!ENV`` or ``!LAUNCH`` is used as-is (older site files with the launch
line written directly into ``template`` keep working), but then ``mrun`` cannot
be used with that site. Two placeholders only take effect under ``mrun`` and
expand to nothing inside sbatch scripts, where the launcher picks up the counts
from the allocation: ``!NPFLAG`` becomes ``-n <nproc>`` and ``!CPTFLAG`` becomes
``-c <cpus per task>`` (use the latter with ``srun``).


Pipeline requirements
---------------------

``mbatch`` works best with an existing pipeline structure that can be
broken down into stages. Each stage has its own script and outputs its
products to disk. A stage may depend on the outputs of other stages.

When writing a new pipeline or modifying an existing one to work with
``mbatch``, we recommend using the ``argparse`` Python module. Only a few things need to be kept in mind:

* The pipeline stage scripts do *not* need to do any versioning or tagging of individual runs. This is done through
  the ``mbatch`` project name specified for each submission.
* Every pipeline stage script should accept an argument ``--output-dir``. The user will not have
  to set this argument; it is managed by ``mbatch``.
* The script should only accept one positional argument: ``mbatch`` allows you
  to loop over different values of this argument when submitting jobs. Any
  number of optional arguments can be provided.
* All of the stage output products should then be stored in the directory pointed to by ``args.output-dir``.
* If the stage needs products as input from a different stage e.g. with name ``stage1``, they should be obtained from
  ``{args.output_dir}/../stage1/``.

That's it! Once your pipeline scripts have been set up this way, you will need to write a configuration
file that specifies things like what MPI scheme to use for each stage, what
other stages it depends on, etc.


Example
-------

Let's go over the simple example in the `example/` directory of mbatch's Github
repository. To try out the example yourself, you will have to clone the
repository as explained earlier.

We change into the example directory where there are a set of Python scripts
stage1.py, stage2.py, stage3.py, stage4.py that contain rudimentary example
pipeline stages that may or may not read some inputs and save output data to disk.

For this example, we will create a directory called `output` that will hold
any output data. `mbatch` works by submitting a set of scripts using SLURM's
`sbatch` and asking for outputs from these scripts to be organized into
separate stage directories for each script, which are all under the same "project"
directory. The `output` directory we make here will be the root (parent) directory
for any projects we submit for this example.

.. code-block:: bash

		$ cd example
		$ mkdir output
		$ ls
		
		example
		├── output/
		├── stage1.py
		├── stage2.py
		├── stage3.py
		├── stage4.py
		└── example.yml


We also see an example configuration file example.yml which will
be the input for `mbatch` that stitches together these stage scripts.

Let's examine example.yml closely. The YAML file includes the following:

.. code-block:: bash

		root_dir: output/


This indicates that the root directory for any projects run with this configuration
file will be `output/`.  A project with name "foo", for example, will then go into
the directory `output/foo/` and outputs of pipeline stages of this project will go
into sub-directories of `output/foo/`.

Next up in `example.yml` we see

.. code-block:: bash

		globals:
		    lmax: 3000
		    lmin: 100


This defines two arguments that are global to all pipeline stages. These
arguments can then be referenced by any pipeline stage that we wish to make
it accessible to. More on this later.

Further down in `example.yml` we see

.. code-block:: bash

		gitcheck_pkgs:
		    - numpy
		    - scipy

		gitcheck_paths:
		    - ./
		      

`gitcheck_pkgs`: This directs `mbatch` to log the git status (commit hash, branch, etc.)
and/or package version of the listed Python packages. Whether these packages
have changed will subseqently influence whether previously completed stages
are re-used. `gitcheck_paths` is similar, but instead of specifying
a package, you specify a path to a directory that is under git version control.
In this example `./` will refer to the `mbatch` repository itself.


Finally, in example.yml we see the definition of the pipeline stages, which are
described in the comments below:


.. code-block:: bash

		# This structure will contain all the pipeline stage
		# definitions. The order in which the stages are listed
		# below does not matter, but the `depends` section in
		# each stage will influence the order in which they are
		# actually queued.
		stages:

		    # This first stage named `stage1` uses the python executable to run
		    # stage1.py (in the same directory). It passes no arguments (no globals
		    # either). And since it doesn't have a `parallel` section, it uses
		    # default options, including requesting only a walltime of 15 minutes.
		    # It does not depend on any other stages either, so it won't wait in
		    # the queue for others to finish.
		    stage1:
		        exec: python
		        script: stage1.py
		
		    # This stage named `stage2` also doesn't depend on others and thus won't
		    # wait, but it (a) does specify that we should pass the global variables
		    # as optional arguments to stage2.py. It also passes a few other options
		    # to the script. It does not pass any positional arguments.
		    # It also explicitly says to use 8 OpenMP threads and
		    # requests 15 minutes of walltime.
            # Note: If hyper-threading (2 threads per core) is enabled in SLURM
            # template, the generated sbatch script will have
            # OMP_NUM_THREADS=16 and --cpus-per-task=16
		    stage2:
		        exec: python
		        script: stage2.py
		        globals:
		            - lmin
		            - lmax
		        options:
		            arg1: 0
		            arg2: 1
		            flag1: true
		        parallel:
		            threads: 8
		            walltime: 00:15:00
		    
		    
		    # This stage named `stage3` depends on stage1 and stage2, so it will
		    # only start after stage1 and stage2 have successfully completed with
		    # exit code zero. In addition to passing globals and the optional argument
		    # "nsims", it also passes one positional argument "TTTT" specified through
		    # the "arg" keyword.
		    # In the ``parallel`` section we request nproc=4 MPI processes. As an
		    # alternative to specifying the exact number of OpenMP threads, we provide
		    # an estimate for the maximum memory each process will use memory_gb and
		    # the minimum number of threads to use. Based on the memory available on
		    # a single node at the computing site and the number of cores per node,
		    # mbatch will use an even number of threads = max(min_threads,
		    # cores_per_node/memory_per node * memory_gb). 
		    stage3:
		         exec: python
		         script: stage3.py
		         depends:
		             - stage1
		             - stage2
			 globals:
			     - lmin
			     - lmax
			 options:
			     nsims: 32
			     arg: TTTT
			 parallel:
			     nproc: 4
			     memory_gb: 4
			     min_threads: 8
			     walltime: 00:15:00

		    # This stage named `stage3loop` is similar to `stage3` but
		    # it provides a list for `arg`. This will create N copies
		    # of this stage, each of which loop the positional argument
		    # over the N elements of the list specified by `arg`.
		    stage3loop:
		        exec: python
		        script: stage3.py
		        depends:
		            - stage1
			    - stage2
			globals:
			    - lmin
			    - lmax
			options:
			    nsims: 32
			arg:
			    - TTTT
			    - TTEE
			    - TETE
			parallel:
			    nproc: 4
			    memory_gb: 4
			    min_threads: 8
			    walltime: 00:15:00

		    # Another stage that depends on a previous one
		    stage4:
 		        exec: python
			script: stage4.py
			depends:
			    - stage3
			    - stage3loop
			parallel:
			    nproc: 1
			    threads: 8
			    walltime: 00:15:00
					      
		     # Another stage that depends on stage4, but uses
		     # the same script as did stage4.
		     stage5:
		         exec: python
			 script: stage4.py
		     depends:
			     - stage4
			 parallel:
			     nproc: 1
			     threads: 8
			     walltime: 00:15:00
						

We can run this pipeline configuration with `mbatch`. Here is how it looks when run locally (not on a remote system that has SLURM installed):

.. code-block:: bash

		$ mbatch foo example.yml
		No SLURM detected. We will be locally executing commands serially.
		We are doing a dry run, so we will just print to screen.
		SUMMARY FOR SUBMISSION OF PROJECT foo
		stage1     [SUBMIT]
		stage2     [SUBMIT]
		stage3     [SUBMIT]
		stage3loop_TTTT    [SUBMIT]
		stage3loop_TTEE    [SUBMIT]
		stage3loop_TETE    [SUBMIT]
		stage4     [SUBMIT]
		stage5     [SUBMIT]
		Proceed with this? (Y/n)

	
which shows a summary of the stages that will be reused or submitted (in a first run where no products exist, all will be submitted). You will receive a prompt to confirm the submission.

Here, `mbatch` has detected that all stages need to be run (because no previous outputs exist),
and asks us to confirm the submission. After proceeding and the commands have completed
(in serial execution, since we are trying this locally), the directory structure now looks like:


.. code-block:: bash

		$ tree .
		.
		├── example.yml
		├── output
		│   └── foo
		│       ├── stage1
		│       │   ├── stage1_result.txt
		│       │   └── stage_config.yml
		│       ├── stage2
		│       │   ├── stage2_result.txt
		│       │   └── stage_config.yml
		│       ├── stage3
		│       │   ├── stage3_result_TTTT.txt
		│       │   └── stage_config.yml
		│       ├── stage3loop_TETE
		│       │   ├── stage3_result_TETE.txt
		│       │   └── stage_config.yml
		│       ├── stage3loop_TTEE
		│       │   ├── stage3_result_TTEE.txt
		│       │   └── stage_config.yml
		│       ├── stage3loop_TTTT
		│       │   ├── stage3_result_TTTT.txt
		│       │   └── stage_config.yml
		│       ├── stage4
		│       │   ├── stage4_result.txt
		│       │   └── stage_config.yml
		│       └── stage5
		│           ├── stage4_result.txt
		│           └── stage_config.yml
		├── stage1.py
		├── stage2.py
		├── stage3.py
		└── stage4.py


For more information on running mbatch, use

.. code-block:: bash

	mbatch -h


Wrapper for OpenMP+MPI jobs
---------------------------

``mbatch`` now includes a wrapper ``wmpi`` for hybrid OpenMP+MPI jobs that are not part
of a pipeline. Here's how to use it:

.. code-block:: bash

		
	usage: wmpi [-h] [-d DEPENDENCIES] [-o OUTPUT_DIR] [-t THREADS] [-s SITE]
		    [-n NAME] [-A ACCOUNT] [-q QOS] [-p PARTITION] [-c CONSTRAINT]
		    [-w WALLTIME] [--dry-run]
		    N Command

	Submit hybrid OpenMP+MPI jobs

	positional arguments:
	  N                     Number of MPI jobs
	  Command               Command

	optional arguments:
	  -h, --help            show this help message and exit
	  -d DEPENDENCIES, --dependencies DEPENDENCIES
				Comma separated list of dependency JOBIDs
	  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
				Output directory
	  -t THREADS, --threads THREADS
				Number of threads
	  -s SITE, --site SITE  Site name (optional; will auto-detect if not provided)
	  -n NAME, --name NAME  Job name
	  -A ACCOUNT, --account ACCOUNT
				Account name
	  -q QOS, --qos QOS     QOS name
	  -p PARTITION, --partition PARTITION
				Partition name
	  -c CONSTRAINT, --constraint CONSTRAINT
				Constraint name
	  -w WALLTIME, --walltime WALLTIME
				Walltime
	  --dry-run             Only show submissions.

`mbatch` will then pick a template for an `sbatch` configuration file by detecting what cluster computer you are using (built-in sites: trillium, niagara, perlmutter, symmetry and penn-gpc), populate this template and submit it using `sbatch`. The idea behind this wrapper is that you won't have to think too much about which cluster you are on (beyond the core counts).


Launching interactively with mrun
---------------------------------

``mrun`` launches a hybrid OpenMP+MPI command right away, using the same
site-aware ``env`` and ``launcher`` blocks that go into the sbatch scripts
(thread exports, CPU binding and the ``mpirun``/``srun`` line). This means quick
tests and benchmarks are set up and bound the same way as batch jobs submitted
with ``mbatch`` or ``wmpi``. Here's how to use it:

.. code-block:: bash

	usage: mrun [-h] [-n NPROC] [-t THREADS] [-s SITE] [-p PARTITION]
	            [-c CONSTRAINT] [-e EXTRA] [--no-env] [--dry-run] [--bench-sht]
	            ...

	Launch a hybrid MPI+OpenMP command with the site-aware launcher from the site
	configuration (the same one used in sbatch scripts). Use inside an interactive
	allocation (salloc, debugjob) or on a login node.

	positional arguments:
	  command               Command to launch (put it after --)

	options:
	  -h, --help            show this help message and exit
	  -n NPROC, --nproc NPROC
	                        Number of MPI processes (default: $SLURM_NTASKS, else
	                        1)
	  -t THREADS, --threads THREADS
	                        OpenMP threads per process (default:
	                        $SLURM_CPUS_PER_TASK, else $OMP_NUM_THREADS, else 1)
	  -s SITE, --site SITE  Site name (optional; will auto-detect if not provided)
	  -p PARTITION, --partition PARTITION
	                        Partition name (only used to look up threads per core)
	  -c CONSTRAINT, --constraint CONSTRAINT
	                        Constraint name (only used to look up threads per
	                        core)
	  -e EXTRA, --extra EXTRA
	                        Extra shell commands to run after the site env block
	                        and before launching, e.g. to activate a virtual
	                        environment.
	  --no-env              Skip the site `env` block (module loads etc.), e.g. if
	                        your environment is already set up.
	  --dry-run             Print the launch script without running it.
	  --bench-sht           Instead of a command, run the SHT benchmark `mbench
	                        sht`; arguments after -- are passed to it. Needs
	                        mbatch and pixell in the launched environment.

	Example: mrun -n 4 -t 24 -- python myscript.py --lmax 4000

Everything after ``--`` is the command to launch, passed through with its
quoting intact. ``mrun`` replaces itself with the launch script, so the exit
code of your command is the exit code of ``mrun``.

Modes of use
~~~~~~~~~~~~

**Inside an interactive allocation** (e.g. ``salloc`` or ``debugjob``). This is
the main use case. ``-n`` and ``-t`` default to the allocation's
``$SLURM_NTASKS`` and ``$SLURM_CPUS_PER_TASK``, so this is often all you need:

.. code-block:: bash

	salloc --nodes=1 --ntasks=4 --cpus-per-task=24 --time=1:00:00
	mrun -- python stage1.py --lmax 4000

Pass ``-n``/``-t`` to run with fewer processes or threads than the allocation
provides, e.g. to scan thread counts in a benchmark:

.. code-block:: bash

	for t in 8 24 48 96; do mrun -n 1 -t $t -- python bench.py; done

**On a login node or a machine without an allocation.** Sites whose launcher
uses ``mpirun`` run the processes on the current node, with the same binding
rules as batch jobs. ``-n`` and ``-t`` default to 1 and ``$OMP_NUM_THREADS``
when no allocation is present. Sites whose launcher uses ``srun`` (e.g.
``niagara``, ``perlmutter``) need an allocation; outside one, ``srun`` will
either fail or request a new allocation, depending on the cluster. Keep
login-node runs short and small, following your site's policies.

**Dry run.** ``--dry-run`` prints the fully rendered launch script (env block,
extra commands, thread exports, binding logic and launch line) without running
anything. This is useful for checking what binding a given thread count
produces:

.. code-block:: bash

	mrun -n 4 -t 8 --dry-run -- python x.py

Environment handling
~~~~~~~~~~~~~~~~~~~~

By default the launch script runs, in order:

1. the site ``env`` block (module loads etc.),
2. any commands passed with ``-e``/``--extra``,
3. the site ``launcher`` block.

This mirrors the ``!ENV``, ``!EXTRA`` and ``!LAUNCH`` order in the sbatch
templates. Use ``-e`` to activate a virtual environment after the modules are
loaded, and ``--no-env`` to skip the module loads when your shell is already set
up (the launcher's thread exports and binding are still applied):

.. code-block:: bash

	mrun -e "source ~/venv/bin/activate" -- python myscript.py
	mrun --no-env -- python myscript.py

The ``env`` block is run with a non-interactive ``bash``, so the ``module``
command must be available as an exported shell function. This is the default
with Lmod; if it isn't the case on your system, load modules yourself and use
``--no-env``.

Placeholders in the launcher
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``mrun`` fills the same placeholders as the sbatch templates (``!CMD``,
``!THREADS``, ``!HYPERTHREADS``, ``!TASKS``), plus two that only take effect
under ``mrun`` and expand to nothing inside sbatch scripts:

* ``!NPFLAG`` becomes ``-n <nproc>``.
* ``!CPTFLAG`` becomes ``-c <threads x threads_per_core>``. Use it with
  ``srun``, since recent Slurm versions do not pass ``--cpus-per-task`` from an
  allocation down to ``srun``. ``-p``/``-c`` select the partition and constraint
  used to look up ``threads_per_core``.

``mrun`` only works with sites that define a ``launcher`` block (all built-in
sites do). See the Configuration section above for the site file layout.


Benchmarking with mbench
------------------------

``mbench`` provides benchmark workloads to run through ``mrun``, so that you can
see how a given number of processes, threads and CPU binding performs on a site.
Each MPI process runs its own copy of the benchmark. ``mbench`` does not change
any thread settings, so the results reflect the environment set up by your site
file and shell. Benchmarks are chosen with a subcommand; currently there is
one, ``sht``, which needs pixell (installable with the ``bench`` extra, e.g.
``pip install -e ".[bench]"``).

.. code-block:: bash

	mbench sht --res 30 --lmax 300 --nrep 2  # quick, small test
	mrun -n 1 -t 8 -- mbench sht --res 2 --op map2alm alm2map
	mrun -n 1 -t 8 -- mbench sht --pix healpix --nside 2048 --pol
	for t in 8 24 48 96; do mrun -n 1 -t $t -- mbench sht; done
	mrun -t 24 --bench-sht -- --full-sky   # same as: mrun -t 24 -- mbench sht --full-sky

``mbench sht`` draws random alms with a flat spectrum and times
``pixell.curvedsky`` map2alm and/or alm2map (``--op``). By default it uses a CAR
map covering a declination band (``--dec``, -63 to 23 degrees) at ``--res``
arcmin; ``--full-sky`` uses a full-sky CAR map, and ``--pix healpix`` a full-sky
HEALPix map at ``--nside``. ``--lmax`` defaults to 4000, so lower it together
with the resolution (it should not exceed about 180*60/res for CAR or
3*nside for HEALPix). ``--pol`` uses T, Q, U instead of a single scalar map,
and ``--double`` switches from single to double precision. Each operation is run
once as a warm-up and then ``--nrep`` times, and the mean, best and individual
times are printed.
