import numpy as np
from scipy.stats import logistic
from os.path import split, join, isfile
from os import makedirs
from ml_tools.paths import get_cur_script_path
from ml_tools.stan import load_stan_model_cached
from ml_tools.utils import save_pickle_safely
from sdm_ml.presence_absence_model import PresenceAbsenceModel
from sklearn.preprocessing import StandardScaler


def add_intercept(X):

    return np.concatenate([X, np.ones((X.shape[0], 1))], axis=1)


class IndependentHierarchicalModel(PresenceAbsenceModel):

    def __init__(self):

        cur_path = split(get_cur_script_path(__file__))[0]
        stan_model_path = join(cur_path, 'independent_mixed.stan')
        assert isfile(stan_model_path)
        self.stan_model = load_stan_model_cached(stan_model_path)
        self.scaler = None
        self.is_fit = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:

        self.scaler = StandardScaler()
        scaled_x = self.scaler.fit_transform(X)
        scaled_x = add_intercept(scaled_x)

        stan_data = {
          'N': scaled_x.shape[0],
          'n_species': y.shape[1],
          'n_cov': scaled_x.shape[1],
          'y': y,
          'X': scaled_x
        }

        self.fit = self.stan_model.sampling(data=stan_data)
        self.is_fit = True

    def predict_log_marginal_probabilities(self, X: np.ndarray) -> np.ndarray:

        assert self.is_fit

        test_x = self.scaler.transform(X)
        test_x = add_intercept(test_x)

        n_species = self.fit['coefficients'].shape[-1]

        y_pred = np.empty((test_x.shape[0], n_species, 2))

        for cur_species in range(n_species):

            cur_coeff_draws = self.fit['coefficients'][..., cur_species]
            cur_logits = test_x @ cur_coeff_draws.T
            cur_probs = logistic.cdf(cur_logits)
            mean_probs = np.mean(cur_probs, axis=1)

            y_pred[:, cur_species, 0] = 1 - mean_probs
            y_pred[:, cur_species, 1] = mean_probs

        return np.log(y_pred)

    def calculate_log_likelihood(self, X: np.ndarray, y: np.ndarray) \
            -> np.ndarray:

        log_y_pred = self.predict_log_marginal_probabilities(X)

        site_log_lik = np.sum(
            y * log_y_pred[..., 1] + (1 - y) * log_y_pred[..., 0], axis=1)

        return site_log_lik

    def save_model(self, target_folder: str) -> None:

        makedirs(target_folder, exist_ok=True)

        save_pickle_safely(self.scaler, join(target_folder, 'scaler.pkl'))

        with open(join(target_folder, 'fit.txt'), 'w') as f:
            print(self.fit, file=f)

        np.savez(join(target_folder, 'samples.npz'),
                 **self.fit.extract())
