print("Starting")
import time
import argparse

parser = argparse.ArgumentParser(description = 'stage1.')
# parser.add_argument('project', help='Name of project.')
parser.add_argument("--output-dir", type=str,  default=None,help='Output directory.')
args = parser.parse_args()

time.sleep(1)
