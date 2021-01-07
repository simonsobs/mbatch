import time
import argparse
import numpy as np

parser = argparse.ArgumentParser(description = 'stage1.')
parser.add_argument("--output-dir", type=str,  default=None,help='Output directory.')
args = parser.parse_args()

time.sleep(2)

np.savetxt(f'{args.output_dir}/stage1_result.txt',np.random.random((100,100)))
