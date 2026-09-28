# External analysis tooling

The harness now supplies `SteamAppId` and `SteamGameId` for native Steam
targets from the target manifest. These variables provide launch context to an
already authenticated Steam client; they are not an authentication bypass.
Native K2 must still be launched with a licensed, logged-in client.

For binary work, two optional analysis tools were evaluated:

* ReAgent (`re-agent`) can produce bounded manifests and export evidence with
  `re-agent plan`, `re-agent evidence --manifest`, and `re-agent status
  --manifest`. Its candidate source remains advisory until the existing
  compile, byte/signature, and live harness gates pass.
* AgentDecompile CLI can run headlessly against a configured Ghidra backend,
  for example `agentdecompile-cli --binary <path> search-symbols --query
  MainLoop` and `get-functions --identifier <name>`. These queries are useful
  for locating cross-build candidates; they do not authorize address-table
  changes without independent byte evidence.

The repository keeps the current generated tables and adjudication records as
the source of truth. External tool output should be captured into a separate
research artifact and reviewed before importing any signature or codecave.
