#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@authors: Alex Mallen (atmallen@uw.edu)
Built on code from Henning Lange (helange@uw.edu)
"""

# TODO: add covariates to mainline DPK

import torch

from torch import nn
from torch import optim

import numpy as np

class KoopmanProb(nn.Module):
    r'''
    model_obj: an object that specifies the function f and how to optimize
               it. The object needs to implement numerous function. See
               below for some examples.
    sample_num: number of samples from temporally local loss used to
                reconstruct the global error surface.
    batch_size: Number of temporal snapshots processed by SGD at a time
                default = 32
                type: int
    parallel_batch_size: Number of temporaly local losses sampled in parallel.
                         This number should be as high as possible but low enough
                         to not cause memory issues.
                         default = 1000
                         type: int
    device: The device on which the computations are carried out.
            Example: cpu, cuda:0, or list of GPUs for multi-GPU usage, i.e. ['cuda:0', 'cuda:1']
            default = 'cpu'
    seed: The seed to set for pyTorch and numpy--WARNING: does not seem to make results reproducible
    loss_weights: torch.tensor of shape (xt.shape[0],) that represents how to weight the losses over time.
                  default=None
    '''

    def __init__(self, model_obj, sample_num=12, seed=None, **kwargs):

        super(KoopmanProb, self).__init__()
        self.total_freqs = model_obj.total_freqs
        self.num_freqs = model_obj.num_freqs

        if seed is not None:
            torch.set_deterministic(True)
            torch.manual_seed(seed)
            np.random.seed(seed)

        if 'device' in kwargs:
            self.device = kwargs['device']
            if type(kwargs['device']) == list:
                self.device = kwargs['device'][0]
                multi_gpu = True
            else:
                multi_gpu = False
        else:
            self.device = 'cpu'
            multi_gpu = False

        self.multi_gpu = multi_gpu

        self.parallel_batch_size = kwargs['parallel_batch_size'] if 'parallel_batch_size' in kwargs else 1000
        self.batch_size = kwargs['batch_size'] if 'batch_size' in kwargs else 32
        self.loss_weights = kwargs['loss_weights'] if 'loss_weights' in kwargs else None

        self.covariates_mean = 0
        self.covariates_std = 1
        # Initial guesses for frequencies
        self.omegas = torch.linspace(0.01, 0.5, self.total_freqs, device=self.device)

        model_obj = model_obj.to(self.device)
        self.model_obj = nn.DataParallel(model_obj, device_ids=kwargs['device']) if multi_gpu else model_obj
        self.sample_num = sample_num
        self.num_fixed_omegas = 0

    def find_fourier_omegas(self, xt, num_fourier_modes, tt=None):
        """
        computes the argmax of the fft of xt to find frequencies the data exhibits. The first
        num_fourier_modes values of self.omega will be fixed to these values throughout optimization
        (although they will still be tuned through SGD if lr_omega != 0 when you call fit)
        :param xt: the data to initialize fourier modes with. Data samples must be equally spaced
        :param num_fourier_modes: the number of fourier frequencies to find
        :return: omegas found
        """
        if tt is not None:
            raise ValueError("Fourier frequencies of non uniform samples is not yet implemented")

        self.num_fixed_omegas = max(self.num_fixed_omegas, num_fourier_modes)
        best_omegas = None
        if num_fourier_modes > 0:
            xt_ft = np.fft.fft(xt, axis=0)
            adj_xt_ft = (abs(xt_ft) + abs(np.flip(xt_ft))).reshape(xt_ft.size)
            freqs = np.tile(np.fft.fftfreq(len(xt_ft)), xt.shape[1])

            best_omegas = np.zeros(num_fourier_modes)
            i = 0
            num_found = 0
            while num_found < num_fourier_modes:
                amax = np.argpartition(-adj_xt_ft[:len(xt_ft) // 2], i)[i]  # ith biggest freq
                if freqs[amax] != 0 and all(abs(1 - best_omegas / freqs[amax]) > 0.1):
                    best_omegas[num_found] = freqs[amax]
                    num_found += 1
                i += 1

            best_omegas = 2 * np.pi * torch.tensor(best_omegas)

        if best_omegas is not None:
            idx = 0
            for num_freqs in self.num_freqs:
                self.omegas[idx:idx + num_fourier_modes] = best_omegas
                idx += num_freqs
        return best_omegas

    def init_periods(self, periods):
        """
        sets the first len(periods) frequencies for each parameter equal to 2 pi / periods,
        which will remain constant through optimization (although they will still be tuned through SGD
        if lr_omega != 0 when you call fit)
        :param periods: the periods you think the data exhibits
        """
        if len(periods) > min(self.num_freqs):
            raise ValueError("Too many periods provided. Must be at most min(self.num_freqs).")

        self.num_fixed_omegas = max(self.num_fixed_omegas, len(periods))  # increase it if necessary
        hard_coded_omegas = 2 * np.pi / torch.tensor(periods, dtype=float)
        idx = 0
        for num_freq in self.num_freqs:
            self.omegas[idx:idx + len(periods)] = hard_coded_omegas
            idx += num_freq

    def sample_error(self, xt, which, tt=None):
        '''
        sample_error computes all temporally local losses within the first
        period, i.e. between [0,2pi/t]
        Parameters
        ----------
        xt : TYPE numpy.array
            Temporal data whose first dimension is time.
        which : TYPE int
            Index of the entry of omega
        Returns
        -------
        TYPE numpy.array
            Matrix that contains temporally local losses between [0,2pi/t]
            dimensions: [T, sample_num]
        '''
        if type(xt) == np.ndarray:
            xt = torch.tensor(xt, device=self.device)

        num_samples = self.sample_num
        omega = self.omegas
        batch = self.parallel_batch_size

        t = torch.arange(xt.shape[0], device=self.device) + 1
        errors = []

        pi_block = torch.zeros((num_samples, len(omega)), device=self.device)
        pi_block[:, which] = torch.arange(0, num_samples) * np.pi * 2 / num_samples

        if t.shape[0] < batch:
            batch = t.shape[0]
        for i in range(int(np.ceil(xt.shape[0] / batch))):
            t_batch = t[i * batch:(i + 1) * batch][:, None]
            wt = t_batch * omega[None]
            wt[:, which] = 0
            wt = wt[:, None] + pi_block[None]
            k = torch.cat([torch.cos(wt), torch.sin(wt)], -1)  # TODOTHIS MIGHT BE WRONG BECAUSE OF INDEXING # [cos_mu_w1, cos_mu_w2, cos_sigma_w1, cos_sigma_w2, cos_alpha_w1, cos_alpha_w2, sin...]
            loss = self.model_obj(k, xt[i * batch:(i + 1) * batch, None], None).cpu().detach().numpy()
            errors.append(loss)

        if self.device.startswith('cuda'):
            torch.cuda.empty_cache()

        return np.concatenate(errors, axis=0)

    def reconstruct(self, errors, use_heuristic=True):
        """
        reconstructs the total error surface from samples of temporally local loss functions
        :param errors: the temporally local loss functions for t=1,2... sampled within 2pi/t
        :param use_heuristic: whether to implement the unknown phase problem heuristic to improve optimization
        :return: Global loss function (the first period--from 0 to 2pi) with respect to omega, its fft
        """

        e_fft = np.fft.fft(errors)
        E_ft = np.zeros(errors.shape[0] * self.sample_num, dtype=np.complex64)

        for t in range(1, e_fft.shape[0] + 1):
            E_ft[np.arange(self.sample_num // 2) * t] += e_fft[t - 1, :self.sample_num // 2]

        E_ft = np.concatenate([E_ft, np.conj(np.flip(E_ft))])[:-1]
        E = np.real(np.fft.ifft(E_ft))

        if use_heuristic:
            E = -np.abs(E - np.median(E))
            # E = gaussian_filter(E, 5)

        return E, E_ft

    def fft(self, xt, i, tt=None, verbose=False):
        '''
        fft first samples all temporaly local losses within the first period
        and then reconstructs the global error surface w.r.t. omega_i
        Parameters
        ----------
        xt : TYPE numpy.array
            Temporal data whose first dimension is time.
        i : TYPE int
            Index of the entry of omega
        verbose : TYPE boolean, optional
            DESCRIPTION. The default is False.
        tt : TYPE numpy.array
            the times of measurement of xt
        Returns
        -------
        E : TYPE numpy.array
            Global loss surface in time domain.
        E_ft : TYPE
            Global loss surface in frequency domain.
        '''
        assert (tt is None), "Not yet implemented for non-uniform samples"  # TODO


        E, E_ft = self.reconstruct(self.sample_error(xt, i))
        omegas = np.linspace(0, 0.5, len(E))

        # get the values of omega that have already been used
        omegas_current = self.omegas.cpu().detach().numpy()
        omegas_current[i] = -1
        for j, num_freqs in enumerate(self.num_freqs):
            lower = sum(self.num_freqs[:j])
            upper = sum(self.num_freqs[:j + 1])
            if lower <= i < upper:
                omegas_current = omegas_current[lower:upper]

        found = False
        j = 0
        while not found:

            amax = np.argpartition(E, j)[j]  # jth biggest freq
            # The if statement avoids non-unique entries in omega and that the
            # frequencies are 0 (should be handled by bias term)
            # "nonzero AND has a period that's more than 1 different from those that have already been discovered"
            if amax >= 1 and np.all(np.abs(2 * np.pi / omegas_current - 1 / omegas[amax]) > 1):
                found = True
                if verbose:
                    print('Setting', i, 'to', 1 / omegas[amax])

                self.omegas[i] = torch.from_numpy(np.array([omegas[amax]]))
                self.omegas[i] *= 2 * np.pi

            j += 1

        # plt.plot(omegas, E)
        # plt.title(f"omega {i}")
        # plt.xlabel("frequency (periods per time)")
        # plt.ylabel("loss")
        # plt.show()

        return E, E_ft

    def sgd(self, xt, tt=None, covariates=None, weight_decay=0, verbose=False, lr_theta=1e-5, lr_omega=1e-5, training_mask=None):
        '''
        sgd performs a single epoch of stochastic gradient descent on parameters
        of f (Theta) and frequencies omega
        Parameters
        ----------
        xt : TYPE numpy.array
            Temporal data whose first dimension is time.
        tt : TYPE numpy.array
            the times of measurement of xt
        covariates : np.array of shape (time, n)
        verbose : TYPE boolean, optionally
            The default is False.
        Returns
        -------
        TYPE float
            Loss.
        '''

        batch_size = self.batch_size

        T = xt.shape[0]

        omega = nn.Parameter(self.omegas)

        # opt = optim.Adam(self.model_obj.parameters(), lr=1e-4 * (1 / (1 + np.exp(-(iteration - 15)))), betas=(0.99, 0.9999), eps=1e-5, weight_decay=weight_decay)
        # opt = optim.SGD(self.model_obj.parameters(), lr=lr_theta * (1 / (1 + np.exp(-(iteration - 15)))), weight_decay=weight_decay)
        opt = optim.SGD(self.model_obj.parameters(), lr=lr_theta, weight_decay=weight_decay)
        opt_omega = optim.SGD([omega], lr=lr_omega / T)

        t = torch.arange(T, device=self.device) if tt is None else torch.tensor(tt, device=self.device)
        covars = torch.zeros((T,0)) if covariates is None else (covariates - self.covariates_mean) / self.covariates_std

        losses = []

        # create random batches
        idxs = np.arange(T)
        np.random.shuffle(idxs)
        batches = idxs[:T // batch_size * batch_size].reshape((T // batch_size, batch_size))

        for i in range(len(batches)):
            opt.zero_grad()
            opt_omega.zero_grad()

            ts = t[batches[i]]

            o = torch.unsqueeze(omega, 0)
            ts_ = torch.unsqueeze(ts, -1).type(torch.get_default_dtype()) + 1

            xt_t = torch.tensor(xt[batches[i], :], device=self.device)

            wt = ts_ * o

            k = torch.cat([torch.cos(wt), torch.sin(wt), covars[batches[i], :]], -1)
            batch_mask = training_mask[batches[i]] if training_mask is not None else None

            batch_losses = self.model_obj(k, xt_t, batch_mask)
            if self.loss_weights is not None:
                weighted_losses = batch_losses * self.loss_weights[batches[i]]
                loss = torch.mean(weighted_losses)
            else:
                loss = torch.mean(batch_losses)

            loss.backward()

            opt.step()
            opt_omega.step()

            losses.append(loss.cpu().detach().numpy())

        if verbose:
            print('Setting periods to', 2 * np.pi / omega)

        self.omegas = omega.data

        return np.mean(losses)

    def fit(self, xt, tt=None, covariates=None, iterations=20, interval=10, cutoff=50, weight_decay=1e-3, verbose=False,
            lr_theta=1e-4, lr_omega=1e-5, training_mask=None):
        '''
        Given a dataset, this function alternatingly optimizes omega and
        parameters of f. Specifically, the algorithm performs interval many
        epochs, then updates all entries in omega. This process is repeated
        until iterations-many epochs have been performed
        Parameters
        ----------
        xt : TYPE 2D numpy.array
            Temporal data whose first dimension is time.
        tt : TYPE 1D numpy.array of shape (xt.shape[0],)
            the times of measurement of xt. Default None, which assumes tt is uniform
        covariates : TYPE np.array of shape (xt.shape[0], num_covariates)
            covariates that should be passed into the neural network along with the
            sines and cosines. Covariates are normalized before passing into NN, and
            the normalization is remembered for when `predict` is called
        iterations : TYPE int, optional
            Total number of SGD epochs
        interval : TYPE, optional
            The interval at which omegas are updated, i.e. if
            interval is 5, then omegas are updated every 5 epochs. The default is 5.
        verbose : TYPE boolean, optional
            DESCRIPTION. The default is False.
        cutoff : TYPE int, number of iterations after which to stop updating omegas
        weight_decay : TYPE float, regularization parameter
        lr_theta : TYPE float, learning rate for the model object
        lr_omega : TYPE float, learning rate for adjusting omegas
        training_mask : TYPE torch.tensor or np.array, which training data points should be
                        using in optimizing the location parameter (eg. mu).
                        shape should match xt. a 1 indicates to train mu on that data,
                        a 0 indicates not to.
                        Default: None (equivalent to torch.ones(xt.shape))
        Returns
        -------
        Losses
        '''
        assert (len(xt.shape) > 1), 'Input data needs to be at least 2D'
        if training_mask is not None:
            training_mask = torch.Tensor(training_mask)
        if (covariates is None and self.model_obj.num_covariates != 0) or covariates.shape[1] != self.model_obj.num_covariates:
            raise ValueError(f"model object requires {self.model_obj.num_covariates} covariates but {covariates.shape[1] if covariates is not None else 0} were provided")
        if self.model_obj.num_covariates != 0:
            if covariates is not None:
                covariates = torch.Tensor(covariates)
                self.covariates_mean = covariates.mean(axis=0)
                self.covariates_std = covariates.std(axis=0)

        l = None
        losses = []
        for i in range(iterations):

            if i % interval == 0 and i < cutoff:
                # only update omegas that are note the first self.num_fixed_omegas idxs of each param
                param_num = 0
                for num_freqs in self.num_freqs:
                    for k in range(param_num + self.num_fixed_omegas, param_num + num_freqs):
                        self.fft(xt, k, tt=tt, verbose=verbose)
                    param_num += num_freqs

            if verbose:
                print('Iteration ', i)
                print(2 * np.pi / self.omegas)

            l = self.sgd(xt, tt=tt, covariates=covariates, weight_decay=weight_decay, verbose=verbose,
                         lr_theta=lr_theta, lr_omega=lr_omega, training_mask=training_mask)
            losses.append(l)
            if verbose:
                print('Loss: ', l)
            elif i % 50 == 10:
                print(f"Loss at iteration {i}: {l}")

            if not np.isfinite(l):
                break

        print("Final loss:", l)
        return losses

    def predict(self, T, covariates=None):
        '''
        Predicts the data from 1 to T.
        Parameters
        ----------
        T : TYPE int
            Prediction horizon
            TYPE numpy.ndarray
            Exact times for which to predict, 1D array
        covariates : TYPE np.array of shape (xt.shape[0], num_covariates)
            covariates that should be passed into the neural network along with the
            sines and cosines
        Returns
        -------
        TYPE numpy.array
            xhat from 0 to T.
        '''
        if (covariates is None and self.model_obj.num_covariates != 0) or covariates.shape[1] != self.model_obj.num_covariates:
            raise ValueError(
                f"model object requires {self.model_obj.num_covariates} covariates but {covariates.shape[1] if covariates is not None else 0} were provided")

        t = torch.arange(T, device=self.device) + 1 if isinstance(T, int) else torch.tensor(T, device=self.device)
        ts_ = torch.unsqueeze(t, -1).type(torch.get_default_dtype())
        covars = torch.zeros((T,0)) if covariates is None else (torch.Tensor(covariates) - self.covariates_mean) / self.covariates_std
        o = torch.unsqueeze(self.omegas, 0)

        k = torch.cat([torch.cos(ts_ * o), torch.sin(ts_ * o), covars], -1)

        if self.multi_gpu:
            params = self.model_obj.module.decode(k)
        else:
            params = self.model_obj.decode(k)

        return tuple(param.cpu().detach().numpy() for param in params)
