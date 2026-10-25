import pytest


class PortachiaviFinto:
    def __init__(self):
        self.d = {}

    def get_password(self, s, u):
        return self.d.get((s, u))

    def set_password(self, s, u, p):
        self.d[(s, u)] = p

    def delete_password(self, s, u):
        del self.d[(s, u)]


@pytest.fixture(autouse=True)
def isolamento(monkeypatch, tmp_path):
    """Mai toccare il portachiavi o le preferenze reali del computer che esegue i test."""
    from archiviofoto import chiavi
    finto = PortachiaviFinto()
    monkeypatch.setattr(chiavi, "_keyring", lambda: finto)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    for var in ("APPDATA", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(var, str(tmp_path / "utente"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ARCHIVIOFOTO_RELEASE_URL", "http://127.0.0.1:9/nessuno")  # niente rete reale
    return finto
