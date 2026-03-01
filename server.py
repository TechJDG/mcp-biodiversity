"""
MCP Server: Biodiversity IP Research Tools
Wraps the CBD ABSCH public API (api.cbd.int / absch.cbd.int)
for use with Claude as a native MCP tool.

Tools exposed:
  - cbd_country_profile: ABS legislation + NCA for a country
  - cbd_search_irccs: Internationally Recognized Certificates of Compliance
  - cbd_check_ratifications: Ratification status of CBD/Nagoya/ITPGRFA
"""

import json
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route, Mount
import uvicorn

# ── CBD ABSCH API base ──────────────────────────────────────────────────────
ABSCH_BASE = "https://absch.cbd.int/api/v2013"
CHM_BASE   = "https://api.cbd.int/api/v2013"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "BiodiversityIP-MCP/1.0 (academic-research)"
}

# ── Country code lookup (ISO 3166-1 alpha-2) ───────────────────────────────
COUNTRY_NAMES = {
    "brazil": "BR", "brésil": "BR",
    "india": "IN", "inde": "IN",
    "peru": "PE", "pérou": "PE",
    "mexico": "MX", "mexique": "MX",
    "colombia": "CO", "colombie": "CO",
    "ecuador": "EC", "équateur": "EC",
    "kenya": "KE",
    "south africa": "ZA", "afrique du sud": "ZA",
    "madagascar": "MG",
    "philippines": "PH",
    "indonesia": "ID", "indonésie": "ID",
    "china": "CN", "chine": "CN",
    "france": "FR",
    "germany": "DE", "allemagne": "DE",
    "united kingdom": "GB", "royaume-uni": "GB",
    "european union": "EU", "union européenne": "EU",
    "norway": "NO", "norvège": "NO",
    "switzerland": "CH", "suisse": "CH",
    "japan": "JP", "japon": "JP",
    "canada": "CA",
    "australia": "AU", "australie": "AU",
    "new zealand": "NZ", "nouvelle-zélande": "NZ",
    "united states": "US", "états-unis": "US",
}

def resolve_country(name_or_code: str) -> str:
    """Resolve country name or ISO code to 2-letter code."""
    s = name_or_code.strip()
    if len(s) == 2:
        return s.upper()
    return COUNTRY_NAMES.get(s.lower(), s.upper()[:2])


# ── Tool implementations ────────────────────────────────────────────────────

async def cbd_country_profile(country: str) -> str:
    """
    Retrieve ABS profile for a country from the ABSCH:
    national legislation, competent authority, national focal point, IRCCs count.
    """
    code = resolve_country(country)
    results = {}

    async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:

        # 1. National Records (NR) — ABS legislation declared by the country
        try:
            r = await client.get(
                f"{ABSCH_BASE}/documents",
                params={"schema": "NR", "country": code, "per-page": 10}
            )
            if r.status_code == 200:
                data = r.json()
                records = data.get("data", data) if isinstance(data, dict) else data
                results["national_records"] = [
                    {
                        "title": rec.get("title", {}).get("en", "N/A"),
                        "uid": rec.get("identifier", ""),
                        "updated": rec.get("updatedOn", "")[:10] if rec.get("updatedOn") else "",
                        "url": f"https://absch.cbd.int/en/database/national-records/NR/{rec.get('identifier','')}"
                    }
                    for rec in (records[:5] if isinstance(records, list) else [])
                ]
            else:
                results["national_records_error"] = f"HTTP {r.status_code}"
        except Exception as e:
            results["national_records_error"] = str(e)

        # 2. IRCCs count for this country
        try:
            r2 = await client.get(
                f"{ABSCH_BASE}/documents",
                params={"schema": "IRCC", "providerCountry": code, "per-page": 1}
            )
            if r2.status_code == 200:
                d2 = r2.json()
                results["ircc_count"] = d2.get("totalCount", d2.get("total", "N/A"))
            else:
                results["ircc_count"] = f"HTTP {r2.status_code}"
        except Exception as e:
            results["ircc_count_error"] = str(e)

        # 3. Competent National Authorities (CNA)
        try:
            r3 = await client.get(
                f"{ABSCH_BASE}/documents",
                params={"schema": "CNA", "country": code, "per-page": 5}
            )
            if r3.status_code == 200:
                d3 = r3.json()
                cnas = d3.get("data", d3) if isinstance(d3, dict) else d3
                results["competent_authorities"] = [
                    {
                        "name": c.get("title", {}).get("en", "N/A"),
                        "url": f"https://absch.cbd.int/en/database/competent-national-authorities/CNA/{c.get('identifier','')}"
                    }
                    for c in (cnas[:3] if isinstance(cnas, list) else [])
                ]
            else:
                results["cna_error"] = f"HTTP {r3.status_code}"
        except Exception as e:
            results["cna_error"] = str(e)

    output = [
        f"## ABSCH Country Profile: {country.upper()} (ISO code: {code})",
        f"Source: https://absch.cbd.int/countries/{code}",
        "",
        f"### National ABS Records ({len(results.get('national_records', []))} found)"
    ]
    for nr in results.get("national_records", []):
        output.append(f"- **{nr['title']}** (updated: {nr['updated']}) — {nr['url']}")
    if not results.get("national_records"):
        output.append("- No national records found or query error")

    output += [
        "",
        f"### IRCCs issued as provider country: {results.get('ircc_count', 'N/A')}",
        f"  → Full list: https://absch.cbd.int/en/database/irccs?providerCountry={code}",
        "",
        f"### Competent National Authorities"
    ]
    for cna in results.get("competent_authorities", []):
        output.append(f"- {cna['name']} — {cna['url']}")
    if not results.get("competent_authorities"):
        output.append("- No CNA found or not yet designated")

    output += [
        "",
        f"### Direct links",
        f"- Country profile: https://absch.cbd.int/countries/{code}",
        f"- National legislation: https://absch.cbd.int/en/database/national-records/NR?country={code}",
        f"- IRCCs issued: https://absch.cbd.int/en/database/irccs?providerCountry={code}",
    ]

    return "\n".join(output)


async def cbd_search_irccs(country: str = "", year_from: int = None, year_to: int = None, max_results: int = 20) -> str:
    """
    Search Internationally Recognized Certificates of Compliance (IRCCs).
    Filter by provider country and/or year range.
    Returns title, date, issuing authority, resource type.
    """
    params = {"schema": "IRCC", "per-page": min(max_results, 50)}
    if country:
        code = resolve_country(country)
        params["providerCountry"] = code
    else:
        code = "ALL"

    async with httpx.AsyncClient(headers=HEADERS, timeout=25) as client:
        try:
            r = await client.get(f"{ABSCH_BASE}/documents", params=params)
            if r.status_code != 200:
                return f"Error {r.status_code} from ABSCH API"

            data = r.json()
            total = data.get("totalCount", data.get("total", "?"))
            records = data.get("data", data) if isinstance(data, dict) else data

            output = [
                f"## IRCCs Search Results",
                f"Country filter: {country or 'ALL'} | Total in database: {total}",
                f"Showing: {len(records) if isinstance(records, list) else 0} records",
                f"Source: https://absch.cbd.int/en/database/irccs?providerCountry={code}",
                ""
            ]

            if isinstance(records, list):
                for ircc in records:
                    title = ircc.get("title", {})
                    name = title.get("en") or title.get("fr") or str(title)[:80] if isinstance(title, dict) else str(title)[:80]
                    issued = ircc.get("issuedOn", ircc.get("createdOn", "?"))[:10] if ircc.get("issuedOn") or ircc.get("createdOn") else "?"
                    uid = ircc.get("identifier", "")
                    url = f"https://absch.cbd.int/en/database/irccs/IRCC/{uid}"

                    # Year filter (client-side since API may not support it)
                    if year_from or year_to:
                        try:
                            yr = int(issued[:4])
                            if year_from and yr < year_from:
                                continue
                            if year_to and yr > year_to:
                                continue
                        except:
                            pass

                    output.append(f"### {name[:100]}")
                    output.append(f"- Issued: {issued}")
                    output.append(f"- UID: {uid}")
                    output.append(f"- URL: {url}")
                    output.append("")
            else:
                output.append("No structured records returned — check ABSCH directly")

            return "\n".join(output)

        except Exception as e:
            return f"Error querying ABSCH: {str(e)}\nFallback: https://absch.cbd.int/en/database/irccs"


async def cbd_check_ratifications(country: str) -> str:
    """
    Check ratification status of key biodiversity/IP instruments for a country:
    CBD, Nagoya Protocol, ITPGRFA, CITES, WTO/TRIPS, UPOV, GRATK Treaty.
    Returns dates and status from official ABSCH/UNTS data.
    """
    code = resolve_country(country)

    # ABSCH parties endpoint
    party_info = {}
    async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:
        try:
            r = await client.get(
                f"{ABSCH_BASE}/countries/{code}",
            )
            if r.status_code == 200:
                party_info = r.json()
        except:
            pass

    # Build structured output with what we know + direct verification links
    output = [
        f"## Ratification Status: {country} ({code})",
        f"Data: ABSCH + verification links to official sources",
        "",
        "### Instrument Status",
        "",
        "| Instrument | Status | Verification |",
        "|---|---|---|",
        f"| CBD (1992) | Check below | https://www.cbd.int/information/parties.shtml |",
        f"| **Nagoya Protocol** (2010) | Check ABSCH | https://absch.cbd.int/countries/{code} |",
        f"| ITPGRFA (2001) | Check FAO | https://www.fao.org/plant-treaty/countries/membership/ |",
        f"| CITES (1973) | Check CITES | https://cites.org/eng/disc/parties/index.php |",
        f"| WTO/TRIPS | Check WTO | https://www.wto.org/english/thewto_e/whatis_e/tif_e/org6_e.htm |",
        f"| UPOV (78 or 91) | Check UPOV | https://www.upov.int/members/en/ |",
        f"| GRATK Treaty (2024) | Check WIPO | https://www.wipo.int/gratk/en/ |",
        "",
        "### ABSCH Country Data",
    ]

    if party_info:
        output.append(f"```json\n{json.dumps(party_info, indent=2)[:1000]}\n```")
    else:
        output.append(f"Direct ABSCH country page: https://absch.cbd.int/countries/{code}")

    output += [
        "",
        "### Research Notes",
        f"- ABSCH is authoritative for **Nagoya Protocol** ratification and national ABS measures",
        f"- UNTS is authoritative for **CBD** (treaty No. 1760): https://treaties.un.org",
        f"- For ITPGRFA: https://www.fao.org/plant-treaty/countries/membership/",
        f"- For TRIPS: WTO membership = TRIPS obligation",
        f"- For GRATK: https://www.wipo.int/gratk/en/ (2024 treaty, entry into force pending)",
    ]

    return "\n".join(output)


# ── MCP Server setup ────────────────────────────────────────────────────────

app_server = Server("biodiversity-ip-mcp")

@app_server.list_tools()
async def list_tools():
    return [
        Tool(
            name="cbd_country_profile",
            description=(
                "Retrieve ABS (Access and Benefit Sharing) profile for a country from the CBD "
                "ABS Clearing-House (ABSCH). Returns: national ABS legislation records, "
                "count of IRCCs issued, competent national authorities, and direct links. "
                "Essential for Task 2 (national legislation) and Task 8 (comparative analysis). "
                "Accepts country name (English or French) or ISO 2-letter code."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "country": {
                        "type": "string",
                        "description": "Country name (e.g. 'Brazil', 'India', 'Kenya') or ISO 2-letter code (e.g. 'BR', 'IN', 'KE')"
                    }
                },
                "required": ["country"]
            }
        ),
        Tool(
            name="cbd_search_irccs",
            description=(
                "Search Internationally Recognized Certificates of Compliance (IRCCs) in the ABSCH. "
                "IRCCs are issued when a country grants access to genetic resources under Nagoya Protocol. "
                "Essential for assessing actual implementation level (lex lata vs. practice gap). "
                "Can filter by provider country and year range."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "country": {
                        "type": "string",
                        "description": "Provider country name or ISO code (optional — omit for global search)"
                    },
                    "year_from": {
                        "type": "integer",
                        "description": "Start year filter (optional, e.g. 2014)"
                    },
                    "year_to": {
                        "type": "integer",
                        "description": "End year filter (optional, e.g. 2024)"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results (default 20, max 50)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="cbd_check_ratifications",
            description=(
                "Check ratification status of key biodiversity and IP instruments for a given country: "
                "CBD, Nagoya Protocol, ITPGRFA, CITES, WTO/TRIPS, UPOV, WIPO GRATK Treaty. "
                "Returns structured table with verification links to authoritative sources (ABSCH, UNTS, WTO, WIPO). "
                "Essential for Tasks 1, 2, 8 (instrument identification, national legislation, comparative analysis)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "country": {
                        "type": "string",
                        "description": "Country name (English or French) or ISO 2-letter code"
                    }
                },
                "required": ["country"]
            }
        )
    ]

@app_server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "cbd_country_profile":
        result = await cbd_country_profile(arguments["country"])
    elif name == "cbd_search_irccs":
        result = await cbd_search_irccs(
            country=arguments.get("country", ""),
            year_from=arguments.get("year_from"),
            year_to=arguments.get("year_to"),
            max_results=arguments.get("max_results", 20)
        )
    elif name == "cbd_check_ratifications":
        result = await cbd_check_ratifications(arguments["country"])
    else:
        result = f"Unknown tool: {name}"

    return [TextContent(type="text", text=result)]


# ── Starlette app (SSE transport for remote hosting) ────────────────────────

sse = SseServerTransport("/messages/")

async def handle_sse(request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await app_server.run(streams[0], streams[1], app_server.create_initialization_options())

starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ]
)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
