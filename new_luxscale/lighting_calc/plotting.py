"""Matplotlib figures for distribution and heatmap (GUI / PDF helpers)."""

import tempfile

import matplotlib.pyplot as plt
import numpy as np

from .constants import luminaire_shapes


def _fixture_draw_size(luminaire_name):
    meta = luminaire_shapes.get(luminaire_name)
    if not meta:
        return (0.5, 0.5)
    sh = meta.get("shape")
    if sh == "circle":
        d = float(meta.get("diameter", 0.5))
        return (d, d)
    if sh == "square":
        s = float(meta.get("size", 0.5))
        return (s, s)
    if sh == "rectangle":
        return (float(meta.get("width", 0.5)), float(meta.get("height", 0.1)))
    return (0.5, 0.5)


def draw_lighting_distribution(length, width, luminaire_name, num_x, num_y):
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.set_xlim(0, length)
    ax.set_ylim(0, width)
    ax.set_aspect("equal")
    ax.set_title("Lighting Distribution")

    size_x, size_y = _fixture_draw_size(luminaire_name)
    margin = 1
    dx = (length - 2 * margin) / num_x
    dy = (width - 2 * margin) / num_y

    for i in range(num_x):
        for j in range(num_y):
            cx = margin + (i + 0.5) * dx
            cy = margin + (j + 0.5) * dy
            ax.add_patch(
                plt.Rectangle(
                    (cx - size_x / 2, cy - size_y / 2),
                    size_x,
                    size_y,
                    color="orange",
                )
            )

    ax.set_xlabel("Length (m)")
    ax.set_ylabel("Width (m)")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
        fig.savefig(tmpfile.name, bbox_inches="tight")
        return tmpfile.name


def draw_heatmap(length, width, num_x, num_y):
    heatmap = np.zeros((100, 100))
    for i in range(num_x):
        for j in range(num_y):
            x = int(((i + 0.5) * length / num_x) / length * 100)
            y = int(((j + 0.5) * width / num_y) / width * 100)
            heatmap[y, x] += 1
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.imshow(
        heatmap,
        cmap="YlOrRd",
        interpolation="bilinear",
        extent=[0, length, 0, width],
        origin="lower",
    )
    ax.set_title("Heatmap")
    ax.set_xlabel("Length (m)")
    ax.set_ylabel("Width (m)")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
        fig.savefig(tmpfile.name, bbox_inches="tight")
        return tmpfile.name
