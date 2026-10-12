# aut2fa para Python

Envie, consulte e verifique códigos 2FA pela [API aut2fa](https://doc.aut2fa.com). O SDK usa Python 3.10 ou superior, tem licença MIT e não exige dependências de runtime.

## Instalar pelo GitHub

O código está no [repositório aut2fa-python](https://github.com/jhowbhz/aut2fa-python). A distribuição `aut2fa` ainda aguarda a primeira publicação no PyPI; a conta e o Trusted Publisher precisam ser configurados.

Com Git instalado, instale o código do repositório:

```bash
python -m pip install "git+https://github.com/jhowbhz/aut2fa-python.git"
```

Para instalar um checkout local, execute `python -m pip install .` na raiz. O nome de importação também é `aut2fa`.

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

## Preparar a publicação no PyPI

O workflow `.github/workflows/publish.yml` publica somente por acionamento manual com uma tag Git existente, como `v0.1.0`. Criar uma tag não publica o pacote. O workflow confere a tag contra a versão de `pyproject.toml`, testa e constrói essa tag antes do upload.

Crie a conta PyPI e configure um [Trusted Publisher pendente](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) com estes valores:

| Campo | Valor |
| --- | --- |
| Nome do projeto PyPI | `aut2fa` |
| Proprietário do repositório | `jhowbhz` |
| Repositório | `aut2fa-python` |
| Nome do arquivo do workflow | `publish.yml` |
| Ambiente GitHub | `pypi` |

Crie também o ambiente `pypi` nas configurações do GitHub. O job de upload usa [Trusted Publishing com OpenID Connect (OIDC)](https://docs.pypi.org/trusted-publishers/using-a-publisher/), com `id-token: write`, sem senha ou token PyPI persistente. A publicação inicial continua pendente até configurar essas contas e executar o workflow.

## Licença

O SDK usa a [licença MIT](LICENSE). Consulte o [histórico de alterações](CHANGELOG.md) para acompanhar as versões.
