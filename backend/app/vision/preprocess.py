"""Classical image preprocessing: quality assessment, deskew, binarization."""

import cv2
import numpy as np

try:  # C++ kernel (native/); the NumPy path below is the reference implementation
    from clawback_native import sauvola as _native_sauvola
except ImportError:  # pragma: no cover - exercised when the extension is not built
    _native_sauvola = None

BLUR_THRESHOLD = 100.0  # variance of Laplacian below this reads as out of focus
LOW_CONTRAST_THRESHOLD = 35.0


def assess_quality(gray: np.ndarray) -> dict[str, float | bool]:
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast = float(gray.std())
    return {
        "sharpness": round(sharpness, 1),
        "contrast": round(contrast, 1),
        "brightness": round(float(gray.mean()), 1),
        "blurry": sharpness < BLUR_THRESHOLD,
        "low_contrast": contrast < LOW_CONTRAST_THRESHOLD,
    }


def sauvola(gray: np.ndarray, window: int = 31, k: float = 0.2, r: float = 128.0) -> np.ndarray:
    """Adaptive binarization; 255 = background, 0 = ink."""
    if _native_sauvola is not None:
        return np.asarray(_native_sauvola(gray, window, k, r))
    return sauvola_reference(gray, window, k, r)


def sauvola_reference(gray: np.ndarray, window: int = 31, k: float = 0.2, r: float = 128.0) -> np.ndarray:
    """Vectorised NumPy Sauvola with the same window clipping as the C++ kernel."""
    img = gray.astype(np.float64)
    h, w = img.shape
    half = window // 2
    integral = np.pad(img, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    integral_sq = np.pad(img * img, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    ys, xs = np.arange(h), np.arange(w)
    y0, y1 = np.clip(ys - half, 0, h), np.clip(ys + half + 1, 0, h)
    x0, x1 = np.clip(xs - half, 0, w), np.clip(xs + half + 1, 0, w)
    n = np.outer(y1 - y0, x1 - x0)

    def window_sum(table: np.ndarray) -> np.ndarray:
        return np.asarray(table[np.ix_(y1, x1)] - table[np.ix_(y0, x1)] - table[np.ix_(y1, x0)] + table[np.ix_(y0, x0)])

    mean = window_sum(integral) / n
    std = np.sqrt(np.maximum(window_sum(integral_sq) / n - mean * mean, 0.0))
    threshold = mean * (1.0 + k * (std / r - 1.0))
    return np.where(img > threshold, 255, 0).astype(np.uint8)


def estimate_skew(binary: np.ndarray, max_angle: float = 10.0) -> float:
    """Projection-profile deskew: the rotation that makes text rows sharpest
    maximises the variance of horizontal ink sums. Coarse-to-fine search on a
    downscaled copy keeps this to a few milliseconds."""
    ink = 255 - binary
    scale = 800 / max(ink.shape)
    if scale < 1:
        ink = cv2.resize(ink, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    def score(angle: float) -> float:
        return float(np.var(_rotate(ink, angle, border=0).sum(axis=1)))

    coarse = max(np.arange(-max_angle, max_angle + 0.01, 0.5), key=score)
    fine = max(np.arange(coarse - 0.5, coarse + 0.51, 0.1), key=score)
    return round(float(fine), 2)


def deskew(image: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.1:
        return image
    return _rotate(image, angle, border=255)


def _rotate(image: np.ndarray, angle: float, border: int) -> np.ndarray:
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    value = (border,) * 3 if image.ndim == 3 else border
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_LINEAR, borderValue=value)
