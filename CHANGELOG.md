# Histórico de alterações

## 0.1.0 - 2026-10-11

Primeira versão do SDK Python aut2fa, com distribuição e importação `aut2fa`:

- Envio, consulta de status e verificação pela API pública
- Respostas com atributos, nomes JSON `snake_case`, valores nulos e campos adicionais
- `ApiError` com status HTTP, código, detalhe, erros de validação e `Retry-After` bruto
- Erros distintos para transporte, timeout e respostas inválidas
- Base HTTP/HTTPS e timeout configuráveis, validação de IDs e chaves de idempotência
- Redirects bloqueados e nenhuma tentativa automática
- Testes HTTP locais, wheel e sdist com licença MIT
- Integração contínua e publicação manual no PyPI via Trusted Publisher

A publicação no PyPI aguarda configuração da conta e do publisher. O código pode ser instalado pelo GitHub ou por um checkout local.
