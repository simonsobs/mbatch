import os,sys,shutil,subprocess,warnings,glob
import argunparse,yaml,math,time
from prompt_toolkit import print_formatted_text as fprint, HTML
import random
from pathlib import Path
from pprint import pprint
import shlex

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
    arg = [arg]
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
    # First try ~/.slurmr/*.yml
    home = str(Path.home())
    homepath = os.path.join(home,".slurmr/*.yml")
    fs = glob.glob(homepath)
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

def get_project_dir(root_dir,project):
    return os.path.join(root_dir,project)

def get_output_dir(root_dir,stage,project):
    return os.path.abspath(os.path.join(get_project_dir(root_dir,project),stage))

def get_stage_config_filename(root_dir,stage,project):
    return os.path.join(get_output_dir(root_dir,stage,project),'stage_config.yml')
    
def submit_slurm(stage,sbatch_config,parallel_config,execution,
                 script,pargs,dry_run,output_dir,site,project,
                 depstr=None,account=None,qos=None):
    cpn = sbatch_config['cores_per_node']
    template = sbatch_config['template']
    try:
        nproc = parallel_config['nproc']
    except (TypeError,KeyError) as e:
        nproc = 1
        fprint(HTML(f"<ansiyellow>No stage['parallel']['nproc'] found for {stage}. Assuming number of MPI processes nproc=1.</ansiyellow>"))


    try:
        memory_gb = parallel_config['memory_gb']
        if 'threads' in list(parallel_config.keys()): raise_exception("Both memory_gb and threads should not be specified.")
        if not('memory_per_node_gb' in list(sbatch_config.keys())): raise_exception("Using memory_gb but no memory_per_node_gb in site configuration.")
        if not('min_threads' in list(parallel_config.keys())): raise_exception("Need min_threads if using memory_gb.")
        # Maximum number of processes per node
        threads = max(math.ceil(1.*cpn/sbatch_config['memory_per_node_gb']*parallel_config['memory_gb'] ),parallel_config['min_threads'])
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

    num_cores = nproc * threads
    num_nodes = int(math.ceil(num_cores/cpn))
    totcores = num_nodes * cpn
    tasks_per_node = int(nproc*1./num_nodes)
    percent_used = num_cores*100./float(totcores)

    if percent_used<90.: 
        fprint(HTML(f"<ansiyellow>Stage {stage}: with {nproc} MPI process(es) and {threads} thread(s) and {num_nodes} nodes in the request, this means a node will have less than 90% of its cores utilized. Reconsider the way you choose your thread count or number of processes.</ansiyellow>"))

    template = template.replace('!JOBNAME',f'{stage}_{project}')
    template = template.replace('!NODES',str(num_nodes))
    template = template.replace('!WALL',walltime)
    template = template.replace('!TASKSPERNODE',str(tasks_per_node))
    template = template.replace('!TASKS',str(nproc)) # must come below !TASKSPERNODE
    template = template.replace('!THREADS',str(threads))
    cmd = ' '.join([execution,script,pargs]) + f' --output-dir {output_dir}'

    template = template.replace('!CMD',cmd)
    template = template.replace('!OUT',get_out_file_root(output_dir,stage,project,site))

    if dry_run:
        fprint(HTML(f'<skyblue><b>{stage}</b></skyblue>'))
        fprint(HTML(f'<skyblue><b>{"".join(["="]*len(stage))}</b></skyblue>'))
        fprint(HTML(f'<skyblue>{template}</skyblue>'))
    
    # Get current time in Unix milliseconds to define log directory
    init_time_ms = int(time.time()*1e3)
    fname = os.path.join(f'{output_dir}',f'slurm_submission_{project}_{stage}_{site}_{init_time_ms}.sh')
    if not(dry_run):
        with open(fname,'w') as f:
            f.write(template)
    cmds = []
    cmds.append('sbatch')
    cmds.append(f'--parsable')
    if not(account is None): cmds.append(f'--account={account}')
    if not(qos is None): cmds.append(f'--qos={qos}')
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
    
