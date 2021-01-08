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
* Requires Python >= 3.6

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

First, you should pip install ``mbatch``, either off PyPI:

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

Pipeline requirements
---------------------

``mbatch`` works best with an existing pipeline structure that can be
broken down into stages. Each stage has its own script and outputs its
products to disk. A stage may depend on the outputs of other stages.

When writing a new pipeline or modifying an existing one to work with
``mbatch``, we recommend using the ``argparse`` Python module. Only a few things need to be kept in mind:

* The pipeline stages scripts do *not* need to do any versioning or tagging of individual runs. This is done through
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
    



