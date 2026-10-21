# Leftover dashboard (React)

A React page that calls the Leftover API: a chart of meals rescued over the last 30 days,
a table of food available now, and (after logging in with a JWT) claiming and your claims.

```bash
npm install
npm run dev      # http://localhost:5173, expects the backend on http://localhost:8000
npm run build    # production files in dist/
```

In Docker, nginx serves the built files and forwards `/api/*` to the backend set in `BACKEND_URL`.
