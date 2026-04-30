"""Try various parametric fits on the per-minute duration data."""
import csv
import numpy as np
from scipy.optimize import curve_fit
from scipy.interpolate import CubicSpline
from scipy.signal import medfilt

with open('minute_durations.csv') as f:
    r = csv.DictReader(f)
    data = [(int(row['minute_index']), int(row['duration_ms']), int(row['n_observations'])) for row in r]

x = np.array([d[0] for d in data])
y = np.array([d[1] for d in data], dtype=float)
n = np.array([d[2] for d in data])
print(f'Data: {len(x)} minutes, mean={y.mean():.0f}ms, range=[{y.min():.0f}, {y.max():.0f}]')

y_smooth = medfilt(y, kernel_size=5)
print(f'Median-5 smoothed: range=[{y_smooth.min():.0f}, {y_smooth.max():.0f}]')


def m_sine(x, a, b, period, phase):
    return a + b * np.sin(2 * np.pi * x / period + phase)


def m_2harm(x, a, b1, p1, b2, p2):
    return a + b1 * np.sin(2 * np.pi * x / 1440 + p1) + b2 * np.sin(2 * np.pi * 2 * x / 1440 + p2)


def m_3harm(x, a, b1, p1, b2, p2, b3, p3):
    t = 2 * np.pi * x / 1440
    return a + b1 * np.sin(t + p1) + b2 * np.sin(2 * t + p2) + b3 * np.sin(3 * t + p3)


def m_4harm(x, a, b1, p1, b2, p2, b3, p3, b4, p4):
    t = 2 * np.pi * x / 1440
    return a + b1 * np.sin(t + p1) + b2 * np.sin(2 * t + p2) + b3 * np.sin(3 * t + p3) + b4 * np.sin(4 * t + p4)


def m_5harm(x, a, b1, p1, b2, p2, b3, p3, b4, p4, b5, p5):
    t = 2 * np.pi * x / 1440
    return a + b1 * np.sin(t + p1) + b2 * np.sin(2 * t + p2) + b3 * np.sin(3 * t + p3) + b4 * np.sin(4 * t + p4) + b5 * np.sin(5 * t + p5)


def m_2gauss(x, base, da, dc, dw, ea, ec, ew):
    return base + da * np.exp(-((x - dc) / dw) ** 2) + ea * np.exp(-((x - ec) / ew) ** 2)


def m_cos_power(x, base, amp, phase, power):
    angle = 2 * np.pi * x / 1440 + phase
    return base + amp * np.abs(np.cos(angle)) ** power


def m_2sech(x, base, da, dc, dw, ea, ec, ew):
    """Two sech^2 bumps (smoother than gaussian)."""
    return base + da / np.cosh((x - dc) / dw) ** 2 + ea / np.cosh((x - ec) / ew) ** 2


def m_2cos_bump(x, base, da, dc, dw, ea, ec, ew):
    """Two raised-cosine bumps with finite support."""
    d1 = (x - dc) / dw
    e1 = (x - ec) / ew
    a1 = np.where(np.abs(d1) < 1, da * np.cos(np.pi * d1 / 2) ** 2, 0)
    a2 = np.where(np.abs(e1) < 1, ea * np.cos(np.pi * e1 / 2) ** 2, 0)
    return base + a1 + a2


# Allow models to wrap (period 1440)
def cyclic_x(x):
    return x % 1440


models = [
    ("sine 1H", m_sine, [3000, 1000, 1440, 0]),
    ("2 harmonics", m_2harm, [3000, 1000, 0, 1500, 0]),
    ("3 harmonics", m_3harm, [3000, 1000, 0, 1500, 0, 1000, 0]),
    ("4 harmonics", m_4harm, [3000, 1000, 0, 1500, 0, 1000, 0, 500, 0]),
    ("5 harmonics", m_5harm, [3000, 1000, 0, 1500, 0, 1000, 0, 500, 0, 300, 0]),
    ("2 gaussians", m_2gauss, [2000, 3000, 500, 80, 3000, 1080, 80]),
    ("cos^p", m_cos_power, [3000, 2000, 0, 2.0]),
    ("2 sech^2", m_2sech, [2000, 3000, 500, 80, 3000, 1080, 80]),
    ("2 raised-cos", m_2cos_bump, [2000, 3000, 500, 200, 3000, 1080, 200]),
]

print()
print('Model fits (lower RMS = better):')
print(f'{"Model":<18} {"params":>7} {"RMS":>10} {"max err":>10}')
print('-' * 50)

results = []
for name, func, p0 in models:
    try:
        popt, _ = curve_fit(func, x, y_smooth, p0=p0, maxfev=20000)
        pred = func(x, *popt)
        rms = np.sqrt(np.mean((y - pred) ** 2))
        mx = np.max(np.abs(y - pred))
        rms_smooth = np.sqrt(np.mean((y_smooth - pred) ** 2))
        results.append((name, len(popt), rms, mx, popt, func, rms_smooth))
        print(f'{name:<18} {len(popt):>7} {rms:>10.0f} {mx:>10.0f}')
    except Exception as e:
        print(f'{name:<18}: FAILED ({type(e).__name__}: {e})')

results.sort(key=lambda r: r[2])

print()
print(f'Best parametric: {results[0][0]} with RMS {results[0][2]:.0f}ms (vs smoothed: {results[0][6]:.0f}ms)')
print('Params:', np.round(results[0][4], 3))

print()
print('=== Non-parametric baselines ===')

# Cubic spline through 24 hour means
hour_avgs = np.array([np.mean(y[h * 60:(h + 1) * 60]) for h in range(24)])
hour_x = np.arange(24) * 60 + 30
hour_x_ext = np.concatenate(([hour_x[-1] - 1440], hour_x, [hour_x[0] + 1440]))
hour_y_ext = np.concatenate(([hour_avgs[-1]], hour_avgs, [hour_avgs[0]]))
cs = CubicSpline(hour_x_ext, hour_y_ext)
pred_cs = cs(x)
rms_cs = np.sqrt(np.mean((y - pred_cs) ** 2))
print(f'Cubic spline through 24 hour means: RMS {rms_cs:.0f}ms')

# Cubic spline through 24 medians
hour_meds = np.array([np.median(y[h * 60:(h + 1) * 60]) for h in range(24)])
hour_y_ext_med = np.concatenate(([hour_meds[-1]], hour_meds, [hour_meds[0]]))
cs_med = CubicSpline(hour_x_ext, hour_y_ext_med)
pred_csm = cs_med(x)
rms_csm = np.sqrt(np.mean((y - pred_csm) ** 2))
print(f'Cubic spline through 24 hour medians: RMS {rms_csm:.0f}ms')

# Cubic spline through y_smooth (median-filtered) — sample at hour boundaries
print(f'Median-filtered data itself: RMS vs raw y = {np.sqrt(np.mean((y - y_smooth) ** 2)):.0f}ms')
