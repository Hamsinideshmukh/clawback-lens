"""Renders synthetic documents to degraded page images with known ground truth.

Used by the evaluation harness, the vision tests, and scripts/seed.py."""

import random
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from training.corpus import SyntheticDocument

PAGE_W, PAGE_H = 1240, 1754  # A4 at 150 DPI


@dataclass
class Degradation:
    rotation: float = 0.0
    noise_sigma: float = 0.0
    blur: bool = False
    shadow: bool = False  # uneven illumination, as in phone photos
    jpeg_quality: int | None = None

    @classmethod
    def random(cls, rng: random.Random) -> "Degradation":
        return cls(
            rotation=round(rng.uniform(-6, 6), 1),
            noise_sigma=rng.choice([0.0, 4.0, 8.0]),
            blur=rng.random() < 0.3,
            shadow=rng.random() < 0.4,
            jpeg_quality=rng.choice([None, 70, 85]),
        )


def render(doc: SyntheticDocument, rng: random.Random, degradation: Degradation | None = None) -> np.ndarray:
    """Returns a BGR page image."""
    page = Image.new("L", (PAGE_W, PAGE_H), 255)
    draw = ImageDraw.Draw(page)
    title = ImageFont.load_default(size=44)
    body = ImageFont.load_default(size=rng.choice([26, 28, 30]))

    y = 110
    draw.text((90, y), doc.lines[0], font=title, fill=0)
    y += 100
    for line in doc.lines[1:]:
        for wrapped in _wrap(draw, line, body, PAGE_W - 180):
            draw.text((90, y), wrapped, font=body, fill=rng.randint(0, 40))
            y += 46
        y += 8

    image = np.array(page)
    if doc.with_signature:
        y = min(y + 60, PAGE_H - 260)
        draw_text = ImageDraw.Draw(page)
        draw_text.text((90, y + 60), "Signature:", font=body, fill=0)
        image = np.array(page)
        _draw_signature(image, x=300, y=y, rng=rng)
    if doc.qr_payload:
        qr = cv2.QRCodeEncoder.create().encode(doc.qr_payload)
        qr = cv2.resize(qr, (260, 260), interpolation=cv2.INTER_NEAREST)
        image[PAGE_H - 420 : PAGE_H - 160, PAGE_W - 400 : PAGE_W - 140] = qr

    return _degrade(cv2.cvtColor(image, cv2.COLOR_GRAY2BGR), degradation or Degradation(), rng)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    return [*lines, current] if current else lines


def _draw_signature(image: np.ndarray, x: int, y: int, rng: random.Random) -> None:
    """A cursive-like scribble: a sum of sinusoids along a slightly rising baseline."""
    width = rng.randint(280, 420)
    t = np.linspace(0, 1, 400)
    loops = rng.uniform(5, 9)
    xs = x + t * width + 18 * np.sin(2 * np.pi * loops * t + rng.uniform(0, 3))
    ys = y + 70 - 25 * t + 32 * np.sin(2 * np.pi * loops * t * 1.3) + 10 * np.sin(2 * np.pi * rng.uniform(1, 3) * t)
    points = np.stack([xs, ys], axis=1).astype(np.int32)
    cv2.polylines(image, [points], isClosed=False, color=20, thickness=3, lineType=cv2.LINE_AA)


def _degrade(image: np.ndarray, d: Degradation, rng: random.Random) -> np.ndarray:
    if d.shadow:
        gradient = np.linspace(0.55, 1.0, image.shape[1])[None, :, None]
        image = (image.astype(np.float32) * gradient).astype(np.uint8)
    if d.rotation:
        h, w = image.shape[:2]
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), d.rotation, 1.0)
        image = cv2.warpAffine(image, matrix, (w, h), borderValue=(255, 255, 255))
    if d.blur:
        image = cv2.GaussianBlur(image, (3, 3), 0)
    if d.noise_sigma:
        noise = np.random.default_rng(rng.randint(0, 2**31)).normal(0, d.noise_sigma, image.shape)
        image = np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    if d.jpeg_quality:
        _, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, d.jpeg_quality])
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    return image
