param(
    [string]$Bind = $env:BIND,
    [string]$Source = $env:SOURCE,
    [string]$Carrier = $env:CARRIER,
    [string]$CacheSeconds = $env:CACHE_SECONDS,
    [string]$PythonBin = $env:PYTHON_BIN
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Bind)) { $Bind = "127.0.0.1:18080" }
if ([string]::IsNullOrWhiteSpace($Source)) { $Source = "android" }
if ([string]::IsNullOrWhiteSpace($Carrier)) { $Carrier = "all" }
if ([string]::IsNullOrWhiteSpace($CacheSeconds)) { $CacheSeconds = "300" }

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if ([string]::IsNullOrWhiteSpace($PythonBin)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        $PythonBin = $cmd.Source
    } else {
        $py = Get-Command py -ErrorAction SilentlyContinue
        if (-not $py) { throw "Python not found. Install Python 3.10+ or set PYTHON_BIN." }
        $PythonBin = $py.Source
    }
}

$Script = Join-Path $ProjectDir "mahsa_bridge.py"
$StdOut = Join-Path $LogDir "stdout.log"
$StdErr = Join-Path $LogDir "stderr.log"

if ((Split-Path -Leaf $PythonBin).ToLowerInvariant() -eq "py.exe") {
    & $PythonBin -3 $Script --serve $Bind --source $Source --carrier $Carrier --cache-seconds $CacheSeconds 1>> $StdOut 2>> $StdErr
} else {
    & $PythonBin $Script --serve $Bind --source $Source --carrier $Carrier --cache-seconds $CacheSeconds 1>> $StdOut 2>> $StdErr
}
