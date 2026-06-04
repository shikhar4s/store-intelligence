param(
    [switch]$ApiOnly,
    [switch]$WithCv,
    [switch]$SkipResourceDownload,
    [switch]$SkipModelWarmup,
    [switch]$SkipVideoDemoCheck,
    [switch]$SkipDataSeed,
    [switch]$ForceResourceRefresh
)

$ErrorActionPreference = "Stop"

$StoreArchives = @(
    @{
        Name = "Store 1"
        Url = "https://uc.hackerearth.com/he-public-ap-south-1/Store%201-20260602T101818Z-3-001ec38db8.zip"
        Target = "datasets/cctv_footage/Store 1"
        MinVideos = 4
    },
    @{
        Name = "Store 2"
        Url = "https://uc.hackerearth.com/he-public-ap-south-1/Store%202-20260602T101819Z-3-001099f208.zip"
        Target = "datasets/cctv_footage/Store 2"
        MinVideos = 4
    }
)

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message"
}

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required. Install Docker Desktop and reopen this terminal."
    }
}

function Invoke-Compose {
    if ($script:UseLegacyCompose) {
        & docker-compose @args
    } else {
        & docker compose @args
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose command failed: $($args -join ' ')"
    }
}

function Set-DotEnvValue($Name, $Value) {
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example"
    }
    $lines = @(Get-Content ".env")
    $pattern = "^$([regex]::Escape($Name))="
    $updated = $false
    $newLines = foreach ($line in $lines) {
        if ($line -match $pattern) {
            $updated = $true
            "$Name=$Value"
        } else {
            $line
        }
    }
    if (-not $updated) {
        $newLines += "$Name=$Value"
    }
    Set-Content -Path ".env" -Value $newLines -Encoding UTF8
}

function Get-DotEnvValue($Name, $Default) {
    $envValue = [Environment]::GetEnvironmentVariable($Name)
    if ($envValue) {
        return $envValue
    }
    if (Test-Path ".env") {
        $line = Get-Content ".env" | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
        if ($line) {
            return ($line -replace "^$([regex]::Escape($Name))=", "")
        }
    }
    return $Default
}

function Get-VideoCount($Path) {
    if (-not (Test-Path $Path)) {
        return 0
    }
    $extensions = @(".mp4", ".mov", ".mkv", ".avi", ".m4v")
    return @(
        Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $extensions -contains $_.Extension.ToLowerInvariant() }
    ).Count
}

function Invoke-DownloadFile($Url, $OutFile) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutFile) | Out-Null
    $oldProgress = $ProgressPreference
    $ProgressPreference = "SilentlyContinue"
    try {
        if (Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue) {
            try {
                Start-BitsTransfer -Source $Url -Destination $OutFile -ErrorAction Stop
                return
            } catch {
                Write-Host "BITS download failed, retrying with Invoke-WebRequest: $($_.Exception.Message)"
            }
        }
        Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -TimeoutSec 300
    } finally {
        $ProgressPreference = $oldProgress
    }
}

function Test-ZipReadable($ZipPath) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path $ZipPath))
    try {
        $entries = @($zip.Entries | Where-Object { -not [string]::IsNullOrWhiteSpace($_.Name) })
        if ($entries.Count -eq 0) {
            throw "Zip has no file entries."
        }
        return $entries.Count
    } finally {
        $zip.Dispose()
    }
}

function Install-StoreArchive($Spec) {
    $target = $Spec.Target
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    $existingVideos = Get-VideoCount $target
    if ((-not $ForceResourceRefresh) -and $existingVideos -ge [int]$Spec.MinVideos) {
        Write-Host "$($Spec.Name) clips already present in $target ($existingVideos videos); skipping download."
        return
    }

    $cacheDir = ".setup-cache"
    $safeName = ($Spec.Name -replace "[^A-Za-z0-9_-]", "_")
    $zipPath = Join-Path $cacheDir "$safeName.zip"
    $extractDir = Join-Path $cacheDir "extract_$safeName"

    Write-Step "Downloading $($Spec.Name) CCTV archive"
    if ($ForceResourceRefresh -or -not (Test-Path $zipPath) -or ((Get-Item $zipPath).Length -lt 1048576)) {
        Invoke-DownloadFile -Url $Spec.Url -OutFile $zipPath
    } else {
        Write-Host "Using cached archive $zipPath"
    }

    $entryCount = Test-ZipReadable $zipPath
    Write-Host "Verified zip: $entryCount file entries."

    if (Test-Path $extractDir) {
        $resolvedExtract = (Resolve-Path $extractDir).Path
        $resolvedCache = (Resolve-Path $cacheDir).Path
        if (-not $resolvedExtract.StartsWith($resolvedCache, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clear unexpected path: $resolvedExtract"
        }
        Remove-Item -LiteralPath $extractDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $extractDir | Out-Null

    Write-Step "Extracting $($Spec.Name)"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force

    $allowedExtensions = @(".mp4", ".mov", ".mkv", ".avi", ".m4v", ".png", ".jpg", ".jpeg")
    $files = Get-ChildItem -LiteralPath $extractDir -Recurse -File |
        Where-Object {
            $allowedExtensions -contains $_.Extension.ToLowerInvariant() -and
            $_.FullName -notmatch "\\__MACOSX\\"
        }
    if (-not $files) {
        throw "No CCTV media files found inside $zipPath"
    }

    foreach ($file in $files) {
        $dest = Join-Path $target $file.Name
        if ((Test-Path $dest) -and (-not $ForceResourceRefresh)) {
            $existing = Get-Item $dest
            if ($existing.Length -eq $file.Length) {
                continue
            }
        }
        Copy-Item -LiteralPath $file.FullName -Destination $dest -Force
    }

    $finalVideos = Get-VideoCount $target
    if ($finalVideos -lt [int]$Spec.MinVideos) {
        throw "$($Spec.Name) extraction produced only $finalVideos videos; expected at least $($Spec.MinVideos)."
    }
    Write-Host "$($Spec.Name) ready in $target ($finalVideos videos)."
}

function Wait-Api($ApiPort) {
    $healthUrl = "http://127.0.0.1:$ApiPort/health"
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
            Write-Host "API is ready: $($health.status)"
            return
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    Invoke-Compose logs --tail=120 api
    throw "API did not become healthy within 180 seconds."
}

function Warm-RequiredModels {
    if ($SkipModelWarmup) {
        Write-Host "Skipping model warm-up."
        return
    }
    if (-not $WithCv) {
        Write-Host "Model warm-up skipped because API-only mode is enabled."
        return
    }
    Write-Step "Warming required model weights"
    try {
        Invoke-Compose exec -T api python -c "from pipeline.model_loader import load_ultralytics_model; load_ultralytics_model('yolo11n.pt'); print('required live preview model ready: yolo11n.pt')"
    } catch {
        throw "Required model warm-up failed. Live detection will not start reliably until yolo11n.pt can be downloaded or mounted. $($_.Exception.Message)"
    }
    try {
        Invoke-Compose exec -T api python -c "from pipeline.model_loader import load_ultralytics_model; load_ultralytics_model('rtdetr-x.pt'); print('optional high-accuracy model ready: rtdetr-x.pt')"
    } catch {
        Write-Warning "Optional RT-DETR-X warm-up failed. The default live preview still works with yolo11n.pt. $($_.Exception.Message)"
    }
}

function Test-CvRuntime {
    if (-not $WithCv) {
        return
    }
    Write-Step "Verifying CV runtime inside the API container"
    try {
        Invoke-Compose exec -T api python -c "import cv2, lap; print('opencv ready:', cv2.__version__); print('lap tracker ready:', getattr(lap, '__version__', 'installed'))"
    } catch {
        throw "CV runtime could not import inside Docker. Rebuild the image after pulling the latest Dockerfile so OpenCV and tracker dependencies are installed. Original error: $($_.Exception.Message)"
    }
}

function Test-VideoDemoReadiness {
    if ($SkipVideoDemoCheck) {
        Write-Host "Skipping video-demo readiness check."
        return
    }
    if (-not $WithCv) {
        Write-Host "Video-demo readiness check skipped because API-only mode is enabled."
        return
    }
    if ($SkipModelWarmup) {
        Write-Warning "Video-demo readiness check skipped because model warm-up was skipped."
        return
    }

    Write-Step "Verifying live video-demo readiness"
    Invoke-Compose exec -T api python -m scripts.verify_video_demo `
        --input datasets/cctv_footage `
        --model yolo11n.pt `
        --tracker botsort.yaml `
        --max-clips-per-store 1 `
        --frames-per-clip 1 `
        --compact
}

function Test-VideoDemoHttpStream($ApiPort) {
    if ($SkipVideoDemoCheck) {
        return
    }
    if (-not $WithCv) {
        return
    }
    if ($SkipModelWarmup) {
        return
    }

    Write-Step "Smoke testing browser video-demo stream"
    Invoke-Compose exec -T api python -m scripts.smoke_video_stream `
        --url http://127.0.0.1:8000 `
        --model yolo11n.pt `
        --imgsz 640 `
        --stride 30 `
        --stream-fps 1 `
        --read-timeout 90 `
        --min-bytes 512
}

function Initialize-DashboardData($ApiPort) {
    if ($SkipDataSeed) {
        Write-Host "Skipping dashboard data seed."
        return
    }

    $storesUrl = "http://127.0.0.1:$ApiPort/stores"
    try {
        $stores = Invoke-RestMethod -Uri $storesUrl -TimeoutSec 10
        $eventCount = 0
        foreach ($store in $stores.stores) {
            $eventCount += [int]$store.event_count
        }
        if ($eventCount -gt 0) {
            Write-Host "Dashboard already has $eventCount events; skipping seed."
            return
        }
    } catch {
        Write-Warning "Could not inspect existing store data; will attempt seed. $($_.Exception.Message)"
    }

    Write-Step "Seeding dashboard data from discovered CCTV clips"
    try {
        Invoke-Compose exec -T api python -m pipeline.detect --input datasets/cctv_footage --output /tmp/bootstrap_events.jsonl --force-fallback
        Invoke-Compose exec -T api python -m pipeline.replay /tmp/bootstrap_events.jsonl --url http://127.0.0.1:8000/events/ingest --speed 100 --batch-size 100
    } catch {
        Write-Warning "CCTV fallback seed failed; using synthetic demo events. $($_.Exception.Message)"
        Invoke-Compose exec -T api python -m scripts.seed_demo --output /tmp/demo_store1.jsonl --store-id STORE_BLR_002
        Invoke-Compose exec -T api python -m pipeline.replay /tmp/demo_store1.jsonl --url http://127.0.0.1:8000/events/ingest --speed 100 --batch-size 100
        Invoke-Compose exec -T api python -m scripts.seed_demo --output /tmp/demo_store2.jsonl --store-id STORE_MUM_1076
        Invoke-Compose exec -T api python -m pipeline.replay /tmp/demo_store2.jsonl --url http://127.0.0.1:8000/events/ingest --speed 100 --batch-size 100
    }
}

Write-Step "Checking prerequisites"
Require-Command docker

try {
    docker compose version *> $null
    $script:UseLegacyCompose = $false
} catch {
    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        $script:UseLegacyCompose = $true
    } else {
        throw "Docker Compose is required. Install Docker Desktop with Compose support."
    }
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

if (-not $ApiOnly) {
    $WithCv = $true
}

if ($WithCv) {
    $env:INSTALL_CV = "true"
    Set-DotEnvValue "INSTALL_CV" "true"
    Write-Host "CV dependencies and required model warm-up are enabled. Use -ApiOnly for a lighter API-only setup."
} else {
    $env:INSTALL_CV = "false"
    Set-DotEnvValue "INSTALL_CV" "false"
    Write-Host "API-only mode enabled. Dashboard works; live model detection requires rerun with -WithCv."
}

New-Item -ItemType Directory -Force -Path "data", "outputs", "datasets", "datasets/cctv_footage", ".setup-cache" | Out-Null

if (-not $SkipResourceDownload) {
    foreach ($archive in $StoreArchives) {
        Install-StoreArchive $archive
    }
} else {
    Write-Host "Skipping CCTV resource download."
}

Write-Step "Starting Docker services"
Invoke-Compose up --build -d

$apiPort = Get-DotEnvValue "API_PORT" "8000"
Wait-Api $apiPort
Test-CvRuntime
Warm-RequiredModels
Test-VideoDemoReadiness
Test-VideoDemoHttpStream $apiPort
Initialize-DashboardData $apiPort

Write-Host ""
Write-Host "Setup complete."
Write-Host "Dashboard: http://127.0.0.1:$apiPort/dashboard"
Write-Host "Live detection viewer: http://127.0.0.1:$apiPort/video-demo"
Write-Host "OpenAPI docs: http://127.0.0.1:$apiPort/docs"
Write-Host ""
Write-Host "Useful checks:"
Write-Host "  docker compose ps"
Write-Host "  docker compose logs -f api"
