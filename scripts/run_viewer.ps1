param(
    [string]$Scene = "generated/scenes/phase3-demo",
    [string]$Godot = $env:GODOT_BIN,
    [string]$ApiUrl = ""
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Godot) {
    $portable = Join-Path $projectRoot ".tools/godot/Godot_v4.7.2-stable_win64.exe"
    if (Test-Path -LiteralPath $portable) {
        $Godot = $portable
    } else {
        $command = Get-Command godot -ErrorAction SilentlyContinue
        if ($command) { $Godot = $command.Source }
    }
}
if (-not $Godot) {
    throw "Godot 4 was not found. Set GODOT_BIN or pass -Godot with its executable path."
}
$scenePath = if ([IO.Path]::IsPathRooted($Scene)) { $Scene } else { Join-Path $projectRoot $Scene }
if (-not $ApiUrl -and -not (Test-Path -LiteralPath (Join-Path $scenePath "manifest.json"))) {
    throw "No scene manifest at $scenePath. Run: uv run banc-explorer scene export --path <path-result.json> --output $Scene"
}
$engineArguments = @("--path", (Join-Path $projectRoot "godot"), "--")
if (Test-Path -LiteralPath (Join-Path $scenePath "manifest.json")) {
    $engineArguments += @("--scene-dir", $scenePath)
}
if ($ApiUrl) { $engineArguments += @("--api-url", $ApiUrl) }
& $Godot @engineArguments
exit $LASTEXITCODE
