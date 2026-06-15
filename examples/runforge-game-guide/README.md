# RunForge Game Guide MVP

RunForge is a game guide and strategy-tool site prototype built from Agent Reach research. It starts with Balatro seed/build workflows and is designed to expand into more strategy-heavy games.

## Product Direction

- First game hub: Balatro / 小丑牌
- First tool: seed advisor for Steel King / Baron / Mime routes
- Content model: guide pages, seed pages, build pages, database pages, and tool pages
- Growth model: SEO long-tail traffic, seed submissions, newsletter capture, affiliate/deal routing, and paid advanced tools

## Agent Reach Research Sources

Agent Reach channels used:

- Exa semantic web search
- Bilibili public search API
- GitHub search
- Web page reading through Jina Reader
- Vercel domain availability checks

Useful Balatro references found:

- GAMES.GG Baron + Mime guide: https://games.gg/balatro/guides/baron-mime-balatro-build/
- GAMES.GG Steel Cards guide: https://games.gg/balatro/guides/balatro-steel-cards-guide/
- Balatro Seeds: https://balatroseeds.com/
- BalatroSeed Chinese routes: https://balatroseed.net/zh
- EFHIII calculator: https://efhiii.github.io/balatro-calculator/
- Blueprint seed analyzer: https://github.com/miaklwalker/Blueprint
- Balatro4j seed analyzer/finder: https://github.com/alex-cova/balatro4j
- Ouija seed finder: https://github.com/OptimusPi/Ouija

Seed/build examples included in the MVP:

- `9OUU79` - Steel King practice route
- `U8RJYV6N` - high-ceiling legendary route into Steel King
- `6B678B4W` - DNA / Baron / Mime route
- `1U9CYPIT` - teaching-friendly Baron + Mime route

The MVP labels route output as product-demo guidance. A production version should connect a real seed parser before claiming exact shop or pack outcomes.

## Domain Candidates

Checked through Vercel domain availability on 2026-06-15.

Best low-cost `.com` candidates:

- `deckroutes.com` - available, $11.25/year
- `buildroutes.com` - available, $11.25/year
- `stratroutes.com` - available, $11.25/year
- `pixelroutes.com` - available, $11.25/year
- `gameguideforge.com` - available, $11.25/year
- `playbookgg.com` - available, $11.25/year

Best `.gg` candidates:

- `runforge.gg` - available, $129.99/year
- `seedforge.gg` - available, $129.99/year
- `seedroute.gg` - available, $129.99/year
- `guideforge.gg` - available, $129.99/year
- `routedeck.gg` - available, $129.99/year

Recommendation:

- Buy `deckroutes.com` if you want the cheapest domain that still fits Balatro and future deckbuilder/roguelike games.
- Buy `runforge.gg` if you want to preserve the current RunForge brand and accept the higher `.gg` renewal cost.

## Game Categories Worth Targeting

Best starting niche:

- Roguelike deckbuilders and strategy roguelites

Why:

- Players search for builds, seeds, synergies, unlocks, route planning, and calculators.
- Tool pages have better retention than plain news.
- Balatro, Slay the Spire, Monster Train, Backpack Battles, and similar games all support repeatable content templates.

Candidate game hubs:

- Balatro
- Slay the Spire / Slay the Spire 2
- Monster Train 2
- Backpack Battles
- Die in the Dungeon
- Gambonanza
- Sol Cesto
- Hades II

## Development

```bash
npm install
npm run dev
npm run build
```

## Deploy

This is a Vite app. Import the folder into Vercel and set:

- Framework preset: Vite
- Build command: `npm run build`
- Output directory: `dist`

