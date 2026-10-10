<#
.SYNOPSIS
  Dispara manualmente uma acao da Lambda (sorteio, reenvio ou reversao).

.PARAMETER Action          weekly | resend | revert
.PARAMETER Team            ID do time (opcional em `weekly`: sem ele, todos os times ativos).
.PARAMETER Week            Semana ISO (ex.: 2026-W42). Obrigatoria em `resend`.
.PARAMETER DryRun          So em `weekly`: sorteia e mostra a mensagem, sem gravar nem enviar.
.PARAMETER PropertiesFile  Caminho do .properties (padrao: config/app.properties).

.EXAMPLE
  .\scripts\invoke.ps1 -Action weekly -DryRun
  .\scripts\invoke.ps1 -Action weekly -Team plataforma
  .\scripts\invoke.ps1 -Action resend -Team plataforma -Week 2026-W42
  .\scripts\invoke.ps1 -Action revert -Team plataforma
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('weekly', 'resend', 'revert')][string]$Action,
    [ValidatePattern('^[a-z0-9-]{1,40}$')][string]$Team,
    [ValidatePattern('^\d{4}-W\d{2}$')][string]$Week,
    [switch]$DryRun,
    [string]$PropertiesFile = (Join-Path (Split-Path -Parent $PSScriptRoot) 'config\app.properties')
)

. "$PSScriptRoot\common.ps1"

if ($Action -eq 'resend' -and (-not $Team -or -not $Week)) { throw '-Action resend exige -Team e -Week.' }
if ($Action -eq 'revert' -and -not $Team) { throw '-Action revert exige -Team.' }
if ($DryRun -and $Action -ne 'weekly') { throw '-DryRun so vale para -Action weekly.' }

$evt = [ordered]@{ action = $Action }
if ($Team)   { $evt['team'] = $Team }
if ($Week)   { $evt['week'] = $Week }
if ($DryRun) { $evt['dry_run'] = $true }

$props = Read-Properties -Path $PropertiesFile
Initialize-Aws -Region (Get-Prop $props 'aws.region' -Required) -ProfileName (Get-Prop $props 'aws.profile')
$outputs = Get-StackOutputs -StackName (Get-Prop $props 'stack.name' -Required) -Require 'FunctionName'

$result = Invoke-DrawLambda -FunctionName $outputs['FunctionName'] -PayloadJson ($evt | ConvertTo-Json -Compress)
$result | ConvertTo-Json -Depth 10
