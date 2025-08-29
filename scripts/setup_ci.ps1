param(
    [string]$OwnerRepo,
    [switch]$Open
)

$ErrorActionPreference = 'Stop'

function Get-OwnerRepoFromGit {
    try {
        $url = (git remote get-url origin) 2>$null
        if (-not $url) { $url = (git remote -v | Select-String -Pattern 'origin\s+(\S+)' | ForEach-Object { $_.Matches[0].Groups[1].Value } | Select-Object -First 1) }
        if (-not $url) { return $null }
        # Support SSH and HTTPS
        if ($url -match '^git@github.com:(.+?)\.git$') { return $Matches[1] }
        if ($url -match '^https?://github.com/(.+?)(?:\.git)?$') { return $Matches[1] }
        return $null
    } catch {
        return $null
    }
}

function Update-ReadmeBadge([string]$OwnerRepo) {
    $readmePath = Join-Path -Path (Get-Location) -ChildPath 'README.md'
    if (-not (Test-Path $readmePath)) {
        Write-Host "README.md не найден по пути $readmePath" -ForegroundColor Yellow
        return $false
    }

    $content = Get-Content -Raw -Path $readmePath
    $badgePattern = '\[!\[CI\]\(https://github.com/[^\)]*/actions/workflows/ci.yml/badge.svg\?branch=main\)\]\(https://github.com/[^\)]*/actions/workflows/ci.yml\)'
    $newBadge = "[![CI](https://github.com/$OwnerRepo/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/$OwnerRepo/actions/workflows/ci.yml)"

    if ($content -match $badgePattern) {
        $updated = [regex]::Replace($content, $badgePattern, [System.Text.RegularExpressions.Regex]::Escape($newBadge).Replace('\\', '\\\\'))
    } else {
        # Попробуем заменить только OWNER/REPO
        $updated = $content -replace 'OWNER/REPO', [System.Text.RegularExpressions.Regex]::Escape($OwnerRepo)
    }

    if ($updated -ne $content) {
        Copy-Item -Path $readmePath -Destination "$readmePath.bak" -Force
        Set-Content -Path $readmePath -Value $updated -Encoding UTF8
        Write-Host "README.md обновлён. Резервная копия: README.md.bak" -ForegroundColor Green
        return $true
    } else {
        Write-Host "README.md уже содержит корректный бейдж или не удалось найти шаблон для замены." -ForegroundColor Yellow
        return $false
    }
}

function Show-Links([string]$OwnerRepo) {
    $actionsUrl = "https://github.com/$OwnerRepo/actions/workflows/ci.yml"
    $branchesSettingsUrl = "https://github.com/$OwnerRepo/settings/branches"
    $repoUrl = "https://github.com/$OwnerRepo"

    Write-Host "\nПолезные ссылки:" -ForegroundColor Cyan
    Write-Host "- Репозиторий:        $repoUrl"
    Write-Host "- GitHub Actions CI:  $actionsUrl"
    Write-Host "- Branch protection:  $branchesSettingsUrl"

    if ($Open) {
        Start-Process $repoUrl
        Start-Process $actionsUrl
        Start-Process $branchesSettingsUrl
    }
}

# 1) Определяем owner/repo
if (-not $OwnerRepo -or $OwnerRepo.Trim() -eq '') {
    $OwnerRepo = Get-OwnerRepoFromGit
}

if (-not $OwnerRepo) {
    Write-Host "Не удалось определить owner/repo из git. Запустите с параметром -OwnerRepo <owner/repo>." -ForegroundColor Red
    exit 1
}

Write-Host "Использую owner/repo: $OwnerRepo" -ForegroundColor Cyan

# 2) Проверка наличия workflow файла
$workflowPath = Join-Path -Path (Get-Location) -ChildPath '.github/workflows/ci.yml'
if (-not (Test-Path $workflowPath)) {
    Write-Host "Внимание: .github/workflows/ci.yml не найден. CI бейдж будет вести на страницу, но workflow отсутствует в репозитории." -ForegroundColor Yellow
}

# 3) Обновление бейджа в README.md
Update-ReadmeBadge -OwnerRepo $OwnerRepo | Out-Null

# 4) Вывод ссылок на ручные действия
Show-Links -OwnerRepo $OwnerRepo

Write-Host "\nДальнейшие шаги:" -ForegroundColor Cyan
Write-Host "1) Откройте Branch protection и включите Required status checks для main."
Write-Host "2) Убедитесь, что первый прогон Actions прошёл, затем выберите джоб 'CI / build' в списке checks."
Write-Host "3) При необходимости запустите: git add README.md; git commit -m 'docs: update CI badge'; git push"
