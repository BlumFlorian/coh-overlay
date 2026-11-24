# Clash of Heroes: Gesammelte Spieldaten

Stand: 2026-11-12. Legende: ✅ belegt (mit Quelle), ⚠️ unbestätigt oder Quellen widersprechen sich, im Spiel prüfen, ❌ fehlt noch.

Quellenkürzel:
- **FW** = Fandom-Wiki (Infoboxen der Einheitenseiten, PC/HD-Werte)
- **BB** = GameFAQs-Strategy-Guide von Blackbird (DS, alle Werte auf Einheiten-Level 5, „Quick Battle“)
- **WT** = GameFAQs-Walkthrough 63331 (HD-Version, Battle-Basics-Abschnitt)
- **DE** = offizielle Dotemu-Ankündigungen zur Definitive Edition auf Steam (Mai bis Juli 2023)
- **GP** = Gamepressure-Guide

> **Wichtig:** Die DE weicht an mehreren Stellen vom DS-Original ab (siehe Abschnitt 6).
> Maßgeblich bleiben die Werte im Spiel, siehe KONZEPT.md, Abschnitt „Kalibrierung“.
> Die Tabellen hier sind Startwerte für den Simulator, keine endgültige Wahrheit.

## 1. Kernmechaniken

| Regel | Inhalt | Status |
|---|---|---|
| Spielfeld | Pro Seite **8 Spalten × 6 Reihen**. Der Gegner ist oben, man selbst unten. Dahinter liegt die Heldenzone. | ✅ BB |
| Züge pro Runde | Normalerweise **3**. Celerity Ring gibt +1. | ✅ FW („generally three“), GP |
| Bewegen | Nur die hinterste Einheit einer Spalte darf genommen und auf eine andere Spalte gesetzt werden. Kostet 1 Zug. | ✅ GP |
| Angriffsformation | Core: 3 gleiche Einheiten gleicher Farbe senkrecht. Elite (1×2): 2 gleichfarbige Core dahinter. Champion (2×2): 4 gleichfarbige Core dahinter (2×2). | ✅ FW, BB |
| Formationen steigen auf | Neue Formationen und Wände rücken an die Front (zum Gegner hin). Idle-Einheiten darunter rutschen nach hinten. | ✅ BB, FW |
| Wand | 3 oder mehr gleichfarbige Core-Einheiten waagerecht. Wandsegmente gehen nach vorn. Eigene Angriffe gehen durch, gegnerische werden geblockt. Elite und Champion bilden keine Wände. | ✅ FW |
| Wand-Fusion | Zwei Wandsegmente in derselben Spalte verschmelzen **einmal** zu einer dicken Wand. Ein drittes Segment entsteht dahinter als eigene Wand. Auch teilweise überlappende Segmente verschmelzen. | ✅ FW, WT |
| Löschen / Chain | Eigene Einheit oder Wand entfernen kostet 1 Zug. Jede dadurch entstehende Formation oder Wand gibt **+1 Zug**. Mehrere Chains in einem Zug ergeben also Netto-Gewinn. Es gibt kein Limit pro Runde. | ✅ FW (Chain) |
| Fremde Züge als Chain | Rutschen eigene Einheiten durch einen gegnerischen Angriff oder das Auflösen eigener Formationen in eine Wand, entsteht sie zu Beginn des eigenen Zuges und gibt einen Freizug. | ✅ BB |
| Laden | Eine Formation startet mit etwa **50 % ihres Max-Angriffs** und steigt bis zur Max-PWR, wenn die Ladezeit abläuft. Beispiel: Archer Lv5 startet mit 4 von 8. | ✅ BB / ⚠️ Kurve (linear?) |
| Werte im Spiel | Ladende Formationen zeigen oben die Runden bis zum Angriff, unten die aktuelle PWR. PWR ist zugleich Angriff und HP. | ✅ WT, DE |
| Schaden | Ein Angriff läuft durch die gegnerische Spalte. Idle-Einheiten ziehen ihre **Toughness** ab und sterben sofort. Wände ziehen ihre aktuelle HP ab. Ladende Formationen ziehen ihre **aktuelle PWR** ab und überleben, solange PWR übrig ist. Der Rest trifft den Helden. | ✅ FW (Power), WT |
| Link | Formationen **gleicher Farbe**, die **in derselben Runde angreifen** (gleiche Restladezeit). Formel: jede verlinkte **Core**-Formation gibt allen *anderen* Link-Partnern **+15 %**, **Elite +25 %**, **Champion +50 %**. Beispiel: Champion + 2 Core: Cores je +65 %, Champion +30 %. Eine fusionierte Formation zählt beim Link als 2 (3, …) Formationen. Der Bonus greift erst beim Angriff, nicht beim Laden. Binding Orb: Link-Bonus +50 %. | ✅ WT (Forum-Formel von „Tarzanman0“) / ⚠️ für DE prüfen |
| Fusion | Gleiche Einheit, gleiche Farbe, hinter eine ladende Formation gesetzt. Startwert und Max-PWR verdoppeln sich, bei X Fusionen ×(X+1). Es gilt die **Restladezeit der ersten** Formation. Elite und Champion können auch fusionieren. Die Verstärkungen werden zurückerstattet. Braucht 6 freie Reihen, eine Wand in der Spalte verhindert Fusion. Doubling Cape / Lion's Mane: +50 %. | ✅ BB, FW |
| Angriffsreihenfolge | Pro Runde greifen Formationen in Erstellungsreihenfolge an. Verlinkte vor unverlinkten. Innerhalb eines Links geht die schnellste Animation zuerst, Core meist vor Elite/Champion (Succubus ist besonders langsam). | ⚠️ BB (beobachtet) |
| Verstärkung | Holt Einheiten aus der Reserve, kostet 1 Zug (King's Crown: gratis). Die Drops erzeugen **nie** sofort eine Formation. Liegt schon eine fremdfarbige Einheit oben, kommt mit 33 % die passende Farbe darauf. | ✅ GP / ⚠️ BB (Drop-Regel) |
| High-Tier-Cap | Höchstens 4 Elite, oder 2 Elite + 1 Champion, oder 2 Champions gleichzeitig auf dem Feld. Ein eingegrabener Treant zählt mit. | ⚠️ BB („ungeschriebene Regel“) |
| Einheitenlimit | Max. 32 Core in der Reserve plus Feld (Helden-Unit-Cap) | ⚠️ BB |
| Mana (MP) | Max. MP = Max. HP des Helden (Lv1: 10, Lv10: 100). Schaden austeilen gibt **1 MP pro Schadenspunkt**, Schaden nehmen **2 MP pro Punkt**. Jeder Link, jede Fusion und jeder Chain-Extrazug gibt ca. 6 %, jeder ungenutzte Zug am Rundenende ca. 3 %. Überlauf verfällt. Schadenszauber geben dem Zaubernden kein MP. | ✅ BB / ⚠️ (6 %, 3 %) |
| Puzzle-Modus | Eine volle Runde. Danach greifen **alle** erstellten Formationen sofort an, egal wie lange sie laden würden. Ziel: alle gegnerischen Einheiten zerstören. Der Gegner hat keinen Zug. | ✅ FW (Battle Puzzle) |

## 2. Einheiten

### 2.1 Werte

- **FW-Spalten** zeigen Werte als „A → B“. Nach Abgleich mit BB ist das sehr wahrscheinlich **Level 1 → Max-Level** (z. B. Swordsman FW 6→11, BB Lv5 = 11). Das ist ⚠️ und sollte geprüft werden. Es ist **nicht** die Lade-Kurve.
- **BB Lv5** = DS-Werte auf Level 5. **CT** = Ladezeit in Runden.
- **DE-CT** = Ladezeit laut offiziellen DE-Profilen. Leer heißt: dort nicht genannt.

| Fraktion | Einheit | Tier | FW Angriff | FW Toughness | FW CT | BB Lv5 Atk/Tough/CT | DE-CT |
|---|---|---|---|---|---|---|---|
| Sylvan | Hunter | Core | 2 → 7 | 1 → 2 | 1 | 7 / 2 / 1 | 1 |
| Sylvan | Pixie | Core | 1 → 5 | 1 → 2 | 2 | 6 / 2 / 2 | 2 |
| Sylvan | Bear | Core | 5 → 10 | 1 → 3 | 2 | 10 / 3 / 2 | 2 |
| Sylvan | Druid | Elite | 9 → 21 | 3 → 5 | 2 | 25 / 5 / 2 | 2 |
| Sylvan | Deer | Elite | 16 → 28 | 3 → 5 | 3 | 26 / 5 / 3 | 3 |
| Sylvan | Unicorn | Elite | 14 → 26 | 4 → 6 | 2 | 30 / 6 / 2 | – |
| Sylvan | Treant | Champion | 50 → 95 | 15 → 29 | 4 | 95 / 29 / 5 | 5 |
| Sylvan | Emerald Dragon | Champion | 45 → 90 | 9 → 21 | 4 | 105 / 21 / 4 | – |
| Haven | Swordsman | Core | 6 → 11 | 2 → 3 | 3 | 11 / 3 / 3 | 3 |
| Haven | Archer | Core | 3 → 8 | 1 → 3 | 2 | 8 / 3 / 2 | 2 |
| Haven | Spearman | Core | 4 → 9 | 1 → 2 | 3 | 9 / 2 / 3 | 3 |
| Haven | Knight | Elite | 20 → 32 | 4 → 6 | 4 | 30 / 6 / 4 | 4 |
| Haven | Priestess | Elite | 10 → 22 | 2 → 4 | 4 | 22 / 4 / 4 | 4 |
| Haven | Angel | Champion | 70 → 115 | 14 → 23 | 6 | 115 / 23 / 6 | 6 |
| Haven | Griffin | Champion | 55 → 100 | 12 → 21 | 5 | 105 / 21 / 5 | 5 |
| Haven | Sword Master | Champion (geheim) | 60 → 105 | 18 → 27 | 6 | 135 / 27 / 6 | 6 |
| Necropolis | Skeleton | Core | 4 → 9 | 1 → 3 | 2 | 9 / 3 / 2 | 2 |
| Necropolis | Zombie | Core | 3 → 8 | 1 → 2 | 2 | 8 / 4 / 2 | 2 |
| Necropolis | Ebon Guard | Core | 5 → 10 | 1 → 3 | 3 | 10 / 3 / 3 | 3 |
| Necropolis | Vampire | Elite | 13 → 25 | 3 → 5 | 4 | 27 / 5 / 4 | 4 |
| Necropolis | Ghost | Elite | 13 → 25 | 3 → 5 | 3 | 26 / 5 / 4 | 3 |
| Necropolis | Bone Dragon | Champion | 60 → 110 | 11 → 20 | 5 | 105 / 20 / 5 | 5 |
| Necropolis | Death Knight | Champion | 60 → 105 | 15 → 24 | 6 | 120 / 24 / 6 | 6 |
| Necropolis | Wraith | Champion (geheim) | 20 → 55 | 4 → 13 | 5 | 67 / 13 / 4 | 5 |
| Inferno | Horned Demon | Core | 6 → 11 | 1 → 3 | 3 | 11 / 3 / 3 | 3 |
| Inferno | Imp | Core | 5 → 10 | 1 → 3 | 3 | 10 / 3 / 3 | 3 |
| Inferno | Hellhound | Core | 4 → 9 | 1 → 3 | 2 | 9 / 3 / 2 | 2 |
| Inferno | Succubus | Elite | 25 → 37 | 5 → 7 | 4 | 37 / 7 / 4 | 4 |
| Inferno | Nightmare | Elite | 23 → 35 | 4 → 7 | 4 | 34 / 7 / 4 | 4 |
| Inferno | Sorcerer | Elite (geheim) | 17 → 29 | 4 → 7 | 3 | 34 / 7 / 2 | 3 |
| Inferno | Abyssal Lord | Champion | 60 → 105 | 11 → 20 | 5 | 120 / 20 / 6 | 5 |
| Inferno | Pit Fiend | Champion | 60 → 115 | 13 → 22 | 5 | 110 / 22 / 5 | 5 |
| Academy | Apprentice | Core | 3 → 8 | 1 → 2 | 2 | 8 / 2 / 2 | **1** |
| Academy | Gremlin | Core | 6 → 14 | 1 → 2 | 2 | 18 / 3 / 2 | 2 |
| Academy | Golem | Core | 5 → 10 | 1 → 3 | 3 | 10 / 3 / 3 | 3 |
| Academy | Mage („Wizard“ in DE) | Elite | 17 → 29 | 4 → 6 | 4 | 30 / 6 / 4 | 4 |
| Academy | Djinn | Elite | 15 → 27 | 4 → 6 | 3 | 32 / 6 / 3 | 3 |
| Academy | Rakshasa | Champion | 50 → 95 | 10 → 21 | 5 | 105 / 21 / 5 | 5 |
| Academy | Titan | Champion | 65 → 110 | 13 → 22 | 6 | 110 / 22 / 6 | 6 |
| Academy | Phoenix | Champion (geheim) | 70 → 115 | 16 → 25 | 5 | 125 / 25 / 6 | 5 |

Hinweise:
- Je Fraktion gibt es 3 Core-, 2–3 Elite- und 2–3 Champion-Typen. Pro Kampf wählt man 3 Core (jede eine Farbe) und 2 High-Tier-Slots.
- Die Unit-Namen aus der alten DATEN.md (Gremlin/Golem bei Academy ✅, Hell Hound/Demon bei Inferno ✅, Lich ❌ gibt es nicht, Djinn ✅) sind jetzt geklärt. „Acid Dragon“ heißt **Emerald Dragon**.

### 2.2 Spezialfähigkeiten (für den Simulator)

| Einheit | Regel | Quelle |
|---|---|---|
| Hunter, Archer, Bear, Swordsman, Skeleton, Ebon Guard, Horned Demon, Hellhound, Golem, Apprentice | Keine Sonderregel | FW, BB |
| Pixie | Beim Angriff Bonus von +0 bis +10 PWR, proportional zur MP-Füllung (vermutlich +1 je 10 %). Gilt erst beim Angriff, nicht beim Laden. | BB ⚠️ |
| Gremlin | Verliert pro durchquerter gegnerischer Reihe 2 PWR (max. −12 bei 6 Reihen). Fällt dadurch nie auf 0. Das Zusammenspiel mit Treffern ist unklar. | BB ⚠️ |
| Spearman | **First Strike**: verliert keine PWR gegen Idle-Einheiten und Formationen mit PWR ≤ eigener PWR. Wände bremsen normal (Golden Spear ändert das). | BB, DE |
| Zombie | **Plagued Bite**: getroffene Formation verliert 2 PWR pro Runde. Stapelt pro Zombie-Formation, verdoppelt sich bei Fusion nicht. | BB |
| Imp | DS: entzieht dem Helden MP bei Treffer. DE und FW: explodiert bei Treffer auf eine Formation mit Flächenschaden. | ⚠️ widersprüchlich, DE-Version gilt |
| Druid | Getroffene Formation: Ladezeit **+2** (DE, FW). DS: +3, Elder Staff +1. | DE ✅ |
| Deer | Springt über Wände. DE: **1 Wandreihe**, DS: 2 Wände. Deer Antler: alle Wände. | DE ✅ |
| Unicorn | Beim Laden: Aura/Barriere. DS: über die ganze erste Reihe, blockt 15 PWR je Spalte (Lv5), stapelbar, Champions zahlen doppelt. DE: schützt sich selbst und die Nachbarspalten. | ⚠️ DE-Umfang prüfen |
| Treant | Trifft er den Helden, gräbt er sich mit HP = verursachtem Schaden ein. Danach jede Runde 10 % seiner HP als Schaden am Gegner und Heilung beim eigenen Helden. Ist unbeweglich, nicht löschbar und zählt zum High-Tier-Cap. | BB, DE |
| Emerald Dragon | Säure auf allen erreichten Feldern (bis 2 Spalten): 3 Schaden pro Feld an Einheiten darauf. DS: bis zu 5 Runden oder bis zum ersten Treffer. DE und FW: **1 Runde**. | ⚠️ DE: 1 Runde |
| Knight | DS: startet mit voller PWR, lädt nicht weiter. DE: Schild in Höhe von **50 %** der Max-PWR beim Laden (FW: 40 %). Knight's Armor: startet voll. | ⚠️ DE: 50 % |
| Priestess | Heilt den eigenen Helden pro Laderunde (DS: 3 HP, fusioniert 5). | BB |
| Angel | Heilt jede Laderunde eigene beschädigte Formationen um 25 % (aufgerundet) ihrer Max-PWR. Zwei Angels heilen sich gegenseitig. Trifft 2 Spalten. | BB, DE |
| Griffin | Trifft er eine stärkere Formation: Battle Dive mit 2× aktueller PWR, danach ist er weg. DE: auch beim Erreichen der Helden-HP-Leiste. | BB / DE ⚠️ |
| Sword Master | DE: Schockwelle in die gegnerische Spalte zu Beginn jeder Runde. DS: „Mortal Wound“, 3 Schaden pro Runde nach Heldentreffer, stapelbar. | ⚠️ DE-Werte fehlen |
| Vampire | Blood Drain: Heldenschaden heilt den eigenen Helden 1:1 | BB, DE |
| Ghost | Beim Laden unverwundbar. Angreifer verlieren die aktuelle PWR des Ghosts und laufen durch. Nur als Idle zerstörbar (oder durch Ghost, Wraith, Djinn-Kombo). | BB, DE |
| Bone Dragon | Frisst Idle-Einheiten: deren Toughness wird **addiert** statt abgezogen | BB, FW |
| Death Knight | Zieht beim Laden PWR von gegnerischen Formationen ab (DS: keine Sonderregel beobachtet) | FW, DE ⚠️ Rate fehlt |
| Wraith | Tötet alles, was er trifft, sofort, auch den Helden. PWR wird normal reduziert. Beim Laden fragil. | BB, DE |
| Succubus | 4 Feuerbälle mit je 25 % Atk. Jeder stoppt am ersten Objekt und macht 25 % davon Splash auf die 4 Nachbarfelder. | BB |
| Nightmare | Greift eine Nightmare an, greifen **alle** ladenden Nightmares mit ihrer aktuellen PWR mit an. Link-Sonderfälle siehe BB-Guide. | BB, DE |
| Sorcerer | Beschädigte, nicht zerstörte Formation wird wieder idle. Wirkt nicht gegen Ghosts. | BB, DE |
| Abyssal Lord | DE: absorbiert PWR gefallener eigener Formationen beim Laden. DS: durchschlagender Feuerstrahl. | ⚠️ DE-Rate fehlt |
| Pit Fiend | Besiegte Einheiten bleiben als brennende Leichen liegen | FW, DE ⚠️ Effekt |
| Mage | Trifft er eine Idle-Einheit in seiner Spalte, springt Elektrizität orthogonal auf alle verbundenen Idle-Einheiten und zerstört sie (erst nach seinem Angriff). Wände und Formationen leiten nicht. | BB |
| Djinn | Schadet nicht, friert getroffene Einheiten ein (DE und FW: 3 Runden, DS: 4). Trifft ein Angriff eine gefrorene Formation mit ≥ 25 % Schaden, zerspringt sie. | BB, DE |
| Rakshasa | Heldentreffer zieht gleich viel HP **und** MP ab | BB, DE |
| Titan | Vor dem Angriff verlieren alle verbundenen gegnerischen Wände die Hälfte (aufgerundet) ihrer aktuellen HP | BB, DE |
| Phoenix | Supernova: 10 Schaden pro Feld in den 2 Spalten links und rechts. Wiederbelebt Formationen (DE) bzw. den Helden (DS) einmal, solange er lädt. | BB, DE ⚠️ |

## 3. Wände nach Fraktion

| Fraktion | Basis-HP / Max (fusioniert) | Spezial | Quelle |
|---|---|---|---|
| Haven | höchster Wert, Max 16 | keine | BB, DE |
| Sylvan | 6 / 12 | regeneriert **2 HP pro Runde** (Vine Gloves: 4) | BB, DE |
| Necropolis | 6 / 12 | Sterbende Idle-Einheiten hinterlassen Knochenwände: Core 1× 1 HP, Elite 2× 1 HP, Champion 4× 2 HP | BB, DE |
| Inferno | 5 / 10 | Nahkämpfer, die durchlaufen, bekommen 2× 25 % (aufgerundet) der aktuellen Wand-HP als Feuerschaden | BB, DE |
| Academy | DS: HP = Anzahl Wände, max. 10. **DE: Basis 6, +5 HP pro weiterer gebildeter Wand** | DE ✅ / Obergrenze ❌ |

## 4. Helden und Zauber

Die DE hat **15 Helden**: die 10 Originalhelden, 4 spielbare Bosse aus dem DLC „I Am the Boss“ und einen neuen Multiplayer-Boss. Werte gelten für DS-Level 10 (100 HP), es sei denn, es steht etwas anderes da.

| Held | Fraktion | Zauber | Effekt | Quelle |
|---|---|---|---|---|
| Anwen | Sylvan | Arrow Storm (DS: Sniper Shot) | DE: Pfeilhagel auf **3 gewählte Spalten** und die HP-Leiste. FW: Mittelpfeil 25, äußere je 12. DS: 50 % Max-HP auf eine Spalte. | DE, FW |
| Findan | Sylvan | Swift Strike | Alle ladenden Formationen auf CT 1. Setzt sie bis zum Angriff temporär auf Max-PWR. | BB, FW |
| Godric | Haven | Holy Shield | Schild mit 50 % Max-HP vor der eigenen Heldenzone für 1 Runde. Restwert ×2 wird danach auf den Gegner geschossen. | FW, DE, BB |
| Varkas | Haven | Elrath's Sword | FW: alle ladenden Formationen +30 % PWR. BB (DS): Reihe 1 und 2 des Gegners bekommen 10 % bzw. 5 % Max-HP Schaden pro Feld. | ⚠️ widersprüchlich |
| Fiona | Necropolis | Blood Ritual | Alle eigenen Idle-Core werden geopfert (zu Wänden). Schaden = ½ ihrer summierten Toughness, auf eine Spalte. | BB, DE |
| Markal | Necropolis | Death March | Alle Idle-Elite und -Champions sofort geladen. Ermöglicht Chains und Fusionen. | BB, FW |
| Aidan | Inferno | Fiery Brimstone | Alle eigenen Wände werden Feuerbälle in ihrer Spalte, Schaden = Wand-HP | BB, DE |
| Jezebeth | Inferno | Wall Crusher | Alle gegnerischen Wände explodieren: 25 % ihrer HP an angrenzende Einheiten, pro Feld nicht stapelnd | BB, FW |
| Nadia | Academy | Lightning Strike | 5 Blitze auf zufällige 2×2-Flächen, je 21 Schaden (Lv10) | BB, DE |
| Cyrus | Academy | Staff of Explosia | Stab landet in Reihe 1–2 mit 25 % Max-HP Aufprallschaden. Explodiert sofort oder nach 2 Runden mit 15 % Max-HP pro Feld in einer Raute (13 Felder). | BB |
| Azexes, Carlyle, Ludmilla, Azh Rafir | Bosse (DLC) | ❌ | Vermutlich die 4 Kampagnen-Bosse. Azh Rafir nutzt laut FW Staff of Explosia. | ⚠️ |
| MP-Boss (neu) | ❌ | ❌ | Name und Fähigkeit nicht gefunden | ❌ |

KI-Verhalten (DS, für das Gegnermodell): Anwen, Cyrus, Nadia, Fiona und Varkas zaubern sofort, wenn die Leiste voll ist. Anwen und Fiona zielen auf die am schwächsten verteidigte Spalte. Godric zaubert eine Runde vor einem drohenden Treffer. Die KI greift bevorzugt idle Champions an und schützt die eigenen. (BB)

## 5. Artefakte (vollständig, 50 Stück) ✅ Quelle: Gamepressure (DE-Namen)

Die DS-Namen weichen teils ab (z. B. „Enchanted Staff“ = Elder Staff, „Blessed Helm“ = Holy Blade mit 10 % statt 20 % Krit). Die Zahlen unten sind die DE-Werte.

### Irollan
| Artefakt | Effekt |
|---|---|
| Leaf Plate | Helden-HP +25 % |
| Golden Roots | Zerstörte Wände respawnen mit 1 HP |
| Deer Antler | Deer springen über ALLE gegnerischen Wände |
| Elder Staff | Druiden-Fähigkeit +1 pro mit dem Druiden verlinkter Formation |
| Doubling Cape | Fusionsangriffe +50 % |
| Vine Gloves | Wände regenerieren doppelt so schnell |
| Treant's Sap | Treant-Wurzeln saugen doppelt so viel HP |
| Dragon Scales | Emerald-Dragon-Säure hält 1 Runde länger |
| Boost Boots | Angriffe gewinnen PWR für jede überquerte Reihe des Gegners |
| Ring of Life | Einmalige Wiederbelebung, danach 2 % Max-HP Regeneration pro Runde |

### Holy Griffin Empire
| Artefakt | Effekt |
|---|---|
| Phoenix Feather | Einmalige Wiederbelebung mit 25 % HP |
| Lion's Mane | Fusionsangriffe +50 % PWR |
| Knight's Armor | Knight-Formationen laden ab voller PWR |
| Golden Spear | Spearman-First-Strike gilt auch für Wandeinheiten |
| Holy Blade | 20 % Chance auf kritischen Treffer pro Angriff |
| King's Crown | Verstärkung kostet keinen Zug |
| Blessed Wing | Angel heilt ladende Formationen sofort auf volle PWR |
| Feathered Helm | Griffin-Ladezeit −1 |
| Staff of Elrath | Priestess schadet dem Gegner statt den Helden zu heilen |
| Crown of Elrath | Spell-Meter füllt sich doppelt so schnell |

### Heresh
| Artefakt | Effekt |
|---|---|
| Cursed Shield | Gegnerische Wände −50 % Stärke |
| Blood of the One | Vampire Blood Drain +25 % |
| Ritual Dagger | Löschen einer Idle-Core-Einheit löscht eine zufällige gegnerische Core-Einheit in der gegenüberliegenden Spalte |
| Spider Cloak | Helden-Max-HP −75 %, alle Angriffe +75 % |
| Plague Rat | Zombie Plague Bite doppelt so stark |
| Blood Ring | Besiegte gegnerische Idle-Einheiten füllen MP auf |
| Crown of Thorns | Gegnerischer Held verliert 2 HP pro Runde |
| Twilight Urn | Wände aus gefallenen Idle-Einheiten +100 % |
| Book of the Dead | Einmalige Wiederbelebung durch Absorbieren aller Idle-Einheiten |
| Talon's Talon | Bone Dragon absorbiert doppelte Toughness |

### Sheogh
| Artefakt | Effekt |
|---|---|
| Rage Shield | Flammenschaden trifft eine Reihe mehr |
| Thorn Whip | Nightmares erreichen Max-Power beim gleichzeitigen Start mit anderen Nightmares |
| Magma Shard | Abyssal Lord erhält 100 % der Power gefallener Formationen |
| Celerity Ring | +1 Zug pro Runde |
| Burning Horn | Succubus +25 % Angriff |
| Volcano Armor | Brandschaden für gegnerische Einheiten, die durch eigene ladende Formationen laufen |
| Pit Master's Tail | Pit-Fiend-Ladezeit −1 |
| Crippling Flail | Senkt die Start-Ladepower gegnerischer Formationen |
| Revive Flame | Einmalige Wiederbelebung mit 5 HP. Alle Formationen starten sofort mit voller Power. |
| Chaos Crown | Chains geben HP statt MP |

### Silver Cities
| Artefakt | Effekt |
|---|---|
| Gauntlet | Wände frei auf dem Feld greifen und platzieren |
| Absorb Circlet | Wand löschen gibt MP in Höhe ihrer Stärke |
| Mana Shield | Schaden zieht zuerst MP ab, dann HP |
| Battle Wand | Kampf startet mit vollem Mana |
| Djinn's Sash | Gefrorene Gegner zerspringen bei einem Djinn-Treffer |
| Golden Fist | Titan-Schockwelle zerstört gegnerische Wände komplett |
| Scimitar | Rakshasa-Spirale wird von Idle-Einheiten nicht gebremst |
| Binding Orb | Link-Bonus +50 % |
| Transform Gem | Mages fusionieren unabhängig von der Farbe |
| Revival Ring | Einmalige Wiederbelebung mit 5 HP und vollem Mana |

## 6. Bekannte Abweichungen DS → Definitive Edition

Laut offiziellen DE-Profilen (Steam, 2023) gegenüber BB (DS):
- Apprentice CT 2 → **1**; Ghost 4 → **3**; Sorcerer 2 → **3**; Wraith 4 → **5**; Phoenix 6 → **5**; Abyssal Lord 6 → **5**; Treant laut FW 4, DE **5**
- Druid +3 → **+2** Ladezeit; Deer springt über **1** statt 2 Wandreihen; Djinn friert **3** statt 4 Runden ein
- Knight: Schild **50 %** der Max-PWR statt Start mit voller PWR
- Imp: Flächenschaden statt MP-Entzug; Abyssal Lord: absorbiert PWR gefallener Formationen
- Academy-Wände: Basis 6, +5 pro weiterer Wand; Necropolis-Wände: Basis 6
- Anwen: 3 Spalten statt einer
- Die DE hat den Multiplayer laut Steam „fully reworked and re-balanced“. PC Gamer schreibt dagegen, das Update ändere „almost nothing“. Vermutlich betrifft das Rebalancing vor allem den MP-Modus.

## 6b. Aus eigenen Screenshots verifiziert (DE, 2026-11-12, Godric Lv10 vs. Fiona Lv10)

- **Werte-Ansicht:** erscheint, solange L1 gehalten wird. Sie zeigt das Raster und pro idle Einheit ein Herz mit der **Toughness**.
  Elite und Champion haben eine Zahl.
- **Raster 8×6 pro Seite** ✅. Bei 1920×1080 ist eine Zelle etwa 85 px groß. Gegnerraster etwa x 617–1302, y 118–508. Eigenes Raster etwa y 572–960.
- **Toughness bei Heldenlevel 10 = FW-Maximalwert** ✅: Spearman 2, Swordsman 3, Knight 6, Griffin 21, Skeleton 3, Death Knight 24.
  Daraus folgt: FW „A → B“ bedeutet Heldenlevel 1 → 10. Im Simulator ist jetzt `max_level = 10` eingestellt.
- Die vermummte Necropolis-Core-Einheit (lila/grün) hat Toughness 3. Das passt zu Ebon Guard (3), nicht zu Zombie (2). Noch zu klären.
- Haven-Farben im Bild: Blau, Gold, Weiß.
- Hover über eine Einheit zeigt „3“ und „5“: vermutlich Ladezeit 3 und Start-PWR 5 der möglichen Formation (Spearman Lv10: Max 9 → Start 5 = 50 % aufgerundet ✅ passt zur Annahme).
- Elite- und Champion-Vorrat wird seitlich angezeigt (z. B. Knight 10/10, Angel 5/5, Ghost 3/3, Death Knight 5/5).
- Steuerung (Controller): Y Heldenzauber, X Zug beenden, A Einheit greifen/setzen, B Einheit löschen, LT Verstärkung, LB+RB Artefakt-Details.
- Die Zugzahl wird unten in der Mitte angezeigt (im Screenshot 2).

### Screenshot 233733 (L1-Ansicht während des Gegnerzugs)
- **Necropolis-Wände: 6 HP, fusioniert 12** ✅
- Ladende Formationen zeigen über der Leiste eine große Zahl (vermutlich Restladezeit) und darunter rechts die aktuelle PWR.
- **Knight** (ich): Restladezeit 3, PWR 20. Rechnung: Max 32, Start 16, Ladezeit 4, nach 1 Tick 16 + 16/4 = 20 ✅. Die Ladekurve ist linear.
- **Skeleton-Formationen**: PWR 7. **Ebon-Guard-Formation**: PWR 9. Beide zeigen **keine** Ladezeit-Zahl.
  Mit **Aufrunden** passen beide zu „noch 1 Runde“ (Skeleton 5 → 7, Ebon Guard 5 → 7 → 9). Der Simulator rundet jetzt auf.
  Hypothese: Bei Restladezeit 1 wird keine Zahl angezeigt. ⚠️
- **Griffin** (ich): Restladezeit 4, PWR **57**, erwartet waren 60. Mögliche Ursache: Der Death Knight entzieht beim Laden PWR (DE-Beschreibung). ⚠️
- **Death Knight**: Zahl 5, PWR **79**. Mit Start 53 und Max 105 entsprechen 79 genau 3 von 6 Ticks, das passt nicht zu „5“. ⚠️ Eventuell sind 5 die Runden ohne Drain-Effekte oder etwas anderes.
- Oben links beim Gegner steht eine geflügelte „3“: wahrscheinlich seine verbleibenden Züge. Unten ist meine Anzeige ausgegraut.
- Reserve-Zähler: Gegner 10, ich 13.

### Vom User bestätigt bzw. aus Spielbildern (2026-11-13)
- **Extrazüge:** Jede Formation oder Wand, die durch **eine** Aktion zusätzlich entsteht, gibt +1 Zug.
  - Löschen: 3 − 1 + 1 pro Formation/Wand.
  - Verschieben: die erste ist „normal“, jede weitere gibt +1 (Combo); Nachrutsch-Kaskaden ebenfalls.
  - Eine Einheit kann gleichzeitig senkrecht (Formation) und waagerecht (Wand) zählen.
- **Der Startspieler hat im ersten Zug 2 Züge**, sonst 3. Das Tool liest die Zahl aber aus der UI.
- **Zuganzeige:** Emblem unter der Spalte, in der der Cursor steht.
- **Zug beenden** gibt MP für ungenutzte Züge.
- **Elite- und Champion-Formationen** belegen in der DE nur ihr eigenes Feld (1×2 bzw. 2×2). Die Core-Einheiten dahinter verschwinden.

### Im Spiel geprüft (2026-11-23, Bilder 20261123_111246 -> 20261123_121043)
- S8/R1 gelöscht: Weiße Wand (Reihe 3) und goldene Wand (Reihe 4) entstehen **gleichzeitig**. Der goldene Reiter wird nicht aktiviert, denn das Gold direkt hinter ihm geht in die Wand.
- Züge 2 -> 3: Löschen kostet 1, jede Wand gibt +1, **kein** Combo-Zuschlag beim Löschen (`combo_on_delete_gives_moves: false`).
- Haven-Wand: einfach **7**, verschmolzen **14** (vorher 8/16 angenommen). Die Erkennung liest jetzt die Wand-Zahl: zweistellig = Doppelwand.
- Reserve 0 -> 4: 1 für die gelöschte Einheit plus 1 je verschmolzenem Wandsegment (3).
- Offen: Magie nur 1 % statt der geschätzten 12 % (2 Extrazüge à 6 %). Geben Wände keine Magie? ⚠️

### Magie gemessen (2026-11-24, alle L1-Analysen bis 20261124_153431)
- Aufeinanderfolgende Analysen im selben Zug, Plan bis zum Nachrufen gespielt: 1 Chain (Formation durch Löschen) **+3 bis +4 %**; Bewegen und Nachrufen ohne Chain **+0 %** (5 Fälle). -> `mp_per_extra_move: 0.035` (vorher 0.06).
- Über den Rundenwechsel (17 Fälle, Ausgleichsrechnung, Rest ±3 %): **0,82** je ausgeteiltem und **1,55** je erhaltenem Schadenspunkt (vorher 1 und 2).
- Fusion: nur ein Fall (mit Chain zusammen +4 %) -> klein, `mp_per_fusion: 0.01` ⚠️. Link-Partner und ungenutzte Züge noch ungeprüft ⚠️.
- Wände durch Löschen: siehe oben (2 Extrazüge, nur +1 %) – möglicherweise geben Wände weniger als Angriffsformationen ⚠️.

## 7. Weiterhin offen ❌

- Genaue DE-Zahlen (Atk/Toughness pro Level): am zuverlässigsten per OCR aus der Einheitenübersicht im Spiel
- Lade-Kurve: linear von 50 % auf 100 %? (BB: Start = halbe Max-PWR)
- Link-Formel (15/25/50 %) in der DE bestätigen
- Die 5 DLC- bzw. Boss-Helden und ihre Zauber
- Sword-Master-Schockwelle, Death-Knight-Drain, Abyssal-Lord-Absorption: genaue Werte
- Wand-HP Haven (Basis), Academy-Obergrenze in der DE

## Quellen
- Fandom-Wiki, Einheiten (40 Seiten, Kategorie „Clash of Heroes creatures“), z. B. https://mightandmagic.fandom.com/wiki/Swordsman_(CoH); Mechaniken: Linking, Chain_(CoH), Fusion, Power_(CoH), Wall, Charge_time, Battle_Puzzle, Hero_spells; Fraktionsseiten Sylvan/Haven/Necropolis/Inferno/Academy_(CoH)
- GameFAQs, Strategy Guide von Blackbird (DS, Formeln, Lv5-Werte): https://gamefaqs.gamespot.com/ds/960173-might-and-magic-clash-of-heroes/faqs/59239
- GameFAQs, Guide and Walkthrough (Link-Formel): https://gamefaqs.gamespot.com/ds/960173-might-and-magic-clash-of-heroes/faqs/63331
- Steam-News zur DE (Character Profiles Anwen, Godric, Fiona, Aidan, Nadia; Gameplay Introduction; Release): https://store.steampowered.com/news/app/2213300
- Steam-Seite DE: https://store.steampowered.com/app/2213300/
- Gamepressure-Guide (Artefakte): https://www.gamepressure.com/mightandmagicclashofheroes/artifacts/z02e3f
