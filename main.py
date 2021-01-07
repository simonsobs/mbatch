import os,sys,shutil,subprocess,copy,shlex,glob,re
import argparse
import warnings
import yaml
import slurmr
from prompt_toolkit import print_formatted_text as fprint, HTML, prompt
from pprint import pprint

"""
Caching

We take a conservative approach to caching and reusing.
In order for a stage to be reused, four conditions have to be met:
1. There must be a SLURM output file (or local equivalent) that
clearly indicates that the most recent job was completed successfully
2. There must be a saved configuration file in the directory
that perfectly matches the submitted config for that stage
3. Git hashes and package versions should match (this can be overriden)
4. it must not depend on a stage that is not going to be reused NOT IMPLEMENTED YET

To do 1:
1. we search for get_out_file_root()* in the output directory and pick the last one
2. we extract the jobid from that
3. we run
sacct -j JOBID --format=State --parsable2
4. This should return
State
COMPLETED
COMPLETED
...
or something like that. We check that this is the case. Make sure this is sufficient by looking at niagara history.

To do 2:
When jobs are submitted, we save a config file for that section there and check against it.


During submissions, we just need to show a summary like

Stage1               REUSED
Stage2               SKIPPED
Stage3               SUBMITTED
Stage4               SUBMITTED

and do a Y/N confirm on that summary. Skipping should be rare and is done through the --skip
argument. That will force reuse without doing the above checks.




"""
    
def main(args):

    # Load config file
    with open(args.config_yaml, 'r') as stream:
        config = yaml.safe_load(stream)

    # Root directory
    root_dir = config['root_dir']
    
    # Check if we have SLURM
    have_slurm = slurmr.check_slurm()
    if not(have_slurm):
        print("No SLURM detected. We will be locally "
              "executing commands serially.")
    if args.dry_run:
        print("We are doing a dry run, so we will just print to "
              "screen.")

    # Do git checks
    pkg_gitdict = slurmr.gitcheck(config,'gitcheck_pkgs',package=True)
    pth_gitdict = slurmr.gitcheck(config,'gitcheck_paths',package=False)

    # Get global values if any
    global_vals = config.get('globals',{})

    # Get stages in order of dependencies
    cstages = config['stages']
    stage_names = list(cstages.keys())

    # Unroll loops from cstags into ostages
    cstages = config['stages']
    ostages = {} # Unrolled stage dictionary
    unroll_map = {} # dict mapping parent stage name to list of unrolled iterated stage names
    for stage in stage_names:
        # Check if this is a looped stage
        if ('arg' in cstages[stage]):
            if (type(cstages[stage]['arg'])) in [list,tuple]:
                unroll_map[stage] = []
                for k,arg in enumerate(cstages[stage]['arg']):
                    if len(shlex.split(arg))>1: raise Exception("Argument should not be interpretable as multiple arguments.")
                    new_stage_name = f'{stage}_{arg}'
                    if new_stage_name in stage_names:
                        slurmr.raise_exception(f"Internal loop stage name "
                                        "clashes with {stage}_!loop_iteration_{k}. "
                                        "Please use a different stage name.")
                    ostages[new_stage_name] = copy.deepcopy(cstages[stage])
                    del ostages[new_stage_name]['arg']
                    ostages[new_stage_name]['arg'] = cstages[stage]['arg'][k]
                    unroll_map[stage].append(new_stage_name)
            else:
                if len(shlex.split(cstages[stage]['arg']))>1: raise Exception("Argument should not be interpretable as multiple arguments.")
                ostages[stage] = copy.deepcopy(cstages[stage])
        else:
            ostages[stage] = copy.deepcopy(cstages[stage])

    stage_names = list(ostages.keys())
    # Map dependencies
    deps = {} # Mapping from stage to its dependencies
    depended = [] # List of stages that are depended on
    for sname in stage_names:
        ds = ostages[sname].get('depends')
        if ds is None: continue
        my_deps = []
        for d in ds:
            if not(d in stage_names) and not(d in unroll_map):
                slurmr.raise_exception(f"Stage {d} required by {sname} not found in configuration file.")
            if d in unroll_map:
                my_deps = my_deps + unroll_map[d]
            else:
                my_deps.append(d)
        depended = depended + my_deps
        deps[sname] = my_deps

    if slurmr.has_loop(deps): slurmr.raise_exception("Circular dependency detected.")
    stages = slurmr.flatten(deps) # Ordered by dependency
    # The above only contains stages that depend on something or something also depends on
    # Let's just append any others and warn about them
    for ostage in stage_names:
        if ostage not in stages:
            fprint(HTML(f"<ansiyellow>WARNING: stage {ostage} does not depend on anything, and nothing depends on it. Adding to queue anyway...</ansiyellow>"))
            stages.append(ostage)
    if set(stages)!=set(stage_names): slurmr.raise_exception("Internal error in arranging stages. Please report this bug.")

    # Check sanity of skipped stages list
    if args.skip is None: args.skip = []
    for skipstage in args.skip:
        if not(skipstage in stages): slurmr.raise_exception("Asked to skip a stage that is not in the list of stages.")
    
    # Parse arguments and prepare SLURM scripts

    if have_slurm or args.force_slurm:
        site = slurmr.detect_site() if args.site is None else args.site
        sbatch_config = slurmr.load_template(site)

    ###########################
    reuse_stages = []

    if not(args.no_reuse):
        # We decide which ones to resume here
        for stage in stages:
            # We check if the last submitted job (if it exists) was completed
            # TODO: add check for local runs, not just sbatch
            root = slurmr.get_out_file_root(root_dir,stage,args.project,site) + "_"
            suffix = ".txt"
            fs = glob.glob(root + "*" + suffix)
            if len(fs)==0:
                completed = False
            else:
                last_job = max([int(re.search(rf'{root}(.*?){suffix}', f).group(1)) for f in fs])
                output = slurmr.run_local(['sacct', '-j',
                                           str(last_job), '--format=State',
                                           '--parsable2'],
                                          verbose=False).split('\n')
                completed = True
                for i,line in enumerate(output):
                    if i==0:
                        if line.strip()!='State': slurmr.raise_exception("Unexpected output from sacct.")
                    elif i==(len(output)-1):
                        if line.strip()!='': slurmr.raise_exception("Unexpected output from sacct.")
                    else:
                        if line.strip()!='COMPLETED':
                            completed = False
                            break

            if not(completed): continue


            # Next check if dictionaries match
            try:
                with open(slurmr.get_stage_config_filename(root_dir,stage,args.project), 'r') as stream:
                    saved_config = yaml.safe_load(stream)
            except:
                fprint(HTML(f"<ansiyellow>Could not find saved configuration for {stage} even though completed job was detected. Will not re-use this stage.</ansiyellow>"))
                continue
            # We don't need to make sure the parallel options are the same
            saved_config['stage'][stage].pop('parallel', None)
            comp_dict = copy.deepcopy(ostages[stage])
            comp_dict.pop('parallel', None)
            # TODO: make sure this comparison of nested dictionaries is sufficient
            if saved_config['stage'][stage]!=comp_dict: continue

            # Next we check if there are git differences
            if not(args.ignore_git):
                if saved_config['stage']['pkg_gitdict']!=pkg_gitdict: continue
                if saved_config['stage']['pth_gitdict']!=pth_gitdict: continue

            # We made it this far, which means this stage can be reused
            reuse_stages.append(stage)

    ###########################

    is_sbatch = (have_slurm or args.force_slurm) and not(args.force_local)
    is_local = not(have_slurm) or args.force_local
    if sum([int(x) for x in [is_sbatch,is_local]])!=1: slurmr.raise_exception("Inconsistency in submission vs. local. Report bug.")
    
    # Check if any reused stages have dependencies that are not reused
    # If so we will not reuse those stages
    # Algorithm is linear since `stages` is already sorted
    for stage in stages:
        if stage in reuse_stages:
            if not(stage in deps): continue
            redo = False
            for d in deps[stage]:
                if d in reuse_stages: redo = True
            if redo: reuse_stages.remove(stage)
            
            
    # A summary and a prompt
    print(f"SUMMARY FOR SUBMISSION OF PROJECT {args.project}")
    for stage in stages:
        if stage in reuse_stages:
            sumtxt='<red><b>[REUSE]</b></red>'
        elif stage in args.skip: sumtxt='<red><b>[SKIP]</b></red>'
        else: sumtxt='<green>[SUBMIT]</green>'
        fprint(HTML(stage+'\t\t'+sumtxt))

    reply = prompt("Should we proceed with this? (Y/n)")
    reply = reply.strip().upper()
    if reply in ['Y','YES']:
        pass
    elif reply in ['N','NO']:
        sys.exit(0)
    else:
        slurmr.raise_exception("Invalid input.")

        
    # Make project directory
    proj_dir = slurmr.get_project_dir(root_dir,args.project)
    os.makedirs(proj_dir, exist_ok=True)

    jobids = {}
    for stage in stages:
        if stage in args.skip:
            fprint(HTML(f"<ansiyellow>Skipping stage {stage} as requested.</ansiyellow>"))
            if stage in depended: fprint(HTML(f"<ansiyellow>WARNING: skipped stage {stage} is depended on by others.</ansiyellow>"))
            continue
        if stage in reuse_stages:
            fprint(HTML(f"<ansiyellow>Reusing stage {stage} as requested.</ansiyellow>"))
            if stage in depended: fprint(HTML(f"<ansiyellow>WARNING: reused stage {stage} is depended on by others.</ansiyellow>"))
            continue

        # Get command
        execution,script,pargs = slurmr.get_command(global_vals, copy.deepcopy(ostages), stage)

        # Make output directory
        output_dir =  slurmr.get_output_dir(root_dir,stage,args.project)
        os.makedirs(output_dir, exist_ok=True)


        # Construct dependency string
        now_deps = deps.get(stage,[])
        if len(now_deps)>=1:
            jlist = []
            for s in now_deps:
                if not(s in args.skip) and not(s in reuse_stages):
                    jlist.append(jobids[s])
            if len(jlist)>=1:
                depstr = ':'.join(jlist)
                depstr = "--dependency=afterok:" + depstr
            else:
                depstr = None
        else:
            depstr = None
        
        if is_sbatch:
            jobid = slurmr.submit_slurm(stage,sbatch_config,
                                        copy.deepcopy(ostages[stage]).get('parallel',None),
                                        execution,script,pargs,
                                        dry_run=args.dry_run,
                                        output_dir=output_dir,
                                        project=args.project,
                                        site=site,depstr=depstr,
                                        account=args.account,
                                        qos=args.qos)
        if is_local:
            if pargs=='':
                cmds = [execution,script, '--output-dir',output_dir]
            else:
                cmds = [execution,script, pargs, '--output-dir',output_dir]
            jobid = slurmr.run_local(cmds,dry_run=args.dry_run)

        if not(args.dry_run):
            out_dict = {}
            out_dict['stage'] = {stage: copy.deepcopy(ostages[stage])}
            out_dict['stage']['pkg_gitdict'] = pkg_gitdict
            out_dict['stage']['pth_gitdict'] = pth_gitdict
            with open(slurmr.get_stage_config_filename(root_dir,stage,args.project), 'w') as f:
                yaml.dump(out_dict, f, default_flow_style=False)

        jobids[stage] = jobid
    

if __name__ == '__main__':
    if '--show-site-path' in sys.argv:
        print(slurmr.get_site_path())
        sys.exit(0)
    parser = argparse.ArgumentParser(description = 'A pipeline script plumbing tool.')
    parser.add_argument('project', help='Name of project.')
    parser.add_argument('config_yaml', help='Path to the configuration file.')
    parser.add_argument("--site",     type=str,  default=None,help="Name of a pre-defined cluster site. "
                        "If not specified, will attempt to detect automatically.")
    parser.add_argument("--dry-run", action='store_true',help='Only show submissions.')
    parser.add_argument("--no-reuse", action='store_true',help='Do not reuse any stages (unless implicitly requested through the --skip argument).')
    parser.add_argument("--ignore-git", action='store_true',help='Ignore git differences when deciding whether to reuse a stage.')
    parser.add_argument("--force-local", action='store_true',help='Force local run.')
    parser.add_argument("--force-slurm", action='store_true',help="Force SLURM. "
                        "If SLURM is not detected and --dry-run is not enabled, this will fail.")
    parser.add_argument('--skip', nargs='+', help='List of stages to skip, separated by space. These stages will be skipped even if others depend on them.')
    parser.add_argument("-A","--account", type=str,  default=None,help='sbatch account argument. e.g. on cori, use this to select the account that is charged.')
    parser.add_argument("-q","--qos", type=str,  default=None,help='sbatch QOS argument. e.g. on cori, the default is debug, which only provides 30 minutes, so you should explicitly use "--qos regular" on cori.')
    args = parser.parse_args()
    if args.force_local and args.force_slurm: slurmr.raise_exception("You can\'t force both local and SLURM.")
    main(args)
