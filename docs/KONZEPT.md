# CoH Move Advisor: Konzept

Ziel: ein Overlay, das in Might & Magic: Clash of Heroes – Definitive Edition (Steam, App 2213300)
für die aktuelle Runde die beste Zugfolge anzeigt. Die Züge führt der Spieler selbst aus.

## 1. Grundsatz: nicht bannbar durch Design

Das Tool **berührt das Spiel technisch überhaupt nicht**. Es sieht nur, was auch auf dem Monitor zu sehen ist.

| Erlaubt (macht das Tool) | Tabu (macht das Tool nie) |
|---|---|
| Bildschirmaufnahme über die offizielle Windows-API (Windows Graphics Capture / DXGI Desktop Duplication) | Prozessspeicher lesen oder schreiben (`ReadProcessMemory`) |
| Eigenes, separates Fenster: transparent, click-through, always-on-top. Alternativ auf einem zweiten Monitor. | DLL-Injection, Hooks in DirectX/OpenGL, Modding der Spieldateien |
| Der Spieler klickt selbst | Maus- oder Tastatureingaben automatisieren (Bot) |
| Läuft als normaler User-Prozess | Netzwerkverkehr mitschneiden oder manipulieren, Admin-/Treiber-Komponenten |

Warum das sicher ist:
- Ein Anti-Cheat wie VAC (für das Original-Spiel gelistet, für die DE unbestätigt) erkennt Cheats an Eingriffen in den Spielprozess: Injection, Speicherzugriffe, bekannte Signaturen. Ein externer Prozess, der nur den Desktop aufnimmt, unterscheidet sich technisch nicht von OBS oder Discord-Streaming.
- Ohne Eingabe-Automatisierung gibt es kein auffälliges Klickmuster.
- Restrisiko: Nicht technisch, sondern über die Nutzungsbedingungen. Externe Hilfsmittel in Ranked/Online-PvP verstoßen meist gegen die ToS, auch wenn sie nicht erkennbar sind.
  **Empfehlung: im Tool einen Schalter „nur Kampagne/Puzzles/Offline“ als Standard.** Online-Spiele gegen Menschen sind damit unfair gegenüber dem Gegner.

## 2. Architektur

```
┌──────────────┐  Frames  ┌────────────────┐  Board-State  ┌─────────────┐  Zugfolge  ┌───────────┐
│ Capture      │ ───────▶ │ Board-Erkennung│ ────────────▶ │ Solver      │ ─────────▶ │ Overlay   │
│ (WGC, ~5 fps)│          │ (Template/CNN) │   (JSON)      │ (Suche+Eval)│            │ (Pfeile)  │
└──────────────┘          └────────────────┘               └─────────────┘            └───────────┘
                                   ▲                              ▲
                          Kalibrierung (Raster,          Datenbank (units.json,
                          Sprites, Zahlen-OCR)           artifacts.json, heroes.json)
```

Vorgeschlagener Stack: **Python** für Prototyp, Erkennung und Overlay (`windows-capture` oder `dxcam`, OpenCV, PySide6),
den Solver später bei Bedarf in **Rust** (über PyO3), falls Python zu langsam ist.

### 2.0 Setup-Entscheidung
- Das Spiel läuft **borderless** auf dem Hauptmonitor, Overlay bzw. Berater-Fenster auf dem **zweiten Monitor**.
  Borderless lässt sich zuverlässig aufnehmen. Exklusives Vollbild kann bei der Aufnahme schwarze Bilder liefern und Overlays verdecken.
- Einsatz: Kampagne/offline und online nur gegen den Freund. Am besten sagt man ihm vorher Bescheid, dann ist es fair und ein guter Showcase.

### 2.1 Capture
- Das Spielfenster wird über den Fenstertitel gefunden und nur dieses Fenster aufgenommen (WGC). Die Aufnahme läuft im Fenster- oder Borderless-Modus.
- Analysiert wird nur, wenn sich das Bild stabilisiert hat, also keine Animation mehr läuft (Frame-Diff < Schwelle).

### 2.2 Board-Erkennung
Pro Feld wird erkannt:
- Leer, Core, Elite-Teil, Champion-Teil, Wand oder ladende Formation
- Einheitentyp und Farbe. Die Farbe ist ein Tint auf demselben Sprite, also Typ per Template-/Feature-Match und Farbe per Hue-Histogramm.
- Zahlen per OCR auf kleinen, festen Ziffern-Templates (ohne Tesseract): Ladezeit und Stärke bei Formationen, Wand-HP, Helden-HP, MP, verbleibende Züge, Reserve-Zähler.

Erkannt werden beide Feldhälften, die gegnerische ist für die Schadensberechnung nötig.
Ergebnis ist ein `BoardState`-JSON. Ein Debug-Fenster zeigt die Erkennung an, damit man Fehler sofort sieht.

### 2.3 Kalibrierung (gleichzeitig Datenquelle)
Die DE ist rebalanced, deshalb sollen die Einheitenwerte **aus dem Spiel selbst** kommen:
1. Raster-Kalibrierung: Der Nutzer klickt einmal die Ecken beider Spielfelder an. Das wird pro Auflösung gespeichert.
2. Sprite-Sammlung: Ein „Lernmodus“ speichert Feldausschnitte. Der Nutzer labelt sie einmal (Typ/Farbe), das sind etwa 15 Einheiten pro Fraktion.
3. Werte-Import: Im Spiel gibt es eine Einheitenübersicht (Truppenindex mit Angriff, HP, Ladezeit). Das Tool liest diese Seiten per OCR ein und schreibt `units.json`. Fehlende Werte trägt man von Hand nach.

### 2.4 Spielmodell (Simulator)
Ein deterministischer Simulator der eigenen Runde:
- `apply(move)` mit `move ∈ {Move(src, dst), Delete(cell), Reinforce, CastSpell}`
- Danach folgt die Auflösung: Schwerkraft und Nachrutschen, Formationserkennung (senkrecht 3 = Angriff, waagerecht 3 = Wand, Elite/Champion-Muster),
  Sortierung (Wände vorn, dann Formationen, dann Idle), Fusion, Chain-Erstattung, Combos.
- `end_turn()` lädt die Formationen und löst Angriffe aus, die bei 0 sind. Dann wird die Spalte des Gegners aufgelöst:
  Angriff minus Toughness bzw. Stärke jedes Blockers, nacheinander, der Rest trifft den Helden. Link-Bonus und Spezialeffekte werden angewendet.
- Spezialfähigkeiten und Artefakte sind **Hooks** (`on_launch`, `on_charge_tick`, `on_hit`, `on_death`, `modify_power` …), datengetrieben aus JSON.
  Neue Einheiten oder Artefakte brauchen so keinen Solver-Umbau.

### 2.5 Solver
- Es wird die eigene Runde mit 3 (±) Aktionen durchsucht. Die Verzweigung liegt bei etwa 8×7 Moves + ≤48 Deletes + Reinforce, also ~100 pro Aktion und ~10⁶ Sequenzen für 3 Aktionen.
  Machbar mit Transpositionstabelle, denn viele Zugreihenfolgen führen zum selben Zustand, und Pruning: Chains verlängern die Suche, sinnlose Deletes fallen weg.
- **Bewertung** als gewichtete Summe:
  - Erwarteter Schaden am Helden, gewichtet nach Ladezeit (sofort > in 2 Runden), inklusive Link- und Fusionsbonus
  - Abgefangener Schaden: Wie gut blocken eigene Wände und Formationen die gegnerischen Angriffe, die bald starten? Dafür wird die gegnerische Seite simuliert.
  - Bedrohte eigene Formationen, also solche, die getroffen werden, bevor sie fertig sind
  - MP-Gewinn, Reserve und Board-Potenzial (Fast-Formationen: 2 gleiche übereinander)
  - Tödliche Linie: Gewinnt eine Zugfolge sicher, gilt Score = ∞
- Optional: Für die Gegnerrunde 1-Ply „Worst-Case“-Antwort (Expectimax ist wegen Zufalls-Verstärkungen schwer, daher nur Heuristik).
- Die Gewichte sind konfigurierbar und werden später per Selbstspiel im Simulator getunt.

### 2.6 Overlay
- Das Fenster ist rahmenlos, transparent und click-through (`WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST`). Es zeichnet **nur in seinem eigenen Fenster**, nicht im Spiel.
- Anzeige: nummerierte Pfeile „1 → 2 → 3“ auf dem Raster, X für Löschen, Text mit erwartetem Schaden.
  Darunter stehen die Top-3-Alternativen per Hotkey sowie eine Gefahrenanzeige für gegnerische Spalten, die bald zuschlagen.
- Hotkeys über die globale Hotkey-API (nur Tastatur des Tools, nichts wird ans Spiel gesendet): Analysieren, Alternativen wechseln, Overlay aus.
- Fallback „Second Screen“: dasselbe Bild als normales Fenster auf einem zweiten Monitor. Das ist noch weiter vom Spiel entfernt.

## 3. Meilensteine

1. **Simulator + Solver offline**: Board-State per Hand eingeben, Regeln anhand von 10–20 Screenshots echter Situationen verifizieren. Battle-Puzzles aus der Kampagne sind ideale Testfälle, weil sie eine eindeutige Lösung haben.
2. **Erkennung**: Screenshot → BoardState mit >99 % Feldgenauigkeit
3. **Live-Capture + Overlay**
4. **Datenimport** aus dem Truppenindex, Artefakte und Heldenzauber als Hooks
5. **Tuning** der Gewichte

## 4. Offene Punkte / Daten, die fehlen
Siehe DATEN.md (❌ und ⚠️). Insbesondere:
- Einheitenwerte (Angriff, Toughness, Ladezeit, Größe, Stärkezuwachs pro Ladezeit-Runde)
- Exakte Formeln für Link-Bonus, Fusionsbonus, Combo und Chain
- Heldenzauber und -passive (15 Helden in der DE)
- Rastergröße und Basis-Züge pro Runde in der DE

## 5. Andere Fraktionen, ohne Haven zu verschlechtern

Stand 2026-11-13: Erkennung und Regeln sind an Haven-Kämpfen (Ritter) entwickelt und getestet. Ein großer Teil ist aber fraktionsunabhängig und muss nicht neu gebaut werden.

**Schon allgemein (gleiche UI für alle):** Raster und Geometrie, Herz-Symbol und Toughness-Zahl, Wand-Symbol, Ladebalken samt Füllstandsmarke und Cursor-Vorschau, Zuganzeige, Reserve-Zähler, Kontingent-Kästen (gleiche Schrift), HP-Balken und Zauberleisten. Die Einheiten-Klassen (A/B/C …) lernt die Asset-Bibliothek nach Aussehen, nicht nach Haven-Vorlagen.

**Fraktionsabhängig, offen:**
1. **Fraktion erkennen.** Bisher ist fest angenommen: ich Haven, Gegner Necropolis (`Hero`-Standard und `vision.analyze`). Heute war der Gegner aber Inferno. Das betrifft Wandwerte und Wandregeln (Sylvan regeneriert, Inferno brennt, Academy wächst, Necropolis hinterlässt Knochenwände). Lösung: Fraktion aus dem Helden-Porträt oder den Icons im Kontingent-Kasten erkennen, mit je einer Vorlage pro Held bzw. Einheit.
2. **Tier-Schwellen.** Elite/Champion werden an der Toughness erkannt (Core ≤ 3, Champion ≥ 10). Das passt für fast alle Einheiten, aber nicht für Wraith auf niedrigem Level (Toughness 4). Für die Grenzfälle zusätzlich die Größe des Pieces nutzen.
3. **Sondereffekte auf dem Brett:** Einhorn-Aura, Djinn-Eis (gefrorene Einheiten), Säure des Emerald Dragon, brennende Leichen (Pit Fiend), eingegrabene Treants, Knochenwände. Jeder Effekt bekommt eine eigene, abschaltbare Erkennung, die nur für die passende Fraktion aktiv ist.
4. **Spezialfähigkeiten im Simulator:** Viele sind in DATEN.md beschrieben, aber noch nicht umgesetzt.

**Damit Haven nicht schlechter wird:**
- **Regressionstests mit echten Aufnahmen:** Für einen festen Satz Haven-Aufnahmen wird die erkannte Belegung als „Soll“ gespeichert, mit manuell geprüften Stellen. Jede Änderung an der Erkennung muss diese Tests weiter bestehen. Neue Fraktionen bekommen ihren eigenen Satz.
- **Vorlagen und Schwellen pro Fraktion** in eigenen Dateien (z. B. `coh/data/<fraktion>/`), mit den heutigen Werten als Haven-Standard. Gemeinsames (Schrift, Balken, Symbole) bleibt an einer Stelle.
- **Replay-Bericht pro Fraktion** (`tools/replay.py`): Wiederkehrende Abweichungen zeigen, wo eine Regel oder Erkennung für diese Fraktion nicht passt.
