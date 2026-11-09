#!/usr/bin/env python3
"""Vérifie qu'un sprite livré reste le rendu Pixellab : même silhouette, pixels à peine retouchés.

Usage : pixellab_fidelity.py --base pixellab.png --final sprite.png [--min-shape 0.95] [--min-pixels 0.75]
Sortie : JSON {ok, shape, pixels, size}. Code 0 fidèle, 1 trop modifié, 2 comparaison impossible.

Une planche d'animation est comparée sur sa première frame (coin haut gauche, à la taille du rendu).
Un rendu généré à un multiple entier du canevas (Pixellab ne descend pas sous 16 px) est réduit d'abord.
"""
import argparse
import json
import sys
from collections import Counter

from PIL import Image

# Écart RGB cumulé toléré : un recalage de palette ne compte pas comme une retouche.
COLOR_TOLERANCE = 60


def fail(message):
    print(json.dumps({"ok": False, "error": message}))
    return 2


def block_majority(image, size):
    """Réduit par un facteur entier : chaque pixel prend la couleur majoritaire de son bloc, ou reste transparent."""
    width, height = size
    step_x, step_y = image.width // width, image.height // height
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    source = image.load()
    for y in range(height):
        for x in range(width):
            block = [source[x * step_x + i, y * step_y + j] for j in range(step_y) for i in range(step_x)]
            visible = [pixel for pixel in block if pixel[3] > 0]
            if len(visible) * 2 >= len(block):
                out.putpixel((x, y), Counter(visible).most_common(1)[0][0])
    return out


def aligned(base, final):
    """Ramène les deux images à la même taille, ou renvoie None si elles ne se comparent pas."""
    if base.size == final.size:
        return base, final
    fx, fy = base.width / final.width, base.height / final.height
    if fx == fy and fx.is_integer() and fx > 1:
        return block_majority(base, final.size), final
    if final.width >= base.width and final.height >= base.height:
        return base, final.crop((0, 0, base.width, base.height))
    return None


def compare(base, final):
    """Part des pixels à silhouette identique, et part des pixels visibles restés proches du rendu."""
    width, height = base.size
    a, b = base.load(), final.load()
    same_shape = visible = close = 0
    for y in range(height):
        for x in range(width):
            pa, pb = a[x, y], b[x, y]
            shown_a, shown_b = pa[3] > 0, pb[3] > 0
            same_shape += shown_a == shown_b
            if shown_a or shown_b:
                visible += 1
                if shown_a and shown_b and sum(abs(pa[i] - pb[i]) for i in range(3)) <= COLOR_TOLERANCE:
                    close += 1
    return same_shape / (width * height), (close / visible if visible else 0.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--final", required=True)
    parser.add_argument("--min-shape", type=float, default=0.95)
    parser.add_argument("--min-pixels", type=float, default=0.75)
    args = parser.parse_args()
    try:
        base = Image.open(args.base).convert("RGBA")
        final = Image.open(args.final).convert("RGBA")
    except OSError as error:
        return fail(str(error))
    pair = aligned(base, final)
    if pair is None:
        return fail("sizes do not compare: %dx%d vs %dx%d" % (base.width, base.height, final.width, final.height))
    shape, pixels = compare(*pair)
    ok = shape >= args.min_shape and pixels >= args.min_pixels
    print(json.dumps({"ok": ok, "shape": round(shape, 3), "pixels": round(pixels, 3), "size": "%dx%d" % pair[0].size}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
