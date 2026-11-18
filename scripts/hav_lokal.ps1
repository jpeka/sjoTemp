# Kör HaV-insamlingen på din egen dator och skickar resultatet till GitHub.
#
# HaV:s server tar inte emot anslutningar från GitHub Actions, men fungerar från svenska nät.
# Skriptet uppdaterar repot, hämtar HaV:s badvattenprov, committar och pushar.
# Pushen startar automatiskt en ny byggning av webbsidan.
#
# Första gången:   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\sjoTemp\scripts\hav_lokal.ps1"
# Schemalägg:      se README.md, avsnittet "HaV på din dator".

$ErrorActionPreference = "Stop"
$repo = Join-Path $env:USERPROFILE "sjoTemp"
$log = Join-Path $repo "hav_lokal.log"

# Hitta Python: först i PATH, annars Anaconda i hemmappen.
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python -or $python -like "*WindowsApps*") {
    $python = Join-Path $env:USERPROFILE "anaconda3\python.exe"
}
if (-not (Test-Path $python)) { throw "Hittar inte Python. Installera Python eller ange sökvägen i skriptet." }

if (-not (Test-Path (Join-Path $repo ".git"))) {
    git clone https://github.com/jpeka/sjoTemp.git $repo
}
Set-Location $repo

Start-Transcript -Path $log -Append | Out-Null
try {
    git pull --rebase --quiet
    & $python scripts/collect.py --source hav
    git add data
    if (git status --porcelain data) {
        git -c user.name="jpeka" -c user.email="jpeka@users.noreply.github.com" commit --quiet -m "HaV-prov (lokal körning) $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
        git pull --rebase --quiet
        git push --quiet
        Write-Output "Nya HaV-värden pushade."
    } else {
        Write-Output "Inga nya HaV-värden."
    }
} finally {
    Stop-Transcript | Out-Null
}
