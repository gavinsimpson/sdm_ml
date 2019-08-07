import numpy as np
import gpflow as gpf
from os.path import join
from .multi_output_gp import MultiOutputGP
from sdm_ml.presence_absence_model import PresenceAbsenceModel
from functools import partial
from distutils.dir_util import copy_tree


class CrossValidatedMultiOutputGP(PresenceAbsenceModel):

    def __init__(self, variances_to_try, cv_save_dir, n_folds=4, n_kernels=10,
                 add_bias=True, rbf_var=0.1, bias_var=0.1,
                 kern_var_trainable=False, n_inducing=100, maxiter=int(1E6)):

        self.model = None
        self.is_fit = False
        self.variances_to_try = variances_to_try
        self.cv_save_dir = cv_save_dir
        self.n_folds = n_folds

        self.kernel_fun = partial(
            MultiOutputGP.build_default_kernel, n_kernels=n_kernels,
            add_bias=add_bias, kern_var_trainable=kern_var_trainable,
            rbf_var=rbf_var, bias_var=bias_var)

        self.model_fun = partial(MultiOutputGP, n_inducing=n_inducing,
                                 n_latent=n_kernels, maxiter=maxiter)

    def fit(self, X, y):

        n_dims = X.shape[1]
        n_outputs = y.shape[1]

        kern_fun = partial(self.kernel_fun, n_dims=n_dims, n_outputs=n_outputs)

        def get_model(w_prior):

            # We need to make a model creation function.
            cur_kernel = kern_fun(w_prior=w_prior)
            model_fun = partial(self.model_fun, kernel=cur_kernel)
            return model_fun()

        mean_scores = list()

        for cur_variance in self.variances_to_try:

            print(f'Fitting {cur_variance:.2f}')

            model_fun = lambda: get_model(cur_variance) # NOQA

            cur_mean_score = MultiOutputGP.cross_val_score(
                X, y, model_fun, save_dir=join(
                    self.cv_save_dir, f'{cur_variance:.2f}'),
                n_folds=self.n_folds)

            gpf.reset_default_graph_and_session()

            print(f'Mean likelihood is {cur_mean_score}')

            mean_scores.append(cur_mean_score)

        mean_scores = np.array(mean_scores)
        best_score = np.argmax(mean_scores)
        best_variance = self.variances_to_try[best_score]

        print(f'Best score of {mean_scores[best_score]:.2f} obtained by '
              f'setting prior variance to {best_variance:.2f}')

        best_model = get_model(best_variance)

        best_model.fit(X, y)

        self.is_fit = True
        self.model = best_model

    def predict_log_marginal_probabilities(self, X):

        return self.model.predict_log_marginal_probabilities(X)

    def calculate_log_likelihood(self, X, y):

        return self.model.calculate_log_likelihood(X, y)

    def save_model(self, target_folder):

        self.model.save_model(target_folder)

        # Copy over the cv results
        copy_tree(self.cv_save_dir, join(target_folder, 'cv_results'))