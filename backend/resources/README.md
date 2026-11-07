# Offline country database

`dbip-country-lite.mmdb.gz` is the unmodified November 2026 DB-IP Country Lite
MMDB download. Country results are approximate network locations, not a
person's nationality or exact location. Anycast and VPN addresses may differ.

- Source: https://db-ip.com/db/download/ip-to-country-lite
- Download: https://download.db-ip.com/free/dbip-country-lite-2026-11.mmdb.gz
- License: Creative Commons Attribution 4.0 International
  (https://creativecommons.org/licenses/by/4.0/).
- Attribution: IP Geolocation by DB-IP (https://db-ip.com).
- Compressed SHA-256: `75fe430010f6d38a8c4331c202bf0df6ce3221a6e6d823b9e5a6d951e4cf9758`
- Uncompressed MD5 (verified against the publisher): `5974b336a7409ec854f67eacd52c2061`

HomeTools displays attribution on the shared admin country map, including
results exported from DevTools and GlobalAssetHistory. Visitor addresses are
looked up locally and are not sent to DB-IP or persisted by this lookup.

To update the monthly snapshot, download the new MMDB gzip from the source
page, verify its uncompressed checksum against that page, replace this file,
update this provenance, run the GeoIP tests, then restart workers. An updated
GeoIP-compatible MMDB (plain or gzip) can instead be supplied with
`GEOIP_DATABASE=/absolute/path/to/country.mmdb`.
