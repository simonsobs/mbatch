import os,sys,shutil,subprocess,warnings
import argunparse

def check_slurm():
    try:
        ret = subprocess.run(["sbatch","-V"],capture_output=True)
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

def run_local(execution,script,args,dry_run):
    print(f"Running {[execution,script,args]} locally...")
    cmds = [execution,script,args]
    if dry_run:
        print(' '.join(cmds))
        return True
    else:
        sp = subprocess.run(cmds,capture_output=False,stderr=sys.stderr, stdout=sys.stdout)
        return sp.returncode==0

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
        warnings.warn(f'No site specified through --site; detected *{sites[0]}* automatically.')
    else:
        raise Exception(f"More than one site detected through environment variables: {sites}. Please specificy explicitly through the --site argument.")
    return sites[0]

def load_template(site):
    this_dir, this_filename = os.path.split(__file__)
    template_path = os.path.join(this_dir, "data", "sites", f"{site}.yml")
    with open(template_path,'r') as f:
        string = f.read()
    return string
    
def submit_slurm(site,execution,script,pargs,dry_run):
    if site is None: site = detect_site()
    slurm_string = load_template(site)


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
            
