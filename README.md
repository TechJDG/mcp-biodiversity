# MCP Biodiversity IP — CBD ABSCH Tools

MCP server exposing CBD ABS Clearing-House data to Claude.

## Tools

- `cbd_country_profile` — ABS profile for a country (legislation, IRCCs, competent authority)
- `cbd_search_irccs` — Search IRCCs by country and year
- `cbd_check_ratifications` — Ratification status of CBD/Nagoya/ITPGRFA/GRATK

## Deploy on Render (free, no credit card required)

1. Upload this folder to a GitHub repository (public)
2. Go to https://render.com → "New Web Service"
3. Connect your GitHub repo
4. Settings:
   - Runtime: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `python server.py`
   - Plan: **Free**
5. Click "Create Web Service"
6. Your MCP URL: `https://[your-app].onrender.com/sse`

Note: On the free plan, the server sleeps after 15 min of inactivity.
First request after sleep takes ~10 seconds. Normal for academic use.

## Add to Claude

Claude.ai → Settings → Integrations → Add MCP server:
`https://[your-app].onrender.com/sse`
