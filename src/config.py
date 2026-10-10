"""Configuracao: variaveis de ambiente e token da Meta (SSM SecureString, cache em memoria)."""

import os

_token = None


def env(chave, padrao=""):
    return os.environ.get(chave, padrao)


def access_token():
    global _token
    if _token is None:
        import boto3  # import tardio: modulos puros nao dependem de boto3

        resp = boto3.client("ssm").get_parameter(Name=env("ACCESS_TOKEN_PARAM"), WithDecryption=True)
        _token = resp["Parameter"]["Value"]
    return _token
