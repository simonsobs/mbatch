======
mbatch
======

``mbatch`` is a parallelized pipeline script plumbing tool. It aims to be simple; it does *not* aim to be powerful, flexible or automagical e.g. like ``parsl``. It is intended to be of specialized use for SLURM-based hybrid MPI+OpenMP pipelines and emphasizes versioning, reproducibility and controlled caching.  ``mbatch`` aims to provide a quick way to stitch together existing pipeline scripts without requiring significant code changes. A pipeline can be put together using a YAML file that stitches together various stages, where each stage has its own script that outputs products to disk. Unlike more generic pipeline tools (e.g. ``ceci``, ``BBpipe``), dependencies between stages have to be specified manually, and are only used to specify dependencies between SLURM submissions. ``mbatch`` also allows optional checks of the git cleanliness of specified modules, and logs this to aid future reproducibility.

* Free software: BSD license
* OS support: Unix-like (e.g. Linux, Mac OS X, but not Windows)
* Requires Python >= 3.6


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

Usage
-----

``mbatch`` works best with an existing pipeline structure that can be
broken down into stages. Each stage has its own script and outputs its
products to disk. A stage may depend on the outputs of other stages.

When writing a new pipeline or modifying an existing one to work with
``mbatch``, only a few things need to be kept in mind:

* The pipeline stages scripts do *not* need to do any versioning or tagging of individual runs. This is done through
  the ``mbatch`` project name specified for each submission.
* Every pipeline stage script should accept an argument ``--output-dir``. The user will not have
  to set this argument; it is managed by ``mbatch``.
* All of the stage output products should then be stored in the directory pointed to by ``args.output-dir``.
* If the stage needs products as input from a different stage e.g. with name ``stage1``, they should be obtained from
  ``{args.output_dir}/../stage1/``.

That's it! Once your pipeline scripts have been set up this way, you will need to write a configuration
file that specifies things like what MPI scheme to use for each stage, what other stages it depends on, etc.

