"""Frozen CLIP ViT-B/32 (OpenAI, MIT) frame embeddings on a context crop around the GT person box.

Rationale: the confusable pairs are time-reversals of each other; what disambiguates them is the
*state* before vs after (seated vs standing, door open vs closed, object in hand vs on surface,
garment on vs off). CLIP frame embeddings + zero-shot state-prompt similarities at the start and
end of the segment encode that directly. Nothing is fitted here.
"""
import os
from functools import lru_cache

import cv2
import numpy as np
import torch

N_FRAMES = 8
CTX_PAD = 0.6
MODEL, PRETRAINED = "ViT-B-32", "openai"

# State prompts; features use the start/end similarity and its change.
PROMPTS = [
    "a photo of a person sitting on a chair",
    "a photo of a person sitting on a sofa or bed",
    "a photo of a person standing upright",
    "a photo of a person bending down",
    "a photo of a person holding an object in their hand",
    "a photo of a person with empty hands",
    "a photo of an object lying on the floor",
    "a photo of an object on a table",
    "a photo of an open door",
    "a photo of a closed door",
    "a photo of an open cabinet, drawer or fridge",
    "a photo of a closed cabinet, drawer or fridge",
    "a photo of a person wearing a jacket",
    "a photo of a person wearing a hat",
    "a photo of a person holding a piece of clothing",
    "a photo of a person putting on shoes",
]


@lru_cache(maxsize=None)
def clip_model():
    import open_clip
    m, _, pre = open_clip.create_model_and_transforms(MODEL, pretrained=PRETRAINED)
    m.eval()
    tok = open_clip.get_tokenizer(MODEL)
    with torch.no_grad():
        t = m.encode_text(tok(PROMPTS))
        t = t / t.norm(dim=-1, keepdim=True)
    cfg = open_clip.get_pretrained_cfg(MODEL, PRETRAINED)
    return m, t, np.array(cfg["mean"], np.float32), np.array(cfg["std"], np.float32)


def weight_path():
    import open_clip
    url = open_clip.get_pretrained_url(MODEL, PRETRAINED)
    return os.path.expanduser(os.path.join("~/.cache/clip", os.path.basename(url))), url


def _prep(crop, mean, std):
    h, w = crop.shape[:2]
    s = 224 / min(h, w)
    r = cv2.resize(crop, (max(224, int(round(w * s))), max(224, int(round(h * s)))), interpolation=cv2.INTER_CUBIC)
    y0, x0 = (r.shape[0] - 224) // 2, (r.shape[1] - 224) // 2
    r = r[y0:y0 + 224, x0:x0 + 224, ::-1].astype(np.float32) / 255.0
    return ((r - mean) / std).transpose(2, 0, 1)


@torch.no_grad()
def embed_crops(crops):
    """crops: list of BGR arrays -> (N,512) L2-normalised image embeddings, (N,P) prompt cosine sims."""
    m, txt, mean, std = clip_model()
    x = torch.from_numpy(np.stack([_prep(c, mean, std) for c in crops]))
    e = m.encode_image(x)
    e = e / e.norm(dim=-1, keepdim=True)
    return e.numpy().astype(np.float32), (e @ txt.T).numpy().astype(np.float32)
