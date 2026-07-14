param(
    [Parameter(Position = 0)]
    [string]$Command = "help",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$ArgsList,

    [string]$ComposeFile = "docker-compose.local.yml"
)

$ErrorActionPreference = "Stop"

function Show-Usage {
    Write-Host "dutils.ps1 - local docker compose utility"
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  ./dutils.ps1 <command> [args...]"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  redeploy <service...>       Build (no-cache) + up --force-recreate --no-deps"
    Write-Host "  build <service...>          Build service(s) (cached)"
    Write-Host "  rebuild <service...>        Build service(s) with --no-cache"
    Write-Host "  up [service...]             Start service(s) in detached mode"
    Write-Host "  down                        Stop and remove containers/networks"
    Write-Host "  restart <service...>        Restart service(s)"
    Write-Host "  logs <service> [--tail N]   Show logs (defaults: --tail 200 -f)"
    Write-Host "  ps [service...]             Show compose service status"
    Write-Host "  pull [service...]           Pull image(s)"
    Write-Host "  exec <service> <cmd...>     Execute a command in a running container"
    Write-Host "  config                      Show resolved compose config"
    Write-Host "  help                        Show this help"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -ComposeFile <path>         Override compose file (default: docker-compose.local.yml)"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  ./dutils.ps1 redeploy frontend"
    Write-Host "  ./dutils.ps1 logs backend --tail 100"
    Write-Host "  ./dutils.ps1 exec backend python manage.py migrate"
}

function Resolve-ComposePath([string]$PathValue) {
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return Join-Path $PSScriptRoot $PathValue
}

function Invoke-Compose([string[]]$ComposeArgs) {
    $composePath = Resolve-ComposePath $ComposeFile
    if (-not (Test-Path $composePath)) {
        throw "Compose file not found: $composePath"
    }

    Write-Host "> docker compose -f $composePath $($ComposeArgs -join ' ')"
    & docker compose -f $composePath @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE"
    }
}

switch ($Command.ToLowerInvariant()) {
    "redeploy" {
        if (-not $ArgsList -or $ArgsList.Count -eq 0) {
            throw "redeploy requires at least one service name"
        }
        foreach ($service in $ArgsList) {
            Invoke-Compose -ComposeArgs @("build", "--no-cache", $service)
            Invoke-Compose -ComposeArgs @("up", "-d", "--force-recreate", "--no-deps", $service)
        }
    }

    "build" {
        if (-not $ArgsList -or $ArgsList.Count -eq 0) {
            throw "build requires at least one service name"
        }
        Invoke-Compose -ComposeArgs (@("build") + $ArgsList)
    }

    "rebuild" {
        if (-not $ArgsList -or $ArgsList.Count -eq 0) {
            throw "rebuild requires at least one service name"
        }
        Invoke-Compose -ComposeArgs (@("build", "--no-cache") + $ArgsList)
    }

    "up" {
        if ($ArgsList -and $ArgsList.Count -gt 0) {
            Invoke-Compose -ComposeArgs (@("up", "-d") + $ArgsList)
        }
        else {
            Invoke-Compose -ComposeArgs @("up", "-d")
        }
    }

    "down" {
        Invoke-Compose -ComposeArgs @("down")
    }

    "restart" {
        if (-not $ArgsList -or $ArgsList.Count -eq 0) {
            throw "restart requires at least one service name"
        }
        Invoke-Compose -ComposeArgs (@("restart") + $ArgsList)
    }

    "logs" {
        if (-not $ArgsList -or $ArgsList.Count -eq 0) {
            throw "logs requires a service name"
        }

        if ($ArgsList -notcontains "--tail") {
            Invoke-Compose -ComposeArgs (@("logs", "-f", "--tail", "200") + $ArgsList)
        }
        else {
            Invoke-Compose -ComposeArgs (@("logs", "-f") + $ArgsList)
        }
    }

    "ps" {
        if ($ArgsList -and $ArgsList.Count -gt 0) {
            Invoke-Compose -ComposeArgs (@("ps") + $ArgsList)
        }
        else {
            Invoke-Compose -ComposeArgs @("ps")
        }
    }

    "pull" {
        if ($ArgsList -and $ArgsList.Count -gt 0) {
            Invoke-Compose -ComposeArgs (@("pull") + $ArgsList)
        }
        else {
            Invoke-Compose -ComposeArgs @("pull")
        }
    }

    "exec" {
        if (-not $ArgsList -or $ArgsList.Count -lt 2) {
            throw "exec requires: exec <service> <command...>"
        }
        Invoke-Compose -ComposeArgs (@("exec", "-T") + $ArgsList)
    }

    "config" {
        Invoke-Compose -ComposeArgs @("config")
    }

    "help" {
        Show-Usage
    }

    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Show-Usage
        exit 1
    }
}
