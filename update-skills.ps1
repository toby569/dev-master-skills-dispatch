[CmdletBinding()]
param(
    [switch]$LinksOnly,
    [switch]$NoAI,
    [string]$AgentHome
)

$arguments = @((Join-Path $PSScriptRoot 'update-skills.py'))
if ($LinksOnly) { $arguments += '--links-only' }
if ($NoAI) { $arguments += '--no-ai' }
if ($AgentHome) { $arguments += '--agent-home', $AgentHome }
$ErrorActionPreference = 'Stop'
& python @arguments
exit $LASTEXITCODE
