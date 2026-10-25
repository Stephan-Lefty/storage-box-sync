import time


def test_uneingerichtet(eigene_ablage):
    from storage_box_sync import state
    from storage_box_sync.config import Einstellungen

    z = state.ermittle(Einstellungen())
    assert z.stufe == "uneingerichtet"


def test_fehlender_ordner(einstellungen, eigene_ablage):
    from storage_box_sync import state

    einstellungen.lokal = str(eigene_ablage / "gibt-es-nicht")
    z = state.ermittle(einstellungen)
    assert z.stufe == "fehler"
    assert "nicht vorhanden" in " ".join(z.lang).lower()


def test_fehlende_pruefdatei_ist_ein_fehler(einstellungen):
    from storage_box_sync import state

    z = state.ermittle(einstellungen)
    assert z.stufe == "fehler"
    assert "nicht eingehängt" in z.kurz.lower()


def test_grundlauf_steht_aus(einstellungen):
    from storage_box_sync import state

    (einstellungen.lokal_pfad / einstellungen.pruefdatei).write_text("x")
    z = state.ermittle(einstellungen)
    assert z.stufe == "unbekannt"
    assert "Grundlauf" in z.kurz


def test_guter_und_veralteter_stand(einstellungen):
    from storage_box_sync import state

    (einstellungen.lokal_pfad / einstellungen.pruefdatei).write_text("x")
    einstellungen.grundlauf_erledigt = True

    state.schreibe_lauf("abgleich", 0, time.time() - 30, None, "fertig")
    assert state.ermittle(einstellungen).stufe == "gut"

    # Lauf künstlich altern lassen
    import json

    from storage_box_sync import paths

    daten = json.loads(paths.zustand_datei().read_text(encoding="utf-8"))
    daten["ende"] = time.time() - (state.VERALTET_NACH_STUNDEN + 2) * 3600
    paths.zustand_datei().write_text(json.dumps(daten), encoding="utf-8")

    z = state.ermittle(einstellungen)
    assert z.stufe == "veraltet"
    assert "Stunden" in z.kurz


def test_fehlgeschlagener_lauf_behaelt_letzten_erfolg(einstellungen):
    from storage_box_sync import state

    (einstellungen.lokal_pfad / einstellungen.pruefdatei).write_text("x")
    einstellungen.grundlauf_erledigt = True

    state.schreibe_lauf("abgleich", 0, time.time() - 60, None, "gut")
    state.schreibe_lauf("abgleich", 7, time.time() - 10, None, "kaputt")

    z = state.ermittle(einstellungen)
    assert z.stufe == "fehler"
    assert any("erfolgreich" in zeile for zeile in z.lang)
    assert state.lies_lauf()["letzter_erfolg"]


def test_oertliche_sperre(eigene_ablage):
    from storage_box_sync import state

    assert state.sperre_setzen() is True
    assert state.laeuft_schon() is True
    assert state.sperre_setzen() is False
    state.sperre_loesen()
    assert state.laeuft_schon() is False


def test_verwaiste_sperre_wird_entfernt(eigene_ablage):
    import json

    from storage_box_sync import paths, state

    paths.sperr_datei().write_text(json.dumps({"pid": 999999, "beginn": 0}), encoding="utf-8")
    assert state.laeuft_schon() is False
    assert not paths.sperr_datei().exists()


def test_protokolle_werden_aufgeraeumt(eigene_ablage):
    from storage_box_sync import state

    for nummer in range(45):
        datei = state.neues_protokoll(f"test{nummer:03d}")
        datei.write_text("x")
    state.raeume_protokolle_auf(behalten=10)
    assert len(state.protokolle(500)) == 10
