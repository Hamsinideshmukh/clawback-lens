// Sauvola adaptive thresholding in O(1) per pixel using integral images.
//
//   T(x, y) = m(x, y) * (1 + k * (s(x, y) / R - 1))
//
// m and s are the mean and standard deviation of the window centred on
// (x, y). Phone photos of receipts have uneven lighting that defeats a global
// threshold; Sauvola handles it, but a naive implementation costs O(w^2) per
// pixel. Two integral images (sum and sum of squares) reduce every window
// statistic to four table lookups.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

namespace {

using Image = py::array_t<uint8_t, py::array::c_style | py::array::forcecast>;

Image sauvola(const Image& image, int window, double k, double r) {
  if (image.ndim() != 2) {
    throw std::invalid_argument("expected a 2-D grayscale image");
  }
  if (window < 3 || window % 2 == 0) {
    throw std::invalid_argument("window must be an odd integer >= 3");
  }

  const auto h = static_cast<std::size_t>(image.shape(0));
  const auto w = static_cast<std::size_t>(image.shape(1));
  const uint8_t* src = image.data();

  // (h + 1) x (w + 1) tables with a zero first row and column, so window sums
  // need no boundary special cases.
  const std::size_t stride = w + 1;
  std::vector<double> sum((h + 1) * stride, 0.0);
  std::vector<double> sq((h + 1) * stride, 0.0);

  Image out({h, w});
  uint8_t* dst = out.mutable_data();
  const auto half = static_cast<std::size_t>(window / 2);

  {
    py::gil_scoped_release release;  // pure C++ below: let other threads run

    for (std::size_t y = 0; y < h; ++y) {
      double row_sum = 0.0;
      double row_sq = 0.0;
      for (std::size_t x = 0; x < w; ++x) {
        const double v = src[y * w + x];
        row_sum += v;
        row_sq += v * v;
        sum[(y + 1) * stride + x + 1] = sum[y * stride + x + 1] + row_sum;
        sq[(y + 1) * stride + x + 1] = sq[y * stride + x + 1] + row_sq;
      }
    }

    for (std::size_t y = 0; y < h; ++y) {
      const std::size_t y0 = y > half ? y - half : 0;
      const std::size_t y1 = std::min(h, y + half + 1);
      for (std::size_t x = 0; x < w; ++x) {
        const std::size_t x0 = x > half ? x - half : 0;
        const std::size_t x1 = std::min(w, x + half + 1);
        const double n = static_cast<double>((y1 - y0) * (x1 - x0));

        const double s = sum[y1 * stride + x1] - sum[y0 * stride + x1] -
                         sum[y1 * stride + x0] + sum[y0 * stride + x0];
        const double s2 = sq[y1 * stride + x1] - sq[y0 * stride + x1] -
                          sq[y1 * stride + x0] + sq[y0 * stride + x0];

        const double mean = s / n;
        const double stddev = std::sqrt(std::max(0.0, s2 / n - mean * mean));
        const double threshold = mean * (1.0 + k * (stddev / r - 1.0));
        dst[y * w + x] = src[y * w + x] > threshold ? 255 : 0;
      }
    }
  }
  return out;
}

}  // namespace

PYBIND11_MODULE(_core, m) {
  m.doc() = "Native image kernels for the Clawback Lens document vision pipeline";
  m.def("sauvola", &sauvola, py::arg("image"), py::arg("window") = 31,
        py::arg("k") = 0.2, py::arg("r") = 128.0,
        "Sauvola binarization of a uint8 grayscale image. Returns 255 for "
        "background and 0 for ink.");
}
