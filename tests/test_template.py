"""Testes estaticos do template CloudFormation (AC-12, AC-13) e do pacote (NFR-01)."""

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PERMITIDOS = {"AWS::DynamoDB::Table", "AWS::Logs::LogGroup", "AWS::SNS::Topic", "AWS::SNS::Subscription",
              "AWS::IAM::Role", "AWS::Lambda::Function", "AWS::Lambda::EventInvokeConfig", "AWS::Scheduler::Schedule"}


def test_tipos_de_recurso_no_free_tier():
    tipos = set(re.findall(r"^\s+Type:\s+(AWS::\S+)", (RAIZ / "infra/template.yaml").read_text(), re.M))
    assert tipos <= PERMITIDOS, tipos - PERMITIDOS


def test_dynamodb_provisionado_e_sem_pitr():
    t = (RAIZ / "infra/template.yaml").read_text()
    assert "BillingMode: PROVISIONED" in t and "PointInTimeRecovery" not in t


def test_template_sem_segredos():
    t = (RAIZ / "infra/template.yaml").read_text()
    assert not re.search(r"EAA[A-Za-z0-9]{10,}|secret\.", t)


def test_src_plano_sem_dependencias_de_terceiros():
    src = RAIZ / "src"
    assert not [p for p in src.iterdir() if p.is_dir() and p.name != "__pycache__"]
    assert sum(p.stat().st_size for p in src.glob("*.py")) < 100_000
    stdlib_ou_runtime = {"json", "logging", "secrets", "time", "datetime", "zoneinfo", "re", "random", "collections",
                         "decimal", "os", "urllib", "boto3", "botocore", "itertools"}
    locais = {p.stem for p in src.glob("*.py")}
    for p in src.glob("*.py"):
        for m in re.findall(r"^\s*(?:from|import)\s+([a-zA-Z_][\w]*)", p.read_text(encoding="utf-8"), re.M):
            assert m in stdlib_ou_runtime | locais, f"{p.name} importa {m}"
