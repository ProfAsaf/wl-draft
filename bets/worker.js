/* The W/L Draft bets server: the friends' title bets, kept in one Durable Object so every phone sees
   the same ledger at the same moment. There's no money and no stake: a bet is one friend saying a
   player will (yes) or won't (no) finish first, and another friend taking the other side. The page's
   title odds at the time are written down with it, read from the site's own data.json, so nobody can
   post an offer at made-up odds. Every request carries the group code (the GROUP_CODE secret). */

const SITE = 'https://profasaf.github.io';
const DATA = `${SITE}/wl-draft/data.json`;
const ORIGINS = [SITE, 'http://localhost:8766'];
const MAX_OPEN = 20;  // open offers per person, so one bad night can't flood the board

const cors = (origin) => ({
  'Access-Control-Allow-Origin': origin,
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-Group-Code',
  Vary: 'Origin',
});
const json = (body, status, origin) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...cors(origin) },
});

export default {
  async fetch(request, env) {
    const origin = ORIGINS.includes(request.headers.get('Origin')) ? request.headers.get('Origin') : SITE;
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors(origin) });
    const code = (request.headers.get('X-Group-Code') || '').trim().toLowerCase();
    if (!env.GROUP_CODE || code !== String(env.GROUP_CODE).trim().toLowerCase()) return json({ error: 'wrong group code' }, 401, origin);
    const ledger = env.MARKET.get(env.MARKET.idFromName('ledger'));
    const res = await ledger.fetch(request);
    return json(await res.json(), res.status, origin);
  },
};

export class Market {
  constructor(ctx) {
    this.ctx = ctx;
  }

  // Who's in the league and each one's title odds right now, from the site's data.json.
  async odds() {
    const r = await fetch(DATA, { cf: { cacheTtl: 60 } });
    if (!r.ok) throw new Error('data.json ' + r.status);
    const d = await r.json();
    return new Map(d.people.map((p, s) => [p.name, d.oddsNow[s]]));
  }

  async fetch(request) {
    const url = new URL(request.url);
    const bets = (await this.ctx.storage.get('bets')) || [];
    const done = async (status = 200) => {
      await this.ctx.storage.put('bets', bets);
      return Response.json({ bets: bets.filter((b) => b.status !== 'canceled') }, { status });
    };
    if (request.method === 'GET' && url.pathname === '/bets') {
      return Response.json({ bets: bets.filter((b) => b.status !== 'canceled') });
    }
    if (request.method !== 'POST') return Response.json({ error: 'not found' }, { status: 404 });

    let body;
    try { body = await request.json(); } catch (e) { return Response.json({ error: 'bad request' }, { status: 400 }); }
    let odds;
    try { odds = await this.odds(); } catch (e) { return Response.json({ error: 'odds unavailable' }, { status: 503 }); }
    const by = String(body.by || '');
    if (!odds.has(by)) return Response.json({ error: 'who are you?' }, { status: 400 });
    const now = new Date().toISOString();

    // Post an offer: "<by> says <player> will / won't finish first".
    if (url.pathname === '/bets') {
      const player = String(body.player || ''), side = body.side === 'no' ? 'no' : body.side === 'yes' ? 'yes' : null;
      if (!odds.has(player) || !side) return Response.json({ error: 'bad bet' }, { status: 400 });
      if (bets.filter((b) => b.by === by && b.status === 'open').length >= MAX_OPEN) return Response.json({ error: 'too many open offers' }, { status: 429 });
      bets.push({ id: crypto.randomUUID().slice(0, 8), by, player, side, odds: odds.get(player), at: now, status: 'open' });
      return done(201);
    }

    // Take the other side of an open offer, or cancel your own.
    const m = /^\/bets\/([\w-]+)\/(take|cancel)$/.exec(url.pathname);
    const bet = m && bets.find((b) => b.id === m[1]);
    if (!bet) return Response.json({ error: 'no such bet' }, { status: 404 });
    if (bet.status !== 'open') return Response.json({ error: 'already ' + bet.status }, { status: 409 });
    if (m[2] === 'take') {
      if (by === bet.by) return Response.json({ error: 'that one is yours' }, { status: 409 });
      Object.assign(bet, { status: 'taken', taker: by, takenAt: now, takenOdds: odds.get(bet.player) });
    } else {
      if (by !== bet.by) return Response.json({ error: 'only ' + bet.by + ' can cancel it' }, { status: 403 });
      Object.assign(bet, { status: 'canceled', canceledAt: now });
    }
    return done();
  }
}
