import numpy as np
import scipy.io
from scipy.stats import kurtosis, skew
import os

def load_cwru_mat(filepath):
    """Extract Drive End (DE) vibration signal from CWRU .mat file."""
    data = scipy.io.loadmat(filepath)
    for key in data.keys():
        if 'DE_time' in key:
            return data[key].flatten()
    raise KeyError(f"Could not find DE_time vibration data in {filepath}")

def extract_features(signal_window, sample_rate=12000, num_fft_bins=16):
    """
    Extract embedded-friendly statistical and frequency features from a vibration window.
    Designed specifically to be implementable in pure C using CMSIS-DSP on Cortex-M.
    
    Returns a 1D feature vector:
    - Time-domain: RMS, Peak-to-Peak, Crest Factor, Kurtosis, Skewness, Variance
    - Frequency-domain: Energy in `num_fft_bins` frequency bands
    """
    # 1. Time-Domain Metrics (Low computation cost on MCU)
    rms = np.sqrt(np.mean(signal_window ** 2))
    peak_to_peak = np.ptp(signal_window)
    crest_factor = (peak_to_peak / 2.0) / (rms + 1e-8)
    kurt = float(kurtosis(signal_window))
    skew_val = float(skew(signal_window))
    variance = float(np.var(signal_window))
    
    # 2. Frequency-Domain Metrics (FFT energy bins)
    # On Cortex-M, arm_rfft_fast_f32 gives the magnitude spectrum
    fft_vals = np.abs(np.fft.rfft(signal_window))
    # Bin into num_fft_bins bands
    bin_size = len(fft_vals) // num_fft_bins
    fft_bins = []
    for i in range(num_fft_bins):
        start = i * bin_size
        end = (i + 1) * bin_size if i < num_fft_bins - 1 else len(fft_vals)
        fft_bins.append(np.mean(fft_vals[start:end]))
    
    feature_vector = np.array([rms, peak_to_peak, crest_factor, kurt, skew_val, variance] + fft_bins, dtype=np.float32)
    return feature_vector

def window_signal(signal, window_size=1024, step_size=512, sample_rate=12000, num_fft_bins=16):
    """Slice raw vibration continuous signal into overlapping windows and extract features."""
    num_windows = (len(signal) - window_size) // step_size
    features = []
    for i in range(num_windows):
        start = i * step_size
        window = signal[start:start + window_size]
        features.append(extract_features(window, sample_rate, num_fft_bins))
    return np.array(features, dtype=np.float32)
