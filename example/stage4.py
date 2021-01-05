import argparse

parser = argparse.ArgumentParser(description = 'stage4.')
parser.add_argument("--output-dir", type=str,  default=None,help='Output directory.')
args = parser.parse_args()
