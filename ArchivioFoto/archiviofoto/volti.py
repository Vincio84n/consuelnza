"""Rilevamento e raggruppamento dei volti con OpenCV (YuNet + SFace): locale, nessun dato inviato all'esterno."""
import urllib.request

import numpy as np

from .core import ErroreArchivio, open_image, preview, master_path

MODELLI = {
    "detector": ("face_detection_yunet_2023mar.onnx",
                 "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"),
    "recognizer": ("face_recognition_sface_2021dec.onnx",
                   "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"),
}


def _cv2():
    try:
        import cv2
    except ImportError:
        raise ErroreArchivio("riconoscimento volti: installa OpenCV con  pip install opencv-python-headless")
    if not hasattr(cv2, "FaceDetectorYN"):
        raise ErroreArchivio("OpenCV troppo vecchio: serve la versione 4.8 o successiva")
    return cv2


def modelli(root):
    d = root / "modelli"
    d.mkdir(exist_ok=True)
    paths = {}
    for k, (name, url) in MODELLI.items():
        p = d / name
        if not p.exists() or p.stat().st_size < 10_000:
            try:
                tmp = p.with_suffix(".part")
                urllib.request.urlretrieve(url, tmp)
                tmp.replace(p)
            except Exception as e:
                raise ErroreArchivio(f"download del modello {name} fallito ({e}). "
                                     f"Scaricalo a mano da {url} e mettilo in {d}")
        paths[k] = str(p)
    return paths


class Motore:
    def __init__(self, root):
        cv2 = self.cv2 = _cv2()
        m = modelli(root)
        self.det = cv2.FaceDetectorYN.create(m["detector"], "", (320, 320), 0.8, 0.3, 5000)
        self.rec = cv2.FaceRecognizerSF.create(m["recognizer"], "")

    def analizza(self, im):
        rgb = preview(im, 1600)
        bgr = np.asarray(rgb)[:, :, ::-1].copy()
        h, w = bgr.shape[:2]
        self.det.setInputSize((w, h))
        _, faces = self.det.detect(bgr)
        out = []
        for f in (faces if faces is not None else []):
            if f[2] < 24 or f[3] < 24:  # volti troppo piccoli danno impronte inaffidabili
                continue
            crop = self.rec.alignCrop(bgr, f)
            emb = self.rec.feature(crop).flatten()
            emb = emb / (np.linalg.norm(emb) or 1)
            out.append({"box": [round(float(f[0]) / w, 4), round(float(f[1]) / h, 4),
                                round(float(f[2]) / w, 4), round(float(f[3]) / h, 4)],
                        "score": round(float(f[14]), 3),
                        "emb": [round(float(x), 5) for x in emb]})
        return out


def raggruppa(volti, soglia):
    """Raggruppamento greedy per somiglianza coseno. volti: lista di dict con 'emb' e opzionale 'nome'.
    Restituisce la lista dei gruppi (indici). I volti con lo stesso nome finiscono sempre nello stesso gruppo."""
    if not volti:
        return []
    E = np.array([v["emb"] for v in volti], dtype=np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True).clip(1e-6)
    gruppi, centri = [], []
    per_nome = {}
    ordine = sorted(range(len(volti)), key=lambda i: (volti[i].get("nome") is None, -volti[i].get("score", 0)))
    for i in ordine:
        nome = volti[i].get("nome")
        if nome and nome in per_nome:
            g = per_nome[nome]
        else:
            g = None
            if centri:
                sims = np.array(centri) @ E[i]
                j = int(sims.argmax())
                # non unire un volto con nome a un gruppo che ha già un nome diverso
                nome_j = next((volti[k].get("nome") for k in gruppi[j] if volti[k].get("nome")), None)
                if sims[j] >= soglia and (not nome or not nome_j or nome_j == nome):
                    g = j
            if g is None:
                gruppi.append([])
                centri.append(np.zeros_like(E[i]))
                g = len(gruppi) - 1
            if nome:
                per_nome[nome] = g
        gruppi[g].append(i)
        c = E[gruppi[g]].mean(axis=0)
        centri[g] = c / (np.linalg.norm(c) or 1)
    return gruppi


def ritaglio(root, rec, box, size=160):
    im, _ = open_image(master_path(root, rec))
    rgb = preview(im, 1600)
    w, h = rgb.size
    x, y, bw, bh = box
    m = 0.25
    crop = rgb.crop((max(0, (x - bw * m) * w), max(0, (y - bh * m) * h),
                     min(w, (x + bw * (1 + m)) * w), min(h, (y + bh * (1 + m)) * h)))
    crop.thumbnail((size, size))
    return crop
