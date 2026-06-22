# NowLens frontend

A Next.js (App Router) console for NowLens AI — ask grounded ServiceNow questions, search the corpus, and manage ingestion.

## Develop

```bash
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
# open http://localhost:3000
```

## Build

```bash
npm run build && npm start
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Base URL of the NowLens API (browser-side) |

## Structure

```
src/
  app/
    layout.tsx        root layout, fonts, AuthProvider
    page.tsx          → redirects to /chat
    chat/page.tsx     "Ask" — grounded, cited answers (the signature view)
    search/page.tsx   hybrid retrieval (sources only)
    admin/page.tsx    ingestion + jobs/documents (operator/admin)
    globals.css       design system
  components/         AppShell, AuthGate, AnswerCard, LensMark
  lib/                api client, types, auth context
```

## Design

The UI is built around a "lens / grounding" thesis: citations and a grounded/ungrounded
focus bar are first-class, so you always see whether an answer is backed by indexed
documentation and which passages it cited. Palette is a cool blueprint scheme (deep blue +
teal on cool paper); type pairs Space Grotesk (display), Inter (body), and JetBrains Mono
(data/citations).

Auth is handled client-side via JWT stored in `localStorage`; the API client attaches the
bearer token and surfaces the API's uniform error envelope.
