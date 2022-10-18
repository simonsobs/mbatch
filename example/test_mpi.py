from mpi4py import MPI
import numpy as np
import os,sys

# from pixell.utils
def allgather(a, comm):
    """Convenience wrapper for Allgather that returns the result
    rather than needing an output argument."""
    a   = np.asarray(a)
    res = np.zeros((comm.size,)+a.shape,dtype=a.dtype)
    if np.issubdtype(a.dtype, np.string_):
        comm.Allgather(a.view(dtype=np.uint8), res.view(dtype=np.uint8))
    else:
        comm.Allgather(a, res)
    return res


comm = MPI.COMM_WORLD
rank = comm.Get_rank()
ntasks = comm.Get_size()

if ntasks<=1: raise ValueError

my_value = np.asarray([rank,])

print(rank,ntasks)

all_values = allgather(my_value,comm)
sum = all_values.sum()
if not(sum==(ntasks*(ntasks-1)/2)): raise ValueError
print(all_values)
print("Success.")
