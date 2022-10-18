import os,sys,time,stat
import math, random, string
import argparse
import mbatch

def main():

    parser = argparse.ArgumentParser(description='Submit hybrid OpenMP+MPI jobs')
    parser.add_argument("N", type=int,help='Number of MPI jobs')
    parser.add_argument("Command", type=str,help='Command')
    parser.add_argument("-d", "--dependencies",     type=str,  default=None,help="Comma separated list of dependency JOBIDs")
    parser.add_argument("-o", "--output-dir",     type=str,  default="./",help="Output directory")
    parser.add_argument("-t", "--threads",     type=int,  default=1,help="Number of threads")
    parser.add_argument("-s", "--site",     type=str,  default=None,help="Site name (optional; will auto-detect if not provided)")
    parser.add_argument("-n", "--name",     type=str,  default="job",help="Job name")
    parser.add_argument("-A", "--account",     type=str,  default=None,help="Account name")
    parser.add_argument("-q", "--qos",     type=str,  default=None,help="QOS name")
    parser.add_argument("-p", "--partition",     type=str,  default=None,help="Partition name")
    parser.add_argument("-c", "--constraint",     type=str,  default=None,help="Constraint name")
    parser.add_argument("-w", "--walltime",     type=str,  default="00:15:00",help="Walltime")
    parser.add_argument("--dry-run", action='store_true',help='Only show submissions.')


    args = parser.parse_args()
    output_dir = args.output_dir
    site = mbatch.detect_site() if args.site is None else args.site
    sbatch_config = mbatch.load_template(site)
    template = sbatch_config['template']
    constraint = mbatch.get_default(sbatch_config,'constraint',args.constraint)
    qos = mbatch.get_default(sbatch_config,'qos',args.qos)
    partition = mbatch.get_default(sbatch_config,'part',args.partition)
    account = mbatch.get_default(sbatch_config,'account',args.account)
    cpn = sbatch_config['architecture'][constraint][partition]['cores_per_node']
    out_file_root = os.path.join(args.output_dir,f'slurm_out_{args.name}_{site}')
    sbatch_file_root = os.path.join(f'{output_dir}',f'slurm_submission_{args.name}_{site}')
    if not(args.dependencies is None):
        jlist = args.dependencies.split(',')
        depstr = ':'.join(jlist)
        depstr = "--dependency=afterok:" + depstr
    else:
        depstr = None
    mbatch.submit_slurm_core(template,args.name,args.Command,args.N,cpn,args.threads,args.walltime,args.dry_run,
                      args.output_dir,site,out_file_root,sbatch_file_root,
                      depstr=depstr,account=account,qos=qos,partition=partition,constraint=constraint)
