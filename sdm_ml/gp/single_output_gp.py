import gpflow
import numpy as np
from tqdm import tqdm
from scipy.stats import norm
from sdm_ml.model import PresenceAbsenceModel
from sklearn.preprocessing import StandardScaler
from sdm_ml.gp.utils import find_starting_z, predict_with_link


# TODO: Maybe allow for a more flexible kernel etc.

class SingleOutputGP(PresenceAbsenceModel):

    def __init__(self, num_inducing=100, opt_steps=1000, verbose=False,
                 n_draws_pred=4000):

        self.models = list()
        self.scaler = None
        self.num_inducing = num_inducing
        self.opt_steps = opt_steps
        self.verbose = verbose
        self.n_draws_pred = n_draws_pred

    def fit(self, X, y):

        self.scaler = StandardScaler()
        X = self.scaler.fit_transform(X)
        Z = find_starting_z(X, self.num_inducing)

        for i in tqdm(range(y.shape[1])):

            cur_outcomes = y[:, i].astype(np.float64).reshape(-1, 1)
            cur_kernel = gpflow.kernels.RBF(input_dim=X.shape[1], ARD=True)

            # TODO: May be able to move this outside the loop.
            cur_likelihood = gpflow.likelihoods.Bernoulli()

            m = gpflow.models.SVGP(X, cur_outcomes, kern=cur_kernel,
                                   likelihood=cur_likelihood, Z=Z)

            gpflow.train.ScipyOptimizer().minimize(m, maxiter=self.opt_steps,
                                                   disp=self.verbose)

            self.models.append(m)

    def predict(self, X):

        assert(len(self.models) > 0)
        predictions = list()

        X = self.scaler.transform(X)

        for m in self.models:

            means, variances = m.predict_f(X)
            means, variances = np.squeeze(means), np.squeeze(variances)
            draws = predict_with_link(means, variances, link_fun=norm.cdf
                                      samples=self.n_draws_pred)

            pred_mean_prob = np.mean(draws, axis=0)
            predictions.append(pred_mean_prob)

        return np.stack(predictions, axis=1)
