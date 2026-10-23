# W/L Draft Tracker: Design

Working design for the 2026-27 wins/losses draft site, agreed in conversation on 2026-10-20. Nothing is built yet.

The numbers in the sketches are made up. They describe one mid-January day, about 40 games into the season, and they agree with each other across screens.

## Decisions

- **Scope:** this season's race. A past-seasons page can come later if old drafts turn up.
- **Hosting:** a public GitHub Pages site. A GitHub Actions job refreshes the data, and the page itself polls ESPN while games are live.
- **Look:** dark scoreboard style that switches to light when the phone is in light mode. Light, template-based trash talk.
- **Constraints:** phone first, and fast (under 100 KB per load).

## Rules

- A pick is a team plus W or L, so there are 60 possible picks. 30 were drafted in a 6-round snake, slot order Ryan, Brian, Matt, Nick, Asaf.
- Score = wins on W picks + losses on L picks.
- Portland is legitimately drafted twice (Nick W, Ryan L). Utah went undrafted.
- Assumed: regular-season games only, matching the official standings (the NBA Cup final doesn't count).

## The draft

| Round | Ryan | Brian | Matt | Nick | Asaf |
|---|---|---|---|---|---|
| 1 | SAS W | OKC W | SAC L | BKN L | LAC L |
| 2 | NYK W | BOS W | CHI L | NOP L | MIL L |
| 3 | MEM L | HOU W | PHI W | DET W | DEN W |
| 4 | LAL W | TOR W | DAL L | MIN W | CLE W |
| 5 | GSW L | MIA W | WAS L | POR W | CHA L |
| 6 | POR L | ORL W | PHX L | IND W | ATL W |

## Draft-day numbers (BetMGM lines, Oct 19)

| | Projected points | VegasBot from the same slot |
|---|---|---|
| Matt | 300.1 | 298.3 |
| Ryan | 296.5 | 298.1 |
| Brian | 296.1 | 298.3 |
| Asaf | 294.5 | 294.5 |
| Nick | 293.7 | 295.7 |

Projections use the lines scaled to a real season (see Wins above Vegas). On the lines as posted they were Brian 299, Matt 299, Ryan 297, Nick 295, Asaf 295, and the bots 298, 298, 301, 297, 295 in the same order.

The group drafted 29 of the 30 options the lines valued most. The exception is Utah L (worth 44.5); Portland L (40.5) went in its place.

## Metrics

- **Points:** wins on W picks + losses on L picks.
- **Wins above Vegas:** points minus each pick's preseason line, prorated to its games played. A W pick expects line/82 per game; an L pick expects (82 - line)/82. The posted lines add up to 1,242 wins but a season has 1,230, which would make W picks look worse and L picks better, so every line is first scaled by 1,230/1,242.
- **VegasBot:** for each draft slot, a bot that drafts in the same snake order and always takes the highest-value pick left by the lines as posted, the way a person reading them would. It is scored on real results all season. Ties in value are broken by the over/under juice.
- **Title odds:** about 12,000 simulations of the remaining schedule. Each team's strength comes from its current win total on Kalshi's betting market, snapshotted each morning before the first tip. Without a market snapshot, the preseason strength is calibrated so the model reproduces its scaled Vegas line over the actual schedule; it then blends with the team's record, with the line counting as 25 games. Each simulation first draws how good every team really is from that uncertainty, so the odds aren't overconfident (preseason they come out at 17-25% for everyone). Games with a posted DraftKings spread (in ESPN's feed) use the spread. The same simulations pick tonight's "biggest game": the one whose result moves title odds most.

## Screens

Bottom tab bar: Standings, Tonight, Race, Draft. Swiping left or right also moves between them: the tabs sit side by side and page under the finger, each keeping its own scroll position (except across the race chart, where a sideways drag moves through the season, and while reordering games). The first visit asks "Who are you?" and remembers the answer on that phone, to highlight your row and tailor Tonight. All times are shown in the viewer's own time zone. In the sketches the viewer is Asaf.

### Standings (home)

```
+------------------------------------+
| W/L DRAFT 26-27          (*) LIVE  |
| Thu Jan 14 - updated 1 min ago     |
+------------------------------------+
| "RyanBot is beating Ryan by 4.     |
|  The robots are coming."           |
+------------------------------------+
|  #  NAME    PTS  LAST  TITLE       |
|  1  Brian   152   +4    34%   ^1   |
|  2  Matt    149    0    24%   v1   |
|  3  Ryan    147   +3    21%        |
|  4  Asaf    143   +2    14%   you  |
|  5  Nick    138   +1     7%        |
+------------------------------------+
| TONIGHT - up to +3 for you         |
|  POR @ MIL  6:00 PM  need POR  +1  |
|  DEN @ LAC  8:30 PM  need DEN  +2  |
|  2 live now, 2 more games      >   |
+------------------------------------+
| Standings  Tonight   Race   Draft  |
+------------------------------------+
```

### Tap a name, then a pick

```
+------------------------------------+
|  4  Asaf    143   +2    14%   you  |
|     PICK    PTS     VEGAS  NEXT    |
|     LAC L   27      +0.9   vDEN    |
|            of 40                   |
|     MIL L   26      -1.6   vPOR    |
|     DEN W   25      +0.9   @LAC    |
|     CLE W   22      -1.7   Fri     |
|     CHA L   22      +0.8   Fri     |
|     ATL W   21      -0.2   Sat     |
+------------------------------------+

Each pick shows what it has added to your score ("27 of 40": 27 points from 40 games), not the team's own record, which reads backwards for an L pick. The team's W-L is in the pick's panel.

+------------------------------------+
| POR W - Nick, pick #24             |
| 18-22, pace 37 wins, line 41.5     |
| -2.2 vs Vegas so far               |
| Last 10: L W W L L W L L W L       |
| Next: @MIL tonight, v DEN Sat      |
| Rival: Ryan has POR L              |
+------------------------------------+
```

### Tonight

Order: the biggest game, then live games, then the rest by tip-off time. Game types get tags: head-to-head, tank bowl (two L picks facing each other), win-win (both outcomes' owners want the same team).

Anyone can put the games in their own order with the Reorder button. It turns every game into a thin row (the teams with your picks marked, and the time or score) under a pinned bar. Tap a row to pick it, then move it with Top, Up, Down and Bottom as many times as you like, or drag a row by the handle on its right. Reset goes back to the usual order. Save order keeps the new order on that phone for the rest of the day; Cancel drops the changes.

Once a game tips off, its card adds points per quarter and each team's top performer, both from the scoreboard the page already polls. "Box score" opens a sheet with the full player stats for both teams and the last 15 plays (substitutions left out) from ESPN's game summary (about 35-50 KB). It's fetched only on tap and refreshed every 10 seconds while a live game's sheet is open; ESPN's servers hold a copy about 9 seconds, so faster gains nothing. The sheet only redraws when something changed, so a refresh never interrupts a tap or a scroll. The squares in a pick's game log open the same sheet for past games.

Live games show each team's chance to win, and the box score charts it through the game, with a toggle to the score margin instead (the choice is kept on that phone). The chart has the away team's side on top and the home team's below, a scale down the right (100% / 75% / 50%, or points ahead with "Tied" in the middle), the periods along the bottom and a dot at the current moment of a live game; under the margin view it lists each team's biggest lead and when. It's our own calculation from three things only: the score, the time left and who has the ball (inferred from the last play, since ESPN doesn't report possession; marked with an orange dot). Nothing about the teams, records or betting lines. It's Stern's (1994) random-walk model with neither team favored: the chance the current margin survives normal noise with a spread of 18.5 points per 48 minutes, shrinking with the square root of the time left (never counted as under 30 seconds). 18.5 best predicted the winners of the 1,231 games of 2025-26 from each quarter break (`scripts/calibrate_win_prob.py`, data in `data/quarter_scores_2025_26.json`). The ball is worth half a possession (about 0.55 points), rising to a full possession over the last 24 seconds. ESPN's free data has no shot clock.

The box score's Media tab plays ESPN's highlight clips in the page (iPhones stream them at phone quality, about 12 MB for a 100-second clip; the full-size file is about 140 MB, so it's only a fallback), shows ESPN's game recap story as text, and has Takes: what NBA writers are posting about the game on Bluesky. Highlights always come first, since there are only a few of them and there can be many takes.

Takes come from Bluesky's public search, which is free, needs no key and answers web pages directly. Only posts from about 340 NBA writers, beat reporters and analysts count: the members of public Bluesky lists of NBA media (national writers, plus team media lists for the Celtics, Bucks, Jazz, Kings, Pacers, Raptors, 76ers and Spurs), stored as account IDs in `site/writers.json` by `scripts/bsky_writers.py`, which should be rerun now and then. The page searches each team's nickname and shorthand ("Cavaliers", "Cavs") and each team's three top scorers so far (by full name when the surname is common), from 20 minutes before tip-off to 4 hours after, leaving out replies and posts Bluesky has labeled. Bluesky's search has no "or", so each name is a separate query, and it refuses its own next-page links without a login, so earlier posts are fetched by asking for posts from before the oldest one so far. A finished game is read once; while a live game's Media tab is open, the newest posts are checked every minute (about 8 KB per name), and only the takes redraw, so a playing highlight keeps playing. Tapping a writer's name opens the post on Bluesky. X is where more NBA writers post, but its API isn't free.

Each started game also gets a short story, written by rules in the page (no AI service, so no key to hide and nothing to pay for): what happened (a comeback, a run, a big quarter, a lead built, a go-ahead basket) and why (shooting and turnover gaps, a cold shooter, foul trouble), naming the players behind it, from the play-by-play text ("Tyrese Maxey makes 26-foot three point jumper"). Cards show two sentences; the box score sheet three. While the Tonight tab is open the page re-reads each live game's play-by-play about once a minute (a finished game's once), roughly 40 KB per game.

```
+------------------------------------+
| TONIGHT       6 games - 2 live now |
| You need POR and DEN (up to +3)    |
+------------------------------------+
| BIGGEST GAME   moves odds 6 pts    |
| POR @ MIL      6:00 PM   MIL -3.5  |
|  POR win:  Nick +1, you +1         |
|  MIL win:  Ryan +1                 |
|  Portland Civil War, game 41       |
+------------------------------------+
| (*) SAC @ BKN   Q2 1:30   51-49    |
|  TANK BOWL: Matt v Nick            |
|  BKN win: Matt +1                  |
|  SAC win: Nick +1                  |
+------------------------------------+
| (*) PHI @ NYK   Q3 4:12   88-84    |
|  PHI win: Matt +1                  |
|  NYK win: Ryan +1                  |
+------------------------------------+
| HOU @ MEM      6:00 PM   HOU -2.5  |
|  WIN-WIN: both want Houston        |
|  HOU win: Brian +1, Ryan +1        |
+------------------------------------+
| UTA @ GSW      8:00 PM   GSW -6.5  |
|  UTA win: Ryan +1                  |
+------------------------------------+
| DEN @ LAC      8:30 PM   DEN -4.5  |
|  DEN win: you +2 (both picks)      |
+------------------------------------+
```

### Race

```
+------------------------------------+
| THE RACE                           |
| [vs Vegas]  Points  Odds  Rank     |
| +--------------------------------+ |
| | one line per person, names at  | |
| | the line ends; zero = exactly  | |
| | on Vegas pace; drag to scrub   | |
| +--------------------------------+ |
| Jan 14                             |
| Brian +6.1  Matt +3.1  Ryan +2.1   |
| Asaf  -0.9  Nick -5.9              |
+------------------------------------+
| MOMENTS                            |
|  Dec 3   Matt takes the lead       |
|  Dec 25  Ryan goes 0-for-4         |
|  Jan 13  Brian back on top         |
|  > Replay the season               |
+------------------------------------+
```

### Draft

```
+------------------------------------+
| DRAFT BOARD     shade = vs Vegas   |
|     Ryan  Brian Matt  Nick  Asaf   |
|  1  SAS W OKC W SAC L BKN L LAC L  |
|  2  NYK W BOS W CHI L NOP L MIL L  |
|  3  MEM L HOU W PHI W DET W DEN W  |
|  4  LAL W TOR W DAL L MIN W CLE W  |
|  5  GSW L MIA W WAS L POR W CHA L  |
|  6  POR L ORL W PHX L IND W ATL W  |
+------------------------------------+
| BEAT THE BOT                       |
|  Brian 152  vs BrianBot 146   +6   |
|  Matt  149  vs MattBot  147   +2   |
|  Ryan  147  vs RyanBot  151   -4   |
|  Asaf  143  vs AsafBot  144   -1   |
|  Nick  138  vs NickBot  142   -4   |
+------------------------------------+
| PORTLAND CIVIL WAR    POR 18-22    |
|  Ryan (L) 22   Nick (W) 18         |
+------------------------------------+
| THE PICK NOBODY MADE               |
|  UTA L would have 24 by now        |
+------------------------------------+
| STEAL  POR L   #30 Ryan   +2.2     |
| BUST   BKN L   #4  Nick   -3.0     |
+------------------------------------+
```

## Look and feel

- Near-black background, cards one step lighter, big condensed numbers. One compact display font for numbers and headers; everything else in the phone's own system font.
- Each person keeps one color everywhere (rows, chart lines, rooting tags). The five colors stay distinguishable for colorblind viewers.
- Team abbreviations in team colors (ESPN's feed includes them). No logo images, which keeps pages light.
- Ahead of Vegas is shaded blue and behind is shaded red. Not green against red, which colorblind viewers can't tell apart, and not orange, which is a person color.
- Points tick up when a game goes final, rows slide when ranks change, and the live dot pulses. All of it turns off when the phone's reduce-motion setting is on.
- Tap targets at least 44 px; body text at least 15 px; numbers use fixed-width digits so columns don't jiggle.

## Trash talk

One headline at a time on the home screen. Headlines come from templates triggered by the data (streaks, lead changes, bot comparisons, upsets, milestones) and stay friendly. Examples:

- "RyanBot is beating Ryan by 4. The robots are coming."
- "The Kings won again. Matt is not okay."
- "Brian's Thunder are 31-9. Of course they are."
- "Portland Civil War: Ryan leads Nick 22-18."

## Data and updates

```
GitHub Action every ~15 min during game hours, plus a morning catch-up
  -> pulls results from ESPN, recomputes standings, odds, history
  -> commits a ~20 KB data.json -> GitHub Pages serves the site
Phone opens the site
  -> shows data.json instantly
  -> if games are live: polls ESPN every 30 s, adds finals immediately
```

- Source: `site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=YYYYMMDD`. Free, no key, readable directly by a web page, and it includes DraftKings spreads. It serves one day per request (date ranges are rejected), which is why the season history is precomputed into data.json.
- The NBA's own feeds (`cdn.nba.com`) refuse these requests, so ESPN is the only source.
- The page polls only while a game is live and the page is visible.
- One HTML file with inline CSS and JS, one data file, one small font. Charts are hand-drawn SVG; no frameworks or chart libraries.

## Mockup

A clickable mockup filled with a sample mid-January season is published privately at https://claude.ai/artifact/TYyVRyxNsCqH2FQ4Z5a1BQ.

- Page: `mockup/index.html`. Data: `mockup/sample-data.js`, generated by `python scripts/make_sample_data.py 64`.
- Local preview: start the `mockup` server in `.claude/launch.json` and open `/preview.html` (rebuild it with `python scripts/build_preview.py`).
- The sample's numbers come from the model, so some differ from the sketches above: title odds, bot totals, and which game is tonight's biggest.

## Later

- What-if mode: pick winners of upcoming games and watch title odds move.
- Share button that sends the standings to the group chat.
- Lead-change alerts.
- Past seasons and career wins above Vegas, if old drafts turn up.

## Preseason lines

BetMGM win totals, table last modified 2026-10-19 ([source](https://sports.betmgm.com/en/blog/nba/nba-odds-predictions-season-win-totals-bm23/)):

ATL 43.5, BOS 51.5, BKN 24.5, CHA 38.5, CHI 29.5, CLE 48.5, DAL 34.5, DEN 49.5, DET 49.5, GSW 36.5, HOU 48.5, IND 44.5, LAC 28.5, LAL 46.5, MEM 29.5, MIA 46.5, MIL 25.5, MIN 48.5, NOP 28.5, NYK 52.5, OKC 62.5, ORL 43.5, PHI 49.5, PHX 40.5, POR 41.5, SAS 59.5, SAC 21.5, TOR 46.5, UTA 37.5, WAS 34.5.
