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
- PostgreSQL
- Psycopg 3
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
export DATABASE_URL="postgresql://USUARIO:SENHA@HOST:5432/NOME_DO_BANCO"
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

Melhor opção para este projeto:

- Render para a aplicação
- Render Postgres para o banco

Comando de produção:

```bash
gunicorn TOPTEENS:app
```

Variáveis recomendadas:

```bash
DATABASE_URL=postgresql://USUARIO:SENHA@HOST:5432/NOME_DO_BANCO
TOPTEENS_SECRET_KEY=sua_chave_forte_aqui
TOPTEENS_HTTPS_ONLY=1
```

### Deploy no Render

O projeto já possui o arquivo [render.yaml](/Users/tiagocarvalho/Library/CloudStorage/OneDrive-Pessoal/TOPTEENS/render.yaml), que prepara:

- um `Web Service`
- um banco `PostgreSQL`
- ligação automática do `DATABASE_URL`
- geração automática da chave secreta

Passo a passo:

1. Envie as alterações mais recentes para o GitHub.
2. Entre em https://render.com
3. Clique em `New +`
4. Escolha `Blueprint`
5. Conecte o repositório `TOP-TEENS`
6. O Render vai ler o `render.yaml`
7. Confirme a criação do serviço web e do banco
8. Aguarde o primeiro deploy
9. Acesse a URL pública gerada pelo Render

Observações importantes:

O projeto agora usa `PostgreSQL` como banco principal, o que é mais adequado para uso online com múltiplos acessos.

- Se o plano `free` não aparecer na sua conta, troque no painel para o plano disponível mais barato.
- Na primeira execução, a aplicação cria automaticamente as tabelas necessárias.
- O usuário master padrão continua sendo `tio`, com a senha inicial `topteens123`, então troque essa senha assim que entrar.

## Arquivos que não devem subir para o GitHub

Exemplos:

- `.venv/`
- `.secret_key`
- `__pycache__/`
- `*.pyc`

## Status

Projeto finalizado em uma versão funcional para uso e evolução.
