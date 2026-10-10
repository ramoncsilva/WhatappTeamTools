<#
.SYNOPSIS
  Sincroniza o projeto com a AWS: stack CloudFormation, segredo no SSM e codigo da Lambda.

.DESCRIPTION
  1. Le config/app.properties
  2. Cria/atualiza a stack (infra/template.yaml)
  3. Grava secret.* no SSM Parameter Store como SecureString
  4. Empacota src/*.py (layout plano) e publica na Lambda (sem S3)

  E idempotente: pode ser executado quantas vezes quiser.

.PARAMETER PropertiesFile  Caminho do .properties (padrao: config/app.properties).
.PARAMETER SkipInfra       Nao executa o passo 2.
.PARAMETER SkipSecrets     Nao executa o passo 3.
.PARAMETER SkipCode        Nao executa o passo 4.

.EXAMPLE
  .\scripts\deploy.ps1
  .\scripts\deploy.ps1 -SkipInfra -SkipSecrets     # so republica o codigo
#>
[CmdletBinding()]
param(
    [string]$PropertiesFile = (Join-Path (Split-Path -Parent $PSScriptRoot) 'config\app.properties'),
    [switch]$SkipInfra,
    [switch]$SkipSecrets,
    [switch]$SkipCode
)

. "$PSScriptRoot\common.ps1"

$props = Read-Properties -Path $PropertiesFile
$region = Get-Prop $props 'aws.region' -Required
$stack  = Get-Prop $props 'stack.name' -Required
Initialize-Aws -Region $region -ProfileName (Get-Prop $props 'aws.profile')

$who = (Invoke-Aws @('sts', 'get-caller-identity', '--query', 'Arn', '--output', 'text')) -join ''
Write-Host "Conta/identidade AWS: $who  |  regiao: $region  |  stack: $stack"

# ---------------------------------------------------------------- 2. Infra
if (-not $SkipInfra) {
    Write-Host "`n[1/3] CloudFormation (infra/template.yaml)"
    $overrides = @(
        "AlertEmail=$(Get-Prop $props 'alert.email' -Required)",
        "ScheduleExpression=$(Get-Prop $props 'schedule.expression' 'cron(0 9 ? * MON *)')",
        "ScheduleTimezone=$(Get-Prop $props 'schedule.timezone' 'America/Sao_Paulo')",
        "ScheduleState=$(Get-Prop $props 'schedule.state' 'ENABLED')",
        "WhatsappApiVersion=$(Get-Prop $props 'whatsapp.api.version' 'v25.0')",
        "WhatsappPhoneNumberId=$(Get-Prop $props 'whatsapp.phone.number.id' -Required)",
        "WhatsappSendMode=$(Get-Prop $props 'whatsapp.send.mode' 'auto')",
        "WhatsappTemplateName=$(Get-Prop $props 'whatsapp.template.name')",
        "WhatsappTemplateLanguage=$(Get-Prop $props 'whatsapp.template.language' 'pt_BR')",
        "DrawMaxAttempts=$(Get-Prop $props 'draw.max.attempts' '200')",
        "LogRetentionDays=$(Get-Prop $props 'log.retention.days' '30')"
    )
    $template = Join-Path $RepoRoot 'infra\template.yaml'
    Invoke-Aws (@('cloudformation', 'deploy', '--template-file', $template, '--stack-name', $stack,
            '--capabilities', 'CAPABILITY_IAM', '--no-fail-on-empty-changeset',
            '--tags', 'project=whatsapp-team-draw', '--parameter-overrides') + $overrides) | Out-Host
}
else { Write-Host "`n[1/3] CloudFormation: ignorado (-SkipInfra)" }

$outputs = Get-StackOutputs -StackName $stack -Require 'FunctionName', 'AccessTokenParameterName'

# ---------------------------------------------------------------- 3. Segredos
if (-not $SkipSecrets) {
    Write-Host "`n[2/3] Segredos -> SSM Parameter Store (SecureString)"
    # Hoje ha um unico segredo. Novos segredos: mapear secret.<nome> para um parametro em /<stack>/...
    $token = Get-Prop $props 'secret.whatsapp.access.token'
    if ($token -eq '') {
        Write-Warning 'secret.whatsapp.access.token vazio: o parametro SSM NAO foi atualizado. A Lambda nao conseguira enviar mensagens.'
    }
    else {
        # O valor vai na linha de comando do aws.exe (visivel a processos locais durante a chamada)
        # e nunca e impresso. Standard tier + chave aws/ssm = gratuito.
        Invoke-Aws @('ssm', 'put-parameter', '--name', $outputs['AccessTokenParameterName'],
            '--type', 'SecureString', '--overwrite', '--value', $token) | Out-Null
        Write-Host "  gravado: $($outputs['AccessTokenParameterName'])"
    }
}
else { Write-Host "`n[2/3] Segredos: ignorado (-SkipSecrets)" }

# ---------------------------------------------------------------- 4. Codigo
if (-not $SkipCode) {
    Write-Host "`n[3/3] Codigo da Lambda (src/ -> $($outputs['FunctionName']))"
    $srcDir = Join-Path $RepoRoot 'src'
    if (-not (Test-Path (Join-Path $srcDir 'index.py'))) {
        throw 'src/index.py nao existe. Implemente a Lambda (ver specs/001-sorteio-semanal/tasks.md) ou use -SkipCode.'
    }
    $buildDir = Join-Path $RepoRoot 'build'
    $zip = Join-Path $buildDir 'lambda.zip'
    New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue

    # Layout PLANO e so *.py: o Compress-Archive do Windows PowerShell 5.1 grava separadores "\"
    # em subpastas, o que quebra o import no Linux da Lambda.
    $files = @(Get-ChildItem -LiteralPath $srcDir -File -Filter '*.py')
    Compress-Archive -LiteralPath $files.FullName -DestinationPath $zip -CompressionLevel Optimal
    $kb = [math]::Round((Get-Item $zip).Length / 1KB, 1)
    Write-Host "  pacote: $kb KB ($($files.Count) arquivos)"
    if ($kb -gt 100) { Write-Warning 'Pacote acima de 100 KB (NFR-01). Revise o que esta em src/.' }

    Invoke-Aws @('lambda', 'update-function-code', '--function-name', $outputs['FunctionName'],
        '--zip-file', "fileb://$zip", '--query', 'LastUpdateStatus', '--output', 'text') | Out-Null
    Invoke-Aws @('lambda', 'wait', 'function-updated', '--function-name', $outputs['FunctionName']) | Out-Null
    Write-Host '  codigo publicado.'
}
else { Write-Host "`n[3/3] Codigo: ignorado (-SkipCode)" }

Write-Host @"

Pronto. Proximos passos:
  1. Confirme a inscricao no e-mail de alerta (SNS) enviado para $(Get-Prop $props 'alert.email').
  2. Copie data\roster.example.json para data\roster.json, edite e rode:  .\scripts\sync-roster.ps1
  3. Teste sem enviar nada:  .\scripts\invoke.ps1 -Action weekly -DryRun
"@
