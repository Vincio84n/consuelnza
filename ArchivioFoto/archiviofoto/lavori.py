"""Esecuzione dei comandi dalla webapp, uno alla volta, con avanzamento e log in tempo reale."""
import contextlib
import re
import threading
import time

AVANZA = re.compile(r"^\s+\S+-R\d{3}-F\d+")


class _Scrittore:
    def __init__(self, stato):
        self.stato, self.buf = stato, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            riga, self.buf = self.buf.split("\n", 1)
            self.stato["righe"].append(riga)
            if AVANZA.match(riga):
                self.stato["fatti"] += 1
        return len(s)

    def flush(self):
        pass


class Lavori:
    def __init__(self):
        self.lock = threading.Lock()
        self.stato = {"attivo": False, "titolo": "", "righe": [], "fatti": 0, "totale": 0, "codice": None, "inizio": 0, "fine": 0}

    def avvia(self, titolo, comandi, totale=0):
        """comandi: lista di argv per cli.main, eseguiti in sequenza (si ferma al primo errore)."""
        if not self.lock.acquire(blocking=False):
            return False
        self.stato.update(attivo=True, titolo=titolo, righe=[], fatti=0, totale=totale, codice=None, inizio=time.time(), fine=0)

        def esegui():
            from .cli import main
            w = _Scrittore(self.stato)
            codice = 0
            try:
                with contextlib.redirect_stdout(w), contextlib.redirect_stderr(w):
                    for argv in comandi:
                        print("$ archivio " + " ".join(argv))
                        codice = main(argv)
                        if codice:
                            break
                    w.write("\n")
            except Exception as e:  # main gestisce già gli errori: qui solo l'imprevisto del runner
                self.stato["righe"].append(f"ERRORE del gestore lavori: {e}")
                codice = 2
            finally:
                self.stato.update(attivo=False, codice=codice, fine=time.time())
                self.lock.release()

        threading.Thread(target=esegui, daemon=True).start()
        return True

    def istantanea(self):
        s = dict(self.stato)
        s["righe"] = s["righe"][-300:]
        return s
