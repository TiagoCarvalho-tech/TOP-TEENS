# Nova Teens

Aplicação web para controle do desafio `Nova Teens`, com foco em cadastro de adolescentes, lançamento de atividades cumpridas, ranking e gestão de acesso por líderes de GA.

## Funcionalidades

- Cadastro de adolescentes com:
  - nome
  - data de nascimento
  - contato
  - gênero
  - pai e mãe
  - líder de GA
- Geração automática de matrícula
- Edição e exclusão de adolescentes
- Cadastro de atividades com pontuação
- Lançamento de várias atividades de uma só vez em `Cumprimentos`
- Ranking geral
- Ranking por gênero
- Ranking por líder de GA
- Lembrete de aniversários próximos
- Cadastro de líderes com aprovação do usuário master
- Login com controle de acesso
- Troca de senha

## Tecnologias

- Python 3
- Flask
- SQLite
- HTML + CSS

## Estrutura principal

- [TOPTEENS.py](/Users/tiagocarvalho/Library/CloudStorage/OneDrive-Pessoal/TOPTEENS/TOPTEENS.py): aplicação principal e rotas
- [database.py](/Users/tiagocarvalho/Library/CloudStorage/OneDrive-Pessoal/TOPTEENS/database.py): criação e acesso ao banco
- [Adolescente.py](/Users/tiagocarvalho/Library/CloudStorage/OneDrive-Pessoal/TOPTEENS/Adolescente.py): regras e operações de adolescentes
- [Atividade.py](/Users/tiagocarvalho/Library/CloudStorage/OneDrive-Pessoal/TOPTEENS/Atividade.py): atividades e cumprimentos
- [Pontuacao.py](/Users/tiagocarvalho/Library/CloudStorage/OneDrive-Pessoal/TOPTEENS/Pontuacao.py): cálculo de rankings e resumos

## Como rodar localmente

No terminal:

```bash
cd "/Users/tiagocarvalho/Library/CloudStorage/OneDrive-Pessoal/TOPTEENS"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python TOPTEENS.py
```

Depois abra no navegador:

```text
http://127.0.0.1:5000
```

## Acesso inicial

Usuário master padrão:

- usuário: `tio`
- senha inicial: `topteens123`

Importante:

- troque a senha logo no primeiro acesso
- líderes de GA devem criar conta pela tela de cadastro
- o master precisa aprovar essas contas antes do primeiro login

## Atividades padrão

O sistema já inicia com estas atividades:

- Presença: 10
- Meditação: 20
- Bíblia e anotação: 10
- Visitante: 1
- Apps: 40
- Desafio: 40

## Segurança

O projeto inclui:

- proteção CSRF
- bloqueio temporário após tentativas inválidas de login
- sessões com cookies mais seguros
- chave secreta fora do código-fonte
- separação de permissões entre master e líder
- restrição de acesso do líder apenas ao próprio GA

## Publicação

Para disponibilizar online, você pode usar:

- Railway
- Render

Comando de produção:

```bash
gunicorn TOPTEENS:app
```

Variáveis recomendadas:

```bash
TOPTEENS_SECRET_KEY=sua_chave_forte_aqui
TOPTEENS_HTTPS_ONLY=1
```

Observação:

Como o projeto usa `SQLite`, é importante usar armazenamento persistente na hospedagem. Para uso mais robusto em produção, o ideal é migrar depois para `PostgreSQL`.

## Arquivos que não devem subir para o GitHub

Exemplos:

- `.venv/`
- `.secret_key`
- `topteens.db`
- `__pycache__/`
- `*.pyc`

## Status

Projeto finalizado em uma versão funcional para uso e evolução.
