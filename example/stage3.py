import argparse
import numpy as np

parser = argparse.ArgumentParser(description = 'stage3.')
parser.add_argument('estimator', help='Name of estimator.')
parser.add_argument("--output-dir", type=str,  default=None,help='Output direactory.')
parser.add_argument("--nsims", type=int,  default=1,help='Number of simulations.')
parser.add_argument("--lmin", type=int,  default=100,help='Minimum multipole.')
parser.add_argument("--lmax", type=int,  default=3000,help='Maximum multipole.')
args = parser.parse_args()


a = np.loadtxt(f'{args.output_dir}/../stage1/stage1_result.txt')
b = np.loadtxt(f'{args.output_dir}/../stage2/stage2_result.txt')

np.savetxt(f'{args.output_dir}/stage3_result_{args.estimator}.txt',np.random.random((100,100)))
