import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "topteens.db"


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS adolescentes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matricula TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL,
                nascimento TEXT NOT NULL,
                contato TEXT,
                sexo TEXT NOT NULL,
                pai TEXT,
                mae TEXT,
                lider_ga TEXT NOT NULL,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS atividades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                pontos INTEGER NOT NULL CHECK (pontos >= 0),
                descricao TEXT,
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cumprimentos_tarefas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                adolescente_id INTEGER NOT NULL,
                atividade_id INTEGER NOT NULL,
                data_cumprimento TEXT NOT NULL,
                cumpriu INTEGER NOT NULL CHECK (cumpriu IN (0, 1)),
                observacoes TEXT,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(adolescente_id) REFERENCES adolescentes(id) ON DELETE CASCADE,
                FOREIGN KEY(atividade_id) REFERENCES atividades(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS presencas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                adolescente_id INTEGER NOT NULL,
                data_presenca TEXT NOT NULL,
                presente INTEGER NOT NULL CHECK (presente IN (0, 1)),
                pontos INTEGER NOT NULL DEFAULT 5 CHECK (pontos >= 0),
                observacoes TEXT,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(adolescente_id) REFERENCES adolescentes(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_adolescentes_nome ON adolescentes(nome);
            CREATE INDEX IF NOT EXISTS idx_adolescentes_lider_ga ON adolescentes(lider_ga);
            CREATE INDEX IF NOT EXISTS idx_cumprimentos_adolescente ON cumprimentos_tarefas(adolescente_id);
            CREATE INDEX IF NOT EXISTS idx_presencas_adolescente ON presencas(adolescente_id);
            """
        )

        colunas_usuarios = {
            row["name"] for row in connection.execute("PRAGMA table_info(usuarios)").fetchall()
        }
        def adicionar_coluna_se_faltar(nome_coluna, sql):
            if nome_coluna in colunas_usuarios:
                return
            try:
                connection.execute(sql)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

        adicionar_coluna_se_faltar(
            "contato",
            "ALTER TABLE usuarios ADD COLUMN contato TEXT",
        )
        adicionar_coluna_se_faltar(
            "aniversario",
            "ALTER TABLE usuarios ADD COLUMN aniversario TEXT",
        )
        adicionar_coluna_se_faltar(
            "tentativas_falhas",
            "ALTER TABLE usuarios ADD COLUMN tentativas_falhas INTEGER NOT NULL DEFAULT 0",
        )
        adicionar_coluna_se_faltar(
            "bloqueado_ate",
            "ALTER TABLE usuarios ADD COLUMN bloqueado_ate TEXT",
        )
        adicionar_coluna_se_faltar(
            "role",
            "ALTER TABLE usuarios ADD COLUMN role TEXT NOT NULL DEFAULT 'LIDER'",
        )
        adicionar_coluna_se_faltar(
            "aprovado",
            "ALTER TABLE usuarios ADD COLUMN aprovado INTEGER NOT NULL DEFAULT 0",
        )
        adicionar_coluna_se_faltar(
            "lider_ga",
            "ALTER TABLE usuarios ADD COLUMN lider_ga TEXT",
        )
