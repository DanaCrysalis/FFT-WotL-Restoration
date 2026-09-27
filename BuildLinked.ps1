# Set Working Directory
Split-Path $MyInvocation.MyCommand.Path | Push-Location
[Environment]::CurrentDirectory = $PWD

# Regenerate the War of the Lions event data (scripts, text, nxd tables, textures) before publishing
python tools/build_data.py
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }

dotnet publish "./WotLCharacters.csproj" -c Release -o "$env:RELOADEDIIMODS/fftivc.npcs.wotlcharacters" /p:OutputPath="./bin/Release" /p:ReloadedILLink="true"

# Restore Working Directory
Pop-Location
