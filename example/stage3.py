import argparse

parser = argparse.ArgumentParser(description = 'stage3.')
parser.add_argument('estimator', help='Name of estimator.')
parser.add_argument("--output-dir", type=str,  default=None,help='Output directory.')
parser.add_argument("--nsims", type=int,  default=1,help='Number of simulations.')
parser.add_argument("--lmin", type=int,  default=100,help='Minimum multipole.')
parser.add_argument("--lmax", type=int,  default=3000,help='Maximum multipole.')
args = parser.parse_args()
