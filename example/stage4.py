import argparse
import numpy as np

parser = argparse.ArgumentParser(description = 'stage4.')
parser.add_argument("--output-dir", type=str,  default=None,help='Output directory.')
args = parser.parse_args()


a = np.loadtxt(f'{args.output_dir}/../stage3/stage3_result_TTTT.txt')

np.savetxt(f'{args.output_dir}/stage4_result.txt',np.random.random((100,100)))
