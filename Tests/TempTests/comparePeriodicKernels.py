from matplotlib import pyplot as plt
from Util.kernelUtil import sampleCurves, doGPR
from Kernels.baseKernels import C

from Kernels.periodicKernel import *

# np.seterr(all='raise') # Raise exceptions instead of RuntimeWarnings. The exceptions can then be caught by the debugger



# kPER = GPy.kern.Cosine(1) + kC
# kPER = GPy.kern.StdPeriodic(1) + kC
kPER = PureStdPeriodicKernel(1) + C



## Displays

kPER.plot()
print(kPER)
sampleCurves(kPER)

plt.show()


## Fitting

X = np.linspace(-10, 10, 101)[:, None]

Y = np.cos( (X - 5) / 2 )**2 * 7 + np.random.randn(101, 1) * 1 #- 100

doGPR(X, Y, kPER, 10)
