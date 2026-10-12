<p align="center">
  <a href="https://aut2fa.com">
    <img src="https://raw.githubusercontent.com/jhowbhz/aut2fa-python/main/.github/assets/banner.png" alt="aut2fa para Python: você envia o código, a gente entrega por WhatsApp, SMS, Telegram e e-mail" width="100%">
  </a>
</p>

<p align="center">
  <a href="https://pypi.org/project/aut2fa/"><img src="https://img.shields.io/pypi/v/aut2fa?color=00cfc5&label=PyPI" alt="Versão no PyPI"></a>
  <a href="https://pypi.org/project/aut2fa/"><img src="https://img.shields.io/pypi/pyversions/aut2fa?color=3776ab&logo=python&logoColor=white" alt="Versões do Python"></a>
  <a href="https://pepy.tech/project/aut2fa"><img src="https://img.shields.io/pepy/dt/aut2fa?color=00cfc5&label=downloads" alt="Downloads"></a>
  <a href="https://github.com/jhowbhz/aut2fa-python/actions/workflows/ci.yml"><img src="https://github.com/jhowbhz/aut2fa-python/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/dependências-0-00cfc5" alt="Zero dependências">
  <img src="https://img.shields.io/badge/typing-py.typed-3776ab" alt="Tipado com py.typed">
  <a href="LICENSE"><img src="https://img.shields.io/pypi/l/aut2fa?color=00cfc5" alt="Licença MIT"></a>
</p>

<p align="center">
  <b>Envie códigos 2FA por WhatsApp, SMS, Telegram e e-mail com uma chamada de API.</b><br>
  <a href="https://aut2fa.com">Site</a> ·
  <a href="https://doc.aut2fa.com">Documentação</a> ·
  <a href="https://aut2fa.com">Criar conta grátis</a> ·
  <a href="https://github.com/jhowbhz/aut2fa-python/issues">Reportar problema</a>
</p>

---

## Por que usar

- **Um endpoint, quatro canais.** Você chama `send`, e a aut2fa entrega por WhatsApp, SMS, Telegram ou e-mail.
- **Sem gerar nem guardar código.** A API pode gerar o código; você só chama `verify` com o que o usuário digitou.
- **Zero dependências.** Só biblioteca padrão do Python 3.10+. Nada de `requests` no seu ambiente.
- **Tipado.** Inclui `py.typed`, com respostas como objetos e autocompletar no editor.
- **Seguro por padrão.** Bloqueia redirecionamentos, não repete requisições sozinho e valida as entradas antes de chamar a API.
- **Erros claros.** `ApiError`, `NetworkError`, `RequestTimeoutError` e `InvalidResponseError` separam cada tipo de falha.

## Instalar

```bash
pip install aut2fa
```

Também funciona com `uv add aut2fa` e `poetry add aut2fa`.

## Começar em 30 segundos

```python
import os

from aut2fa import Aut2fa

client = Aut2fa(os.environ["AUT2FA_API_KEY"])

# 1. Envia o código para o usuário
send = client.send(to="+5511999999999")

# 2. Confere o código que o usuário digitou
result = client.verify(send.id, code="123456")

if result.valid:
    print("Login liberado")
```

Crie sua conta em [aut2fa.com](https://aut2fa.com) para pegar a chave da aplicação.

## Enviar e verificar um código

Guarde a application key na variável de ambiente `AUT2FA_API_KEY`. O envio sem `code` deixa a API gerar o código:

```python
import os

from aut2fa import Aut2fa

client = Aut2fa(os.environ["AUT2FA_API_KEY"])
send = client.send(to="+5511999999999")
status = client.status(send.id)
print(status.status)

result = client.verify(send.id, code="123456")
if result.valid:
    print("Código verificado")
else:
    print(result.verification, result.attempts_left)
```

`valid=False` com HTTP 200 é um resultado normal. Confirme `result.valid` antes de considerar a verificação concluída.

Para enviar seu próprio código, informe os campos opcionais. Reutilize a mesma chave de idempotência somente para o mesmo envio:

```python
send = client.send(
    to="+5511999999999",
    code="123456",
    locale="pt-BR",
    idempotency_key="checkout-42",
)
```

## Métodos e respostas

O cliente autentica cada chamada com `Authorization: Bearer` e solicita JSON. Os métodos correspondem aos endpoints públicos:

| Método | Endpoint | Retorno |
| --- | --- | --- |
| `send(*, to, code=None, locale=None, idempotency_key=None)` | `POST /v1/send` | `SendResponse` |
| `status(id)` | `GET /v1/send/{id}/status` | `SendResponse` |
| `verify(id, *, code)` | `POST /v1/send/{id}/verify` | `VerificationResponse` |

Leia os campos com atributos, como `send.id`, `send.expires_at` e `result.attempts_left`. As respostas mantêm `snake_case`, preservam `None` e aceitam campos adicionais. Datas permanecem strings JSON, sem conversão para `datetime`.

O campo JSON `from` usa o atributo `send.from_`, pois `from` é uma palavra reservada do Python. `response.to_dict()` devolve um dicionário com os nomes originais, incluindo `from` e campos futuros.

## Configurar conexão e timeout

A base padrão é `https://api.aut2fa.com`, com timeout de 10 segundos. Para um servidor local ou proxy, configure a URL e um timeout positivo e finito:

```python
client = Aut2fa(
    os.environ["AUT2FA_API_KEY"],
    base_url="http://127.0.0.1:8080",
    timeout=5.0,
)
```

O timeout vale para operações de socket, incluindo conexão e leitura; ele não representa um prazo total da chamada. O cliente bloqueia redirects e não realiza retries automáticos. Após um timeout, o envio ou a verificação pode ter sido processado pela API.

A application key e a chave de idempotência não podem estar vazias nem conter caracteres de controle. Idempotência aceita até 255 bytes UTF-8. IDs aceitam letras ASCII, números, `_` e `-`; a base aceita HTTP ou HTTPS sem credenciais, query ou fragmento. Entradas inválidas nessa configuração geram `ValueError` antes da requisição.

`to`, `code` e `locale` aceitam strings; `None` omite os opcionais do envio. Um código numérico gera `ValueError`, evitando perda de zeros à esquerda. A API valida o número de destino, o formato do código e o locale.

## Tratar falhas

Uma rejeição HTTP gera `ApiError`; falhas de transporte e respostas inválidas usam tipos distintos:

```python
from aut2fa import (
    ApiError,
    InvalidResponseError,
    NetworkError,
    RequestTimeoutError,
)

try:
    send = client.send(to="+5511999999999")
except ApiError as error:
    print(error.status, error.code, error.detail)
    print(error.errors, error.retry_after)
except RequestTimeoutError:
    print("A requisição excedeu o timeout configurado")
except NetworkError:
    print("Não foi possível completar a conexão com a API")
except InvalidResponseError as error:
    print("Resposta inválida", error.status)
```

`ApiError.status` contém o status HTTP real, mesmo que o JSON informe outro status. `code`, `detail` e `errors` preservam o problema retornado pela API; quando `detail` estiver ausente, uma mensagem HTTP genérica o substitui. `retry_after` mantém o valor bruto de `Retry-After`, ou `None`. Um corpo de erro não JSON ou inesperado resulta em `code="http_error"`, sem expor seu conteúdo.

`InvalidResponseError` indica JSON inválido, uma resposta que não seja objeto ou ausência dos campos obrigatórios. `NetworkError.__cause__` preserva a falha de transporte. `RequestTimeoutError` também é um `NetworkError` e um `TimeoutError` do Python.

## Testar e construir o pacote

Os testes usam `unittest` e um servidor HTTP local. Eles não chamam a API pública nem enviam mensagens. Em um ambiente virtual ativo, instale o SDK e as ferramentas de desenvolvimento:

```bash
python -m pip install . build twine ruff
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m build
python -m twine check --strict dist/*
```

A integração contínua executa testes em Python 3.10 a 3.14 no Linux e em Python 3.14 no Windows. Ela constrói wheel e sdist, valida os metadados e testa o wheel instalado fora do checkout.

## Publicar novas versões

As versões são publicadas pelo workflow `.github/workflows/publish.yml`, acionado manualmente com uma tag existente, como `v0.1.1`. Ele confere a tag contra a versão do `pyproject.toml`, testa, constrói e envia ao PyPI com [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) via OIDC, sem senha ou token salvo no repositório.

## Outras linguagens

| Linguagem | Pacote | Repositório |
| --- | --- | --- |
| Python | [`aut2fa`](https://pypi.org/project/aut2fa/) | [aut2fa-python](https://github.com/jhowbhz/aut2fa-python) |
| Node.js | [`@aut2fa/node`](https://www.npmjs.com/package/@aut2fa/node) | [aut2fa-node](https://github.com/jhowbhz/aut2fa-node) |
| Go | [`github.com/jhowbhz/aut2fa-go`](https://pkg.go.dev/github.com/jhowbhz/aut2fa-go) | [aut2fa-go](https://github.com/jhowbhz/aut2fa-go) |

## Contribuir

Encontrou um bug ou tem uma ideia? Abra uma [issue](https://github.com/jhowbhz/aut2fa-python/issues) ou envie um pull request. Consulte o [histórico de alterações](CHANGELOG.md) para acompanhar as versões.

Se este SDK te ajudou, deixe uma ⭐ no repositório. Isso ajuda outros devs a encontrá-lo.

---

<p align="center">
  <a href="https://doc.aut2fa.com">Documentação da API</a> · Licença <a href="LICENSE">MIT</a> · Feito pela <a href="https://aut2fa.com">aut2fa</a>
</p>
