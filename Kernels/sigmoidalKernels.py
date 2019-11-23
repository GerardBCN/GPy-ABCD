import numpy as np
from GPy.kern.src.basis_funcs import BasisFuncKernel
from GPy.core.parameterization import Param
from paramz.transformations import Logexp
from paramz.caching import Cache_this
from abc import abstractmethod



class SigmoidalKernelBase(BasisFuncKernel):
    """
    Abstract superclass for sigmoidal kernels
    """

    def __init__(self, input_dim: int, reverse: bool = False, variance: float = 1., location: float = 0., slope: float = 1.,
                 active_dims: int = None, name: str = 'sigmoidal_kernel_base') -> None:
        self.reverse = reverse
        super(SigmoidalKernelBase, self).__init__(input_dim, variance, active_dims, False, name)
        # TO REMOVE VARIANCE: comment line above; uncomment below; remove self.variance factors from subclass methods
        # super(BasisFuncKernel, self).__init__(input_dim, active_dims, name)
        # assert self.input_dim == 1, "Basis Function Kernel only implemented for one dimension. Use one kernel per dimension (and add them together) for more dimensions"
        # self.ARD = False
        # self.variance = 1
        self.location = Param('location', location)
        self.slope = Param('slope', slope, Logexp()) # This +ve constraint makes non-reverse sigmoids only fit (+ve or -ve) curves going away from 0; similarly for other kernels
        self.link_parameters(self.location, self.slope)

    # NOTE: is_reversed() is NOT always reliable since these are only covariances after all and therefore flipped-direction fits can just happen
    #   HOWEVER: when it works this is "reversed" w.r.t. whichever value self.reverse has
    @abstractmethod
    def is_reversed(self):
        pass

    @staticmethod
    def _sech(x): # Because the np.cosh overflows too easily before inversion
        return 2 / (np.exp(x) + np.exp(-x))
    @staticmethod
    def _csch(x):
        return 2 / (np.exp(x) - np.exp(-x))
    @staticmethod
    def _sigmoid_function(x, l, s):
        return (1 + np.tanh( (x - l) / s )) / 2
    @staticmethod
    def _sigmoid_function_dl(x, l, s):
        minus_arg = (l - x) / s
        return - SigmoidalKernelBase._sech(minus_arg) ** 2 / (2 * s)
    @staticmethod
    def _sigmoid_function_ds(x, l, s):
        minus_arg = (l - x) / s
        return minus_arg * SigmoidalKernelBase._sech(minus_arg) ** 2 / (2 * s)
    @staticmethod
    def _sigmoid_function_opposites_sum_height(l, sl, s): # Height of sig(x, l, s) + sig(x, sl, -s) - 1
        return np.tanh((sl - l) / (2*s)) # Simplification of: 2 * SigmoidalKernelBase._sigmoid_function((sl - l) / 2, 0, s) - 1

    def update_gradients_diag(self, dL_dKdiag, X):
        raise NotImplementedError



# Based on LogisticBasisFuncKernel
class SigmoidalKernel(SigmoidalKernelBase):
    """
    Sigmoidal kernel
    (ascending by default; descending by reverse=True)
    """

    def __init__(self, input_dim: int, reverse: bool = False, variance: float = 1., location: float = 0., slope: float = 1.,
                 active_dims: int = None, name: str = 'sigmoidal') -> None:
        super(SigmoidalKernel, self).__init__(input_dim, reverse, variance, location, slope, active_dims, name)

    def is_reversed(self):
        return (self.slope < 0) ^ self.reverse

    @Cache_this(limit=3, ignore_args=())
    def _phi(self, X):
        asc = self._sigmoid_function(X, self.location, self.slope)
        return 1 - asc if self.reverse else asc

    def update_gradients_full(self, dL_dK, X, X2=None):
        super(SigmoidalKernel, self).update_gradients_full(dL_dK, X, X2)
        if X2 is None or X is X2:
            phi1 = self.phi(X)
            if phi1.ndim != 2:
                phi1 = phi1[:, None]

            dphi1_dl = self._sigmoid_function_dl(X, self.location, self.slope)
            self.location.gradient = np.sum(self.variance * 2 * (dL_dK * phi1.dot(dphi1_dl.T)).sum())

            dphi1_ds = self._sigmoid_function_ds(X, self.location, self.slope)
            self.slope.gradient = np.sum(self.variance * 2 * (dL_dK * phi1.dot(dphi1_ds.T)).sum())
        else:
            phi1 = self.phi(X)
            phi2 = self.phi(X2)
            if phi1.ndim != 2:
                phi1 = phi1[:, None]
                phi2 = phi2[:, None]

            dphi1_dl = self._sigmoid_function_dl(X, self.location, self.slope)
            dphi2_dl = self._sigmoid_function_dl(X2, self.location, self.slope)
            self.location.gradient = np.sum(self.variance * (dL_dK * (phi1.dot(dphi2_dl.T) + phi2.dot(dphi1_dl.T))).sum())

            dphi1_ds = self._sigmoid_function_ds(X, self.location, self.slope)
            dphi2_ds = self._sigmoid_function_ds(X2, self.location, self.slope)
            self.slope.gradient = np.sum(self.variance * (dL_dK * (phi1.dot(dphi2_ds.T) + phi2.dot(dphi1_ds.T))).sum())

        self.location.gradient = np.where(np.isnan(self.location.gradient), 0, self.location.gradient)
        self.slope.gradient = np.where(np.isnan(self.slope.gradient), 0, self.slope.gradient)

        if self.reverse: # Works this simply (a single sign flip per product above)
            self.location.gradient = - self.location.gradient
            self.slope.gradient = - self.slope.gradient


class SigmoidalIndicatorKernelOneLocation(SigmoidalKernelBase):
    """
    Sigmoidal indicator function kernel
    (hat by default; positive-well by reverse=True)
    """

    def __init__(self, input_dim: int, reverse: bool = False, variance: float = 1., location: float = 0., slope: float = 1.,
                 active_dims: int = None, name: str = 'sigmoidal_indicator') -> None:
        super(SigmoidalIndicatorKernelOneLocation, self).__init__(input_dim, reverse, variance, location, slope, active_dims, name)

    def is_reversed(self):
        return (self.slope < 0) ^ self.reverse

    @Cache_this(limit=3, ignore_args=())
    def _phi(self, X):
        asc = self._sigmoid_function(X, self.location, self.slope)
        hat = 4 * asc * (1 - asc) # Increasing the peak from 0.25 to 1
        return 1 - hat if self.reverse else hat

    def update_gradients_full(self, dL_dK, X, X2=None):
        super(SigmoidalIndicatorKernelOneLocation, self).update_gradients_full(dL_dK, X, X2)
        if X2 is None or X is X2:
            phi1 = self.phi(X)
            if phi1.ndim != 2:
                phi1 = phi1[:, None]

            asc1 = self._sigmoid_function(X, self.location, self.slope)

            dphi1_dl = 4 * (1 - 2 * asc1) * self._sigmoid_function_dl(X, self.location, self.slope)
            self.location.gradient = np.sum(self.variance * 2 * (dL_dK * phi1.dot(dphi1_dl.T)).sum())

            dphi1_ds = 4 * (1 - 2 * asc1) * self._sigmoid_function_ds(X, self.location, self.slope)
            self.slope.gradient = np.sum(self.variance * 2 * (dL_dK * phi1.dot(dphi1_ds.T)).sum())
        else:
            phi1 = self.phi(X)
            phi2 = self.phi(X2)
            if phi1.ndim != 2:
                phi1 = phi1[:, None]
                phi2 = phi2[:, None]

            asc1 = self._sigmoid_function(X, self.location, self.slope)
            asc2 = self._sigmoid_function(X2, self.location, self.slope)

            dphi1_dl = 4 * (1 - 2 * asc1) * self._sigmoid_function_dl(X, self.location, self.slope)
            dphi2_dl = 4 * (1 - 2 * asc2) * self._sigmoid_function_dl(X2, self.location, self.slope)
            self.location.gradient = np.sum(self.variance * (dL_dK * (phi1.dot(dphi2_dl.T) + phi2.dot(dphi1_dl.T))).sum())

            dphi1_ds = 4 * (1 - 2 * asc1) * self._sigmoid_function_ds(X, self.location, self.slope)
            dphi2_ds = 4 * (1 - 2 * asc2) * self._sigmoid_function_ds(X2, self.location, self.slope)
            self.slope.gradient = np.sum(self.variance * (dL_dK * (phi1.dot(dphi2_ds.T) + phi2.dot(dphi1_ds.T))).sum())

        self.location.gradient = np.where(np.isnan(self.location.gradient), 0, self.location.gradient)
        self.slope.gradient = np.where(np.isnan(self.slope.gradient), 0, self.slope.gradient)

        if self.reverse: # Works this simply (a single sign flip per product above)
            self.location.gradient = - self.location.gradient
            self.slope.gradient = - self.slope.gradient


class SigmoidalIndicatorKernel(SigmoidalKernelBase):
    """
    Sigmoidal indicator function kernel with a start and a stop location:
    ascendingSigmoid(location) + (1 - ascendingSigmoid(stop_location)) - 1, i.e. ascendingSigmoid(location) - ascendingSigmoid(stop_location)
    (hat if location <= stop_location, and positive-well otherwise; can flip from one to the other by reverse=True)
    """

    def __init__(self, input_dim: int, reverse: bool = False, variance: float = 1., location: float = 0., stop_location: float = 1., slope: float = 1.,
                 active_dims: int = None, name: str = 'sigmoidal_indicator') -> None:
        super(SigmoidalIndicatorKernel, self).__init__(input_dim, reverse, variance, location, slope, active_dims, name)
        self.stop_location = Param('stop_location', stop_location)
        self.link_parameters(self.stop_location)

    def is_reversed(self):
        return ((self.location > self.stop_location) ^ (self.slope < 0)) ^ self.reverse

    @Cache_this(limit=3, ignore_args=())
    def _phi(self, X):
        asc = self._sigmoid_function(X, self.location, self.slope)
        desc = self._sigmoid_function(X, self.stop_location, -self.slope)
        height = SigmoidalKernelBase._sigmoid_function_opposites_sum_height(self.location, self.stop_location, self.slope)
        hat = (asc + desc - 1) / height #if self.location > self.stop_location else asc - asc2 + 1 # Note: it does not affect the gradients
        return 1 - hat if self.reverse else hat

    def update_gradients_full(self, dL_dK, X, X2=None):
        super(SigmoidalIndicatorKernel, self).update_gradients_full(dL_dK, X, X2)
        if X2 is None: X2 = X

        phi1 = self.phi(X)
        phi2 = self.phi(X2) if X2 is not X else phi1
        if phi1.ndim != 2:
            phi1 = phi1[:, None]
            phi2 = phi2[:, None] if X2 is not X else phi1

        asc = self._sigmoid_function(X, self.location, self.slope)
        desc = self._sigmoid_function(X, self.stop_location, -self.slope)
        inv_height = 1 / SigmoidalKernelBase._sigmoid_function_opposites_sum_height(self.location, self.stop_location, self.slope)
        numerator = asc + desc - 1

        height_arg = (self.location - self.stop_location) / (2 * self.slope)
        dinvheight_dl = (SigmoidalKernelBase._csch(height_arg) ** 2) / (2 * self.slope)
        dinvheight_dsl = - dinvheight_dl
        dinvheight_ds = height_arg * dinvheight_dsl

        # Only asc * inv_height contains l
        dphi1_dl = self._sigmoid_function_dl(X, self.location, self.slope) * inv_height + asc * dinvheight_dl
        dphi2_dl = self._sigmoid_function_dl(X2, self.location, self.slope) * inv_height + asc * dinvheight_dl
        self.location.gradient = np.sum(self.variance * (dL_dK * (phi1.dot(dphi2_dl.T) + phi2.dot(dphi1_dl.T))).sum())

        # Only desc * inv_height contains sl
        dphi1_dsl = self._sigmoid_function_dl(X, self.stop_location, -self.slope) * inv_height + desc * dinvheight_dsl
        dphi2_dsl = self._sigmoid_function_dl(X2, self.stop_location, -self.slope) * inv_height + desc * dinvheight_dsl
        self.stop_location.gradient = np.sum(self.variance * (dL_dK * (phi1.dot(dphi2_dsl.T) + phi2.dot(dphi1_dsl.T))).sum())

        dphi1_ds = (self._sigmoid_function_ds(X, self.location, self.slope) - self._sigmoid_function_ds(X, self.stop_location, -self.slope)) * inv_height + numerator * dinvheight_ds
        dphi2_ds = (self._sigmoid_function_ds(X2, self.location, self.slope) - self._sigmoid_function_ds(X2, self.stop_location, -self.slope)) * inv_height + numerator * dinvheight_ds
        self.slope.gradient = np.sum(self.variance * (dL_dK * (phi1.dot(dphi2_ds.T) + phi2.dot(dphi1_ds.T))).sum())

        self.location.gradient = np.where(np.isnan(self.location.gradient), 0, self.location.gradient)
        self.stop_location.gradient = np.where(np.isnan(self.stop_location.gradient), 0, self.stop_location.gradient)
        self.slope.gradient = np.where(np.isnan(self.slope.gradient), 0, self.slope.gradient)

        if self.reverse: # Works this simply (a single sign flip per product above)
            self.location.gradient = - self.location.gradient
            self.stop_location.gradient = - self.stop_location.gradient
            self.slope.gradient = - self.slope.gradient
