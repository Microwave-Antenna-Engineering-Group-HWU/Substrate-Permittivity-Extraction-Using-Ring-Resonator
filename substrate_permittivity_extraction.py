#!/usr/bin/env python3
"""
Substrate Permittivity Extraction Using Ring Resonator
=====================================================
Calculates effective permittivity (ε_e) and substrate permittivity (ε_r)
from a microstrip ring‑resonator S‑parameter file and visualises the results.

How to run
----------
1. Install dependencies:
     pip install -r requirements.txt
2. Edit the CONFIG block below.
3. Execute:
     python substrate_permittivity_extraction.py
"""

# ── CONFIG ────────────────────────────────────────────────────────────
S2P_FILE = "Measurements/10M_6G_no_soldermask.s2p"
RING_LENGTH_MM  = 100.0       # Ring circumference (mm)
SUBSTRATE_H_MM  = 1.6        # Substrate thickness H (mm)
TRACE_W_MM      = 3         # Microstrip trace width W (mm)

MIN_PEAK_DB     = 16.0         # Peak detection threshold above median (dB)
SAVE_CSV        = "results.csv"   # Set to None to skip CSV export
SHOW_PLOT       = True            # Set False to suppress figure

# --- Calibration (set CALIBRATE_L = True to use this feature) ---
CALIBRATE_L = False  # Set to True to override L with a value estimated from a known resonance
CALIBRATION_FREQ_HZ = 1.0e9  # Known resonance frequency (Hz)
CALIBRATION_EPSILON = 4.2    # Known permittivity (ε_r or ε_eff)
CALIBRATION_MODE_N = 1       # Mode number for the known resonance
# ──────────────────────────────────────────────────────────────────────

# --- Imports ---
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from skrf import Network

# Speed of light in vacuum (m/s)
C0 = 299_792_458.0

def microstrip_eps_r(eps_eff, h, w):
    """
    Calculate substrate permittivity (ε_r) from effective permittivity (ε_e),
    substrate height h, and trace width w using the inverted microstrip equation.
    """
    a = 1.0 / np.sqrt(1.0 + 12.0 * h / w)
    return (2.0 * eps_eff + a - 1.0) / (1.0 + a)

def find_s21_peaks(mag_db, min_peak_db):
    """
    Find resonance peaks in the S21 magnitude (in dB).
    Peaks are detected above the median + min_peak_db threshold.
    Returns the indices of the detected peaks.
    """
    threshold = np.median(mag_db) + min_peak_db
    print(f"Peak detection threshold: {threshold:.2f} dB")
    peaks, _ = find_peaks(mag_db, height=threshold)
    return peaks

def calculate_loss_tangent(freq, mag_db, peaks):
    """
    Estimate the loss tangent for each resonance peak using the -3 dB bandwidth method.
    Returns a list of loss tangent values for each peak.
    """
    loss_tangents = []
    for peak_idx in peaks:
        peak_mag = mag_db[peak_idx]
        half_mag = peak_mag - 3  # -3 dB point
        # Search left
        left = peak_idx
        while left > 0 and mag_db[left] > half_mag:
            left -= 1
        # Search right
        right = peak_idx
        while right < len(mag_db) - 1 and mag_db[right] > half_mag:
            right += 1
        f_left = freq[left]
        f_right = freq[right]
        f0 = freq[peak_idx]
        bw = f_right - f_left  # -3 dB bandwidth (Hz)
        # Q factor and loss tangent
        Q = f0 / bw if bw > 0 else np.nan
        # For a ring resonator, tan(delta) ≈ 1/Q
        loss_tangent = 1 / Q if Q > 0 else np.nan
        loss_tangents.append(loss_tangent)
    return loss_tangents

def estimate_effective_length(eps_known, freq_Hz, mode_n):
    """
    Back-calculate effective resonator length L_eff from known ε_r or ε_e and a known resonance.
    """
    return (C0 * mode_n) / (freq_Hz * np.sqrt(eps_known))

def main():
    # Load S-parameter data from Touchstone file
    ntwk = Network(S2P_FILE);
    freq = ntwk.f  # Frequency array (Hz)
    s21 = ntwk.s[:, 0, 1]  # S21 complex values
    mag_db = 20 * np.log10(np.abs(s21))  # Magnitude in dB

    # Find resonance peaks in S21
    peaks = find_s21_peaks(mag_db, MIN_PEAK_DB)
    freqs = freq[peaks]  # Resonant frequencies
    n_modes = np.arange(1, len(freqs) + 1)  # Mode numbers
    if len(freqs) == 0:
        raise RuntimeError("No peaks detected; adjust MIN_PEAK_DB or check data.")

    # Convert ring and substrate dimensions to meters
    if CALIBRATE_L:
        L = estimate_effective_length(CALIBRATION_EPSILON, CALIBRATION_FREQ_HZ, CALIBRATION_MODE_N)
        print(f"[Calibration] Using estimated L = {L*1e3:.2f} mm (from ε = {CALIBRATION_EPSILON}, f = {CALIBRATION_FREQ_HZ/1e9:.3f} GHz, n = {CALIBRATION_MODE_N})")
    else:
        L = RING_LENGTH_MM / 1e3
    h = SUBSTRATE_H_MM / 1e3
    w = TRACE_W_MM / 1e3

    # Calculate effective and substrate permittivity
    eps_eff = (C0 * n_modes / (freqs * L)) ** 2
    eps_r = microstrip_eps_r(eps_eff, h, w)

    # Print mode numbers
    print(f"n_modes: {n_modes}")

    # Calculate loss tangent for each peak
    loss_tangents = calculate_loss_tangent(freq, mag_db, peaks)

    # Create results DataFrame
    df = pd.DataFrame(
        dict(mode_n=n_modes, freq_Hz=freqs, eps_eff=eps_eff, eps_r=eps_r, loss_tan=loss_tangents)
    )

    # Print results to console
    print(df.to_string(index=False, float_format=lambda x: f"{x:.4g}"))
    print(f"Average ε_eff = {df.eps_eff.mean():.4g}")
    print(f"Average ε_r   = {df.eps_r.mean():.4g}")
    print(f"Average loss tangent = {df.loss_tan.mean():.4g}")

    # Optionally save results to CSV
    if SAVE_CSV:
        df.to_csv(SAVE_CSV, index=False)
        print(f"CSV saved → {SAVE_CSV}")

    # Plotting
    if SHOW_PLOT:
        # Separate S21 plot
        plt.figure(figsize=(8, 4))
        plt.plot(freq / 1e9, mag_db, lw=1.2, label="|S21|")
        plt.scatter(freqs / 1e9, mag_db[peaks], c="tab:orange", zorder=3, label="Detected Peaks")
        plt.title(f"Ring Resonator S21, L = {RING_LENGTH_MM:.1f} mm")
        plt.xlabel("Frequency [GHz]")
        plt.ylabel("S21 [dB]")
        plt.grid(True, ls=":")
        plt.legend()
        plt.tight_layout()
        plt.savefig("ring_resonator_S21.png", dpi=300)
        plt.show()

        # Permittivity plot
        fig, ax_eps = plt.subplots(figsize=(7, 4), constrained_layout=True)
        ax_eps.plot(freqs / 1e9, eps_eff, "o-", ms=4,
                    label="ε_e – effective/measured", color="tab:orange")
        ax_eps.plot(freqs / 1e9, eps_r, "o-", ms=4,
                    label="ε_r – back‑calculated", color="tab:green")
        ax_eps.axhline(eps_r.mean(), color="tab:green", ls="--", lw=0.8)
        ax_eps.axhline(eps_eff.mean(), color="tab:orange", ls="--", lw=0.8)
        ax_eps.set_title(
            f"Dielectric Constant for h = {SUBSTRATE_H_MM:.2f} mm, w = {TRACE_W_MM:.2f} mm"
        )
        ax_eps.set_xlabel("Frequency [GHz]")
        ax_eps.set_ylabel("Permittivity")
        ax_eps.grid(True, ls=":")
        ax_eps.legend()
        fig.savefig("ring_resonator_permittivity.png", dpi=300)
        plt.show()

if __name__ == "__main__":
    main()
