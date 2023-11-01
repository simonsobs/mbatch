import os,sys,shutil,subprocess,warnings,glob,re,shlex,copy
import argunparse,yaml,math,time
from prompt_toolkit import print_formatted_text as fprint, HTML, prompt
import random
from pathlib import Path
from pprint import pprint
import argparse

"""
Files produced:
e.g. project foo, stages bar1, bar2

# SLURM
foo
  bar1
     slurm_out_{stage}_{project}_{site}_{slurm)_{jobid}.txt # SLURM output, used to extract job id
     stage_config_{jobid}.yml # config file, contains time as well

# LOCAL
foo
  bar1
     local_out_{stage}_{project}_state_{jobid}.txt # completion status for local run, jobid is time when job finished
     stage_config_{jobid}.yml # config file, contains time as well (different from above)



"""

def query_yes_no(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")

def argmax(iterable):
    return max(enumerate(iterable), key=lambda x: x[1])[0]

def sint(x):
    if x.strip()=='': return 0
    return int(x)

def check_slurm():
    try:
        ret = subprocess.run(["sbatch","-V"])
        return True
    except FileNotFoundError:
        return False

def gitcheck(config,cname,package):
    try:
        gitchecks = config[cname]
    except:
        gitchecks = []
    odict = {}
    for pkg in gitchecks:
        #TODO: do something more with ginfo
        ginfo = get_info(package=pkg if package else None,
                                path=pkg if not(package) else None,
                                validate=True)
        odict[pkg] = ginfo
    return odict

def get_command(global_vals, stage_configs, stage):
    stage_config = stage_configs[stage]
    execution = stage_config['exec']
    if not(execution in ['python','python3']):
        raise_exception("Only Python execution "
                        "is currently supported. "
                        "Shell support will be "
                        "added soon.")
    script_name = stage_config['script']
    global_opts = stage_config.get('globals',[])
    arg = stage_config.get('arg','')
    if not(isinstance(arg,str)): raise_exception(f"arg should be a string. {artg} in {stage} does not satisfy this.")
    arg = [arg] if arg!='' else []
    options = stage_config.get('options',{})
    optkeys = list(options.keys())
    for global_opt in global_opts:
        if global_opt in optkeys:
            pprint(stage_configs[stage])
            pprint(stage)
            raise_exception(f"{global_opt} in {stage} config is already a global.")
        options[global_opt] = global_vals[global_opt]
    unparser = argunparse.ArgumentUnparser()
    unparsed = unparser.unparse(*arg, **options)
    if unparsed=='\"\"' or unparsed=='\'\'': unparsed = ''
    #TODO: check for malicious content in unparsed string since it comes
    #from an external library
    return execution,script_name,unparsed

def run_local(cmds,dry_run=False,verbose=True):
    icmds = [c.strip() for c in cmds]
    cmds = []
    for c in icmds:
        cmds = cmds + shlex.split(c)
    if verbose: print(f"Running {cmds} locally...")
    if dry_run:
        if verbose: print(' '.join(cmds))
        return str(random.randint(1,32768))
    else:
        sp = subprocess.run(cmds,stderr=sys.stderr, stdout=subprocess.PIPE)
        output = sp.stdout.decode("utf-8")
        if verbose: print(output)
        if sp.returncode!=0: raise_exception("Command returned non-zero exit code. See earlier error messages.")
        return output

def detect_site():
    sites = []
    env_check = os.environ.get('CLUSTER',None)
    if env_check=='niagara':
        sites.append( 'niagara' )
    elif env_check=='symmetry':
        sites.append( 'symmetry' )
    elif env_check=='penn-gpc':
        sites.append( 'penn-gpc' )
        
    env_check = os.environ.get('NERSC_HOST',None)
    if env_check=='cori':
        sites.append( 'cori' )
        
    if len(sites)==0:
        warnings.warn('No site specified through --site and did not automatically detect any sites. Using generic SLURM template.')
        sites.append( 'generic' )
    elif len(sites)==1:
        fprint(HTML(f'<ansiyellow>No site specified through --site; detected <b>{sites[0]}</b> automatically.</ansiyellow>'))
    else:
        raise_exception(f"More than one site detected through environment variables: {sites}. Please specificy explicitly through the --site argument.")
    return sites[0]

def get_site_path():
    # First try ~/.mbatch/*.yml
    home = str(Path.home())
    homepath = os.path.join(home,".mbatch")
    fs = glob.glob(homepath+"/*.yml")
    if len(fs)>=1: return homepath
    # Otherwise get path relative to this module
    this_dir, this_filename = os.path.split(__file__)
    template_path = os.path.join(this_dir, "data", "sites")
    return template_path

def load_template(site):
    template_path = os.path.join(get_site_path(), f"{site}.yml")
    with open(template_path, 'r') as stream:
        sbatch_config = yaml.safe_load(stream)
    return sbatch_config

def get_out_file_root(root_dir,stage,project,site):
    return os.path.join(get_output_dir(root_dir,stage,project),f'slurm_out_{stage}_{project}_{site}')

def get_local_out_file(root_dir,stage,project):
    return os.path.join(get_output_dir(root_dir,stage,project),f'local_out_{stage}_{project}_state')


def get_project_dir(root_dir,project):
    return os.path.join(root_dir,project)

def get_output_dir(root_dir,stage,project):
    return os.path.abspath(os.path.join(get_project_dir(root_dir,project),stage))

def get_stage_config_filename(root_dir,stage,project,jobid):
    return os.path.join(get_output_dir(root_dir,stage,project),f'stage_config_{jobid}.yml')


def get_default(config,name,arg):
    if not(arg is None):
        return arg
    else:
        return config[f'default_{name}']

def get_tpc(sbatch_config,constraint,partition):
    try:
        tpc = sbatch_config['architecture'][constraint][partition]['threads_per_core']
    except:
        fprint(HTML(f"<ansiyellow>WARNING: Number of threads per core not specified. Assuming hyperthreading by factor 2x ...</ansiyellow>"))
        tpc = 2
    return tpc
    
def submit_slurm(stage,sbatch_config,parallel_config,execution,
                 script,pargs,dry_run,output_dir,site,project,root_dir,
                 depstr=None,account=None,qos=None,partition=None,constraint=None):

    constraint = get_default(sbatch_config,'constraint',constraint)
    qos = get_default(sbatch_config,'qos',qos)
    partition = get_default(sbatch_config,'part',partition)
    account = get_default(sbatch_config,'account',account)
    cpn = sbatch_config['architecture'][constraint][partition]['cores_per_node']
    tpc = get_tpc(sbatch_config,constraint,partition)
    template = sbatch_config['template']
    cmd = ' '.join([execution,script,pargs]) + f' --output-dir {output_dir}'
    try:
        nproc = parallel_config['nproc']
    except (TypeError,KeyError) as e:
        nproc = 1
        fprint(HTML(f"<ansiyellow>No stage['parallel']['nproc'] found for {stage}. Assuming number of MPI processes nproc=1.</ansiyellow>"))

    try:
        memory_gb = parallel_config['memory_gb']
        if 'threads' in list(parallel_config.keys()): raise_exception("Both memory_gb and threads should not be specified.")
        if not('memory_per_node_gb' in list(sbatch_config['architecture'][constraint][partition].keys())): raise_exception("Using memory_gb but no memory_per_node_gb in site configuration.")
        if not('min_threads' in list(parallel_config.keys())): raise_exception("Need min_threads if using memory_gb.")
        # Maximum number of processes per node
        threads = max(math.ceil(1.*cpn/sbatch_config['architecture'][constraint][partition]['memory_per_node_gb']*parallel_config['memory_gb'] ),parallel_config['min_threads'])
        threads = threads + (threads%2)
        fprint(HTML(f"<ansiyellow>Converted memory {memory_gb} GB to number of threads {threads}.</ansiyellow>"))
    except (TypeError,KeyError) as e:
        threads = None

    if threads is None:
        try:
            threads = parallel_config['threads']
        except (TypeError,KeyError) as e:
            threads = cpn
            fprint(HTML(f"<ansiyellow>No stage['parallel']['threads'] found for {stage}. Assuming number of OpenMP threads={cpn}.</ansiyellow>"))
        
    try:
        walltime = parallel_config['walltime']
    except (TypeError,KeyError) as e:
        walltime = "00:15:00"
        fprint(HTML(f"<ansiyellow>No stage['parallel']['walltime'] found for <b>{stage}</b>. Assuming <b>walltime of {walltime}</b>.</ansiyellow>"))

    name = f'{stage}_{project}'
    out_file_root = get_out_file_root(root_dir,stage,project,site)
    sbatch_file_root = get_sbatch_script_file_root(output_dir,project,stage,site)
    return submit_slurm_core(template,name,cmd,nproc,cpn,threads,walltime,dry_run,
                             output_dir,site,out_file_root,sbatch_file_root,
                             depstr=depstr,account=account,qos=qos,partition=partition,constraint=constraint,threads_per_core=tpc)

def submit_slurm_core(template,name,cmd,nproc,cpn,threads,walltime,dry_run,output_dir,site,out_file_root,sbatch_file_root,
                      depstr=None,account=None,qos=None,partition=None,constraint=None,threads_per_core=2):

    num_cores = nproc * threads
    num_nodes = int(math.ceil(num_cores/cpn))
    totcores = num_nodes * cpn
    tasks_per_node = int(nproc*1./num_nodes)
    percent_used = num_cores*100./float(totcores)

    if percent_used<90.: 
        fprint(HTML(f"<ansiyellow>Submission {name} with {nproc} MPI process(es) and {threads} thread(s) and {num_nodes} nodes in the request, this means a node will have less than 90% of its cores utilized. Reconsider the way you choose your thread count or number of processes.</ansiyellow>"))

    template = template.replace('!JOBNAME',name)
    template = template.replace('!NODES',str(num_nodes))
    template = template.replace('!WALL',walltime)
    template = template.replace('!TASKSPERNODE',str(tasks_per_node))
    template = template.replace('!TASKS',str(nproc)) # must come below !TASKSPERNODE
    template = template.replace('!THREADS',str(threads))
    template = template.replace('!HYPERTHREADS',str(threads_per_core*threads))

    def _parse_none(string, pre):
        if string.lower().strip()=='none': return ''
        else: return f'\n#SBATCH --{pre}={string}'
        
    template = template.replace('!CMD',cmd)
    template = template.replace('!ACCOUNT',_parse_none(account,'account'))
    template = template.replace('!CONSTRAINT',_parse_none(constraint,'constraint'))
    template = template.replace('!QOS',_parse_none(qos,'qos'))
    template = template.replace('!PARTITION',_parse_none(partition,'partition'))
    template = template.replace('!OUT',out_file_root)

    if dry_run:
        fprint(HTML(f'<skyblue><b>{name}</b></skyblue>'))
        fprint(HTML(f'<skyblue><b>{"".join(["="]*len(name))}</b></skyblue>'))
        fprint(HTML(f'<skyblue>{template}</skyblue>'))
    
    # Get current time in Unix milliseconds to define log directory
    init_time_ms = int(time.time()*1e3)
    fname = f'{sbatch_file_root}_{init_time_ms}.sh'
    if not(dry_run):
        with open(fname,'w') as f:
            f.write(template)
    cmds = []
    cmds.append('sbatch')
    cmds.append(f'--parsable')
    if depstr is not None: cmds.append(f'{depstr}')
    cmds.append(fname)
    jobid = run_local(cmds,dry_run).strip()
    print(f"Submitted and obtained jobid {jobid}")
    return jobid
        

def get_sbatch_script_file_root(output_dir,project,stage,site):
    return os.path.join(f'{output_dir}',f'slurm_submission_{project}_{stage}_{site}')

# In actsims also currently, but this should be its final home
def pretty_info(info):
    name = info['package'] if info['package'] is not None else info['path']
    pstr = f'\n{name}'
    pstr = pstr + '\n'+''.join(["=" for x in range(len(name))])
    for key in info.keys():
        if key=='package': continue
        pstr = pstr + '\n' + f'\t{key:<10}{str(info[key]):<40}'
    return pstr

# In actsims also currently, but this should be its final home
def get_info(package=None,path=None,validate=True):
    import git
    import importlib
    info = {}
    if package is None:
        if path is None:
            raise_exception("One of package or path must be specified.")
        path = os.path.dirname(path)
        version = None
    else:
        mod = importlib.import_module(package)
        try:
            version = mod.__version__
        except AttributeError:
            version = None
        path = mod.__file__
        path = os.path.dirname(path)
    info['package'] = package
    info['path'] = path
    info['version'] = version
    try:
        repo = git.Repo(path,search_parent_directories=True)
        is_git = True
    except git.exc.InvalidGitRepositoryError:
        is_git = False
    info['is_git'] = is_git
    if is_git:
        chash = str(repo.head.commit)
        untracked = len(repo.untracked_files)>0
        changes = len(repo.index.diff(None))>0
        branch = str(repo.active_branch)
        info['hash'] = chash
        info['untracked'] = untracked
        info['changes'] = changes
        info['branch'] = branch
    else:
        if validate:
            if version is None:
                raise_exception(f"The provided package or path at {info['path']} neither has"
                                " any git information nor version information.")
            if not('site-packages' in path):
                raise_exception(f"The provided package or path at {info['path']} neither has"
                                " any git information nor does it seem to be in a site-packages directory.")
    return info





'''
Modified from rcludwick's Github Gist: https://gist.github.com/rcludwick/3663979

These functions take a dictionary of dependencies in the following way:

depdict = { 'a' : [ 'b', 'c', 'd'],
            'b' : [ 'c', 'd'],
            'e' : [ 'f', 'g']
            }

has_loop() will check for dep loops in the dep dict with true or false.

flatten() will create an ordered list of items according to the dependency structure.

Note:  To generate a list of dependencies in increasing order of dependencies, say for a build, run: flatten(MyDepDict)
'''

def _order(idepdict, val=None, level=0):
    '''Generates a relative order in a dep dictionary'''
    results = {}
    if val is None:
        for k,v in idepdict.items():
            for dep in v:
                results.setdefault(k,0)
                d = _order(idepdict, val=dep, level=level+1)
                for dk, dv in d.items():
                    if dv > results.get(dk,0):
                        results[dk] = dv
        return results
    else:
        results[val] = level
        deps = idepdict.get(val, None)
        if deps is None or deps == []:
            return { val: level }
        else:
            for dep in deps:
                d = _order(idepdict, val=dep, level=level+1)
                for dk, dv in d.items():
                    if dv > results.get(dk,0):
                        results[dk] = dv
            return results

def _invert(d):
    '''Inverts a dictionary'''
    i = {}
    for k,v in d.items():
        try:
            iterator = iter(v)
        except TypeError:
            depl = i.get(v, [])
            depl.append(k)
            i[v] = depl
        else:
            for dep in v:
                depl = i.get(dep, [])
                depl.append(k)
                i[dep] = depl
    return i

def flatten(depdict):
    '''flatten() generates a list of deps in order'''
    #Generate an inverted deplist
    ideps = _invert(depdict)

    #generate relative order
    order = _order(ideps)

    #Invert the order
    iorder = _invert(order)

    #Sort the keys and append to a list
    output = [] 
    for key in sorted(list(iorder.keys())):
        output.extend(iorder[key])
    return output


def has_loop(depdict, seen=None, val=None):
    '''Check to see if a given depdict has a dependency loop'''
    if seen is None:
        for k, v in depdict.items(): 
            seen = []
            for val in v: 
                if has_loop(depdict, seen=list(seen), val=val):
                    return True
            
    else:
        if val in seen:
            return True
        else:
            seen.append(val)
            k = val
            v = depdict.get(k,[])
            for val in v:
                if has_loop(depdict, seen=list(seen), val=val):
                    return True
    
    return False            
            

def raise_exception(message):
    fprint(HTML(f"<red>{message}</red>"))
    raise Exception
    

"""
Caching

We take a conservative approach to caching and reusing.
In order for a stage to be reused, four conditions have to be met:
1. There must be a SLURM output file (or local equivalent) that
clearly indicates that the most recent job was completed successfully
2. There must be a saved configuration file in the directory
that perfectly matches the submitted config for that stage
3. Git hashes and package versions should match (this can be overriden)
4. it must not depend on a stage that is not going to be reused

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
    
def main():
    if '--show-site-path' in sys.argv:
        print(get_site_path())
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
    parser.add_argument("-q", "--qos",     type=str,  default=None,help="QOS name")
    parser.add_argument("-p", "--partition",     type=str,  default=None,help="Partition name")
    parser.add_argument("-c", "--constraint",     type=str,  default=None,help="Constraint name")
    args = parser.parse_args()
    if args.force_local and args.force_slurm: raise_exception("You can\'t force both local and SLURM.")

    # Load config file
    with open(args.config_yaml, 'r') as stream:
        config = yaml.safe_load(stream)

    # Root directory
    root_dir = config['root_dir']
    
    # Check if we have SLURM
    have_slurm = check_slurm()
    if not(have_slurm):
        print("No SLURM detected. We will be locally "
              "executing commands serially.")
    if args.dry_run:
        print("We are doing a dry run, so we will just print to "
              "screen.")

    # Do git checks
    pkg_gitdict = gitcheck(config,'gitcheck_pkgs',package=True)
    pth_gitdict = gitcheck(config,'gitcheck_paths',package=False)

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
                        raise_exception(f"Internal loop stage name "
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
                raise_exception(f"Stage {d} required by {sname} not found in configuration file.")
            if d in unroll_map:
                my_deps = my_deps + unroll_map[d]
            else:
                my_deps.append(d)
        depended = depended + my_deps
        deps[sname] = my_deps

    if has_loop(deps): raise_exception("Circular dependency detected.")
    stages = flatten(deps) # Ordered by dependency
    # The above only contains stages that depend on something or something also depends on
    # Let's just append any others and warn about them
    for ostage in stage_names:
        if ostage not in stages:
            fprint(HTML(f"<ansiyellow>WARNING: stage {ostage} does not depend on anything, and nothing depends on it. Adding to queue anyway...</ansiyellow>"))
            stages.append(ostage)
    if set(stages)!=set(stage_names): raise_exception("Internal error in arranging stages. Please report this bug.")

    # Check sanity of skipped stages list
    if args.skip is None: args.skip = []
    for skipstage in args.skip:
        if not(skipstage in stages): raise_exception("Asked to skip a stage that is not in the list of stages.")
    
    # Parse arguments and prepare SLURM scripts

    if have_slurm or args.force_slurm:
        site = detect_site() if args.site is None else args.site
        sbatch_config = load_template(site)
    else:
        site = 'local'

    ###########################
    reuse_stages = []

    if not(args.no_reuse):
        # We decide which ones to resume here
        last_time = 0
        last_time_local = 0
        last_job = None
        last_job_local = None
        for stage in stages:
            print(f"Checking {stage}...")
            # We check if the last submitted job (if it exists) was completed
            # TODO: add check for local runs, not just sbatch
            root = get_out_file_root(root_dir,stage,args.project,site) + "_"
            suffix = ".txt"
            fs = glob.glob(root + "*" + suffix)
            if len(fs)==0:
                completed = False
                print("No output file found")
            else:
                last_job = max([sint(re.search(rf'{root}(.*?){suffix}', f).group(1)) for f in fs])
                output = run_local(['sacct', '-j',
                                           str(last_job), '--format=State',
                                           '--parsable2'],
                                          verbose=False).split('\n')
                completed = True
                for i,line in enumerate(output):
                    if i==0:
                        if line.strip()!='State': raise_exception("Unexpected output from sacct.")
                    elif i==(len(output)-1):
                        if line.strip()!='': raise_exception("Unexpected output from sacct.")
                    else:
                        if line.strip()!='COMPLETED':
                            completed = False
                            print("COMPLETED string not found")
                            break
                            
            if completed:
                # Get time, to compare with possible completed local run
                with open(get_stage_config_filename(root_dir,stage,args.project,last_job), 'r') as stream:
                    last_time = yaml.safe_load(stream)['stage']['time']


            # Also check for local run completed outputs
            root = get_local_out_file(root_dir,stage,args.project) + "_"
            suffix = ".txt"
            fs = glob.glob(root + "*" + suffix)
            completed_local = False
            if len(fs)!=0:
                last_job_local = max([sint(re.search(rf'{root}(.*?){suffix}', f).group(1)) for f in fs])
                with open(get_local_out_file(root_dir,stage,args.project)+f"_{last_job_local}.txt",'r') as f:
                    cstatus = f.read().strip()
                if cstatus=='COMPLETED':
                    completed_local = True
                    with open(get_stage_config_filename(root_dir,stage,args.project,last_job_local), 'r') as stream:
                        last_time_local = yaml.safe_load(stream)['stage']['time']
            
            if completed or completed_local:
                last_job = [last_job,last_job_local][argmax([last_time,last_time_local])]
                if last_job is None: raise_exception("Error in last completed job detection. Report bug.")
            else:
                continue

            # Next check if dictionaries match
            try:
                with open(get_stage_config_filename(root_dir,stage,args.project,last_job), 'r') as stream:
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
                if saved_config['stage']['pkg_gitdict']!=pkg_gitdict: 
                    print(saved_config['stage']['pkg_gitdict'])
                    print(pkg_gitdict)
                    print("Package git changed; not reusing")
                    continue
                if saved_config['stage']['pth_gitdict']!=pth_gitdict: 
                    print("Path git changed; not reusing")
                    continue

            # We made it this far, which means this stage can be reused
            reuse_stages.append(stage)

    ###########################

    is_sbatch = (have_slurm or args.force_slurm) and not(args.force_local)
    is_local = not(have_slurm) or args.force_local
    if sum([int(x) for x in [is_sbatch,is_local]])!=1: raise_exception("Inconsistency in submission vs. local. Report bug.")
    
    # Check if any reused stages have dependencies that are not reused
    # If so we will not reuse those stages
    # Algorithm is linear since `stages` is already sorted
    for stage in stages:
        if stage in reuse_stages:
            if not(stage in deps): continue
            redo = False
            for d in deps[stage]:
                if not(d in reuse_stages) and not(d in args.skip): redo = True
            if redo: reuse_stages.remove(stage)
            
    # A summary and a prompt
    print(f"SUMMARY FOR SUBMISSION OF PROJECT {args.project}")
    for stage in stages:
        if stage in reuse_stages:
            sumtxt='<red><b>[REUSE]</b></red>'
        elif stage in args.skip: sumtxt='<red><b>[SKIP]</b></red>'
        else: sumtxt='<green>[SUBMIT]</green>'
        fprint(HTML(stage+'\t\t'+sumtxt))

    reply = query_yes_no("Proceed with this?")
    if not(reply):
        sys.exit(0)

        
    # Make project directory
    proj_dir = get_project_dir(root_dir,args.project)
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
        execution,script,pargs = get_command(global_vals, copy.deepcopy(ostages), stage)

        # Make output directory
        output_dir =  get_output_dir(root_dir,stage,args.project)
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
            jobid = submit_slurm(stage,sbatch_config,
                                 copy.deepcopy(ostages[stage]).get('parallel',None),
                                 execution,script,pargs,
                                 dry_run=args.dry_run,
                                 output_dir=output_dir,
                                 project=args.project,
                                 site=site,root_dir=root_dir,depstr=depstr,
                                 account=args.account,
                                 qos=args.qos,
                                 partition=args.partition,
                                 constraint=args.constraint)
        if is_local:
            if pargs=='':
                cmds = [execution,script, '--output-dir',output_dir]
            else:
                cmds = [execution,script, pargs, '--output-dir',output_dir]
            run_local(cmds,dry_run=args.dry_run)
            
            # Get current time in Unix milliseconds and use that as jobid
            jobid = str(int(time.time()*1e3))
            # Save job completion confirmation
            with open(get_local_out_file(root_dir,stage,args.project)+f"_{jobid}.txt",'w') as f:
                f.write('COMPLETED')

        if not(args.dry_run):
            out_dict = {}
            out_dict['stage'] = {stage: copy.deepcopy(ostages[stage])}
            out_dict['stage']['pkg_gitdict'] = pkg_gitdict
            out_dict['stage']['pth_gitdict'] = pth_gitdict
            init_time_ms = int(time.time()*1e3) # Save time when it was saved
            out_dict['stage']['time'] = init_time_ms
            with open(get_stage_config_filename(root_dir,stage,args.project,jobid), 'w') as f:
                yaml.dump(out_dict, f, default_flow_style=False)

        jobids[stage] = jobid
    

if __name__ == '__main__':
    main()


    
