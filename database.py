from os import environ

import psycopg
from psycopg.rows import dict_row


def get_database_url():
    database_url = environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "Defina a variável de ambiente DATABASE_URL com a conexão do PostgreSQL."
        )
    return database_url


def get_connection():
    return psycopg.connect(get_database_url(), row_factory=dict_row)


def init_db():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    contato TEXT,
                    aniversario TEXT,
                    username TEXT NOT NULL UNIQUE,
                    senha_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'LIDER',
                    aprovado INTEGER NOT NULL DEFAULT 0,
                    lider_ga TEXT,
                    tentativas_falhas INTEGER NOT NULL DEFAULT 0,
                    bloqueado_ate TEXT,
                    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS adolescentes (
                    id SERIAL PRIMARY KEY,
                    matricula TEXT NOT NULL UNIQUE,
                    nome TEXT NOT NULL,
                    nascimento TEXT NOT NULL,
                    contato TEXT,
                    sexo TEXT NOT NULL,
                    pai TEXT,
                    mae TEXT,
                    lider_ga TEXT NOT NULL,
                    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS atividades (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    pontos INTEGER NOT NULL CHECK (pontos >= 0),
                    descricao TEXT,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cumprimentos_tarefas (
                    id SERIAL PRIMARY KEY,
                    adolescente_id INTEGER NOT NULL REFERENCES adolescentes(id) ON DELETE CASCADE,
                    atividade_id INTEGER NOT NULL REFERENCES atividades(id) ON DELETE CASCADE,
                    data_cumprimento TEXT NOT NULL,
                    cumpriu INTEGER NOT NULL CHECK (cumpriu IN (0, 1)),
                    observacoes TEXT,
                    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS auditoria_eventos (
                    id SERIAL PRIMARY KEY,
                    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
                    tipo_evento TEXT NOT NULL,
                    alvo_tipo TEXT NOT NULL,
                    alvo_id INTEGER,
                    detalhes TEXT,
                    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_adolescentes_nome
                ON adolescentes(nome)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_adolescentes_lider_ga
                ON adolescentes(lider_ga)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cumprimentos_adolescente
                ON cumprimentos_tarefas(adolescente_id)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_auditoria_usuario
                ON auditoria_eventos(usuario_id, criado_em DESC)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_auditoria_evento
                ON auditoria_eventos(tipo_evento, criado_em DESC)
                """
            )

            cursor.execute(
                "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS contato TEXT"
            )
            cursor.execute(
                "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS aniversario TEXT"
            )
            cursor.execute(
                "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS tentativas_falhas INTEGER NOT NULL DEFAULT 0"
            )
            cursor.execute(
                "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bloqueado_ate TEXT"
            )
            cursor.execute(
                "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'LIDER'"
            )
            cursor.execute(
                "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS aprovado INTEGER NOT NULL DEFAULT 0"
            )
            cursor.execute(
                "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS lider_ga TEXT"
            )
            cursor.execute(
                "ALTER TABLE cumprimentos_tarefas ADD COLUMN IF NOT EXISTS falta_justificada INTEGER NOT NULL DEFAULT 0"
            )
