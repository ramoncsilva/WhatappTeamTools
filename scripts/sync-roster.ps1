<#
.SYNOPSIS
  Sincroniza times, pessoas e tarefas (data/roster.json) com o banco na AWS.

.DESCRIPTION
  Envia o arquivo inteiro para a acao `sync_roster` da Lambda, que aplica as regras de dominio
  (quem entra ganha contador 0 para toda tarefa; quem sai e inativado, nunca apagado).
  Declarativo e idempotente: o arquivo descreve o estado desejado.

.PARAMETER RosterFile      Caminho do JSON (padrao: data/roster.json).
.PARAMETER PropertiesFile  Caminho do .properties (padrao: config/app.properties).
.PARAMETER DryRun          Mostra o que mudaria, sem gravar.

.EXAMPLE
  .\scripts\sync-roster.ps1 -DryRun
  .\scripts\sync-roster.ps1
#>
[CmdletBinding()]
param(
    [string]$RosterFile = (Join-Path (Split-Path -Parent $PSScriptRoot) 'data\roster.json'),
    [string]$PropertiesFile = (Join-Path (Split-Path -Parent $PSScriptRoot) 'config\app.properties'),
    [switch]$DryRun
)

. "$PSScriptRoot\common.ps1"

if (-not (Test-Path -LiteralPath $RosterFile)) {
    throw "Roster nao encontrado: $RosterFile. Copie data\roster.example.json para data\roster.json e edite."
}
$rosterRaw = Get-Content -LiteralPath $RosterFile -Raw -Encoding UTF8
try { $null = $rosterRaw | ConvertFrom-Json } catch { throw "JSON invalido em ${RosterFile}: $($_.Exception.Message)" }

$props = Read-Properties -Path $PropertiesFile
Initialize-Aws -Region (Get-Prop $props 'aws.region' -Required) -ProfileName (Get-Prop $props 'aws.profile')
$outputs = Get-StackOutputs -StackName (Get-Prop $props 'stack.name' -Required) -Require 'FunctionName'

# O JSON do roster e embutido como texto (sem reserializar) para preservar acentos e estrutura.
$dry = if ($DryRun) { 'true' } else { 'false' }
$payload = '{"action":"sync_roster","dry_run":' + $dry + ',"roster":' + $rosterRaw + '}'

Write-Host "Sincronizando $RosterFile -> $($outputs['FunctionName'])$(if ($DryRun) { ' (dry run)' })"
$result = Invoke-DrawLambda -FunctionName $outputs['FunctionName'] -PayloadJson $payload
$result | ConvertTo-Json -Depth 10
