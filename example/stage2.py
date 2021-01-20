import time
import numpy as np
import argparse

parser = argparse.ArgumentParser(description = 'stage2.')
parser.add_argument("--output-dir", type=str,  default=None,help='Output direactory.')
parser.add_argument("--nsims", type=int,  default=1,help='Number of simulations.')
parser.add_argument("--flag1", action='store_true',help='A flag.')
parser.add_argument("--arg1", type=int,  default=100,help='An optional arg.')
parser.add_argument("--arg2", type=int,  default=3000,help='An optional arg.')
parser.add_argument("--lmin", type=int,  default=100,help='Minimum multipole.')
parser.add_argument("--lmax", type=int,  default=3000,help='Maximum multipole.')
args = parser.parse_args()

time.sleep(2)

np.savetxt(f'{args.output_dir}/stage2_result.txt',np.random.random((100,100)))
