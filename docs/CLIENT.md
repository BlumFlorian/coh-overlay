# Client – Anforderungen (Stand 2026-11-24)

**Umsetzung:** Stufe 1 (F1–F10) und Stufe 2 (F11–F12) umgesetzt in `tools/client.py`, Datenformat `coh/boardio.py`,
Auswertung `coh/training.py`, Start `Client starten.bat`. Stufe 3 (F13–F14) offen.
Farben: zusätzlich gelernte Farb-Vorlagen (`dataset/client_state.json`), damit die Legende nur einmal benannt werden muss.

Ziel: Das Overlay bekommt ein richtiges Programmfenster (statt Konsole). Es zeigt, **auf welchem
erkannten Brett** ein Vorschlag beruht, und nimmt **Korrekturen** und **Zug-Feedback** auf. Diese
landen als maschinenlesbare Daten in einem Ordner und dienen als Grundlage für Trainings-Sessions
(Regressionstests, Kalibrierung, Verbesserung der Erkennung und des Solvers).

## Rahmen (vom Nutzer festgelegt)
- **Zweiter Monitor:** Das Client-Fenster liegt dauerhaft dort, das Spiel auf dem Hauptmonitor.
  Das Overlay über dem Spiel bleibt wie bisher.
- **Korrektur Feld für Feld:** exakte Soll-Werte, direkt als Testfall nutzbar.
- **Zug-Feedback** gehört in die erste Ausbaustufe.
- **Technik:** PySide6 (Qt).

## Funktionale Anforderungen

### Muss
| Nr | Anforderung |
|----|-------------|
| F1 | **Start per Doppelklick** (`Client starten.bat`). Der Client startet und stoppt das Overlay, zeigt den Status (Spielfenster, Controller, bereit / analysiert / Vorschlag in X s) und das Log (ausklappbar). |
| F2 | **Brett-Ansicht** der neuesten Analyse, live aktualisiert: beide Seiten als 8×6-Raster mit Typ, Farbe, Stärke, Ladezeit, Wand-HP; mehrfeldrige Pieces (Elite 1×2, Champion 2×2, Formationen) als ein Block. Unsichere Felder markiert. |
| F3 | **Screenshot daneben** (zoombar), Raster darübergelegt umschaltbar – zum direkten Vergleich. |
| F4 | **Kopfwerte:** Züge, Reserve, HP beider Seiten, Magie beider Seiten, Kontingent – alle korrigierbar. |
| F5 | **Plan-Anzeige:** Aktionen, „Warum“, Folgezug-Vorschau, Hinweise „Unsicher“. |
| F6 | **Farb-Legende:** Die Klassen (a, b, c …) sind je Analyse beliebig benannt. Der Client zeigt je Klasse ein Beispielbild; der Nutzer benennt die echte Farbe (z. B. Gold/Blau/Weiß). Korrekturen speichern echte Farben, nicht Buchstaben. |
| F7 | **„Brett falsch“:** Klick auf ein Feld → Dialog: leer / Einheit / Elite / Champion / Wand / ladende Formation / unbekannt; Einheitentyp, Farbe, Stärke, Ladezeit, Wand-HP, Größe. Mehrere Felder nacheinander, dann speichern. Freitext-Notiz. |
| F8 | **„Vorschlag schlecht“:** Markieren, optional den besseren Zug eingeben (Aktionen per Klick: Spalte → Spalte, Löschen Feld, Verstärkung, Zauber) und/oder Freitext („erst platzieren, dann löschen“). |
| F9 | **Speichern** je Meldung in `dataset/corrections/<Zeit>/`: Screenshot(s), `erkannt.json`, `korrigiert.json` (nur bei Brett-Korrektur), `zug.json` (nur bei Zug-Feedback), `notiz.txt`. |
| F10 | **Verlauf:** frühere Analysen durchblättern, nachträglich korrigieren (z. B. nach dem Spiel). Bereits gemeldete Analysen erkennbar. |

### Soll
| Nr | Anforderung |
|----|-------------|
| F11 | **Einstellungen** im Fenster (Zauber, Rechenbudget, Vorausschau, Halte-Dauer), gespeichert. |
| F12 | **Trainings-Ansicht:** alle Korrekturen gegen die aktuelle Erkennung laufen lassen → Trefferquote je Merkmal (Typ, Farbe, Wand-HP, Ladezeit, Kopfwerte) und Liste der Abweichungen. |

### Kann (später)
| Nr | Anforderung |
|----|-------------|
| F13 | Korrekturen automatisch als Regressionstests (`tests/test_corrections.py`). |
| F14 | Zug-Feedback als Solver-Testfälle: Solver soll den Nutzerzug mindestens gleich gut bewerten. |

## Nicht-funktionale Anforderungen
- **Bann-sicher:** weiterhin nur Bildschirm lesen, keine Eingaben ans Spiel.
- **Keine Verlangsamung:** Analyse-Zeit bleibt gleich (Client läuft in eigenem Prozess).
- **Robust:** Absturz des Clients beendet nicht das Overlay und umgekehrt.
- **Lokal:** keine Netzwerkzugriffe, alle Daten unter `dataset/` (nicht im Git).
- **Deutsch**, Windows, Start per Doppelklick; bestehende `.bat` bleiben nutzbar.
- **Wartbar:** Datenformat versioniert (`"format": 1`), Brett-JSON aus denselben Klassen wie der Solver (`coh/model.py`).

## Architektur (Vorschlag)
- **Zwei Prozesse:** Client (Qt) startet das Overlay (Tk, unverändert) als Unterprozess und liest
  dessen Log. Qt und Tk im selben Prozess wären fehleranfällig.
- **Austausch über Dateien:** Das Overlay speichert je Analyse zusätzlich `<Zeit>.json`
  (erkanntes Brett, Kopfwerte, Unsicherheiten, Plan, Klassen-Beispielausschnitte). Der Client
  beobachtet `dataset/analysis/` und zeigt die neueste Analyse. Ältere Analysen ohne JSON werden
  bei Bedarf aus dem Screenshot nacherkannt.
- **Datenformat Brett** (`erkannt.json` / `korrigiert.json`):
  `{"format": 1, "bild": "...png", "kopf": {...}, "ich": [Piece...], "gegner": [Piece...],
  "farben": {"a": "Gold", ...}}` mit Piece = `kind, col, row, w, h, unit, color, hp, ct, power`.

## Ausbaustufen
1. Overlay schreibt Analyse-JSON; Client mit F1–F10.
2. F11–F12 (Einstellungen, Trainings-Ansicht).
3. F13–F14 (automatische Tests aus Korrekturen).
