param(
    [Parameter(Mandatory=$true)][string]$PromptFile,
    [string]$Model = "claude-sonnet-4.5"
)
$ErrorActionPreference = "Stop"
# Pipe prompt via stdin — passing multiline strings via -p truncates at newlines.
Get-Content -Raw -Encoding UTF8 $PromptFile | & 'C:\.tools\.npm-global\copilot.cmd' --allow-all-tools --model $Model
exit $LASTEXITCODE
