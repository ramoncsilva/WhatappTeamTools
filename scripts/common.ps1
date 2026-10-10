# Funcoes compartilhadas pelos scripts. Uso: . "$PSScriptRoot\common.ps1"
# Compativel com Windows PowerShell 5.1 e PowerShell 7+.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:AwsExtra = @()

function Read-Properties {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Arquivo nao encontrado: $Path. Copie config/app.properties.example para config/app.properties e preencha."
    }
    $props = [ordered]@{}
    $n = 0
    foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        $n++
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $i = $t.IndexOf('=')
        # Nao ecoa o conteudo da linha: ela pode conter um segredo.
        if ($i -lt 1) { throw "Linha $n de $Path invalida (esperado chave=valor)." }
        $props[$t.Substring(0, $i).Trim()] = $t.Substring($i + 1).Trim()
    }
    return $props
}

function Get-Prop {
    param(
        [Parameter(Mandatory)]$Props,
        [Parameter(Mandatory)][string]$Key,
        [string]$Default = '',
        [switch]$Required
    )
    if ($Props.Contains($Key) -and $Props[$Key] -ne '') { return [string]$Props[$Key] }
    if ($Required) { throw "Propriedade obrigatoria ausente ou vazia: $Key" }
    return $Default
}

function Initialize-Aws {
    param([Parameter(Mandatory)][string]$Region, [string]$ProfileName = '')
    if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
        throw 'AWS CLI v2 nao encontrado no PATH. Instale: https://aws.amazon.com/cli/'
    }
    $script:AwsExtra = @('--region', $Region)
    if ($ProfileName -ne '') { $script:AwsExtra += @('--profile', $ProfileName) }
}

function Invoke-Aws {
    # Executa o AWS CLI e devolve a saida padrao. Lanca excecao se o exit code != 0.
    param([Parameter(Mandatory)][string[]]$CliArgs)
    $all = @($CliArgs) + @($script:AwsExtra)
    # Splatting (@all): no PowerShell 5.1, `& aws $all` pode passar o array como UM argumento.
    $out = & aws @all
    if ($LASTEXITCODE -ne 0) { throw "aws $($CliArgs[0]) $($CliArgs[1]) falhou (exit code $LASTEXITCODE)." }
    return $out
}

function Get-StackOutputs {
    param([Parameter(Mandatory)][string]$StackName, [string[]]$Require = @())
    $json = (Invoke-Aws @('cloudformation', 'describe-stacks', '--stack-name', $StackName,
            '--query', 'Stacks[0].Outputs', '--output', 'json')) -join "`n"
    $map = @{}
    $parsed = $json | ConvertFrom-Json          # `null` (stack sem outputs) vira $null
    if ($null -ne $parsed) {
        foreach ($o in @($parsed)) { $map[$o.OutputKey] = $o.OutputValue }
    }
    foreach ($k in $Require) {
        if (-not $map.ContainsKey($k)) {
            throw "A stack '$StackName' nao tem a output '$k'. Rode scripts\deploy.ps1 (sem -SkipInfra) primeiro."
        }
    }
    return $map
}

function Write-Utf8NoBom {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Text)
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-DrawLambda {
    # Invoca a Lambda de forma sincrona com um payload JSON (string) e devolve o objeto de resposta.
    param([Parameter(Mandatory)][string]$FunctionName, [Parameter(Mandatory)][string]$PayloadJson)
    $buildDir = Join-Path $script:RepoRoot 'build'
    New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
    $inFile = Join-Path $buildDir 'payload.json'
    $outFile = Join-Path $buildDir 'response.json'
    try {
        Write-Utf8NoBom -Path $inFile -Text $PayloadJson
        $meta = (Invoke-Aws @('lambda', 'invoke', '--function-name', $FunctionName,
                '--cli-binary-format', 'raw-in-base64-out', '--cli-read-timeout', '90',
                '--payload', "file://$inFile", $outFile, '--output', 'json')) -join "`n" | ConvertFrom-Json
        $body = Get-Content -LiteralPath $outFile -Raw -Encoding UTF8
        if ($meta.PSObject.Properties.Name -contains 'FunctionError' -and $meta.FunctionError) {
            throw "A Lambda retornou erro ($($meta.FunctionError)): $body"
        }
        return ($body | ConvertFrom-Json)
    }
    finally {
        # O payload pode conter nomes de pessoas; nao deixar copia em disco.
        Remove-Item -LiteralPath $inFile, $outFile -Force -ErrorAction SilentlyContinue
    }
}
