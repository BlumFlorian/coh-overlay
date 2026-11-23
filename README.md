# CoH Move Advisor

Zug-Berater als Overlay für *Might & Magic: Clash of Heroes – Definitive Edition* (Steam, Windows).

Im eigenen Zug **L1** halten: Das Tool liest das Spielfeld vom Bildschirm, simuliert die möglichen Züge und zeichnet den besten Vorschlag als Pfeile und Kreuze über das Spiel – samt kurzer Begründung („Warum: Elite aktiviert, Schaden am Gegner +41“).

- **Rein lesend:** nur Bildschirmaufnahmen und Controller-Eingaben abfragen, kein Eingriff in Spiel oder Speicher.
- **Ganzheitlich:** Chains und Combos, Elite/Champion-Aktivierung (auch über zwei Züge), gebundene Angriffe, Wände, Verstärkung, Kontingent, Holy Shield, Vorausschau auf den nächsten Zug.
- **Ehrlich:** Was die Erkennung nicht sicher weiß, steht als „Unsicher“, gleichwertige Alternativen als „Knapp“.

Konzept: [`docs/KONZEPT.md`](docs/KONZEPT.md), Spieldaten und geprüfte Regeln: [`docs/DATEN.md`](docs/DATEN.md).

> Fan-Projekt ohne Verbindung zu Ubisoft oder Dotemu. Getestet mit Haven (Godric) bei 1920×1080.

## Setup (einmalig)

Voraussetzung: Windows 10/11 und Python 3.12.

```powershell
git clone https://github.com/BlumFlorian/coh-overlay.git
cd coh-overlay
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Danach per Doppelklick starten: **`Overlay starten.bat`** (Zugvorschläge) bzw. **`Replay auswerten.bat`** (Vorhersage gegen Wirklichkeit).

## 1. Daten sammeln (L1-Modus)

```powershell
.venv\Scripts\python tools\capture.py
```

- Läuft im Hintergrund. Das Spiel am besten **borderless** auf dem Hauptmonitor laufen lassen, das Terminal auf dem zweiten Monitor.
- Im Kampf **L1** drücken (oder **F9**). Gespeichert werden zwei Bilder: `*_board.png` (normales Brett) und 0,6 s später `*_info.png` (Werte-Ansicht).
- Ablage: `dataset\<Datum>\`. Wenn die Werte-Ansicht langsamer einblendet, `--delay 1.0` verwenden.
- `--learn` zeigt die gedrückten Controller-Tasten, `--test` macht ein einzelnes Testbild.

Ideal sind möglichst unterschiedliche Situationen: alle Fraktionen, Elite und Champions, ladende Formationen, Wände, beide Seiten.
Damit werden die Werte in `coh/data/units.json` verifiziert und die Bilderkennung (Meilenstein 2) trainiert.

## 2. Overlay (Zugvorschläge live)

```powershell
.venv\Scripts\python tools\overlay.py
```

- Im eigenen Zug **L1 halten** (ca. 0,5 s). Das Tool fotografiert die Werte-Ansicht, erkennt das Brett und zeichnet den Vorschlag über das Spiel:
  nummerierte Pfeile (Einheit von Spalte X nach Spalte Y), rote Kreuze (löschen), oben links eine kompakte Karte „Dein Zug“ mit nur den Schritten des aktuellen Zuges (plus Warnung, wenn ein Kontingent fast leer ist).
- Alles Weitere (Kontingent, Zauber, Vorschau auf den nächsten Zug, „Unsicher“, „Knapp“) steht in der Konsole und in der Analyse-Datei.
- Oben rechts stehen klein Tipps für das L1-Halten (Liste `TIPS` in `tools/overlay.py`).
- **Unsicher / Knapp:** Was die Erkennung nicht sicher weiß, steht als „Unsicher: …“ in Konsole und Analyse-Datei (unbekannte Felder, Farbe eines Champions unter dem Cursor, mögliche gegnerische Links, nicht gelesene Anzeigen). Liegen die zwei besten Pläne fast gleichauf, steht die Alternative als „Knapp“ daneben, und du entscheidest. Beides landet in der Analyse-Datei und im Replay-Bericht.
- **R1** blendet das Overlay ein und aus. Auf der Tastatur gilt **F8** = analysieren (nur bei offener Werte-Ansicht) und **F7** = ein/aus.
- Aus der Spielanzeige gelesen: wer am Zug ist, die verbleibenden Züge (Emblem unter der Cursor-Spalte) und beide Reserve-Zähler.
  Unbekannte Ziffern der Zuganzeige landen in `dataset\glyphs\` und werden als Vorlage nachgetragen (`coh\data\move_glyphs\<ziffer>_<n>.png`).
- **Kontingent:** Bei jeder Analyse werden die Kästen mit den Elite- und Champion-Zahlen beider Spieler gelesen („aktuell/max“, meiner oben links, der des Gegners unten rechts) und über die Analysen hinweg verfolgt (`coh/stock.py`). Die Zahlen sinken nur, wenn eine Einheit stirbt, also idle getroffen oder beim Laden vernichtet; Angreifen kostet nichts. Der Solver bewertet solche Verluste umso teurer, je weniger übrig sind, und den Verlust des letzten Exemplars mit einem großen Zuschlag. Für gegnerische Verluste gilt dasselbe als Gewinn. Ab einem Rest von 1 erscheint im Overlay eine Warnung.
- **Vorausschau auf den nächsten eigenen Zug:** Die besten Kandidaten (`--lookahead 8`, 0 = aus) werden inklusive des besten eigenen Folgezugs bewertet. So zählen Vorbereitungen, die sich erst einen Zug später auszahlen, etwa ein Champion, der nur in zwei Zügen aktivierbar ist. Der Folgezug steht als „Nächster Zug (Vorschau)“ in Konsole und Analyse-Datei. Reines Löschen ohne Chain wird als letzte Aktion eines Zuges mit betrachtet. Ein vorhergesagter Sieg nach dem nächsten Gegnerzug zählt nur als großer Bonus, nicht als sicher, weil die Simulation keine Gegnerzüge kennt.
- **Gesamtabwägung:** Ein Sieg im nächsten Zug wiegt jede Kombination aus Einheitenverlusten auf (`win_value`), ein späterer Sieg zählt weniger (`end_decay`), weil der Gegner mehr Züge zum Reagieren hat. Für die eigene Niederlage gilt dasselbe spiegelbildlich. Fremde Einheiten in den zwei Reihen hinter einer idle Elite oder einem idle Champion zählen als „verschüttet“ (`bury_*`). Bei der Verstärkung werden die Farben umgekehrt zur Häufigkeit auf dem Feld gewürfelt. Elites und Champions fallen mit: pro Abwurf mit `ht_drop_base` × Anteil freier Felder (Schalter in `units.json`), nur wenn sie passen (1×2 bzw. 2×2 frei), noch im Kontingent sind und die Obergrenze (4 Elites / 2 Elites + 1 Champion / 2 Champions) es zulässt. Was hinter Elites und Champions fällt, wird über 32 Würfe gemittelt.
- **Champions aktivieren, auch über zwei Züge:** Für jede idle Elite und jeden idle Champion schätzt der Solver, wie viele Aktionen bis zur Aktivierung fehlen (`activation_cost` in `coh/solver.py`). Dazu zählen Löschungen davor, wenn er zu weit hinten steht, fremde Einheiten dahinter und gleichfarbige Core, die aus anderen Spalten geholt werden müssen (samt Freiräumen). Je weniger fehlt, desto mehr zählt er (`reach_*`, bis 2 Züge voraus). Reine Löschungen, die einen Champion näher an die Aktivierung bringen, sind jederzeit erlaubt, auch mehrere hintereinander. Pläne, nach denen im nächsten Zug aktiviert werden kann, kommen immer in die Vorausschau. Reicht das Rechenbudget nicht für alle Züge, werden die besten Pläne gierig zu Ende gespielt, damit der dritte Zug nicht fehlt.
- **Kettenreaktionen und Combos:** Entstehen durch eine Bewegung gleichzeitig Formation und Wand (oder mehrere Formationen), gibt jede weitere einen Zug zurück. Alles, was danach durch Nachrutschen entsteht, und jede Formation oder Wand nach einer Löschung zählen ebenso. Das ist in der Suche enthalten, und das Overlay zeigt es als „(Chain +N)“.
- **Magieanzeige:** Gelesen wird sie aus der Anzeige. Simuliert wird, was sie füllt: Extrazüge durch Chains und Combos, Fusionen, ungenutzte Züge beim Beenden (je ca. 3 %), Schaden (der Getroffene bekommt mehr) und gebundene Angriffe. Alle Werte sind geschätzt und als Schalter in `units.json` hinterlegt (`mp_*`). In der Bewertung zählt sie nur wenig (`mp`), weil Heldenzauber noch nicht simuliert werden.
- **Heldenzauber (Godric, Holy Shield):** Bei voller Leiste ist „Heldenzauber (Y)“ eine kostenlose Aktion. Der Schild hat 50 % der Max-HP und hält eine Gegnerrunde. Er schützt nur die Helden-HP, denn Angriffe gehen erst durch deine Einheiten. Danach geht der Rest ×2 front-to-back auf den Gegner, gleichmäßig auf alle Spalten verteilt (Schalter `holy_shield_*` in `units.json`). Eine volle Leiste aufzuheben hat einen eigenen Wert (`spell_ready`), der Zauber muss ihn schlagen. Mit `--spell ""` plant das Overlay keinen Zauber ein.
- Elite und Champions werden nie zum Löschen vorgeschlagen. Ihre Aktivierung wird bevorzugt: Passende Core-Einheiten dahinter zählen als Vorbereitung, und Angriffe, die erst nach dem Vorausschau-Horizont starten (Angel CT 6), werden mitbewertet.
- Mögliche Schritte: Bewegen (auch Elite 1×2 und Champion 2×2), Löschen mit Chain, **Verstärkung rufen** (danach L1 neu halten, weil der Fall zufällig ist), **Zug beenden** für MP.
- Das Ergebnis ist deterministisch: Gleiches Brett ergibt gleichen Vorschlag (feste Seeds, festes Rechenbudget `--nodes`, Mittel über `--frames` Bilder). Die Cursor-Zelle wird erkannt und als unbekannt behandelt.
- Jede Analyse wird unter `dataset\analysis\` gespeichert (Bild, Debug-Bild mit erkannten Klassen, Vorschlag).
- Das Overlay ist für Bildschirmaufnahmen unsichtbar, also auch für OBS und Discord.
- Test ohne Spiel: `.venv\Scripts\python tools\analyze_image.py <bild>_info.png --solve`

Stand: Erkannt werden idle Grundeinheiten (in Klassen a, b, c … nach Aussehen), Wände, ladende Formationen und Elite/Champions (als Blocker).
Vorgeschlagen werden nur Züge mit Grundeinheiten (Bewegen, Löschen mit Chain, Formationen, Wände, Fusion).

## 2b. Replay-Auswertung (Vorhersage gegen Wirklichkeit)

Doppelklick auf `Replay auswerten.bat` oder:

```powershell
.venv\Scripts\python tools\replay.py                 # alle Aufnahmen in dataset\analysis
.venv\Scripts\python tools\replay.py --day 20261113  # nur ein Tag
```

- Erkennt alle gespeicherten L1-Analysen neu (die Asset-Bibliothek wird dabei nur gelesen) und gruppiert sie zu Kämpfen und Zügen.
- Für zwei aufeinanderfolgende eigene Züge wird der erste eine Runde weitersimuliert und mit dem zweiten verglichen: Heldenschaden, Formationen (abgefeuert, lädt weiter, weg) und Kontingent.
- Bericht: `dataset\replay\bericht_<Zeit>.md`, mit Zusammenfassung, offenen Fragen (Unsicherheiten der Erkennung) und den einzelnen Abweichungen.
- **Am aussagekräftigsten**, wenn du zu Beginn jedes eigenen Zuges L1 hältst. Fehlen Runden, sind die Vergleiche nur grob.
- Abweichungen sind Hinweise, keine Beweise: Dazwischen liegen deine und die gegnerischen Züge. Was sich wiederholt, zeigt eine falsche Regel oder einen Erkennungsfehler.

## 3. Solver mit eingetipptem Brett

```powershell
.venv\Scripts\python -m coh.cli examples\beispiel1.txt          # Top-3-Vorschläge
.venv\Scripts\python -m coh.cli examples\beispiel1.txt --steps  # Brett nach jedem Schritt
```

Das Brettformat ist in `examples/beispiel1.txt` und in `coh/model.py` beschrieben.

## Rechenzeit

- Eine Analyse dauert etwa 5–12 Sekunden (vorher 12–24). Die Kandidaten der Vorausschau laufen im Overlay parallel auf mehreren Kernen (Prozess-Pool aus der Standardbibliothek). Das Ergebnis ist identisch zur seriellen Rechnung.
- Seit 2026-11-23 spielt der Solver die besten unfertigen Plaene (je erstem Zug) bis zum letzten Zug aus und haengt geplante Folgezug-Aktionen an, wenn Zuege uebrig blieben. Das kostet etwa 2-4 Sekunden mehr, dafuer bleiben keine Zuege mehr ungenutzt, die Chains freigeschaltet haben.
- Das Overlay zeigt unter dem Plan eine Zeile „Warum:“ (Wirkung gegenüber sofort Zug beenden, 5 Runden simuliert). Seit 2026-11-23 wird auch „zuerst Verstärkung rufen“ bewertet (4 Würfe, danach kleine Suche).
- Parallel rechnet nur, wer es mit `solve(..., parallel=True)` anfordert, und das tut nur das Overlay. Grund: Unter Windows laden die Hilfsprozesse das Startskript neu. Eigene Skripte mit `parallel=True` brauchen deshalb `if __name__ == "__main__":`.
- `COH_WORKERS=1` schaltet das Parallelisieren ab, `COH_WORKERS=4` begrenzt es auf 4 Prozesse. Geht mit dem Pool etwas schief, rechnet der Solver automatisch seriell weiter.
- Schneller, aber mit weniger Qualität: `--lookahead 4` oder `--lookahead 0` (keine Vorausschau).

## Tests

```powershell
.venv\Scripts\python -m pytest -q
```

## Struktur

| Datei | Inhalt |
|---|---|
| `coh/data/units.json` | Einheitenwerte, Wand-Werte und unsichere Regeln als Schalter |
| `coh/model.py` | Brett, Pieces, Text-Format |
| `coh/rules.py` | Simulator: Züge, Formationen, Wände, Chains, Fusion, Laden, Links, Angriffe, einige Spezialfähigkeiten |
| `coh/solver.py` | Beam-Suche über die eigenen Aktionen, Bewertung durch Simulation über 5 Runden |
| `tools/capture.py` | L1/F9-Screenshot-Sammler (rein passiv) |

## Noch nicht im Simulator

Heldenzauber außer Godrics Holy Shield (gegnerische Zauber gar nicht), die meisten Elite- und Champion-Spezialfähigkeiten
(umgesetzt sind Spearman, Druid, Zombie, Vampire, Ghost und Bone Dragon) sowie die meisten Artefakte.
Gegnerzüge werden nicht vorhergesagt, nur seine bereits ladenden Angriffe.
