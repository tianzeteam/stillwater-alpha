# Vendored dependencies

## bitget/
Official Bitget V3 Open API Python SDK, vendored from
`BitgetLimited/v3-bitget-api-sdk` (`bitget-python-sdk-api/bitget`), master branch,
downloaded 2026-09-09. The upstream repo carries no LICENSE file as of that date;
code remains (c) Bitget. No local modifications — the data layer wraps it
(`src/data.py`) and suppresses the SDK's debug `print()`s via stdout redirect.
Public market-data endpoints only; credentials are empty strings.
