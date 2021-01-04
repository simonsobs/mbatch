import os,sys,shutil,subprocess,warnings
import argunparse,yaml,math,time
from prompt_toolkit import print_formatted_text as pprint, HTML
import random

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
    for pkg in gitchecks:
        #TODO: do something more with ginfo
        ginfo = get_info(package=pkg if package else None,
                                path=pkg if not(package) else None,
                                validate=True)
        print(pretty_info(ginfo))

def get_command(global_vals, stage_configs, stage):
    stage_config = stage_configs[stage]
    execution = stage_config['exec']
    if not(execution in ['python','python3']):
        raise Exception("Only Python execution "
                        "is currently supported. "
                        "Shell support will be "
                        "added soon.")
    script_name = stage_config['script']
    global_opts = stage_config.get('globals',[])
    args = stage_config.get('args',[])
    options = stage_config.get('options',{})
    optkeys = list(options.keys())
    for global_opt in global_opts:
        if global_opt in optkeys: raise Exception(f"{global_opt} in {stage} config is already a global.")
        options[global_opt] = global_vals[global_opt]
    unparser = argunparse.ArgumentUnparser()
    unparsed = unparser.unparse(*args, **options)
    #TODO: check for malicious content in unparsed string since it comes
    #from an external library
    return execution,script_name,unparsed

def run_local(cmds,dry_run):
    print(f"Running {cmds} locally...")
    if dry_run:
        print(' '.join(cmds))
        return str(random.randint(1,32768))
    else:
        sp = subprocess.run(cmds,stderr=sys.stderr, stdout=subprocess.PIPE)
        output = sp.stdout.decode("utf-8")
        print(output)
        if sp.returncode!=0: raise Exception
        return output

def detect_site():
    sites = []
    env_check = os.environ.get('CLUSTER',None)
    if env_check=='niagara':
        sites.append( 'niagara' )
        
    env_check = os.environ.get('NERSC_HOST',None)
    if env_check=='cori':
        sites.append( 'cori' )
        
    if len(sites)==0:
        warnings.warn('No site specified through --site and did not automatically detect any sites. Using generic SLURM template.')
        sites.append( 'generic' )
    elif len(sites)==1:
        pprint(HTML(f'<ansiyellow>No site specified through --site; detected <b>{sites[0]}</b> automatically.</ansiyellow>'))
    else:
        raise Exception(f"More than one site detected through environment variables: {sites}. Please specificy explicitly through the --site argument.")
    return sites[0]

def load_template(site):
    this_dir, this_filename = os.path.split(__file__)
    template_path = os.path.join(this_dir, "data", "sites", f"{site}.yml")
    with open(template_path, 'r') as stream:
        sbatch_config = yaml.safe_load(stream)
    return sbatch_config
    
def submit_slurm(stage,sbatch_config,parallel_config,execution,
                 script,pargs,dry_run,output_dir,site,project,
                 depstr=None):
    cpn = sbatch_config['cores_per_node']
    template = sbatch_config['template']
    try:
        nproc = parallel_config['nproc']
    except (TypeError,KeyError) as e:
        nproc = 1
        pprint(HTML(f"<ansiyellow>No stage['parallel']['nproc'] found for {stage}. Assuming number of MPI processes nproc=1.</ansiyellow>"))
    try:
        threads = parallel_config['threads']
    except (TypeError,KeyError) as e:
        threads = cpn
        pprint(HTML(f"<ansiyellow>No stage['parallel']['threads'] found for {stage}. Assuming number of OpenMP threads={cpn}.</ansiyellow>"))
    try:
        walltime = parallel_config['walltime']
    except (TypeError,KeyError) as e:
        walltime = "00:15:00"
        pprint(HTML(f"<ansiyellow>No stage['parallel']['walltime'] found for <b>{stage}</b>. Assuming <b>walltime of {walltime}</b>.</ansiyellow>"))

    num_cores = nproc * threads
    num_nodes = int(math.ceil(num_cores/cpn))
    totcores = num_nodes * cpn
    tasks_per_node = int(nproc*1./num_nodes)
    percent_used = num_cores*100./float(totcores)

    if percent_used<90.: 
        pprint(HTML(f"<ansiyellow>warnings.warn(f'Stage {stage}: with {nproc} MPI process(es) and {threads} thread(s), we require {fnodes} nodes. Given that we round up to {nodes} in the request, this means a node will have <90% of its cores utilized. Reconsider the way you choose your threads..</ansiyellow>"))

    template = template.replace('!JOBNAME',f'{stage}_{project}')
    template = template.replace('!NODES',str(num_nodes))
    template = template.replace('!WALL',walltime)
    template = template.replace('!TASKSPERNODE',str(tasks_per_node))
    template = template.replace('!TASKS',str(nproc)) # must come below !TASKSPERNODE
    template = template.replace('!THREADS',str(threads))
    cmd = ' '.join([execution,script,pargs])
    template = template.replace('!CMD',cmd)
    template = template.replace('!OUT',os.path.join(output_dir,f'slurm_out_{stage}'))

    if dry_run:
        pprint(HTML(f'<skyblue><b>{stage}</b></skyblue>'))
        pprint(HTML(f'<skyblue><b>{"".join(["="]*len(stage))}</b></skyblue>'))
        pprint(HTML(f'<skyblue>{template}</skyblue>'))
    
    # Get current time in Unix milliseconds to define log directory
    init_time_ms = int(time.time()*1e3)
    fname = os.path.join(f'{output_dir}',f'slurm_submission_{project}_{stage}_{site}_{init_time_ms}.sh')
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
            raise Exception("One of package or path must be specified.")
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
                raise Exception(f"The provided package or path at {info['path']} neither has"
                                " any git information nor version information.")
            if not('site-packages' in path):
                raise Exception(f"The provided package or path at {info['path']} neither has"
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
            

