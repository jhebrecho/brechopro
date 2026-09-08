# BrechóPro — versão pronta para Railway

Sistema privado para gestão de brechó com login, estoque, fotos, consignantes, clientes, PDV, vendas, repasses, financeiro, relatórios, etiquetas QR e backup.

## Publicação no Railway

1. Envie **os arquivos e pastas que estão dentro desta pasta** para a raiz do repositório `jhebrecho/brechopro` no GitHub. Não envie o ZIP fechado.
2. No Railway, crie um projeto e faça deploy do repositório `jhebrecho/brechopro`, branch `main`.
3. Adicione um volume persistente montado em `/data`.
4. Configure as variáveis:
   - `BRECHOPRO_SECRET`: chave longa e aleatória.
   - `BRECHOPRO_ADMIN_EMAIL`: seu e-mail de acesso.
   - `BRECHOPRO_ADMIN_PASSWORD`: uma senha forte inicial.
   - `BRECHOPRO_STORAGE_DIR=/data`
   - `BRECHOPRO_DEMO_DATA=false`
5. Gere um domínio público no Railway e abra o endereço.

O primeiro usuário administrador é criado somente quando o banco está vazio. Depois do primeiro acesso, você também pode trocar a senha dentro do sistema.

## Segurança

Não envie `.env`, bancos `.db`, fotos de clientes/peças ou backups ao GitHub. O `.gitignore` já evita esses arquivos quando Git é usado normalmente.

## Desenvolvimento local

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Abra `http://127.0.0.1:8000`.
