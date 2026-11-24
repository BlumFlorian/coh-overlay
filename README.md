# CoH Move Advisor

*[Deutsche Version](README.de.md)*

A move-advisor overlay for *Might & Magic: Clash of Heroes – Definitive Edition* (Steam, Windows).

During your turn, open the game's **stats grid** (the view that shows unit values on the board) and hold it for about half a second. The tool reads the board from the screen, simulates your possible moves and draws the best suggestion as arrows and crosses on top of the game, with a short explanation (e.g. „Warum: Elite aktiviert, Schaden am Gegner +41“ – the overlay text is German).

- **Read-only:** it only takes screenshots and reads controller/keyboard input. It never touches the game process or its memory.
- **Big picture:** chains and combos, elite/champion activation (also across two turns), linked attacks, walls, reinforcements, elite/champion stock, Holy Shield, look-ahead to your next turn.
- **Honest:** anything the recognition is not sure about is shown as „Unsicher“ (unsure), equally good alternatives as „Knapp“ (close call).

Concept: [`docs/KONZEPT.md`](docs/KONZEPT.md), game data and verified rules: [`docs/DATEN.md`](docs/DATEN.md) (both in German).

> Fan project, not affiliated with Ubisoft or Dotemu. Tested with Haven (Godric) at 1920×1080. The in-game texts used for recognition and the console output are in German.

## Controls

| Action | Controller | Keyboard |
|---|---|---|
| Analyse the board | Hold the **left shoulder button** for ~0.5 s (L1 on PlayStation, LB on Xbox, L on Switch Pro). In the game this also shows the stats grid. | Open the stats grid with the game's key, then press **F8** |
| Show/hide overlay | **Right shoulder button** (R1 / RB / R) | **F7** |

Controllers are read through SDL's game-controller mapping, so most common pads work. If yours is not detected, the keyboard keys always work.

## Setup (once)

Requirements: Windows 10/11 and Python 3.12.

```powershell
git clone https://github.com/BlumFlorian/coh-overlay.git
cd coh-overlay
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Then start by double-clicking **`CoH-Berater starten.bat`** (the only starter).

Run the game **borderless** on your main monitor.

## 0. Client window (recommended)

**`CoH-Berater starten.bat`** opens a window for your second monitor and also starts the overlay.
It shows the recognized board next to the screenshot (what the suggestion is based on), head values,
plan, history and log. Name the colors once in the legend (letters are arbitrary per analysis); the
client then assigns them itself. **"✎ Brett falsch melden"** corrects cells and values,
**"👎 Vorschlag schlecht"** records a better move. Reports go to `dataset/corrections/<time>/` as JSON
for training; **"📊 Training"** evaluates the current recognition against all corrections.
Requirements and data format: `docs/CLIENT.md` (German).

## 1. Overlay (live suggestions)

```powershell
.venv\Scripts\python tools\overlay.py
```

- In your turn, open the stats grid (see [Controls](#controls)). The tool captures it, recognises the board and draws the plan: numbered arrows (move a unit from column X to column Y), red crosses (delete), and a compact card „Dein Zug“ (your turn) in the top left with the steps of the current turn.
- **„Warum“ (why):** one line explains the plan compared to ending the turn right away (simulated over 5 rounds), e.g. elites activated, new attacks, damage dealt and blocked.
- **„Unsicher“ / „Knapp“:** what the recognition does not know for sure is listed as „Unsicher“ (unrecognised cells, colour of an elite/champion, possible enemy links, unread counters). If the two best plans are almost equal, the alternative is shown as „Knapp“ and you decide.
- Read from the game's UI: whose turn it is, remaining moves, both reserve counters, both elite/champion stocks, magic bars and wall values (yours and the enemy's).
- **Stock:** elite/champion losses are weighted more heavily the fewer remain; losing the last one carries a large penalty. Enemy losses count the same way as a gain.
- **Look-ahead:** the best candidates are rated together with your best follow-up turn, so preparations that only pay off a turn later (e.g. a champion that needs two turns to activate) are recognised.
- **Using all moves:** chains can give back many moves; the search plays promising plans to the end, so no moves are wasted.
- **Reinforcements:** calling reinforcements *first* is rated as well (averaged over several random drops, including possible elites/champions). Afterwards, open the stats grid again for a new suggestion.
- **Linked attacks:** forming a core attack that fires *before* a charging elite/champion of the same colour is penalised, because those units could link with it later.
- **Holy Shield (Godric):** with a full bar, casting is a free action. A full bar kept for later has its own value; casting must beat it. `--spell ""` disables it.
- Elites and champions are never suggested for deletion.
- Results are deterministic: the same board gives the same suggestion (fixed seeds, fixed search budget `--nodes`, averaged over `--frames` screenshots).
- Every analysis is saved to `dataset\analysis\` (screenshot, debug image with recognised classes, suggestion).
- The overlay is invisible to screen capture (OBS, Discord).
- Test without the game: `.venv\Scripts\python tools\analyze_image.py <image>.png --solve`

**Tip:** move the cursor to an empty column or a wall before analysing. The cursor hides the colour of the unit underneath.

## 2. Replay report (prediction vs. reality)

In the client: **"🔁 Replay"**, or:

```powershell
.venv\Scripts\python tools\replay.py                 # all recordings in dataset\analysis
.venv\Scripts\python tools\replay.py --day 20261113  # a single day
```

- Re-recognises all saved analyses and groups them into battles and turns.
- For two consecutive own turns, the first is simulated one round further and compared with the second: hero damage, formations (fired, still charging, gone) and stock.
- Report: `dataset\replay\bericht_<time>.md` with summary, open questions and individual deviations.
- Most useful when you analyse at the start of every turn.

## 3. Collecting screenshots

```powershell
.venv\Scripts\python tools\capture.py
```

Press the left shoulder button (or **F9**) in a battle. Two images are saved: the normal board and, 0.6 s later, the stats grid. `--delay 1.0` if the grid appears more slowly, `--learn` shows pressed controller buttons, `--test` takes a single test image.

## 4. Solver with a typed board

```powershell
.venv\Scripts\python -m coh.cli examples\beispiel1.txt          # top 3 suggestions
.venv\Scripts\python -m coh.cli examples\beispiel1.txt --steps  # board after every step
```

The board format is described in `examples/beispiel1.txt` and `coh/model.py`.

## Performance

- One analysis takes about 10–20 seconds. Look-ahead candidates run in parallel on several cores; the result is identical to the serial computation.
- `COH_WORKERS=1` disables parallelism, `COH_WORKERS=4` limits it to 4 processes.
- Faster but less thorough: `--lookahead 4` or `--lookahead 0` (no look-ahead).

## Tests

```powershell
.venv\Scripts\python -m pytest -q
```

## Structure

| File | Content |
|---|---|
| `coh/data/units.json` | Unit stats, wall values and uncertain rules as switches |
| `coh/vision.py` | Board recognition from the stats grid |
| `coh/model.py` | Board, pieces, text format |
| `coh/rules.py` | Simulator: moves, formations, walls, chains, fusion, charging, links, attacks, some special abilities |
| `coh/solver.py` | Beam search over your actions, rating by simulation over 5 rounds |
| `tools/overlay.py` | Live overlay |
| `tools/capture.py` | Screenshot collector (passive) |

## Not simulated yet

Hero spells other than Godric's Holy Shield (enemy spells not at all), most elite and champion special abilities
(implemented: Spearman, Druid, Zombie, Vampire, Ghost, Bone Dragon) and most artefacts.
Enemy moves are not predicted, only attacks that are already charging. Factions other than Haven are only partly covered.
